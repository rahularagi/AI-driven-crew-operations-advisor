'use client';
import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Bot } from 'lucide-react';
import { api } from '@/lib/api';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage, ChatResponse } from '@/types';
import type { ToastItem } from '@/components/shared/Toast';

const SESSION_KEY = 'crewops_session_id';

function getSessionId(): string {
  if (typeof window === 'undefined') return 'sess-ssr';
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) { id = `sess-${crypto.randomUUID()}`; localStorage.setItem(SESSION_KEY, id); }
  return id;
}

const QUICK_CHIPS = [
  "Who's on AI305?",
  "Show today's delays",
  "Pending proposals",
  "FTL status C-007",
];

interface Props {
  addToast: (t: Omit<ToastItem, 'id'>) => void;
  injectMessage?: string;
}

export function ChatPanel({ addToast, injectMessage }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (injectMessage) { setInput(injectMessage); }
  }, [injectMessage]);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: ChatMessage = { role: 'user', content: text.trim(), timestamp: Date.now() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    try {
      const res = await api.chat({ session_id: getSessionId(), message: text.trim(), user_id: 'ops_controller_01' }) as ChatResponse;
      let content = res.response;
      // Handle push notification drain
      if (content.startsWith('[ALERT]')) {
        const parts = content.split('\n\n---\n');
        const alertPart = parts[0].replace('[ALERT]\n', '');
        content = parts.slice(1).join('\n\n---\n');
        addToast({ type: 'critical', message: alertPart.slice(0, 120) });
      }
      const aiMsg: ChatMessage = {
        role: 'assistant',
        content,
        mode: res.mode,
        requires_confirmation: res.requires_confirmation,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch {
      addToast({ type: 'critical', message: 'Chat unavailable — check LLM_PROVIDER in .env' });
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error: could not reach AI backend.', timestamp: Date.now() }]);
    } finally {
      setLoading(false);
    }
  }, [loading, addToast]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 py-2 shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <Bot size={13} style={{ color: 'var(--brand)' }} />
        <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text)' }}>AI Assistant</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3">
        {messages.length === 0 && (
          <p className="text-xs text-center mt-6" style={{ color: 'var(--muted)' }}>
            Ask about crew, flights, FTL, or disruptions
          </p>
        )}
        {messages.map((m, i) => (
          <MessageBubble
            key={i}
            msg={m}
            onConfirm={() => send('YES')}
            onCancel={() => send('NO')}
          />
        ))}
        {loading && (
          <div className="flex justify-start mb-2">
            <div className="px-3 py-2 rounded-lg text-xs" style={{ background: 'var(--raised)', color: 'var(--muted)' }}>
              <span className="blink">●●●</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Quick chips */}
      <div className="px-3 pb-1 flex gap-1.5 flex-wrap shrink-0">
        {QUICK_CHIPS.map(chip => (
          <button
            key={chip}
            onClick={() => send(chip)}
            className="px-2 py-0.5 rounded-full text-[10px] transition-colors hover:opacity-80"
            style={{ background: 'var(--raised)', color: 'var(--muted2)', border: '1px solid var(--border2)' }}
          >
            {chip}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="px-3 pb-3 pt-1 shrink-0">
        <div
          className="flex items-center gap-2 rounded-lg px-3 py-2"
          style={{ background: 'var(--raised)', border: '1px solid var(--border2)' }}
        >
          <input
            className="flex-1 bg-transparent text-xs outline-none placeholder:text-[var(--muted)]"
            style={{ color: 'var(--text)' }}
            placeholder="Ask anything…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send(input)}
          />
          <button
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            className="p-1 rounded transition-colors disabled:opacity-40"
            style={{ color: 'var(--brand)' }}
          >
            <Send size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
