"""
RAG检索服务
CV使用向量检索（整体embedding），JD使用关键词提取，外部知识库使用向量检索
"""
import re
from typing import List, Optional
import asyncio

from core.types import RagBundle, DocChunk
from core.config import agent_settings
from services.embed_service import embedding_service
from services.doc_store import doc_store
from storage.dao import cv_dao
from logs import setup_logger

logger = setup_logger(__name__)

# 项目/实习相关关键词白名单
PROJECT_HINTS = ["项目", "实习", "project", "experience", "intern", "develop", "build", "实现", "开发"]


class RAGService:
    """RAG检索服务"""
    
    def __init__(self):
        self.top_k = agent_settings.RAG_TOPK
        self.token_budget = agent_settings.RAG_TOKEN_BUDGET
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        从问题中提取关键词（改进版：支持中英文混合）
        
        Args:
            text: 问题文本
        
        Returns:
            关键词列表
        """
        # 保留中文字符、英文字母和空格，移除其他标点符号
        text = re.sub(r'[^\w\u4e00-\u9fff\s]', ' ', text)
        # 提取中文词和英文单词
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text.lower())
        # 过滤停用词和短词
        stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        keywords = [w for w in words if len(w) > 1 and w not in stop_words]
        return keywords[:10]  # 最多返回10个关键词
    
    async def _select_cv_snippets_by_embedding(self, question: str) -> List[str]:
        """
        使用向量检索从CV中提取相关片段（整体embedding，不分片）
        
        Args:
            question: 问题文本
        
        Returns:
            相关CV内容列表（如果找到相似CV，返回其完整内容）
        """
        if not question or not question.strip():
            return []
        
        try:
            # 检查embedding服务是否可用
            if embedding_service is None or not embedding_service.api_key:
                logger.warning("Embedding服务不可用，降级到关键词匹配")
                return []
            
            # 生成问题的embedding
            query_emb = await embedding_service.embed(question)
            if query_emb is None:
                logger.warning("无法生成问题embedding，降级到关键词匹配")
                return []
            
            # 从数据库搜索相似的CV（整体embedding）
            # 注意：search_similar_cvs只会返回有embedding的CV
            similar_cvs = await cv_dao.search_similar_cvs(query_emb, limit=1)
            
            if similar_cvs:
                cv = similar_cvs[0]
                cv_content = cv.get("content", "")
                similarity = cv.get("similarity", 0)
                
                # 相似度阈值：0.3（降低阈值，因为CV是整体embedding，相似度可能较低）
                if cv_content and similarity > 0.3:
                    logger.info(f"向量检索找到相似CV，相似度: {similarity:.3f}")
                    # 返回整个CV内容（不分片）
                    return [cv_content]
                else:
                    logger.info(f"CV相似度过低: {similarity:.3f}，降级到关键词匹配")
                    return []
            else:
                # 如果未找到，可能是CV没有embedding，尝试获取CV并自动生成embedding
                logger.info("向量检索未找到相似CV，尝试获取CV并检查embedding状态")
                try:
                    cv_info = await cv_dao.get_default_cv(auto_generate_embedding=True)
                    if cv_info and cv_info.get("content"):
                        # 如果CV存在但没有embedding，get_default_cv会自动生成
                        # 但生成是异步的，可能需要等待
                        # 这里先返回空，让降级逻辑处理
                        logger.info("CV存在但可能缺少embedding，已触发自动生成，降级到关键词匹配")
                except Exception as e:
                    logger.warning(f"获取CV时出错: {e}")
                
                return []
        except Exception as e:
            logger.warning(f"CV向量检索失败: {e}，降级到关键词匹配")
            return []
    
    def _select_cv_snippets_keyword(self, cv_text: str, question: str) -> List[str]:
        """
        从CV中提取相关片段（基于关键词匹配，降级方案）
        
        Args:
            cv_text: CV文本
            question: 问题文本
        
        Returns:
            相关片段列表
        """
        if not cv_text or not cv_text.strip():
            logger.warning("CV文本为空，无法提取片段")
            return []
        
        # 按段落分割CV
        paragraphs = [p.strip() for p in cv_text.split('\n') if p.strip()]
        
        if not question or not question.strip():
            # 如果问题为空，优先返回项目/实习段，否则返回前5段
            project_blocks = [p for p in paragraphs if any(k in p.lower() for k in PROJECT_HINTS)]
            return project_blocks[:5] if project_blocks else paragraphs[:5]
        
        q_lower = question.lower()
        
        # 优先：问题中提到项目/实习
        if any(k in q_lower for k in PROJECT_HINTS):
            project_blocks = [p for p in paragraphs if any(k in p.lower() for k in PROJECT_HINTS)]
            if project_blocks:
                logger.info(f"项目类问题命中，返回 {len(project_blocks[:5])} 段项目内容")
                return project_blocks[:5]
        
        # 否则：常规关键词匹配
        keywords = self._extract_keywords(question)
        if not keywords:
            # 如果没有关键词，优先返回项目/实习段，否则前5段
            project_blocks = [p for p in paragraphs if any(k in p.lower() for k in PROJECT_HINTS)]
            return project_blocks[:5] if project_blocks else paragraphs[:5]
        
        # 计算每个段落的相关度（关键词匹配数）
        scored_paragraphs = []
        for para in paragraphs:
            para_lower = para.lower()
            score = sum(1 for kw in keywords if kw in para_lower)
            if score > 0:
                scored_paragraphs.append((score, para))
        
        # 按分数排序，返回前3个
        scored_paragraphs.sort(reverse=True, key=lambda x: x[0])
        result = [para for _, para in scored_paragraphs[:3]]
        
        # fallback：优先返回项目/实习，否则前5段
        if not result:
            project_blocks = [p for p in paragraphs if any(k in p.lower() for k in PROJECT_HINTS)]
            result = project_blocks[:5] if project_blocks else paragraphs[:5]
            logger.info("关键词匹配失败，使用项目/实习或前5段fallback")
        
        return result
    
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
        估算文本的token数量（优化版：对小段落简化估算）
        
        Args:
            text: 文本
        
        Returns:
            估算的token数
        """
        # 对于小段落，直接使用长度估算（更快）
        if len(text) < 200:
            return len(text) // 2
        
        # 对于长段落，使用更精确的估算
        # 中文字符数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        # 英文单词数
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
        # 简单估算：中文字符 * 1.5 + 英文单词
        return int(chinese_chars * 1.5 + english_words)
    
    def _trim_chunk(self, chunk: str, max_chars: int = 1000) -> str:
        """
        裁剪单个chunk的最大字符数（防止超长文档）
        
        Args:
            chunk: 文本片段
            max_chars: 最大字符数
        
        Returns:
            裁剪后的文本
        """
        if len(chunk) > max_chars:
            return chunk[:max_chars] + "..."
        return chunk
    
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
            # 先裁剪超长chunk
            chunk = self._trim_chunk(chunk)
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
            chunk = self._trim_chunk(chunk)
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
            # 先裁剪超长chunk
            trimmed_content = self._trim_chunk(chunk.content)
            tokens = self._estimate_tokens(trimmed_content)
            if used + tokens <= budget:
                # 如果内容被裁剪，创建新的chunk
                if trimmed_content != chunk.content:
                    trimmed_chunk = DocChunk(
                        content=trimmed_content,
                        source=chunk.source,
                        metadata=chunk.metadata,
                        score=chunk.score
                    )
                    trimmed_ext.append(trimmed_chunk)
                else:
                    trimmed_ext.append(chunk)
                used += tokens
            else:
                remaining = budget - used
                if remaining > 50:
                    # 创建截断的chunk
                    trimmed_chunk = DocChunk(
                        content=trimmed_content[:remaining * 2],
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
            cv_text: CV文本（用于降级方案）
            jd_text: JD文本
            session_id: 会话ID（用于外部知识库过滤）
        
        Returns:
            RagBundle对象
        """
        # 并行执行CV向量检索、JD提取和外部知识库检索
        # CV使用向量检索（整体embedding，不分片）
        cv_task = asyncio.create_task(
            self._select_cv_snippets_by_embedding(question)
        )
        jd_task = asyncio.create_task(
            asyncio.to_thread(self._select_jd_snippets, jd_text, question)
        )
        
        # 外部知识库向量检索
        ext_chunks = []
        try:
            # 检查 embedding_service 和 doc_store 是否可用
            if embedding_service is not None and hasattr(doc_store, 'search_by_embedding'):
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
        jd_chunks = await jd_task  # 等待JD提取完成
        
        # 如果向量检索失败或未找到，降级到关键词匹配
        if not cv_chunks and cv_text:
            logger.info("CV向量检索未找到结果，降级到关键词匹配")
            cv_chunks = await asyncio.to_thread(
                self._select_cv_snippets_keyword, cv_text, question
            )
        
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

