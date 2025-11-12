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
        chat_history = session_state.get_history_with_embeddings(limit=20)  # 最近20条
        
        if not chat_history:
            return None
        
        # 2. 获取CV和岗位信息（异步并行）
        cv_task = None
        job_task = None
        
        if user_id:
            cv_task = asyncio.create_task(cv_dao.get_cv_by_user_id(user_id))
        
        job_task = asyncio.create_task(job_position_dao.get_job_position_by_session(session_id))
        
        # 等待结果
        cv_info = None
        job_info = None
        
        if cv_task:
            try:
                cv_info = await cv_task
            except Exception as e:
                logger.error(f"获取CV失败: {e}")
        
        try:
            job_info = await job_task
        except Exception as e:
            logger.error(f"获取岗位信息失败: {e}")
        
        # 3. 构建上下文（最近对话摘要）
        recent_dialogue = "\n".join([
            f"{item['speaker']}: {item['content']}"
            for item in chat_history[-10:]  # 最近10条对话
        ])
        
        # 4. 构建prompt - 为面试者提供回答建议
        prompt_parts = [
            "你是一位专业的面试助手，专门为面试者提供回答建议。",
            "",
            "最近对话：",
            recent_dialogue,
        ]
        
        if question:
            prompt_parts.extend([
                "",
                "当前面试官的问题：",
                question,
            ])
        
        if job_info:
            prompt_parts.extend([
                "",
                "岗位信息：",
                f"岗位名称：{job_info.get('title', '')}",
                f"岗位描述：{job_info.get('description', '')}",
                f"岗位要求：{job_info.get('requirements', '')}",
            ])
        
        if cv_info:
            prompt_parts.extend([
                "",
                "候选人简历（摘要）：",
                cv_info.get('content', '')[:500] + "..." if len(cv_info.get('content', '')) > 500 else cv_info.get('content', ''),
            ])
        
        prompt_parts.extend([
            "",
            "请基于以上信息，为面试者提供专业的回答建议。建议应该：",
            "1. 针对面试官的问题或当前对话上下文",
            "2. 结合岗位要求和候选人背景",
            "3. 提供具体、实用的回答要点和技巧",
            "4. 帮助面试者更好地展示自己的能力和经验",
            "5. 语言简洁明了，易于理解和应用",
            "",
            "请提供详细的回答建议。"
        ])
        
        prompt = "\n".join(prompt_parts)
        
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
            # 生成查询向量
            query_embedding = await embedding_service.generate_embedding(query)
            if query_embedding is None:
                return []
            
            # 获取所有对话历史
            history = session_state.get_history_with_embeddings()
            
            # 计算相似度
            results = []
            for item in history:
                if item.get('embedding') is None:
                    continue
                
                item_embedding = np.array(item['embedding'])
                # 计算余弦相似度
                similarity = np.dot(query_embedding, item_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(item_embedding)
                )
                
                results.append({
                    **item,
                    'similarity': float(similarity)
                })
            
            # 按相似度排序
            results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            return results[:top_k]
        except Exception as e:
            logger.error(f"检索相关上下文失败: {e}")
            return []


# 全局Agent实例
interview_agent = InterviewAssistantAgent()

