"""
VAD分段+partial/final聚合器（优化版：三段式端点，真流式识别）
"""
import asyncio
import time
import re
from typing import Callable, Optional, List, Dict, Any
import numpy as np
from concurrent.futures import ThreadPoolExecutor, Future

from asr.engine import get_asr_engine
from core.state import SessionState
from asr.postprocess import get_postprocessor
from config import settings
from logs import setup_logger, log_metric
from utils.audio import estimate_energy, convert_to_float32, denoise_audio

logger = setup_logger(__name__)

# 持久线程池（避免频繁创建销毁）
_executor: Optional[ThreadPoolExecutor] = None

def get_executor() -> ThreadPoolExecutor:
    """获取持久线程池（增加worker数量以支持多会话并发）"""
    global _executor
    if _executor is None:
        # 增加worker数量：每个会话需要2个worker（mic+sys），加上缓冲
        # 默认8个worker，支持4个并发会话
        max_workers = 8
        _executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="asr")
        logger.info(f"ASR线程池已创建，worker数量: {max_workers}")
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
        self.energy_threshold_multiplier = 2.5  # 降低阈值，提高敏感度，减少漏检
        self.min_energy_threshold = 0.008  # 最小能量阈值，避免噪声误判
        
        # 状态
        self.in_speech = False
        self.speech_buffer: List[np.ndarray] = []  # 前置缓冲
        self.last_partial_time: float = 0
        self.last_segment_has_trailing_silence = False  # 记录上一段是否有尾静音
        
        # 去噪配置
        self.enable_denoise = getattr(settings, 'ASR_ENABLE_DENOISE', True)
        self.denoise_chunk_size = 3200  # 每次去噪的块大小（200ms @ 16kHz）
        
        # 去重配置：避免短时间内重复的结果
        self.last_final_text = ""  # 上一次的最终结果
        self.last_final_time = 0.0  # 上一次最终结果的时间
        self.duplicate_threshold = 2.0  # 去重时间窗口（秒）
    
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
        
        # 音频去噪（可选，在能量计算前进行）
        if self.enable_denoise and len(pcm_chunk) >= 256:
            try:
                pcm_chunk = denoise_audio(
                    pcm_chunk,
                    sample_rate=self.state.sr,
                    enable_highpass=True,
                    enable_spectral=True,
                    enable_gate=True
                )
            except Exception as e:
                # 去噪失败不影响主流程
                logger.debug(f"音频去噪失败（继续处理）: {e}")
        
        # 计算 RMS（浮点域）
        rms = self._calculate_rms(pcm_chunk)
        self._update_noise_level(rms)
        
        # 能量门控阈值（仅做预过滤，优化为更准确的检测）
        # 使用动态阈值：噪声水平 * 倍数，但不低于最小阈值
        energy_threshold = max(
            self.min_energy_threshold,
            self.state.noise_level * self.energy_threshold_multiplier
        )
        # 添加滞后机制，避免在阈值附近频繁切换
        if self.in_speech:
            # 在语音中时，使用较低的阈值（避免过早结束）
            has_energy = rms > (energy_threshold * 0.7)
        else:
            # 不在语音中时，使用正常阈值（避免误触发）
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
        """产出部分结果（优化：添加超时和错误处理）"""
        if len(self.state.segment_buffer) == 0:
            return
        
        # 合并当前语音段
        segment = np.concatenate(self.state.segment_buffer)
        
        # 使用流式识别（不重置 cache），带超时
        try:
            segment_duration = len(segment) / self.state.sr
            # 部分结果超时时间更短（1秒或段长*1.5，取较小值）
            timeout = min(max(segment_duration * 1.5, 0.5), 1.5)
            
            raw_text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    get_executor(),
                    self._recognize_streaming,
                    segment,
                    False  # 不重置 cache
                ),
                timeout=timeout
            )
            
            if raw_text.strip():
                # 部分结果也进行轻量后处理（不进行断句修正）
                text = self.postprocessor.clean_oral_speech(raw_text)
                
                # 只更新有变化的文本（避免重复发送）
                if text.strip() and text != self.state.partial_text:
                    self.state.partial_text = text
                    timestamp = time.time()
                    await on_partial(text, timestamp)
        except asyncio.TimeoutError:
            # 部分结果超时不影响主流程，静默忽略
            pass
        except Exception as e:
            logger.debug(f"部分结果识别错误（不影响主流程）: {e}")
    
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
    
    def _is_similar_text(self, text1: str, text2: str) -> bool:
        """
        判断两个文本是否相似（用于去重）
        """
        if not text1 or not text2:
            return False
        
        # 完全相同的文本
        if text1 == text2:
            return True
        
        # 去除标点和空格后比较
        clean1 = re.sub(r'[。！？，、\s]', '', text1)
        clean2 = re.sub(r'[。！？，、\s]', '', text2)
        
        if clean1 == clean2:
            return True
        
        # 如果其中一个包含另一个（可能是部分重复）
        if len(clean1) > 0 and len(clean2) > 0:
            if clean1 in clean2 or clean2 in clean1:
                # 但要求长度差异不能太大
                len_ratio = min(len(clean1), len(clean2)) / max(len(clean1), len(clean2))
                if len_ratio > 0.7:  # 长度相似度超过70%
                    return True
        
        return False
    
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
        future: Optional[Future] = None
        
        try:
            # 提交任务到线程池
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(
                get_executor(),
                self._recognize_streaming,
                segment,
                True  # 重置 cache（新段开始）
            )
            
            # 等待结果，带超时（根据段长动态调整）
            segment_duration = len(segment) / self.state.sr
            # 超时时间：段长 * 2 + 1秒（保证足够时间，但不过长）
            timeout = min(max(segment_duration * 2 + 1.0, 2.0), 6.0)
            raw_text = await asyncio.wait_for(
                future,
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"ASR识别超时 (segment_length={len(segment)}, duration={len(segment)/self.state.sr:.2f}s)，取消任务")
            # 尝试取消任务（虽然executor中的任务无法直接取消，但至少不会继续等待）
            if future and not future.done():
                # 标记为已取消，避免继续处理结果
                pass
            raw_text = ""
        except asyncio.CancelledError:
            logger.info(f"ASR识别任务被取消 (session={self.state.sid})")
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
                    # 去重检查：避免短时间内重复的结果
                    current_time = time.time()
                    time_since_last = current_time - self.last_final_time
                    
                    # 如果结果与上次相同或非常相似，且在时间窗口内，则跳过
                    if (time_since_last < self.duplicate_threshold and 
                        self._is_similar_text(text, self.last_final_text)):
                        logger.debug(f"跳过重复结果: {text} (距离上次 {time_since_last:.2f}s)")
                        # 清空部分结果
                        self.state.partial_text = ""
                        return
                    
                    self.state.increment_stats("transcripts_generated")
                    
                    # 更新去重状态
                    self.last_final_text = text
                    self.last_final_time = current_time
                    
                    # 调用最终结果回调（带时间戳）
                    if on_final:
                        try:
                            await on_final(text, start_time, end_time)
                        except Exception as e:
                            logger.error(f"最终结果回调错误: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"后处理错误: {e}", exc_info=True)
                # 即使后处理失败，也尝试发送原始文本（但也要过滤）
                if raw_text.strip():
                    # 简单过滤：至少要有非标点字符
                    if len(re.sub(r'[。！？，、\s]', '', raw_text)) >= self.postprocessor.min_sentence_length:
                        if on_final:
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
