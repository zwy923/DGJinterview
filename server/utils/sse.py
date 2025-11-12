"""
SSE（Server-Sent Events）响应工具
"""
from typing import AsyncGenerator
from fastapi.responses import StreamingResponse
import json

from logs import setup_logger

logger = setup_logger(__name__)


async def sse_response(generator: AsyncGenerator[str, None]):
    """
    将异步生成器转换为SSE响应
    
    Args:
        generator: 异步生成器，yield字符串内容
    
    Returns:
        StreamingResponse对象
    """
    async def event_stream():
        try:
            async for chunk in generator:
                # 发送增量内容
                yield f"event: delta\n"
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            
            # 发送完成信号
            yield f"event: done\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"SSE流式响应失败: {e}")
            # 发送错误信号
            yield f"event: error\n"
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用nginx缓冲
        }
    )

