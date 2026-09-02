'use client';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { useProposals } from '@/hooks/useProposals';
import { ProposalCard } from './ProposalCard';
import type { ToastItem } from '@/components/shared/Toast';

interface Props {
  addToast: (t: Omit<ToastItem, 'id'>) => void;
}

export function DisruptionInbox({ addToast }: Props) {
  const { data: proposals = [], isLoading, error, refetch } = useProposals();

  return (
    <div className="flex flex-col h-full">
      <div
        className="flex items-center justify-between px-3 py-2 shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <AlertTriangle size={13} style={{ color: 'var(--warning)' }} />
          <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text)' }}>
            Disruption Inbox
          </span>
          {proposals.length > 0 && (
            <span
              className="px-1.5 py-0.5 rounded-full text-[10px] font-bold"
              style={{ background: 'var(--danger)', color: '#fff' }}
            >
              {proposals.length}
            </span>
          )}
        </div>
        <button onClick={() => refetch()} className="p-1 rounded hover:bg-[var(--raised)]" style={{ color: 'var(--muted)' }}>
          <RefreshCw size={12} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {isLoading && <p className="text-xs text-center mt-4" style={{ color: 'var(--muted)' }}>Loading…</p>}
        {error && <p className="text-xs text-center mt-4" style={{ color: 'var(--danger)' }}>Backend offline</p>}
        {!isLoading && !error && proposals.length === 0 && (
          <div className="flex flex-col items-center justify-center h-24 gap-1">
            <span className="text-lg">✓</span>
            <p className="text-xs" style={{ color: 'var(--muted)' }}>No pending proposals</p>
          </div>
        )}
        {proposals.map(p => (
          <ProposalCard key={p.proposal_id} proposal={p} addToast={addToast} />
        ))}
      </div>
    </div>
  );
}
