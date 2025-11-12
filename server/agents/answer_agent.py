"""
AnswerAgent：核心编排器
融合RAG结果并驱动流式生成
"""
import asyncio
from typing import Callable, Literal, Optional
import time

from core.state import SessionState
from core.types import RagBundle
from services.rag_service import rag_service
from services.llm_service import llm_service
from logs import setup_logger

logger = setup_logger(__name__)


class AnswerAgent:
    """面试助手Agent"""
    
    def __init__(self, state: SessionState, cv_text: str, jd_text: str):
        """
        初始化Agent
        
        Args:
            state: SessionState实例
            cv_text: CV文本
            jd_text: JD文本
        """
        self.state = state
        self.cv_text = cv_text
        self.jd_text = jd_text
    
    def _build_prompt(
        self,
        question: str,
        rag_bundle: RagBundle,
        mode: Literal["brief", "full"]
    ) -> str:
        """
        构建Prompt
        
        Args:
            question: 问题文本
            rag_bundle: RAG检索结果
            mode: 模式（brief或full）
        
        Returns:
            完整prompt
        """
        # 获取最近对话历史
        recent_history = self.state.get_history_with_embeddings(limit=10)
        dialogue_text = ""
        if recent_history:
            dialogue_lines = []
            for item in recent_history:
                speaker_name = "面试官" if item.get("speaker") == "interviewer" else "我"
                content = item.get("content", "")
                if content:
                    dialogue_lines.append(f"{speaker_name}：{content}")
            dialogue_text = "\n".join(dialogue_lines)
        
        # 构建CV部分
        cv_section = ""
        if rag_bundle.cv_chunks:
            cv_section = "\n".join(rag_bundle.cv_chunks)
        
        # 构建JD部分
        jd_section = ""
        if rag_bundle.jd_chunks:
            jd_section = "\n".join(rag_bundle.jd_chunks)
        
        # 构建外部知识库部分
        ext_section = ""
        if rag_bundle.ext_chunks:
            ext_lines = []
            for chunk in rag_bundle.ext_chunks:
                ext_lines.append(chunk.content)
            ext_section = "\n".join(ext_lines)
        
        # 根据模式选择不同的prompt模板
        if mode == "brief":
            # 快答模式：一句话回答
            prompt = f"""你是一位专业的面试助手，帮助面试者回答问题。

【当前问题】
{question}

【简历信息】
{cv_section if cv_section else "（无）"}

【岗位信息】
{jd_section if jd_section else "（无）"}

【外部知识】
{ext_section if ext_section else "（无）"}

【最近对话】
{dialogue_text if dialogue_text else "（无）"}

请基于以上内容，用一句话简短回答这个问题。以第一人称表述。"""
        else:
            # 正常模式：详细回答
            prompt = f"""你是一位专业的面试助手，帮助面试者优化回答。

【当前问题】
{question}

【简历信息】
{cv_section if cv_section else "（无）"}

【岗位信息】
{jd_section if jd_section else "（无）"}

【外部知识】
{ext_section if ext_section else "（无）"}

【最近对话】
{dialogue_text if dialogue_text else "（无）"}

请基于以上内容，生成一个详细、结构化的回答建议。回答要：
- 自然、自信，以第一人称表述
- 结合简历中的相关经验
- 与岗位要求对齐
- 长度控制在6-12句话

如果某些信息缺失，可以简要说明假设。"""
        
        return prompt
    
    async def generate_answer(
        self,
        question: str,
        mode: Literal["brief", "full"] = "full",
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        生成回答（流式）
        
        Args:
            question: 问题文本
            mode: 模式（brief或full）
            stream_callback: 流式回调函数（可选）
        
        Returns:
            完整回答文本
        """
        if not question or not question.strip():
            logger.warning("问题为空，跳过生成")
            return ""
        
        try:
            # 1. RAG检索
            logger.info(f"开始RAG检索，问题: {question[:50]}...")
            rag_bundle = await rag_service.query(
                question=question,
                cv_text=self.cv_text,
                jd_text=self.jd_text,
                session_id=self.state.sid
            )
            
            # 2. 构建Prompt
            prompt = self._build_prompt(question, rag_bundle, mode)
            
            # 3. 流式生成
            logger.info(f"开始流式生成，模式: {mode}")
            full_answer = ""
            
            async for chunk in llm_service.stream_generate(prompt, mode=mode):
                full_answer += chunk
                if stream_callback:
                    try:
                        # 检查是否是协程函数
                        if asyncio.iscoroutinefunction(stream_callback):
                            await stream_callback(chunk)
                        else:
                            stream_callback(chunk)
                    except Exception as e:
                        logger.warning(f"流式回调失败: {e}")
            
            # 4. 将最终答案写入历史
            if full_answer:
                self.state.add_to_history(
                    content=full_answer,
                    speaker="assistant",
                    timestamp=None  # 使用默认时间戳
                )
                logger.info(f"回答生成完成，长度: {len(full_answer)}")
            
            return full_answer
        
        except Exception as e:
            logger.error(f"生成回答失败: {e}")
            return ""


# 全局实例（可选，如果需要单例）
# answer_agent = None

