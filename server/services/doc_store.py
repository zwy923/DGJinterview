"""
文档存储服务（pgvector）
"""
import numpy as np
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from storage.pg import pg_pool
from core.types import DocChunk
from core.config import agent_settings
from logs import setup_logger

logger = setup_logger(__name__)


class DocumentStore:
    """文档存储和检索服务"""
    
    async def add_documents(
        self,
        docs: List[Dict[str, Any]],
        session_id: Optional[str] = None
    ) -> bool:
        """
        添加文档到知识库
        
        Args:
            docs: 文档列表，每个文档包含：
                - content: 文本内容
                - title: 标题（可选）
                - metadata: 元数据（可选）
                - embedding: embedding向量（可选，如果没有会自动生成）
            session_id: 会话ID（可选，用于隔离）
        
        Returns:
            是否成功
        """
        if not pg_pool.pool or not pg_pool.vector_available:
            logger.warning("PostgreSQL或pgvector不可用，跳过文档存储")
            return False
        
        if not docs:
            return True
        
        try:
            from services.embed_service import embedding_service
            
            async with pg_pool.pool.acquire() as conn:
                for doc in docs:
                    content = doc.get("content", "").strip()
                    if not content:
                        continue
                    
                    title = doc.get("title", "")
                    metadata = doc.get("metadata", {})
                    embedding = doc.get("embedding")
                    
                    # 如果没有提供embedding，自动生成
                    if embedding is None:
                        embedding = await embedding_service.embed(content)
                        if embedding is None:
                            logger.warning(f"无法生成embedding，跳过文档: {title or content[:50]}")
                            continue
                    
                    # 转换为PostgreSQL格式
                    embedding_str = f"[{','.join(map(str, embedding))}]"
                    metadata_json = json.dumps(metadata) if metadata else None
                    
                    # 插入到knowledge_base表
                    query = """
                        INSERT INTO knowledge_base (session_id, title, content, embedding, metadata)
                        VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                        ON CONFLICT DO NOTHING
                    """
                    
                    await conn.execute(
                        query,
                        session_id,
                        title,
                        content,
                        embedding_str,
                        metadata_json
                    )
            
            logger.info(f"成功添加 {len(docs)} 个文档到知识库")
            return True
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            return False
    
    async def search_by_embedding(
        self,
        query_emb: np.ndarray,
        top_k: int,
        session_id: Optional[str] = None
    ) -> List[DocChunk]:
        """
        通过embedding向量检索文档
        
        Args:
            query_emb: 查询向量
            top_k: 返回top_k个结果
            session_id: 会话ID（可选，用于过滤）
        
        Returns:
            文档片段列表
        """
        if not pg_pool.pool or not pg_pool.vector_available:
            logger.warning("PostgreSQL或pgvector不可用，返回空结果")
            return []
        
        if query_emb is None or len(query_emb) == 0:
            return []
        
        try:
            # 转换为PostgreSQL格式
            embedding_str = f"[{','.join(map(str, query_emb))}]"
            
            # 构建查询（使用余弦相似度）
            if session_id:
                query = """
                    SELECT id, title, content, metadata,
                           1 - (embedding <=> $1::vector) as similarity
                    FROM knowledge_base
                    WHERE session_id = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                """
                params = [embedding_str, session_id, top_k]
            else:
                query = """
                    SELECT id, title, content, metadata,
                           1 - (embedding <=> $1::vector) as similarity
                    FROM knowledge_base
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                """
                params = [embedding_str, top_k]
            
            async with pg_pool.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
            
            results = []
            for row in rows:
                results.append(DocChunk(
                    content=row["content"],
                    source="knowledge_base",
                    metadata={
                        "id": row["id"],
                        "title": row.get("title", ""),
                        **(row.get("metadata") or {})
                    },
                    score=float(row["similarity"]) if row.get("similarity") else None
                ))
            
            logger.debug(f"检索到 {len(results)} 个文档片段")
            return results
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []


# 全局实例
doc_store = DocumentStore()

