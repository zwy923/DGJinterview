import { useState, useRef, useEffect } from "react";
import { connectASRWebSocket, startSystemAudio, stopSystemAudio, stopWebSocket } from "../api/websocket";
import AudioTestPanel from "./AudioTestPanel";
import AudioLevelMeter from "./AudioLevelMeter";
import { AudioWorkletManager } from "../audio/audioWorkletManager";

interface Props {
  onUserText: (text: string, isPartial?: boolean) => void;
  onInterviewerText: (text: string, isPartial?: boolean) => void;
  sessionId?: string; // 会话ID
}

export default function AudioController({ onUserText, onInterviewerText, sessionId = "default" }: Props) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string>("");
  const [connectionStatus, setConnectionStatus] = useState<string>("未连接");
  const [systemAudioEnabled, setSystemAudioEnabled] = useState(false);
  const [showTestPanel, setShowTestPanel] = useState(false);
  const [systemStream, setSystemStream] = useState<MediaStream | null>(null);
  // 用户麦克风相关
  const userWsRef = useRef<WebSocket | null>(null);
  const userStreamRef = useRef<MediaStream | null>(null);
  const userWorkletManagerRef = useRef<AudioWorkletManager | null>(null);
  const userProcessorRef = useRef<ScriptProcessorNode | null>(null); // 降级模式使用
  const userAudioContextRef = useRef<AudioContext | null>(null); // 降级模式使用
  
  // 系统音频WebSocket连接
  const systemWsRef = useRef<WebSocket | null>(null);

  // 启动用户麦克风录音
  const startUserAudio = async () => {
    try {
      console.log("🎤 开始捕获用户麦克风...");
      
      // 获取麦克风权限（与测试保持一致）
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true // 与测试保持一致，使用 AGC
        }
      });
      
      userStreamRef.current = stream;
      
      // 创建WebSocket连接（新接口：/ws/audio/{session_id}/mic）
      userWsRef.current = connectASRWebSocket(sessionId, "mic", {
        onFinal: (text) => {
          onUserText(text, false);
        },
        onPartial: (text) => {
          // 部分结果用于实时显示（斜体或灰色）
          onUserText(text, true);
        },
        onInfo: (text) => {
          console.log("[mic] Info:", text);
          if (text.includes("connected")) {
            setConnectionStatus("已连接 - 识别中");
          }
        },
        onError: (text) => {
          console.error("[mic] Error:", text);
          setError(text);
        }
      });
      
      // 使用 AudioWorklet 替代 ScriptProcessor
      // 如果 AudioWorklet 加载失败，可以降级到 ScriptProcessor
      let workletManager: AudioWorkletManager | null = null;
      try {
        workletManager = new AudioWorkletManager();
        await workletManager.initialize(stream, {
        onAudioFrame: (data, metadata) => {
          // 发送音频帧（带元数据）
          if (userWsRef.current?.readyState === WebSocket.OPEN) {
            try {
              // 创建带元数据的消息
              // 格式：seq(4) + t0(8) + sr(4) + channels(1) + frameCount(4) + rms(4) = 25字节
              // 使用 32 字节对齐，便于后续扩展
              const header = new ArrayBuffer(32);
              const view = new DataView(header);
              let offset = 0;
              view.setUint32(offset, metadata.seq, true); offset += 4;
              view.setFloat64(offset, metadata.t0, true); offset += 8;
              view.setUint32(offset, metadata.sr, true); offset += 4;
              view.setUint8(offset, metadata.channels); offset += 1;
              view.setUint32(offset, metadata.frameCount, true); offset += 4;
              if (metadata.rms !== undefined) {
                view.setFloat32(offset, metadata.rms, true); offset += 4;
              }
              // offset 现在应该是 25，剩余 7 字节为 padding（自动为 0）
              
              // 合并 header 和音频数据
              const combined = new Uint8Array(header.byteLength + data.byteLength);
              combined.set(new Uint8Array(header), 0);
              combined.set(new Uint8Array(data), header.byteLength);
              
              // 检查 WebSocket 缓冲状态（避免阻塞）
              if (userWsRef.current.bufferedAmount > 1024 * 1024) { // 1MB
                console.warn('[Audio] WebSocket buffer full, dropping frame');
                return;
              }
              
              userWsRef.current.send(combined.buffer);
            } catch (error) {
              console.error('[Audio] Failed to send audio frame:', error);
              // 不抛出错误，继续处理下一帧
            }
          }
        },
        onError: (error) => {
          console.error("AudioWorklet error:", error);
          setError(`音频处理错误: ${error.message}`);
        }
      });
      
      userWorkletManagerRef.current = workletManager;
      console.log("✅ 用户麦克风已启动（AudioWorklet）");
      } catch (workletError) {
        console.warn("AudioWorklet 初始化失败，降级到 ScriptProcessor（与测试逻辑一致）:", workletError);
        // 降级到 ScriptProcessor（与测试逻辑完全一致）
        const audioContext = new AudioContext({ sampleRate: 16000 });
        userAudioContextRef.current = audioContext;
        const source = audioContext.createMediaStreamSource(stream);
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        userProcessorRef.current = processor;
        
        // 创建静音的 GainNode（ScriptProcessor 必须连接输出才能工作）
        const silentGain = audioContext.createGain();
        silentGain.gain.value = 0;
        processor.connect(silentGain);
        silentGain.connect(audioContext.destination);
        
        processor.onaudioprocess = (event) => {
          if (userWsRef.current?.readyState === WebSocket.OPEN) {
            try {
              const inputData = event.inputBuffer.getChannelData(0);
              // 转换为16位PCM（与测试逻辑一致）
              const pcmData = new Int16Array(inputData.length);
              for (let i = 0; i < inputData.length; i++) {
                pcmData[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
              }
              // 直接发送 PCM 数据（无元数据头，与测试一致）
              userWsRef.current.send(pcmData.buffer);
            } catch (error) {
              console.error('[Audio] ScriptProcessor send error:', error);
            }
          }
        };
        
        source.connect(processor);
        userWorkletManagerRef.current = null; // 标记使用 ScriptProcessor
        console.log("✅ 用户麦克风已启动（ScriptProcessor 降级模式，与测试一致）");
      }
      
    } catch (err) {
      console.error("用户麦克风启动失败:", err);
      throw new Error("无法访问麦克风，请检查权限设置");
    }
  };

  // 启动系统音频（通过后端）
  const startSystemAudioCapture = async () => {
    try {
      console.log("🔊 启动后端系统音频捕获...");
      
      // 创建系统音频WebSocket连接（新接口：/ws/audio/{session_id}/sys）
      systemWsRef.current = connectASRWebSocket(sessionId, "sys", {
        onFinal: (text) => {
          onInterviewerText(text, false);
        },
        onPartial: (text) => {
          // 部分结果用于实时显示
          onInterviewerText(text, true);
        },
        onInfo: (text) => {
          console.log("[sys] Info:", text);
        },
        onError: (text) => {
          console.error("[sys] Error:", text);
          setError(text);
        }
      });
      
      // 等待WebSocket连接建立
      await new Promise((resolve, reject) => {
        if (systemWsRef.current) {
          systemWsRef.current.onopen = resolve;
          systemWsRef.current.onerror = reject;
          // 设置超时
          setTimeout(() => reject(new Error("连接超时")), 5000);
        }
      });
      
      // 启动后端系统音频捕获
      const success = await startSystemAudio(systemWsRef.current!);
      if (!success) {
        throw new Error("后端系统音频启动失败");
      }
      
      console.log("✅ 系统音频已启动");
      
      // 为了显示音频级别，我们也需要获取系统音频流
      try {
        const systemStream = await navigator.mediaDevices.getDisplayMedia({
          audio: true,
          video: false
        });
        setSystemStream(systemStream);
      } catch (err) {
        console.warn("无法获取系统音频流用于显示:", err);
      }
      
    } catch (err) {
      console.error("系统音频启动失败:", err);
      throw new Error("系统音频启动失败，请检查后端服务");
    }
  };

  // 启动麦克风录音
  const startMic = async () => {
    try {
      setError("");
      console.log("🎤 开始捕获麦克风...");
      
      await startUserAudio();
      
      setConnectionStatus("已连接 - 识别中");
      setRecording(true);
      
    } catch (err) {
      console.error("麦克风启动失败:", err);
      setError(err instanceof Error ? err.message : "麦克风启动失败");
    }
  };

  // 停止麦克风录音
  const stopMic = () => {
    console.log("🛑 停止麦克风录音");
    
    // 停止用户音频处理（AudioWorklet 或 ScriptProcessor）
    if (userWorkletManagerRef.current) {
      userWorkletManagerRef.current.stop();
      userWorkletManagerRef.current = null;
    }
    
    // 清理 ScriptProcessor 降级模式
    if (userProcessorRef.current) {
      userProcessorRef.current.disconnect();
      userProcessorRef.current = null;
    }
    
    if (userAudioContextRef.current) {
      userAudioContextRef.current.close();
      userAudioContextRef.current = null;
    }
    
    if (userStreamRef.current) {
      userStreamRef.current.getTracks().forEach(track => track.stop());
      userStreamRef.current = null;
    }
    
    if (userWsRef.current) {
      stopWebSocket(userWsRef.current);
      userWsRef.current = null;
    }
    
    setRecording(false);
    if (!systemAudioEnabled) {
      setConnectionStatus("未连接");
    }
  };

  // 启动系统音频
  const startSystem = async () => {
    try {
      setError("");
      console.log("🔊 启动系统音频...");
      
      await startSystemAudioCapture();
      setSystemAudioEnabled(true);
      console.log("✅ 系统音频已启动");
      
    } catch (err) {
      console.error("系统音频启动失败:", err);
      setError(err instanceof Error ? err.message : "系统音频启动失败，请检查后端服务");
    }
  };

  // 停止系统音频
  const stopSystem = () => {
    console.log("🛑 停止系统音频");
    
    if (systemWsRef.current) {
      stopSystemAudio(systemWsRef.current).then(() => {
        stopWebSocket(systemWsRef.current!);
        systemWsRef.current = null;
      });
    }
    
    if (systemStream) {
      systemStream.getTracks().forEach(track => track.stop());
      setSystemStream(null);
    }
    
    setSystemAudioEnabled(false);
    if (!recording) {
      setConnectionStatus("未连接");
    }
  };



  // 清理资源
  useEffect(() => {
    return () => {
      if (recording) {
        stopMic();
      }
      if (systemAudioEnabled) {
        stopSystem();
      }
    };
  }, []);

  return (
    <div className="mt-6 flex flex-col gap-4">
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200 shadow-inner">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          onClick={recording ? stopMic : startMic}
          className={`rounded-xl bg-gradient-to-r px-5 py-2.5 text-sm font-semibold text-white shadow-lg transition duration-200 hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-primary/60 ${
            recording
              ? 'from-rose-500 to-rose-600'
              : 'from-emerald-500 to-emerald-600'
          }`}
        >
          {recording ? '⏹ 停止麦克风' : '🎤 开始麦克风'}
        </button>

        <button
          onClick={systemAudioEnabled ? stopSystem : startSystem}
          className={`rounded-xl bg-gradient-to-r px-5 py-2.5 text-sm font-semibold text-white shadow-lg transition duration-200 hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-primary/60 ${
            systemAudioEnabled
              ? 'from-rose-500 to-rose-600'
              : 'from-brand-primary to-brand-secondary'
          }`}
        >
          {systemAudioEnabled ? '⏹ 停止系统音频' : '🔊 开始系统音频'}
        </button>

        <button
          type="button"
          onClick={() => setShowTestPanel(true)}
          className="rounded-xl border border-slate-700 bg-slate-900/70 px-5 py-2.5 text-sm font-semibold text-slate-200 shadow-lg transition duration-200 hover:-translate-y-0.5 hover:border-brand-primary/60 hover:text-brand-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-primary/60"
        >
          🎧 音频测试
        </button>
      </div>

      {(recording || systemAudioEnabled) && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="mb-3 text-center text-sm font-semibold text-slate-200">
            📊 实时音频监控
          </div>

          {recording && (
            <AudioLevelMeter
              stream={userStreamRef.current}
              label="🎤 麦克风"
              color="#10b981"
              isActive={recording}
            />
          )}

          {systemAudioEnabled && (
            <AudioLevelMeter
              stream={systemStream}
              label="🔊 系统音频"
              color="#8b5cf6"
              isActive={systemAudioEnabled}
            />
          )}
        </div>
      )}

      <div className="text-center text-xs text-slate-400">
        <div className="mb-1">
          状态:
          <span
            className={`ml-1 font-semibold ${
              connectionStatus.includes('已连接')
                ? 'text-emerald-400'
                : connectionStatus.includes('错误')
                  ? 'text-rose-400'
                  : 'text-amber-400'
            }`}
          >
            {connectionStatus}
          </span>
        </div>
        <div className="mb-1">
          麦克风:
          <span className={`ml-1 font-semibold ${recording ? 'text-emerald-400' : 'text-amber-400'}`}>
            {recording ? '✓ 已启用' : '✗ 未启用'}
          </span>
        </div>
        <div className="mb-2">
          系统音频:
          <span className={`ml-1 font-semibold ${systemAudioEnabled ? 'text-emerald-400' : 'text-amber-400'}`}>
            {systemAudioEnabled ? '✓ 已启用' : '✗ 未启用'}
          </span>
        </div>
        <div className="text-slate-500">
          {recording || systemAudioEnabled
            ? recording && systemAudioEnabled
              ? '正在录音中，同时捕获您和面试官的声音...'
              : recording
                ? '正在录音中，仅捕获您的声音'
                : '正在录音中，仅捕获面试官的声音'
            : '点击按钮开始录音，可分别控制麦克风和系统音频'}
        </div>
      </div>

      {showTestPanel && (
        <AudioTestPanel onClose={() => setShowTestPanel(false)} />
      )}
    </div>
  );
}