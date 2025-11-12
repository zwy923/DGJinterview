"""
API路由模块（仅保留语音识别相关功能）
"""
import asyncio
from fastapi import APIRouter, HTTPException

from utils.schemas import (
    ChatHistoryRequest, ChatHistoryResponse,
    CVRequest, CVResponse,
    JobPositionRequest, JobPositionResponse,
    KnowledgeBaseRequest, KnowledgeBaseResponse
)
from storage.dao import transcript_dao, cv_dao, job_position_dao, kb_dao
from logs import setup_logger

logger = setup_logger(__name__)

# 创建路由器
router = APIRouter()


# =====================================================
# 聊天记录相关接口
# =====================================================

@router.post("/chat/save", response_model=ChatHistoryResponse)
async def save_chat_message_api(request: ChatHistoryRequest):
    """保存聊天消息到内存（不保存到数据库）"""
    try:
        # 延迟导入，避免循环导入
        from ws.ws_audio import _sessions
        
        # 获取会话状态
        session_key = f"{request.session_id}_mic"
        session_state = _sessions.get(session_key) if _sessions else None
        if not session_state:
            session_key = f"{request.session_id}_sys"
            session_state = _sessions.get(session_key) if _sessions else None
        
        if session_state:
            # 直接添加到内存历史（不生成embedding）
            session_state.add_to_history(
                content=request.message.content,
                speaker=request.message.speaker,
                timestamp=request.message.timestamp
            )
            return ChatHistoryResponse(success=True, message="消息已添加到内存")
        else:
            return ChatHistoryResponse(success=False, message="会话未找到，请先建立WebSocket连接")
    except ValueError as e:
        logger.error(f"保存消息参数错误: {e}")
        return ChatHistoryResponse(success=False, message=f"参数错误: {str(e)}")
    except Exception as e:
        logger.exception("保存消息失败")
        return ChatHistoryResponse(success=False, message="保存失败，请稍后重试")


@router.get("/chat/history/{session_id}")
async def get_chat_history_api(session_id: str):
    """获取会话聊天记录（从内存）"""
    try:
        # 延迟导入，避免循环导入
        from ws.ws_audio import _sessions
        
        # 获取会话状态
        session_key = f"{session_id}_mic"
        session_state = _sessions.get(session_key) if _sessions else None
        if not session_state:
            session_key = f"{session_id}_sys"
            session_state = _sessions.get(session_key) if _sessions else None
        
        if session_state and hasattr(session_state, "get_history_with_embeddings"):
            history = session_state.get_history_with_embeddings()
            # 转换为API格式
            messages = []
            for item in history:
                messages.append({
                    "id": item.get("timestamp", ""),
                    "speaker": item.get("speaker", "unknown"),
                    "content": item.get("content", ""),
                    "timestamp": item.get("timestamp", ""),
                    "type": "text"
                })
            return {"messages": messages}
        else:
            return {"messages": []}
    except ValueError as e:
        logger.error(f"获取聊天记录参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("获取聊天记录失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/chat/stats/{session_id}")
async def get_chat_stats_api(session_id: str):
    """获取会话统计信息（从内存）"""
    try:
        # 延迟导入，避免循环导入
        from ws.ws_audio import _sessions
        
        # 获取会话状态
        session_key = f"{session_id}_mic"
        session_state = _sessions.get(session_key) if _sessions else None
        if not session_state:
            session_key = f"{session_id}_sys"
            session_state = _sessions.get(session_key) if _sessions else None
        
        if session_state and hasattr(session_state, "get_history_with_embeddings"):
            history = session_state.get_history_with_embeddings()
            
            user_count = sum(1 for h in history if h.get("speaker") == "user")
            interviewer_count = sum(1 for h in history if h.get("speaker") == "interviewer")
            system_count = sum(1 for h in history if h.get("speaker") == "system")
            
            return {
                "total_messages": len(history),
                "user_messages": user_count,
                "interviewer_messages": interviewer_count,
                "system_messages": system_count,
                "last_activity": history[-1].get("timestamp") if history else None
            }
        else:
            return {
                "total_messages": 0,
                "user_messages": 0,
                "interviewer_messages": 0,
                "system_messages": 0,
                "last_activity": None
            }
    except ValueError as e:
        logger.error(f"获取统计信息参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("获取统计信息失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


# =====================================================
# CV相关接口（保留，但移除embedding生成）
# =====================================================

@router.post("/cv", response_model=CVResponse)
async def save_cv_api(request: CVRequest):
    """上传/更新CV（支持幂等性：同一user_id会更新而非创建新记录）"""
    try:
        # 验证输入
        if not request.user_id or not request.content:
            raise HTTPException(status_code=400, detail="user_id和content不能为空")
        
        # 检查PostgreSQL是否可用
        from storage.pg import pg_pool
        if not pg_pool.pool:
            raise HTTPException(
                status_code=503,
                detail="PostgreSQL未连接，无法保存CV。请检查PostgreSQL服务是否运行，并查看服务器日志获取详细信息。"
            )
        
        # 保存CV（不生成embedding）
        cv_id = await cv_dao.save_cv(
            user_id=request.user_id,
            content=request.content,
            embedding=None,  # 不再生成embedding
            metadata=request.metadata
        )
        
        if cv_id == 0:
            raise HTTPException(status_code=500, detail="保存CV失败（PostgreSQL可能未正确初始化）")
        
        # 获取保存的CV
        cv = await cv_dao.get_cv_by_user_id(request.user_id)
        if not cv:
            raise HTTPException(status_code=404, detail="CV未找到")
        
        # 使用model_validate确保类型安全
        return CVResponse.model_validate(cv)
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"保存CV参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("保存CV失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/cv/{user_id}", response_model=CVResponse)
async def get_cv_api(user_id: str):
    """获取CV"""
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id不能为空")
        
        cv = await cv_dao.get_cv_by_user_id(user_id)
        if not cv:
            raise HTTPException(status_code=404, detail="CV未找到")
        
        # 使用model_validate确保类型安全
        return CVResponse.model_validate(cv)
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"获取CV参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("获取CV失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


# =====================================================
# 岗位信息相关接口（保留，但移除embedding生成）
# =====================================================

@router.post("/job-position", response_model=JobPositionResponse)
async def save_job_position_api(request: JobPositionRequest):
    """创建/更新岗位信息（支持幂等性：同一session_id会更新而非创建新记录）"""
    try:
        # 验证输入
        if not request.session_id or not request.title:
            raise HTTPException(status_code=400, detail="session_id和title不能为空")
        
        # 保存岗位信息（不生成embedding）
        job_id = await job_position_dao.save_job_position(
            session_id=request.session_id,
            title=request.title,
            description=request.description,
            requirements=request.requirements,
            embedding=None,  # 不再生成embedding
            metadata=request.metadata
        )
        
        if job_id == 0:
            raise HTTPException(status_code=500, detail="保存岗位信息失败")
        
        # 获取保存的岗位信息
        job = await job_position_dao.get_job_position_by_session(request.session_id)
        if not job:
            raise HTTPException(status_code=404, detail="岗位信息未找到")
        
        # 使用model_validate确保类型安全
        return JobPositionResponse.model_validate(job)
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"保存岗位信息参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("保存岗位信息失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/job-position/{session_id}", response_model=JobPositionResponse)
async def get_job_position_api(session_id: str):
    """获取岗位信息"""
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id不能为空")
        
        job = await job_position_dao.get_job_position_by_session(session_id)
        if not job:
            raise HTTPException(status_code=404, detail="岗位信息未找到")
        
        # 使用model_validate确保类型安全
        return JobPositionResponse.model_validate(job)
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"获取岗位信息参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("获取岗位信息失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


# =====================================================
# 知识库相关接口（保留，但移除embedding生成）
# =====================================================

@router.post("/knowledge-base", response_model=KnowledgeBaseResponse)
async def save_knowledge_base_api(request: KnowledgeBaseRequest):
    """添加知识库条目（按session）"""
    try:
        # 验证输入
        if not request.session_id or not request.title or not request.content:
            raise HTTPException(status_code=400, detail="session_id、title和content不能为空")
        
        # 保存知识库条目（不生成embedding）
        kb_id = await kb_dao.save_knowledge(
            title=request.title,
            content=request.content,
            embedding=None,  # 不再生成embedding
            metadata=request.metadata,
            session_id=request.session_id
        )
        
        if kb_id == 0:
            raise HTTPException(status_code=500, detail="保存知识库条目失败")
        
        # 返回结果（简化版）
        return KnowledgeBaseResponse(
            id=kb_id,
            session_id=request.session_id,
            title=request.title,
            content=request.content,
            metadata=request.metadata,
            created_at=None
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"保存知识库条目参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("保存知识库条目失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/knowledge-base/{session_id}")
async def get_knowledge_base_api(session_id: str):
    """获取session的知识库条目"""
    try:
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id不能为空")
        
        knowledge_items = await kb_dao.get_knowledge_by_session(session_id)
        return {"items": knowledge_items}
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"获取知识库条目参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("获取知识库条目失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")
