"""
WebSocket 工具函数
"""
import json
from typing import Any, Dict


async def send_json(ws, payload: Dict[str, Any]):
    """
    发送JSON消息到WebSocket客户端
    
    Args:
        ws: WebSocket连接对象
        payload: 要发送的字典数据
    """
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        print(f"[WS SEND ERROR] {e}")


async def receive_json(ws) -> Dict[str, Any]:
    """
    从WebSocket接收JSON消息
    
    Args:
        ws: WebSocket连接对象
    
    Returns:
        解析后的字典数据
    """
    try:
        msg = await ws.receive()
        if "text" in msg:
            return json.loads(msg["text"])
        return {}
    except Exception as e:
        print(f"[WS RECEIVE ERROR] {e}")
        return {}

