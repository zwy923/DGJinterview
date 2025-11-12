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


