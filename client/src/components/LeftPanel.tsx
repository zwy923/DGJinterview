import { useState } from "react";
import AudioController from "./AudioController";

interface ChatMessage {
  id: string;
  speaker: 'user' | 'interviewer';
  content: string;
  timestamp: string;
  isPartial?: boolean;
}

interface Props {
  chatHistory: ChatMessage[];
  onUserText: (text: string) => void;
  onInterviewerText: (text: string) => void;
  sessionId?: string;
}

export default function LeftPanel({ 
  chatHistory, 
  onUserText, 
  onInterviewerText,
  sessionId = "default"
}: Props) {
  const [manualText, setManualText] = useState("");

  // 手动输入面试官的话
  const handleManualInput = () => {
    if (manualText.trim()) {
      onInterviewerText(manualText.trim());
      setManualText("");
    }
  };

  return (
    <div className="left-panel-content">
      <h2>💬 面试对话记录</h2>
      
      {/* 聊天记录显示区域 */}
      <div className="chat-container">
        <div className="chat-messages">
          {chatHistory.length === 0 ? (
            <div className="empty-chat">
              <div className="empty-icon">💭</div>
              <p>开始语音识别，对话记录将显示在这里</p>
            </div>
          ) : (
            chatHistory.map((message, index) => {
              // 检查是否为部分结果（通过检查是否有 partial 属性或通过消息类型）
              const isPartial = (message as any).isPartial || false;
              
              return (
                <div 
                  key={message.id} 
                  className={`chat-message ${message.speaker === 'user' ? 'user-message' : 'interviewer-message'} ${isPartial ? 'partial-message' : ''}`}
                >
                  <div className="message-bubble">
                    <div className="message-header">
                      <span className="speaker-name">
                        {message.speaker === 'user' ? '我' : '面试官'}
                      </span>
                      <span className="message-time">
                        {new Date(message.timestamp).toLocaleTimeString()}
                        {isPartial && <span className="partial-badge">识别中...</span>}
                      </span>
                    </div>
                    <div className={`message-content ${isPartial ? 'partial-content' : ''}`}>
                      {message.content}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
      
      {/* 手动输入面试官的话 */}
      <div style={{ 
        marginTop: '1rem',
        padding: '1rem',
        background: 'rgba(0, 0, 0, 0.2)',
        borderRadius: '0.75rem',
        border: '1px solid rgba(255, 255, 255, 0.1)'
      }}>
        <div style={{ 
          fontSize: '0.875rem', 
          color: '#e5e7eb', 
          marginBottom: '0.5rem',
          fontWeight: '600'
        }}>
          📝 手动输入面试官的话
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="text"
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
            placeholder="输入面试官说的话..."
            style={{
              flex: 1,
              padding: '0.5rem',
              borderRadius: '0.375rem',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              background: 'rgba(0, 0, 0, 0.3)',
              color: '#e5e7eb',
              fontSize: '0.875rem'
            }}
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                handleManualInput();
              }
            }}
          />
          <button
            onClick={handleManualInput}
            disabled={!manualText.trim()}
            style={{
              padding: '0.5rem 1.5rem',
              borderRadius: '0.375rem',
              border: 'none',
              background: manualText.trim() ? 'linear-gradient(135deg, #10b981, #059669)' : 'rgba(107, 114, 128, 0.5)',
              color: 'white',
              cursor: manualText.trim() ? 'pointer' : 'not-allowed',
              fontSize: '0.875rem',
              fontWeight: '600',
              minWidth: '80px',
              transition: 'all 0.2s ease'
            }}
          >
            发送
          </button>
        </div>
      </div>
      
      <AudioController 
        onUserText={onUserText} 
        onInterviewerText={onInterviewerText}
        sessionId={sessionId}
      />
    </div>
  );
}
