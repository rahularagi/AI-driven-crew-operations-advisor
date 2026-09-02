'use client';
import { useState } from 'react';
import { Check, X, ChevronDown } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { SEVERITY_COLORS } from '@/lib/constants';
import { SeverityBadge } from '@/components/shared/SeverityBadge';
import { CountdownTimer } from './CountdownTimer';
import type { Proposal } from '@/types';
import type { ToastItem } from '@/components/shared/Toast';

interface Props {
  proposal: Proposal;
  addToast: (t: Omit<ToastItem, 'id'>) => void;
}

export function ProposalCard({ proposal, addToast }: Props) {
  const qc = useQueryClient();
  const [dismissed, setDismissed] = useState(false);
  const colors = SEVERITY_COLORS[proposal.severity] ?? SEVERITY_COLORS.LOW;

  const accept = useMutation({
    mutationFn: () => api.acceptProposal(proposal.proposal_id, 'ops_controller_01'),
    onSuccess: () => {
      setDismissed(true);
      addToast({ type: 'success', message: `✓ Proposal ${proposal.proposal_id} accepted` });
      setTimeout(() => qc.invalidateQueries({ queryKey: ['proposals'] }), 600);
    },
    onError: () => addToast({ type: 'critical', message: `Failed to accept ${proposal.proposal_id}` }),
  });

  const reject = useMutation({
    mutationFn: () => api.rejectProposal(proposal.proposal_id, { decided_by: 'ops_controller_01', rejection_reason: 'controller rejected' }),
    onSuccess: () => {
      addToast({ type: 'info', message: `Proposal ${proposal.proposal_id} rejected — re-proposing` });
      qc.invalidateQueries({ queryKey: ['proposals'] });
    },
    onError: () => addToast({ type: 'critical', message: `Failed to reject ${proposal.proposal_id}` }),
  });

  if (dismissed) return null;

  const isCritical = proposal.severity === 'CRITICAL';
  const depTime = proposal.scheduled_departure
    ? new Date(proposal.scheduled_departure).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
    : '—';
  const minsToDepart = proposal.scheduled_departure
    ? Math.round((new Date(proposal.scheduled_departure).getTime() - Date.now()) / 60_000)
    : null;

  return (
    <div
      className={`rounded-lg overflow-hidden mb-2 ${isCritical ? 'pulse-ring' : ''}`}
      style={{ border: `1px solid ${colors.border}` }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2" style={{ background: colors.header }}>
        <div className="flex items-center gap-2">
          <SeverityBadge severity={proposal.severity} />
          <span className="text-xs font-semibold" style={{ color: 'var(--text)' }}>
            {proposal.flight_number ?? proposal.leg_id}
            {proposal.origin_iata && proposal.destination_iata && ` ${proposal.origin_iata}→${proposal.destination_iata}`}
          </span>
          {minsToDepart !== null && minsToDepart > 0 && (
            <span className="text-xs" style={{ color: 'var(--muted2)' }}>departs {minsToDepart}m</span>
          )}
        </div>
        <CountdownTimer proposedAt={proposal.proposed_at} severity={proposal.severity} />
      </div>

      {/* Body */}
      <div className="px-3 py-2" style={{ background: 'var(--surface)' }}>
        <p className="text-xs mb-2" style={{ color: 'var(--muted2)' }}>
          {proposal.disruption_reason} ({proposal.disruption_type})
        </p>

        {proposal.proposed_crew_id ? (
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full" style={{ background: 'var(--success)' }} />
            <span className="text-xs font-medium" style={{ color: 'var(--text)' }}>
              {proposal.proposed_crew_id}
            </span>
            <span className="text-xs" style={{ color: 'var(--muted)' }}>
              Score: {proposal.proposal_score.toFixed(0)}
            </span>
          </div>
        ) : (
          <p className="text-xs mb-2" style={{ color: 'var(--warning)' }}>
            ⚠ No replacement found. Manual handling required.
          </p>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 mt-2">
          {proposal.proposed_crew_id && (
            <button
              onClick={() => accept.mutate()}
              disabled={accept.isPending}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors"
              style={{ background: 'rgba(16,185,129,0.15)', color: 'var(--success)', border: '1px solid rgba(16,185,129,0.3)' }}
            >
              <Check size={11} /> Confirm
            </button>
          )}
          <button
            onClick={() => reject.mutate()}
            disabled={reject.isPending}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors"
            style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--danger)', border: '1px solid rgba(239,68,68,0.25)' }}
          >
            <X size={11} /> Reject
          </button>
          <span className="ml-auto text-[10px]" style={{ color: 'var(--muted)' }}>
            {new Date(proposal.proposed_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>
    </div>
  );
}
