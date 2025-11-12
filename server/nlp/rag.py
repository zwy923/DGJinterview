"""
检索器：BM25+pgvector+重排+内存检索
"""
import asyncio
from typing import List, Optional
import numpy as np

from storage.dao import transcript_dao, kb_dao
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
    


# 全局检索器实例
rag_retriever = RAGRetriever()

