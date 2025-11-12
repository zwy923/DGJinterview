"""
Pydantic模型定义
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


# =====================================================
# 聊天消息模型
# =====================================================

class ChatMessage(BaseModel):
    """单条聊天消息（语音识别结果、GPT回复等）"""
    id: str = Field(..., description="唯一消息ID（通常为时间戳毫秒）")
    timestamp: str = Field(..., description="时间戳 ISO 格式")
    speaker: str = Field(..., description="说话者：'user' | 'interviewer' | 'system'")
    content: str = Field(..., description="消息文本内容")
    type: str = Field("text", description="类型：'text' | 'audio' | 'system'")
    confidence: Optional[float] = Field(None, description="识别置信度（0-1）")


class ChatHistoryRequest(BaseModel):
    """请求保存单条聊天记录"""
    session_id: str
    message: ChatMessage


class ChatHistoryResponse(BaseModel):
    """保存结果响应"""
    success: bool
    message: str


# =====================================================
# GPT / 分析模型
# =====================================================

class GPTRequest(BaseModel):
    """GPT 生成请求"""
    prompt: str
    stream: bool = Field(False, description="是否流式返回")
    temperature: Optional[float] = Field(None, description="温度参数")
    max_tokens: Optional[int] = Field(None, description="最大token数")
    session_id: Optional[str] = Field(None, description="会话ID（用于获取岗位信息、知识库、对话历史）")
    user_id: Optional[str] = Field(None, description="用户ID（用于获取CV）")
    use_rag: bool = Field(True, description="是否使用RAG检索增强上下文")


class GPTResponse(BaseModel):
    """GPT 回复"""
    reply: str
    usage: Optional[Dict[str, int]] = Field(None, description="Token使用情况")


class GPTStreamChunk(BaseModel):
    """GPT 流式响应块"""
    content: str
    done: bool = Field(False, description="是否完成")
    usage: Optional[Dict[str, int]] = Field(None, description="Token使用情况")


class InterviewAnalysisRequest(BaseModel):
    """面试分析请求"""
    type: str
    data: dict
    session_id: str = Field(..., description="会话ID")


class InterviewAnalysisResponse(BaseModel):
    """面试分析响应"""
    analysis: Dict[str, Any]
    summary: str
    recommendations: List[str]
    score: Optional[float] = Field(None, description="综合评分（0-100）")


# =====================================================
# WebSocket消息模型
# =====================================================

class WSStartMessage(BaseModel):
    """WebSocket启动消息"""
    type: str = "start"
    session_id: str
    sample_rate: int = 16000
    source: str = Field("mic", description="音频源：'mic' | 'sys'")


class WSStopMessage(BaseModel):
    """WebSocket停止消息"""
    type: str = "stop"


class WSInfoMessage(BaseModel):
    """WebSocket信息消息"""
    type: str = "info"
    seq: int
    text: str


class WSFinalMessage(BaseModel):
    """WebSocket最终识别结果"""
    type: str = "final"
    seq: int
    text: str
    confidence: Optional[float] = None


class WSPartialMessage(BaseModel):
    """WebSocket部分识别结果"""
    type: str = "partial"
    seq: int
    text: str


class WSErrorMessage(BaseModel):
    """WebSocket错误消息"""
    type: str = "error"
    seq: int
    text: str
    code: Optional[str] = None


# =====================================================
# RAG相关模型
# =====================================================

class RAGQuery(BaseModel):
    """RAG查询请求"""
    query: str
    top_k: int = Field(5, description="返回top-k结果")
    rerank: bool = Field(True, description="是否重排序")


class RAGResult(BaseModel):
    """RAG查询结果"""
    content: str
    score: float
    metadata: Optional[Dict[str, Any]] = None


class RAGResponse(BaseModel):
    """RAG响应"""
    results: List[RAGResult]
    query: str
    total: int


# =====================================================
# 会话统计模型
# =====================================================

class SessionStats(BaseModel):
    """会话统计信息"""
    session_id: str
    total_messages: int
    user_messages: int
    interviewer_messages: int
    system_messages: int
    last_activity: Optional[str] = None
    duration_seconds: Optional[float] = None
    total_words: Optional[int] = None


# =====================================================
# CV相关模型
# =====================================================

class CVRequest(BaseModel):
    """CV上传请求"""
    user_id: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class CVResponse(BaseModel):
    """CV响应"""
    id: int
    user_id: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# =====================================================
# 岗位信息相关模型
# =====================================================

class JobPositionRequest(BaseModel):
    """岗位信息请求"""
    session_id: str
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class JobPositionResponse(BaseModel):
    """岗位信息响应"""
    id: int
    session_id: str
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# =====================================================
# 知识库相关模型
# =====================================================

class KnowledgeBaseRequest(BaseModel):
    """知识库条目请求"""
    session_id: Optional[str] = None
    title: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeBaseResponse(BaseModel):
    """知识库条目响应"""
    id: int
    session_id: Optional[str] = None
    title: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


# =====================================================
# Agent相关模型
# =====================================================

class AgentSuggestRequest(BaseModel):
    """Agent建议请求"""
    session_id: str
    user_id: Optional[str] = None


class AgentSuggestResponse(BaseModel):
    """Agent建议响应"""
    suggestion: Optional[str] = None
    success: bool
    message: Optional[str] = None
