"""
LangChain 自定义组件
封装现有的 LLM API 和检索器
"""
from typing import List, Optional, Any, AsyncIterator
import numpy as np

from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult, ChatGenerationChunk
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from asr.session import SessionState
from nlp.llm_api import llm_api
from utils.embedding import embedding_service
from nlp.exceptions import LLMError, RetrievalError
from logs import setup_logger

logger = setup_logger(__name__)


class CustomLLMWrapper(BaseChatModel):
    """自定义 LLM 包装器，封装现有的 llm_api"""
    
    @property
    def _llm_type(self) -> str:
        return "custom_llm"
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """同步生成（LangChain 会调用异步版本）"""
        raise NotImplementedError("请使用异步方法")
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """异步生成（支持流式，通过回调实时推送token）"""
        try:
            # 将 LangChain 消息转换为 API 格式
            api_messages = []
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    api_messages.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    api_messages.append({"role": "assistant", "content": msg.content})
            
            # 使用流式生成，通过回调实时推送token
            content_parts = []
            async for chunk in llm_api.chat(api_messages, stream=True, **kwargs):
                if chunk.get("content"):
                    content = chunk["content"]
                    content_parts.append(content)
                    
                    # 通过 run_manager 实时推送token（如果提供了回调）
                    if run_manager:
                        try:
                            # 创建 AIMessage chunk 并触发回调
                            from langchain_core.messages import AIMessageChunk
                            chunk_msg = AIMessageChunk(content=content)
                            await run_manager.on_llm_new_token(chunk_msg.content)
                        except Exception as callback_error:
                            # 回调失败不影响主流程
                            logger.debug(f"回调推送token失败: {callback_error}")
                
                if chunk.get("done"):
                    break
            
            content = "".join(content_parts)
            
            # 返回 ChatResult
            generation = ChatGeneration(
                message=AIMessage(content=content),
                generation_info={}
            )
            return ChatResult(generations=[generation])
        except LLMError:
            # 重新抛出LLMError
            raise
        except Exception as e:
            logger.error(f"LLM生成失败: {e}")
            raise LLMError(f"LLM调用失败: {str(e)}", cause=e)
    
    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """异步流式生成（返回 AsyncIterator[ChatGenerationChunk]）"""
        try:
            # 将 LangChain 消息转换为 API 格式
            api_messages = []
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    api_messages.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    api_messages.append({"role": "assistant", "content": msg.content})
            
            # 使用流式生成，实时yield每个token
            async for chunk in llm_api.chat(api_messages, stream=True, **kwargs):
                if chunk.get("content"):
                    content = chunk["content"]
                    
                    # 创建 ChatGenerationChunk 并yield
                    from langchain_core.messages import AIMessageChunk
                    chunk_msg = AIMessageChunk(content=content)
                    generation_chunk = ChatGenerationChunk(
                        message=chunk_msg,
                        generation_info={}
                    )
                    yield generation_chunk
                    
                    # 通过 run_manager 触发回调
                    if run_manager:
                        try:
                            await run_manager.on_llm_new_token(chunk_msg.content)
                        except Exception as callback_error:
                            logger.debug(f"回调推送token失败: {callback_error}")
                
                if chunk.get("done"):
                    break
                    
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"LLM流式生成失败: {e}")
            raise LLMError(f"LLM流式调用失败: {str(e)}", cause=e)


class SessionMemoryRetriever(BaseRetriever):
    """基于 SessionState 的内存检索器"""
    
    def __init__(self, session_state: SessionState, top_k: int = 3):
        super().__init__()
        self.session_state = session_state
        self.top_k = top_k
    
    def _get_relevant_documents(
        self, query: str, *, run_manager: Optional[Any] = None
    ) -> List[Document]:
        """同步检索（LangChain 会调用异步版本）"""
        raise NotImplementedError("请使用异步方法")
    
    async def _aget_relevant_documents(
        self, query: str, *, run_manager: Optional[Any] = None
    ) -> List[Document]:
        """异步检索相关文档"""
        try:
            # 检查 session_state
            if not hasattr(self.session_state, "get_history_with_embeddings"):
                logger.warning("SessionState未初始化embedding历史")
                return []
            
            # 生成查询向量
            query_embedding = await embedding_service.generate_embedding(query)
            if query_embedding is None:
                raise RetrievalError("生成查询向量失败")
            
            # 标准化查询向量
            qe = np.array(query_embedding, dtype=np.float32)
            qe_norm = np.linalg.norm(qe)
            if qe_norm == 0:
                logger.warning("查询向量为零向量")
                return []
            
            # 获取所有对话历史
            history = self.session_state.get_history_with_embeddings()
            if not history:
                return []
            
            # 计算相似度
            results = []
            for item in history:
                item_embedding = item.get('embedding')
                if item_embedding is None:
                    continue
                
                # 标准化item向量
                ie = np.array(item_embedding, dtype=np.float32)
                ie_norm = np.linalg.norm(ie)
                
                # 检查零向量
                if ie_norm == 0:
                    continue
                
                # 计算余弦相似度
                similarity = float(np.dot(qe, ie) / (qe_norm * ie_norm))
                
                # 过滤负数相似度（噪声）
                if similarity < 0:
                    continue
                
                # 构建文档
                speaker = item.get('speaker', 'unknown')
                content = item.get('content', '')
                if content:
                    doc = Document(
                        page_content=content,
                        metadata={
                            'speaker': speaker,
                            'similarity': similarity,
                            'timestamp': item.get('timestamp')
                        }
                    )
                    results.append((doc, similarity))
            
            # 按相似度排序并返回top_k
            results.sort(key=lambda x: x[1], reverse=True)
            return [doc for doc, _ in results[:self.top_k]]
        except RetrievalError:
            # 重新抛出RetrievalError
            raise
        except Exception as e:
            logger.exception(f"检索相关文档失败: {e}")
            raise RetrievalError(f"内存检索失败: {str(e)}", cause=e)


class RAGRetriever(BaseRetriever):
    """RAG检索器：封装数据库和知识库检索为LangChain Retriever"""
    
    def __init__(self, session_id: Optional[str] = None, top_k: int = 5):
        super().__init__()
        self.session_id = session_id
        self.top_k = top_k
        # 延迟导入避免循环依赖
        from nlp.rag import rag_retriever
        self.rag_retriever = rag_retriever
    
    def _get_relevant_documents(
        self, query: str, *, run_manager: Optional[Any] = None
    ) -> List[Document]:
        """同步检索（LangChain 会调用异步版本）"""
        raise NotImplementedError("请使用异步方法")
    
    async def _aget_relevant_documents(
        self, query: str, *, run_manager: Optional[Any] = None
    ) -> List[Document]:
        """异步检索相关文档（从数据库和知识库）"""
        try:
            # 生成查询向量
            query_embedding = await embedding_service.generate_embedding(query)
            if query_embedding is None:
                raise RetrievalError("生成查询向量失败")
            
            # 从数据库检索
            results = await self.rag_retriever.retrieve(
                query=query,
                query_embedding=query_embedding,
                session_id=self.session_id,
                top_k=self.top_k
            )
            
            # 转换为Document对象
            documents = []
            for item in results:
                content = item.get('content', '')
                if content:
                    doc = Document(
                        page_content=content,
                        metadata={
                            'speaker': item.get('speaker', 'unknown'),
                            'similarity': item.get('similarity', 0.0),
                            'timestamp': item.get('timestamp'),
                            'source': 'database'
                        }
                    )
                    documents.append(doc)
            
            return documents
        except RetrievalError:
            raise
        except Exception as e:
            logger.exception(f"RAG检索失败: {e}")
            raise RetrievalError(f"RAG检索失败: {str(e)}", cause=e)

