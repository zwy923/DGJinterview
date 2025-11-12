"""
基于LangChain的面试助手Agent（性能优化版）
使用LangChain的Chain、Prompt和Retriever封装
"""
import asyncio
import hashlib
import json
from typing import List, Dict, Any, Optional, Tuple
from functools import lru_cache

from langchain_core.runnables import RunnableMap, RunnableSequence
from langchain_core.output_parsers import StrOutputParser

from asr.session import SessionState
from storage.dao import cv_dao, job_position_dao
from nlp.langchain_components import CustomLLMWrapper, SessionMemoryRetriever
from nlp.prompts import prompt_manager
from nlp.exceptions import AgentError, RetrievalError
from config import settings
from logs import setup_logger
from utils.redis_client import redis_get_json, redis_setex_json

logger = setup_logger(__name__)


class InterviewAssistantAgent:
    """基于LangChain的面试助手Agent：为面试者提供回答建议（性能优化版）"""
    
    def __init__(self):
        self.timeout = settings.AGENT_TIMEOUT
        self.llm = CustomLLMWrapper()
        
        # LLM并发控制（优化⑥）
        self._llm_semaphore = asyncio.Semaphore(getattr(settings, 'LLM_CONCURRENCY_LIMIT', 5))
        
        # 上下文token预算（优化⑤）
        self.max_context_tokens = 6000
        
        # 预热标志
        self._preloaded = False
        
        self._build_chain()
    
    def _build_chain(self):
        """构建LangChain Chain（优化⑦：JSON格式Prompt）"""
        # 从prompt_manager获取模板
        try:
            self.prompt_template = prompt_manager.get_prompt("interview_answer")
        except Exception as e:
            logger.error(f"加载Prompt模板失败: {e}")
            # 使用优化的JSON格式模板作为fallback（优化⑦）
            from langchain_core.prompts import ChatPromptTemplate
            self.prompt_template = ChatPromptTemplate.from_template(
                """You are an interview assistant. Generate concise, practical answer suggestions.

Context:
{{
  "cv": "{cv}",
  "job": "{job}",
  "dialogue": "{dialogue}",
  "question": "{question}"
}}

Generate a concise, practical answer suggestion."""
            )
        
        # 构建Chain：使用RunnableMap组合输入，然后通过模板和LLM
        self.chain = (
            RunnableMap({
                "cv": lambda x: x.get("cv", "") if isinstance(x, dict) else "",
                "job": lambda x: x.get("job", "") if isinstance(x, dict) else "",
                "question": lambda x: x.get("question", "") if isinstance(x, dict) else "",
                "dialogue": lambda x: x.get("dialogue", "") if isinstance(x, dict) else "",
            })
            | self.prompt_template
            | self.llm
            | StrOutputParser()
        )
    
    async def preload(self):
        """预热Chain（优化①）"""
        if self._preloaded:
            return
        
        try:
            dummy = {
                "cv": "",
                "job": "",
                "question": "test",
                "dialogue": ""
            }
            await self.chain.ainvoke(dummy)
            self._preloaded = True
            if logger.isEnabledFor(20):  # DEBUG
                logger.debug("Agent Chain预热完成")
        except Exception as e:
            logger.warning(f"Agent Chain预热失败: {e}")
    
    async def suggest_answer(
        self,
        session_state: SessionState,
        session_id: str,
        user_id: Optional[str] = None,
        question: Optional[str] = None
    ) -> Optional[str]:
        """
        为面试者提供回答建议（轻量化，不阻塞）
        
        Args:
            session_state: 会话状态（包含内存对话历史）
            session_id: 会话ID
            user_id: 用户ID（可选，用于获取CV）
            question: 面试官的问题（可选，如果不提供则基于最近对话）
        
        Returns:
            回答建议或None（超时/失败时）
        """
        try:
            # 使用asyncio.timeout (Python 3.11+)
            async with asyncio.timeout(self.timeout):
                return await self._generate_answer_suggestion(session_state, session_id, user_id, question)
        except TimeoutError:
            if logger.isEnabledFor(30):  # WARNING
                logger.warning(f"Agent生成建议超时（{self.timeout}s）")
            return None
        except AgentError as e:
            if logger.isEnabledFor(40):  # ERROR
                logger.error(f"Agent生成建议失败: {e.message}")
            return None
        except Exception as e:
            logger.exception(f"Agent生成建议未知错误: {e}")
            return None
    
    async def _collect_context_data(
        self,
        session_state: SessionState,
        session_id: str,
        user_id: Optional[str] = None
    ) -> Tuple[Optional[dict], Optional[dict], List[dict]]:
        """
        并行收集上下文数据（CV、Job、对话历史）- 优化②：Redis缓存 + asyncio.to_thread
        """
        # 并行获取CV和岗位信息（优化②：Redis缓存）
        cv_info = None
        job_info = None
        
        # CV缓存（优化②）
        if user_id:
            cache_key = f"cv:{user_id}"
            cached_cv = await redis_get_json(cache_key)
            if cached_cv:
                cv_info = cached_cv
                if logger.isEnabledFor(20):  # DEBUG
                    logger.debug(f"从缓存获取CV: {user_id}")
            else:
                cv_info = await cv_dao.get_cv_by_user_id(user_id)
                if cv_info:
                    await redis_setex_json(cache_key, 600, cv_info)  # TTL=10min
        else:
            # 默认CV缓存
            cache_key = "cv:default"
            cached_cv = await redis_get_json(cache_key)
            if cached_cv:
                cv_info = cached_cv
            else:
                cv_info = await cv_dao.get_default_cv()
                if cv_info:
                    await redis_setex_json(cache_key, 600, cv_info)
        
        # Job缓存（优化②）
        cache_key = f"job:{session_id}"
        cached_job = await redis_get_json(cache_key)
        if cached_job:
            job_info = cached_job
            if logger.isEnabledFor(20):  # DEBUG
                logger.debug(f"从缓存获取Job: {session_id}")
        else:
            job_info = await job_position_dao.get_job_position_by_session(session_id)
            if job_info:
                await redis_setex_json(cache_key, 600, job_info)  # TTL=10min
        
        # 获取对话历史（优化③：直接获取，不重复处理）
        chat_history = []
        if hasattr(session_state, "get_history_with_embeddings"):
            chat_history = session_state.get_history_with_embeddings(limit=20)
        
        return cv_info, job_info, chat_history
    
    def _format_context_data(
        self,
        cv_info: Optional[dict],
        job_info: Optional[dict],
        chat_history: List[dict],
        question: Optional[str],
        rag_context: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, str]:
        """
        格式化上下文数据为模板变量（优化③：减少字符串拼接，优化⑤：智能裁剪）
        """
        # 优化③：直接使用生成器表达式，避免多次append
        recent_dialogue_parts = (
            f"{item.get('speaker', 'unknown')}: {item.get('content', '')}"
            for item in chat_history[-10:]
            if item.get('content')
        )
        recent_dialogue = "\n".join(recent_dialogue_parts) if chat_history else "暂无对话记录"
        
        # 优化⑤：向量相似裁剪 - 如果提供了RAG上下文，优先使用
        if rag_context:
            rag_dialogue_parts = (
                f"{item.get('speaker', 'unknown')}: {item.get('content', '')}"
                for item in rag_context[:5]  # 最多5条
                if item.get('content')
            )
            rag_dialogue = "\n".join(rag_dialogue_parts)
            if rag_dialogue:
                recent_dialogue = f"{recent_dialogue}\n\n相关上下文：\n{rag_dialogue}"
        
        # 格式化问题
        question_text = question or "无特定问题，请基于对话上下文提供建议"
        
        # 格式化岗位信息（优化⑤：智能裁剪）
        job_text = "无岗位信息"
        if job_info:
            job_title = job_info.get('title', '')
            job_desc = job_info.get('description', '')
            job_req = job_info.get('requirements', '')
            job_parts = []
            if job_title:
                job_parts.append(f"岗位名称：{job_title}")
            if job_desc:
                # 优化⑤：动态裁剪
                max_job_desc_len = 200
                job_parts.append(f"岗位描述：{job_desc[:max_job_desc_len]}")
            if job_req:
                max_job_req_len = 300
                job_parts.append(f"岗位要求：{job_req[:max_job_req_len]}")
            if job_parts:
                job_text = "\n".join(job_parts)
        
        # 格式化简历信息（优化⑤：智能裁剪 + 预摘要缓存）
        cv_text = "无简历信息"
        if cv_info:
            cv_content = cv_info.get('content', '')
            if cv_content:
                # 优化⑤：动态token预算裁剪
                # 估算token数（简单估算：1 token ≈ 4字符）
                estimated_tokens = len(cv_content) // 4
                if estimated_tokens > self.max_context_tokens // 2:
                    # 如果CV太长，裁剪到合理长度
                    max_cv_len = (self.max_context_tokens // 2) * 4
                    cv_text = cv_content[:max_cv_len] + "..."
                    if logger.isEnabledFor(20):  # DEBUG
                        logger.debug(f"CV内容过长，裁剪到 {max_cv_len} 字符")
                else:
                    cv_text = cv_content
                if logger.isEnabledFor(20):  # DEBUG
                    logger.debug(f"格式化CV信息，长度: {len(cv_text)}")
            else:
                if logger.isEnabledFor(30):  # WARNING
                    logger.warning("CV信息存在但content字段为空")
        else:
            if logger.isEnabledFor(30):  # WARNING
                logger.warning("cv_info为None，无法使用简历信息")
        
        return {
            "cv": cv_text,
            "job": job_text,
            "question": question_text,
            "dialogue": recent_dialogue,
        }
    
    async def _generate_answer_suggestion(
        self,
        session_state: SessionState,
        session_id: str,
        user_id: Optional[str] = None,
        question: Optional[str] = None
    ) -> Optional[str]:
        """
        内部方法：生成回答建议（优化④：异步管线并发生成，优化⑥：结果缓存）
        """
        try:
            # 优化⑥：查询缓存
            query_inputs = {
                "session_id": session_id,
                "user_id": user_id,
                "question": question
            }
            query_hash = hashlib.sha1(
                json.dumps(query_inputs, sort_keys=True).encode()
            ).hexdigest()
            cache_key = f"ans:{query_hash}"
            
            cached_result = await redis_get_json(cache_key)
            if cached_result:
                if logger.isEnabledFor(20):  # DEBUG
                    logger.debug(f"从缓存获取回答建议: {query_hash[:8]}")
                return cached_result
            
            # 优化④：并发执行上下文收集和RAG检索
            cv_job_task = asyncio.create_task(
                self._collect_context_data(session_state, session_id, user_id)
            )
            
            # 如果提供了问题，同时进行RAG检索
            rag_task = None
            if question and hasattr(session_state, "get_history_with_embeddings"):
                rag_task = asyncio.create_task(
                    self.retrieve_relevant_context(session_state, question, top_k=5)
                )
            
            # 等待上下文数据
            cv_info, job_info, chat_history = await cv_job_task
            
            # 等待RAG检索（如果启动）
            rag_context = None
            if rag_task:
                rag_context = await rag_task
            
            if not chat_history:
                if logger.isEnabledFor(20):  # DEBUG
                    logger.debug("对话历史为空")
                return None
            
            # 2. 格式化数据（优化③：减少字符串拼接）
            inputs = self._format_context_data(cv_info, job_info, chat_history, question, rag_context)
            
            # 3. 使用LangChain Chain生成建议（优化⑥：并发控制）
            async with self._llm_semaphore:
                result = await self.chain.ainvoke(inputs)
            
            result = result.strip() if result else None
            
            # 优化⑥：缓存结果
            if result:
                await redis_setex_json(cache_key, 600, result)  # TTL=10min
            
            return result
        except AgentError:
            raise
        except Exception as e:
            logger.exception(f"生成回答建议失败: {e}")
            raise AgentError(f"生成回答建议失败: {str(e)}", cause=e)
    
    async def retrieve_relevant_context(
        self,
        session_state: SessionState,
        query: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        从内存对话历史中检索相关上下文（使用LangChain Retriever，优化⑤：向量相似裁剪）
        
        Args:
            session_state: 会话状态
            query: 查询文本
            top_k: 返回数量
        
        Returns:
            相关对话片段列表
        """
        try:
            # 使用LangChain Retriever（优化⑤：向量相似裁剪）
            retriever = SessionMemoryRetriever(session_state, top_k=top_k)
            documents = await retriever.aget_relevant_documents(query)
            
            # 转换为原有格式
            results = []
            for doc in documents:
                results.append({
                    'content': doc.page_content,
                    'speaker': doc.metadata.get('speaker', 'unknown'),
                    'similarity': doc.metadata.get('similarity', 0.0),
                    'timestamp': doc.metadata.get('timestamp')
                })
            
            return results
        except RetrievalError as e:
            if logger.isEnabledFor(40):  # ERROR
                logger.error(f"检索相关上下文失败: {e.message}")
            return []
        except Exception as e:
            logger.exception(f"检索相关上下文未知错误: {e}")
            return []


# 全局Agent实例（单例模式，优化①）
_interview_agent: Optional[InterviewAssistantAgent] = None


def get_interview_agent() -> InterviewAssistantAgent:
    """获取全局Agent实例（单例模式）"""
    global _interview_agent
    if _interview_agent is None:
        _interview_agent = InterviewAssistantAgent()
    return _interview_agent


# 向后兼容：保持原有的全局实例
interview_agent = get_interview_agent()
