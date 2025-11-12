import { useState, useRef, useEffect } from "react";

interface AudioTestPanelProps {
  onClose: () => void;
}

interface AudioDevice {
  deviceId: string;
  label: string;
  kind: string;
}

export default function AudioTestPanel({ onClose }: AudioTestPanelProps) {
  const [isVisible, setIsVisible] = useState(true);
  const [micLevel, setMicLevel] = useState(0);
  const [systemLevel, setSystemLevel] = useState(0);
  const [micDevices, setMicDevices] = useState<AudioDevice[]>([]);
  const [selectedMicDevice, setSelectedMicDevice] = useState<string>("");
  const [micTestActive, setMicTestActive] = useState(false);
  const [systemTestActive, setSystemTestActive] = useState(false);
  const [error, setError] = useState<string>("");

  // 音频流引用
  const micStreamRef = useRef<MediaStream | null>(null);
  const systemStreamRef = useRef<MediaStream | null>(null);
  const micAudioContextRef = useRef<AudioContext | null>(null);
  const systemAudioContextRef = useRef<AudioContext | null>(null);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const systemAnalyserRef = useRef<AnalyserNode | null>(null);
  const micAnimationRef = useRef<number | null>(null);
  const systemAnimationRef = useRef<number | null>(null);

  // 获取音频设备列表
  useEffect(() => {
    const getAudioDevices = async () => {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const audioInputs = devices
          .filter(device => device.kind === 'audioinput')
          .map(device => ({
            deviceId: device.deviceId,
            label: device.label || `麦克风 ${device.deviceId.slice(0, 8)}`,
            kind: device.kind
          }));
        
        setMicDevices(audioInputs);
        
      } catch (err) {
        console.error("获取音频设备失败:", err);
        setError("无法获取音频设备列表");
      }
    };

    getAudioDevices();
  }, []);

  // 麦克风测试
  const startMicTest = async () => {
    try {
      setError("");
      
      // 停止之前的测试
      stopMicTest();
      
      const constraints: MediaStreamConstraints = {
        audio: {
          deviceId: selectedMicDevice ? { exact: selectedMicDevice } : undefined,
          sampleRate: 44100,
          channelCount: 1,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false
        }
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      micStreamRef.current = stream;

      // 创建音频上下文和分析器
      const audioContext = new AudioContext();
      micAudioContextRef.current = audioContext;
      
      // 确保音频上下文处于运行状态
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }
      
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      
      micAnalyserRef.current = analyser;
      source.connect(analyser);

      // 开始音频分析
      setMicTestActive(true);
      startMicLevelMonitoring();
      
    } catch (err) {
      console.error("麦克风测试启动失败:", err);
      setError(`麦克风测试失败: ${err instanceof Error ? err.message : '未知错误'}`);
    }
  };

  const stopMicTest = () => {
    if (micAnimationRef.current) {
      cancelAnimationFrame(micAnimationRef.current);
      micAnimationRef.current = null;
    }
    
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach(track => track.stop());
      micStreamRef.current = null;
    }
    
    if (micAudioContextRef.current) {
      micAudioContextRef.current.close();
      micAudioContextRef.current = null;
    }
    
    setMicTestActive(false);
    setMicLevel(0);
  };

  // 系统音频测试
  const startSystemTest = async () => {
    try {
      setError("");
      
      // 停止之前的测试
      stopSystemTest();
      
      // 获取屏幕共享音频
      const stream = await navigator.mediaDevices.getDisplayMedia({
        audio: {
          sampleRate: 44100,
          channelCount: 1,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false
        },
        video: false
      });

      // 检查是否有音频轨道
      const audioTracks = stream.getAudioTracks();
      if (audioTracks.length === 0) {
        throw new Error("未检测到音频轨道，请确保选择了包含音频的屏幕或应用程序");
      }

      systemStreamRef.current = stream;

      // 创建音频上下文和分析器
      const audioContext = new AudioContext();
      systemAudioContextRef.current = audioContext;
      
      // 确保音频上下文处于运行状态
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }
      
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      
      systemAnalyserRef.current = analyser;
      source.connect(analyser);

      // 开始音频分析
      setSystemTestActive(true);
      startSystemLevelMonitoring();
      
    } catch (err) {
      console.error("系统音频测试启动失败:", err);
      setError(`系统音频测试失败: ${err instanceof Error ? err.message : '未知错误'}`);
    }
  };

  const stopSystemTest = () => {
    if (systemAnimationRef.current) {
      cancelAnimationFrame(systemAnimationRef.current);
      systemAnimationRef.current = null;
    }
    
    if (systemStreamRef.current) {
      systemStreamRef.current.getTracks().forEach(track => track.stop());
      systemStreamRef.current = null;
    }
    
    if (systemAudioContextRef.current) {
      systemAudioContextRef.current.close();
      systemAudioContextRef.current = null;
    }
    
    setSystemTestActive(false);
    setSystemLevel(0);
  };

  // 麦克风音频级别监控
  const startMicLevelMonitoring = () => {
    const analyser = micAnalyserRef.current;
    if (!analyser) {
      console.error("麦克风分析器未初始化");
      return;
    }

    console.log("开始麦克风音频级别监控");
    
    const updateLevel = () => {
      if (!micAnalyserRef.current) {
        console.log("麦克风分析器已销毁，停止监控");
        return;
      }
      
      // 同时使用时域和频域数据，获得更好的灵敏度
      const timeData = new Uint8Array(analyser.frequencyBinCount);
      const freqData = new Uint8Array(analyser.frequencyBinCount);
      
      micAnalyserRef.current.getByteTimeDomainData(timeData);
      micAnalyserRef.current.getByteFrequencyData(freqData);
      
      // 计算时域峰值和RMS
      let timeSum = 0;
      let timePeak = 0;
      for (let i = 0; i < timeData.length; i++) {
        const normalized = Math.abs((timeData[i] - 128) / 128);
        timeSum += normalized * normalized;
        timePeak = Math.max(timePeak, normalized);
      }
      const timeRms = Math.sqrt(timeSum / timeData.length);
      
      // 计算频域平均音量
      const freqAverage = freqData.reduce((sum, value) => sum + value, 0) / freqData.length;
      const freqLevel = freqAverage / 255;
      
      // 组合时域和频域数据
      const timeLevel = Math.max(timeRms, timePeak * 0.8);
      const combinedLevel = Math.max(timeLevel, freqLevel * 0.5);
      
      // 大幅放大音量显示
      const amplifiedLevel = Math.min(100, combinedLevel * 800); // 进一步增加到800倍
      
      // 使用立方根缩放，使低音量更明显
      const cubeLevel = Math.pow(amplifiedLevel, 1/3) * 15;
      const level = Math.max(0, Math.min(100, cubeLevel));
      
      setMicLevel(level);
      
      // 调试信息（仅在开发环境）
      if (level > 0) {
        console.log(`麦克风音量: ${level.toFixed(1)}%`);
      }
      
      // 继续监控
      micAnimationRef.current = requestAnimationFrame(updateLevel);
    };
    
    updateLevel();
  };

  // 系统音频级别监控
  const startSystemLevelMonitoring = () => {
    const analyser = systemAnalyserRef.current;
    if (!analyser) {
      console.error("系统音频分析器未初始化");
      return;
    }

    console.log("开始系统音频级别监控");
    
    const updateLevel = () => {
      if (!systemAnalyserRef.current) {
        console.log("系统音频分析器已销毁，停止监控");
        return;
      }
      
      // 同时使用时域和频域数据，获得更好的灵敏度
      const timeData = new Uint8Array(analyser.frequencyBinCount);
      const freqData = new Uint8Array(analyser.frequencyBinCount);
      
      systemAnalyserRef.current.getByteTimeDomainData(timeData);
      systemAnalyserRef.current.getByteFrequencyData(freqData);
      
      // 计算时域峰值和RMS
      let timeSum = 0;
      let timePeak = 0;
      for (let i = 0; i < timeData.length; i++) {
        const normalized = Math.abs((timeData[i] - 128) / 128);
        timeSum += normalized * normalized;
        timePeak = Math.max(timePeak, normalized);
      }
      const timeRms = Math.sqrt(timeSum / timeData.length);
      
      // 计算频域平均音量
      const freqAverage = freqData.reduce((sum, value) => sum + value, 0) / freqData.length;
      const freqLevel = freqAverage / 255;
      
      // 组合时域和频域数据
      const timeLevel = Math.max(timeRms, timePeak * 0.8);
      const combinedLevel = Math.max(timeLevel, freqLevel * 0.5);
      
      // 大幅放大音量显示
      const amplifiedLevel = Math.min(100, combinedLevel * 800); // 进一步增加到800倍
      
      // 使用立方根缩放，使低音量更明显
      const cubeLevel = Math.pow(amplifiedLevel, 1/3) * 15;
      const level = Math.max(0, Math.min(100, cubeLevel));
      
      setSystemLevel(level);
      
      // 调试信息（仅在开发环境）
      if (level > 0) {
        console.log(`系统音频音量: ${level.toFixed(1)}%`);
      }
      
      // 继续监控
      systemAnimationRef.current = requestAnimationFrame(updateLevel);
    };
    
    updateLevel();
  };

  // 清理资源
  useEffect(() => {
    return () => {
      stopMicTest();
      stopSystemTest();
    };
  }, []);

  // 音量条组件
  const VolumeBar = ({ level, color, label }: { level: number; color: string; label: string }) => (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '0.5rem'
      }}>
        <span style={{ fontSize: '0.875rem', fontWeight: '500' }}>{label}</span>
        <span style={{ 
          fontSize: '0.75rem', 
          color: level > 10 ? '#10b981' : '#6b7280',
          fontWeight: level > 10 ? '600' : '400'
        }}>
          {Math.round(level)}%
        </span>
      </div>
      <div style={{
        width: '100%',
        height: '12px',
        backgroundColor: '#e5e7eb',
        borderRadius: '6px',
        overflow: 'hidden',
        position: 'relative',
        border: '1px solid #d1d5db'
      }}>
        <div style={{
          width: `${Math.max(2, level)}%`, // 最小显示2%宽度
          height: '100%',
          background: level > 20 ? 
            `linear-gradient(90deg, ${color}, ${color}cc)` : 
            `linear-gradient(90deg, #f59e0b, #f59e0bcc)`,
          borderRadius: '5px',
          transition: 'width 0.1s ease-out, background 0.2s ease-out',
          boxShadow: level > 10 ? `0 0 6px ${color}60` : 'none',
          position: 'relative'
        }}>
          {/* 添加动态效果 */}
          {level > 5 && (
            <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: `linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent)`,
              animation: 'shimmer 1.5s infinite'
            }} />
          )}
        </div>
      </div>
      {/* 添加音量指示器 */}
      <div style={{
        fontSize: '0.625rem',
        color: level > 10 ? '#10b981' : '#9ca3af',
        marginTop: '0.25rem',
        textAlign: 'center'
      }}>
        {level > 10 ? '✅ 音频正常' : level > 2 ? '⚠️ 音量较低' : '❌ 无音频输入'}
      </div>
    </div>
  );

  if (!isVisible) return null;

  return (
    <>
      <style>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}>
      <div style={{
        backgroundColor: 'white',
        borderRadius: '0.75rem',
        padding: '1.5rem',
        maxWidth: '500px',
        width: '90%',
        maxHeight: '80vh',
        overflow: 'auto',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)'
      }}>
        {/* 标题栏 */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.5rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid #e5e7eb'
        }}>
          <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: '600', color: '#111827' }}>
            🎵 音频输入测试
          </h3>
          <button
            onClick={() => {
              setIsVisible(false);
              onClose();
            }}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '1.5rem',
              cursor: 'pointer',
              color: '#6b7280',
              padding: '0.25rem'
            }}
          >
            ×
          </button>
        </div>

        {error && (
          <div style={{
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#dc2626',
            padding: '0.75rem',
            borderRadius: '0.5rem',
            marginBottom: '1rem',
            fontSize: '0.875rem'
          }}>
            {error}
          </div>
        )}

        {/* 麦克风测试 */}
        <div style={{ marginBottom: '2rem' }}>
          <h4 style={{ margin: '0 0 1rem 0', fontSize: '1rem', fontWeight: '600', color: '#374151' }}>
            🎤 麦克风测试
          </h4>
          
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: '500', marginBottom: '0.5rem' }}>
              选择麦克风设备:
            </label>
            <select
              value={selectedMicDevice}
              onChange={(e) => setSelectedMicDevice(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                border: '1px solid #d1d5db',
                borderRadius: '0.375rem',
                fontSize: '0.875rem'
              }}
            >
              <option value="">默认麦克风</option>
              {micDevices.map(device => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label}
                </option>
              ))}
            </select>
          </div>

          <VolumeBar 
            level={micLevel} 
            color="#10b981" 
            label="麦克风音量" 
          />

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {!micTestActive ? (
              <button
                onClick={startMicTest}
                style={{
                  backgroundColor: '#10b981',
                  color: 'white',
                  border: 'none',
                  borderRadius: '0.375rem',
                  padding: '0.5rem 1rem',
                  fontSize: '0.875rem',
                  fontWeight: '500',
                  cursor: 'pointer'
                }}
              >
                🎤 开始测试
              </button>
            ) : (
              <button
                onClick={stopMicTest}
                style={{
                  backgroundColor: '#ef4444',
                  color: 'white',
                  border: 'none',
                  borderRadius: '0.375rem',
                  padding: '0.5rem 1rem',
                  fontSize: '0.875rem',
                  fontWeight: '500',
                  cursor: 'pointer'
                }}
              >
                ⏹ 停止测试
              </button>
            )}
          </div>
        </div>

        {/* 系统音频测试 */}
        <div style={{ marginBottom: '2rem' }}>
          <h4 style={{ margin: '0 0 1rem 0', fontSize: '1rem', fontWeight: '600', color: '#374151' }}>
            🔊 系统音频测试
          </h4>
          
          <div style={{
            backgroundColor: '#f9fafb',
            padding: '0.75rem',
            borderRadius: '0.5rem',
            marginBottom: '1rem',
            fontSize: '0.875rem',
            color: '#6b7280'
          }}>
            💡 系统音频测试需要屏幕共享权限，请选择包含音频的屏幕或应用程序
          </div>

          <VolumeBar 
            level={systemLevel} 
            color="#8b5cf6" 
            label="系统音频音量" 
          />

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {!systemTestActive ? (
              <button
                onClick={startSystemTest}
                style={{
                  backgroundColor: '#8b5cf6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '0.375rem',
                  padding: '0.5rem 1rem',
                  fontSize: '0.875rem',
                  fontWeight: '500',
                  cursor: 'pointer'
                }}
              >
                🔊 开始测试
              </button>
            ) : (
              <button
                onClick={stopSystemTest}
                style={{
                  backgroundColor: '#ef4444',
                  color: 'white',
                  border: 'none',
                  borderRadius: '0.375rem',
                  padding: '0.5rem 1rem',
                  fontSize: '0.875rem',
                  fontWeight: '500',
                  cursor: 'pointer'
                }}
              >
                ⏹ 停止测试
              </button>
            )}
          </div>
        </div>

        {/* 状态信息 */}
        <div style={{
          backgroundColor: '#f3f4f6',
          padding: '1rem',
          borderRadius: '0.5rem',
          fontSize: '0.875rem',
          color: '#374151'
        }}>
          <div style={{ fontWeight: '600', marginBottom: '0.5rem' }}>📊 测试状态</div>
          <div>麦克风: {micTestActive ? '✅ 测试中' : '❌ 未测试'}</div>
          <div>系统音频: {systemTestActive ? '✅ 测试中' : '❌ 未测试'}</div>
          {micTestActive && (
            <div style={{ marginTop: '0.5rem', color: micLevel > 10 ? '#10b981' : '#f59e0b' }}>
              麦克风音量: {micLevel > 10 ? '正常' : '过低，请检查麦克风'}
            </div>
          )}
          {systemTestActive && (
            <div style={{ marginTop: '0.5rem', color: systemLevel > 10 ? '#8b5cf6' : '#f59e0b' }}>
              系统音频: {systemLevel > 10 ? '正常' : '过低，请检查系统音频设置'}
            </div>
          )}
        </div>
      </div>
      </div>
    </>
  );
}
