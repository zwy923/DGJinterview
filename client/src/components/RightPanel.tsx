import { useState, useEffect } from "react";

interface ChatMessage {
  id: string;
  speaker: 'user' | 'interviewer';
  content: string;
  timestamp: string;
}

interface Props {
  chatHistory: ChatMessage[];
  sessionId?: string;
  userId?: string;
  agentReply?: { question: string; reply: string } | null;
}

export default function RightPanel({ agentReply }: Props) {
  const [gptReply, setGptReply] = useState("AI助手回答将显示在这里...");

  // 当收到agent回答时，更新显示
  useEffect(() => {
    if (agentReply) {
      setGptReply(agentReply.reply);
    }
  }, [agentReply]);


  return (
    <div className="right-panel-content">
      <h2>🤖 面试助手</h2>
      
      {/* Agent回答区域 */}
      <div className="card gpt-box">
        <div style={{ 
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1rem'
        }}>
          <h3 style={{ 
            fontSize: '1rem', 
            fontWeight: '600', 
            color: '#e5e7eb',
            margin: 0
          }}>
            🤖 AI助手回答
          </h3>
        </div>
        {agentReply && (
          <div style={{
            marginBottom: '1rem',
            padding: '0.75rem',
            background: 'rgba(59, 130, 246, 0.1)',
            borderRadius: '0.5rem',
            border: '1px solid rgba(59, 130, 246, 0.3)'
          }}>
            <div style={{
              fontSize: '0.75rem',
              color: '#9ca3af',
              marginBottom: '0.25rem'
            }}>
              您的问题：
            </div>
            <div style={{
              fontSize: '0.875rem',
              color: '#e5e7eb'
            }}>
              {agentReply.question}
            </div>
          </div>
        )}
        <div className="gpt-content">
          <div style={{ whiteSpace: 'pre-wrap' }}>{gptReply}</div>
        </div>
      </div>
    </div>
  );
}
