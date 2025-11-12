import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Layout from './Layout';
import { useChatHistory } from './ChatHistory';
import type { InterviewSession, ChatMessage } from './ChatHistory';

export default function InterviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // 聊天记录管理
  const chatHistory = useChatHistory({
    sessionId: id || '',
    onMessageAdd: (message: ChatMessage) => {
      console.log('新消息:', message);
    },
    onSessionUpdate: (updatedSession: InterviewSession) => {
      setSession(updatedSession);
    }
  });

  // 加载面试配置
  useEffect(() => {
    if (id) {
      loadInterviewConfig();
    }
  }, [id]);

  const loadInterviewConfig = () => {
    try {
      const interviewHistory = JSON.parse(localStorage.getItem('interviewHistory') || '[]');
      const interview = interviewHistory.find((item: any) => item.id === id);
      
      if (interview) {
        // 创建新的面试会话
        const newSession: InterviewSession = {
          id: id!,
          config: {
            programmingLanguages: interview.programmingLanguages,
            position: interview.position,
            jobRequirements: interview.jobRequirements
          },
          messages: [],
          startTime: new Date().toISOString(),
          status: 'active'
        };
        
        chatHistory.addMessage({
          speaker: 'system',
          content: `面试开始 - 职位：${interview.position}`,
          type: 'system'
        });
        
        setSession(newSession);
      } else {
        // 如果找不到面试配置，返回主页
        navigate('/');
      }
    } catch (error) {
      console.error('加载面试配置失败:', error);
      navigate('/');
    }
  };


  // 结束面试
  const endInterview = () => {
    if (session) {
      const updatedSession = {
        ...session,
        endTime: new Date().toISOString(),
        status: 'completed' as const
      };
      
      chatHistory.addMessage({
        speaker: 'system',
        content: '面试结束',
        type: 'system'
      });
      
      setSession(updatedSession);
    }
  };

  // 暂停面试
  const pauseInterview = () => {
    if (session) {
      const updatedSession = {
        ...session,
        status: 'paused' as const
      };
      
      chatHistory.addMessage({
        speaker: 'system',
        content: '面试暂停',
        type: 'system'
      });
      
      setSession(updatedSession);
    }
  };

  // 恢复面试
  const resumeInterview = () => {
    if (session) {
      const updatedSession = {
        ...session,
        status: 'active' as const
      };
      
      chatHistory.addMessage({
        speaker: 'system',
        content: '面试恢复',
        type: 'system'
      });
      
      setSession(updatedSession);
    }
  };

  // 分析面试表现
  const analyzeInterview = async () => {
    setIsLoading(true);
    try {
      const analysis = await chatHistory.analyzeInterview();
      console.log('面试分析结果:', analysis);
    } catch (error) {
      console.error('分析失败:', error);
    } finally {
      setIsLoading(false);
    }
  };

  if (!session) {
    return (
      <div className="loading-container">
        <div className="loading"></div>
        <p>加载面试配置中...</p>
      </div>
    );
  }

  return (
    <div className="interview-page">
      {/* 面试头部信息 */}
      <div className="interview-header">
        <div className="interview-info">
          <h1>{session.config.position}</h1>
          <div className="interview-meta">
            <span className="status-badge status-active">
              {session.status === 'active' ? '进行中' : 
               session.status === 'paused' ? '已暂停' : '已结束'}
            </span>
            <span className="duration">
              时长: {Math.floor((Date.now() - new Date(session.startTime).getTime()) / 60000)}分钟
            </span>
          </div>
        </div>
        
        <div className="interview-actions">
          <button onClick={endInterview} className="action-btn end-btn">
            结束面试
          </button>
        </div>
      </div>

      {/* 面试配置信息 */}
      <div className="interview-config">
        <div className="config-section">
          <h3>编程语言</h3>
          <div className="config-tags">
            {session.config.programmingLanguages.map(lang => (
              <span key={lang} className="config-tag">{lang}</span>
            ))}
          </div>
        </div>
        
        <div className="config-section">
          <h3>工作要求</h3>
          <p className="config-text">{session.config.jobRequirements}</p>
        </div>
        
      </div>

      {/* 聊天记录统计 */}
      <div className="chat-stats">
        {chatHistory.getSessionStats() && (
          <div className="stats-grid">
            <div className="stat-item">
              <span className="stat-label">总消息数</span>
              <span className="stat-value">{chatHistory.getSessionStats()?.totalMessages}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">用户消息</span>
              <span className="stat-value">{chatHistory.getSessionStats()?.userMessages}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">面试官消息</span>
              <span className="stat-value">{chatHistory.getSessionStats()?.interviewerMessages}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">面试时长</span>
              <span className="stat-value">
                {Math.floor((chatHistory.getSessionStats()?.duration || 0) / 60000)}分钟
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 主要的面试界面 */}
      <Layout sessionId={id || "default"} />
    </div>
  );
}
