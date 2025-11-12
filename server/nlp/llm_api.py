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
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"LLM API错误: {response.status} - {error_text}")
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

