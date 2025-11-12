"""
IAsrEngine 接口 + FunASRStreaming 实现
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict
import numpy as np
from funasr import AutoModel

from config import settings
from logs import setup_logger
import torch;
logger = setup_logger(__name__)


class IAsrEngine(ABC):
    """ASR引擎接口"""
    
    @abstractmethod
    def recognize(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """识别音频"""
        pass
    
    @abstractmethod
    def reset(self):
        """重置引擎状态"""
        pass


class FunASRStreaming(IAsrEngine):
    """FunASR流式识别引擎（支持 per-session cache）"""
    
    def __init__(self):
        self.model: Optional[AutoModel] = None
        self._load_model()
    
    def _load_model(self):
        """加载FunASR模型"""
        try:
            logger.info(f"⏳ Loading FunASR model (device={settings.ASR_DEVICE})...")
            self.model = AutoModel(
                model=settings.ASR_MODEL,
                vad_model=settings.ASR_VAD_MODEL,
                punc_model=settings.ASR_PUNC_MODEL,
                device=settings.ASR_DEVICE,
                disable_update=True,
            )
            logger.info("✅ FunASR model ready")
        except Exception as e:
            logger.error(f"FunASR模型加载失败: {e}")
            raise
    
    def recognize(self, audio: np.ndarray, sample_rate: int = 16000, cache: Optional[Dict] = None) -> str:
        """
        识别音频（支持外部 cache）
        
        Args:
            audio: PCM音频数组（int16）
            sample_rate: 采样率
            cache: 外部 cache（用于 per-session cache），如果为 None 则使用内部 cache
        
        Returns:
            识别文本
        """
        if self.model is None:
            logger.error("FunASR模型未加载")
            return ""
        
        if audio.size == 0:
            return ""
        
        try:
            # 转换为float32并归一化
            pcm_f32 = (audio.astype(np.float32) / 32768.0).clip(-1.0, 1.0)
            
            # 使用指定的 cache（确保流式识别的连续性）
            # 如果 cache 为 None，创建一个新的，但通常应该传入 per-session cache
            if cache is None:
                logger.warning("ASR cache 为 None，将创建新 cache，可能影响流式识别连续性")
                use_cache = {}
            else:
                use_cache = cache
            
            # 使用模型识别（复用 cache 实现流式）
            res = self.model.generate(input=pcm_f32, cache=use_cache, fs=sample_rate)
            
            if isinstance(res, list) and len(res) > 0:
                text = res[0].get("text", "")
                return text
        except Exception as e:
            logger.error(f"ASR识别错误: {e}")
        
        return ""
    
    def reset(self):
        """重置引擎状态（清空内部cache）"""
        # 注意：per-session cache 由 SessionState 管理，这里只重置内部 cache
        pass


# 全局ASR引擎实例（单例）
_asr_engine: Optional[FunASRStreaming] = None


def get_asr_engine() -> IAsrEngine:
    """获取ASR引擎实例（单例模式）"""
    global _asr_engine
    if _asr_engine is None:
        _asr_engine = FunASRStreaming()
    return _asr_engine

