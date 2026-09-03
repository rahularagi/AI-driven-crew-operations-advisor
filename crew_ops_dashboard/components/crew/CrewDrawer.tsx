'use client';
import { useState } from 'react';
import { X, MapPin, Clock, User } from 'lucide-react';
import { useCrewFtl } from '@/hooks/useCrewFtl';
import { FtlBar } from './FtlBar';
import { FTL_CAPS } from '@/lib/constants';
import { api } from '@/lib/api';
import type { ToastItem } from '@/components/shared/Toast';

interface CrewBasic {
  crew_id: string;
  full_name: string;
  designation: string;
  role: string;
  home_base: string;
}

const REASONS = ['SICK_CALL', 'PERSONAL', 'TRAINING', 'OTHER'] as const;

interface Props {
  crew: CrewBasic;
  onClose: () => void;
  onAskAI: (msg: string) => void;
  addToast?: (t: Omit<ToastItem, 'id'>) => void;
}

const STATUS_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  AVAILABLE:   { color: '#10B981', bg: 'rgba(16,185,129,0.12)', label: '● Available' },
  RESTING:     { color: '#F59E0B', bg: 'rgba(245,158,11,0.12)',  label: '◐ Resting'   },
  UNAVAILABLE: { color: '#EF4444', bg: 'rgba(239,68,68,0.12)',   label: '✕ Unavailable' },
};

function initials(name: string) {
  return name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
}

export function CrewDrawer({ crew, onClose, onAskAI, addToast }: Props) {
  const { data: ftl, isLoading } = useCrewFtl(crew.crew_id);
  const status = STATUS_STYLES[ftl?.status ?? ''] ?? { color: '#6B7280', bg: 'rgba(107,114,128,0.12)', label: '— Unknown' };

  return (
    <div
      className="drawer-enter fixed top-0 right-0 h-full w-80 z-40 flex flex-col overflow-y-auto"
      style={{ background: '#0D1424', borderLeft: '2px solid #1E3A5F' }}
    >
      {/* Accent strip */}
      <div style={{ height: 3, background: 'linear-gradient(90deg, #3B82F6, #6366F1)' }} />

      {/* Header */}
      <div className="p-4 flex items-start gap-3" style={{ borderBottom: '1px solid #1E2D45' }}>
        {/* Avatar */}
        <div
          className="shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold"
          style={{ background: 'linear-gradient(135deg, #1E3A5F, #312E81)', color: '#93C5FD' }}
        >
          {initials(crew.full_name)}
        </div>

        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm truncate" style={{ color: '#F1F5F9' }}>{crew.full_name}</div>
          <div className="text-[10px] mt-0.5" style={{ color: '#64748B' }}>
            {crew.crew_id} · {crew.designation.replace('_', ' ')} · {crew.role}
          </div>
          {ftl && (
            <span
              className="inline-block mt-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold"
              style={{ background: status.bg, color: status.color }}
            >
              {status.label}
            </span>
          )}
        </div>

        <button
          onClick={onClose}
          className="shrink-0 p-1 rounded-lg transition-colors hover:bg-[#1E2D45]"
          style={{ color: '#475569' }}
        >
          <X size={15} />
        </button>
      </div>

      {isLoading && (
        <p className="text-xs text-center mt-6" style={{ color: '#475569' }}>Loading…</p>
      )}

      {ftl && (
        <div className="p-4 flex flex-col gap-3">

          {/* Location card */}
          <div
            className="rounded-lg px-3 py-2.5 flex items-center gap-2"
            style={{ background: '#111D2E', border: '1px solid #1E2D45' }}
          >
            <MapPin size={12} style={{ color: '#3B82F6', flexShrink: 0 }} />
            <div>
              <div className="text-xs font-semibold" style={{ color: '#CBD5E1' }}>{ftl.current_airport}</div>
              {ftl.at_home_base && (
                <div className="text-[10px]" style={{ color: '#10B981' }}>At home base</div>
              )}
            </div>
          </div>

          {/* FTL card */}
          <div
            className="rounded-lg p-3"
            style={{ background: '#111D2E', border: '1px solid #1E2D45' }}
          >
            <div className="flex items-center gap-1.5 mb-2.5">
              <Clock size={11} style={{ color: '#6366F1' }} />
              <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: '#6366F1' }}>FTL State</span>
            </div>
            <div className="flex flex-col gap-2">
              <FtlBar value={ftl.flight_hours_current_duty} cap={ftl.max_duty_period_hours} label="Current duty" />
              <FtlBar value={ftl.flight_hours_28_day}       cap={FTL_CAPS.flight_hours_28_day}  label="28-day hours" />
              <FtlBar value={ftl.duty_hours_7_day}          cap={FTL_CAPS.duty_hours_7_day}      label="7-day hours" />
              <FtlBar value={ftl.consecutive_duty_days}     cap={FTL_CAPS.consecutive_duty_days} label="Consec. days" />
            </div>
          </div>

          {/* Updated */}
          {ftl.last_updated && (
            <div className="text-[10px] text-right" style={{ color: '#334155' }}>
              Updated {new Date(ftl.last_updated).toLocaleString('en-GB')}
            </div>
          )}
        </div>
      )}

      {/* Mark Unavailable */}
      <div className="px-4 pb-3">
        <UnavailableForm crewId={crew.crew_id} addToast={addToast} />
      </div>

      {/* Actions */}
      <div className="mt-auto p-4" style={{ borderTop: '1px solid #1E2D45' }}>
        <button
          onClick={() => onAskAI(`FTL status for ${crew.crew_id}`)}
          className="w-full py-2 rounded-lg text-xs font-semibold transition-colors"
          style={{ background: 'linear-gradient(90deg, #1E3A5F, #1E1B4B)', color: '#93C5FD', border: '1px solid #2D4A7A' }}
        >
          Ask AI about {crew.crew_id}
        </button>
      </div>
    </div>
  );
}

function UnavailableForm({ crewId, addToast }: { crewId: string; addToast?: (t: Omit<ToastItem, 'id'>) => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [open, setOpen]       = useState(false);
  const [reason, setReason]   = useState<string>(REASONS[0]);
  const [startDate, setStart] = useState(today);
  const [endDate, setEnd]     = useState(today);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    try {
      await api.markUnavailable(crewId, { reason, start_date: startDate, end_date: endDate });
      addToast?.({ type: 'success', message: `${crewId} marked unavailable (${reason})` });
      setOpen(false);
    } catch {
      addToast?.({ type: 'critical', message: `Failed to mark ${crewId} unavailable` });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full py-1.5 rounded-lg text-xs font-semibold transition-colors"
        style={{
          background: open ? '#1A0A0A' : 'rgba(239,68,68,0.08)',
          color: '#EF4444',
          border: '1px solid rgba(239,68,68,0.25)',
        }}
      >
        {open ? '✕ Cancel' : 'Mark Unavailable'}
      </button>

      {open && (
        <div
          className="mt-2 rounded-lg p-3 flex flex-col gap-2.5"
          style={{ background: '#0F1A2A', border: '1px solid #1E2D45' }}
        >
          <div>
            <label className="text-[10px] uppercase tracking-widest font-semibold" style={{ color: '#475569' }}>Reason</label>
            <select
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="w-full mt-1 px-2 py-1.5 rounded-md text-xs outline-none"
              style={{ background: '#111D2E', color: '#CBD5E1', border: '1px solid #1E2D45' }}
            >
              {REASONS.map(r => <option key={r} value={r}>{r.replace('_', ' ')}</option>)}
            </select>
          </div>

          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[10px] uppercase tracking-widest font-semibold" style={{ color: '#475569' }}>From</label>
              <input
                type="date" value={startDate} onChange={e => setStart(e.target.value)}
                className="w-full mt-1 px-2 py-1.5 rounded-md text-xs outline-none"
                style={{ background: '#111D2E', color: '#CBD5E1', border: '1px solid #1E2D45' }}
              />
            </div>
            <div className="flex-1">
              <label className="text-[10px] uppercase tracking-widest font-semibold" style={{ color: '#475569' }}>To</label>
              <input
                type="date" value={endDate} onChange={e => setEnd(e.target.value)}
                className="w-full mt-1 px-2 py-1.5 rounded-md text-xs outline-none"
                style={{ background: '#111D2E', color: '#CBD5E1', border: '1px solid #1E2D45' }}
              />
            </div>
          </div>

          <button
            onClick={submit}
            disabled={loading}
            className="py-1.5 rounded-md text-xs font-semibold disabled:opacity-50 transition-opacity"
            style={{ background: '#7F1D1D', color: '#FCA5A5', border: '1px solid #991B1B' }}
          >
            {loading ? 'Submitting…' : 'Confirm Mark Unavailable'}
          </button>
        </div>
      )}
    </div>
  );
}
