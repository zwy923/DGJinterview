"""
系统音频捕获模块
使用 pyaudio 和 numpy 捕获系统音频，支持实时流式处理
"""
import asyncio
import threading
import time
import numpy as np
import pyaudio
from typing import Optional, Callable, Dict, Any
from queue import Queue
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SystemAudioCapture:
    """系统音频捕获器"""
    
    def __init__(self, 
                 sample_rate: int = 16000,
                 channels: int = 1,
                 chunk_size: int = 1024,
                 format: int = pyaudio.paInt16):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.format = format
        
        self.audio = None
        self.stream = None
        self.is_capturing = False
        self.audio_queue = Queue(maxsize=100)
        self.callbacks: Dict[str, Callable] = {}
        
    def initialize(self) -> bool:
        """初始化音频系统"""
        try:
            self.audio = pyaudio.PyAudio()
            
            # 查找合适的输入设备
            device_index = self._find_system_audio_device()
            if device_index is None:
                logger.warning("未找到系统音频设备，使用默认设备")
                device_index = None
                
            logger.info(f"使用音频设备索引: {device_index}")
            return True
            
        except Exception as e:
            logger.error(f"音频系统初始化失败: {e}")
            return False
    
    def _find_system_audio_device(self) -> Optional[int]:
        """查找系统音频设备（立体声混音器、What U Hear等）"""
        if not self.audio:
            return None
            
        device_count = self.audio.get_device_count()
        logger.info(f"发现 {device_count} 个音频设备")
        
        # 优先查找输入设备
        input_devices = []
        for i in range(device_count):
            try:
                info = self.audio.get_device_info_by_index(i)
                device_name = info.get('name', '').lower()
                max_input_channels = info.get('maxInputChannels', 0)
                
                # 只考虑有输入通道的设备
                if max_input_channels > 0:
                    input_devices.append((i, info, max_input_channels))
                    
            except Exception as e:
                logger.debug(f"检查设备 {i} 失败: {e}")
        
        # 在输入设备中查找系统音频设备
        system_devices = []
        for i, info, max_channels in input_devices:
            device_name = info.get('name', '').lower()
            
            # 查找可能的系统音频设备
            system_keywords = [
                'stereo mix', '立体声混音', 'what u hear', 
                'system audio', 'loopback', 'monitor'
            ]
            
            if any(keyword in device_name for keyword in system_keywords):
                system_devices.append((i, info, max_channels))
                logger.info(f"找到系统音频设备: {info['name']} (索引: {i}, 输入声道: {max_channels})")
        
        # 如果有系统音频设备，返回第一个
        if system_devices:
            i, info, max_channels = system_devices[0]
            return i
        
        # 如果没有找到专门的系统音频设备，使用第一个有输入通道的设备
        if input_devices:
            i, info, max_channels = input_devices[0]
            logger.info(f"使用默认输入设备: {info['name']} (索引: {i}, 输入声道: {max_channels})")
            return i
                
        return None
    
    def start_capture(self) -> bool:
        """开始音频捕获"""
        if not self.audio:
            logger.error("音频系统未初始化")
            return False
            
        if self.is_capturing:
            logger.warning("音频捕获已在进行中")
            return True
            
        try:
            # 获取设备信息以确定正确的声道数
            device_index = self._find_system_audio_device()
            if device_index is not None:
                device_info = self.audio.get_device_info_by_index(device_index)
                max_channels = device_info.get('maxInputChannels', 1)
                
                # 确保至少有一个声道
                if max_channels <= 0:
                    logger.error(f"设备 {device_index} 不支持输入声道")
                    return False
                
                # 使用设备支持的最大声道数，但限制为2
                actual_channels = min(max_channels, 2)
                logger.info(f"设备 {device_index} 支持 {max_channels} 个输入声道，使用 {actual_channels} 个声道")
            else:
                logger.error("未找到可用的音频输入设备")
                return False
            
            # 创建音频流，添加错误处理
            try:
                self.stream = self.audio.open(
                    format=self.format,
                    channels=actual_channels,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self.chunk_size,
                    stream_callback=self._audio_callback
                )
            except Exception as stream_error:
                logger.error(f"创建音频流失败: {stream_error}")
                
                # 如果立体声混音设备失败，尝试使用默认设备
                if device_index is not None:
                    logger.info("尝试使用默认音频设备...")
                    try:
                        self.stream = self.audio.open(
                            format=self.format,
                            channels=1,  # 使用单声道
                            rate=self.sample_rate,
                            input=True,
                            input_device_index=None,  # 使用默认设备
                            frames_per_buffer=self.chunk_size,
                            stream_callback=self._audio_callback
                        )
                        logger.info("使用默认音频设备成功")
                    except Exception as default_error:
                        logger.error(f"默认设备也失败: {default_error}")
                        return False
                else:
                    return False
            
            self.is_capturing = True
            self.stream.start_stream()
            logger.info("系统音频捕获已启动")
            return True
            
        except Exception as e:
            logger.error(f"启动音频捕获失败: {e}")
            return False
    
    def stop_capture(self):
        """停止音频捕获"""
        if not self.is_capturing:
            return
            
        self.is_capturing = False
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error(f"停止音频流失败: {e}")
            finally:
                self.stream = None
                
        logger.info("系统音频捕获已停止")
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """音频数据回调函数"""
        if not self.is_capturing:
            return (None, pyaudio.paComplete)
            
        try:
            # 将字节数据转换为numpy数组
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            
            # 如果是多声道，转换为单声道（取平均值）
            if len(audio_data.shape) > 1 or audio_data.size > frame_count:
                # 重新整形为 (frame_count, channels)
                channels = audio_data.size // frame_count
                if channels > 1:
                    audio_data = audio_data.reshape(frame_count, channels)
                    # 取平均值转换为单声道
                    audio_data = np.mean(audio_data, axis=1).astype(np.int16)
                else:
                    audio_data = audio_data.reshape(frame_count)
            
            # 将数据放入队列
            if not self.audio_queue.full():
                self.audio_queue.put(audio_data)
            
            # 触发回调
            for name, callback in self.callbacks.items():
                try:
                    callback(audio_data)
                    # 调试：每100个块打印一次（约每秒一次，假设1024样本/块，16kHz采样率）
                    if hasattr(self, '_callback_count'):
                        self._callback_count += 1
                    else:
                        self._callback_count = 1
                    if self._callback_count % 100 == 0:
                        logger.debug(f"系统音频回调 [{name}]: 已处理 {self._callback_count} 个音频块，当前块大小: {len(audio_data)}")
                except Exception as e:
                    logger.error(f"音频回调 [{name}] 执行失败: {e}")
                    
        except Exception as e:
            logger.error(f"音频回调处理失败: {e}")
            
        return (None, pyaudio.paContinue)
    
    def add_callback(self, name: str, callback: Callable[[np.ndarray], None]):
        """添加音频数据回调"""
        self.callbacks[name] = callback
        
    def remove_callback(self, name: str):
        """移除音频数据回调"""
        self.callbacks.pop(name, None)
    
    def get_audio_data(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """获取音频数据（非阻塞）"""
        try:
            return self.audio_queue.get(timeout=timeout)
        except:
            return None
    
    def cleanup(self):
        """清理资源"""
        self.stop_capture()
        
        if self.audio:
            try:
                self.audio.terminate()
            except Exception as e:
                logger.error(f"清理音频系统失败: {e}")
            finally:
                self.audio = None
                
        logger.info("系统音频捕获器已清理")


# 全局音频捕获器实例
_audio_capture: Optional[SystemAudioCapture] = None

def get_audio_capture() -> SystemAudioCapture:
    """获取全局音频捕获器实例"""
    global _audio_capture
    if _audio_capture is None:
        _audio_capture = SystemAudioCapture()
        if not _audio_capture.initialize():
            raise RuntimeError("无法初始化系统音频捕获器")
    return _audio_capture

async def start_system_audio_capture(callback: Callable[[np.ndarray], None]) -> bool:
    """启动系统音频捕获"""
    try:
        capture = get_audio_capture()
        capture.add_callback("system_audio", callback)
        return capture.start_capture()
    except Exception as e:
        logger.error(f"启动系统音频捕获失败: {e}")
        return False

def stop_system_audio_capture():
    """停止系统音频捕获"""
    global _audio_capture
    if _audio_capture:
        _audio_capture.stop_capture()
        _audio_capture.remove_callback("system_audio")

def cleanup_system_audio():
    """清理系统音频资源"""
    global _audio_capture
    if _audio_capture:
        _audio_capture.cleanup()
        _audio_capture = None
