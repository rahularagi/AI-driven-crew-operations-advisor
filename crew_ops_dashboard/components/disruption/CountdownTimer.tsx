'use client';
import { useEffect, useState } from 'react';
import { SEVERITY_WINDOWS } from '@/lib/constants';

export function CountdownTimer({ proposedAt, severity }: { proposedAt: string; severity: string }) {
  const windowMin = SEVERITY_WINDOWS[severity] ?? 0;
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    if (!windowMin) return;
    const deadline = new Date(proposedAt).getTime() + windowMin * 60_000;
    const tick = () => setRemaining(Math.max(0, Math.floor((deadline - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [proposedAt, windowMin]);

  if (!windowMin) return null;

  const m = Math.floor(remaining / 60);
  const s = remaining % 60;
  const isUrgent = remaining < 300;

  return (
    <span
      className="text-xs font-mono font-bold"
      style={{ color: isUrgent ? 'var(--danger)' : 'var(--muted2)' }}
    >
      {m}:{String(s).padStart(2, '0')}
    </span>
  );
}
