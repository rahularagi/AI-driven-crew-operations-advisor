'use client';
import { STATUS_COLORS } from '@/lib/constants';

export function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? '#6B7280';
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide"
      style={{ background: color + '22', color, border: `1px solid ${color}44` }}
    >
      {status}
    </span>
  );
}
