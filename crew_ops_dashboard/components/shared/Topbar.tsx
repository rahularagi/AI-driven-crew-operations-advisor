'use client';
import { Plane, Bell } from 'lucide-react';
import { useHealth } from '@/hooks/useHealth';

interface TopbarProps {
  pendingCount: number;
  onAlertsClick: () => void;
}

export function Topbar({ pendingCount, onAlertsClick }: TopbarProps) {
  const { data: health } = useHealth();
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
  const isLive = health?.database === 'connected';

  return (
    <div
      className="flex items-center justify-between px-4 h-11 shrink-0"
      style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2">
        <Plane size={16} style={{ color: 'var(--brand)' }} />
        <span className="font-bold text-sm tracking-wide" style={{ color: 'var(--text)' }}>CrewOps</span>
        <span className="text-xs ml-2" style={{ color: 'var(--muted)' }}>{dateStr}</span>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${isLive ? 'blink' : ''}`}
            style={{ background: isLive ? 'var(--success)' : 'var(--muted)' }}
          />
          <span className="text-xs" style={{ color: isLive ? 'var(--success)' : 'var(--muted)' }}>
            {isLive ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
        <button
          onClick={onAlertsClick}
          className="relative p-1.5 rounded hover:bg-[var(--raised)] transition-colors"
          style={{ color: 'var(--muted)' }}
        >
          <Bell size={16} />
          {pendingCount > 0 && (
            <span
              className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center"
              style={{ background: 'var(--danger)', color: '#fff' }}
            >
              {pendingCount > 9 ? '9+' : pendingCount}
            </span>
          )}
        </button>
        <div
          className="px-2 py-1 rounded text-xs font-medium"
          style={{ background: 'var(--raised)', color: 'var(--muted2)' }}
        >
          OC ops_01
        </div>
      </div>
    </div>
  );
}
