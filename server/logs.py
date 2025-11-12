"""
结构化日志与指标模块
"""
import json
import logging
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional
from functools import wraps

from config import settings


class StructuredFormatter(logging.Formatter):
    """结构化JSON日志格式化器"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # 添加额外字段
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        return json.dumps(log_data, ensure_ascii=False)


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self.metrics: Dict[str, Any] = {
            "asr_requests": 0,
            "asr_errors": 0,
            "llm_requests": 0,
            "llm_errors": 0,
            "ws_connections": 0,
            "ws_disconnections": 0,
            "audio_chunks_processed": 0,
            "transcripts_saved": 0,
        }
    
    def increment(self, metric: str, value: int = 1):
        """增加指标值"""
        if metric in self.metrics:
            self.metrics[metric] += value
    
    def set(self, metric: str, value: Any):
        """设置指标值"""
        self.metrics[metric] = value
    
    def get(self, metric: str) -> Any:
        """获取指标值"""
        return self.metrics.get(metric, 0)
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有指标"""
        return self.metrics.copy()


# 全局指标收集器
metrics = MetricsCollector()


def setup_logger(
    name: str = "interview_backend",
    level: Optional[str] = None
) -> logging.Logger:
    """
    设置并返回日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别（默认从配置读取）
    
    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    
    if level is None:
        level = settings.LOG_LEVEL
    
    logger.setLevel(getattr(logging, level.upper()))
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logger.level)
    
    # 根据配置选择格式化器
    if settings.LOG_FORMAT == "json":
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


def log_metric(metric: str, value: int = 1):
    """装饰器：记录指标"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                metrics.increment(metric)
                return result
            except Exception as e:
                metrics.increment(f"{metric}_errors")
                raise
            finally:
                duration = time.time() - start_time
                logger = logging.getLogger(func.__module__)
                logger.debug(f"{func.__name__} took {duration:.3f}s")
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                metrics.increment(metric)
                return result
            except Exception as e:
                metrics.increment(f"{metric}_errors")
                raise
            finally:
                duration = time.time() - start_time
                logger = logging.getLogger(func.__module__)
                logger.debug(f"{func.__name__} took {duration:.3f}s")
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# 默认日志记录器
default_logger = setup_logger()

