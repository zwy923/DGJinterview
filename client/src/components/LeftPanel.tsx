import { useState, useEffect, useRef } from "react";
import AudioController from "./AudioController";
import { getChatHistory, type ChatMessage as ApiChatMessage } from "../api/apiClient";

interface ChatMessage {
  id: string;
  speaker: 'user' | 'interviewer' | 'system';
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
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatMessagesRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 手动输入面试官的话
  const handleManualInput = () => {
    if (manualText.trim()) {
      onInterviewerText(manualText.trim());
      setManualText("");
    }
  };

  // 检查是否接近底部
  const isNearBottom = (element: HTMLElement): boolean => {
    const threshold = 100; // 100px 阈值
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    return distance < threshold;
  };

  // 智能滚动到最新消息
  const scrollToBottom = (force: boolean = false) => {
    if (!chatMessagesRef.current) return;
    
    const element = chatMessagesRef.current;
    
    // 如果用户手动滚动了，检查是否需要自动滚动
    if (!force && !shouldAutoScrollRef.current) {
      // 如果用户不在底部附近，不自动滚动
      if (!isNearBottom(element)) {
        return;
      }
      // 如果用户在底部附近，恢复自动滚动
      shouldAutoScrollRef.current = true;
    }
    
    // 使用 requestAnimationFrame 确保在渲染后滚动
    requestAnimationFrame(() => {
      if (chatMessagesRef.current && shouldAutoScrollRef.current) {
        // 使用 scrollIntoView 更可靠
        if (messagesEndRef.current) {
          messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
        } else {
          // 降级方案
          chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight;
        }
      }
    });
  };

  // 处理滚动事件，检测用户是否手动滚动
  const handleScroll = () => {
    if (!chatMessagesRef.current) return;
    
    const element = chatMessagesRef.current;
    const isAtBottom = isNearBottom(element);
    
    // 清除之前的超时
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
    }
    
    // 如果用户不在底部，暂停自动滚动
    if (!isAtBottom) {
      shouldAutoScrollRef.current = false;
    } else {
      // 如果用户滚动回底部，恢复自动滚动
      scrollTimeoutRef.current = setTimeout(() => {
        shouldAutoScrollRef.current = true;
      }, 500); // 500ms 延迟，避免频繁切换
    }
  };

  // 当聊天记录更新时智能滚动
  useEffect(() => {
    scrollToBottom();
  }, [chatHistory]);

  // 添加滚动事件监听
  useEffect(() => {
    const element = chatMessagesRef.current;
    if (element) {
      element.addEventListener('scroll', handleScroll, { passive: true });
      return () => {
        element.removeEventListener('scroll', handleScroll);
        if (scrollTimeoutRef.current) {
          clearTimeout(scrollTimeoutRef.current);
        }
      };
    }
  }, []);

  // 从后端加载聊天历史
  useEffect(() => {
    const loadHistory = async () => {
      if (!sessionId) return;
      
      setIsLoadingHistory(true);
      try {
        const history = await getChatHistory(sessionId);
        // 将后端格式转换为前端格式
        const formattedHistory: ChatMessage[] = history.map((msg: ApiChatMessage) => ({
          id: msg.id?.toString() || Date.now().toString(),
          speaker: msg.speaker as 'user' | 'interviewer' | 'system',
          content: msg.content,
          timestamp: msg.timestamp || new Date().toISOString(),
          isPartial: false,
        }));
        
        // 合并本地和远程消息（避免重复）
        // 注意：这里只是加载，实际合并逻辑应该在父组件中处理
        console.log('Loaded chat history from backend:', formattedHistory.length, 'messages');
      } catch (error) {
        console.error('Failed to load chat history:', error);
      } finally {
        setIsLoadingHistory(false);
      }
    };

    loadHistory();
  }, [sessionId]);

  return (
    <div className="left-panel-content">
      <h2>💬 面试对话记录</h2>
      
      {/* 聊天记录显示区域 */}
      <div className="chat-container">
        <div className="chat-messages" ref={chatMessagesRef}>
          {isLoadingHistory ? (
            <div className="empty-chat">
              <div className="empty-icon">⏳</div>
              <p>正在加载聊天记录...</p>
            </div>
          ) : chatHistory.length === 0 ? (
            <div className="empty-chat">
              <div className="empty-icon">💭</div>
              <p>开始语音识别，对话记录将显示在这里</p>
            </div>
          ) : (
            <>
              {chatHistory.map((message, index) => {
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
              })}
              <div ref={messagesEndRef} />
            </>
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
