'use client';
import { useState } from 'react';
import { Check, X, AlertTriangle, UserCheck } from 'lucide-react';
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

  const isApproval = !!proposal.proposed_crew_id;
  const isCritical = proposal.severity === 'CRITICAL';

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

  const fmt = (iso?: string) =>
    iso ? new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : null;

  const depTime = fmt(proposal.scheduled_departure);
  const arrTime = fmt(proposal.scheduled_arrival);

  // Visual identity per card type
  const accentColor  = isApproval ? '#3B82F6' : '#EF4444';
  const typeBg       = isApproval ? 'rgba(59,130,246,0.12)' : 'rgba(239,68,68,0.12)';
  const typeColor    = isApproval ? '#60A5FA' : '#F87171';
  const TypeIcon     = isApproval ? UserCheck : AlertTriangle;
  const typeLabel    = isApproval ? 'APPROVAL NEEDED' : 'DISRUPTION';

  return (
    <div
      className={`rounded-lg overflow-hidden mb-2 ${isCritical ? 'pulse-ring' : ''}`}
      style={{ border: `1px solid ${colors.border}`, borderLeft: `3px solid ${accentColor}` }}
    >
      {/* Type tag row */}
      <div
        className="flex items-center justify-between px-3 py-1.5"
        style={{ background: typeBg, borderBottom: `1px solid ${accentColor}22` }}
      >
        <div className="flex items-center gap-1.5">
          <TypeIcon size={11} style={{ color: typeColor }} />
          <span className="text-[10px] font-bold tracking-wider" style={{ color: typeColor }}>
            {typeLabel}
          </span>
        </div>
        <CountdownTimer proposedAt={proposal.proposed_at} severity={proposal.severity} />
      </div>

      {/* Flight header */}
      <div className="flex items-center justify-between px-3 py-2" style={{ background: colors.header }}>
        <div className="flex items-center gap-2">
          <SeverityBadge severity={proposal.severity} />
          <span className="text-xs font-semibold" style={{ color: 'var(--text)' }}>
            {proposal.flight_number ?? proposal.leg_id}
            {proposal.origin_iata && proposal.destination_iata && ` · ${proposal.origin_iata}→${proposal.destination_iata}`}
          </span>
        </div>
        {/* Flight timing */}
        {(depTime || arrTime) && (
          <div className="flex items-center gap-1 text-[10px]" style={{ color: 'var(--muted2)' }}>
            {depTime && <span>dep {depTime}</span>}
            {depTime && arrTime && <span style={{ color: 'var(--muted)' }}>·</span>}
            {arrTime && <span>arr {arrTime}</span>}
          </div>
        )}
      </div>

      {/* Body */}
      <div className="px-3 py-2" style={{ background: 'var(--surface)' }}>
        <p className="text-xs mb-2" style={{ color: 'var(--muted2)' }}>
          {proposal.disruption_reason} <span style={{ color: 'var(--muted)' }}>({proposal.disruption_type})</span>
        </p>

        {/* Crew change row */}
        <div className="flex items-center gap-2 mb-2 text-xs">
          <span style={{ color: 'var(--muted)' }}>Removed:</span>
          <span className="font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(239,68,68,0.12)', color: '#F87171', border: '1px solid rgba(239,68,68,0.25)' }}>
            {proposal.removed_crew_id}
          </span>
          {isApproval && (
            <>
              <span style={{ color: 'var(--muted)' }}>→</span>
              <span style={{ color: 'var(--muted)' }}>Replace:</span>
              <span className="font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(59,130,246,0.12)', color: '#60A5FA', border: '1px solid rgba(59,130,246,0.25)' }}>
                {proposal.proposed_crew_id}
              </span>
              <span className="text-[10px]" style={{ color: 'var(--muted)' }}>
                Score: {proposal.proposal_score.toFixed(0)}
              </span>
            </>
          )}
        </div>

        {!isApproval && (
          <p className="text-xs mb-2" style={{ color: 'var(--warning)' }}>
            ⚠ No replacement found — manual handling required.
          </p>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 mt-2">
          {isApproval && (
            <button
              onClick={() => accept.mutate()}
              disabled={accept.isPending}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors"
              style={{ background: 'rgba(59,130,246,0.15)', color: '#60A5FA', border: '1px solid rgba(59,130,246,0.3)' }}
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
            <X size={11} /> {isApproval ? 'Reject' : 'Dismiss'}
          </button>
          <span className="ml-auto text-[10px]" style={{ color: 'var(--muted)' }}>
            raised {new Date(proposal.proposed_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>
    </div>
  );
}
