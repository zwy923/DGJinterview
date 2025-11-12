"""
LLM API（流式）- 使用 OpenAI SDK
"""
import json
from typing import AsyncIterator, Optional, Dict, Any
from openai import OpenAI, AsyncOpenAI
from config import settings
from logs import setup_logger, log_metric

logger = setup_logger(__name__)


class LLMAPI:
    """LLM API客户端（支持流式）- 使用 OpenAI SDK"""
    
    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        
        # 初始化 OpenAI 客户端（同步和异步）
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            self.async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        else:
            self.client = None
            self.async_client = None
        
        logger.info(f"LLM API初始化: 模型={self.model}, Base URL={self.base_url}")
    
    async def chat(
        self,
        messages: list,
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        调用LLM API（使用 OpenAI SDK）
        
        Args:
            messages: 消息列表
            stream: 是否流式返回
            temperature: 温度参数
            max_tokens: 最大token数
        
        Yields:
            LLM响应块
        """
        if not self.api_key or not self.async_client:
            logger.warning("LLM API密钥未配置，返回模拟响应")
            yield {"content": "LLM API未配置", "done": True}
            return
        
        # 根据模型类型选择正确的参数名
        token_limit = max_tokens or self.max_tokens
        model_lower = self.model.lower()
        
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
        
        # 构建请求参数
        request_params = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        
        # 设置token限制参数
        if use_max_completion_tokens:
            request_params["max_completion_tokens"] = token_limit
            logger.debug(f"使用 max_completion_tokens={token_limit}")
        else:
            request_params["max_tokens"] = token_limit
            logger.debug(f"使用 max_tokens={token_limit}")
        
        # 设置temperature参数（某些模型不支持自定义temperature）
        if not use_default_temperature:
            request_params["temperature"] = temperature or self.temperature
            logger.debug(f"使用 temperature={request_params['temperature']}")
        else:
            logger.debug("不设置 temperature 参数，使用模型默认值")
        
        try:
            if stream:
                # 流式响应 - 使用 OpenAI SDK 的流式方法
                try:
                    # 使用 stream=True 创建流式响应
                    stream_obj = await self.async_client.chat.completions.create(**request_params)
                    
                    async for chunk in stream_obj:
                        if chunk.choices and len(chunk.choices) > 0:
                            delta = chunk.choices[0].delta
                            if delta and delta.content:
                                yield {
                                    "content": delta.content,
                                    "done": False
                                }
                    
                    yield {"done": True}
                    
                except Exception as stream_error:
                    error_msg = str(stream_error)
                    error_lower = error_msg.lower()
                    logger.error(f"流式请求失败: {error_msg}")
                    
                    # 如果错误是因为流式不支持，自动降级为非流式
                    is_stream_unsupported = (
                        "stream" in error_lower and 
                        ("unsupported" in error_lower or 
                         "verified" in error_lower or 
                         "organization" in error_lower or
                         "unsupported_value" in error_lower)
                    )
                    
                    if is_stream_unsupported:
                        logger.warning("检测到流式响应不支持，自动降级为非流式响应")
                        request_params["stream"] = False
                        
                        # 使用非流式逻辑（复用下面的错误处理）
                        # 直接调用非流式分支的逻辑
                        try:
                            response = await self.async_client.chat.completions.create(**request_params)
                            
                            if response.choices and len(response.choices) > 0:
                                message = response.choices[0].message
                                content = message.content if message else None
                                
                                # 检查 finish_reason，如果是 'length' 且 content 为空，说明 token 限制太小
                                finish_reason = response.choices[0].finish_reason if hasattr(response.choices[0], 'finish_reason') else None
                                
                                if content:
                                    usage = response.usage.model_dump() if response.usage else {}
                                    yield {
                                        "content": content,
                                        "done": True,
                                        "usage": usage
                                    }
                                    logger.info(f"降级为非流式成功，返回内容长度: {len(content)}")
                                    return
                                elif finish_reason == 'length' or (not content and finish_reason):
                                    # 如果因为长度限制而截断，且内容为空，说明 token 限制太小
                                    # 或者 finish_reason 存在但内容为空（可能是推理模型）
                                    logger.warning(f"降级后因长度限制未获取到内容（finish_reason={finish_reason}），尝试大幅增加 max_completion_tokens")
                                    
                                    # 检查 usage 信息，看是否有 reasoning_tokens
                                    usage_info = response.usage.model_dump() if response.usage else {}
                                    reasoning_tokens = usage_info.get('completion_tokens_details', {}).get('reasoning_tokens', 0) if isinstance(usage_info.get('completion_tokens_details'), dict) else 0
                                    
                                    if reasoning_tokens > 0:
                                        logger.info(f"检测到推理token使用: {reasoning_tokens}，说明模型需要更多token生成实际内容")
                                    
                                    # 尝试大幅增加 token 限制并重试（推理模型需要更多token）
                                    if use_max_completion_tokens and "max_completion_tokens" in request_params:
                                        current_limit = request_params["max_completion_tokens"]
                                        # 如果检测到推理token，大幅增加限制
                                        if reasoning_tokens > 0:
                                            new_limit = max(current_limit * 3, 2000)  # 至少2000，或当前值的3倍
                                        else:
                                            new_limit = min(current_limit * 2, 2000)  # 最多2000
                                        
                                        # 如果已经尝试过增加，且仍然失败，使用更大的值
                                        if current_limit >= 1000:
                                            new_limit = 4000  # 推理模型可能需要更多token
                                        
                                        logger.info(f"尝试增加 max_completion_tokens 从 {current_limit} 到 {new_limit}")
                                        request_params["max_completion_tokens"] = new_limit
                                        
                                        try:
                                            retry_response = await self.async_client.chat.completions.create(**request_params)
                                            if retry_response.choices and len(retry_response.choices) > 0:
                                                retry_message = retry_response.choices[0].message
                                                retry_content = retry_message.content if retry_message else None
                                                if retry_content:
                                                    usage = retry_response.usage.model_dump() if retry_response.usage else {}
                                                    yield {
                                                        "content": retry_content,
                                                        "done": True,
                                                        "usage": usage
                                                    }
                                                    logger.info(f"增加token限制后成功，返回内容长度: {len(retry_content)}")
                                                    return
                                                else:
                                                    # 仍然没有内容，记录详细信息
                                                    retry_finish_reason = retry_response.choices[0].finish_reason if hasattr(retry_response.choices[0], 'finish_reason') else None
                                                    retry_usage = retry_response.usage.model_dump() if retry_response.usage else {}
                                                    logger.warning(f"增加token限制后仍无内容，finish_reason={retry_finish_reason}, usage={retry_usage}")
                                        except Exception as retry_error:
                                            logger.error(f"增加token限制后重试失败: {retry_error}")
                            
                            # 如果到这里说明没有获取到内容，记录详细信息
                            logger.warning(f"降级后未获取到内容，response: {response}, choices: {response.choices if hasattr(response, 'choices') else 'N/A'}")
                            
                        except Exception as fallback_error:
                            error_msg = str(fallback_error)
                            logger.error(f"降级请求失败: {error_msg}")
                            
                            # 如果错误是因为参数问题，尝试修复参数后重试
                            if not use_max_completion_tokens and "max_tokens" in error_msg.lower() and "max_completion_tokens" in error_msg.lower():
                                logger.info("降级时检测到 max_tokens 参数错误，尝试使用 max_completion_tokens")
                                if "max_tokens" in request_params:
                                    del request_params["max_tokens"]
                                request_params["max_completion_tokens"] = token_limit
                                
                                if "temperature" in error_msg.lower() and ("only the default" in error_msg.lower() or "unsupported value" in error_msg.lower()):
                                    if "temperature" in request_params:
                                        del request_params["temperature"]
                                
                                try:
                                    response = await self.async_client.chat.completions.create(**request_params)
                                    if response.choices and len(response.choices) > 0:
                                        message = response.choices[0].message
                                        content = message.content if message else None
                                        if content:
                                            usage = response.usage.model_dump() if response.usage else {}
                                            yield {
                                                "content": content,
                                                "done": True,
                                                "usage": usage
                                            }
                                            logger.info(f"降级重试成功，返回内容长度: {len(content)}")
                                            return
                                except Exception as retry_error:
                                    logger.error(f"降级重试也失败: {retry_error}")
                            
                            yield {"content": f"API错误: {error_msg}", "done": True, "error": True}
                            return
                        
                        # 如果正常执行到这里但没有return，说明没有获取到内容
                        yield {"content": "未获取到响应内容", "done": True, "error": True}
                    else:
                        # 其他类型的错误，直接返回错误信息
                        logger.error(f"流式请求失败（非流式不支持错误）: {error_msg}")
                        yield {"content": f"API错误: {error_msg}", "done": True, "error": True}
            else:
                # 非流式响应
                try:
                    response = await self.async_client.chat.completions.create(**request_params)
                    content = response.choices[0].message.content if response.choices else ""
                    usage = response.usage.model_dump() if response.usage else {}
                    
                    yield {
                        "content": content or "",
                        "done": True,
                        "usage": usage
                    }
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"LLM API错误: {error_msg}")
                    
                    # 如果错误是因为 max_tokens 参数，尝试使用 max_completion_tokens
                    if not use_max_completion_tokens and "max_tokens" in error_msg.lower() and "max_completion_tokens" in error_msg.lower():
                        logger.info("检测到 max_tokens 参数错误，尝试使用 max_completion_tokens")
                        if "max_tokens" in request_params:
                            del request_params["max_tokens"]
                        request_params["max_completion_tokens"] = token_limit
                        
                        # 检查是否也有temperature错误
                        if "temperature" in error_msg.lower() and ("only the default" in error_msg.lower() or "unsupported value" in error_msg.lower()):
                            logger.info("检测到 temperature 参数错误，移除 temperature 参数使用默认值")
                            if "temperature" in request_params:
                                del request_params["temperature"]
                        
                        # 重试
                        try:
                            response = await self.async_client.chat.completions.create(**request_params)
                            content = response.choices[0].message.content if response.choices else ""
                            usage = response.usage.model_dump() if response.usage else {}
                            yield {
                                "content": content or "",
                                "done": True,
                                "usage": usage
                            }
                        except Exception as retry_error:
                            logger.error(f"重试后仍然错误: {retry_error}")
                            yield {"content": f"API错误: {str(retry_error)}", "done": True, "error": True}
                    # 如果只是temperature错误
                    elif "temperature" in error_msg.lower() and ("only the default" in error_msg.lower() or "unsupported value" in error_msg.lower()):
                        logger.info("检测到 temperature 参数错误，移除 temperature 参数使用默认值")
                        if "temperature" in request_params:
                            del request_params["temperature"]
                        
                        try:
                            response = await self.async_client.chat.completions.create(**request_params)
                            content = response.choices[0].message.content if response.choices else ""
                            usage = response.usage.model_dump() if response.usage else {}
                            yield {
                                "content": content or "",
                                "done": True,
                                "usage": usage
                            }
                        except Exception as retry_error:
                            logger.error(f"重试后仍然错误: {retry_error}")
                            yield {"content": f"API错误: {str(retry_error)}", "done": True, "error": True}
                    else:
                        yield {"content": f"API错误: {error_msg}", "done": True, "error": True}
                        
        except Exception as e:
            logger.error(f"LLM API调用失败: {e}")
            yield {"content": f"API调用失败: {str(e)}", "done": True, "error": True}
    
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
