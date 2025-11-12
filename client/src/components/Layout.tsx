import { useState, useRef, useEffect } from "react";
import LeftPanel from "./LeftPanel";
import RightPanel from "./RightPanel";
import { getChatHistory, type ChatMessage as ApiChatMessage } from "../api/apiClient";

interface Props {
  sessionId?: string;
  userId?: string;
}

export default function Layout({ sessionId = "default", userId }: Props) {
  const [activePanel, setActivePanel] = useState<'left' | 'right'>('left');
  const [chatHistory, setChatHistory] = useState<Array<{
    id: string;
    speaker: 'user' | 'interviewer';
    content: string;
    timestamp: string;
    isPartial?: boolean;
  }>>([]);
  const [agentReply, setAgentReply] = useState<{ question: string; reply: string } | null>(null);
  
  // 部分结果临时存储（用于更新）
  const partialResultsRef = useRef<Map<string, number>>(new Map());

  // 从后端加载聊天历史
  useEffect(() => {
    const loadHistory = async () => {
      if (!sessionId) return;
      
      try {
        const history = await getChatHistory(sessionId);
        // 将后端格式转换为前端格式
        const formattedHistory = history.map((msg: ApiChatMessage) => ({
          id: msg.id?.toString() || Date.now().toString(),
          speaker: msg.speaker as 'user' | 'interviewer',
          content: msg.content,
          timestamp: msg.timestamp || new Date().toISOString(),
          isPartial: false,
        }));
        
        // 合并到现有历史（避免重复）
        setChatHistory(prev => {
          const existingIds = new Set(prev.map(m => m.id));
          const newMessages = formattedHistory.filter(m => !existingIds.has(m.id));
          // 按时间戳排序
          const allMessages = [...prev, ...newMessages].sort((a, b) => 
            new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
          );
          return allMessages;
        });
      } catch (error) {
        console.error('Failed to load chat history:', error);
      }
    };

    loadHistory();
  }, [sessionId]);

  // 添加新消息到聊天历史
  const addMessage = (speaker: 'user' | 'interviewer', content: string) => {
    if (content.trim()) {
      const newMessage = {
        id: Date.now().toString(),
        speaker,
        content: content.trim(),
        timestamp: new Date().toISOString()
      };
      setChatHistory(prev => [...prev, newMessage]);
    }
  };

  // 处理用户语音识别结果（支持部分结果）
  const handleUserText = (text: string, isPartial: boolean = false) => {
    if (isPartial) {
      // 部分结果：更新或创建临时消息
      const partialId = 'user-partial';
      setChatHistory(prev => {
        const filtered = prev.filter(msg => msg.id !== partialId);
        return [...filtered, {
          id: partialId,
          speaker: 'user' as const,
          content: text,
          timestamp: new Date().toISOString(),
          isPartial: true
        }];
      });
    } else {
      // 最终结果：移除部分结果，添加最终结果
      setChatHistory(prev => {
        const filtered = prev.filter(msg => msg.id !== 'user-partial');
        return [...filtered, {
          id: Date.now().toString(),
          speaker: 'user' as const,
          content: text,
          timestamp: new Date().toISOString(),
          isPartial: false
        }];
      });
    }
  };

  // 处理面试官语音识别结果（支持部分结果）
  const handleInterviewerText = (text: string, isPartial: boolean = false) => {
    if (isPartial) {
      // 部分结果：更新或创建临时消息
      const partialId = 'interviewer-partial';
      setChatHistory(prev => {
        const filtered = prev.filter(msg => msg.id !== partialId);
        return [...filtered, {
          id: partialId,
          speaker: 'interviewer' as const,
          content: text,
          timestamp: new Date().toISOString(),
          isPartial: true
        }];
      });
    } else {
      // 最终结果：移除部分结果，添加最终结果
      setChatHistory(prev => {
        const filtered = prev.filter(msg => msg.id !== 'interviewer-partial');
        return [...filtered, {
          id: Date.now().toString(),
          speaker: 'interviewer' as const,
          content: text,
          timestamp: new Date().toISOString(),
          isPartial: false
        }];
      });
    }
  };

  // 处理Agent回答
  const handleAgentReply = (question: string, reply: string) => {
    setAgentReply({ question, reply });
    // 自动切换到右侧面板显示回答
    setActivePanel('right');
  };

  return (
    <div className="app-container">
      {/* 应用头部 */}
      <header className="app-header">
        <div className="header-content">
          <h1 className="app-title">
            <span className="title-icon">🎯</span>
            11面试
          </h1>
          <div className="header-subtitle">面试辅助</div>
        </div>
      </header>

      {/* 移动端标签页切换 */}
      <nav className="mobile-tabs">
        <button 
          className={`tab-button ${activePanel === 'left' ? 'active' : ''}`}
          onClick={() => setActivePanel('left')}
        >
          <span className="tab-icon">💬</span>
          <span className="tab-text">聊天记录</span>
        </button>
        <button 
          className={`tab-button ${activePanel === 'right' ? 'active' : ''}`}
          onClick={() => setActivePanel('right')}
        >
          <span className="tab-icon">🤖</span>
          <span className="tab-text">面试助手</span>
        </button>
      </nav>

      {/* 主内容区域 */}
      <main className="main-content">
        <div className={`left-panel ${activePanel === 'left' ? 'active' : ''}`}>
          <LeftPanel 
            chatHistory={chatHistory}
            onUserText={handleUserText}
            onInterviewerText={handleInterviewerText}
            onAgentReply={handleAgentReply}
            sessionId={sessionId}
            userId={userId}
          />
        </div>
        <div className={`right-panel ${activePanel === 'right' ? 'active' : ''}`}>
          <RightPanel 
            chatHistory={chatHistory}
            sessionId={sessionId}
            userId={userId}
            agentReply={agentReply}
          />
        </div>
      </main>
    </div>
  );
}
