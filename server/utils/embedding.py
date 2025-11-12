"""
向量化服务：异步生成文本向量
"""
import asyncio
import aiohttp
import json
import numpy as np
from typing import List, Optional, Dict
from functools import lru_cache
from config import settings
from logs import setup_logger

logger = setup_logger(__name__)


class EmbeddingService:
    """向量化服务：异步调用OpenAI embedding API"""
    
    def __init__(self):
        self.api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
        self.base_url = settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL
        self.model = settings.EMBEDDING_MODEL
        self._cache: Dict[str, np.ndarray] = {}  # 简单内存缓存
    
    async def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        异步生成单个文本的向量
        
        Args:
            text: 输入文本
        
        Returns:
            向量数组（1536维）或None（失败时）
        """
        if not text or not text.strip():
            return None
        
        # 检查缓存
        text_key = text.strip()
        if text_key in self._cache:
            return self._cache[text_key]
        
        if not self.api_key:
            logger.warning("Embedding API密钥未配置，返回None")
            return None
        
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": text
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Embedding API错误: {response.status} - {error_text}")
                        return None
                    
                    data = await response.json()
                    embedding_data = data.get("data", [])
                    if not embedding_data:
                        logger.error("Embedding API返回空数据")
                        return None
                    
                    embedding = np.array(embedding_data[0]["embedding"], dtype=np.float32)
                    
                    # 缓存结果（限制缓存大小）
                    if len(self._cache) < 1000:
                        self._cache[text_key] = embedding
                    
                    return embedding
        except asyncio.TimeoutError:
            logger.error("Embedding API调用超时")
            return None
        except Exception as e:
            logger.error(f"Embedding API调用失败: {e}")
            return None
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[np.ndarray]]:
        """
        批量生成向量（优化：使用batch API）
        
        Args:
            texts: 文本列表
        
        Returns:
            向量数组列表
        """
        if not texts:
            return []
        
        # 过滤空文本并检查缓存
        valid_texts = []
        text_indices = []
        cached_results = []
        
        for i, text in enumerate(texts):
            if not text or not text.strip():
                cached_results.append((i, None))
            else:
                text_key = text.strip()
                if text_key in self._cache:
                    cached_results.append((i, self._cache[text_key]))
                else:
                    valid_texts.append(text)
                    text_indices.append(i)
        
        if not valid_texts:
            # 所有文本都在缓存中
            results = [None] * len(texts)
            for idx, embedding in cached_results:
                results[idx] = embedding
            return results
        
        if not self.api_key:
            logger.warning("Embedding API密钥未配置")
            return [None] * len(texts)
        
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": valid_texts
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Embedding API错误: {response.status} - {error_text}")
                        return [None] * len(texts)
                    
                    data = await response.json()
                    embedding_data = data.get("data", [])
                    
                    # 构建结果列表
                    results = [None] * len(texts)
                    
                    # 填充缓存结果
                    for idx, embedding in cached_results:
                        results[idx] = embedding
                    
                    # 填充新生成的结果
                    for i, item in enumerate(embedding_data):
                        if i < len(text_indices):
                            embedding = np.array(item["embedding"], dtype=np.float32)
                            text_idx = text_indices[i]
                            results[text_idx] = embedding
                            
                            # 缓存
                            text_key = valid_texts[i].strip()
                            if len(self._cache) < 1000:
                                self._cache[text_key] = embedding
                    
                    return results
        except asyncio.TimeoutError:
            logger.error("Embedding API批量调用超时")
            return [None] * len(texts)
        except Exception as e:
            logger.error(f"Embedding API批量调用失败: {e}")
            return [None] * len(texts)
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()


# 全局向量化服务实例
embedding_service = EmbeddingService()

