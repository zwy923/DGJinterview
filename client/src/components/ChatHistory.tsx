import { useState, useEffect } from "react";

export interface ChatMessage {
  id: string;
  timestamp: string;
  speaker: 'user' | 'interviewer' | 'system';
  content: string;
  type: 'text' | 'audio' | 'system';
  isPartial?: boolean; // 是否为部分结果
}

export interface InterviewSession {
  id: string;
  config: {
    programmingLanguages: string[];
    uploadResume: boolean;
    useKnowledgeBase: boolean;
    position: string;
    jobRequirements: string;
  };
  messages: ChatMessage[];
  startTime: string;
  endTime?: string;
  status: 'active' | 'completed' | 'paused';
}

interface ChatHistoryProps {
  sessionId: string;
  onMessageAdd: (message: ChatMessage) => void;
  onSessionUpdate: (session: InterviewSession) => void;
}

export function useChatHistory({ sessionId, onMessageAdd, onSessionUpdate }: ChatHistoryProps) {
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // 加载会话数据
  useEffect(() => {
    loadSession();
  }, [sessionId]);

  const loadSession = () => {
    try {
      const savedSession = localStorage.getItem(`interview_${sessionId}`);
      if (savedSession) {
        const sessionData = JSON.parse(savedSession);
        setSession(sessionData);
      }
    } catch (error) {
      console.error('加载会话失败:', error);
    }
  };

  // 添加消息到会话
  const addMessage = async (message: Omit<ChatMessage, 'id' | 'timestamp'>) => {
    const newMessage: ChatMessage = {
      id: Date.now().toString(),
      timestamp: new Date().toISOString(),
      ...message
    };

    if (session) {
      const updatedSession = {
        ...session,
        messages: [...session.messages, newMessage]
      };
      
      setSession(updatedSession);
      saveSession(updatedSession);
      
      // 同步保存到后端
      try {
        await saveMessageToBackend(sessionId, newMessage);
      } catch (error) {
        console.error('保存到后端失败:', error);
      }
      
      onMessageAdd(newMessage);
    }
  };

  // 保存消息到后端
  const saveMessageToBackend = async (sessionId: string, message: ChatMessage) => {
    const response = await fetch(`http://${window.location.hostname}:8000/api/chat/save`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        session_id: sessionId,
        message: {
          id: message.id,
          timestamp: message.timestamp,
          speaker: message.speaker,
          content: message.content,
          type: message.type
        }
      })
    });

    if (!response.ok) {
      throw new Error('保存到后端失败');
    }

    return await response.json();
  };

  // 保存会话到本地存储
  const saveSession = (sessionData: InterviewSession) => {
    try {
      localStorage.setItem(`interview_${sessionId}`, JSON.stringify(sessionData));
      onSessionUpdate(sessionData);
    } catch (error) {
      console.error('保存会话失败:', error);
    }
  };

  // 导出聊天记录为结构化数据
  const exportChatHistory = () => {
    if (!session) return null;

    const structuredData = {
      sessionId: session.id,
      config: session.config,
      duration: session.endTime 
        ? new Date(session.endTime).getTime() - new Date(session.startTime).getTime()
        : Date.now() - new Date(session.startTime).getTime(),
      messageCount: session.messages.length,
      messages: session.messages.map(msg => ({
        speaker: msg.speaker,
        content: msg.content,
        timestamp: msg.timestamp,
        type: msg.type
      })),
      summary: {
        userMessages: session.messages.filter(msg => msg.speaker === 'user').length,
        interviewerMessages: session.messages.filter(msg => msg.speaker === 'interviewer').length,
        systemMessages: session.messages.filter(msg => msg.speaker === 'system').length,
        totalDuration: session.endTime 
          ? new Date(session.endTime).getTime() - new Date(session.startTime).getTime()
          : Date.now() - new Date(session.startTime).getTime()
      }
    };

    return structuredData;
  };

  // 发送结构化数据到GPT API
  const sendToGPT = async (structuredData: any) => {
    setIsLoading(true);
    try {
      const response = await fetch(`http://${window.location.hostname}:8000/api/gpt/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'interview_analysis',
          session_id: sessionId,
          data: {}
        })
      });

      if (response.ok) {
        const result = await response.json();
        return result;
      } else {
        throw new Error('GPT API请求失败');
      }
    } catch (error) {
      console.error('发送到GPT失败:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  // 分析面试表现
  const analyzeInterview = async () => {
    const structuredData = exportChatHistory();
    if (!structuredData) return;

    try {
      const analysis = await sendToGPT(structuredData);
      
      // 添加分析结果到会话
      addMessage({
        speaker: 'system',
        content: `面试分析完成：${analysis.summary}`,
        type: 'system'
      });

      return analysis;
    } catch (error) {
      console.error('分析面试失败:', error);
      addMessage({
        speaker: 'system',
        content: '面试分析失败，请稍后重试',
        type: 'system'
      });
    }
  };

  // 获取会话统计信息
  const getSessionStats = () => {
    if (!session) return null;

    return {
      totalMessages: session.messages.length,
      userMessages: session.messages.filter(msg => msg.speaker === 'user').length,
      interviewerMessages: session.messages.filter(msg => msg.speaker === 'interviewer').length,
      duration: session.endTime 
        ? new Date(session.endTime).getTime() - new Date(session.startTime).getTime()
        : Date.now() - new Date(session.startTime).getTime(),
      lastActivity: session.messages.length > 0 
        ? session.messages[session.messages.length - 1].timestamp
        : session.startTime
    };
  };

  return {
    session,
    addMessage,
    exportChatHistory,
    analyzeInterview,
    getSessionStats,
    isLoading
  };
}
