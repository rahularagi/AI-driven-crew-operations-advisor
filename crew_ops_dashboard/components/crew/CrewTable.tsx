'use client';
import { useState } from 'react';
import { Search } from 'lucide-react';
import { useCrewFtl } from '@/hooks/useCrewFtl';
import { CrewDrawer } from './CrewDrawer';
import { MOCK_CREW } from '@/lib/constants';
import type { ToastItem } from '@/components/shared/Toast';

const STATUS_ICON: Record<string, string> = {
  AVAILABLE:   '✓',
  RESTING:     '💤',
  UNAVAILABLE: '✗',
};

function CrewRow({ crew, onView }: { crew: typeof MOCK_CREW[0]; onView: () => void }) {
  const { data: ftl } = useCrewFtl(crew.crew_id);
  const statusColor = ftl?.status === 'AVAILABLE' ? 'var(--success)'
    : ftl?.status === 'RESTING' ? 'var(--muted2)'
    : 'var(--danger)';
  const pct = ftl ? Math.min(100, (ftl.flight_hours_current_duty / ftl.max_duty_period_hours) * 100) : 0;
  const barColor = pct >= 85 ? '#EF4444' : pct >= 60 ? '#F59E0B' : '#10B981';

  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td className="px-3 py-2">
        <div className="text-xs font-medium" style={{ color: 'var(--text)' }}>{crew.full_name}</div>
        <div className="text-[10px]" style={{ color: 'var(--muted)' }}>{crew.crew_id}</div>
      </td>
      <td className="px-3 py-2 text-xs" style={{ color: 'var(--muted2)' }}>{crew.designation.replace('_', ' ')}</td>
      <td className="px-3 py-2 text-xs font-mono" style={{ color: 'var(--muted2)' }}>{crew.home_base}</td>
      <td className="px-3 py-2">
        <span className="text-xs font-semibold" style={{ color: statusColor }}>
          {ftl ? `${STATUS_ICON[ftl.status] ?? '?'} ${ftl.status}` : '—'}
        </span>
      </td>
      <td className="px-3 py-2">
        {ftl ? (
          <div className="flex items-center gap-2">
            <div className="w-16 h-1.5 rounded-full" style={{ background: 'var(--overlay)' }}>
              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: barColor }} />
            </div>
            <span className="text-[10px] font-mono" style={{ color: 'var(--muted)' }}>
              {ftl.flight_hours_current_duty.toFixed(1)}h
            </span>
          </div>
        ) : <span style={{ color: 'var(--muted)' }}>—</span>}
      </td>
      <td className="px-3 py-2">
        <button
          onClick={onView}
          className="px-2 py-0.5 rounded text-[10px] font-medium transition-colors hover:opacity-80"
          style={{ background: 'var(--raised)', color: 'var(--muted2)', border: '1px solid var(--border2)' }}
        >
          View
        </button>
      </td>
    </tr>
  );
}

interface Props {
  addToast: (t: Omit<ToastItem, 'id'>) => void;
  onAskAI: (msg: string) => void;
}

export function CrewTable({ addToast, onAskAI }: Props) {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<typeof MOCK_CREW[0] | null>(null);

  const filtered = MOCK_CREW.filter(c =>
    c.full_name.toLowerCase().includes(search.toLowerCase()) ||
    c.crew_id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full relative">
      {/* Search */}
      <div className="p-3 shrink-0" style={{ borderBottom: '1px solid var(--border)' }}>
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
          style={{ background: 'var(--raised)', border: '1px solid var(--border2)' }}
        >
          <Search size={12} style={{ color: 'var(--muted)' }} />
          <input
            className="flex-1 bg-transparent text-xs outline-none placeholder:text-[var(--muted)]"
            style={{ color: 'var(--text)' }}
            placeholder="Search crew…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs" style={{ borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--raised)', borderBottom: '1px solid var(--border)', position: 'sticky', top: 0 }}>
              {['Name', 'Role', 'Base', 'Status', 'FTL Today', 'Actions'].map(h => (
                <th key={h} className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wide" style={{ color: 'var(--muted)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(c => (
              <CrewRow key={c.crew_id} crew={c} onView={() => setSelected(c)} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Drawer */}
      {selected && (
        <>
          <div className="fixed inset-0 z-30" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setSelected(null)} />
          <CrewDrawer
            crew={selected}
            onClose={() => setSelected(null)}
            onAskAI={(msg) => { onAskAI(msg); setSelected(null); }}
            addToast={addToast}
          />
        </>
      )}
    </div>
  );
}
