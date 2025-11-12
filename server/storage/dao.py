"""
transcripts/kb CRUD操作
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import numpy as np
import json

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
            
            # 序列化metadata为JSON字符串（asyncpg需要）
            metadata_json = json.dumps(metadata) if metadata else None
            
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
                metadata_json
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
            results = []
            for row in rows:
                result = dict(row)
                # 将metadata从JSON字符串转换为字典
                if result.get('metadata') and isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
                elif result.get('metadata') is None:
                    result['metadata'] = None
                
                # 将datetime对象转换为ISO格式字符串
                if result.get('timestamp') and hasattr(result['timestamp'], 'isoformat'):
                    result['timestamp'] = result['timestamp'].isoformat()
                elif result.get('timestamp') is None:
                    result['timestamp'] = None
                
                results.append(result)
            return results
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
            
            # 序列化metadata为JSON字符串（asyncpg需要）
            metadata_json = json.dumps(metadata) if metadata else None
            
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
                metadata_json
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
            results = []
            for row in rows:
                result = dict(row)
                # 将metadata从JSON字符串转换为字典
                if result.get('metadata') and isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
                elif result.get('metadata') is None:
                    result['metadata'] = None
                
                # 将datetime对象转换为ISO格式字符串
                if result.get('created_at') and hasattr(result['created_at'], 'isoformat'):
                    result['created_at'] = result['created_at'].isoformat()
                elif result.get('created_at') is None:
                    result['created_at'] = None
                
                results.append(result)
            return results
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
            
            # 序列化metadata为JSON字符串（asyncpg需要）
            metadata_json = json.dumps(metadata) if metadata else None
            
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
                metadata_json
            )
            
            return result['id'] if result else 0
        except Exception as e:
            logger.error(f"保存CV失败: {e}")
            return 0
    
    async def get_default_cv(self, auto_generate_embedding: bool = True) -> Optional[Dict[str, Any]]:
        """
        获取默认CV（第一个用户的CV，按创建时间排序）
        
        Args:
            auto_generate_embedding: 如果embedding为空且API密钥已配置，是否自动生成
        
        Returns:
            CV信息或None
        """
        if not pg_pool.pool:
            return None
        
        try:
            # 先尝试查询embedding字段（检查pgvector是否可用）
            has_embedding = False
            try:
                query_with_embedding = """
                    SELECT id, user_id, content, metadata, created_at, updated_at,
                           CASE WHEN embedding IS NULL THEN NULL ELSE 'has_embedding' END as has_embedding
                    FROM cvs
                    ORDER BY created_at ASC
                    LIMIT 1
                """
                row = await pg_pool.fetchrow(query_with_embedding)
                if row:
                    result = dict(row)
                    has_embedding = result.pop('has_embedding') is not None
                else:
                    return None
            except Exception as e:
                # 如果embedding字段不存在（pgvector未安装），使用基础查询
                logger.debug(f"embedding字段不可用，使用基础查询: {e}")
                query = """
                    SELECT id, user_id, content, metadata, created_at, updated_at
                    FROM cvs
                    ORDER BY created_at ASC
                    LIMIT 1
                """
                row = await pg_pool.fetchrow(query)
                if not row:
                    return None
                result = dict(row)
                has_embedding = False  # 没有embedding字段，标记为False
            
            # 将metadata从JSON字符串转换为字典
            if result.get('metadata') and isinstance(result['metadata'], str):
                result['metadata'] = json.loads(result['metadata'])
            elif result.get('metadata') is None:
                result['metadata'] = None
            
            # 将datetime对象转换为ISO格式字符串
            if result.get('created_at') and hasattr(result['created_at'], 'isoformat'):
                result['created_at'] = result['created_at'].isoformat()
            elif result.get('created_at') is None:
                result['created_at'] = None
            
            if result.get('updated_at') and hasattr(result['updated_at'], 'isoformat'):
                result['updated_at'] = result['updated_at'].isoformat()
            elif result.get('updated_at') is None:
                result['updated_at'] = None
            
            # 自动生成embedding（如果需要）
            if auto_generate_embedding and not has_embedding and result.get('content'):
                try:
                    from utils.embedding import embedding_service
                    if embedding_service.api_key:
                        # 异步生成embedding并更新（不阻塞当前请求）
                        import asyncio
                        asyncio.create_task(self._update_cv_embedding(result['user_id'], result['content']))
                        logger.info(f"检测到CV缺少embedding，正在后台生成并更新: user_id={result['user_id']}")
                except Exception as e:
                    logger.warning(f"自动生成CV embedding失败: {e}")
            
            return result
        except Exception as e:
            logger.error(f"获取默认CV失败: {e}")
            return None
    
    async def get_cv_by_user_id(self, user_id: str, auto_generate_embedding: bool = True) -> Optional[Dict[str, Any]]:
        """
        获取用户CV
        
        Args:
            user_id: 用户ID
            auto_generate_embedding: 如果embedding为空且API密钥已配置，是否自动生成
        
        Returns:
            CV信息或None
        """
        if not pg_pool.pool:
            return None
        
        try:
            # 先尝试查询embedding字段（检查pgvector是否可用）
            has_embedding = False
            try:
                query_with_embedding = """
                    SELECT id, user_id, content, metadata, created_at, updated_at,
                           CASE WHEN embedding IS NULL THEN NULL ELSE 'has_embedding' END as has_embedding
                    FROM cvs
                    WHERE user_id = $1
                """
                row = await pg_pool.fetchrow(query_with_embedding, user_id)
                if row:
                    result = dict(row)
                    has_embedding = result.pop('has_embedding') is not None
                else:
                    return None
            except Exception as e:
                # 如果embedding字段不存在（pgvector未安装），使用基础查询
                logger.debug(f"embedding字段不可用，使用基础查询: {e}")
                query = """
                    SELECT id, user_id, content, metadata, created_at, updated_at
                    FROM cvs
                    WHERE user_id = $1
                """
                row = await pg_pool.fetchrow(query, user_id)
                if not row:
                    return None
                result = dict(row)
                has_embedding = False  # 没有embedding字段，标记为False
            
            # 将metadata从JSON字符串转换为字典
            if result.get('metadata') and isinstance(result['metadata'], str):
                result['metadata'] = json.loads(result['metadata'])
            elif result.get('metadata') is None:
                result['metadata'] = None
            
            # 将datetime对象转换为ISO格式字符串
            if result.get('created_at') and hasattr(result['created_at'], 'isoformat'):
                result['created_at'] = result['created_at'].isoformat()
            elif result.get('created_at') is None:
                result['created_at'] = None
            
            if result.get('updated_at') and hasattr(result['updated_at'], 'isoformat'):
                result['updated_at'] = result['updated_at'].isoformat()
            elif result.get('updated_at') is None:
                result['updated_at'] = None
            
            # 自动生成embedding（如果需要）
            if auto_generate_embedding and not has_embedding and result.get('content'):
                try:
                    from utils.embedding import embedding_service
                    if embedding_service.api_key:
                        # 异步生成embedding并更新（不阻塞当前请求）
                        import asyncio
                        asyncio.create_task(self._update_cv_embedding(user_id, result['content']))
                        logger.info(f"检测到CV缺少embedding，正在后台生成并更新: user_id={user_id}")
                except Exception as e:
                    logger.warning(f"自动生成CV embedding失败: {e}")
            
            return result
        except Exception as e:
            logger.error(f"获取CV失败: {e}")
            return None
    
    async def _update_cv_embedding(self, user_id: str, content: str):
        """
        后台更新CV的embedding（内部方法）
        
        Args:
            user_id: 用户ID
            content: CV内容
        """
        try:
            from utils.embedding import embedding_service
            embedding = await embedding_service.generate_embedding(content)
            if embedding is not None:
                embedding_str = f"[{','.join(map(str, embedding))}]"
                try:
                    update_query = """
                        UPDATE cvs
                        SET embedding = $1::vector, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = $2 AND embedding IS NULL
                    """
                    await pg_pool.execute(update_query, embedding_str, user_id)
                    logger.info(f"CV embedding已自动更新: user_id={user_id}")
                except Exception as e:
                    # 如果embedding字段不存在（pgvector未安装），记录警告但不报错
                    if "embedding" in str(e).lower() or "vector" in str(e).lower():
                        logger.warning(f"无法更新CV embedding（pgvector可能未安装）: {e}")
                    else:
                        raise
        except Exception as e:
            logger.error(f"更新CV embedding失败: {e}")
    
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
            
            # 序列化metadata为JSON字符串（asyncpg需要）
            metadata_json = json.dumps(metadata) if metadata else None
            
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
                metadata_json
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
            if not row:
                return None
            
            # 转换数据格式
            result = dict(row)
            
            # 将metadata从JSON字符串转换为字典
            if result.get('metadata') and isinstance(result['metadata'], str):
                result['metadata'] = json.loads(result['metadata'])
            elif result.get('metadata') is None:
                result['metadata'] = None
            
            # 将datetime对象转换为ISO格式字符串
            if result.get('created_at') and hasattr(result['created_at'], 'isoformat'):
                result['created_at'] = result['created_at'].isoformat()
            elif result.get('created_at') is None:
                result['created_at'] = None
            
            if result.get('updated_at') and hasattr(result['updated_at'], 'isoformat'):
                result['updated_at'] = result['updated_at'].isoformat()
            elif result.get('updated_at') is None:
                result['updated_at'] = None
            
            return result
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

