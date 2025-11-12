"""
API路由模块
"""
from fastapi import APIRouter, HTTPException

from utils.schemas import (
    GPTRequest, GPTResponse,
    ChatHistoryRequest, ChatHistoryResponse,
    InterviewAnalysisRequest, InterviewAnalysisResponse,
    CVRequest, CVResponse,
    JobPositionRequest, JobPositionResponse,
    KnowledgeBaseRequest, KnowledgeBaseResponse,
    AgentSuggestRequest, AgentSuggestResponse
)
from storage.dao import transcript_dao, cv_dao, job_position_dao, kb_dao
from gateway.ws_audio import _sessions
from nlp.llm_api import llm_api
from nlp.agent import interview_agent
from utils.embedding import embedding_service
from logs import setup_logger

logger = setup_logger(__name__)

# 创建路由器
router = APIRouter()


@router.post("/gpt", response_model=GPTResponse)
async def ask_gpt(request: GPTRequest):
    """GPT问答接口（增强版：支持CV、知识库、岗位信息、RAG）"""
    try:
        from nlp.rag import rag_retriever
        from gateway.ws_audio import _sessions
        
        # 构建增强的prompt
        enhanced_prompt_parts = []
        
        # 1. 获取CV信息（如果有user_id）
        cv_info = None
        if request.user_id:
            try:
                cv_info = await cv_dao.get_cv_by_user_id(request.user_id)
            except Exception as e:
                logger.warning(f"获取CV失败: {e}")
        
        # 2. 获取岗位信息（如果有session_id）
        job_info = None
        if request.session_id:
            try:
                job_info = await job_position_dao.get_job_position_by_session(request.session_id)
            except Exception as e:
                logger.warning(f"获取岗位信息失败: {e}")
        
        # 3. 获取知识库条目（如果有session_id）
        kb_items = []
        if request.session_id:
            try:
                kb_items = await kb_dao.get_knowledge_by_session(request.session_id, limit=10)
            except Exception as e:
                logger.warning(f"获取知识库失败: {e}")
        
        # 4. RAG检索相关上下文（如果启用）
        rag_context = []
        if request.use_rag and request.session_id:
            try:
                # 获取会话状态（用于内存对话历史）
                session_key = f"{request.session_id}_mic"
                session_state = _sessions.get(session_key)
                if not session_state:
                    session_key = f"{request.session_id}_sys"
                    session_state = _sessions.get(session_key)
                
                if session_state:
                    # 从内存对话历史检索
                    memory_results = await rag_retriever.retrieve_from_memory(
                        session_state,
                        request.prompt,
                        top_k=3
                    )
                    rag_context.extend(memory_results)
                
                # 从PostgreSQL检索相关对话（如果RAG启用）
                if rag_retriever.enabled:
                    query_embedding = await embedding_service.generate_embedding(request.prompt)
                    if query_embedding is not None:
                        db_results = await rag_retriever.retrieve(
                            query=request.prompt,
                            query_embedding=query_embedding,
                            session_id=request.session_id,
                            top_k=3
                        )
                        rag_context.extend(db_results)
            except Exception as e:
                logger.warning(f"RAG检索失败: {e}")
        
        # 5. 构建增强的prompt
        enhanced_prompt_parts.append("你是一位专业的面试助手。请根据以下信息为面试者提供回答建议和技巧。")
        enhanced_prompt_parts.append("")
        
        # 添加CV信息
        if cv_info and cv_info.get('content'):
            cv_content = cv_info['content']
            if len(cv_content) > 1000:
                cv_content = cv_content[:1000] + "..."
            enhanced_prompt_parts.append("【候选人简历】")
            enhanced_prompt_parts.append(cv_content)
            enhanced_prompt_parts.append("")
        
        # 添加岗位信息
        if job_info:
            enhanced_prompt_parts.append("【岗位信息】")
            if job_info.get('title'):
                enhanced_prompt_parts.append(f"岗位名称：{job_info['title']}")
            if job_info.get('description'):
                enhanced_prompt_parts.append(f"岗位描述：{job_info['description']}")
            if job_info.get('requirements'):
                enhanced_prompt_parts.append(f"岗位要求：{job_info['requirements']}")
            enhanced_prompt_parts.append("")
        
        # 添加知识库信息
        if kb_items:
            enhanced_prompt_parts.append("【相关知识库】")
            for item in kb_items[:5]:  # 最多5条
                if item.get('title') and item.get('content'):
                    enhanced_prompt_parts.append(f"- {item['title']}: {item['content'][:200]}")
            enhanced_prompt_parts.append("")
        
        # 添加RAG检索的相关上下文
        if rag_context:
            enhanced_prompt_parts.append("【相关对话上下文】")
            for item in rag_context[:3]:  # 最多3条
                content = item.get('content', '')
                if content:
                    speaker = item.get('speaker', 'unknown')
                    enhanced_prompt_parts.append(f"{speaker}: {content[:150]}")
            enhanced_prompt_parts.append("")
        
        # 添加用户的问题/请求
        enhanced_prompt_parts.append("【用户请求】")
        enhanced_prompt_parts.append(request.prompt)
        enhanced_prompt_parts.append("")
        enhanced_prompt_parts.append("请基于以上信息，为面试者提供专业、实用的回答建议和技巧。")
        
        enhanced_prompt = "\n".join(enhanced_prompt_parts)
        
        # 调用LLM生成回复
        reply = await llm_api.generate(enhanced_prompt, stream=request.stream)
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


# =====================================================
# CV相关接口
# =====================================================

@router.post("/cv", response_model=CVResponse)
async def save_cv_api(request: CVRequest):
    """上传/更新CV"""
    try:
        # 生成向量
        embedding = await embedding_service.generate_embedding(request.content)
        
        # 检查PostgreSQL是否可用
        from storage.pg import pg_pool
        if not pg_pool.pool:
            raise HTTPException(
                status_code=503,
                detail="PostgreSQL未连接，无法保存CV。请检查PostgreSQL服务是否运行，并查看服务器日志获取详细信息。"
            )
        
        # 保存CV
        cv_id = await cv_dao.save_cv(
            user_id=request.user_id,
            content=request.content,
            embedding=embedding,
            metadata=request.metadata
        )
        
        if cv_id == 0:
            raise HTTPException(status_code=500, detail="保存CV失败（PostgreSQL可能未正确初始化）")
        
        # 获取保存的CV
        cv = await cv_dao.get_cv_by_user_id(request.user_id)
        if not cv:
            raise HTTPException(status_code=404, detail="CV未找到")
        
        return CVResponse(**cv)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存CV失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cv/{user_id}", response_model=CVResponse)
async def get_cv_api(user_id: str):
    """获取CV"""
    try:
        cv = await cv_dao.get_cv_by_user_id(user_id)
        if not cv:
            raise HTTPException(status_code=404, detail="CV未找到")
        return CVResponse(**cv)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取CV失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# 岗位信息相关接口
# =====================================================

@router.post("/job-position", response_model=JobPositionResponse)
async def save_job_position_api(request: JobPositionRequest):
    """创建/更新岗位信息"""
    try:
        # 合并文本用于向量化
        full_text = f"{request.title}\n{request.description or ''}\n{request.requirements or ''}".strip()
        
        # 生成向量
        embedding = await embedding_service.generate_embedding(full_text)
        
        # 保存岗位信息
        job_id = await job_position_dao.save_job_position(
            session_id=request.session_id,
            title=request.title,
            description=request.description,
            requirements=request.requirements,
            embedding=embedding,
            metadata=request.metadata
        )
        
        if job_id == 0:
            raise HTTPException(status_code=500, detail="保存岗位信息失败")
        
        # 获取保存的岗位信息
        job = await job_position_dao.get_job_position_by_session(request.session_id)
        if not job:
            raise HTTPException(status_code=404, detail="岗位信息未找到")
        
        return JobPositionResponse(**job)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存岗位信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job-position/{session_id}", response_model=JobPositionResponse)
async def get_job_position_api(session_id: str):
    """获取岗位信息"""
    try:
        job = await job_position_dao.get_job_position_by_session(session_id)
        if not job:
            raise HTTPException(status_code=404, detail="岗位信息未找到")
        return JobPositionResponse(**job)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取岗位信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# 知识库相关接口
# =====================================================

@router.post("/knowledge-base", response_model=KnowledgeBaseResponse)
async def save_knowledge_base_api(request: KnowledgeBaseRequest):
    """添加知识库条目（按session）"""
    try:
        # 生成向量
        embedding = await embedding_service.generate_embedding(request.content)
        
        # 保存知识库条目
        kb_id = await kb_dao.save_knowledge(
            title=request.title,
            content=request.content,
            embedding=embedding,
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
    except Exception as e:
        logger.error(f"保存知识库条目失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-base/{session_id}")
async def get_knowledge_base_api(session_id: str):
    """获取session的知识库条目"""
    try:
        knowledge_items = await kb_dao.get_knowledge_by_session(session_id)
        return {"items": knowledge_items}
    except Exception as e:
        logger.error(f"获取知识库条目失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# Agent相关接口
# =====================================================

@router.post("/agent/suggest", response_model=AgentSuggestResponse)
async def agent_suggest_api(request: AgentSuggestRequest):
    """Agent生成面试建议（异步，轻量化）"""
    try:
        # 获取会话状态
        session_key = f"{request.session_id}_mic"  # 默认使用mic会话
        session_state = _sessions.get(session_key)
        
        if not session_state:
            # 尝试获取sys会话
            session_key = f"{request.session_id}_sys"
            session_state = _sessions.get(session_key)
        
        if not session_state:
            return AgentSuggestResponse(
                suggestion=None,
                success=False,
                message="会话未找到，请先开始录音"
            )
        
        # 调用Agent生成建议
        suggestion = await interview_agent.suggest_question(
            session_state=session_state,
            session_id=request.session_id,
            user_id=request.user_id
        )
        
        if suggestion:
            return AgentSuggestResponse(
                suggestion=suggestion,
                success=True,
                message=None
            )
        else:
            return AgentSuggestResponse(
                suggestion=None,
                success=False,
                message="生成建议超时或失败"
            )
    except Exception as e:
        logger.error(f"Agent生成建议失败: {e}")
        return AgentSuggestResponse(
            suggestion=None,
            success=False,
            message=str(e)
        )
