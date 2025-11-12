"""
FastAPI 入口
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from logs import setup_logger
from storage.pg import pg_pool
from gateway.ws_audio import handle_audio_websocket
from api_routes import router

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("🚀 启动应用...")
    
    # 初始化PostgreSQL（如果启用）
    if settings.RAG_ENABLED:
        try:
            await pg_pool.initialize()
        except Exception as e:
            logger.error(f"PostgreSQL初始化失败: {e}")
    
    yield
    
    # 关闭时清理
    logger.info("🛑 关闭应用...")
    if settings.RAG_ENABLED:
        await pg_pool.close()


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(router, prefix="/api")

# WebSocket路由：/ws/audio/{session_id}/{source}
@app.websocket("/ws/audio/{session_id}/{source}")
async def ws_audio(ws: WebSocket, session_id: str, source: str):
    """
    音频WebSocket端点
    
    Args:
        session_id: 会话ID
        source: 音频源（mic 或 sys）
    """
    if source not in ["mic", "sys"]:
        await ws.close(code=1008, reason="Invalid source. Must be 'mic' or 'sys'")
        return
    
    await handle_audio_websocket(ws, session_id, source)


# 兼容旧的路由（向后兼容）
@app.websocket("/ws/transcribe")
async def ws_transcribe_legacy(ws: WebSocket):
    """旧版WebSocket路由（向后兼容）"""
    # 使用默认session_id和source
    await handle_audio_websocket(ws, "default", "mic")


# 健康检查
@app.get("/")
async def root():
    return {
        "message": f"{settings.APP_NAME} 后端服务运行中",
        "status": "ok",
        "version": settings.APP_VERSION
    }


@app.get("/health")
async def health():
    """健康检查端点"""
    return {
        "status": "healthy",
        "model": "loaded",
        "rag_enabled": settings.RAG_ENABLED
    }


@app.get("/metrics")
async def metrics():
    """指标端点"""
    from logs import metrics
    return metrics.get_all()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
