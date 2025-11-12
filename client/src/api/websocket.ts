/**
 * WebSocket API - 适配新架构
 * 新接口: /ws/audio/{session_id}/{source}
 */

export interface WSMessage {
  type: "info" | "final" | "partial" | "error";
  seq: number;
  text: string;
  confidence?: number;
}

export interface WSMessageHandler {
  onFinal?: (text: string, seq: number, confidence?: number) => void;
  onPartial?: (text: string, seq: number) => void;
  onInfo?: (text: string, seq: number) => void;
  onError?: (text: string, seq: number) => void;
}

/**
 * 连接ASR WebSocket
 * 
 * @param sessionId 会话ID
 * @param source 音频源: "mic" | "sys"
 * @param handlers 消息处理器
 * @returns WebSocket连接
 */
export function connectASRWebSocket(
  sessionId: string,
  source: "mic" | "sys",
  handlers: WSMessageHandler
): WebSocket {
  const url = `ws://${window.location.hostname}:8000/ws/audio/${sessionId}/${source}`;
  const ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    console.log(`[${source}] WebSocket connected: ${sessionId}`);
  };

  ws.onmessage = (event) => {
    try {
      const msg: WSMessage = JSON.parse(event.data);
      
      switch (msg.type) {
        case "final":
          if (handlers.onFinal) {
            handlers.onFinal(msg.text, msg.seq, msg.confidence);
          }
          break;
        case "partial":
          if (handlers.onPartial) {
            handlers.onPartial(msg.text, msg.seq);
          }
          break;
        case "info":
          if (handlers.onInfo) {
            handlers.onInfo(msg.text, msg.seq);
          }
          console.log(`[${source}] Info:`, msg.text);
          break;
        case "error":
          if (handlers.onError) {
            handlers.onError(msg.text, msg.seq);
          }
          console.error(`[${source}] Error:`, msg.text);
          break;
      }
    } catch (error) {
      console.log(`[${source}] Received non-JSON data:`, event.data);
    }
  };

  ws.onclose = (event) => {
    console.log(`[${source}] WebSocket closed:`, event.code, event.reason);
  };

  ws.onerror = (error) => {
    console.error(`[${source}] WebSocket error:`, error);
  };

  return ws;
}

/**
 * 启动系统音频捕获（仅用于source="sys"的连接）
 * 
 * @param ws WebSocket连接
 * @returns Promise<boolean>
 */
export function startSystemAudio(ws: WebSocket): Promise<boolean> {
  return new Promise((resolve) => {
    if (ws.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket未连接，无法启动系统音频");
      resolve(false);
      return;
    }

    const originalOnMessage = ws.onmessage;
    let resolved = false;
    
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "info" && msg.text === "system audio started") {
          if (!resolved) {
            resolved = true;
            resolve(true);
          }
        } else if (msg.type === "error" && msg.text.includes("system audio")) {
          if (!resolved) {
            resolved = true;
            resolve(false);
          }
        }
      } catch (error) {
        console.log("Received non-JSON data:", event.data);
      }
      
      // 调用原始消息处理器
      if (originalOnMessage) {
        originalOnMessage.call(ws, event);
      }
    };
    
    try {
      ws.send(JSON.stringify({ type: "start_system_audio" }));
      
      // 设置超时
      setTimeout(() => {
        if (!resolved) {
          resolved = true;
          resolve(false);
        }
      }, 5000);
    } catch (error) {
      console.error("Failed to send start_system_audio message:", error);
      if (!resolved) {
        resolved = true;
        resolve(false);
      }
    }
  });
}

/**
 * 停止系统音频捕获
 * 
 * @param ws WebSocket连接
 * @returns Promise<boolean>
 */
export function stopSystemAudio(ws: WebSocket): Promise<boolean> {
  return new Promise((resolve) => {
    if (ws.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket未连接，无法停止系统音频");
      resolve(false);
      return;
    }

    const originalOnMessage = ws.onmessage;
    let resolved = false;
    
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "info" && msg.text === "system audio stopped") {
          if (!resolved) {
            resolved = true;
            resolve(true);
          }
        }
      } catch (error) {
        console.log("Received non-JSON data:", event.data);
      }
      
      // 调用原始消息处理器
      if (originalOnMessage) {
        originalOnMessage.call(ws, event);
      }
    };
    
    try {
      ws.send(JSON.stringify({ type: "stop_system_audio" }));
      
      // 设置超时
      setTimeout(() => {
        if (!resolved) {
          resolved = true;
          resolve(true); // 即使没有收到确认，也认为成功
        }
      }, 2000);
    } catch (error) {
      console.error("Failed to send stop_system_audio message:", error);
      if (!resolved) {
        resolved = true;
        resolve(false);
      }
    }
  });
}

/**
 * 停止WebSocket连接
 * 
 * @param ws WebSocket连接
 */
export function stopWebSocket(ws: WebSocket): void {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: "stop" }));
    } catch (error) {
      console.error("Failed to send stop message:", error);
    }
  }
  
  if (ws) {
    ws.close();
  }
}
