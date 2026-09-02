'use client';
import { MODE_COLORS } from '@/lib/constants';
import type { ChatMessage } from '@/types';

interface Props {
  msg: ChatMessage;
  onConfirm?: () => void;
  onCancel?: () => void;
}

export function MessageBubble({ msg, onConfirm, onCancel }: Props) {
  const isUser = msg.role === 'user';
  const modeColor = msg.mode ? (MODE_COLORS[msg.mode] ?? '#374151') : undefined;

  if (isUser) {
    return (
      <div className="flex justify-end mb-2">
        <div
          className="max-w-[80%] px-3 py-2 rounded-lg text-xs"
          style={{ background: 'var(--brand-dim)', color: 'var(--text)', borderLeft: '2px solid var(--brand)' }}
        >
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-2">
      <div
        className="max-w-[90%] px-3 py-2 rounded-lg text-xs"
        style={{ background: 'var(--raised)', color: 'var(--text)', borderLeft: `2px solid ${modeColor ?? 'var(--border2)'}` }}
      >
        {msg.mode && (
          <div className="flex items-center gap-1 mb-1">
            <span className="text-[10px] font-bold uppercase" style={{ color: modeColor }}>{msg.mode}</span>
          </div>
        )}
        <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
        {msg.requires_confirmation && (
          <div className="flex gap-2 mt-2">
            <button
              onClick={onConfirm}
              className="px-2 py-1 rounded text-[10px] font-bold"
              style={{ background: 'rgba(16,185,129,0.2)', color: 'var(--success)', border: '1px solid rgba(16,185,129,0.4)' }}
            >
              ✓ CONFIRM
            </button>
            <button
              onClick={onCancel}
              className="px-2 py-1 rounded text-[10px] font-bold"
              style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--danger)', border: '1px solid rgba(239,68,68,0.3)' }}
            >
              ✗ CANCEL
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
