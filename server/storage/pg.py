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
        self.vector_available: bool = False  # pgvector扩展是否可用
    
    async def initialize(self):
        """初始化连接池"""
        if not settings.PG_ENABLED:
            logger.info("PostgreSQL未启用，跳过初始化")
            return
        
        # 检查PostgreSQL配置是否完整
        if not all([settings.PG_HOST, settings.PG_DB, settings.PG_USER]):
            logger.warning("PostgreSQL配置不完整，跳过初始化")
            return
        
        try:
            logger.info(f"正在连接PostgreSQL: {settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DB}")
            self.pool = await asyncpg.create_pool(
                host=settings.PG_HOST,
                port=settings.PG_PORT,
                database=settings.PG_DB,
                user=settings.PG_USER,
                password=settings.PG_PASSWORD,
                min_size=2,
                max_size=10,
                timeout=10,  # 连接超时10秒
            )
            logger.info("PostgreSQL连接池初始化成功")
            
            # 创建表结构
            await self.create_tables()
        except asyncpg.exceptions.InvalidPasswordError as e:
            logger.error(f"PostgreSQL认证失败: 用户名或密码错误")
            logger.error(f"请检查配置: PG_USER={settings.PG_USER}, PG_PASSWORD={'*' * len(settings.PG_PASSWORD) if settings.PG_PASSWORD else '(空)'}")
            self.pool = None
        except asyncpg.exceptions.InvalidCatalogNameError as e:
            logger.error(f"PostgreSQL数据库不存在: {settings.PG_DB}")
            logger.error(f"请创建数据库或检查配置: PG_DB={settings.PG_DB}")
            self.pool = None
        except (asyncpg.exceptions.ConnectionDoesNotExistError, ConnectionRefusedError, OSError) as e:
            logger.error(f"PostgreSQL连接失败: 无法连接到 {settings.PG_HOST}:{settings.PG_PORT}")
            logger.error(f"请确保PostgreSQL服务正在运行，并检查配置: PG_HOST={settings.PG_HOST}, PG_PORT={settings.PG_PORT}")
            self.pool = None
        except Exception as e:
            logger.error(f"PostgreSQL初始化失败: {type(e).__name__}: {e}")
            logger.error(f"连接配置: {settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DB} (用户: {settings.PG_USER})")
            self.pool = None
    
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
            # 尝试启用pgvector扩展（可选，用于向量检索）
            self.vector_available = False
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                self.vector_available = True
                logger.info("pgvector扩展已启用，向量检索功能可用")
            except Exception as e:
                logger.warning(f"pgvector扩展不可用: {e}")
                logger.warning("向量检索功能将不可用，但基本数据存储功能仍然可用")
                logger.warning("如需使用向量检索，请安装pgvector扩展")
                # 继续创建表，但embedding列将不可用
            
            # 创建transcripts表
            if self.vector_available:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS transcripts (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255) NOT NULL,
                        speaker VARCHAR(50) NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        embedding vector({settings.PG_VECTOR_DIM}),
                        metadata JSONB
                    )
                """)
            else:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS transcripts (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255) NOT NULL,
                        speaker VARCHAR(50) NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB
                    )
                """)
            
            # 创建knowledge_base表（支持session隔离）
            if self.vector_available:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS knowledge_base (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255),
                        title VARCHAR(255) NOT NULL,
                        content TEXT NOT NULL,
                        embedding vector({settings.PG_VECTOR_DIM}),
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            else:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_base (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255),
                        title VARCHAR(255) NOT NULL,
                        content TEXT NOT NULL,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            # 创建cvs表
            if self.vector_available:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS cvs (
                        id SERIAL PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL UNIQUE,
                        content TEXT NOT NULL,
                        embedding vector({settings.PG_VECTOR_DIM}),
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            else:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS cvs (
                        id SERIAL PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL UNIQUE,
                        content TEXT NOT NULL,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            # 创建job_positions表
            if self.vector_available:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS job_positions (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255) NOT NULL UNIQUE,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        requirements TEXT,
                        embedding vector({settings.PG_VECTOR_DIM}),
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            else:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS job_positions (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255) NOT NULL UNIQUE,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        requirements TEXT,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            # 创建索引
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS transcripts_session_id_idx 
                ON transcripts(session_id)
            """)
            
            if self.vector_available:
                try:
                    await conn.execute("""
                        CREATE INDEX IF NOT EXISTS transcripts_embedding_idx 
                        ON transcripts USING hnsw (embedding vector_cosine_ops)
                    """)
                    
                    await conn.execute("""
                        CREATE INDEX IF NOT EXISTS knowledge_base_embedding_idx 
                        ON knowledge_base USING hnsw (embedding vector_cosine_ops)
                    """)
                    
                    await conn.execute("""
                        CREATE INDEX IF NOT EXISTS cvs_embedding_idx 
                        ON cvs USING hnsw (embedding vector_cosine_ops)
                    """)
                except Exception as e:
                    logger.warning(f"创建向量索引失败: {e}")
            
            # 为knowledge_base添加session_id索引
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS knowledge_base_session_id_idx 
                ON knowledge_base(session_id)
            """)
            
            # 为cvs表创建索引
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS cvs_user_id_idx 
                ON cvs(user_id)
            """)
            
            # 为job_positions表创建索引
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS job_positions_session_id_idx 
                ON job_positions(session_id)
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

