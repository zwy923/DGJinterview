"""
LLM API（流式）
"""
import aiohttp
import json
from typing import AsyncIterator, Optional, Dict, Any
from config import settings
from logs import setup_logger, log_metric

logger = setup_logger(__name__)


class LLMAPI:
    """LLM API客户端（支持流式）"""
    
    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        logger.info(f"LLM API初始化: 模型={self.model}, Base URL={self.base_url}")
    
    async def chat(
        self,
        messages: list,
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        调用LLM API
        
        Args:
            messages: 消息列表
            stream: 是否流式返回
            temperature: 温度参数
            max_tokens: 最大token数
        
        Yields:
            LLM响应块
        """
        if not self.api_key:
            logger.warning("LLM API密钥未配置，返回模拟响应")
            yield {"content": "LLM API未配置", "done": True}
            return
        
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 根据模型类型选择正确的参数名
        # 某些新模型（如Claude、gpt-5-mini）使用 max_completion_tokens，而OpenAI使用 max_tokens
        token_limit = max_tokens or self.max_tokens
        model_lower = self.model.lower()
        
        # 记录模型名称用于调试
        logger.debug(f"使用模型: {self.model} (小写: {model_lower})")
        
        # 检查模型名称，决定使用哪个参数
        use_max_completion_tokens = False
        use_default_temperature = False
        
        # 检测需要特殊处理的模型
        if "claude" in model_lower or "anthropic" in self.base_url.lower():
            use_max_completion_tokens = True
            logger.debug("检测到Claude模型，使用 max_completion_tokens")
        elif "gpt-5" in model_lower or "gpt-4o" in model_lower or "gpt-4o-mini" in model_lower:
            # gpt-5系列和gpt-4o系列使用 max_completion_tokens，且temperature只支持默认值
            use_max_completion_tokens = True
            use_default_temperature = True
            logger.info(f"检测到 {self.model} 模型，使用 max_completion_tokens 且不设置 temperature（使用默认值）")
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        
        # 设置token限制参数
        if use_max_completion_tokens:
            payload["max_completion_tokens"] = token_limit
            logger.debug(f"使用 max_completion_tokens={token_limit}")
        else:
            payload["max_tokens"] = token_limit
            logger.debug(f"使用 max_tokens={token_limit}")
        
        # 设置temperature参数（某些模型不支持自定义temperature）
        if not use_default_temperature:
            payload["temperature"] = temperature or self.temperature
            logger.debug(f"使用 temperature={payload['temperature']}")
        else:
            logger.debug("不设置 temperature 参数，使用模型默认值")
        
        logger.debug(f"请求payload: {json.dumps({k: v for k, v in payload.items() if k != 'messages'}, indent=2)}")
        
        try:
            async with aiohttp.ClientSession() as session:
                # 第一次尝试
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"LLM API错误: {response.status} - {error_text}")
                        
                        # 如果错误是因为 max_tokens 参数，尝试使用 max_completion_tokens
                        if not use_max_completion_tokens and "max_tokens" in error_text.lower() and "max_completion_tokens" in error_text.lower():
                            logger.info("检测到 max_tokens 参数错误，尝试使用 max_completion_tokens")
                            # 修改payload并重试
                            if "max_tokens" in payload:
                                del payload["max_tokens"]
                            payload["max_completion_tokens"] = token_limit
                            
                            # 检查是否也有temperature错误
                            if "temperature" in error_text.lower() and ("only the default" in error_text.lower() or "unsupported value" in error_text.lower()):
                                logger.info("检测到 temperature 参数错误，移除 temperature 参数使用默认值")
                                if "temperature" in payload:
                                    del payload["temperature"]
                            
                            # 重新创建session进行重试
                            async with aiohttp.ClientSession() as retry_session:
                                async with retry_session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as retry_response:
                                    if retry_response.status != 200:
                                        retry_error_text = await retry_response.text()
                                        logger.error(f"LLM API重试后仍然错误: {retry_response.status} - {retry_error_text}")
                                        
                                        # 如果还有temperature错误，再次重试
                                        if "temperature" in retry_error_text.lower() and ("only the default" in retry_error_text.lower() or "unsupported value" in retry_error_text.lower()):
                                            logger.info("重试时检测到 temperature 参数错误，移除 temperature 参数")
                                            if "temperature" in payload:
                                                del payload["temperature"]
                                            async with aiohttp.ClientSession() as retry_session2:
                                                async with retry_session2.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as retry_response2:
                                                    if retry_response2.status != 200:
                                                        retry_error_text2 = await retry_response2.text()
                                                        logger.error(f"LLM API第二次重试后仍然错误: {retry_response2.status} - {retry_error_text2}")
                                                        yield {"content": f"API错误: {retry_error_text2}", "done": True, "error": True}
                                                        return
                                                    # 使用retry_response2继续处理
                                                    async for chunk in self._process_response(retry_response2, stream):
                                                        yield chunk
                                                    return
                                        else:
                                            yield {"content": f"API错误: {retry_error_text}", "done": True, "error": True}
                                            return
                                    else:
                                        # 重试成功，处理响应
                                        async for chunk in self._process_response(retry_response, stream):
                                            yield chunk
                                        return
                        # 如果只是temperature错误
                        elif "temperature" in error_text.lower() and ("only the default" in error_text.lower() or "unsupported value" in error_text.lower()):
                            logger.info("检测到 temperature 参数错误，移除 temperature 参数使用默认值")
                            if "temperature" in payload:
                                del payload["temperature"]
                            async with aiohttp.ClientSession() as retry_session:
                                async with retry_session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as retry_response:
                                    if retry_response.status != 200:
                                        retry_error_text = await retry_response.text()
                                        logger.error(f"LLM API重试后仍然错误: {retry_response.status} - {retry_error_text}")
                                        yield {"content": f"API错误: {retry_error_text}", "done": True, "error": True}
                                        return
                                    # 处理响应
                                    async for chunk in self._process_response(retry_response, stream):
                                        yield chunk
                                    return
                        else:
                            yield {"content": f"API错误: {error_text}", "done": True, "error": True}
                            return
                    
                    # 第一次请求成功，处理响应
                    async for chunk in self._process_response(response, stream):
                        yield chunk
        except Exception as e:
            logger.error(f"LLM API调用失败: {e}")
            yield {"content": f"API调用失败: {str(e)}", "done": True, "error": True}
    
    async def _process_response(self, response: aiohttp.ClientResponse, stream: bool) -> AsyncIterator[Dict[str, Any]]:
        """处理API响应（流式或非流式）"""
        try:
            if stream:
                async for line in response.content:
                    if line:
                        line_str = line.decode('utf-8').strip()
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            if data_str == '[DONE]':
                                yield {"done": True}
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data.get('choices', [{}])[0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    yield {
                                        "content": content,
                                        "done": False
                                    }
                            except json.JSONDecodeError:
                                continue
            else:
                data = await response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                usage = data.get('usage', {})
                yield {
                    "content": content,
                    "done": True,
                    "usage": usage
                }
        except Exception as e:
            logger.error(f"处理响应时出错: {e}")
            yield {"content": f"处理响应失败: {str(e)}", "done": True, "error": True}
    
    @log_metric("llm_requests")
    async def generate(
        self,
        prompt: str,
        stream: bool = False,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        生成文本（非流式，返回完整结果）
        
        Args:
            prompt: 提示词
            stream: 是否流式返回（此方法始终返回完整结果）
            max_tokens: 最大token数（可选，用于限制回答长度）
        
        Returns:
            生成的文本
        """
        messages = [{"role": "user", "content": prompt}]
        content_parts = []
        
        async for chunk in self.chat(messages, stream=False, max_tokens=max_tokens):
            if chunk.get("content"):
                content_parts.append(chunk["content"])
            if chunk.get("done"):
                break
        
        return "".join(content_parts)


# 全局LLM API实例
llm_api = LLMAPI()

