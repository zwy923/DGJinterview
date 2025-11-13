"""
音频工具：重采样、增益、能量估计、去噪
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


def apply_highpass_filter(audio: np.ndarray, sample_rate: int, cutoff: float = 80.0) -> np.ndarray:
    """
    应用高通滤波器（去除低频噪声）
    
    Args:
        audio: 输入音频数组
        sample_rate: 采样率
        cutoff: 截止频率（Hz）
    
    Returns:
        滤波后的音频数组
    """
    if len(audio) < 3:
        return audio
    
    # 转换为float32
    audio_float = convert_to_float32(audio)
    
    # 设计Butterworth高通滤波器
    nyquist = sample_rate / 2.0
    normal_cutoff = cutoff / nyquist
    b, a = scipy.signal.butter(2, normal_cutoff, btype='high', analog=False)
    
    # 应用滤波器
    filtered = scipy.signal.filtfilt(b, a, audio_float)
    
    # 转换回原始格式
    if audio.dtype == np.int16:
        return (filtered * 32768.0).clip(-32768, 32767).astype(np.int16)
    return filtered


def apply_spectral_subtraction(
    audio: np.ndarray,
    sample_rate: int,
    noise_factor: float = 2.0,
    alpha: float = 2.0
) -> np.ndarray:
    """
    应用谱减法去噪（轻量级去噪算法）
    
    Args:
        audio: 输入音频数组
        sample_rate: 采样率
        noise_factor: 噪声估计因子（越大去噪越强）
        alpha: 过减因子（越大去噪越强，但可能失真）
    
    Returns:
        去噪后的音频数组
    """
    if len(audio) < 256:  # 太短的音频不处理
        return audio
    
    # 转换为float32
    audio_float = convert_to_float32(audio)
    
    # 使用短时傅里叶变换（STFT）
    frame_length = 512
    hop_length = 256
    
    # 计算STFT
    stft = scipy.signal.stft(
        audio_float,
        sample_rate,
        nperseg=frame_length,
        noverlap=frame_length - hop_length,
        window='hann'
    )
    frequencies, times, Zxx = stft
    
    # 估计噪声功率谱（使用前几帧，假设是静音）
    noise_frames = min(10, Zxx.shape[1] // 4)
    if noise_frames > 0:
        noise_power = np.mean(np.abs(Zxx[:, :noise_frames]) ** 2, axis=1, keepdims=True)
    else:
        noise_power = np.median(np.abs(Zxx) ** 2, axis=1, keepdims=True)
    
    # 计算信号功率谱
    signal_power = np.abs(Zxx) ** 2
    
    # 谱减法：从信号功率中减去噪声功率
    # 使用过减因子alpha，并添加底噪floor
    floor_factor = 0.02  # 保留2%的原始信号，避免过度去噪
    enhanced_power = signal_power - alpha * noise_factor * noise_power
    enhanced_power = np.maximum(enhanced_power, floor_factor * signal_power)
    
    # 计算增强后的幅度
    enhanced_magnitude = np.sqrt(enhanced_power)
    
    # 保持原始相位
    enhanced_stft = enhanced_magnitude * np.exp(1j * np.angle(Zxx))
    
    # 逆STFT
    _, enhanced_audio = scipy.signal.istft(
        enhanced_stft,
        sample_rate,
        nperseg=frame_length,
        noverlap=frame_length - hop_length,
        window='hann'
    )
    
    # 裁剪到原始长度
    if len(enhanced_audio) > len(audio_float):
        enhanced_audio = enhanced_audio[:len(audio_float)]
    elif len(enhanced_audio) < len(audio_float):
        # 如果变短了，用零填充
        padding = np.zeros(len(audio_float) - len(enhanced_audio), dtype=np.float32)
        enhanced_audio = np.concatenate([enhanced_audio, padding])
    
    # 转换回原始格式
    if audio.dtype == np.int16:
        return (enhanced_audio * 32768.0).clip(-32768, 32767).astype(np.int16)
    return enhanced_audio


def apply_simple_noise_gate(
    audio: np.ndarray,
    threshold_db: float = -40.0,
    attack_ms: float = 5.0,
    release_ms: float = 50.0,
    sample_rate: int = 16000
) -> np.ndarray:
    """
    应用简单的噪声门控（低于阈值的信号衰减）
    
    Args:
        audio: 输入音频数组
        threshold_db: 门控阈值（分贝）
        attack_ms: 启动时间（毫秒）
        release_ms: 释放时间（毫秒）
        sample_rate: 采样率
    
    Returns:
        门控后的音频数组
    """
    if len(audio) == 0:
        return audio
    
    # 转换为float32
    audio_float = convert_to_float32(audio)
    
    # 计算每帧的电平
    frame_length = int(sample_rate * 0.01)  # 10ms帧
    num_frames = len(audio_float) // frame_length
    
    if num_frames == 0:
        return audio
    
    # 计算每帧的RMS
    frames = audio_float[:num_frames * frame_length].reshape(num_frames, frame_length)
    frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))
    
    # 计算增益（低于阈值时衰减）
    threshold_linear = 10 ** (threshold_db / 20.0)
    gain = np.ones(num_frames)
    
    for i in range(num_frames):
        if frame_rms[i] < threshold_linear:
            # 计算衰减量（线性衰减到0.1）
            ratio = frame_rms[i] / threshold_linear
            gain[i] = 0.1 + 0.9 * ratio  # 最低保留10%
    
    # 应用平滑（attack/release）
    attack_samples = int(sample_rate * attack_ms / 1000.0)
    release_samples = int(sample_rate * release_ms / 1000.0)
    
    smoothed_gain = np.ones(num_frames)
    for i in range(1, num_frames):
        if gain[i] > smoothed_gain[i-1]:
            # Attack: 快速上升
            alpha = 1.0 / max(attack_samples // frame_length, 1)
        else:
            # Release: 缓慢下降
            alpha = 1.0 / max(release_samples // frame_length, 1)
        smoothed_gain[i] = alpha * gain[i] + (1 - alpha) * smoothed_gain[i-1]
    
    # 应用增益到每帧
    for i in range(num_frames):
        frames[i] *= smoothed_gain[i]
    
    # 转换回原始格式
    result = frames.flatten()
    if len(result) < len(audio_float):
        result = np.concatenate([result, audio_float[len(result):]])
    
    if audio.dtype == np.int16:
        return (result * 32768.0).clip(-32768, 32767).astype(np.int16)
    return result


def denoise_audio(
    audio: np.ndarray,
    sample_rate: int = 16000,
    enable_highpass: bool = True,
    enable_spectral: bool = True,
    enable_gate: bool = True
) -> np.ndarray:
    """
    综合去噪处理（组合多种去噪方法）
    
    Args:
        audio: 输入音频数组
        sample_rate: 采样率
        enable_highpass: 是否启用高通滤波
        enable_spectral: 是否启用谱减法
        enable_gate: 是否启用噪声门控
    
    Returns:
        去噪后的音频数组
    """
    if len(audio) == 0:
        return audio
    
    result = audio.copy()
    
    # 1. 高通滤波（去除低频噪声）
    if enable_highpass:
        result = apply_highpass_filter(result, sample_rate, cutoff=80.0)
    
    # 2. 谱减法（去除背景噪声）
    if enable_spectral and len(result) >= 512:
        result = apply_spectral_subtraction(result, sample_rate, noise_factor=1.5, alpha=2.0)
    
    # 3. 噪声门控（去除低电平噪声）
    if enable_gate:
        result = apply_simple_noise_gate(result, threshold_db=-35.0, sample_rate=sample_rate)
    
    return result

