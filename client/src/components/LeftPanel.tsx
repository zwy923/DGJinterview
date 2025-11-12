import { useState, useEffect, useRef } from "react";
import AudioController from "./AudioController";
import { getChatHistory, type ChatMessage as ApiChatMessage } from "../api/apiClient";
import { askGPT } from "../api/apiClient";

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
  onAgentReply?: (question: string, reply: string) => void;
  sessionId?: string;
  userId?: string; // 保留以兼容，但当前不使用
}

export default function LeftPanel({ 
  chatHistory, 
  onUserText, 
  onInterviewerText,
  onAgentReply,
  sessionId = "default",
  userId: _userId // 保留以兼容，但当前不使用
}: Props) {
  const [questionText, setQuestionText] = useState("");
  const [isAskingAgent, setIsAskingAgent] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [selectedMessages, setSelectedMessages] = useState<Set<string>>(new Set());
  const [isAnswering, setIsAnswering] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatMessagesRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const scrollTimeoutRef = useRef<number | null>(null);

  // 自动勾选面试官的消息
  useEffect(() => {
    const newSelected = new Set(selectedMessages);
    let hasNewSelection = false;
    
    chatHistory.forEach((msg) => {
      if (msg.speaker === 'interviewer' && !selectedMessages.has(msg.id)) {
        newSelected.add(msg.id);
        hasNewSelection = true;
      }
    });
    
    if (hasNewSelection) {
      setSelectedMessages(newSelected);
    }
  }, [chatHistory]);

  // 切换消息选中状态
  const toggleMessageSelection = (messageId: string) => {
    const newSelected = new Set(selectedMessages);
    if (newSelected.has(messageId)) {
      newSelected.delete(messageId);
    } else {
      newSelected.add(messageId);
    }
    setSelectedMessages(newSelected);
  };

  // 向agent提问（快答）
  const handleAskAgent = async () => {
    if (!questionText.trim() || isAskingAgent) return;
    
    const userQuestion = questionText.trim();
    setQuestionText("");
    setIsAskingAgent(true);
    
    try {
      // 流式响应：实时更新回答（快答）
      let fullReply = "";
      
      const reply = await askGPT(userQuestion, {
        sessionId: sessionId,
        brief: true, // 快答模式
        onChunk: (chunk: string) => {
          fullReply += chunk;
          if (onAgentReply) {
            onAgentReply(userQuestion, fullReply);
          }
        }
      });
      
      if (reply && reply.trim()) {
        if (onAgentReply) {
          onAgentReply(userQuestion, reply.trim());
        }
      } else if (!fullReply) {
        alert("未能获取回答，请稍后重试");
      }
    } catch (error: any) {
      console.error("向agent提问失败:", error);
      alert(`提问失败: ${error.message || "未知错误"}`);
    } finally {
      setIsAskingAgent(false);
    }
  };

  // 回答功能（正常回答，基于选中的消息）
  const handleAnswer = async () => {
    if (selectedMessages.size === 0 || isAnswering) {
      alert("请先选择要回答的面试官消息");
      return;
    }
    
    setIsAnswering(true);
    
    try {
      // 构建问题：基于选中的消息
      const selectedMsgs = chatHistory.filter(msg => selectedMessages.has(msg.id));
      const interviewerMsgs = selectedMsgs.filter(msg => msg.speaker === 'interviewer');
      
      if (interviewerMsgs.length === 0) {
        alert("选中的消息中没有面试官的问题");
        setIsAnswering(false);
        return;
      }
      
      // 合并选中的面试官消息作为问题
      const question = interviewerMsgs.map(msg => msg.content).join('；');
      
      // 流式响应：实时更新回答（正常回答，不是快答）
      let fullReply = "";
      
      const reply = await askGPT(question, {
        sessionId: sessionId,
        brief: false, // 正常回答，不是快答
        onChunk: (chunk: string) => {
          fullReply += chunk;
          if (onAgentReply) {
            onAgentReply(question, fullReply);
          }
        }
      });
      
      if (reply && reply.trim()) {
        if (onAgentReply) {
          onAgentReply(question, reply.trim());
        }
      } else if (!fullReply) {
        alert("未能获取回答，请稍后重试");
      }
    } catch (error: any) {
      console.error("回答失败:", error);
      alert(`回答失败: ${error.message || "未知错误"}`);
    } finally {
      setIsAnswering(false);
    }
  };

  // 检查是否接近底部
  const isNearBottom = (element: HTMLElement): boolean => {
    const threshold = 100;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    return distance < threshold;
  };

  // 智能滚动到最新消息
  const scrollToBottom = (force: boolean = false) => {
    if (!chatMessagesRef.current) return;
    
    const element = chatMessagesRef.current;
    
    if (!force && !shouldAutoScrollRef.current) {
      if (!isNearBottom(element)) {
        return;
      }
      shouldAutoScrollRef.current = true;
    }
    
    requestAnimationFrame(() => {
      if (chatMessagesRef.current && shouldAutoScrollRef.current) {
        if (messagesEndRef.current) {
          messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
        } else {
          chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight;
        }
      }
    });
  };

  // 处理滚动事件
  const handleScroll = () => {
    if (!chatMessagesRef.current) return;
    
    const element = chatMessagesRef.current;
    const isAtBottom = isNearBottom(element);
    
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
    }
    
    if (!isAtBottom) {
      shouldAutoScrollRef.current = false;
    } else {
      scrollTimeoutRef.current = setTimeout(() => {
        shouldAutoScrollRef.current = true;
      }, 500);
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
        const formattedHistory: ChatMessage[] = history.map((msg: ApiChatMessage) => ({
          id: msg.id?.toString() || Date.now().toString(),
          speaker: msg.speaker as 'user' | 'interviewer' | 'system',
          content: msg.content,
          timestamp: msg.timestamp || new Date().toISOString(),
          isPartial: false,
        }));
        
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
    <div className="left-panel-content" style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100%',
      overflow: 'hidden'
    }}>
      <h2 style={{ flexShrink: 0 }}>💬 面试对话记录</h2>
      
      {/* 回答按钮 */}
      <div style={{ 
        marginBottom: '1rem',
        display: 'flex',
        gap: '0.5rem',
        alignItems: 'center',
        flexShrink: 0
      }}>
        <button
          onClick={handleAnswer}
          disabled={selectedMessages.size === 0 || isAnswering}
          style={{
            padding: '0.5rem 1rem',
            borderRadius: '0.5rem',
            border: 'none',
            background: (selectedMessages.size === 0 || isAnswering)
              ? 'rgba(107, 114, 128, 0.5)' 
              : 'linear-gradient(135deg, #10b981, #059669)',
            color: 'white',
            cursor: (selectedMessages.size === 0 || isAnswering) ? 'not-allowed' : 'pointer',
            fontSize: '0.875rem',
            fontWeight: '600',
            transition: 'all 0.2s ease'
          }}
        >
          {isAnswering ? '回答中...' : `回答 (${selectedMessages.size})`}
        </button>
        {selectedMessages.size > 0 && (
          <button
            onClick={() => setSelectedMessages(new Set())}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '0.5rem',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              background: 'transparent',
              color: '#9ca3af',
              cursor: 'pointer',
              fontSize: '0.75rem'
            }}
          >
            清空选择
          </button>
        )}
      </div>
      
      {/* 聊天记录显示区域 */}
      <div className="chat-container" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div className="chat-messages" ref={chatMessagesRef} style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
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
              {chatHistory.map((message) => {
                const isPartial = (message as any).isPartial || false;
                const isSelected = selectedMessages.has(message.id);
                const isInterviewer = message.speaker === 'interviewer';
                
                return (
                  <div 
                    key={message.id} 
                    className={`chat-message ${message.speaker === 'user' ? 'user-message' : 'interviewer-message'} ${isPartial ? 'partial-message' : ''}`}
                    style={{
                      position: 'relative',
                      cursor: isInterviewer ? 'pointer' : 'default',
                      opacity: isInterviewer && !isSelected ? 0.7 : 1,
                      border: isSelected ? '2px solid #10b981' : 'none',
                      borderRadius: isSelected ? '0.5rem' : '0',
                      padding: isSelected ? '0.25rem' : '0'
                    }}
                    onClick={() => isInterviewer && toggleMessageSelection(message.id)}
                  >
                    {isInterviewer && (
                      <div style={{
                        position: 'absolute',
                        left: '-1.5rem',
                        top: '0.5rem',
                        width: '1rem',
                        height: '1rem',
                        border: '2px solid #10b981',
                        borderRadius: '0.25rem',
                        background: isSelected ? '#10b981' : 'transparent',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: 'pointer'
                      }}>
                        {isSelected && (
                          <span style={{ color: 'white', fontSize: '0.75rem' }}>✓</span>
                        )}
                      </div>
                    )}
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
      
      {/* 向Agent提问 */}
      <div style={{ 
        marginTop: '1rem',
        padding: '1rem',
        background: 'rgba(0, 0, 0, 0.2)',
        borderRadius: '0.75rem',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        flexShrink: 0
      }}>
        <div style={{ 
          fontSize: '0.875rem', 
          color: '#e5e7eb', 
          marginBottom: '0.5rem',
          fontWeight: '600'
        }}>
          🤖 向AI助手提问
        </div>
        <div style={{ 
          fontSize: '0.75rem', 
          color: '#9ca3af', 
          marginBottom: '0.75rem'
        }}>
          输入问题，AI助手将基于当前面试上下文、岗位信息和简历给出专业回答（一句话快答）
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="text"
            value={questionText}
            onChange={(e) => setQuestionText(e.target.value)}
            placeholder="输入您的问题..."
            disabled={isAskingAgent}
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
              if (e.key === 'Enter' && !isAskingAgent) {
                handleAskAgent();
              }
            }}
          />
          <button
            onClick={handleAskAgent}
            disabled={!questionText.trim() || isAskingAgent}
            style={{
              padding: '0.5rem 1.5rem',
              borderRadius: '0.375rem',
              border: 'none',
              background: (!questionText.trim() || isAskingAgent)
                ? 'rgba(107, 114, 128, 0.5)' 
                : 'linear-gradient(135deg, #3b82f6, #2563eb)',
              color: 'white',
              cursor: (!questionText.trim() || isAskingAgent) ? 'not-allowed' : 'pointer',
              fontSize: '0.875rem',
              fontWeight: '600',
              minWidth: '80px',
              transition: 'all 0.2s ease'
            }}
          >
            {isAskingAgent ? '提问中...' : '提问'}
          </button>
        </div>
      </div>
      
      <div style={{ flexShrink: 0 }}>
        <AudioController 
          onUserText={onUserText} 
          onInterviewerText={onInterviewerText}
          sessionId={sessionId}
        />
      </div>
    </div>
  );
}
