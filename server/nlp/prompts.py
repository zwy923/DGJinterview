"""
模板与JSON schema
"""
import json
from typing import Dict, Any, Optional
import os

from config import settings
from logs import setup_logger

logger = setup_logger(__name__)


class PromptManager:
    """Prompt模板管理器"""
    
    def __init__(self):
        self.prompts_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "prompts"
        )
        self._prompts: Dict[str, str] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._load_prompts()
    
    def _load_prompts(self):
        """加载所有prompt模板"""
        try:
            # 加载interview_analysis.txt
            analysis_path = os.path.join(self.prompts_dir, "interview_analysis.txt")
            if os.path.exists(analysis_path):
                with open(analysis_path, "r", encoding="utf-8") as f:
                    self._prompts["interview_analysis"] = f.read()
            
            # 加载gpt_qa.txt
            qa_path = os.path.join(self.prompts_dir, "gpt_qa.txt")
            if os.path.exists(qa_path):
                with open(qa_path, "r", encoding="utf-8") as f:
                    self._prompts["gpt_qa"] = f.read()
        except Exception as e:
            logger.error(f"加载prompt模板失败: {e}")
    
    def get_prompt(self, name: str, **kwargs) -> str:
        """
        获取prompt模板并填充变量
        
        Args:
            name: prompt名称
            **kwargs: 模板变量
        
        Returns:
            填充后的prompt
        """
        template = self._prompts.get(name, "")
        if not template:
            logger.warning(f"Prompt模板 '{name}' 不存在")
            return ""
        
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Prompt模板变量缺失: {e}")
            return template
    
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

