"""
向量化服务（已禁用，仅保留接口兼容性）
"""
import numpy as np
from typing import List, Optional
from logs import setup_logger

logger = setup_logger(__name__)


class EmbeddingService:
    """向量化服务（已禁用，AI功能已移除）"""
    
    def __init__(self):
        self.api_key = None
        self.base_url = None
        self.model = None
    
    async def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        异步生成单个文本的向量（已禁用，仅保留接口兼容性）
        
        Args:
            text: 输入文本
        
        Returns:
            None（AI功能已移除）
        """
        # AI功能已移除，不再生成embedding
        return None
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[np.ndarray]]:
        """
        批量生成向量（已禁用，仅保留接口兼容性）
        
        Args:
            texts: 文本列表
        
        Returns:
            None列表（AI功能已移除）
        """
        # AI功能已移除，不再生成embedding
        return [None] * len(texts) if texts else []
    
    def clear_cache(self):
        """清空缓存（已禁用）"""
        pass


# 全局向量化服务实例
embedding_service = EmbeddingService()
