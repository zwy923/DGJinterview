"""
音频工具：重采样、增益、能量估计
"""
import numpy as np
from typing import Tuple, Optional
import scipy.signal


def resample_audio(
    audio: np.ndarray,
    original_sr: int,
    target_sr: int
) -> np.ndarray:
    """
    重采样音频
    
    Args:
        audio: 输入音频数组
        original_sr: 原始采样率
        target_sr: 目标采样率
    
    Returns:
        重采样后的音频数组
    """
    if original_sr == target_sr:
        return audio
    
    # 计算重采样后的长度
    num_samples = int(len(audio) * target_sr / original_sr)
    
    # 使用scipy进行重采样
    resampled = scipy.signal.resample(audio, num_samples)
    
    return resampled.astype(audio.dtype)


def apply_gain(audio: np.ndarray, gain_db: float) -> np.ndarray:
    """
    应用增益（分贝）
    
    Args:
        audio: 输入音频数组
        gain_db: 增益值（分贝）
    
    Returns:
        增益后的音频数组
    """
    if gain_db == 0:
        return audio
    
    # 转换为线性增益
    linear_gain = 10 ** (gain_db / 20.0)
    
    # 应用增益并限制范围
    if audio.dtype == np.int16:
        result = (audio.astype(np.float32) * linear_gain).clip(-32768, 32767)
        return result.astype(np.int16)
    else:
        result = (audio * linear_gain).clip(-1.0, 1.0)
        return result


def estimate_energy(audio: np.ndarray) -> float:
    """
    估计音频能量
    
    Args:
        audio: 输入音频数组
    
    Returns:
        能量值（RMS）
    """
    if len(audio) == 0:
        return 0.0
    
    # 转换为浮点数
    if audio.dtype == np.int16:
        audio_float = audio.astype(np.float32) / 32768.0
    else:
        audio_float = audio.astype(np.float32)
    
    # 计算RMS（均方根）
    rms = np.sqrt(np.mean(audio_float ** 2))
    
    return float(rms)


def estimate_db(audio: np.ndarray, reference: float = 1.0) -> float:
    """
    估计音频分贝值
    
    Args:
        audio: 输入音频数组
        reference: 参考值（默认1.0）
    
    Returns:
        分贝值
    """
    energy = estimate_energy(audio)
    if energy == 0:
        return -np.inf
    
    db = 20 * np.log10(energy / reference)
    return float(db)


def normalize_audio(audio: np.ndarray, target_level_db: float = -3.0) -> np.ndarray:
    """
    归一化音频到目标电平
    
    Args:
        audio: 输入音频数组
        target_level_db: 目标电平（分贝）
    
    Returns:
        归一化后的音频数组
    """
    if len(audio) == 0:
        return audio
    
    # 计算当前电平
    current_db = estimate_db(audio)
    
    # 计算需要的增益
    gain_db = target_level_db - current_db
    
    # 应用增益
    return apply_gain(audio, gain_db)


def detect_silence(
    audio: np.ndarray,
    threshold_db: float = -40.0,
    min_duration_ms: float = 100.0,
    sample_rate: int = 16000
) -> bool:
    """
    检测静音
    
    Args:
        audio: 输入音频数组
        threshold_db: 静音阈值（分贝）
        min_duration_ms: 最小静音持续时间（毫秒）
        sample_rate: 采样率
    
    Returns:
        是否为静音
    """
    if len(audio) == 0:
        return True
    
    # 计算音频电平
    db = estimate_db(audio)
    
    # 检查是否低于阈值
    if db < threshold_db:
        # 检查持续时间
        duration_ms = len(audio) / sample_rate * 1000
        return duration_ms >= min_duration_ms
    
    return False


def convert_to_int16(audio: np.ndarray) -> np.ndarray:
    """
    转换为int16格式
    
    Args:
        audio: 输入音频数组（float32或int16）
    
    Returns:
        int16格式的音频数组
    """
    if audio.dtype == np.int16:
        return audio
    
    # 假设输入是-1.0到1.0的浮点数
    audio_clipped = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio_clipped * 32767).astype(np.int16)
    
    return audio_int16


def convert_to_float32(audio: np.ndarray) -> np.ndarray:
    """
    转换为float32格式
    
    Args:
        audio: 输入音频数组（int16或float32）
    
    Returns:
        float32格式的音频数组（范围-1.0到1.0）
    """
    if audio.dtype == np.float32:
        return audio
    
    # 假设输入是int16
    audio_float = audio.astype(np.float32) / 32768.0
    return audio_float

