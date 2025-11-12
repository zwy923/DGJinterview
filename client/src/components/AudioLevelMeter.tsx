import { useState, useRef, useEffect } from "react";

interface AudioLevelMeterProps {
  stream: MediaStream | null;
  label: string;
  color: string;
  isActive: boolean;
}

export default function AudioLevelMeter({ stream, label, color, isActive }: AudioLevelMeterProps) {
  const [level, setLevel] = useState(0);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);

  useEffect(() => {
    if (!stream || !isActive) {
      setLevel(0);
      return;
    }

    // 创建音频上下文和分析器
    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;
    
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.8;
    
    analyserRef.current = analyser;
    source.connect(analyser);

    // 开始音频级别监控
    const updateLevel = () => {
      if (!analyserRef.current || !isActive) return;

      // 同时使用时域和频域数据，获得更好的灵敏度
      const timeData = new Uint8Array(analyserRef.current.frequencyBinCount);
      const freqData = new Uint8Array(analyserRef.current.frequencyBinCount);
      
      analyserRef.current.getByteTimeDomainData(timeData);
      analyserRef.current.getByteFrequencyData(freqData);
      
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
      const newLevel = Math.max(0, Math.min(100, cubeLevel));
      
      setLevel(newLevel);
      
      if (isActive) {
        animationRef.current = requestAnimationFrame(updateLevel);
      }
    };
    
    updateLevel();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, [stream, isActive]);

  return (
    <div style={{ marginBottom: '0.75rem' }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '0.25rem'
      }}>
        <span style={{ 
          fontSize: '0.75rem', 
          fontWeight: '500',
          color: isActive ? '#374151' : '#9ca3af'
        }}>
          {label}
        </span>
        <span style={{ 
          fontSize: '0.625rem', 
          color: isActive ? '#6b7280' : '#9ca3af',
          minWidth: '30px',
          textAlign: 'right'
        }}>
          {Math.round(level)}%
        </span>
      </div>
      <div style={{
        width: '100%',
        height: '4px',
        backgroundColor: '#e5e7eb',
        borderRadius: '2px',
        overflow: 'hidden',
        position: 'relative'
      }}>
        <div style={{
          width: `${level}%`,
          height: '100%',
          backgroundColor: isActive ? color : '#9ca3af',
          borderRadius: '2px',
          transition: 'width 0.1s ease-out',
          boxShadow: level > 30 && isActive ? `0 0 4px ${color}40` : 'none'
        }} />
      </div>
    </div>
  );
}
