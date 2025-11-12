"""
检索器：BM25+pgvector+重排+内存检索
"""
from typing import List, Optional
import numpy as np

from asr.session import SessionState
from storage.dao import transcript_dao, kb_dao, cv_dao, job_position_dao
from storage.pg import pg_pool
from utils.embedding import embedding_service
from config import settings
from logs import setup_logger

logger = setup_logger(__name__)


class RAGRetriever:
    """RAG检索器：结合BM25和向量检索"""
    
    def __init__(self):
        self.enabled = settings.RAG_ENABLED
    
    async def retrieve(
        self,
        query: str,
        query_embedding: Optional[np.ndarray] = None,
        session_id: Optional[str] = None,
        top_k: int = None,
        rerank: bool = True
    ) -> List[dict]:
        """
        检索相关文档
        
        Args:
            query: 查询文本
            query_embedding: 查询向量（可选）
            session_id: 会话ID（可选，用于过滤）
            top_k: 返回数量
            rerank: 是否重排序
        
        Returns:
            检索结果列表
        """
        if not self.enabled:
            logger.warning("RAG未启用")
            return []
        
        top_k = top_k or settings.RAG_TOP_K
        
        results = []
        
        # 向量检索
        if query_embedding is not None:
            vector_results = await transcript_dao.search_similar(
                query_embedding,
                session_id=session_id,
                limit=top_k * 2  # 获取更多结果用于重排
            )
            results.extend(vector_results)
        
        # TODO: 实现BM25检索
        # bm25_results = await self._bm25_search(query, session_id, top_k * 2)
        # results.extend(bm25_results)
        
        # 去重和重排序
        if rerank:
            results = self._rerank(results, query)
        
        # 返回top_k
        return results[:top_k]
    
    def _rerank(self, results: List[dict], query: str) -> List[dict]:
        """
        重排序结果
        
        Args:
            results: 检索结果
            query: 查询文本
        
        Returns:
            重排序后的结果
        """
        # 简单的重排序：基于相似度分数
        # TODO: 实现更复杂的重排序算法（如cross-encoder）
        sorted_results = sorted(
            results,
            key=lambda x: x.get("similarity", 0.0),
            reverse=True
        )
        return sorted_results
    
    async def search_knowledge_base(
        self,
        query: str,
        query_embedding: Optional[np.ndarray] = None,
        session_id: Optional[str] = None,
        top_k: int = None
    ) -> List[dict]:
        """
        从知识库检索（支持session隔离）
        
        Args:
            query: 查询文本
            query_embedding: 查询向量
            session_id: 会话ID（可选，用于过滤）
            top_k: 返回数量
        
        Returns:
            知识库检索结果
        """
        if not self.enabled or query_embedding is None:
            return []
        
        top_k = top_k or settings.RAG_TOP_K
        
        results = await kb_dao.search_similar(
            query_embedding,
            session_id=session_id,
            limit=top_k
        )
        
        return results
    
    async def retrieve_from_memory(
        self,
        session_state: SessionState,
        query: str,
        top_k: int = 5
    ) -> List[dict]:
        """
        从内存对话历史检索（向量相似度）
        
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
                    'similarity': float(similarity),
                    'source': 'memory'
                })
            
            # 按相似度排序
            results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            return results[:top_k]
        except Exception as e:
            logger.error(f"内存检索失败: {e}")
            return []
    
    async def retrieve_cv_and_job(
        self,
        session_id: str,
        query: str,
        user_id: Optional[str] = None,
        top_k: int = 3
    ) -> dict:
        """
        检索CV和岗位信息
        
        Args:
            session_id: 会话ID
            query: 查询文本
            user_id: 用户ID（可选）
            top_k: 返回数量
        
        Returns:
            包含CV和岗位信息的字典
        """
        result = {
            'cv': None,
            'job_position': None
        }
        
        try:
            # 生成查询向量
            query_embedding = await embedding_service.generate_embedding(query)
            if query_embedding is None:
                return result
            
            # 并行获取CV和岗位信息
            tasks = []
            
            if user_id:
                tasks.append(('cv', cv_dao.get_cv_by_user_id(user_id)))
            
            tasks.append(('job', job_position_dao.get_job_position_by_session(session_id)))
            
            # 执行任务
            for key, task in tasks:
                try:
                    value = await task
                    result[key] = value
                except Exception as e:
                    logger.error(f"获取{key}失败: {e}")
            
            return result
        except Exception as e:
            logger.error(f"检索CV和岗位信息失败: {e}")
            return result


# 全局检索器实例
rag_retriever = RAGRetriever()

