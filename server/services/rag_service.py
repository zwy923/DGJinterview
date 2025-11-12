"""
RAG检索服务
CV/JD使用关键词提取，外部知识库使用向量检索
"""
import re
from typing import List, Optional
import asyncio

from core.types import RagBundle, DocChunk
from core.config import agent_settings
from services.embed_service import embedding_service
from services.doc_store import doc_store
from logs import setup_logger

logger = setup_logger(__name__)


class RAGService:
    """RAG检索服务"""
    
    def __init__(self):
        self.top_k = agent_settings.RAG_TOPK
        self.token_budget = agent_settings.RAG_TOKEN_BUDGET
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        从问题中提取关键词（简单实现）
        
        Args:
            text: 问题文本
        
        Returns:
            关键词列表
        """
        # 移除标点符号
        text = re.sub(r'[^\w\s]', ' ', text)
        # 分词（简单按空格分割）
        words = text.lower().split()
        # 过滤停用词和短词
        stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        keywords = [w for w in words if len(w) > 1 and w not in stop_words]
        return keywords[:10]  # 最多返回10个关键词
    
    def _select_cv_snippets(self, cv_text: str, question: str) -> List[str]:
        """
        从CV中提取相关片段（基于关键词匹配）
        
        Args:
            cv_text: CV文本
            question: 问题文本
        
        Returns:
            相关片段列表
        """
        if not cv_text or not question:
            return []
        
        keywords = self._extract_keywords(question)
        if not keywords:
            return []
        
        # 按段落分割CV
        paragraphs = [p.strip() for p in cv_text.split('\n') if p.strip()]
        
        # 计算每个段落的相关度（关键词匹配数）
        scored_paragraphs = []
        for para in paragraphs:
            para_lower = para.lower()
            score = sum(1 for kw in keywords if kw in para_lower)
            if score > 0:
                scored_paragraphs.append((score, para))
        
        # 按分数排序，返回前3个
        scored_paragraphs.sort(reverse=True, key=lambda x: x[0])
        return [para for _, para in scored_paragraphs[:3]]
    
    def _select_jd_snippets(self, jd_text: str, question: str) -> List[str]:
        """
        从JD中提取相关片段（基于关键词匹配）
        
        Args:
            jd_text: JD文本
            question: 问题文本
        
        Returns:
            相关片段列表
        """
        if not jd_text or not question:
            return []
        
        keywords = self._extract_keywords(question)
        if not keywords:
            return []
        
        # 按段落分割JD
        paragraphs = [p.strip() for p in jd_text.split('\n') if p.strip()]
        
        # 计算每个段落的相关度
        scored_paragraphs = []
        for para in paragraphs:
            para_lower = para.lower()
            score = sum(1 for kw in keywords if kw in para_lower)
            if score > 0:
                scored_paragraphs.append((score, para))
        
        # 按分数排序，返回前3个
        scored_paragraphs.sort(reverse=True, key=lambda x: x[0])
        return [para for _, para in scored_paragraphs[:3]]
    
    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本的token数量（简单实现：中文字符数 + 英文单词数）
        
        Args:
            text: 文本
        
        Returns:
            估算的token数
        """
        # 中文字符数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        # 英文单词数
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
        # 简单估算：中文字符 * 1.5 + 英文单词
        return int(chinese_chars * 1.5 + english_words)
    
    def _trim_to_budget(
        self,
        cv_chunks: List[str],
        jd_chunks: List[str],
        ext_chunks: List[DocChunk]
    ) -> tuple[List[str], List[str], List[DocChunk]]:
        """
        根据token预算裁剪片段（优先级：CV > JD > 外部文档）
        
        Args:
            cv_chunks: CV片段
            jd_chunks: JD片段
            ext_chunks: 外部文档片段
        
        Returns:
            裁剪后的片段
        """
        budget = self.token_budget
        used = 0
        
        # 优先保留CV
        trimmed_cv = []
        for chunk in cv_chunks:
            tokens = self._estimate_tokens(chunk)
            if used + tokens <= budget:
                trimmed_cv.append(chunk)
                used += tokens
            else:
                # 如果超出预算，尝试截断
                remaining = budget - used
                if remaining > 50:  # 至少保留50个token
                    # 简单截断（实际应该更智能）
                    trimmed_cv.append(chunk[:remaining * 2])  # 粗略估算
                break
        
        # 然后保留JD
        trimmed_jd = []
        for chunk in jd_chunks:
            tokens = self._estimate_tokens(chunk)
            if used + tokens <= budget:
                trimmed_jd.append(chunk)
                used += tokens
            else:
                remaining = budget - used
                if remaining > 50:
                    trimmed_jd.append(chunk[:remaining * 2])
                break
        
        # 最后保留外部文档
        trimmed_ext = []
        for chunk in ext_chunks:
            tokens = self._estimate_tokens(chunk.content)
            if used + tokens <= budget:
                trimmed_ext.append(chunk)
                used += tokens
            else:
                remaining = budget - used
                if remaining > 50:
                    # 创建截断的chunk
                    trimmed_chunk = DocChunk(
                        content=chunk.content[:remaining * 2],
                        source=chunk.source,
                        metadata=chunk.metadata,
                        score=chunk.score
                    )
                    trimmed_ext.append(trimmed_chunk)
                break
        
        return trimmed_cv, trimmed_jd, trimmed_ext
    
    async def query(
        self,
        question: str,
        cv_text: str,
        jd_text: str,
        session_id: Optional[str] = None
    ) -> RagBundle:
        """
        执行RAG检索
        
        Args:
            question: 问题文本
            cv_text: CV文本
            jd_text: JD文本
            session_id: 会话ID（用于外部知识库过滤）
        
        Returns:
            RagBundle对象
        """
        # 并行执行CV/JD提取和外部知识库检索
        cv_task = asyncio.create_task(
            asyncio.to_thread(self._select_cv_snippets, cv_text, question)
        )
        jd_task = asyncio.create_task(
            asyncio.to_thread(self._select_jd_snippets, jd_text, question)
        )
        
        # 外部知识库向量检索
        ext_chunks = []
        try:
            query_emb = await embedding_service.embed(question)
            if query_emb is not None:
                ext_chunks = await doc_store.search_by_embedding(
                    query_emb,
                    top_k=self.top_k,
                    session_id=session_id
                )
        except Exception as e:
            logger.warning(f"外部知识库检索失败: {e}")
        
        # 等待CV/JD提取完成
        cv_chunks = await cv_task
        jd_chunks = await jd_task
        
        # 根据token预算裁剪
        cv_chunks, jd_chunks, ext_chunks = self._trim_to_budget(
            cv_chunks, jd_chunks, ext_chunks
        )
        
        return RagBundle(
            cv_chunks=cv_chunks,
            jd_chunks=jd_chunks,
            ext_chunks=ext_chunks
        )


# 全局实例
rag_service = RAGService()

