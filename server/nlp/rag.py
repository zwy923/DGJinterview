"""
检索器：BM25+pgvector+重排+内存检索（性能优化版）
"""
import asyncio
import hashlib
from typing import List, Optional, Dict, Any
from functools import lru_cache
import numpy as np

from storage.dao import transcript_dao, kb_dao
from storage.pg import pg_pool
from utils.embedding import embedding_service
from utils.redis_client import redis_get_json, redis_setex_json
from config import settings
from logs import setup_logger

logger = setup_logger(__name__)


class RAGRetriever:
    """RAG检索器：结合BM25和向量检索（性能优化版）"""
    
    def __init__(self):
        self.enabled = settings.RAG_ENABLED
        
        # 优化⑤：内存检索加速 - session级别的向量索引缓存
        self.session_cache: Dict[str, Any] = {}
        self._cache_lock = asyncio.Lock()
        
        # 优化⑥：内存LRU缓存（超快命中）
        self._lru_cache_size = 128
        self._query_cache: Dict[str, List[dict]] = {}
    
    def _normalize_embedding(self, embedding: np.ndarray) -> np.ndarray:
        """优化⑦：向量归一化（提前计算）"""
        if embedding is None:
            return None
        
        embedding = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return embedding
        return embedding / norm
    
    def _calculate_dynamic_limit(self, query: str, top_k: int) -> int:
        """优化⑧：动态top-k策略"""
        query_len = len(query.split())
        if query_len > 10:
            expand_factor = 1.5  # 长查询，适度扩展
        else:
            expand_factor = 3.0  # 短查询，大幅扩展以提升召回率
        return int(top_k * expand_factor)
    
    def _deduplicate_results(self, results: List[dict]) -> List[dict]:
        """优化④：去重与聚合（哈希映射 + 优先保留高质量源）"""
        seen = set()
        unique = []
        
        for r in results:
            content = r.get("content", "")
            if not content:
                continue
            
            # 使用内容hash + source作为唯一键
            source = r.get("source", "unknown")
            content_id = r.get("id")
            unique_key = f"{source}:{content_id}:{hash(content)}"
            
            if unique_key not in seen:
                seen.add(unique_key)
                unique.append(r)
        
        return unique
    
    def _fuse_scores(self, vector_score: float, bm25_score: float = 0.0) -> float:
        """优化⑩：结果融合算法改进"""
        if bm25_score > 0:
            # 简单学习融合：向量相似度权重0.7，BM25权重0.3
            return 0.7 * vector_score + 0.3 * bm25_score
        return vector_score
    
    async def _bm25_search(
        self,
        query: str,
        session_id: Optional[str] = None,
        top_k: int = 10
    ) -> List[dict]:
        """
        BM25检索（优化②：与向量检索异步并行）
        
        TODO: 实现完整的BM25检索
        当前返回空列表，等待后续实现
        """
        # TODO: 实现BM25检索
        # 可以使用 pg_trgm 或全文搜索
        return []
    
    async def _rerank(
        self,
        results: List[dict],
        query: str
    ) -> List[dict]:
        """
        重排序结果（优化③：向量化 + 异步重排模型）
        
        当前使用简单相似度排序，未来可集成cross-encoder
        """
        if not results:
            return []
        
        # 简单重排序：基于相似度分数
        # 优化③：未来可集成cross-encoder（sentence-transformers/ms-marco-MiniLM-L-6-v2）
        # 示例代码（注释）：
        # texts = [(query, r["content"]) for r in results[:50]]
        # scores = await cross_encoder.score_async(texts)
        # for r, s in zip(results, scores): r["rerank_score"] = s
        
        sorted_results = sorted(
            results,
            key=lambda x: x.get("similarity", 0.0),
            reverse=True
        )
        
        return sorted_results
    
    async def retrieve(
        self,
        query: str,
        query_embedding: Optional[np.ndarray] = None,
        session_id: Optional[str] = None,
        top_k: int = None,
        rerank: bool = True
    ) -> List[dict]:
        """
        检索相关文档（性能优化版）
        
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
            if logger.isEnabledFor(30):  # WARNING
                logger.warning("RAG未启用")
            return []
        
        top_k = top_k or settings.RAG_TOP_K
        
        # 优化⑥：多层缓存策略 - 检查内存LRU缓存
        query_hash = hashlib.sha1(query.encode()).hexdigest()
        cache_key = f"rag_query:{query_hash}:{session_id or 'global'}:{top_k}"
        
        if cache_key in self._query_cache:
            if logger.isEnabledFor(20):  # DEBUG
                logger.debug(f"从内存LRU缓存获取RAG结果: {cache_key[:16]}")
            return self._query_cache[cache_key]
        
        # 优化⑥：检查Redis缓存
        redis_key = f"rag:{query_hash}:{session_id or 'global'}:{top_k}"
        cached_result = await redis_get_json(redis_key)
        if cached_result:
            # 更新内存LRU缓存
            if len(self._query_cache) >= self._lru_cache_size:
                # 简单的FIFO淘汰
                oldest_key = next(iter(self._query_cache))
                del self._query_cache[oldest_key]
            self._query_cache[cache_key] = cached_result
            
            if logger.isEnabledFor(20):  # DEBUG
                logger.debug(f"从Redis缓存获取RAG结果: {query_hash[:16]}")
            return cached_result
        
        # 优化⑦：向量归一化提前计算
        normalized_embedding = None
        if query_embedding is not None:
            normalized_embedding = self._normalize_embedding(query_embedding)
        
        # 优化⑧：动态top-k策略
        dynamic_limit = self._calculate_dynamic_limit(query, top_k)
        
        # 优化①：并发执行transcript和kb检索
        # 优化②：BM25与向量检索异步并行
        tasks = []
        
        if normalized_embedding is not None:
            # 向量检索任务
            vec_task = transcript_dao.search_similar(
                normalized_embedding,
                session_id=session_id,
                limit=dynamic_limit
            )
            tasks.append(("vector", vec_task))
            
            # 知识库检索任务（优化①：并发执行）
            kb_task = kb_dao.search_similar(
                normalized_embedding,
                session_id=session_id,
                limit=dynamic_limit
            )
            tasks.append(("kb", kb_task))
        
        # BM25检索任务（优化②：异步并行）
        bm25_task = self._bm25_search(query, session_id, dynamic_limit)
        tasks.append(("bm25", bm25_task))
        
        # 并发执行所有检索任务
        results = []
        if tasks:
            task_results = await asyncio.gather(
                *[task[1] for task in tasks],
                return_exceptions=True
            )
            
            for (key, _), result in zip(tasks, task_results):
                if isinstance(result, Exception):
                    if logger.isEnabledFor(30):  # WARNING
                        logger.warning(f"{key}检索失败: {result}")
                else:
                    # 添加source标记
                    for item in result:
                        item["source"] = key
                    results.extend(result)
        
        # 优化④：去重与聚合
        results = self._deduplicate_results(results)
        
        # 优化⑩：结果融合算法改进
        for r in results:
            vector_score = r.get("similarity", 0.0)
            bm25_score = r.get("bm25_score", 0.0)
            fused_score = self._fuse_scores(vector_score, bm25_score)
            r["final_score"] = fused_score
            # 保留原始similarity用于兼容
            if "final_score" not in r:
                r["similarity"] = fused_score
        
        # 优化③：去重和重排序
        if rerank:
            results = await self._rerank(results, query)
        else:
            # 即使不重排，也按final_score排序
            results = sorted(
                results,
                key=lambda x: x.get("final_score", x.get("similarity", 0.0)),
                reverse=True
            )
        
        # 返回top_k
        final_results = results[:top_k]
        
        # 优化⑥：缓存结果
        # 更新内存LRU缓存
        if len(self._query_cache) >= self._lru_cache_size:
            oldest_key = next(iter(self._query_cache))
            del self._query_cache[oldest_key]
        self._query_cache[cache_key] = final_results
        
        # 缓存到Redis（TTL=5min）
        await redis_setex_json(redis_key, 300, final_results)
        
        return final_results
    
    async def search_knowledge_base(
        self,
        query: str,
        query_embedding: Optional[np.ndarray] = None,
        session_id: Optional[str] = None,
        top_k: int = None
    ) -> List[dict]:
        """
        从知识库检索（支持session隔离，优化版）
        
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
        
        # 优化⑦：向量归一化
        normalized_embedding = self._normalize_embedding(query_embedding)
        
        results = await kb_dao.search_similar(
            normalized_embedding,
            session_id=session_id,
            limit=top_k
        )
        
        return results
    
    async def clear_cache(self, session_id: Optional[str] = None):
        """清除缓存（用于测试或手动刷新）"""
        if session_id:
            # 清除特定session的缓存
            keys_to_remove = [
                k for k in self._query_cache.keys()
                if session_id in k
            ]
            for k in keys_to_remove:
                del self._query_cache[k]
        else:
            # 清除所有缓存
            self._query_cache.clear()
        
        if logger.isEnabledFor(20):  # DEBUG
            logger.debug(f"已清除RAG缓存: session_id={session_id or 'all'}")


# 全局检索器实例
rag_retriever = RAGRetriever()
