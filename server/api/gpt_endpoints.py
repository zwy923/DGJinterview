"""
GPT端点（HTTP+SSE）
"""
import asyncio
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal

from core.state import SessionState
from core.config import agent_settings
from agents.answer_agent import AnswerAgent
from storage.dao import cv_dao, job_position_dao
from utils.sse import sse_response
from ws.ws_audio import _sessions
from logs import setup_logger

logger = setup_logger(__name__)

router = APIRouter()


class GPTRequest(BaseModel):
    """GPT请求体"""
    text: str
    session_id: Optional[str] = None


@router.get("/api/gpt")
async def gpt_endpoint(
    brief: bool = Query(False, description="是否快答模式"),
    session_id: Optional[str] = Query(None, description="会话ID")
):
    """
    GPT端点（支持SSE流式返回）
    
    Args:
        brief: 是否快答模式（true=快答，false=正常）
        session_id: 会话ID（可选）
    
    Returns:
        SSE流式响应
    """
    # 从query参数获取问题（临时方案）
    # 更好的方案是使用POST请求
    raise HTTPException(status_code=400, detail="请使用POST请求并提供问题文本")


@router.post("/api/gpt")
async def gpt_endpoint_post(
    request: GPTRequest,
    brief: bool = Query(False, description="是否快答模式")
):
    """
    GPT端点（POST，支持SSE流式返回）
    
    Args:
        request: 请求体（包含text和可选的session_id）
        brief: 是否快答模式
    
    Returns:
        SSE流式响应
    """
    question = request.text
    session_id = request.session_id or "default"
    
    if not question:
        raise HTTPException(status_code=400, detail="问题文本不能为空")
    
    # 获取会话状态（如果不存在则创建临时会话）
    state: Optional[SessionState] = None
    if session_id:
        session_key_mic = f"{session_id}_mic"
        session_key_sys = f"{session_id}_sys"
        state = _sessions.get(session_key_mic) or _sessions.get(session_key_sys)
    
    # 如果会话不存在，创建临时会话状态（不持久化到_sessions）
    if not state:
        logger.info(f"会话 {session_id} 不存在，创建临时会话状态")
        state = SessionState(sid=session_id, source="mic")
    
    # 获取CV和JD
    cv_text = state.cv_text or ""
    jd_text = state.jd_text or ""
    
    # 如果state中没有，尝试从数据库获取
    if not cv_text:
        try:
            cv_info = await cv_dao.get_default_cv()
            if cv_info:
                cv_text = cv_info.get("content", "")
                if cv_text:
                    state.cv_text = cv_text
                    logger.info(f"从数据库加载CV，长度: {len(cv_text)}")
                else:
                    logger.warning("数据库中的CV内容为空")
            else:
                logger.warning("数据库中未找到CV")
        except Exception as e:
            logger.error(f"获取CV失败: {e}", exc_info=True)
    
    if not jd_text:
        try:
            job_info = await job_position_dao.get_job_position_by_session(session_id or "default")
            if job_info:
                jd_text = job_info.get("content", "")
                state.jd_text = jd_text
        except Exception as e:
            logger.warning(f"获取JD失败: {e}")
    
    # 创建Agent
    agent = AnswerAgent(state, cv_text, jd_text)
    
    mode: Literal["brief", "full"] = "brief" if brief else "full"
    
    # 创建异步生成器（真正的流式输出）
    async def answer_generator():
        # 使用队列实现真正的流式传输
        queue = asyncio.Queue()
        error_occurred = False
        error_message = None
        
        async def stream_callback(chunk: str):
            """流式回调：将chunk放入队列"""
            if not error_occurred:
                await queue.put(('chunk', chunk))
        
        async def generate_task():
            """生成任务：在后台运行，将chunks放入队列"""
            nonlocal error_occurred, error_message
            try:
                await agent.generate_answer(
                    question=question,
                    mode=mode,
                    stream_callback=stream_callback
                )
            except Exception as e:
                error_occurred = True
                error_message = str(e)
                logger.error(f"生成答案时出错: {e}", exc_info=True)
            finally:
                await queue.put(('done', None))  # 发送结束信号
        
        # 启动生成任务（后台运行）
        task = asyncio.create_task(generate_task())
        
        # 从队列中取出chunks并yield（真正的流式）
        while True:
            try:
                # 使用超时避免永久阻塞
                item_type, item = await asyncio.wait_for(queue.get(), timeout=300.0)
                
                if item_type == 'chunk':
                    yield item
                elif item_type == 'done':
                    # 检查是否有错误
                    if error_occurred:
                        logger.error(f"生成过程中发生错误: {error_message}")
                    break
            except asyncio.TimeoutError:
                logger.error("流式生成超时")
                break
            except Exception as e:
                logger.error(f"流式生成异常: {e}", exc_info=True)
                break
        
        # 确保任务完成
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    return await sse_response(answer_generator())
