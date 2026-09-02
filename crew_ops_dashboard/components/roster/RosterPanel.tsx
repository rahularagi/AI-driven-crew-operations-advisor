'use client';
import { useState } from 'react';
import { ChevronLeft, ChevronRight, RefreshCw, Check } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRoster } from '@/hooks/useRoster';
import { useProposals } from '@/hooks/useProposals';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { api } from '@/lib/api';
import type { RosterRow } from '@/types';
import type { ToastItem } from '@/components/shared/Toast';

function getWeekDates(offset: number): { start: string; end: string; days: Date[] } {
  const now = new Date();
  const mon = new Date(now);
  mon.setDate(now.getDate() - now.getDay() + 1 + offset * 7);
  const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(mon); d.setDate(mon.getDate() + i); return d; });
  const fmt = (d: Date) => d.toISOString().split('T')[0];
  return { start: fmt(days[0]), end: fmt(days[6]), days };
}

function groupByLeg(rows: RosterRow[]): Map<string, RosterRow[]> {
  const m = new Map<string, RosterRow[]>();
  for (const r of rows) {
    if (!m.has(r.leg_id)) m.set(r.leg_id, []);
    m.get(r.leg_id)!.push(r);
  }
  return m;
}

interface Props {
  addToast: (t: Omit<ToastItem, 'id'>) => void;
}

export function RosterPanel({ addToast }: Props) {
  const [weekOffset, setWeekOffset] = useState(0);
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const { start, end, days } = getWeekDates(weekOffset);
  const { data: rows = [], isLoading, error, refetch } = useRoster(start, end);
  const { data: proposals = [] } = useProposals();
  const qc = useQueryClient();
  const disruptedLegs = new Set(proposals.map(p => p.leg_id));

  const approve = useMutation({
    mutationFn: (legId: string) => api.approveLeg(legId, 'ops_controller_01'),
    onSuccess: (_, legId) => {
      addToast({ type: 'success', message: `✓ Leg ${legId} approved` });
      qc.invalidateQueries({ queryKey: ['roster'] });
    },
    onError: () => addToast({ type: 'critical', message: 'Approve failed' }),
  });

  const grouped = groupByLeg(rows);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text)' }}>Roster</span>
          <div className="flex items-center gap-1 ml-2">
            {(['grid', 'list'] as const).map(v => (
              <button
                key={v}
                onClick={() => setView(v)}
                className="px-2 py-0.5 rounded text-[10px] font-medium capitalize transition-colors"
                style={{
                  background: view === v ? 'var(--brand)' : 'var(--raised)',
                  color: view === v ? '#fff' : 'var(--muted)',
                }}
              >
                {v}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setWeekOffset(o => o - 1)} className="p-1 rounded hover:bg-[var(--raised)]" style={{ color: 'var(--muted)' }}>
            <ChevronLeft size={13} />
          </button>
          <span className="text-[10px] w-28 text-center" style={{ color: 'var(--muted2)' }}>
            {days[0].toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })} – {days[6].toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}
          </span>
          <button onClick={() => setWeekOffset(o => o + 1)} className="p-1 rounded hover:bg-[var(--raised)]" style={{ color: 'var(--muted)' }}>
            <ChevronRight size={13} />
          </button>
          <button onClick={() => refetch()} className="p-1 rounded hover:bg-[var(--raised)] ml-1" style={{ color: 'var(--muted)' }}>
            <RefreshCw size={12} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {isLoading && <p className="text-xs text-center mt-4" style={{ color: 'var(--muted)' }}>Loading…</p>}
        {error && <p className="text-xs text-center mt-4" style={{ color: 'var(--danger)' }}>Backend offline</p>}

        {!isLoading && !error && view === 'grid' && (
          <table className="w-full text-[10px]" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--raised)', borderBottom: '1px solid var(--border)' }}>
                <th className="text-left px-3 py-1.5 font-semibold w-28" style={{ color: 'var(--muted)' }}>FLIGHT</th>
                {days.map(d => (
                  <th key={d.toISOString()} className="text-center px-1 py-1.5 font-semibold" style={{ color: 'var(--muted)' }}>
                    {d.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit' })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grouped.size === 0 && (
                <tr><td colSpan={8} className="text-center py-6" style={{ color: 'var(--muted)' }}>No roster data for this week</td></tr>
              )}
              {Array.from(grouped.entries()).map(([legId, legRows]) => {
                const sample = legRows[0];
                const legDate = new Date(sample.scheduled_departure).toISOString().split('T')[0];
                const isDisrupted = disruptedLegs.has(legId);
                const isDraft = legRows.some(r => r.status === 'DRAFT');
                const statusColor = isDisrupted ? '#EF4444' : isDraft ? '#F59E0B' : '#10B981';
                const bg = isDisrupted ? 'rgba(239,68,68,0.08)' : isDraft ? 'rgba(245,158,11,0.08)' : 'rgba(16,185,129,0.06)';

                return (
                  <tr key={legId} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-3 py-2">
                      <div className="font-semibold" style={{ color: 'var(--text)' }}>{sample.flight_number}</div>
                      <div style={{ color: 'var(--muted)' }}>{sample.origin_iata}→{sample.destination_iata}</div>
                    </td>
                    {days.map(d => {
                      const dayStr = d.toISOString().split('T')[0];
                      const isLegDay = legDate === dayStr;
                      return (
                        <td key={dayStr} className="px-1 py-1 text-center">
                          {isLegDay ? (
                            <div
                              className={`rounded px-1 py-1 ${isDisrupted ? 'pulse-ring' : ''}`}
                              style={{ background: bg, border: `1px solid ${statusColor}44` }}
                            >
                              <div className="font-semibold" style={{ color: statusColor }}>
                                {isDisrupted ? '⚠' : isDraft ? '~' : '✓'}
                              </div>
                              <div style={{ color: 'var(--muted)' }}>{legRows.map(r => r.crew_id).join(' ')}</div>
                              {isDraft && !isDisrupted && (
                                <button
                                  onClick={() => approve.mutate(legId)}
                                  className="mt-0.5 px-1 py-0.5 rounded text-[9px] font-bold"
                                  style={{ background: 'rgba(245,158,11,0.2)', color: '#F59E0B' }}
                                >
                                  Approve
                                </button>
                              )}
                            </div>
                          ) : (
                            <span style={{ color: 'var(--border2)' }}>·</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {!isLoading && !error && view === 'list' && (
          <div>
            {grouped.size === 0 && (
              <p className="text-xs text-center mt-6" style={{ color: 'var(--muted)' }}>No roster data for this week</p>
            )}
            {Array.from(grouped.entries()).map(([legId, legRows]) => {
              const sample = legRows[0];
              const isDisrupted = disruptedLegs.has(legId);
              const isDraft = legRows.some(r => r.status === 'DRAFT');
              const dep = new Date(sample.scheduled_departure).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
              const statusLabel = isDisrupted ? 'DISRUPTED' : isDraft ? 'DRAFT' : 'PUBLISHED';

              return (
                <div
                  key={legId}
                  className="flex items-center gap-3 px-3 py-2"
                  style={{ borderBottom: '1px solid var(--border)', borderLeft: `3px solid ${isDisrupted ? '#EF4444' : isDraft ? '#F59E0B' : '#10B981'}` }}
                >
                  <span className="font-mono text-xs font-semibold w-14" style={{ color: 'var(--text)' }}>{sample.flight_number}</span>
                  <span className="text-xs w-20" style={{ color: 'var(--muted2)' }}>{sample.origin_iata}→{sample.destination_iata}</span>
                  <span className="text-xs w-12" style={{ color: 'var(--muted)' }}>{dep}</span>
                  <StatusBadge status={statusLabel} />
                  <span className="text-[10px] flex-1" style={{ color: 'var(--muted)' }}>
                    {legRows.map(r => r.crew_id).join(', ')}
                  </span>
                  {isDraft && !isDisrupted && (
                    <button
                      onClick={() => approve.mutate(legId)}
                      className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold"
                      style={{ background: 'rgba(245,158,11,0.15)', color: '#F59E0B', border: '1px solid rgba(245,158,11,0.3)' }}
                    >
                      <Check size={10} /> Approve
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
