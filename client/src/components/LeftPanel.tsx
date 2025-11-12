import { useState, useEffect, useRef } from "react";
import AudioController from "./AudioController";

interface ChatMessage {
  id: string;
  speaker: 'user' | 'interviewer';
  content: string;
  timestamp: string;
  isPartial?: boolean;
}

interface Props {
  chatHistory: ChatMessage[];
  onUserText: (text: string, isPartial?: boolean) => void;
  onInterviewerText: (text: string, isPartial?: boolean) => void;
  sessionId?: string;
}

export default function LeftPanel({
  chatHistory,
  onUserText,
  onInterviewerText,
  sessionId = "default"
}: Props) {
  const [manualText, setManualText] = useState("");
  const chatMessagesRef = useRef<HTMLDivElement>(null);

  const handleManualInput = () => {
    if (manualText.trim()) {
      onInterviewerText(manualText.trim());
      setManualText("");
    }
  };

  useEffect(() => {
    if (!chatMessagesRef.current) return;

    const lastMessage = chatHistory[chatHistory.length - 1];

    requestAnimationFrame(() => {
      if (!chatMessagesRef.current) return;
      chatMessagesRef.current.scrollTo({
        top: chatMessagesRef.current.scrollHeight,
        behavior: lastMessage?.isPartial ? 'auto' : 'smooth'
      });
    });
  }, [chatHistory]);

  return (
    <div className="flex h-full min-h-[32rem] flex-1 flex-col gap-6 md:max-h-[calc(100vh-220px)]">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">💬 面试对话记录</h2>
      </div>

      <div className="relative flex flex-1 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70 shadow-xl">
        <div
          ref={chatMessagesRef}
          className="custom-scrollbar flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-6 md:min-h-[24rem]"
        >
          {chatHistory.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-slate-400">
              <div className="text-4xl">💭</div>
              <p className="text-sm">开始语音识别，对话记录将显示在这里</p>
            </div>
          ) : (
            <>
              {chatHistory.map(message => {
                const isUser = message.speaker === 'user';
                const isPartial = Boolean(message.isPartial);
                return (
                  <div
                    key={message.id}
                    className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl border px-4 py-3 shadow-sm transition ${
                        isUser
                          ? 'border-brand-primary/50 bg-brand-primary/20 text-slate-50'
                          : 'border-slate-800 bg-slate-900/60 text-slate-100'
                      } ${isPartial ? 'border-dashed opacity-80' : ''}`}
                    >
                      <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
                        <span className="font-semibold text-slate-200">
                          {isUser ? '我' : '面试官'}
                        </span>
                        <span className="flex items-center gap-2">
                          {new Date(message.timestamp).toLocaleTimeString()}
                          {isPartial && (
                            <span className="rounded-full border border-amber-400/50 px-2 py-0.5 text-[10px] font-medium text-amber-300">
                              识别中...
                            </span>
                          )}
                        </span>
                      </div>
                      <div className={`text-sm leading-relaxed ${isPartial ? 'italic text-slate-200' : ''}`}>
                        {message.content}
                      </div>
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
          <span className="text-lg">📝</span>
          手动输入面试官的话
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            type="text"
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
            placeholder="输入面试官说的话..."
            className="w-full rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none ring-brand-primary/30 transition focus:border-brand-primary/60 focus:ring"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleManualInput();
              }
            }}
          />
          <button
            type="button"
            onClick={handleManualInput}
            disabled={!manualText.trim()}
            className="rounded-xl bg-brand-primary px-6 py-2 text-sm font-semibold text-white shadow-lg shadow-brand-primary/20 transition hover:bg-brand-secondary disabled:cursor-not-allowed disabled:opacity-40"
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
