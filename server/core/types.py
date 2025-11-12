"""
核心类型定义
"""
from typing import List, Dict, Literal, Optional, Any
from pydantic import BaseModel


class Message(BaseModel):
    """消息模型"""
    role: Literal["interviewer", "user", "assistant"]
    text: str
    ts: float  # 时间戳（Unix时间戳）


class DocChunk(BaseModel):
    """文档片段"""
    content: str
    source: str  # 来源（如"knowledge_base"）
    metadata: Optional[Dict[str, Any]] = None
    score: Optional[float] = None  # 相似度分数


class RagBundle(BaseModel):
    """RAG检索结果包"""
    cv_chunks: List[str] = []  # CV相关片段
    jd_chunks: List[str] = []  # JD相关片段
    ext_chunks: List[DocChunk] = []  # 外部知识库片段

