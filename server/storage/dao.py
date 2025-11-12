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
    """Knowledge Base数据访问对象（支持session隔离）"""
    
    async def save_knowledge(
        self,
        title: str,
        content: str,
        embedding: Optional[np.ndarray] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None
    ) -> int:
        """
        保存知识库条目
        
        Args:
            title: 标题
            content: 内容
            embedding: 向量嵌入（可选）
            metadata: 元数据（可选）
            session_id: 会话ID（可选，用于隔离）
        
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
                INSERT INTO knowledge_base (session_id, title, content, embedding, metadata)
                VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                RETURNING id
            """
            
            result = await pg_pool.fetchrow(
                query,
                session_id,
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
        session_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索相似的知识库条目
        
        Args:
            query_embedding: 查询向量
            session_id: 会话ID（可选，用于过滤）
            limit: 返回数量限制
        
        Returns:
            相似知识库条目列表
        """
        if not pg_pool.pool:
            return []
        
        try:
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            
            if session_id:
                query = """
                    SELECT id, session_id, title, content, metadata,
                           1 - (embedding <=> $1::vector) as similarity
                    FROM knowledge_base
                    WHERE session_id = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                """
                rows = await pg_pool.fetch(query, embedding_str, session_id, limit)
            else:
                query = """
                    SELECT id, session_id, title, content, metadata,
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
    
    async def get_knowledge_by_session(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取指定session的知识库条目
        
        Args:
            session_id: 会话ID
            limit: 返回数量限制
        
        Returns:
            知识库条目列表
        """
        if not pg_pool.pool:
            return []
        
        try:
            query = """
                SELECT id, title, content, metadata, created_at
                FROM knowledge_base
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """
            
            rows = await pg_pool.fetch(query, session_id, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取知识库条目失败: {e}")
            return []


class CVDAO:
    """CV数据访问对象"""
    
    async def save_cv(
        self,
        user_id: str,
        content: str,
        embedding: Optional[np.ndarray] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        保存CV（支持更新）
        
        Args:
            user_id: 用户ID
            content: CV内容
            embedding: 向量嵌入（可选）
            metadata: 元数据（可选）
        
        Returns:
            插入或更新的记录ID
        """
        if not pg_pool.pool:
            logger.warning("PostgreSQL未初始化，跳过保存")
            return 0
        
        try:
            embedding_str = None
            if embedding is not None:
                embedding_str = f"[{','.join(map(str, embedding))}]"
            
            # 使用 UPSERT (ON CONFLICT) 支持更新
            query = """
                INSERT INTO cvs (user_id, content, embedding, metadata)
                VALUES ($1, $2, $3::vector, $4::jsonb)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """
            
            result = await pg_pool.fetchrow(
                query,
                user_id,
                content,
                embedding_str,
                metadata
            )
            
            return result['id'] if result else 0
        except Exception as e:
            logger.error(f"保存CV失败: {e}")
            return 0
    
    async def get_cv_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户CV
        
        Args:
            user_id: 用户ID
        
        Returns:
            CV信息或None
        """
        if not pg_pool.pool:
            return None
        
        try:
            query = """
                SELECT id, user_id, content, metadata, created_at, updated_at
                FROM cvs
                WHERE user_id = $1
            """
            
            row = await pg_pool.fetchrow(query, user_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"获取CV失败: {e}")
            return None
    
    async def search_similar_cvs(
        self,
        query_embedding: np.ndarray,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索相似的CV
        
        Args:
            query_embedding: 查询向量
            limit: 返回数量限制
        
        Returns:
            相似CV列表
        """
        if not pg_pool.pool:
            return []
        
        try:
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            
            query = """
                SELECT id, user_id, content, metadata,
                       1 - (embedding <=> $1::vector) as similarity
                FROM cvs
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """
            
            rows = await pg_pool.fetch(query, embedding_str, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"搜索相似CV失败: {e}")
            return []


class JobPositionDAO:
    """Job Position数据访问对象"""
    
    async def save_job_position(
        self,
        session_id: str,
        title: str,
        description: Optional[str] = None,
        requirements: Optional[str] = None,
        embedding: Optional[np.ndarray] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        保存岗位信息（支持更新）
        
        Args:
            session_id: 会话ID
            title: 岗位名称
            description: 岗位描述
            requirements: 岗位要求
            embedding: 向量嵌入（可选）
            metadata: 元数据（可选）
        
        Returns:
            插入或更新的记录ID
        """
        if not pg_pool.pool:
            logger.warning("PostgreSQL未初始化，跳过保存")
            return 0
        
        try:
            embedding_str = None
            if embedding is not None:
                embedding_str = f"[{','.join(map(str, embedding))}]"
            
            # 合并描述和要求为完整文本用于向量化
            full_text = f"{title}\n{description or ''}\n{requirements or ''}".strip()
            
            # 使用 UPSERT 支持更新
            query = """
                INSERT INTO job_positions (session_id, title, description, requirements, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5::vector, $6::jsonb)
                ON CONFLICT (session_id) 
                DO UPDATE SET 
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    requirements = EXCLUDED.requirements,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """
            
            result = await pg_pool.fetchrow(
                query,
                session_id,
                title,
                description,
                requirements,
                embedding_str,
                metadata
            )
            
            return result['id'] if result else 0
        except Exception as e:
            logger.error(f"保存岗位信息失败: {e}")
            return 0
    
    async def get_job_position_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话的岗位信息
        
        Args:
            session_id: 会话ID
        
        Returns:
            岗位信息或None
        """
        if not pg_pool.pool:
            return None
        
        try:
            query = """
                SELECT id, session_id, title, description, requirements, metadata, created_at, updated_at
                FROM job_positions
                WHERE session_id = $1
            """
            
            row = await pg_pool.fetchrow(query, session_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"获取岗位信息失败: {e}")
            return None
    
    async def search_similar_positions(
        self,
        query_embedding: np.ndarray,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索相似的岗位
        
        Args:
            query_embedding: 查询向量
            limit: 返回数量限制
        
        Returns:
            相似岗位列表
        """
        if not pg_pool.pool:
            return []
        
        try:
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            
            query = """
                SELECT id, session_id, title, description, requirements, metadata,
                       1 - (embedding <=> $1::vector) as similarity
                FROM job_positions
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """
            
            rows = await pg_pool.fetch(query, embedding_str, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"搜索相似岗位失败: {e}")
            return []


# 全局DAO实例
transcript_dao = TranscriptDAO()
kb_dao = KnowledgeBaseDAO()
cv_dao = CVDAO()
job_position_dao = JobPositionDAO()

