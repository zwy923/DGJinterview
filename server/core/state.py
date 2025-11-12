"""
SessionState（队列、统计、时戳）
重构版本：使用deque管理对话历史，添加CV/JD字段
"""
import asyncio
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import deque
import numpy as np

from config import settings
from core.config import agent_settings


class SessionState:
    """
    音频流状态类
    - 每个 WebSocket 会维护一个独立的 SessionState 实例
    - 包含音频缓存、VAD参数、状态标志、统计信息等
    - 使用deque管理对话历史（最近N条）
    """
    def __init__(self, sid: str, sr: int = None, source: str = "mic"):
        self.sid = sid
        self.source = source  # "mic" or "sys"
        self.sr = sr or settings.ASR_SAMPLE_RATE
        
        # 音频队列和缓冲区（带背压控制）
        self.audio_q: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=settings.WS_AUDIO_QUEUE_MAX_SIZE)
        self.segment_buffer: List[np.ndarray] = []
        
        # 状态标志
        self.stop: bool = False
        self.seq: int = 0
        
        # VAD参数（三段式端点）
        self.last_active: float = time.time()
        self.speech_start: Optional[float] = None  # 语音开始时间
        # 噪声水平初始值（浮点域 RMS，范围 0-1）
        # 初始值约 0.0006，对应 int16 域的 20/32768
        self.noise_level: float = 0.0006
        
        # 流式识别 cache（per-session）
        self.asr_cache: Dict[str, Any] = {}
        
        # 部分结果相关
        self.last_partial_time: float = 0
        self.partial_text: str = ""
        
        # 内存对话历史（使用deque，最多N条，不包含embedding）
        # 每个条目包含：content, speaker, timestamp, metadata
        max_history = agent_settings.CHAT_HISTORY_MAX
        self.chat_history: deque = deque(maxlen=max_history)
        
        # CV和JD文本（用于Agent上下文）
        self.cv_text: str = ""
        self.jd_text: str = ""
        
        # 元数据（模型配置、语言偏好等）
        self.meta: Dict[str, Any] = {}
        
        # 统计信息
        self.stats: Dict[str, Any] = {
            "start_time": datetime.now().isoformat(),
            "audio_chunks_received": 0,
            "segments_processed": 0,
            "transcripts_generated": 0,
            "total_duration_ms": 0,
        }
    
    def next_seq(self) -> int:
        """生成下一个消息序号"""
        self.seq += 1
        return self.seq
    
    def update_stats(self, key: str, value: Any):
        """更新统计信息"""
        self.stats[key] = value
    
    def increment_stats(self, key: str, value: int = 1):
        """增加统计值"""
        if key in self.stats and isinstance(self.stats[key], (int, float)):
            self.stats[key] += value
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        end_time = datetime.now()
        start_time = datetime.fromisoformat(self.stats["start_time"])
        duration = (end_time - start_time).total_seconds()
        
        return {
            **self.stats,
            "duration_seconds": duration,
            "queue_size": self.audio_q.qsize(),
            "buffer_size": len(self.segment_buffer),
            "chat_history_size": len(self.chat_history),
        }
    
    def add_to_history(
        self,
        content: str,
        speaker: str,
        embedding: Optional[np.ndarray] = None,  # 保留参数以兼容，但不再使用
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None
    ):
        """
        添加对话到内存历史（仅内存存储，不保存到数据库）
        不再生成或存储embedding
        
        Args:
            content: 对话内容
            speaker: 说话者
            embedding: 向量嵌入（已废弃，保留以兼容）
            metadata: 元数据（可选）
            timestamp: 时间戳（可选，默认当前时间）
        """
        if not content or not content.strip():
            return
        
        timestamp_str = timestamp or datetime.now().isoformat()
        
        entry = {
            "content": content.strip(),
            "speaker": speaker,
            "timestamp": timestamp_str,
            "metadata": metadata or {}
        }
        
        # deque会自动处理maxlen限制
        self.chat_history.append(entry)
    
    def get_history_with_embeddings(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取对话历史（供Agent调用）
        注意：不再包含embedding字段
        
        Args:
            limit: 返回数量限制（可选）
        
        Returns:
            对话历史列表（最近N条）
        """
        history = list(self.chat_history)
        if limit is not None and limit > 0:
            history = history[-limit:]
        return history.copy()
    
    def clear_history(self):
        """清空对话历史"""
        self.chat_history.clear()
    
    def reset(self):
        """清空状态（可复用 Session）"""
        self.audio_q = asyncio.Queue(maxsize=settings.WS_AUDIO_QUEUE_MAX_SIZE)
        self.segment_buffer.clear()
        self.stop = False
        self.seq = 0
        self.noise_level = 0.0006  # 浮点域 RMS 初始值
        self.last_active = time.time()
        self.speech_start = None
        self.asr_cache = {}
        self.last_partial_time = 0
        self.partial_text = ""
        self.chat_history.clear()  # 清空对话历史
        self.cv_text = ""
        self.jd_text = ""
        self.meta = {}
        self.stats = {
            "start_time": datetime.now().isoformat(),
            "audio_chunks_received": 0,
            "segments_processed": 0,
            "transcripts_generated": 0,
            "total_duration_ms": 0,
        }
    
    def __repr__(self):
        return f"<SessionState sid={self.sid}, source={self.source}, seq={self.seq}, queue={self.audio_q.qsize()}>"

