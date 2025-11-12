"""
基于LangChain的面试助手Agent
使用LangChain的Chain、Prompt和Retriever封装
"""
import asyncio
from typing import List, Dict, Any, Optional, Tuple

from langchain_core.runnables import RunnableMap, RunnableSequence
from langchain_core.output_parsers import StrOutputParser

from asr.session import SessionState
from storage.dao import cv_dao, job_position_dao
from nlp.langchain_components import CustomLLMWrapper, SessionMemoryRetriever
from nlp.prompts import prompt_manager
from nlp.exceptions import AgentError, RetrievalError
from config import settings
from logs import setup_logger

logger = setup_logger(__name__)


class InterviewAssistantAgent:
    """基于LangChain的面试助手Agent：为面试者提供回答建议"""
    
    def __init__(self):
        self.timeout = settings.AGENT_TIMEOUT
        self.llm = CustomLLMWrapper()
        self._build_chain()
    
    def _build_chain(self):
        """构建LangChain Chain"""
        # 从prompt_manager获取模板
        try:
            self.prompt_template = prompt_manager.get_prompt("interview_answer")
        except Exception as e:
            logger.error(f"加载Prompt模板失败: {e}")
            # 使用默认模板作为fallback
            from langchain_core.prompts import ChatPromptTemplate
            self.prompt_template = ChatPromptTemplate.from_template(
                "你是一位专业的面试助手。请基于以下信息提供回答建议：\n{cv}\n{job}\n{question}\n{dialogue}"
            )
        
        # 构建Chain：使用RunnableMap组合输入，然后通过模板和LLM
        # RunnableMap 会并行处理所有键，然后传递给下一个步骤
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
            # 使用asyncio.timeout (Python 3.12+)
            async with asyncio.timeout(self.timeout):
                return await self._generate_answer_suggestion(session_state, session_id, user_id, question)
        except TimeoutError:
            logger.warning(f"Agent生成建议超时（{self.timeout}s）")
            return None
        except AgentError as e:
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
        并行收集上下文数据（CV、Job、对话历史）
        
        Returns:
            (cv_info, job_info, chat_history)
        """
        # 并行获取CV和岗位信息
        tasks = []
        if user_id:
            logger.info(f"开始获取CV信息，user_id: {user_id}")
            tasks.append(("cv", cv_dao.get_cv_by_user_id(user_id)))
        else:
            logger.info("未提供user_id，尝试获取默认CV（第一个用户的CV）")
            tasks.append(("cv", cv_dao.get_default_cv()))
        tasks.append(("job", job_position_dao.get_job_position_by_session(session_id)))
        
        # 获取对话历史（同步方法）
        chat_history = []
        if hasattr(session_state, "get_history_with_embeddings"):
            chat_history = session_state.get_history_with_embeddings(limit=20)
        
        # 使用 gather 并发执行并捕获异常
        cv_info = None
        job_info = None
        if tasks:
            results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
            for (key, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    logger.warning(f"获取{key}失败: {result}")
                else:
                    if key == "cv":
                        cv_info = result
                        if cv_info:
                            logger.info(f"成功获取CV信息，content长度: {len(cv_info.get('content', ''))}")
                        else:
                            logger.warning(f"CV信息为空，user_id: {user_id}")
                    elif key == "job":
                        job_info = result
        
        return cv_info, job_info, chat_history
    
    def _format_context_data(
        self,
        cv_info: Optional[dict],
        job_info: Optional[dict],
        chat_history: List[dict],
        question: Optional[str]
    ) -> Dict[str, str]:
        """
        格式化上下文数据为模板变量
        
        Returns:
            包含 cv, job, question, dialogue 的字典
        """
        # 格式化对话历史
        recent_dialogue_parts = []
        for item in chat_history[-10:]:  # 最近10条对话
            speaker = item.get('speaker', 'unknown')
            content = item.get('content', '')
            if content:  # 只添加有内容的对话
                recent_dialogue_parts.append(f"{speaker}: {content}")
        
        recent_dialogue = "\n".join(recent_dialogue_parts) if recent_dialogue_parts else "暂无对话记录"
        
        # 格式化问题
        question_text = question or "无特定问题，请基于对话上下文提供建议"
        
        # 格式化岗位信息
        job_text = "无岗位信息"
        if job_info:
            job_title = job_info.get('title', '')
            job_desc = job_info.get('description', '')
            job_req = job_info.get('requirements', '')
            job_parts = []
            if job_title:
                job_parts.append(f"岗位名称：{job_title}")
            if job_desc:
                job_parts.append(f"岗位描述：{job_desc[:200]}")
            if job_req:
                job_parts.append(f"岗位要求：{job_req[:300]}")
            if job_parts:
                job_text = "\n".join(job_parts)
        
        # 格式化简历信息
        cv_text = "无简历信息"
        if cv_info:
            cv_content = cv_info.get('content', '')
            if cv_content:
                # 保留更多内容，不要截断太短
                cv_text = cv_content[:2000] + "..." if len(cv_content) > 2000 else cv_content
                logger.info(f"格式化CV信息，长度: {len(cv_text)}")
            else:
                logger.warning("CV信息存在但content字段为空")
        else:
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
        """内部方法：生成回答建议（使用LangChain Chain）"""
        try:
            # 1. 收集上下文数据
            cv_info, job_info, chat_history = await self._collect_context_data(
                session_state, session_id, user_id
            )
            
            if not chat_history:
                logger.debug("对话历史为空")
                return None
            
            # 2. 格式化数据
            inputs = self._format_context_data(cv_info, job_info, chat_history, question)
            
            # 3. 使用LangChain Chain生成建议
            result = await self.chain.ainvoke(inputs)
            return result.strip() if result else None
        except AgentError:
            # 重新抛出AgentError
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
        从内存对话历史中检索相关上下文（使用LangChain Retriever）
        
        Args:
            session_state: 会话状态
            query: 查询文本
            top_k: 返回数量
        
        Returns:
            相关对话片段列表
        """
        try:
            # 使用LangChain Retriever
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
            logger.error(f"检索相关上下文失败: {e.message}")
            return []
        except Exception as e:
            logger.exception(f"检索相关上下文未知错误: {e}")
            return []


# 全局Agent实例
interview_agent = InterviewAssistantAgent()

