"""
API路由模块
"""
import asyncio
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
from nlp.llm_api import llm_api
from utils.embedding import embedding_service
from logs import setup_logger

logger = setup_logger(__name__)

# 创建路由器
router = APIRouter()


def _sanitize_content(content: str, max_length: int = None) -> str:
    """清洗内容，防止prompt注入"""
    if not content:
        return ""
    # 移除换行和代码块标记
    content = content.replace("\n", " ").replace("\r", " ")
    content = content.replace("```", "").replace("`", "")
    # 限制长度
    if max_length and len(content) > max_length:
        content = content[:max_length] + "..."
    return content.strip()


@router.post("/gpt", response_model=GPTResponse)
async def ask_gpt(request: GPTRequest):
    """GPT问答接口（增强版：支持CV、知识库、岗位信息、RAG）"""
    try:
        # 延迟导入，避免循环导入
        from nlp.rag import rag_retriever
        from gateway.ws_audio import _sessions
        
        # 并行获取所有数据源
        tasks = []
        
        # 1. 获取CV信息（如果有user_id）
        if request.user_id:
            tasks.append(("cv", cv_dao.get_cv_by_user_id(request.user_id)))
        
        # 2. 获取岗位信息（如果有session_id）
        if request.session_id:
            tasks.append(("job", job_position_dao.get_job_position_by_session(request.session_id)))
        
        # 并行执行所有查询
        results = {}
        if tasks:
            task_results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
            for (key, _), result in zip(tasks, task_results):
                if isinstance(result, Exception):
                    logger.warning(f"获取{key}失败: {result}")
                else:
                    results[key] = result
        
        cv_info = results.get("cv")
        job_info = results.get("job")
        
        # 3. RAG检索相关上下文（如果启用）
        rag_context = []
        if request.use_rag and request.session_id:
            try:
                # 获取会话状态（用于内存对话历史）
                session_key = f"{request.session_id}_mic"
                session_state = _sessions.get(session_key) if _sessions else None
                if not session_state:
                    session_key = f"{request.session_id}_sys"
                    session_state = _sessions.get(session_key) if _sessions else None
                
                # 严格检查session_state
                if session_state and hasattr(session_state, "get_history_with_embeddings"):
                    try:
                        # 从内存对话历史检索
                        memory_results = await rag_retriever.retrieve_from_memory(
                            session_state,
                            request.prompt,
                            top_k=2
                        )
                        if memory_results:
                            rag_context.extend(memory_results)
                    except Exception as e:
                        logger.warning(f"RAG内存检索失败: {e}")
                else:
                    logger.debug("无有效的session_state，跳过RAG memory检索")
                
                # 从PostgreSQL检索相关对话（如果RAG启用）
                if rag_retriever.enabled:
                    try:
                        query_embedding = await embedding_service.generate_embedding(request.prompt)
                        if query_embedding is not None:
                            db_results = await rag_retriever.retrieve(
                                query=request.prompt,
                                query_embedding=query_embedding,
                                session_id=request.session_id,
                                top_k=2
                            )
                            if db_results:
                                rag_context.extend(db_results)
                    except Exception as e:
                        logger.warning(f"RAG数据库检索失败: {e}")
            except Exception as e:
                logger.warning(f"RAG检索失败: {e}")
        
        # 4. 构建增强的prompt
        enhanced_prompt_parts = []
        enhanced_prompt_parts.append("你是一位专业的面试助手，专门为面试者提供简洁实用的回答建议。")
        enhanced_prompt_parts.append("")
        
        # 添加CV信息
        if cv_info and cv_info.get('content'):
            cv_content = _sanitize_content(cv_info['content'], max_length=500)
            if cv_content:
                enhanced_prompt_parts.append("【简历摘要】")
                enhanced_prompt_parts.append(cv_content)
                enhanced_prompt_parts.append("")
        
        # 添加岗位信息
        if job_info:
            enhanced_prompt_parts.append("【岗位信息】")
            if job_info.get('title'):
                title = _sanitize_content(job_info['title'])
                if title:
                    enhanced_prompt_parts.append(f"岗位：{title}")
            if job_info.get('requirements'):
                req = _sanitize_content(job_info['requirements'], max_length=300)
                if req:
                    enhanced_prompt_parts.append(f"要求：{req}")
            enhanced_prompt_parts.append("")
        
        # 添加RAG检索的相关上下文（最近对话）
        if rag_context:
            enhanced_prompt_parts.append("【最近对话】")
            for item in rag_context[:2]:  # 最多2条
                content = item.get('content', '')
                if content:
                    content = _sanitize_content(content, max_length=100)
                    speaker = item.get('speaker', 'unknown')
                    speaker_name = "面试官" if speaker == "interviewer" else "我"
                    enhanced_prompt_parts.append(f"{speaker_name}：{content}")
            enhanced_prompt_parts.append("")
        
        # 添加用户的问题/请求
        user_prompt = _sanitize_content(request.prompt)
        enhanced_prompt_parts.append("【问题】")
        enhanced_prompt_parts.append(user_prompt)
        enhanced_prompt_parts.append("")
        enhanced_prompt_parts.append("请基于以上简历、岗位信息和对话上下文，用1句话简短回答。")
        
        enhanced_prompt = "\n".join(enhanced_prompt_parts)
        
        # 调用LLM生成回复，限制token数量以保持简洁
        reply = await llm_api.generate(enhanced_prompt, stream=request.stream, max_tokens=300)
        return GPTResponse(reply=reply)
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"GPT问答参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("GPT问答失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


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
    except ValueError as e:
        logger.error(f"保存消息参数错误: {e}")
        return ChatHistoryResponse(success=False, message=f"参数错误: {str(e)}")
    except Exception as e:
        logger.exception("保存消息失败")
        return ChatHistoryResponse(success=False, message="保存失败，请稍后重试")


@router.get("/chat/history/{session_id}")
async def get_chat_history_api(session_id: str):
    """获取会话聊天记录"""
    try:
        transcripts = await transcript_dao.get_transcripts(session_id)
        return {"messages": transcripts}
    except ValueError as e:
        logger.error(f"获取聊天记录参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("获取聊天记录失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


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
    except ValueError as e:
        logger.error(f"获取统计信息参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("获取统计信息失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/gpt/analyze", response_model=InterviewAnalysisResponse)
async def analyze_interview(request: InterviewAnalysisRequest):
    """分析面试表现"""
    try:
        if request.type != "interview_analysis":
            raise HTTPException(status_code=400, detail="Invalid analysis type")
        
        # 获取transcripts（从request.data或request.session_id）
        session_id = request.session_id or (request.data.get("sessionId") if request.data else None) or "unknown"
        transcripts = await transcript_dao.get_transcripts(session_id)
        
        if not transcripts:
            raise HTTPException(status_code=404, detail="未找到聊天记录")
        
        # 构建对话历史（清洗内容）
        chat_history_parts = []
        for t in transcripts:
            speaker = t.get('speaker', 'unknown')
            content = _sanitize_content(t.get('content', ''), max_length=500)
            if content:
                chat_history_parts.append(f"{speaker}: {content}")
        
        chat_history = "\n".join(chat_history_parts)
        
        # 使用LLM进行分析
        prompt = f"""请分析以下面试对话，为面试者提供专业的反馈和建议。

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
    except ValueError as e:
        logger.error(f"分析面试参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("分析面试失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


# =====================================================
# CV相关接口
# =====================================================

@router.post("/cv", response_model=CVResponse)
async def save_cv_api(request: CVRequest):
    """上传/更新CV（支持幂等性：同一user_id会更新而非创建新记录）"""
    try:
        # 验证输入
        if not request.user_id or not request.content:
            raise HTTPException(status_code=400, detail="user_id和content不能为空")
        
        # 生成向量
        embedding = await embedding_service.generate_embedding(request.content)
        
        # 检查PostgreSQL是否可用
        from storage.pg import pg_pool
        if not pg_pool.pool:
            raise HTTPException(
                status_code=503,
                detail="PostgreSQL未连接，无法保存CV。请检查PostgreSQL服务是否运行，并查看服务器日志获取详细信息。"
            )
        
        # 保存CV（DAO层已实现UPSERT，支持幂等性）
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
# 岗位信息相关接口
# =====================================================

@router.post("/job-position", response_model=JobPositionResponse)
async def save_job_position_api(request: JobPositionRequest):
    """创建/更新岗位信息（支持幂等性：同一session_id会更新而非创建新记录）"""
    try:
        # 验证输入
        if not request.session_id or not request.title:
            raise HTTPException(status_code=400, detail="session_id和title不能为空")
        
        # 合并文本用于向量化
        full_text = f"{request.title}\n{request.description or ''}\n{request.requirements or ''}".strip()
        
        # 生成向量
        embedding = await embedding_service.generate_embedding(full_text)
        
        # 保存岗位信息（DAO层已实现UPSERT，支持幂等性）
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
# 知识库相关接口
# =====================================================

@router.post("/knowledge-base", response_model=KnowledgeBaseResponse)
async def save_knowledge_base_api(request: KnowledgeBaseRequest):
    """添加知识库条目（按session）"""
    try:
        # 验证输入
        if not request.session_id or not request.title or not request.content:
            raise HTTPException(status_code=400, detail="session_id、title和content不能为空")
        
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


# =====================================================
# Agent相关接口
# =====================================================

@router.post("/agent/suggest", response_model=AgentSuggestResponse)
async def agent_suggest_api(request: AgentSuggestRequest):
    """Agent为面试者生成回答建议（异步，轻量化，带超时控制）"""
    try:
        # 延迟导入，避免循环导入
        from gateway.ws_audio import _sessions
        from nlp.agent import interview_agent
        
        # 获取会话状态
        session_key = f"{request.session_id}_mic"  # 默认使用mic会话
        session_state = _sessions.get(session_key) if _sessions else None
        
        if not session_state:
            # 尝试获取sys会话
            session_key = f"{request.session_id}_sys"
            session_state = _sessions.get(session_key) if _sessions else None
        
        # 严格检查session_state
        if not session_state or not hasattr(session_state, "get_history_with_embeddings"):
            return AgentSuggestResponse(
                suggestion=None,
                success=False,
                message="会话未找到或无效，请先开始录音"
            )
        
        # 从请求中获取问题（如果有）
        question = None
        if hasattr(request, 'question') and request.question:
            question = request.question
        
        # 调用Agent生成回答建议，带超时控制
        try:
            suggestion = await asyncio.wait_for(
                interview_agent.suggest_answer(
                    session_state=session_state,
                    session_id=request.session_id,
                    user_id=request.user_id,
                    question=question
                ),
                timeout=interview_agent.timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Agent生成建议超时（{interview_agent.timeout}s）")
            return AgentSuggestResponse(
                suggestion=None,
                success=False,
                message="生成建议超时，请稍后重试"
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
                message="生成建议失败"
            )
    except ValueError as e:
        logger.error(f"Agent生成建议参数错误: {e}")
        return AgentSuggestResponse(
            suggestion=None,
            success=False,
            message=f"参数错误: {str(e)}"
        )
    except Exception as e:
        logger.exception("Agent生成建议失败")
        return AgentSuggestResponse(
            suggestion=None,
            success=False,
            message="生成建议失败，请稍后重试"
        )
