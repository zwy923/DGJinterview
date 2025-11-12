import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { connectASRWebSocket, startSystemAudio, stopSystemAudio, stopWebSocket } from "../api/websocket";
import "./AudioRecognitionTest.css";

interface RecognitionResult {
  id: string;
  timestamp: string;
  source: "microphone" | "system";
  text: string;
  confidence?: number;
}

export default function AudioRecognitionTest() {
  const navigate = useNavigate();
  
  // 状态管理
  const [micRecording, setMicRecording] = useState(false);
  const [systemAudioEnabled, setSystemAudioEnabled] = useState(false);
  const [results, setResults] = useState<RecognitionResult[]>([]);
  const [error, setError] = useState<string>("");
  const [connectionStatus, setConnectionStatus] = useState<{
    mic: "未连接" | "连接中" | "已连接" | "错误";
    system: "未连接" | "连接中" | "已连接" | "错误";
  }>({ mic: "未连接", system: "未连接" });

  // 麦克风相关引用
  const micWsRef = useRef<WebSocket | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const micAudioContextRef = useRef<AudioContext | null>(null);

  // 系统音频相关引用
  const systemWsRef = useRef<WebSocket | null>(null);

  // 音频级别监控
  const [micLevel, setMicLevel] = useState(0);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);

  // ============================================
  // 麦克风音频识别
  // ============================================
  const startMicRecognition = async () => {
    try {
      setError("");
      setConnectionStatus(prev => ({ ...prev, mic: "连接中" }));
      console.log("🎤 开始麦克风音频识别测试...");

      // 获取麦克风权限
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      micStreamRef.current = stream;

      // 创建WebSocket连接（新接口：/ws/audio/{session_id}/mic）
      const testSessionId = `test_${Date.now()}`;
      micWsRef.current = connectASRWebSocket(testSessionId, "mic", {
        onFinal: (text) => {
          const result: RecognitionResult = {
            id: Date.now().toString(),
            timestamp: new Date().toLocaleTimeString(),
            source: "microphone",
            text: text,
          };
          setResults((prev) => [...prev, result]);
          console.log("🎤 麦克风识别结果:", text);
        },
        onInfo: (text) => {
          console.log("[mic] Info:", text);
          if (text.includes("connected")) {
            setConnectionStatus(prev => ({ ...prev, mic: "已连接" }));
          }
        },
        onError: (text) => {
          console.error("[mic] Error:", text);
          setConnectionStatus(prev => ({ ...prev, mic: "错误" }));
          setError(text);
        }
      });

      // WebSocket事件监听已在connectASRWebSocket中设置

      // 创建AudioContext处理音频数据
      const audioContext = new AudioContext({ sampleRate: 16000 });
      micAudioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      micProcessorRef.current = processor;

      // 创建音频分析器用于显示音频级别
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      micAnalyserRef.current = analyser;
      source.connect(analyser);

      // 创建静音的 GainNode 作为虚拟输出
      // ScriptProcessor 必须连接输出才能触发 onaudioprocess 事件
      // 通过 gain=0 确保不会播放声音
      const silentGain = audioContext.createGain();
      silentGain.gain.value = 0; // 设置为 0，完全静音
      processor.connect(silentGain);
      silentGain.connect(audioContext.destination);

      // 音频处理回调
      processor.onaudioprocess = (event) => {
        if (micWsRef.current?.readyState === WebSocket.OPEN) {
          const inputBuffer = event.inputBuffer;
          const inputData = inputBuffer.getChannelData(0);

          // 转换为16位PCM
          const pcmData = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            pcmData[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
          }

          // 发送PCM数据
          micWsRef.current.send(pcmData.buffer);
        }

        // 更新音频级别
        if (micAnalyserRef.current) {
          const dataArray = new Uint8Array(micAnalyserRef.current.frequencyBinCount);
          micAnalyserRef.current.getByteFrequencyData(dataArray);
          const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
          setMicLevel(average);
        }
      };

      source.connect(processor);
      // processor → silentGain → destination (静音输出，仅用于触发处理)

      setMicRecording(true);
      console.log("✅ 麦克风识别已启动");
    } catch (err) {
      console.error("麦克风启动失败:", err);
      setError(err instanceof Error ? err.message : "无法访问麦克风，请检查权限设置");
      setConnectionStatus(prev => ({ ...prev, mic: "错误" }));
    }
  };

  const stopMicRecognition = () => {
    console.log("🛑 停止麦克风识别");

    if (micProcessorRef.current) {
      micProcessorRef.current.disconnect();
      micProcessorRef.current = null;
    }

    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((track) => track.stop());
      micStreamRef.current = null;
    }

    if (micWsRef.current) {
      stopWebSocket(micWsRef.current);
      micWsRef.current = null;
    }

    if (micAudioContextRef.current) {
      micAudioContextRef.current.close();
      micAudioContextRef.current = null;
    }

    micAnalyserRef.current = null;
    setMicRecording(false);
    setMicLevel(0);
    setConnectionStatus(prev => ({ ...prev, mic: "未连接" }));
  };

  // ============================================
  // 系统音频识别
  // ============================================
  const startSystemAudioRecognition = async () => {
    try {
      setError("");
      setConnectionStatus(prev => ({ ...prev, system: "连接中" }));
      console.log("🔊 开始系统音频识别测试...");

      // 创建系统音频WebSocket连接（新接口：/ws/audio/{session_id}/sys）
      const testSessionId = `test_${Date.now()}`;
      systemWsRef.current = connectASRWebSocket(testSessionId, "sys", {
        onFinal: (text) => {
          const result: RecognitionResult = {
            id: Date.now().toString(),
            timestamp: new Date().toLocaleTimeString(),
            source: "system",
            text: text,
          };
          setResults((prev) => [...prev, result]);
          console.log("🔊 系统音频识别结果:", text);
        },
        onInfo: async (text) => {
          console.log("[sys] Info:", text);
          if (text.includes("connected")) {
            setConnectionStatus(prev => ({ ...prev, system: "连接中" }));
            
            // 等待连接建立后启动系统音频捕获
            const success = await startSystemAudio(systemWsRef.current!);
            if (success) {
              setSystemAudioEnabled(true);
              setConnectionStatus(prev => ({ ...prev, system: "已连接" }));
              console.log("✅ 系统音频识别已启动");
            } else {
              setError("系统音频启动失败，请检查后端服务");
              setConnectionStatus(prev => ({ ...prev, system: "错误" }));
            }
          }
        },
        onError: (text) => {
          console.error("[sys] Error:", text);
          setConnectionStatus(prev => ({ ...prev, system: "错误" }));
          setError(text);
        }
      });
    } catch (err) {
      console.error("系统音频启动失败:", err);
      setError(err instanceof Error ? err.message : "系统音频启动失败");
      setConnectionStatus(prev => ({ ...prev, system: "错误" }));
    }
  };

  const stopSystemAudioRecognition = async () => {
    console.log("🛑 停止系统音频识别");

    if (systemWsRef.current) {
      await stopSystemAudio(systemWsRef.current);
      stopWebSocket(systemWsRef.current);
      systemWsRef.current = null;
    }

    setSystemAudioEnabled(false);
    setConnectionStatus(prev => ({ ...prev, system: "未连接" }));
  };

  // ============================================
  // 清理和工具函数
  // ============================================
  const clearResults = () => {
    setResults([]);
  };

  const exportResults = () => {
    const dataStr = JSON.stringify(results, null, 2);
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `audio-recognition-test-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // 清理资源
  useEffect(() => {
    return () => {
      if (micRecording) {
        stopMicRecognition();
      }
      if (systemAudioEnabled) {
        stopSystemAudioRecognition();
      }
    };
  }, []);

  return (
    <div className="audio-recognition-test">
      <div className="test-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <div>
            <h2>🎧 音频识别测试模块</h2>
            <p className="test-description">
              测试麦克风音频识别和系统音频识别功能
            </p>
          </div>
          <button
            className="btn btn-small"
            onClick={() => navigate('/')}
            style={{ background: '#6b7280', marginTop: '0' }}
          >
            ← 返回主页
          </button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="error-message">
          <span>⚠️</span>
          <span>{error}</span>
          <button onClick={() => setError("")}>×</button>
        </div>
      )}

      {/* 控制面板 */}
      <div className="control-panel">
        {/* 麦克风控制 */}
        <div className="control-section">
          <h3>🎤 麦克风音频识别</h3>
          <div className="control-buttons">
            {!micRecording ? (
              <button
                className="btn btn-primary"
                onClick={startMicRecognition}
              >
                开始麦克风识别
              </button>
            ) : (
              <button
                className="btn btn-danger"
                onClick={stopMicRecognition}
              >
                停止麦克风识别
              </button>
            )}
          </div>
          <div className="status-info">
            <span className={`status-badge ${connectionStatus.mic === "已连接" ? "connected" : ""}`}>
              {connectionStatus.mic}
            </span>
            {micRecording && (
              <div className="audio-level">
                <span>音频级别:</span>
                <div className="level-bar">
                  <div
                    className="level-fill"
                    style={{ width: `${micLevel}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 系统音频控制 */}
        <div className="control-section">
          <h3>🔊 系统音频识别</h3>
          <div className="control-buttons">
            {!systemAudioEnabled ? (
              <button
                className="btn btn-secondary"
                onClick={startSystemAudioRecognition}
              >
                开始系统音频识别
              </button>
            ) : (
              <button
                className="btn btn-danger"
                onClick={stopSystemAudioRecognition}
              >
                停止系统音频识别
              </button>
            )}
          </div>
          <div className="status-info">
            <span className={`status-badge ${connectionStatus.system === "已连接" ? "connected" : ""}`}>
              {connectionStatus.system}
            </span>
            <p className="status-hint">
              系统音频由后端捕获，无需浏览器权限
            </p>
          </div>
        </div>
      </div>

      {/* 识别结果 */}
      <div className="results-panel">
        <div className="results-header">
          <h3>📝 识别结果 ({results.length})</h3>
          <div className="results-actions">
            <button
              className="btn btn-small"
              onClick={clearResults}
              disabled={results.length === 0}
            >
              清空结果
            </button>
            <button
              className="btn btn-small"
              onClick={exportResults}
              disabled={results.length === 0}
            >
              导出JSON
            </button>
          </div>
        </div>

        <div className="results-list">
          {results.length === 0 ? (
            <div className="empty-results">
              <p>暂无识别结果</p>
              <p className="hint">开始识别后，结果将显示在这里</p>
            </div>
          ) : (
            results.map((result) => (
              <div
                key={result.id}
                className={`result-item ${result.source}`}
              >
                <div className="result-header">
                  <span className="result-source">
                    {result.source === "microphone" ? "🎤" : "🔊"}
                    {result.source === "microphone" ? "麦克风" : "系统音频"}
                  </span>
                  <span className="result-time">{result.timestamp}</span>
                </div>
                <div className="result-text">{result.text}</div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 使用说明 */}
      <div className="instructions">
        <h4>📖 使用说明</h4>
        <ul>
          <li>
            <strong>麦克风识别：</strong>点击"开始麦克风识别"按钮，允许浏览器访问麦克风权限后开始识别
          </li>
          <li>
            <strong>系统音频识别：</strong>点击"开始系统音频识别"按钮，后端将捕获系统音频（需要后端支持）
          </li>
          <li>
            <strong>识别结果：</strong>识别到的文本会实时显示在结果列表中
          </li>
          <li>
            <strong>导出结果：</strong>可以导出所有识别结果为JSON文件
          </li>
        </ul>
      </div>
    </div>
  );
}

