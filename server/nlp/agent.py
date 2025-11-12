"""
轻量化LangChain面试助手Agent
基于内存向量检索为面试者提供回答建议
"""
import asyncio
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime

from asr.session import SessionState
from storage.dao import cv_dao, job_position_dao, kb_dao
from utils.embedding import embedding_service
from nlp.llm_api import llm_api
from config import settings
from logs import setup_logger

logger = setup_logger(__name__)


class InterviewAssistantAgent:
    """轻量化面试助手Agent：为面试者提供回答建议"""
    
    def __init__(self):
        self.timeout = settings.AGENT_TIMEOUT
    
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
            # 使用超时控制，确保轻量化
            return await asyncio.wait_for(
                self._generate_answer_suggestion(session_state, session_id, user_id, question),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Agent生成建议超时（{self.timeout}s）")
            return None
        except Exception as e:
            logger.error(f"Agent生成建议失败: {e}")
            return None
    
    async def _generate_answer_suggestion(
        self,
        session_state: SessionState,
        session_id: str,
        user_id: Optional[str] = None,
        question: Optional[str] = None
    ) -> Optional[str]:
        """内部方法：生成回答建议"""
        # 1. 获取内存对话历史（带向量）
        if not hasattr(session_state, "get_history_with_embeddings"):
            logger.warning("SessionState未初始化embedding历史")
            return None
        
        # get_history_with_embeddings 是同步方法，不需要 await
        chat_history = session_state.get_history_with_embeddings(limit=20)  # 最近20条
        
        if not chat_history:
            logger.debug("对话历史为空")
            return None
        
        # 2. 获取CV和岗位信息（异步并行，使用 asyncio.gather 确保所有任务都被等待）
        cv_info = None
        job_info = None
        
        tasks = []
        if user_id:
            tasks.append(("cv", cv_dao.get_cv_by_user_id(user_id)))
        tasks.append(("job", job_position_dao.get_job_position_by_session(session_id)))
        
        # 使用 gather 并发执行并捕获异常
        if tasks:
            results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
            for (key, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    logger.warning(f"获取{key}失败: {result}")
                else:
                    if key == "cv":
                        cv_info = result
                    elif key == "job":
                        job_info = result
        
        # 3. 构建上下文（最近对话摘要）- 安全提取字段
        recent_dialogue_parts = []
        for item in chat_history[-10:]:  # 最近10条对话
            speaker = item.get('speaker', 'unknown')
            content = item.get('content', '')
            if content:  # 只添加有内容的对话
                recent_dialogue_parts.append(f"{speaker}: {content}")
        
        recent_dialogue = "\n".join(recent_dialogue_parts) if recent_dialogue_parts else "暂无对话记录"
        
        # 4. 构建prompt - 为面试者提供回答建议（优化顺序：问题优先）
        prompt_parts = [
            "你是一位专业的面试助手，专门为面试者提供回答建议。",
        ]
        
        # 优先显示当前问题（如果有）
        if question:
            prompt_parts.extend([
                "\n【当前问题】",
                question,
            ])
        
        # 然后是岗位信息（重要上下文）
        if job_info:
            job_title = job_info.get('title', '')
            job_desc = job_info.get('description', '')
            job_req = job_info.get('requirements', '')
            job_text = f"岗位名称：{job_title}" if job_title else ""
            if job_desc:
                job_text += f"\n岗位描述：{job_desc[:200]}"  # 限制长度
            if job_req:
                job_text += f"\n岗位要求：{job_req[:300]}"  # 限制长度
            if job_text:
                prompt_parts.extend([
                    "\n【岗位信息】",
                    job_text,
                ])
        
        # 然后是简历信息
        if cv_info:
            cv_content = cv_info.get('content', '')
            if cv_content:
                cv_summary = cv_content[:500] + "..." if len(cv_content) > 500 else cv_content
                prompt_parts.extend([
                    "\n【候选人简历摘要】",
                    cv_summary,
                ])
        
        # 最后是对话上下文
        prompt_parts.extend([
            "\n【最近对话摘要】",
            recent_dialogue,
        ])
        
        # 添加指导说明
        prompt_parts.extend([
            "\n请基于以上内容，为面试者提供专业的回答建议。建议应该：",
            "1. 针对当前问题或对话上下文",
            "2. 结合岗位要求和候选人背景",
            "3. 提供具体、实用的回答要点和技巧",
            "4. 帮助面试者更好地展示自己的能力和经验",
            "5. 语言简洁明了，易于理解和应用",
            "\n请提供详细的回答建议。"
        ])
        
        prompt = "".join(prompt_parts)  # 使用空字符串连接，因为已经包含了换行符
        
        # 5. 调用LLM生成建议
        try:
            suggestion = await llm_api.generate(prompt)
            return suggestion.strip() if suggestion else None
        except Exception as e:
            logger.error(f"LLM生成建议失败: {e}")
            return None
    
    async def retrieve_relevant_context(
        self,
        session_state: SessionState,
        query: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        从内存对话历史中检索相关上下文（向量相似度）
        
        Args:
            session_state: 会话状态
            query: 查询文本
            top_k: 返回数量
        
        Returns:
            相关对话片段列表
        """
        try:
            # 检查 session_state
            if not hasattr(session_state, "get_history_with_embeddings"):
                logger.warning("SessionState未初始化embedding历史")
                return []
            
            # 生成查询向量
            query_embedding = await embedding_service.generate_embedding(query)
            if query_embedding is None:
                return []
            
            # 标准化查询向量
            qe = np.array(query_embedding, dtype=np.float32)
            qe_norm = np.linalg.norm(qe)
            if qe_norm == 0:
                logger.warning("查询向量为零向量")
                return []
            
            # 获取所有对话历史
            history = session_state.get_history_with_embeddings()
            if not history:
                return []
            
            # 计算相似度
            results = []
            for item in history:
                item_embedding = item.get('embedding')
                if item_embedding is None:
                    continue
                
                # 标准化item向量
                ie = np.array(item_embedding, dtype=np.float32)
                ie_norm = np.linalg.norm(ie)
                
                # 检查零向量
                if ie_norm == 0:
                    continue
                
                # 计算余弦相似度
                similarity = float(np.dot(qe, ie) / (qe_norm * ie_norm))
                
                # 过滤负数相似度（噪声）
                if similarity < 0:
                    continue
                
                results.append({
                    **item,
                    'similarity': similarity
                })
            
            # 按相似度排序
            results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            return results[:top_k]
        except Exception as e:
            logger.exception(f"检索相关上下文失败: {e}")
            return []


# 全局Agent实例
interview_agent = InterviewAssistantAgent()

