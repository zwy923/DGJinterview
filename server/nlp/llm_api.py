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
        # 某些新模型（如Claude）使用 max_completion_tokens，而OpenAI使用 max_tokens
        token_limit = max_tokens or self.max_tokens
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature or self.temperature,
        }
        
        # 检查模型名称，决定使用哪个参数
        use_max_completion_tokens = False
        if "claude" in self.model.lower() or "anthropic" in self.base_url.lower():
            payload["max_completion_tokens"] = token_limit
            use_max_completion_tokens = True
        else:
            payload["max_tokens"] = token_limit
        
        try:
            async with aiohttp.ClientSession() as session:
                # 第一次尝试
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"LLM API错误: {response.status} - {error_text}")
                        
                        # 如果错误是因为 max_tokens 参数，尝试使用 max_completion_tokens
                        if not use_max_completion_tokens and "max_tokens" in error_text.lower() and "max_completion_tokens" in error_text.lower():
                            logger.info("检测到 max_tokens 参数错误，尝试使用 max_completion_tokens")
                            # 修改payload并重试
                            del payload["max_tokens"]
                            payload["max_completion_tokens"] = token_limit
                            async with session.post(url, headers=headers, json=payload) as retry_response:
                                if retry_response.status != 200:
                                    retry_error_text = await retry_response.text()
                                    logger.error(f"LLM API重试后仍然错误: {retry_response.status} - {retry_error_text}")
                                    yield {"content": f"API错误: {retry_error_text}", "done": True, "error": True}
                                    return
                                # 重试成功，使用retry_response继续处理
                                response = retry_response
                        else:
                            yield {"content": f"API错误: {error_text}", "done": True, "error": True}
                            return
                    
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
            logger.error(f"LLM API调用失败: {e}")
            yield {"content": f"API调用失败: {str(e)}", "done": True, "error": True}
    
    @log_metric("llm_requests")
    async def generate(
        self,
        prompt: str,
        stream: bool = False
    ) -> str:
        """
        生成文本（非流式，返回完整结果）
        
        Args:
            prompt: 提示词
            stream: 是否流式返回（此方法始终返回完整结果）
        
        Returns:
            生成的文本
        """
        messages = [{"role": "user", "content": prompt}]
        content_parts = []
        
        async for chunk in self.chat(messages, stream=False):
            if chunk.get("content"):
                content_parts.append(chunk["content"])
            if chunk.get("done"):
                break
        
        return "".join(content_parts)


# 全局LLM API实例
llm_api = LLMAPI()

