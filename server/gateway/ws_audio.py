"""
WebSocket音频网关
/ws/audio/{sid}/{src}  (src=mic|sys)
"""
import asyncio
import json
import time
import contextlib
from typing import Optional, Dict, Any
from datetime import datetime
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from asr.session import SessionState
from asr.pipeline import ASRPipeline
from storage.dao import transcript_dao
from utils.schemas import ChatMessage
from utils.websocket_tools import send_json
from config import settings
import struct
from logs import setup_logger, metrics

logger = setup_logger(__name__)

# 会话管理
_sessions: Dict[str, SessionState] = {}


async def handle_audio_websocket(ws: WebSocket, session_id: str, source: str):
    """
    处理音频WebSocket连接
    
    Args:
        ws: WebSocket连接
        session_id: 会话ID
        source: 音频源（"mic" 或 "sys"）
    """
    await ws.accept()
    await send_json(ws, {"type": "info", "seq": 0, "text": "connected"})
    
    # 创建或获取会话状态
    session_key = f"{session_id}_{source}"
    if session_key not in _sessions:
        state = SessionState(session_id, settings.ASR_SAMPLE_RATE, source)
        _sessions[session_key] = state
    else:
        state = _sessions[session_key]
        state.reset()
    
    # 创建ASR管道
    pipeline = ASRPipeline(state)
    
    # 系统音频相关
    system_audio_enabled = False
    loop = asyncio.get_running_loop()
    
    def system_audio_callback(audio_data: np.ndarray):
        """系统音频回调函数"""
        if state and not state.audio_q.full():
            try:
                asyncio.run_coroutine_threadsafe(
                    state.audio_q.put(audio_data),
                    loop
                )
            except Exception as e:
                logger.error(f"系统音频回调错误: {e}")
    
    # 部分结果回调
    async def on_partial(text: str, timestamp: float):
        """部分识别结果回调"""
        speaker = "interviewer" if source == "sys" else "user"
        
        # 发送WebSocket消息（部分结果）
        await send_json(ws, {
            "type": "partial",
            "seq": state.next_seq(),
            "text": text,
            "timestamp": timestamp
        })
        
        logger.debug(f"[ASR PARTIAL] ({speaker}) {text}")
    
    # 最终结果回调（带时间戳）
    async def on_final(text: str, start_time: float, end_time: float):
        """最终识别结果回调（面试场景特化：带时间戳和说话人标签）"""
        speaker = "interviewer" if source == "sys" else "user"
        timestamp = datetime.now().isoformat()
        
        # 保存transcript（带时间戳）
        try:
            message = ChatMessage(
                id=str(int(time.time() * 1000)),
                timestamp=timestamp,
                speaker=speaker,
                content=text,
                type="text",
            )
            await transcript_dao.save_transcript(
                session_id=session_id,
                speaker=speaker,
                content=text
            )
        except Exception as e:
            logger.error(f"保存transcript失败: {e}")
        
        # 发送WebSocket消息（带时间戳和说话人标签）
        await send_json(ws, {
            "type": "final",
            "seq": state.next_seq(),
            "text": text,
            "speaker": speaker,
            "start_time": start_time,
            "end_time": end_time,
            "timestamp": timestamp
        })
        
        logger.info(f"[ASR FINAL] ({speaker}) [{start_time:.2f}-{end_time:.2f}s] {text}")
    
    # 音频处理任务
    async def audio_processor():
        """音频处理协程"""
        try:
            while not state.stop:
                try:
                    pcm_chunk = await asyncio.wait_for(
                        state.audio_q.get(),
                        timeout=pipeline.chunk_timeout
                    )
                    try:
                        await pipeline.process_audio_chunk(
                            pcm_chunk,
                            on_partial=on_partial,
                            on_final=on_final
                        )
                    except Exception as e:
                        logger.error(f"处理音频块错误 (session={session_id}): {e}", exc_info=True)
                        # 继续处理下一块，不中断
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"音频处理循环错误 (session={session_id}): {e}", exc_info=True)
                    # 短暂等待后继续
                    await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"音频处理任务异常 (session={session_id}): {e}", exc_info=True)
        finally:
            # 刷新剩余音频
            try:
                await pipeline.flush(on_final=on_final)
            except Exception as e:
                logger.error(f"刷新音频缓冲区错误 (session={session_id}): {e}", exc_info=True)
            logger.info(f"[ASR STOP] Session {session_id} ({source})")
    
    processor_task: Optional[asyncio.Task] = None
    
    try:
        # 启动音频处理任务
        processor_task = asyncio.create_task(audio_processor())
        metrics.increment("ws_connections")
        
        # 处理WebSocket消息
        while True:
            try:
                msg = await ws.receive()
            except Exception as e:
                error_msg = str(e)
                if "disconnect" in error_msg.lower() or "closed" in error_msg.lower():
                    logger.info(f"WebSocket断开: {session_id} ({source})")
                else:
                    logger.error(f"WebSocket接收错误: {e}")
                break
            
            if "text" in msg:
                try:
                    data = json.loads(msg["text"])
                    
                    if data.get("type") == "start_system_audio" and source == "sys":
                        if not system_audio_enabled:
                            success = await asyncio.to_thread(
                                _start_system_audio_capture_sync,
                                system_audio_callback
                            )
                            if success:
                                system_audio_enabled = True
                                await send_json(ws, {
                                    "type": "info",
                                    "seq": 0,
                                    "text": "system audio started"
                                })
                            else:
                                await send_json(ws, {
                                    "type": "error",
                                    "seq": 0,
                                    "text": "failed to start system audio"
                                })
                    
                    elif data.get("type") == "stop_system_audio" and source == "sys":
                        if system_audio_enabled:
                            stop_system_audio_capture()
                            system_audio_enabled = False
                            await send_json(ws, {
                                "type": "info",
                                "seq": 0,
                                "text": "system audio stopped"
                            })
                    
                    elif data.get("type") == "stop":
                        state.stop = True
                        break
                
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析错误: {e}")
                    continue
            
            elif "bytes" in msg:
                # 处理音频数据（可能带元数据）
                b = msg["bytes"]
                
                # 检查是否有元数据头（至少 25 字节，实际 header 是 32 字节）
                if len(b) >= 25:
                    try:
                        # 解析元数据（使用 struct 更安全）
                        # 格式：seq(4) + t0(8) + sr(4) + channels(1) + frameCount(4) + rms(4) = 25字节
                        # header 实际是 32 字节（包含 7 字节 padding），音频数据从 32 字节开始
                        header_data = b[:25]
                        header = struct.unpack('<I d I B I f', header_data)
                        seq, t0, sr, channels, frame_count, rms = header
                        
                        # 提取音频数据（从 32 字节开始，跳过 padding）
                        if len(b) >= 32:
                            audio_data = b[32:]
                        else:
                            # 如果 header 不完整，从 25 字节开始
                            audio_data = b[25:]
                        logger.debug(f"收到带元数据的音频帧: seq={seq}, t0={t0:.3f}, sr={sr}, frames={frame_count}, rms={rms:.4f}")
                    except struct.error:
                        # 解析失败，当作旧格式处理
                        audio_data = b
                else:
                    # 旧格式：纯音频数据
                    audio_data = b
                
                if len(audio_data) % 2 != 0:
                    audio_data = audio_data[:-1]
                
                if len(audio_data) > 0:
                    pcm = np.frombuffer(audio_data, dtype=np.int16)
                    
                    # 背压控制：队列满时处理
                    if state.audio_q.full():
                        if settings.WS_AUDIO_QUEUE_DROP_OLDEST:
                            # 丢弃最旧的
                            try:
                                state.audio_q.get_nowait()
                                logger.warning(f"队列满，丢弃最旧音频块 (session={session_id})")
                            except asyncio.QueueEmpty:
                                pass
                        else:
                            # 或者等待
                            logger.warning(f"队列满，等待空间 (session={session_id})")
                    
                    await state.audio_q.put(pcm)
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket断开: {session_id} ({source})")
    except Exception as e:
        logger.error(f"WebSocket处理错误: {e}")
    
    finally:
        # 清理
        state.stop = True
        if system_audio_enabled:
            stop_system_audio_capture()
        if processor_task:
            processor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await processor_task
        
        # 从会话管理中移除
        if session_key in _sessions:
            del _sessions[session_key]
        
        metrics.increment("ws_disconnections")
        
        with contextlib.suppress(Exception):
            await ws.close()
        
        logger.info(f"[WS] closed: {session_id} ({source})")


def _start_system_audio_capture_sync(callback):
    """同步启动系统音频捕获"""
    try:
        from system_audio_capture import get_audio_capture
        capture = get_audio_capture()
        capture.add_callback("system_audio", callback)
        return capture.start_capture()
    except Exception as e:
        logger.error(f"启动系统音频失败: {e}")
        return False


def stop_system_audio_capture():
    """停止系统音频捕获"""
    try:
        from system_audio_capture import stop_system_audio_capture as _stop
        _stop()
    except Exception as e:
        logger.error(f"停止系统音频失败: {e}")

