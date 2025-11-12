"""
Redis客户端包装器（可选）
"""
from typing import Optional, Any
import json
from config import settings
from logs import setup_logger

logger = setup_logger(__name__)

_redis_client: Optional[Any] = None


def get_redis_client():
    """获取Redis客户端（单例）"""
    global _redis_client
    
    if not settings.REDIS_ENABLED:
        return None
    
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"Redis客户端初始化成功: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        except ImportError:
            logger.warning("redis库未安装，Redis缓存功能将不可用。请安装: pip install redis")
            _redis_client = None
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            _redis_client = None
    
    return _redis_client


async def redis_get(key: str) -> Optional[str]:
    """从Redis获取值"""
    client = get_redis_client()
    if not client:
        return None
    try:
        return await client.get(key)
    except Exception as e:
        if logger.isEnabledFor(30):  # WARNING
            logger.warning(f"Redis GET失败: {e}")
        return None


async def redis_setex(key: str, ttl: int, value: str) -> bool:
    """设置Redis值（带TTL）"""
    client = get_redis_client()
    if not client:
        return False
    try:
        await client.setex(key, ttl, value)
        return True
    except Exception as e:
        if logger.isEnabledFor(30):  # WARNING
            logger.warning(f"Redis SETEX失败: {e}")
        return False


async def redis_get_json(key: str) -> Optional[Any]:
    """从Redis获取JSON值"""
    value = await redis_get(key)
    if value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


async def redis_setex_json(key: str, ttl: int, value: Any) -> bool:
    """设置Redis JSON值（带TTL）"""
    try:
        json_str = json.dumps(value, ensure_ascii=False)
        return await redis_setex(key, ttl, json_str)
    except (TypeError, ValueError) as e:
        if logger.isEnabledFor(30):  # WARNING
            logger.warning(f"Redis SETEX JSON失败: {e}")
        return False


async def close_redis():
    """关闭Redis连接"""
    global _redis_client
    if _redis_client:
        try:
            await _redis_client.close()
            _redis_client = None
        except Exception as e:
            logger.error(f"关闭Redis连接失败: {e}")

