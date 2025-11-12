import { useState, useEffect } from "react";

interface SystemAudioStatusProps {
  isEnabled: boolean;
  onToggle: () => void;
}

export default function SystemAudioStatus({ isEnabled, onToggle }: SystemAudioStatusProps) {
  const [status, setStatus] = useState<'idle' | 'starting' | 'running' | 'stopping' | 'error'>('idle');
  const [error, setError] = useState<string>("");

  useEffect(() => {
    if (isEnabled) {
      setStatus('running');
      setError("");
    } else {
      setStatus('idle');
    }
  }, [isEnabled]);

  const handleToggle = async () => {
    if (status === 'starting' || status === 'stopping') return;
    
    if (isEnabled) {
      setStatus('stopping');
      try {
        await onToggle();
        setStatus('idle');
      } catch (err) {
        setStatus('error');
        setError(err instanceof Error ? err.message : '停止失败');
      }
    } else {
      setStatus('starting');
      try {
        await onToggle();
        setStatus('running');
      } catch (err) {
        setStatus('error');
        setError(err instanceof Error ? err.message : '启动失败');
      }
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case 'running': return '#10b981';
      case 'starting': return '#f59e0b';
      case 'stopping': return '#f59e0b';
      case 'error': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'running': return '✅ 系统音频运行中';
      case 'starting': return '🔄 启动中...';
      case 'stopping': return '🔄 停止中...';
      case 'error': return '❌ 错误';
      default: return '⚪ 未启用';
    }
  };

  return (
    <div style={{
      backgroundColor: '#f9fafb',
      padding: '0.75rem',
      borderRadius: '0.5rem',
      border: '1px solid #e5e7eb',
      marginBottom: '1rem'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '0.5rem'
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          <span style={{
            fontSize: '0.875rem',
            fontWeight: '600',
            color: '#374151'
          }}>
            🔊 后端系统音频
          </span>
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: getStatusColor(),
            animation: status === 'running' ? 'pulse 2s infinite' : 'none'
          }} />
        </div>
        
        <button
          onClick={handleToggle}
          disabled={status === 'starting' || status === 'stopping'}
          style={{
            backgroundColor: isEnabled ? '#ef4444' : '#10b981',
            color: 'white',
            border: 'none',
            borderRadius: '0.375rem',
            padding: '0.375rem 0.75rem',
            fontSize: '0.75rem',
            fontWeight: '500',
            cursor: status === 'starting' || status === 'stopping' ? 'not-allowed' : 'pointer',
            opacity: status === 'starting' || status === 'stopping' ? 0.6 : 1,
            transition: 'all 0.2s ease'
          }}
        >
          {isEnabled ? '停止' : '启动'}
        </button>
      </div>
      
      <div style={{
        fontSize: '0.75rem',
        color: getStatusColor(),
        fontWeight: '500'
      }}>
        {getStatusText()}
      </div>
      
      {error && (
        <div style={{
          fontSize: '0.75rem',
          color: '#ef4444',
          marginTop: '0.25rem',
          padding: '0.25rem',
          backgroundColor: '#fef2f2',
          borderRadius: '0.25rem',
          border: '1px solid #fecaca'
        }}>
          {error}
        </div>
      )}
      
      <div style={{
        fontSize: '0.625rem',
        color: '#6b7280',
        marginTop: '0.5rem'
      }}>
        💡 后端系统音频捕获通过PyAudio直接访问系统音频设备，无需浏览器权限
      </div>
    </div>
  );
}
