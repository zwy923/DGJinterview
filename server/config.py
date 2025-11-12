"""
统一配置模块
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


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
    ASR_DEVICE: str = os.getenv("ASR_DEVICE", "cpu")  # cpu or cuda
    ASR_SAMPLE_RATE: int = 16000
    
    # ASR 后处理配置
    ASR_ENABLE_ORAL_CLEANING: bool = os.getenv("ASR_ENABLE_ORAL_CLEANING", "true").lower() == "false"
    ASR_ENABLE_NUMBER_NORMALIZATION: bool = os.getenv("ASR_ENABLE_NUMBER_NORMALIZATION", "true").lower() == "true"
    ASR_ENABLE_REPEAT_REMOVAL: bool = os.getenv("ASR_ENABLE_REPEAT_REMOVAL", "true").lower() == "true"
    ASR_ENABLE_PUNCTUATION_CORRECTION: bool = os.getenv("ASR_ENABLE_PUNCTUATION_CORRECTION", "true").lower() == "true"
    ASR_MIN_SENTENCE_LENGTH: int = int(os.getenv("ASR_MIN_SENTENCE_LENGTH", "3"))  # 最小句子长度（字符数）
    
    # 语言路由配置（预留）
    ASR_ENABLE_LANG_ID: bool = os.getenv("ASR_ENABLE_LANG_ID", "false").lower() == "true"
    ASR_DEFAULT_LANG: str = os.getenv("ASR_DEFAULT_LANG", "zh")  # zh or en
    
    # WebSocket配置
    WS_MAX_CONNECTIONS: int = 100
    WS_TIMEOUT: int = 300
    
    # 音频配置
    AUDIO_CHUNK_SIZE: int = 1600  # 100ms @ 16kHz（降低延迟）
    AUDIO_NOISE_DECAY: float = 0.995  # 噪声水平衰减系数
    
    # VAD 端点检测配置（三段式）
    VAD_PRE_SPEECH_PADDING: float = 0.2  # 前置缓冲 200ms
    VAD_END_SILENCE: float = 0.4  # 尾静音 400ms（交互场景）
    VAD_MAX_SEGMENT: float = 8.0  # 最大段长 8s（防止长段堆积）
    
    # 流式识别配置
    PARTIAL_INTERVAL: float = 0.2  # 部分结果产出间隔（秒）
    
    # WebSocket 背压配置
    WS_AUDIO_QUEUE_MAX_SIZE: int = 128  # 队列上限（约 2-3s 音频）
    WS_AUDIO_QUEUE_DROP_OLDEST: bool = True  # 队列满时丢弃最旧
    
    # LLM配置
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")
    LLM_BASE_URL: Optional[str] = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2000
    
    # PostgreSQL配置
    PG_HOST: str = os.getenv("PG_HOST", "localhost")
    PG_PORT: int = int(os.getenv("PG_PORT", "5432"))
    PG_DB: str = os.getenv("PG_DB", "interview")
    PG_USER: str = os.getenv("PG_USER", "postgres")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD", "")
    PG_VECTOR_DIM: int = 1536  # OpenAI embedding维度
    
    # RAG配置
    RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "false").lower() == "true"
    RAG_TOP_K: int = 5
    RAG_RERANK_TOP_K: int = 3
    
    # Redis配置（可选）
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    
    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "json"  # json or text
    
    # Pydantic V2 配置
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True
    )


# 全局配置实例
settings = Settings()

