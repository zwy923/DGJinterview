"""
LLM流式生成服务
"""
from typing import AsyncGenerator, Literal
import aiohttp
import json

from core.config import agent_settings
from logs import setup_logger

logger = setup_logger(__name__)


class LLMService:
    """LLM流式生成服务"""
    
    def __init__(self):
        self.api_key = agent_settings.LLM_API_KEY
        self.base_url = agent_settings.LLM_BASE_URL
        self.temperature = agent_settings.LLM_TEMPERATURE
        self.max_tokens = agent_settings.LLM_MAX_TOKENS
        
        # 根据模式选择模型
        self.model_brief = agent_settings.MODEL_NAME_BRIEF
        self.model_full = agent_settings.MODEL_NAME_FULL
        
        if not self.api_key:
            logger.warning("LLM_API_KEY未设置，LLM功能将不可用")
    
    async def stream_generate(
        self,
        prompt: str,
        mode: Literal["brief", "full"] = "full"
    ) -> AsyncGenerator[str, None]:
        """
        流式生成回答
        
        Args:
            prompt: 完整prompt
            mode: 模式（brief或full）
        
        Yields:
            增量文本内容
        """
        if not self.api_key:
            logger.error("LLM_API_KEY未设置，无法生成回答")
            return
        
        model = self.model_brief if mode == "brief" else self.model_full
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url.rstrip('/')}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "stream": True
                }
                
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"LLM API错误: {resp.status} - {error_text}")
                        return
                    
                    async for line in resp.content:
                        if not line:
                            continue
                        
                        # 处理SSE格式
                        line_str = line.decode('utf-8').strip()
                        if not line_str or line_str == "data: [DONE]":
                            continue
                        
                        if line_str.startswith("data: "):
                            line_str = line_str[6:]  # 移除"data: "前缀
                        
                        try:
                            data = json.loads(line_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.warning(f"解析流式响应失败: {e}")
                            continue
        
        except Exception as e:
            logger.error(f"流式生成失败: {e}")
            return


# 全局实例
llm_service = LLMService()

