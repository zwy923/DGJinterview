"""
统一配置模块
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field

# 获取server目录的绝对路径
SERVER_DIR = Path(__file__).parent.resolve()
ENV_FILE_PATH = SERVER_DIR / ".env"


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用基础配置
    APP_NAME: str = "大狗叫面试助手"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # 服务器配置
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # ASR配置
    ASR_MODEL: str = "paraformer-zh"
    ASR_VAD_MODEL: str = "fsmn-vad"
    ASR_PUNC_MODEL: str = "ct-punc"
    ASR_DEVICE: str = os.getenv("ASR_DEVICE", "cuda")  # cpu or cuda（如果系统没有CUDA，使用cpu）
    ASR_SAMPLE_RATE: int = 16000
    
    # ASR 后处理配置
    ASR_ENABLE_ORAL_CLEANING: bool = os.getenv("ASR_ENABLE_ORAL_CLEANING", "true").lower() == "false"
    ASR_ENABLE_NUMBER_NORMALIZATION: bool = os.getenv("ASR_ENABLE_NUMBER_NORMALIZATION", "true").lower() == "true"
    ASR_ENABLE_REPEAT_REMOVAL: bool = os.getenv("ASR_ENABLE_REPEAT_REMOVAL", "true").lower() == "true"
    ASR_ENABLE_PUNCTUATION_CORRECTION: bool = os.getenv("ASR_ENABLE_PUNCTUATION_CORRECTION", "true").lower() == "true"
    ASR_MIN_SENTENCE_LENGTH: int = int(os.getenv("ASR_MIN_SENTENCE_LENGTH", "8"))  # 最小句子长度（字符数），降低阈值提高响应速度
    
    # ASR 去噪配置
    ASR_ENABLE_DENOISE: bool = os.getenv("ASR_ENABLE_DENOISE", "true").lower() == "true"  # 是否启用音频去噪
    
    # 语言路由配置（预留）
    ASR_ENABLE_LANG_ID: bool = os.getenv("ASR_ENABLE_LANG_ID", "false").lower() == "true"
    ASR_DEFAULT_LANG: str = os.getenv("ASR_DEFAULT_LANG", "zh")  # zh or en
    
    # WebSocket配置
    WS_MAX_CONNECTIONS: int = 100
    WS_TIMEOUT: int = 300
    
    # 音频配置
    AUDIO_CHUNK_SIZE: int = 3200  # 200ms @ 16kHz（FunASR最佳帧长，减少碎片化识别）
    AUDIO_NOISE_DECAY: float = 0.997  # 噪声水平衰减系数（稳定噪声估计，避免过于灵敏）
    
    # VAD 端点检测配置（三段式）- 优化为准确性和速度平衡
    VAD_PRE_SPEECH_PADDING: float = 0.2  # 前置缓冲 200ms（保留更多上下文，提高准确度）
    VAD_END_SILENCE: float = 1.0  # 尾静音 900ms（平衡速度和完整度，减少延迟）
    VAD_MAX_SEGMENT: float = 8.0  # 最大段长 8s（更快切分，减少延迟和内存占用）
    
    # 流式识别配置
    PARTIAL_INTERVAL: float = 0.3  # 部分结果产出间隔 300ms（更快的反馈，提升用户体验）
    
    # WebSocket 背压配置
    WS_AUDIO_QUEUE_MAX_SIZE: int = 24  # 队列上限（约 2.4s 音频，配合chunk=3200使用）
    WS_AUDIO_QUEUE_DROP_OLDEST: bool = True  # 队列满时丢弃最旧
    
    # PostgreSQL配置
    PG_HOST: str = os.getenv("PG_HOST", "localhost")
    PG_PORT: int = int(os.getenv("PG_PORT", "5432"))
    PG_DB: str = os.getenv("PG_DB", "interview")
    PG_USER: str = os.getenv("PG_USER", "postgres")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD", "0923")
    PG_VECTOR_DIM: int = 1536  # 向量维度（保留用于数据库表结构兼容性）
    PG_ENABLED: bool = os.getenv("PG_ENABLED", "true").lower() == "true"  # PostgreSQL是否启用（用于CV、对话记录、岗位信息等存储）
    
    # 内存历史配置
    MEMORY_HISTORY_MAX_SIZE: int = int(os.getenv("MEMORY_HISTORY_MAX_SIZE", "1000"))  # 内存历史最大条数
    
    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "json"  # json or text
    
    # Pydantic V2 配置
    model_config = ConfigDict(
        env_file=str(ENV_FILE_PATH),  # 使用绝对路径，确保能找到.env文件
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


# 全局配置实例
settings = Settings()

