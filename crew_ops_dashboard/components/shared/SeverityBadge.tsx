'use client';
import { SEVERITY_COLORS } from '@/lib/constants';

export function SeverityBadge({ severity }: { severity: string }) {
  const c = SEVERITY_COLORS[severity] ?? SEVERITY_COLORS.LOW;
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide"
      style={{ background: c.badge + '22', color: c.badge, border: `1px solid ${c.badge}44` }}
    >
      {severity}
    </span>
  );
}
