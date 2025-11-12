import { useState, useEffect, useRef } from "react";

interface ChatMessage {
  id: string;
  speaker: 'user' | 'interviewer';
  content: string;
  timestamp: string;
}

interface QAPair {
  id: string;
  question: string;
  reply: string;
  timestamp: string;
  isStreaming?: boolean; // 是否正在流式输出
}

interface Props {
  chatHistory: ChatMessage[];
  sessionId?: string;
  userId?: string;
  agentReply?: { question: string; reply: string } | null;
}

export default function RightPanel({ agentReply }: Props) {
  const [qaHistory, setQaHistory] = useState<QAPair[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatMessagesRef = useRef<HTMLDivElement>(null);

  // 当收到agent回答时，添加到历史记录（支持流式更新）
  useEffect(() => {
    if (agentReply && agentReply.question) {
      setQaHistory(prev => {
        // 检查是否已经存在相同的问题（可能是流式更新）
        // 从后往前查找最近的一个相同问题的问答对（可能是正在流式输出的）
        let existingIndex = -1;
        for (let i = prev.length - 1; i >= 0; i--) {
          if (prev[i].question === agentReply.question) {
            existingIndex = i;
            break;
          }
        }
        
        if (existingIndex >= 0) {
          // 更新现有的问答对（流式更新）
          const updated = [...prev];
          const existing = updated[existingIndex];
          
          // 如果新回复比现有回复长，说明是流式更新
          if (agentReply.reply && agentReply.reply.length >= existing.reply.length) {
            updated[existingIndex] = {
              ...existing,
              reply: agentReply.reply,
              isStreaming: true // 标记为流式中
            };
          }
          return updated;
        } else {
          // 添加新的问答对
          return [...prev, {
            id: Date.now().toString(),
            question: agentReply.question,
            reply: agentReply.reply || "",
            timestamp: new Date().toISOString(),
            isStreaming: !!agentReply.reply // 如果有内容，可能是流式中
          }];
        }
      });
    }
  }, [agentReply]);
  
  // 标记流式输出完成（当回复不再更新时）
  useEffect(() => {
    const timer = setTimeout(() => {
      setQaHistory(prev => prev.map(qa => 
        qa.isStreaming ? { ...qa, isStreaming: false } : qa
      ));
    }, 1000); // 1秒后如果没有更新，标记为完成
    
    return () => clearTimeout(timer);
  }, [agentReply]);

  // 自动滚动到底部
  useEffect(() => {
    if (messagesEndRef.current && chatMessagesRef.current) {
      const element = chatMessagesRef.current;
      element.scrollTop = element.scrollHeight;
    }
  }, [qaHistory]);


  return (
    <div className="right-panel-content" style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100%',
      overflow: 'hidden'
    }}>
      <h2 style={{ flexShrink: 0 }}>🤖 面试助手</h2>
      
      {/* 问答历史记录显示区域 */}
      <div className="chat-container" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div className="chat-messages" ref={chatMessagesRef} style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          {qaHistory.length === 0 ? (
            <div className="empty-chat">
              <div className="empty-icon">💭</div>
              <p>AI助手回答将显示在这里</p>
              <p style={{ fontSize: '0.75rem', color: '#71717a', marginTop: '0.5rem' }}>
                在左侧面板向AI助手提问，回答将显示在这里
              </p>
            </div>
          ) : (
            <>
              {qaHistory.map((qa) => (
                <div key={qa.id} style={{ marginBottom: '1.5rem' }}>
                  {/* 问题 */}
                  <div className="chat-message interviewer-message">
                    <div className="message-bubble">
                      <div className="message-header">
                        <span className="speaker-name">❓ 您的问题</span>
                        <span className="message-time">
                          {new Date(qa.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <div className="message-content">
                        {qa.question}
                      </div>
                    </div>
                  </div>
                  
                  {/* 回答 */}
                  <div className="chat-message user-message">
                    <div className="message-bubble" style={{
                      background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                      color: 'white'
                    }}>
                      <div className="message-header">
                        <span className="speaker-name">🤖 AI助手</span>
                        <span className="message-time">
                          {new Date(qa.timestamp).toLocaleTimeString()}
                          {qa.isStreaming && <span className="partial-badge">回答中...</span>}
                        </span>
                      </div>
                      <div className={`message-content ${qa.isStreaming ? 'partial-content' : ''}`} style={{ whiteSpace: 'pre-wrap' }}>
                        {qa.reply}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
