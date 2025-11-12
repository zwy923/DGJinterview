"""
Embedding服务（仅RAG使用）
"""
import numpy as np
from typing import List, Optional
import aiohttp
import json

from core.config import agent_settings
from logs import setup_logger

logger = setup_logger(__name__)


class EmbeddingService:
    """Embedding生成服务"""
    
    def __init__(self):
        self.api_key = agent_settings.EMBEDDING_API_KEY
        self.base_url = agent_settings.EMBEDDING_BASE_URL
        self.model = agent_settings.EMBEDDING_MODEL
        
        if not self.api_key:
            logger.warning("EMBEDDING_API_KEY未设置，embedding功能将不可用")
    
    async def embed(self, text: str) -> Optional[np.ndarray]:
        """
        生成单个文本的embedding
        
        Args:
            text: 输入文本
        
        Returns:
            embedding向量（numpy数组）或None
        """
        if not self.api_key or not text or not text.strip():
            return None
        
        try:
            results = await self.embed_batch([text])
            return results[0] if results else None
        except Exception as e:
            logger.error(f"生成embedding失败: {e}")
            return None
    
    async def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        批量生成embedding
        
        Args:
            texts: 文本列表
        
        Returns:
            embedding向量列表
        """
        if not self.api_key or not texts:
            return []
        
        # 过滤空文本
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return []
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url.rstrip('/')}/embeddings"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.model,
                    "input": valid_texts
                }
                
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Embedding API错误: {resp.status} - {error_text}")
                        return []
                    
                    data = await resp.json()
                    embeddings = []
                    for item in data.get("data", []):
                        embedding = item.get("embedding")
                        if embedding:
                            embeddings.append(np.array(embedding, dtype=np.float32))
                    
                    return embeddings
        except Exception as e:
            logger.error(f"批量生成embedding失败: {e}")
            return []


# 全局实例
embedding_service = EmbeddingService()

