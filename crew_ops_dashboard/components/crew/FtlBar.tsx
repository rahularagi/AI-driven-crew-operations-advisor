'use client';
import { FTL_CAPS } from '@/lib/constants';

interface Props {
  value: number;
  cap: number;
  label: string;
}

export function FtlBar({ value, cap, label }: Props) {
  const pct = Math.min(100, (value / cap) * 100);
  const color = pct >= 85 ? '#EF4444' : pct >= 60 ? '#F59E0B' : '#10B981';

  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] w-28 shrink-0" style={{ color: 'var(--muted)' }}>{label}</span>
      <div className="flex-1 h-1.5 rounded-full" style={{ background: 'var(--overlay)' }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-[10px] w-20 text-right font-mono" style={{ color: 'var(--muted2)' }}>
        {value.toFixed(1)} / {cap}
      </span>
    </div>
  );
}
