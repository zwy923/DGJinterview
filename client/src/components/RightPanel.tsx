import { useState } from "react";
import { askGPT } from "../api/apiClient";

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
}

export default function RightPanel({ chatHistory, sessionId = "default", userId }: Props) {
  const [gptReply, setGptReply] = useState("点击「生成建议」按钮，根据当前对话获取智能回答建议...");
  const [isLoading, setIsLoading] = useState(false);

  // 手动生成回答建议
  const handleGetSuggestion = async () => {
    if (chatHistory.length === 0) {
      setGptReply("暂无对话记录，请先开始面试对话");
      return;
    }

    setIsLoading(true);
    
    try {
      // 构建上下文，包含最近的对话
      const recentMessages = chatHistory.slice(-10); // 最近10条消息
      const context = recentMessages.map(msg => 
        `${msg.speaker === 'user' ? '我' : '面试官'}: ${msg.content}`
      ).join('\n');
      
      const prompt = `面试对话上下文：\n${context}\n\n请基于以上对话，为面试者提供回答建议和技巧，帮助优化回答质量。`;
      
      // 传递sessionId和userId，启用RAG增强
      const reply = await askGPT(prompt, {
        sessionId: sessionId,
        userId: userId,
        useRag: true
      });
      setGptReply(reply);
    } catch (error) {
      console.error("GPT请求失败:", error);
      setGptReply("抱歉，无法获取AI建议，请稍后重试。");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="right-panel-content">
      <h2>🤖 面试助手</h2>
      
      {/* AI 回答建议区域 */}
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
            📝 AI 回答建议
          </h3>
          <button
            onClick={handleGetSuggestion}
            disabled={isLoading || chatHistory.length === 0}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '0.5rem',
              border: 'none',
              background: isLoading || chatHistory.length === 0
                ? 'rgba(107, 114, 128, 0.5)' 
                : 'linear-gradient(135deg, #10b981, #059669)',
              color: 'white',
              cursor: isLoading || chatHistory.length === 0 ? 'not-allowed' : 'pointer',
              fontSize: '0.875rem',
              fontWeight: '600',
              transition: 'all 0.2s ease'
            }}
          >
            {isLoading ? '生成中...' : '生成建议'}
          </button>
        </div>
        <div className="gpt-content">
          {isLoading ? (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '0.5rem',
              color: '#a1a1aa'
            }}>
              <div className="loading"></div>
              正在分析对话，生成建议中...
            </div>
          ) : (
            <div style={{ whiteSpace: 'pre-wrap' }}>{gptReply}</div>
          )}
        </div>
      </div>
    </div>
  );
}
