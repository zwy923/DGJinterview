import { useState, useEffect } from "react";
import { askGPT } from "../api/gptClient";

interface ChatMessage {
  id: string;
  speaker: 'user' | 'interviewer';
  content: string;
  timestamp: string;
}

interface Props {
  chatHistory: ChatMessage[];
}

export default function RightPanel({ chatHistory }: Props) {
  const [gptReply, setGptReply] = useState("等待面试对话，我将为您提供智能回答建议...");
  const [isLoading, setIsLoading] = useState(false);

  // 当检测到新的用户消息时，调用GPT获取建议
  useEffect(() => {
    const lastUserMessage = chatHistory
      .filter(msg => msg.speaker === 'user')
      .slice(-1)[0];
    
    if (lastUserMessage && lastUserMessage.content.trim()) {
      setIsLoading(true);
      
      // 构建上下文，包含最近的对话
      const recentMessages = chatHistory.slice(-6); // 最近6条消息
      const context = recentMessages.map(msg => 
        `${msg.speaker === 'user' ? '我' : '面试官'}: ${msg.content}`
      ).join('\n');
      
      const prompt = `面试对话上下文：\n${context}\n\n请基于以上对话，为用户提供面试回答建议和技巧。`;
      
      askGPT(prompt)
        .then(reply => {
          setGptReply(reply);
          setIsLoading(false);
        })
        .catch(error => {
          console.error("GPT请求失败:", error);
          setGptReply("抱歉，无法获取AI建议，请稍后重试。");
          setIsLoading(false);
        });
    }
  }, [chatHistory]);

  return (
    <div className="right-panel-content">
      <h2>🤖 面试助手</h2>
      <div className="card gpt-box">
        <div className="gpt-content">
          {isLoading ? (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '0.5rem',
              color: '#a1a1aa'
            }}>
              <div className="loading"></div>
              正在分析您的回答，生成建议中...
            </div>
          ) : (
            gptReply
          )}
        </div>
      </div>
    </div>
  );
}
