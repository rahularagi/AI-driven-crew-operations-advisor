'use client';
import { X } from 'lucide-react';
import { useCrewFtl } from '@/hooks/useCrewFtl';
import { FtlBar } from './FtlBar';
import { FTL_CAPS } from '@/lib/constants';

interface CrewBasic {
  crew_id: string;
  full_name: string;
  designation: string;
  role: string;
  home_base: string;
}

interface Props {
  crew: CrewBasic;
  onClose: () => void;
  onAskAI: (msg: string) => void;
}

const STATUS_ICON: Record<string, string> = {
  AVAILABLE:   '✓',
  RESTING:     '💤',
  UNAVAILABLE: '✗',
};

export function CrewDrawer({ crew, onClose, onAskAI }: Props) {
  const { data: ftl, isLoading } = useCrewFtl(crew.crew_id);

  const statusColor = ftl?.status === 'AVAILABLE' ? 'var(--success)'
    : ftl?.status === 'RESTING' ? 'var(--muted2)'
    : 'var(--danger)';

  return (
    <div
      className="drawer-enter fixed top-0 right-0 h-full w-80 z-40 flex flex-col overflow-y-auto"
      style={{ background: 'var(--surface)', borderLeft: '1px solid var(--border)' }}
    >
      {/* Header */}
      <div className="flex items-start justify-between p-4" style={{ borderBottom: '1px solid var(--border)' }}>
        <div>
          <div className="font-semibold text-sm" style={{ color: 'var(--text)' }}>{crew.full_name}</div>
          <div className="text-[10px] mt-0.5" style={{ color: 'var(--muted)' }}>
            {crew.designation} · {crew.role} · {crew.home_base}
          </div>
          {ftl && (
            <div className="text-xs mt-1 font-semibold" style={{ color: statusColor }}>
              {STATUS_ICON[ftl.status] ?? '?'} {ftl.status}
            </div>
          )}
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-[var(--raised)]" style={{ color: 'var(--muted)' }}>
          <X size={16} />
        </button>
      </div>

      {isLoading && <p className="text-xs text-center mt-4" style={{ color: 'var(--muted)' }}>Loading FTL…</p>}

      {ftl && (
        <div className="p-4 flex flex-col gap-4">
          {/* FTL State */}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wide mb-2" style={{ color: 'var(--muted)' }}>FTL State</div>
            <div className="flex flex-col gap-1.5">
              <FtlBar value={ftl.flight_hours_current_duty} cap={ftl.max_duty_period_hours} label="Current duty" />
              <FtlBar value={ftl.flight_hours_28_day}       cap={FTL_CAPS.flight_hours_28_day}   label="28-day hours" />
              <FtlBar value={ftl.duty_hours_7_day}          cap={FTL_CAPS.duty_hours_7_day}       label="7-day hours" />
              <FtlBar value={ftl.consecutive_duty_days}     cap={FTL_CAPS.consecutive_duty_days}  label="Consec. days" />
            </div>
          </div>

          {/* Location */}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wide mb-1" style={{ color: 'var(--muted)' }}>Location</div>
            <div className="text-xs" style={{ color: 'var(--text)' }}>
              {ftl.current_airport}
              {ftl.at_home_base && <span className="ml-1 text-[10px]" style={{ color: 'var(--success)' }}>(home base)</span>}
            </div>
          </div>

          {/* Timestamps */}
          {ftl.last_updated && (
            <div className="text-[10px]" style={{ color: 'var(--muted)' }}>
              Updated: {new Date(ftl.last_updated).toLocaleString('en-GB')}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="mt-auto p-4 flex gap-2" style={{ borderTop: '1px solid var(--border)' }}>
        <button
          onClick={() => onAskAI(`FTL status for ${crew.crew_id}`)}
          className="flex-1 py-1.5 rounded text-xs font-medium transition-colors"
          style={{ background: 'var(--brand-dim)', color: 'var(--brand)', border: '1px solid rgba(59,130,246,0.3)' }}
        >
          Ask AI
        </button>
      </div>
    </div>
  );
}
