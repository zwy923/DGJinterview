"""
LLM API（流式）- 使用 OpenAI SDK（性能优化版）
"""
import asyncio
from enum import Enum
from typing import AsyncIterator, Optional, Dict, Any
from collections import defaultdict
from openai import OpenAI, AsyncOpenAI
import httpx
from config import settings
from logs import setup_logger, log_metric

logger = setup_logger(__name__)


class ErrorType(Enum):
    """错误类型枚举"""
    STREAM_UNSUPPORTED = "stream_unsupported"
    TEMP_UNSUPPORTED = "temp_unsupported"
    MAX_TOKENS_UNSUPPORTED = "max_tokens_unsupported"
    LENGTH_LIMIT = "length_limit"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class LLMAPI:
    """LLM API客户端（支持流式）- 使用 OpenAI SDK（性能优化版）"""
    
    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        
        # 预编译请求参数模板（优化④）
        model_lower = self.model.lower()
        self._use_max_completion_tokens = (
            "claude" in model_lower or 
            "anthropic" in self.base_url.lower() or
            "gpt-5" in model_lower or 
            "gpt-4o" in model_lower
        )
        self._use_default_temp = (
            "gpt-5" in model_lower or 
            "gpt-4o" in model_lower or 
            "gpt-4o-mini" in model_lower
        )
        
        # 动态 token 限制自适应（优化⑥）
        self.token_usage_avg = defaultdict(lambda: 1500)
        
        # 异步限流（优化⑤）
        self._max_concurrent = 10
        # Semaphore 和 Lock 也需要在事件循环中创建，所以延迟初始化
        self._semaphore = None
        self._http_client_lock = None
        
        # 初始化 OpenAI 客户端（优化⑤：连接复用）
        # 注意：httpx.AsyncClient 需要在事件循环中创建，所以延迟初始化
        self._http_client = None
        
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            # async_client 延迟初始化，在第一次使用时创建
            self.async_client = None
        else:
            self.client = None
            self.async_client = None
        
        # 仅在初始化时记录一次（优化⑦：减少日志）
        if logger.isEnabledFor(20):  # DEBUG level
            logger.debug(f"LLM API初始化: 模型={self.model}, Base URL={self.base_url}, "
                        f"use_max_completion_tokens={self._use_max_completion_tokens}, "
                        f"use_default_temp={self._use_default_temp}")
    
    def _classify_error(self, error: Exception) -> ErrorType:
        """错误分类函数（优化②）"""
        error_msg = str(error).lower()
        
        if "stream" in error_msg and ("unsupported" in error_msg or "verified" in error_msg or 
                                      "organization" in error_msg or "unsupported_value" in error_msg):
            return ErrorType.STREAM_UNSUPPORTED
        
        if "temperature" in error_msg and ("only the default" in error_msg or 
                                           "unsupported value" in error_msg):
            return ErrorType.TEMP_UNSUPPORTED
        
        if ("max_tokens" in error_msg or "max_completion_tokens" in error_msg) and \
           ("unsupported" in error_msg or "not supported" in error_msg):
            return ErrorType.MAX_TOKENS_UNSUPPORTED
        
        if "length" in error_msg or "finish_reason" in error_msg:
            return ErrorType.LENGTH_LIMIT
        
        if "connection" in error_msg or "timeout" in error_msg or "network" in error_msg:
            return ErrorType.NETWORK_ERROR
        
        return ErrorType.UNKNOWN
    
    def _build_request_params(self, messages: list, stream: bool, 
                             temperature: Optional[float] = None,
                             max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """构建请求参数（使用预编译模板，优化④）"""
        token_limit = max_tokens or self.max_tokens
        
        # 使用预编译的模板，直接拷贝并修改
        params = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        
        # 根据预编译的模板设置参数
        if self._use_max_completion_tokens:
            params["max_completion_tokens"] = token_limit
        else:
            params["max_tokens"] = token_limit
        
        if not self._use_default_temp:
            params["temperature"] = temperature or self.temperature
        
        return params
    
    def _adjust_token_limit(self, current_limit: int, error_type: ErrorType, 
                           reasoning_tokens: int = 0) -> int:
        """动态调整 token 限制（优化⑥）"""
        if error_type == ErrorType.LENGTH_LIMIT:
            if reasoning_tokens > 0:
                # 推理模型需要更多token
                new_limit = max(current_limit * 3, 2000)
            else:
                new_limit = min(current_limit * 2, 2000)
            
            if current_limit >= 1000:
                new_limit = 4000
            
            return new_limit
        
        # 使用滑动平均预测（优化⑥）
        avg_usage = self.token_usage_avg[self.model]
        if avg_usage > current_limit * 0.8:
            return int(avg_usage * 1.5)
        
        return current_limit
    
    def _update_token_usage(self, usage: Dict[str, Any]):
        """更新 token 使用滑动平均（优化⑥）"""
        if not usage:
            return
        
        completion_tokens = usage.get("completion_tokens", 0)
        if completion_tokens > 0:
            old_avg = self.token_usage_avg[self.model]
            # 指数移动平均：0.8 * old + 0.2 * new
            self.token_usage_avg[self.model] = 0.8 * old_avg + 0.2 * completion_tokens
    
    async def _stream_chat_producer_consumer(
        self, 
        messages: list, 
        request_params: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """生产者-消费者模型流式响应（优化①）"""
        queue = asyncio.Queue(maxsize=50)  # 限制队列大小避免内存溢出
        
        async def producer():
            """生产者：从 SDK 获取 chunk 并放入队列"""
            try:
                stream_obj = await self.async_client.chat.completions.create(**request_params)
                async for chunk in stream_obj:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            await queue.put({
                                "content": delta.content,
                                "done": False
                            })
                await queue.put({"done": True})
            except Exception as e:
                await queue.put({"error": str(e), "done": True})
        
        # 启动生产者任务
        producer_task = asyncio.create_task(producer())
        
        # 消费者：从队列取出并 yield
        try:
            while True:
                item = await queue.get()
                if item.get("done"):
                    if "error" in item:
                        raise Exception(item["error"])
                    yield item
                    break
                yield item
        finally:
            # 确保生产者任务完成
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except asyncio.CancelledError:
                    pass
    
    async def _ensure_async_client(self):
        """确保 async_client 已初始化（延迟初始化）"""
        # 延迟初始化 Semaphore 和 Lock（需要在事件循环中创建）
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        if self._http_client_lock is None:
            self._http_client_lock = asyncio.Lock()
        
        if self.async_client is None and self.api_key:
            async with self._http_client_lock:
                # 双重检查，避免重复创建
                if self.async_client is None:
                    # 创建共享的 httpx.AsyncClient 用于连接池（优化⑤：连接复用）
                    # httpx 支持连接池和并发控制
                    limits = httpx.Limits(max_keepalive_connections=100, max_connections=100)
                    timeout = httpx.Timeout(60.0, connect=10.0)
                    self._http_client = httpx.AsyncClient(
                        limits=limits,
                        timeout=timeout,
                        http2=False  # HTTP/2需要h2包，暂时禁用。如需启用，请安装: pip install httpx[http2]
                    )
                    
                    self.async_client = AsyncOpenAI(
                        api_key=self.api_key,
                        base_url=self.base_url,
                        http_client=self._http_client,
                        timeout=30.0,
                        max_retries=0  # 我们自己处理重试
                    )
    
    async def chat(
        self,
        messages: list,
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        调用LLM API（使用 OpenAI SDK，性能优化版）
        
        Args:
            messages: 消息列表
            stream: 是否流式返回
            temperature: 温度参数
            max_tokens: 最大token数
        
        Yields:
            LLM响应块
        """
        # 确保 async_client 已初始化
        await self._ensure_async_client()
        
        if not self.api_key or not self.async_client:
            if logger.isEnabledFor(30):  # WARNING level
                logger.warning("LLM API密钥未配置，返回模拟响应")
            yield {"content": "LLM API未配置", "done": True}
            return
        
        # 异步限流（优化⑤）
        async with self._semaphore:
            # 使用统一的重试逻辑（优化②）
            async for chunk in self._chat_with_retry(messages, stream, temperature, max_tokens):
                yield chunk
    
    async def _chat_with_retry(
        self,
        messages: list,
        stream: bool,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """统一的重试逻辑（优化②）"""
        request_params = self._build_request_params(messages, stream, temperature, max_tokens)
        original_stream = stream
        retry_count = 0
        max_retries = 3
        
        while retry_count <= max_retries:
            try:
                if stream:
                    # 流式响应：使用生产者-消费者模型（优化①）
                    async for chunk in self._stream_chat_producer_consumer(messages, request_params):
                        yield chunk
                    return
                else:
                    # 非流式响应：直接 await
                    response = await self.async_client.chat.completions.create(**request_params)
                    
                    if response.choices and len(response.choices) > 0:
                        message = response.choices[0].message
                        content = message.content if message else None
                        finish_reason = response.choices[0].finish_reason if hasattr(response.choices[0], 'finish_reason') else None
                        usage = response.usage.model_dump() if response.usage else {}
                        
                        # 更新 token 使用统计（优化⑥）
                        self._update_token_usage(usage)
                        
                        if content:
                            yield {
                                "content": content,
                                "done": True,
                                "usage": usage
                            }
                            return
                        elif finish_reason == 'length' or (not content and finish_reason):
                            # 长度限制，需要增加 token
                            error_type = ErrorType.LENGTH_LIMIT
                            reasoning_tokens = usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0) \
                                if isinstance(usage.get('completion_tokens_details'), dict) else 0
                            
                            current_limit = request_params.get("max_completion_tokens") or \
                                request_params.get("max_tokens") or self.max_tokens
                            new_limit = self._adjust_token_limit(current_limit, error_type, reasoning_tokens)
                            
                            if self._use_max_completion_tokens:
                                request_params["max_completion_tokens"] = new_limit
                            else:
                                request_params["max_tokens"] = new_limit
                            
                            retry_count += 1
                            if logger.isEnabledFor(20):  # DEBUG
                                logger.debug(f"因长度限制增加token到 {new_limit}，重试 {retry_count}/{max_retries}")
                            continue
                    
                    # 没有内容，返回错误
                    yield {"content": "未获取到响应内容", "done": True, "error": True}
                    return
                    
            except Exception as e:
                error_type = self._classify_error(e)
                
                # 根据错误类型调整参数
                if error_type == ErrorType.STREAM_UNSUPPORTED and original_stream:
                    # 流式不支持，降级为非流式
                    stream = False
                    request_params["stream"] = False
                    if logger.isEnabledFor(30):  # WARNING
                        logger.warning("流式响应不支持，降级为非流式响应")
                    retry_count += 1
                    continue
                
                elif error_type == ErrorType.TEMP_UNSUPPORTED:
                    # Temperature 不支持，移除参数
                    if "temperature" in request_params:
                        del request_params["temperature"]
                    if logger.isEnabledFor(20):  # DEBUG
                        logger.debug("移除 temperature 参数，使用默认值")
                    retry_count += 1
                    continue
                
                elif error_type == ErrorType.MAX_TOKENS_UNSUPPORTED:
                    # max_tokens 不支持，切换到 max_completion_tokens
                    if "max_tokens" in request_params:
                        token_limit = request_params.pop("max_tokens")
                        request_params["max_completion_tokens"] = token_limit
                    if logger.isEnabledFor(20):  # DEBUG
                        logger.debug("切换到 max_completion_tokens")
                    retry_count += 1
                    continue
                
                elif error_type == ErrorType.NETWORK_ERROR and retry_count < max_retries:
                    # 网络错误，重试
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)  # 指数退避
                    if logger.isEnabledFor(30):  # WARNING
                        logger.warning(f"网络错误，重试 {retry_count}/{max_retries}: {e}")
                    continue
                
                else:
                    # 其他错误或达到最大重试次数
                    if logger.isEnabledFor(40):  # ERROR
                        logger.error(f"LLM API调用失败: {e}")
                    yield {"content": f"API错误: {str(e)}", "done": True, "error": True}
                    return
        
        # 达到最大重试次数
        if logger.isEnabledFor(40):  # ERROR
            logger.error("达到最大重试次数，放弃请求")
        yield {"content": "API调用失败：达到最大重试次数", "done": True, "error": True}
    
    @log_metric("llm_requests")
    async def generate(
        self,
        prompt: str,
        stream: bool = False,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        生成文本（非流式，返回完整结果）- 轻量封装（优化⑧）
        
        Args:
            prompt: 提示词
            stream: 忽略此参数（此方法始终返回完整结果）
            max_tokens: 最大token数
        
        Returns:
            生成的文本
        """
        # 确保 async_client 已初始化
        await self._ensure_async_client()
        
        if not self.api_key or not self.async_client:
            return "LLM API未配置"
        
        messages = [{"role": "user", "content": prompt}]
        request_params = self._build_request_params(messages, stream=False, max_tokens=max_tokens)
        
        # 直接 await 一次完成，不使用 iterator（优化⑧）
        try:
            response = await self.async_client.chat.completions.create(**request_params)
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if content:
                    # 更新 token 使用统计
                    usage = response.usage.model_dump() if response.usage else {}
                    self._update_token_usage(usage)
                    return content
            return ""
        except Exception as e:
            if logger.isEnabledFor(40):  # ERROR
                logger.error(f"generate() 失败: {e}")
            return f"生成失败: {str(e)}"
    
    async def close(self):
        """关闭 HTTP 客户端连接"""
        if self._http_client:
            await self._http_client.aclose()


# 全局LLM API实例
llm_api = LLMAPI()
