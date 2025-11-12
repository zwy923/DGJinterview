"""
扩展配置模块（AI Agent相关）
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

# 获取server目录的绝对路径
SERVER_DIR = Path(__file__).parent.parent.resolve()
ENV_FILE_PATH = SERVER_DIR / ".env"


class AgentSettings(BaseSettings):
    """AI Agent配置"""
    
    # 自动回答配置
    AUTO_ANSWER_ENABLED: bool = os.getenv("AUTO_ANSWER_ENABLED", "false").lower() == "true"
    
    # 对话历史配置
    CHAT_HISTORY_MAX: int = int(os.getenv("CHAT_HISTORY_MAX", "50"))  # 最近N条消息
    
    # RAG配置
    RAG_TOPK: int = int(os.getenv("RAG_TOPK", "5"))  # 外部检索top_k
    RAG_TOKEN_BUDGET: int = int(os.getenv("RAG_TOKEN_BUDGET", "1200"))  # RAG token预算
    
    # LLM模型配置
    MODEL_NAME_BRIEF: str = os.getenv("MODEL_NAME_BRIEF", "gpt-4o-mini")  # 快答模型名
    MODEL_NAME_FULL: str = os.getenv("MODEL_NAME_FULL", "gpt-4o-mini")  # 正常模式模型名
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    
    # Embedding配置
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    
    # Pydantic V2 配置
    model_config = ConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


# 全局Agent配置实例
agent_settings = AgentSettings()

