import { useState } from "react";
import LeftPanel from "./LeftPanel";
import RightPanel from "./RightPanel";

type Speaker = 'user' | 'interviewer';

interface ChatItem {
  id: string;
  speaker: Speaker;
  content: string;
  timestamp: string;
  isPartial?: boolean;
}

interface Props {
  sessionId?: string;
}

export default function Layout({ sessionId = "default" }: Props) {
  const [activePanel, setActivePanel] = useState<'left' | 'right'>('left');
  const [chatHistory, setChatHistory] = useState<ChatItem[]>([]);

  const handleUserText = (text: string, isPartial: boolean = false) => {
    if (isPartial) {
      const partialId = 'user-partial';
      setChatHistory(prev => {
        const filtered = prev.filter(msg => msg.id !== partialId);
        return [
          ...filtered,
          {
            id: partialId,
            speaker: 'user',
            content: text,
            timestamp: new Date().toISOString(),
            isPartial: true
          }
        ];
      });
    } else {
      setChatHistory(prev => {
        const filtered = prev.filter(msg => msg.id !== 'user-partial');
        return [
          ...filtered,
          {
            id: Date.now().toString(),
            speaker: 'user',
            content: text,
            timestamp: new Date().toISOString(),
            isPartial: false
          }
        ];
      });
    }
  };

  const handleInterviewerText = (text: string, isPartial: boolean = false) => {
    if (isPartial) {
      const partialId = 'interviewer-partial';
      setChatHistory(prev => {
        const filtered = prev.filter(msg => msg.id !== partialId);
        return [
          ...filtered,
          {
            id: partialId,
            speaker: 'interviewer',
            content: text,
            timestamp: new Date().toISOString(),
            isPartial: true
          }
        ];
      });
    } else {
      setChatHistory(prev => {
        const filtered = prev.filter(msg => msg.id !== 'interviewer-partial');
        return [
          ...filtered,
          {
            id: Date.now().toString(),
            speaker: 'interviewer',
            content: text,
            timestamp: new Date().toISOString(),
            isPartial: false
          }
        ];
      });
    }
  };

  return (
    <div className="flex min-h-dvh flex-col bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 py-6 sm:flex-row">
          <div className="text-center sm:text-left">
            <h1 className="flex items-center justify-center gap-3 text-3xl font-semibold text-white sm:justify-start">
              <span className="text-4xl">🎯</span>
              11面试
            </h1>
            <p className="text-sm font-medium text-slate-300">面试辅助</p>
          </div>
        </div>
      </header>

      <nav className="sticky top-0 z-10 flex w-full border-b border-slate-800 bg-slate-900/80 backdrop-blur md:hidden">
        <button
          className={`flex flex-1 items-center justify-center gap-2 px-3 py-3 text-sm font-semibold transition ${
            activePanel === 'left'
              ? 'border-b-2 border-brand-primary/70 bg-brand-primary/20 text-brand-primary'
              : 'text-slate-300 hover:bg-slate-800/70 hover:text-brand-primary'
          }`}
          onClick={() => setActivePanel('left')}
        >
          <span className="text-lg">💬</span>
          <span>聊天记录</span>
        </button>
        <button
          className={`flex flex-1 items-center justify-center gap-2 px-3 py-3 text-sm font-semibold transition ${
            activePanel === 'right'
              ? 'border-b-2 border-brand-primary/70 bg-brand-primary/20 text-brand-primary'
              : 'text-slate-300 hover:bg-slate-800/70 hover:text-brand-primary'
          }`}
          onClick={() => setActivePanel('right')}
        >
          <span className="text-lg">🤖</span>
          <span>面试助手</span>
        </button>
      </nav>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-6 md:flex-row md:items-start md:gap-8">
        <div
          className={`${
            activePanel === 'left' ? 'flex' : 'hidden'
          } md:flex md:min-h-[28rem] md:flex-1 md:overflow-hidden`}
        >
          <LeftPanel
            chatHistory={chatHistory}
            onUserText={handleUserText}
            onInterviewerText={handleInterviewerText}
            sessionId={sessionId}
          />
        </div>
        <div
          className={`${
            activePanel === 'right' ? 'block' : 'hidden'
          } md:block md:w-[360px] md:flex-none md:self-stretch`}
        >
          <RightPanel chatHistory={chatHistory} />
        </div>
      </main>
    </div>
  );
}
