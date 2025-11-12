"""
transcripts/kb CRUD操作
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import numpy as np

from storage.pg import pg_pool
from utils.schemas import ChatMessage
from logs import setup_logger

logger = setup_logger(__name__)


class TranscriptDAO:
    """Transcript数据访问对象"""
    
    async def save_transcript(
        self,
        session_id: str,
        speaker: str,
        content: str,
        embedding: Optional[np.ndarray] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        保存transcript
        
        Args:
            session_id: 会话ID
            speaker: 说话者
            content: 内容
            embedding: 向量嵌入（可选）
            metadata: 元数据（可选）
        
        Returns:
            插入的记录ID
        """
        if not pg_pool.pool:
            logger.warning("PostgreSQL未初始化，跳过保存")
            return 0
        
        try:
            # 转换embedding为PostgreSQL格式
            embedding_str = None
            if embedding is not None:
                embedding_str = f"[{','.join(map(str, embedding))}]"
            
            query = """
                INSERT INTO transcripts (session_id, speaker, content, embedding, metadata)
                VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                RETURNING id
            """
            
            result = await pg_pool.fetchrow(
                query,
                session_id,
                speaker,
                content,
                embedding_str,
                metadata
            )
            
            return result['id'] if result else 0
        except Exception as e:
            logger.error(f"保存transcript失败: {e}")
            return 0
    
    async def get_transcripts(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取会话的transcripts
        
        Args:
            session_id: 会话ID
            limit: 返回数量限制
        
        Returns:
            transcript列表
        """
        if not pg_pool.pool:
            return []
        
        try:
            query = """
                SELECT id, speaker, content, timestamp, metadata
                FROM transcripts
                WHERE session_id = $1
                ORDER BY timestamp ASC
                LIMIT $2
            """
            
            rows = await pg_pool.fetch(query, session_id, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取transcripts失败: {e}")
            return []
    
    async def search_similar(
        self,
        query_embedding: np.ndarray,
        session_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索相似的transcripts
        
        Args:
            query_embedding: 查询向量
            session_id: 会话ID（可选，用于过滤）
            limit: 返回数量限制
        
        Returns:
            相似transcript列表
        """
        if not pg_pool.pool:
            return []
        
        try:
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            
            if session_id:
                query = """
                    SELECT id, session_id, speaker, content, timestamp,
                           1 - (embedding <=> $1::vector) as similarity
                    FROM transcripts
                    WHERE session_id = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                """
                rows = await pg_pool.fetch(query, embedding_str, session_id, limit)
            else:
                query = """
                    SELECT id, session_id, speaker, content, timestamp,
                           1 - (embedding <=> $1::vector) as similarity
                    FROM transcripts
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                """
                rows = await pg_pool.fetch(query, embedding_str, limit)
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"搜索相似transcripts失败: {e}")
            return []


class KnowledgeBaseDAO:
    """Knowledge Base数据访问对象"""
    
    async def save_knowledge(
        self,
        title: str,
        content: str,
        embedding: Optional[np.ndarray] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        保存知识库条目
        
        Args:
            title: 标题
            content: 内容
            embedding: 向量嵌入（可选）
            metadata: 元数据（可选）
        
        Returns:
            插入的记录ID
        """
        if not pg_pool.pool:
            logger.warning("PostgreSQL未初始化，跳过保存")
            return 0
        
        try:
            embedding_str = None
            if embedding is not None:
                embedding_str = f"[{','.join(map(str, embedding))}]"
            
            query = """
                INSERT INTO knowledge_base (title, content, embedding, metadata)
                VALUES ($1, $2, $3::vector, $4::jsonb)
                RETURNING id
            """
            
            result = await pg_pool.fetchrow(
                query,
                title,
                content,
                embedding_str,
                metadata
            )
            
            return result['id'] if result else 0
        except Exception as e:
            logger.error(f"保存知识库条目失败: {e}")
            return 0
    
    async def search_similar(
        self,
        query_embedding: np.ndarray,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索相似的知识库条目
        
        Args:
            query_embedding: 查询向量
            limit: 返回数量限制
        
        Returns:
            相似知识库条目列表
        """
        if not pg_pool.pool:
            return []
        
        try:
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            
            query = """
                SELECT id, title, content, metadata,
                       1 - (embedding <=> $1::vector) as similarity
                FROM knowledge_base
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """
            
            rows = await pg_pool.fetch(query, embedding_str, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"搜索相似知识库条目失败: {e}")
            return []


# 全局DAO实例
transcript_dao = TranscriptDAO()
kb_dao = KnowledgeBaseDAO()

