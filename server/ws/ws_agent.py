"""
WebSocket Agent端点
手动触发回答
"""
import json
from typing import Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

from core.state import SessionState
from core.config import agent_settings
from agents.answer_agent import AnswerAgent
from storage.dao import cv_dao, job_position_dao
from logs import setup_logger

logger = setup_logger(__name__)

# 会话管理（从ws_audio导入）
from ws.ws_audio import _sessions


async def handle_agent_websocket(ws: WebSocket, session_id: str):
    """
    处理Agent WebSocket连接
    
    Args:
        ws: WebSocket连接
        session_id: 会话ID
    """
    await ws.accept()
    logger.info(f"Agent WebSocket连接已建立: {session_id}")
    
    try:
        # 获取会话状态
        session_key_mic = f"{session_id}_mic"
        session_key_sys = f"{session_id}_sys"
        state: SessionState = _sessions.get(session_key_mic) or _sessions.get(session_key_sys)
        
        if not state:
            await ws.send_json({
                "type": "error",
                "message": "会话未找到，请先建立音频WebSocket连接"
            })
            await ws.close()
            return
        
        # 获取CV和JD
        cv_text = state.cv_text or ""
        jd_text = state.jd_text or ""
        
        # 如果state中没有，尝试从数据库获取
        if not cv_text:
            try:
                cv_info = await cv_dao.get_default_cv()
                if cv_info:
                    cv_text = cv_info.get("content", "")
                    state.cv_text = cv_text
            except Exception as e:
                logger.warning(f"获取CV失败: {e}")
        
        if not jd_text:
            try:
                job_info = await job_position_dao.get_job_position_by_session(session_id)
                if job_info:
                    jd_text = job_info.get("content", "")
                    state.jd_text = jd_text
            except Exception as e:
                logger.warning(f"获取JD失败: {e}")
        
        # 创建Agent
        agent = AnswerAgent(state, cv_text, jd_text)
        
        # 流式回调函数
        async def stream_callback(chunk: str):
            await ws.send_json({
                "type": "stream",
                "role": "assistant",
                "delta": chunk
            })
        
        # 处理消息
        while True:
            try:
                data = await ws.receive_text()
                message = json.loads(data)
                
                msg_type = message.get("type")
                if msg_type == "answer":
                    mode = message.get("mode", "full")  # brief 或 full
                    question = message.get("text", "")
                    
                    if not question:
                        await ws.send_json({
                            "type": "error",
                            "message": "问题文本不能为空"
                        })
                        continue
                    
                    # 生成回答
                    await agent.generate_answer(
                        question=question,
                        mode=mode,
                        stream_callback=stream_callback
                    )
                    
                    # 发送完成信号
                    await ws.send_json({
                        "type": "final",
                        "role": "assistant",
                        "done": True
                    })
                else:
                    await ws.send_json({
                        "type": "error",
                        "message": f"未知消息类型: {msg_type}"
                    })
            
            except WebSocketDisconnect:
                logger.info(f"Agent WebSocket连接已断开: {session_id}")
                break
            except json.JSONDecodeError:
                await ws.send_json({
                    "type": "error",
                    "message": "无效的JSON格式"
                })
            except Exception as e:
                logger.error(f"处理Agent消息失败: {e}")
                await ws.send_json({
                    "type": "error",
                    "message": str(e)
                })
    
    except Exception as e:
        logger.error(f"Agent WebSocket处理失败: {e}")
        try:
            await ws.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
        await ws.close()

