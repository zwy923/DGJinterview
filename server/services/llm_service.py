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
        
        # 模型参数兼容性：某些新模型使用 max_completion_tokens 而不是 max_tokens
        # 检测模型名称，判断应该使用哪个参数
        self._use_max_completion_tokens = self._should_use_max_completion_tokens()
        
        if not self.api_key:
            logger.warning("LLM_API_KEY未设置，LLM功能将不可用")
    
    def _should_use_max_completion_tokens(self) -> bool:
        """
        判断是否应该使用 max_completion_tokens 而不是 max_tokens
        
        某些新模型（如 gpt-4o-mini 的新版本）需要使用 max_completion_tokens
        """
        # 检查模型名称，如果包含特定标识，使用 max_completion_tokens
        models_using_completion_tokens = [
            "gpt-4o", "gpt-4o-mini", "o1", "o3"
        ]
        
        model_brief = self.model_brief.lower()
        model_full = self.model_full.lower()
        
        for model_pattern in models_using_completion_tokens:
            if model_pattern in model_brief or model_pattern in model_full:
                return True
        
        return False
    
    def _should_use_max_completion_tokens_for_model(self, model_name: str) -> bool:
        """
        针对特定模型判断是否应该使用 max_completion_tokens
        """
        model_lower = model_name.lower()
        models_using_completion_tokens = [
            "gpt-4o", "gpt-4o-mini", "o1", "o3", "gpt5"
        ]
        
        for model_pattern in models_using_completion_tokens:
            if model_pattern in model_lower:
                return True
        
        return False
    
    def _should_skip_temperature_for_model(self, model_name: str) -> bool:
        """
        判断模型是否不支持自定义 temperature（只支持默认值）
        某些新模型（如 gpt-5-mini）只支持默认 temperature=1
        """
        model_lower = model_name.lower()
        models_without_temperature = [
            "gpt-5", "o1", "o3"
        ]
        
        for model_pattern in models_without_temperature:
            if model_pattern in model_lower:
                return True
        
        return False
    
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
        
        # 根据模型类型选择正确的参数
        use_completion_tokens = self._should_use_max_completion_tokens_for_model(model)
        skip_temperature = self._should_skip_temperature_for_model(model)
        
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
                    "stream": True
                }
                
                # 根据模型类型添加参数
                if not skip_temperature:
                    payload["temperature"] = self.temperature
                
                if use_completion_tokens:
                    payload["max_completion_tokens"] = self.max_tokens
                else:
                    payload["max_tokens"] = self.max_tokens
                
                async with session.post(url, headers=headers, json=payload) as resp:
                    # 处理400错误，可能是参数不兼容
                    if resp.status == 400:
                        error_text = await resp.text()
                        try:
                            error_data = json.loads(error_text)
                            error_msg = error_data.get("error", {}).get("message", "")
                            error_code = error_data.get("error", {}).get("code", "")
                            
                            # 检查是否需要切换参数
                            needs_retry = False
                            
                            # 情况1: max_tokens 需要改为 max_completion_tokens
                            if "max_tokens" in error_msg and "max_completion_tokens" in error_msg:
                                logger.info(f"模型 {model} 需要使用 max_completion_tokens，正在重试...")
                                payload.pop("max_tokens", None)
                                payload["max_completion_tokens"] = self.max_tokens
                                needs_retry = True
                            
                            # 情况2: temperature 不支持自定义值
                            elif "temperature" in error_msg.lower() and ("unsupported" in error_msg.lower() or "only the default" in error_msg.lower()):
                                logger.info(f"模型 {model} 不支持自定义 temperature，移除该参数后重试...")
                                payload.pop("temperature", None)
                                needs_retry = True
                            
                            # 情况3: stream 不支持（需要组织验证或模型不支持流式）
                            elif "stream" in error_msg.lower() and ("verified" in error_msg.lower() or "organization" in error_msg.lower() or "unsupported" in error_msg.lower()):
                                logger.warning(f"模型 {model} 不支持流式输出，降级为非流式请求...")
                                # 降级为非流式请求
                                payload["stream"] = False
                                needs_retry = True
                            
                            # 情况4: 同时需要修复多个参数
                            elif ("max_tokens" in error_msg or "temperature" in error_msg.lower()):
                                # 尝试修复所有可能的参数问题
                                logger.info(f"模型 {model} 需要调整参数，正在重试...")
                                if "max_tokens" in error_msg and "max_completion_tokens" in error_msg:
                                    payload.pop("max_tokens", None)
                                    payload["max_completion_tokens"] = self.max_tokens
                                if "temperature" in error_msg.lower():
                                    payload.pop("temperature", None)
                                needs_retry = True
                            
                            if needs_retry:
                                # 重新发送请求
                                async with session.post(url, headers=headers, json=payload) as retry_resp:
                                    if retry_resp.status != 200:
                                        error_text = await retry_resp.text()
                                        logger.error(f"LLM API错误（重试后）: {retry_resp.status} - {error_text}")
                                        return
                                    
                                    # 如果降级为非流式，需要特殊处理
                                    if not payload.get("stream", True):
                                        # 非流式响应：一次性获取完整内容，然后模拟流式输出
                                        response_data = await retry_resp.json()
                                        choices = response_data.get("choices", [])
                                        if choices:
                                            full_content = choices[0].get("message", {}).get("content", "")
                                            if full_content:
                                                # 模拟流式输出：按词输出（更自然的流式体验）
                                                import asyncio
                                                words = full_content.split()
                                                for i, word in enumerate(words):
                                                    # 第一个词直接输出，后续词前加空格
                                                    if i == 0:
                                                        yield word
                                                    else:
                                                        yield " " + word
                                                    # 添加小延迟，模拟真实流式输出
                                                    await asyncio.sleep(0.02)  # 20ms延迟
                                                return
                                        else:
                                            logger.error(f"非流式响应中未找到内容: {response_data}")
                                            return
                                    
                                    # 继续处理成功的流式响应
                                    resp = retry_resp
                            else:
                                logger.error(f"LLM API错误: {resp.status} - {error_text}")
                                return
                        except (json.JSONDecodeError, KeyError):
                            logger.error(f"LLM API错误: {resp.status} - {error_text}")
                            return
                    elif resp.status != 200:
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

