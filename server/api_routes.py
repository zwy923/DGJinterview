"""
API路由模块
"""
from fastapi import APIRouter, HTTPException

from utils.schemas import (
    GPTRequest, GPTResponse,
    ChatHistoryRequest, ChatHistoryResponse,
    InterviewAnalysisRequest, InterviewAnalysisResponse
)
from storage.dao import transcript_dao
from nlp.llm_api import llm_api
from logs import setup_logger

logger = setup_logger(__name__)

# 创建路由器
router = APIRouter()


@router.post("/gpt", response_model=GPTResponse)
async def ask_gpt(request: GPTRequest):
    """GPT问答接口"""
    try:
        reply = await llm_api.generate(request.prompt, stream=request.stream)
        return GPTResponse(reply=reply)
    except Exception as e:
        logger.error(f"GPT问答失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/save", response_model=ChatHistoryResponse)
async def save_chat_message_api(request: ChatHistoryRequest):
    """保存聊天消息到后端"""
    try:
        await transcript_dao.save_transcript(
            session_id=request.session_id,
            speaker=request.message.speaker,
            content=request.message.content
        )
        return ChatHistoryResponse(success=True, message="消息保存成功")
    except Exception as e:
        logger.error(f"保存消息失败: {e}")
        return ChatHistoryResponse(success=False, message=f"保存失败: {str(e)}")


@router.get("/chat/history/{session_id}")
async def get_chat_history_api(session_id: str):
    """获取会话聊天记录"""
    try:
        transcripts = await transcript_dao.get_transcripts(session_id)
        return {"messages": transcripts}
    except Exception as e:
        logger.error(f"获取聊天记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/stats/{session_id}")
async def get_chat_stats_api(session_id: str):
    """获取会话统计信息"""
    try:
        transcripts = await transcript_dao.get_transcripts(session_id)
        
        user_count = sum(1 for t in transcripts if t.get("speaker") == "user")
        interviewer_count = sum(1 for t in transcripts if t.get("speaker") == "interviewer")
        system_count = sum(1 for t in transcripts if t.get("speaker") == "system")
        
        return {
            "total_messages": len(transcripts),
            "user_messages": user_count,
            "interviewer_messages": interviewer_count,
            "system_messages": system_count,
            "last_activity": transcripts[-1].get("timestamp") if transcripts else None
        }
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gpt/analyze", response_model=InterviewAnalysisResponse)
async def analyze_interview(request: InterviewAnalysisRequest):
    """分析面试表现"""
    try:
        if request.type != "interview_analysis":
            raise HTTPException(status_code=400, detail="Invalid analysis type")
        
        # 获取transcripts（从request.data或request.session_id）
        session_id = request.session_id or request.data.get("sessionId", "unknown")
        transcripts = await transcript_dao.get_transcripts(session_id)
        
        if not transcripts:
            raise HTTPException(status_code=404, detail="未找到聊天记录")
        
        # 构建对话历史
        chat_history = "\n".join([
            f"{t.get('speaker', 'unknown')}: {t.get('content', '')}"
            for t in transcripts
        ])
        
        # 使用LLM进行分析
        prompt = f"""请分析以下面试对话，提供专业的反馈。

面试对话记录：
{chat_history}

请从以下维度进行分析：
1. 回答的逻辑性和完整性
2. 技术深度和准确性
3. 沟通表达能力
4. 需要改进的地方

请提供详细的分析报告。"""
        
        analysis_text = await llm_api.generate(prompt)
        
        # 解析分析结果（简化版，实际应该使用JSON schema）
        return InterviewAnalysisResponse(
            analysis={"raw": analysis_text},
            summary=analysis_text[:200] + "..." if len(analysis_text) > 200 else analysis_text,
            recommendations=[
                "建议增加技术深度讨论",
                "可以多分享项目经验",
                "注意回答的逻辑性和完整性"
            ]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分析面试失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
