'use client';
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';

export interface ToastItem {
  id: string;
  type: 'critical' | 'success' | 'info';
  message: string;
}

const BORDER: Record<string, string> = {
  critical: '#EF4444',
  success:  '#10B981',
  info:     '#3B82F6',
};

export function Toast({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
  useEffect(() => {
    if (item.type !== 'critical') {
      const t = setTimeout(() => onDismiss(item.id), 5000);
      return () => clearTimeout(t);
    }
  }, [item, onDismiss]);

  return (
    <div
      className="fade-in flex items-start gap-2 p-3 rounded-lg min-w-[280px] max-w-[360px]"
      style={{ background: 'var(--surface)', border: `1px solid ${BORDER[item.type]}`, borderLeft: `3px solid ${BORDER[item.type]}` }}
    >
      <span className="text-sm flex-1" style={{ color: 'var(--text)' }}>{item.message}</span>
      <button onClick={() => onDismiss(item.id)} className="text-[var(--muted)] hover:text-[var(--text)]">
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastContainer({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: string) => void }) {
  return (
    <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50">
      {toasts.slice(-3).map(t => <Toast key={t.id} item={t} onDismiss={onDismiss} />)}
    </div>
  );
}
