"""
PostgreSQL/pgvector 连接与DDL
"""
import asyncpg
from typing import Optional, List, Dict, Any
from config import settings
from logs import setup_logger

logger = setup_logger(__name__)


class PostgreSQLPool:
    """PostgreSQL连接池"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """初始化连接池"""
        if not settings.RAG_ENABLED:
            logger.info("RAG未启用，跳过PostgreSQL初始化")
            return
        
        try:
            self.pool = await asyncpg.create_pool(
                host=settings.PG_HOST,
                port=settings.PG_PORT,
                database=settings.PG_DB,
                user=settings.PG_USER,
                password=settings.PG_PASSWORD,
                min_size=2,
                max_size=10,
            )
            logger.info("PostgreSQL连接池初始化成功")
            
            # 创建表结构
            await self.create_tables()
        except Exception as e:
            logger.error(f"PostgreSQL初始化失败: {e}")
            raise
    
    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL连接池已关闭")
    
    async def create_tables(self):
        """创建数据库表结构"""
        if not self.pool:
            return
        
        async with self.pool.acquire() as conn:
            # 启用pgvector扩展
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # 创建transcripts表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transcripts (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    speaker VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    embedding vector(%s),
                    metadata JSONB
                )
            """, settings.PG_VECTOR_DIM)
            
            # 创建knowledge_base表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_base (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector(%s),
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """, settings.PG_VECTOR_DIM)
            
            # 创建索引
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS transcripts_session_id_idx 
                ON transcripts(session_id)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS transcripts_embedding_idx 
                ON transcripts USING hnsw (embedding vector_cosine_ops)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS knowledge_base_embedding_idx 
                ON knowledge_base USING hnsw (embedding vector_cosine_ops)
            """)
            
            logger.info("数据库表结构创建完成")
    
    async def execute(self, query: str, *args) -> Any:
        """执行SQL查询"""
        if not self.pool:
            raise RuntimeError("PostgreSQL连接池未初始化")
        
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """获取查询结果"""
        if not self.pool:
            raise RuntimeError("PostgreSQL连接池未初始化")
        
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """获取单行查询结果"""
        if not self.pool:
            raise RuntimeError("PostgreSQL连接池未初始化")
        
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)


# 全局连接池实例
pg_pool = PostgreSQLPool()

