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


@router.post("/gpt")
async def ask_gpt(request: GPTRequest):
    """GPT问答接口（增强版：支持CV、知识库、岗位信息、RAG）"""
    try:
        # 延迟导入，避免循环导入
        from nlp.rag import rag_retriever
        from gateway.ws_audio import _sessions
        
        # 并行获取所有数据源
        coros = []
        
        # 1. 获取CV信息（如果有user_id则按user_id获取，否则获取默认CV）
        if request.user_id:
            logger.info(f"[/gpt] 开始获取CV信息，user_id: {request.user_id}")
            coros.append(cv_dao.get_cv_by_user_id(request.user_id))
        else:
            logger.info("[/gpt] 未提供user_id，尝试获取默认CV（第一个用户的CV）")
            coros.append(cv_dao.get_default_cv())
        
        # 2. 获取岗位信息（如果有session_id）
        if request.session_id:
            coros.append(job_position_dao.get_job_position_by_session(request.session_id))
        
        # 并行执行所有查询
        results = await asyncio.gather(*coros, return_exceptions=True)
        
        # 处理结果：第一个是CV，第二个是Job（如果存在）
        cv_info, job_info = (results + [None, None])[:2]
        
        # 处理异常
        if isinstance(cv_info, Exception):
            logger.warning(f"获取CV失败: {cv_info}")
            cv_info = None
        
        if isinstance(job_info, Exception):
            logger.warning(f"获取岗位信息失败: {job_info}")
            job_info = None
        
        # 3. 获取对话上下文（如果启用RAG）
        rag_context = []
        recent_dialogue = []
        
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
                        # 1. 获取完整的最近对话历史（直接使用，不依赖向量检索）
                        full_history = session_state.get_history_with_embeddings()
                        if full_history:
                            # 获取最近10条对话作为基础上下文
                            recent_items = full_history[-10:] if len(full_history) > 10 else full_history
                            for item in recent_items:
                                content = item.get('content', '').strip()
                                speaker = item.get('speaker', 'unknown')
                                if content:
                                    recent_dialogue.append({
                                        'content': content,
                                        'speaker': speaker,
                                        'source': 'recent_history'
                                    })
                            logger.info(f"[/gpt] 获取到 {len(recent_dialogue)} 条最近对话历史")
                        else:
                            logger.warning("[/gpt] 未获取到最近对话历史")
                    except Exception as e:
                        logger.warning(f"获取最近对话历史失败: {e}")
                else:
                    logger.warning("[/gpt] 无有效的session_state，跳过对话历史检索")
            except Exception as e:
                logger.warning(f"获取对话上下文失败: {e}")
        # 4. 构建增强的prompt
        enhanced_prompt_parts = []
        enhanced_prompt_parts.append("你是一位专业的后端开发，专门为面试者提供简洁的回答建议。")
        enhanced_prompt_parts.append("")
        
        # 添加CV信息
        if cv_info and cv_info.get('content'):
            # 增加CV内容长度限制，保留更多信息
            cv_content = _sanitize_content(cv_info['content'], max_length=2000)
            if cv_content:
                enhanced_prompt_parts.append("【简历摘要】")
                enhanced_prompt_parts.append(cv_content)
                enhanced_prompt_parts.append("")
                logger.info(f"[/gpt] 已将CV信息添加到prompt，长度: {len(cv_content)}")
        
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
        
        # 去重机制：维护已使用的对话内容集合，避免重复
        used_dialogue_content = set()
        
        def add_dialogue_block(title: str, dialogue_list: list, max_items: int = None):
            """添加对话块，自动去重"""
            if not dialogue_list:
                return
            
            items_to_add = []
            for item in dialogue_list:
                content = item.get('content', '').strip()
                if not content:
                    continue
                
                # 标准化内容用于去重（去除前后空格，统一格式）
                normalized_content = content.strip()
                
                # 检查是否已使用
                if normalized_content in used_dialogue_content:
                    continue
                
                # 添加到已使用集合
                used_dialogue_content.add(normalized_content)
                
                # 添加到待添加列表
                speaker = item.get('speaker', 'unknown')
                speaker_name = "面试官" if speaker == "interviewer" else "我"
                sanitized_content = _sanitize_content(normalized_content, max_length=200)
                items_to_add.append(f"{speaker_name}：{sanitized_content}")
            
            if items_to_add:
                enhanced_prompt_parts.append(title)
                # 如果指定了最大数量，只取最后N条
                if max_items and len(items_to_add) > max_items:
                    items_to_add = items_to_add[-max_items:]
                enhanced_prompt_parts.extend(items_to_add)
                enhanced_prompt_parts.append("")
        
        # 如果传入了选中的消息，优先使用选中的消息作为上下文（用于回答功能）
        if request.selected_messages and request.session_id:
            try:
                from gateway.ws_audio import _sessions
                session_key = f"{request.session_id}_mic"
                session_state = _sessions.get(session_key) if _sessions else None
                if not session_state:
                    session_key = f"{request.session_id}_sys"
                    session_state = _sessions.get(session_key) if _sessions else None
                
                if session_state and hasattr(session_state, "get_history_with_embeddings"):
                    full_history = session_state.get_history_with_embeddings()
                    selected_dialogue = []
                    for msg_id in request.selected_messages:
                        # 从历史中找到对应的消息
                        # 前端传递的id可能是timestamp字符串，需要匹配
                        found = False
                        for item in full_history:
                            # 尝试匹配timestamp（前端id通常是timestamp）
                            item_timestamp = item.get('timestamp', '')
                            # 比较timestamp字符串（可能格式略有不同）
                            if item_timestamp:
                                # 将timestamp转换为可比较的格式
                                try:
                                    from datetime import datetime
                                    item_ts = datetime.fromisoformat(item_timestamp.replace('Z', '+00:00'))
                                    msg_ts = datetime.fromisoformat(msg_id.replace('Z', '+00:00'))
                                    if abs((item_ts - msg_ts).total_seconds()) < 1:  # 1秒内的差异认为是同一消息
                                        found = True
                                except:
                                    # 如果解析失败，直接比较字符串
                                    if str(item_timestamp) == msg_id or item_timestamp.startswith(msg_id) or msg_id.startswith(item_timestamp):
                                        found = True
                            
                            if found:
                                content = item.get('content', '').strip()
                                speaker = item.get('speaker', 'unknown')
                                # 只添加面试官的消息（选中的对话默认是面试官说的话）
                                if content and speaker == "interviewer":
                                    selected_dialogue.append({
                                        'content': content,
                                        'speaker': speaker
                                    })
                                break
                    
                    # 使用去重机制添加选中的对话
                    if selected_dialogue:
                        add_dialogue_block("【选中的对话】", selected_dialogue)
            except Exception as e:
                logger.warning(f"获取选中消息失败: {e}")
        
        # 如果没有选中消息，使用最近对话上下文（去重机制会自动处理重复）
        if not request.selected_messages:
            if recent_dialogue:
                add_dialogue_block("【对话上下文】\n最近对话：", recent_dialogue[-8:], max_items=8)
        
        # 添加用户的问题/请求
        user_prompt = _sanitize_content(request.prompt)
        enhanced_prompt_parts.append("【问题】")
        enhanced_prompt_parts.append(user_prompt)
        enhanced_prompt_parts.append("")
        
        # 根据brief参数决定是快答还是正常回答
        if request.brief:
            enhanced_prompt_parts.append("请基于以上简历、岗位信息和对话上下文，用一句话简洁回答。")
        else:
            enhanced_prompt_parts.append("请基于以上简历、岗位信息和对话上下文，为面试者提供专业、详细的回答建议。")
        
        enhanced_prompt = "\n".join(enhanced_prompt_parts)
        
        # 如果请求流式响应，返回流式
        if request.stream:
            from fastapi.responses import StreamingResponse
            import json as json_lib
            
            async def generate_stream():
                """生成流式响应"""
                try:
                    messages = [{"role": "user", "content": enhanced_prompt}]
                    has_error = False
                    full_content = ""
                    
                    async for chunk in llm_api.chat(messages, stream=True, max_tokens=1000):
                        if chunk.get("error"):
                            # 如果流式不支持，降级为非流式
                            error_msg = chunk.get("content", "")
                            if "stream" in error_msg.lower() and ("unsupported" in error_msg.lower() or "verified" in error_msg.lower()):
                                logger.warning("流式响应失败，降级为非流式响应")
                                # 使用非流式重新生成
                                reply = await llm_api.generate(enhanced_prompt, stream=False, max_tokens=1000)
                                # 将完整内容作为单个块发送
                                data = json_lib.dumps({
                                    "content": reply,
                                    "done": True
                                })
                                yield f"data: {data}\n\n"
                                return
                            else:
                                has_error = True
                                error_data = json_lib.dumps({
                                    "content": error_msg,
                                    "done": True,
                                    "error": True
                                })
                                yield f"data: {error_data}\n\n"
                                return
                        
                        if chunk.get("content"):
                            content = chunk["content"]
                            full_content += content
                            # 发送SSE格式的数据
                            data = json_lib.dumps({
                                "content": content,
                                "done": chunk.get("done", False)
                            })
                            yield f"data: {data}\n\n"
                        
                        if chunk.get("done"):
                            break
                    
                    # 如果没有错误且没有内容，可能是流式失败但未报错，降级为非流式
                    if not has_error and not full_content:
                        logger.warning("流式响应无内容，降级为非流式响应")
                        reply = await llm_api.generate(enhanced_prompt, stream=False, max_tokens=300)
                        data = json_lib.dumps({
                            "content": reply,
                            "done": True
                        })
                        yield f"data: {data}\n\n"
                except Exception as e:
                    logger.error(f"流式生成失败: {e}")
                    # 尝试降级为非流式
                    try:
                        logger.info("尝试降级为非流式响应")
                        reply = await llm_api.generate(enhanced_prompt, stream=False, max_tokens=300)
                        data = json_lib.dumps({
                            "content": reply,
                            "done": True
                        })
                        yield f"data: {data}\n\n"
                    except Exception as fallback_error:
                        logger.error(f"非流式降级也失败: {fallback_error}")
                        error_data = json_lib.dumps({
                            "content": f"生成失败: {str(e)}",
                            "done": True,
                            "error": True
                        })
                        yield f"data: {error_data}\n\n"
            
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应
            reply = await llm_api.generate(enhanced_prompt, stream=False, max_tokens=1000)
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
    """保存聊天消息到内存（不保存到数据库）"""
    try:
        # 延迟导入，避免循环导入
        from gateway.ws_audio import _sessions
        from utils.embedding import embedding_service
        
        # 获取会话状态
        session_key = f"{request.session_id}_mic"
        session_state = _sessions.get(session_key) if _sessions else None
        if not session_state:
            session_key = f"{request.session_id}_sys"
            session_state = _sessions.get(session_key) if _sessions else None
        
        if session_state:
            # 异步生成embedding并添加到内存历史
            async def add_to_memory():
                try:
                    embedding = await embedding_service.generate_embedding(request.message.content)
                    session_state.add_to_history(
                        content=request.message.content,
                        speaker=request.message.speaker,
                        embedding=embedding,
                        timestamp=request.message.timestamp
                    )
                except Exception as e:
                    logger.warning(f"生成embedding失败，仅保存文本: {e}")
                    # 即使embedding失败，也保存文本
                    session_state.add_to_history(
                        content=request.message.content,
                        speaker=request.message.speaker,
                        timestamp=request.message.timestamp
                    )
            
            # 后台任务，不阻塞
            import asyncio
            asyncio.create_task(add_to_memory())
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
        from gateway.ws_audio import _sessions
        
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
        from gateway.ws_audio import _sessions
        
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


@router.post("/gpt/analyze", response_model=InterviewAnalysisResponse)
async def analyze_interview(request: InterviewAnalysisRequest):
    """分析面试表现"""
    try:
        if request.type != "interview_analysis":
            raise HTTPException(status_code=400, detail="Invalid analysis type")
        
        # 获取transcripts（从内存）
        session_id = request.session_id or (request.data.get("sessionId") if request.data else None) or "unknown"
        
        # 延迟导入，避免循环导入
        from gateway.ws_audio import _sessions
        
        # 获取会话状态
        session_key = f"{session_id}_mic"
        session_state = _sessions.get(session_key) if _sessions else None
        if not session_state:
            session_key = f"{session_id}_sys"
            session_state = _sessions.get(session_key) if _sessions else None
        
        if not session_state or not hasattr(session_state, "get_history_with_embeddings"):
            raise HTTPException(status_code=404, detail="未找到聊天记录（会话不存在或已过期）")
        
        history = session_state.get_history_with_embeddings()
        if not history:
            raise HTTPException(status_code=404, detail="未找到聊天记录")
        
        # 构建对话历史（清洗内容）
        chat_history_parts = []
        for h in history:
            speaker = h.get('speaker', 'unknown')
            content = _sanitize_content(h.get('content', ''), max_length=500)
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
        from nlp.exceptions import AgentError
        
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
        
        # 调用Agent生成回答建议（Agent内部已处理超时）
        suggestion = await interview_agent.suggest_answer(
            session_state=session_state,
            session_id=request.session_id,
            user_id=request.user_id,
            question=question
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
    except AgentError as e:
        logger.error(f"Agent生成建议失败: {e.message}")
        return AgentSuggestResponse(
            suggestion=None,
            success=False,
            message=f"生成建议失败: {e.message}"
        )
    except ValueError as e:
        logger.error(f"Agent生成建议参数错误: {e}")
        return AgentSuggestResponse(
            suggestion=None,
            success=False,
            message=f"参数错误: {str(e)}"
        )
    except Exception as e:
        logger.exception("Agent生成建议未知错误")
        return AgentSuggestResponse(
            suggestion=None,
            success=False,
            message="生成建议失败，请稍后重试"
        )
