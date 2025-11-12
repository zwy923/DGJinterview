"""
GPT端点（HTTP+SSE）
"""
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
                state.cv_text = cv_text
        except Exception as e:
            logger.warning(f"获取CV失败: {e}")
    
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
    
    # 创建异步生成器
    async def answer_generator():
        # 使用队列收集流式输出
        chunks = []
        
        async def stream_callback(chunk: str):
            chunks.append(chunk)
        
        # 生成答案（会调用stream_callback）
        await agent.generate_answer(
            question=question,
            mode=mode,
            stream_callback=stream_callback
        )
        
        # 将收集的chunks yield出去
        for chunk in chunks:
            yield chunk
    
    return await sse_response(answer_generator())
