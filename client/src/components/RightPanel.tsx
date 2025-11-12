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

  useEffect(() => {
    const lastUserMessage = chatHistory
      .filter(msg => msg.speaker === 'user')
      .slice(-1)[0];

    if (lastUserMessage && lastUserMessage.content.trim()) {
      setIsLoading(true);

      const recentMessages = chatHistory.slice(-6);
      const context = recentMessages
        .map(msg => `${msg.speaker === 'user' ? '我' : '面试官'}: ${msg.content}`)
        .join('\n');

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
    <div className="flex h-full flex-1 flex-col gap-6 md:sticky md:top-28">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">🤖 面试助手</h2>
      </div>
      <div className="relative flex min-h-[18rem] flex-1 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl">
        <div className="custom-scrollbar flex-1 overflow-y-auto text-sm leading-relaxed text-slate-200">
          {isLoading ? (
            <div className="flex items-center gap-3 text-slate-400">
              <span className="relative flex h-3 w-3">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-primary/60" />
                <span className="relative inline-flex h-3 w-3 rounded-full bg-brand-primary" />
              </span>
              正在分析您的回答，生成建议中...
            </div>
          ) : (
            <p className="whitespace-pre-line text-slate-100">{gptReply}</p>
          )}
        </div>
      </div>
    </div>
  );
}
