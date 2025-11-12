"""
NLP模块统一异常体系
"""
from typing import Optional


class AgentError(Exception):
    """Agent相关异常的基类"""
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.cause = cause


class LLMError(AgentError):
    """LLM调用失败异常"""
    pass


class RetrievalError(AgentError):
    """检索失败异常"""
    pass


class TimeoutError(AgentError):
    """超时异常"""
    pass


class PromptError(AgentError):
    """Prompt模板错误异常"""
    pass

