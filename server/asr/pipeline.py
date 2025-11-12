"""
VAD分段+partial/final聚合器（优化版：三段式端点，真流式识别）
"""
import asyncio
import time
from typing import Callable, Optional, List, Dict, Any
import numpy as np
from concurrent.futures import ThreadPoolExecutor

from asr.engine import get_asr_engine
from asr.session import SessionState
from asr.postprocess import get_postprocessor
from config import settings
from logs import setup_logger, log_metric
from utils.audio import estimate_energy, convert_to_float32

logger = setup_logger(__name__)

# 持久线程池（避免频繁创建销毁）
_executor: Optional[ThreadPoolExecutor] = None

def get_executor() -> ThreadPoolExecutor:
    """获取持久线程池"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="asr")
    return _executor


class ASRPipeline:
    """ASR处理管道：三段式VAD端点 + 流式识别 + partial/final聚合"""
    
    def __init__(self, state: SessionState):
        self.state = state
        self.engine = get_asr_engine()
        self.postprocessor = get_postprocessor()
        
        # 三段式端点参数
        self.pre_speech_padding = settings.VAD_PRE_SPEECH_PADDING
        self.end_silence = settings.VAD_END_SILENCE
        self.max_segment = settings.VAD_MAX_SEGMENT
        
        # 部分结果配置
        self.partial_interval = settings.PARTIAL_INTERVAL
        
        # 音频块处理超时（用于队列等待）
        self.chunk_timeout = 0.15  # 150ms（降低延迟）
        
        # 能量门控（仅做预过滤，真正端点交给 fsmn-vad）
        self.noise_decay = settings.AUDIO_NOISE_DECAY
        self.energy_threshold_multiplier = 2.8  # 优化阈值，平衡敏感度和准确性
        
        # 状态
        self.in_speech = False
        self.speech_buffer: List[np.ndarray] = []  # 前置缓冲
        self.last_partial_time: float = 0
        self.last_segment_has_trailing_silence = False  # 记录上一段是否有尾静音
    
    def _update_noise_level(self, rms: float):
        """更新噪声水平（浮点域 RMS）"""
        self.state.noise_level = (
            self.noise_decay * self.state.noise_level + 
            (1 - self.noise_decay) * rms
        )
    
    def _calculate_rms(self, audio: np.ndarray) -> float:
        """计算 RMS（浮点域）"""
        audio_float = convert_to_float32(audio)
        return estimate_energy(audio_float)
    
    async def process_audio_chunk(
        self,
        pcm_chunk: np.ndarray,
        on_partial: Optional[Callable[[str, float], None]] = None,
        on_final: Optional[Callable[[str, float, float], None]] = None
    ):
        """
        处理音频块（三段式端点检测）
        
        Args:
            pcm_chunk: PCM音频块
            on_partial: 部分结果回调 (text, timestamp)
            on_final: 最终结果回调 (text, start_time, end_time)
        """
        # 更新统计
        self.state.increment_stats("audio_chunks_received")
        
        # 计算 RMS（浮点域）
        rms = self._calculate_rms(pcm_chunk)
        self._update_noise_level(rms)
        
        # 能量门控阈值（仅做预过滤）
        energy_threshold = max(0.01, self.state.noise_level * self.energy_threshold_multiplier)
        has_energy = rms > energy_threshold
        
        current_time = time.time()
        chunk_duration = len(pcm_chunk) / self.state.sr
        
        # 三段式端点检测
        if has_energy:
            # 有能量：更新活动时间
            self.state.last_active = current_time
            
            if not self.in_speech:
                # 开始新语音段
                self.in_speech = True
                self.state.speech_start = current_time - self.pre_speech_padding
                # 将前置缓冲加入语音段
                self.speech_buffer = self.state.segment_buffer.copy()
                self.state.segment_buffer.clear()
            
            # 添加到当前语音段
            self.state.segment_buffer.append(pcm_chunk)
            
            # 检查最大段长（强制切分）
            if self.state.speech_start and (current_time - self.state.speech_start) >= self.max_segment:
                logger.warning(f"达到最大段长 {self.max_segment}s，强制切分")
                # 强制切分时，标记为有尾静音（虽然实际可能没有，但需要添加句号）
                self.last_segment_has_trailing_silence = True
                await self._process_segment(on_partial, on_final)
                # 重置状态
                self.in_speech = False
                self.state.speech_start = None
                self.speech_buffer.clear()
                self.state.segment_buffer.clear()
                self.state.last_active = current_time
                self.last_segment_has_trailing_silence = False
            
            # 周期产出部分结果
            if on_partial and (current_time - self.last_partial_time) >= self.partial_interval:
                await self._emit_partial(on_partial)
                self.last_partial_time = current_time
        
        else:
            # 无能量：检查是否结束
            silence_duration = current_time - self.state.last_active
            
            if self.in_speech:
                if silence_duration >= self.end_silence:
                    # 尾静音达到阈值 -> 一段语音结束
                    self.last_segment_has_trailing_silence = True
                    await self._process_segment(on_partial, on_final)
                    # 重置状态
                    self.in_speech = False
                    self.state.speech_start = None
                    self.speech_buffer.clear()
                    self.state.segment_buffer.clear()
                    self.state.last_active = current_time
                    self.last_segment_has_trailing_silence = False
                else:
                    # 仍在静音中，继续累积（可能恢复）
                    self.state.segment_buffer.append(pcm_chunk)
            else:
                # 未在语音中，累积到前置缓冲（最多保留 pre_speech_padding）
                self.state.segment_buffer.append(pcm_chunk)
                buffer_duration = sum(len(chunk) for chunk in self.state.segment_buffer) / self.state.sr
                if buffer_duration > self.pre_speech_padding:
                    # 移除最旧的块
                    self.state.segment_buffer.pop(0)
    
    async def _emit_partial(self, on_partial: Callable[[str, float], None]):
        """产出部分结果"""
        if len(self.state.segment_buffer) == 0:
            return
        
        # 合并当前语音段
        segment = np.concatenate(self.state.segment_buffer)
        
        # 使用流式识别（不重置 cache）
        try:
            raw_text = await asyncio.get_event_loop().run_in_executor(
                get_executor(),
                self._recognize_streaming,
                segment,
                False  # 不重置 cache
            )
            
            if raw_text.strip():
                # 部分结果也进行轻量后处理（不进行断句修正）
                text = self.postprocessor.clean_oral_speech(raw_text)
                
                if text.strip() and text != self.state.partial_text:
                    self.state.partial_text = text
                    timestamp = time.time()
                    await on_partial(text, timestamp)
        except Exception as e:
            logger.error(f"部分结果识别错误: {e}")
    
    def _recognize_streaming(self, audio: np.ndarray, reset_cache: bool = False) -> str:
        """流式识别（使用 per-session cache）"""
        if reset_cache:
            self.state.asr_cache = {}
        
        # 转换为float32并归一化
        pcm_f32 = convert_to_float32(audio)
        
        # 使用模型识别（复用 cache 实现流式）
        try:
            # 确保 cache 正确传递：
            # - 如果 reset_cache=True，清空 cache 后传入（新段开始）
            # - 如果 reset_cache=False，复用现有 cache（流式连续）
            if reset_cache:
                self.state.asr_cache = {}
            
            # 通过 engine 的 recognize 方法（传入 per-session cache）
            text = self.engine.recognize(
                audio,
                sample_rate=self.state.sr,
                cache=self.state.asr_cache  # 始终传入 cache，确保流式连续性
            )
            return text
        except Exception as e:
            logger.error(f"ASR识别错误: {e}")
            return ""
    
    @log_metric("asr_requests")
    async def _process_segment(
        self,
        on_partial: Optional[Callable[[str, float], None]],
        on_final: Optional[Callable[[str, float, float], None]]
    ):
        """处理音频段（最终识别）"""
        if len(self.state.segment_buffer) == 0:
            return
        
        # 合并音频段（包含前置缓冲）
        all_chunks = self.speech_buffer + self.state.segment_buffer
        segment = np.concatenate(all_chunks) if all_chunks else np.array([], dtype=np.int16)
        
        if len(segment) == 0:
            return
        
        # 更新统计
        self.state.increment_stats("segments_processed")
        duration_ms = len(segment) / self.state.sr * 1000
        self.state.increment_stats("total_duration_ms", int(duration_ms))
        
        # 计算时间戳
        start_time = self.state.speech_start or time.time()
        end_time = time.time()
        
        # 使用持久线程池执行识别（避免阻塞）
        try:
            raw_text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    get_executor(),
                    self._recognize_streaming,
                    segment,
                    True  # 重置 cache（新段开始）
                ),
                timeout=8.0  # 8秒超时，提高响应速度
            )
        except asyncio.TimeoutError:
            logger.error(f"ASR识别超时 (segment_length={len(segment)}, duration={len(segment)/self.state.sr:.2f}s)")
            raw_text = ""
        except Exception as e:
            logger.error(f"ASR识别异常: {e}", exc_info=True)
            raw_text = ""
        
        if raw_text.strip():
            # 后处理：口语清洗 + 断句策略优化
            try:
                text = self.postprocessor.process(
                    raw_text,
                    has_trailing_silence=self.last_segment_has_trailing_silence
                )
                
                if text.strip():
                    self.state.increment_stats("transcripts_generated")
                    
                    # 调用最终结果回调（带时间戳）
                    if on_final:
                        try:
                            await on_final(text, start_time, end_time)
                        except Exception as e:
                            logger.error(f"最终结果回调错误: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"后处理错误: {e}", exc_info=True)
                # 即使后处理失败，也尝试发送原始文本
                if raw_text.strip() and on_final:
                    try:
                        await on_final(raw_text, start_time, end_time)
                    except Exception as e2:
                        logger.error(f"发送原始文本错误: {e2}", exc_info=True)
        
        # 清空部分结果
        self.state.partial_text = ""
    
    async def flush(
        self,
        on_final: Optional[Callable[[str, float, float], None]] = None
    ):
        """刷新缓冲区中的剩余音频"""
        if len(self.state.segment_buffer) > 0 and self.in_speech:
            await self._process_segment(None, on_final)
    
    def reset(self):
        """重置管道状态"""
        self.state.segment_buffer.clear()
        self.speech_buffer.clear()
        self.in_speech = False
        self.state.speech_start = None
        self.last_partial_time = 0
        self.state.partial_text = ""
        self.state.asr_cache = {}
