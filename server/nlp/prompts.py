"""
模板与JSON schema
"""
import json
from typing import Dict, Any, Optional
import os
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from config import settings
from logs import setup_logger
from nlp.exceptions import PromptError

logger = setup_logger(__name__)


class PromptManager:
    """Prompt模板管理器（LangChain ChatPromptTemplate）"""
    
    def __init__(self):
        self.prompts_dir = Path(__file__).parent / "prompts"
        self._prompts: Dict[str, ChatPromptTemplate] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._load_prompts()
    
    def _load_prompts(self):
        """加载所有prompt模板为ChatPromptTemplate对象"""
        try:
            # 遍历prompts目录下的所有.txt文件
            for file_path in self.prompts_dir.glob("*.txt"):
                name = file_path.stem  # 文件名（不含扩展名）
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        template_text = f.read()
                    
                    # 转换为ChatPromptTemplate
                    # 使用from_template自动处理变量
                    template = ChatPromptTemplate.from_template(template_text)
                    self._prompts[name] = template
                    logger.debug(f"加载Prompt模板: {name}")
                except Exception as e:
                    logger.error(f"加载模板文件 {file_path} 失败: {e}")
        except Exception as e:
            logger.error(f"加载prompt模板目录失败: {e}")
    
    def get_prompt(self, name: str) -> ChatPromptTemplate:
        """
        获取prompt模板（ChatPromptTemplate对象）
        
        Args:
            name: prompt名称（文件名，不含扩展名）
        
        Returns:
            ChatPromptTemplate对象
        
        Raises:
            PromptError: 模板不存在时抛出
        """
        template = self._prompts.get(name)
        if not template:
            raise PromptError(f"Prompt模板 '{name}' 不存在")
        return template
    
    def get_prompt_text(self, name: str) -> str:
        """
        获取prompt模板文本（兼容方法）
        
        Args:
            name: prompt名称
        
        Returns:
            模板文本字符串
        """
        template = self.get_prompt(name)
        # 从ChatPromptTemplate提取模板文本
        # 注意：ChatPromptTemplate可能有多个消息，这里简化处理
        if hasattr(template, 'messages') and template.messages:
            # 尝试从第一个消息获取模板
            first_msg = template.messages[0]
            if hasattr(first_msg, 'prompt') and hasattr(first_msg.prompt, 'template'):
                return first_msg.prompt.template
        return str(template)
    
    def register_schema(self, name: str, schema: Dict[str, Any]):
        """注册JSON schema"""
        self._schemas[name] = schema
    
    def get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """获取JSON schema"""
        return self._schemas.get(name)


# 面试分析JSON schema
INTERVIEW_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "number",
            "description": "综合评分（0-100）"
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "优点列表"
        },
        "weaknesses": {
            "type": "array",
            "items": {"type": "string"},
            "description": "不足列表"
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "改进建议"
        },
        "technical_depth": {
            "type": "string",
            "enum": ["基础", "中等", "深入"],
            "description": "技术深度"
        },
        "communication_quality": {
            "type": "string",
            "enum": ["需要改进", "良好", "优秀"],
            "description": "沟通质量"
        }
    },
    "required": ["score", "strengths", "weaknesses", "recommendations"]
}


# 全局prompt管理器
prompt_manager = PromptManager()
prompt_manager.register_schema("interview_analysis", INTERVIEW_ANALYSIS_SCHEMA)

