import { useState, useEffect } from "react";
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
  agentReply?: { question: string; reply: string } | null;
}

export default function RightPanel({ chatHistory, sessionId = "default", userId, agentReply }: Props) {
  const [gptReply, setGptReply] = useState("点击「生成建议」按钮，根据当前对话获取智能回答建议...");
  const [isLoading, setIsLoading] = useState(false);

  // 当收到agent回答时，更新显示
  useEffect(() => {
    if (agentReply) {
      setGptReply(agentReply.reply);
    }
  }, [agentReply]);

  // 手动生成回答建议（流式）
  const handleGetSuggestion = async () => {
    if (chatHistory.length === 0) {
      setGptReply("暂无对话记录，请先开始面试对话");
      return;
    }

    setIsLoading(true);
    
    // 保存当前内容，用于追加（不清空）
    const previousContent = gptReply;
    const separator = previousContent && previousContent.trim() && !previousContent.endsWith('\n\n') ? '\n\n' : '';
    
    try {
      // 构建上下文，包含最近的对话
      const recentMessages = chatHistory.slice(-10); // 最近10条消息
      const context = recentMessages.map(msg => 
        `${msg.speaker === 'user' ? '我' : '面试官'}: ${msg.content}`
      ).join('\n');
      
      const prompt = `面试对话上下文：\n${context}\n\n请基于以上对话，为面试者提供简要回答。`;
      
      // 传递sessionId和userId，启用RAG增强，使用流式响应
      let newContent = '';
      const reply = await askGPT(prompt, {
        sessionId: sessionId,
        userId: userId,
        useRag: true,
        stream: true,
        onChunk: (chunk: string) => {
          // 流式更新显示：在之前内容后追加新内容
          newContent += chunk;
          setGptReply(previousContent + separator + newContent);
        }
      });
      
      // 确保最终内容已设置（流式完成后）
      if (reply) {
        setGptReply(previousContent + separator + reply);
      }
    } catch (error: any) {
      console.error("GPT请求失败:", error);
      setGptReply(previousContent + separator + '抱歉，无法获取AI建议，请稍后重试。');
    } finally {
      setIsLoading(false);
    }
  };

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
