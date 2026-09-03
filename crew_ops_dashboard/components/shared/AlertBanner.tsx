'use client';
import { useEffect, useState } from 'react';
import { AlertTriangle, X, Bell } from 'lucide-react';

export interface AlertBannerItem {
  id: string;
  message: string;
  onAction?: () => void;
  actionLabel?: string;
}

interface Props {
  alert: AlertBannerItem;
  onDismiss: (id: string) => void;
}

export function AlertBanner({ alert, onDismiss }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Slight delay so CSS transition plays
    const t = setTimeout(() => setVisible(true), 30);
    return () => clearTimeout(t);
  }, []);

  return (
    <div
      className="mx-2 mb-2 rounded-lg overflow-hidden shrink-0"
      style={{
        border: '1px solid rgba(239,68,68,0.5)',
        borderLeft: '3px solid #EF4444',
        background: 'rgba(30,10,10,0.97)',
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(8px)',
        transition: 'opacity 0.2s ease, transform 0.2s ease',
      }}
    >
      {/* Title row */}
      <div
        className="flex items-center justify-between px-3 py-1.5"
        style={{ background: 'rgba(239,68,68,0.12)', borderBottom: '1px solid rgba(239,68,68,0.2)' }}
      >
        <div className="flex items-center gap-1.5">
          <Bell size={11} style={{ color: '#F87171' }} />
          <span className="text-[10px] font-bold tracking-wider" style={{ color: '#F87171' }}>
            DISRUPTION ALERT
          </span>
        </div>
        <button onClick={() => onDismiss(alert.id)} style={{ color: 'var(--muted)' }}>
          <X size={12} />
        </button>
      </div>

      {/* Full message */}
      <div className="px-3 py-2">
        <p className="text-xs leading-relaxed" style={{ color: 'var(--text)' }}>
          {alert.message}
        </p>
        {alert.onAction && (
          <button
            onClick={() => { alert.onAction?.(); onDismiss(alert.id); }}
            className="mt-2 px-3 py-1 rounded text-[10px] font-semibold transition-colors hover:opacity-80"
            style={{ background: 'rgba(239,68,68,0.2)', color: '#F87171', border: '1px solid rgba(239,68,68,0.35)' }}
          >
            {alert.actionLabel ?? 'View in Inbox'}
          </button>
        )}
      </div>
    </div>
  );
}
