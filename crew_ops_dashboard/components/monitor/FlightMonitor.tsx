'use client';
import { useState } from 'react';
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import { useFlights } from '@/hooks/useFlights';
import { useProposals } from '@/hooks/useProposals';
import { CREW_REQUIRED } from '@/lib/constants';
import type { FlightLeg } from '@/types';

function flightStatus(leg: FlightLeg, hasProposal: boolean): { label: string; color: string } {
  if (hasProposal)                          return { label: '⚠ DISRUPTED',  color: '#EF4444' };
  if (leg.status === 'CANCELLED')           return { label: '✗ CANCELLED',  color: '#6B7280' };
  if (leg.delay_minutes >= 30)              return { label: `⏱ DELAYED +${leg.delay_minutes}m`, color: '#F59E0B' };
  if (leg.actual_departure)                 return { label: '✈ AIRBORNE',   color: '#3B82F6' };
  return                                           { label: '✓ SCHEDULED',  color: '#6B7280' };
}

function FlightRow({ leg, hasProposal }: { leg: FlightLeg; hasProposal: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const { label, color } = flightStatus(leg, hasProposal);
  const required = CREW_REQUIRED[leg.aircraft_type] ?? 5;
  const filled = leg.assigned_crew.length;
  const crewShort = filled < required;
  const dep = new Date(leg.scheduled_departure).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const arr = new Date(leg.scheduled_arrival).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

  return (
    <div style={{ borderBottom: '1px solid var(--border)' }}>
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-[var(--raised)] transition-colors"
        style={{ borderLeft: `3px solid ${color}` }}
        onClick={() => setExpanded(e => !e)}
      >
        {expanded ? <ChevronDown size={11} style={{ color: 'var(--muted)' }} /> : <ChevronRight size={11} style={{ color: 'var(--muted)' }} />}
        <span className="font-mono text-xs font-semibold w-14" style={{ color: 'var(--text)' }}>{leg.flight_number}</span>
        <span className="text-xs w-20" style={{ color: 'var(--muted2)' }}>{leg.origin_iata}→{leg.destination_iata}</span>
        <span className="text-xs w-20" style={{ color: 'var(--muted)' }}>{dep}–{arr}</span>
        <span className="text-[10px] font-semibold flex-1" style={{ color }}>{label}</span>
        <span
          className="text-[10px] font-mono"
          style={{ color: crewShort ? 'var(--danger)' : 'var(--muted)' }}
        >
          {filled}/{required}
        </span>
        <span className="text-[10px] ml-1" style={{ color: 'var(--muted)' }}>{leg.aircraft_type}</span>
      </div>
      {expanded && (
        <div className="px-8 pb-2" style={{ background: 'var(--raised)' }}>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 mt-1">
            <span className="text-[10px]" style={{ color: 'var(--muted)' }}>Aircraft</span>
            <span className="text-[10px]" style={{ color: 'var(--text)' }}>{leg.aircraft_type} · {leg.aircraft_registration}</span>
            <span className="text-[10px]" style={{ color: 'var(--muted)' }}>Scheduled</span>
            <span className="text-[10px]" style={{ color: 'var(--text)' }}>{dep}</span>
            {leg.actual_departure && <>
              <span className="text-[10px]" style={{ color: 'var(--muted)' }}>Actual dep</span>
              <span className="text-[10px]" style={{ color: 'var(--text)' }}>
                {new Date(leg.actual_departure).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
              </span>
            </>}
            {leg.delay_minutes > 0 && <>
              <span className="text-[10px]" style={{ color: 'var(--muted)' }}>Delay</span>
              <span className="text-[10px]" style={{ color: 'var(--warning)' }}>+{leg.delay_minutes} min</span>
            </>}
            <span className="text-[10px]" style={{ color: 'var(--muted)' }}>Crew</span>
            <span className="text-[10px]" style={{ color: crewShort ? 'var(--danger)' : 'var(--text)' }}>
              {leg.assigned_crew.join(', ') || '—'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export function FlightMonitor() {
  const { data: flights = [], isLoading, error, refetch } = useFlights();
  const { data: proposals = [] } = useProposals();
  const disruptedLegs = new Set(proposals.map(p => p.leg_id));

  return (
    <div className="flex flex-col h-full">
      <div
        className="flex items-center justify-between px-3 py-2 shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full blink" style={{ background: 'var(--success)' }} />
          <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text)' }}>Flight Monitor</span>
          <span className="text-[10px]" style={{ color: 'var(--muted)' }}>polls every 30s</span>
        </div>
        <button onClick={() => refetch()} className="p-1 rounded hover:bg-[var(--raised)]" style={{ color: 'var(--muted)' }}>
          <RefreshCw size={12} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && <p className="text-xs text-center mt-4" style={{ color: 'var(--muted)' }}>Loading…</p>}
        {error && <p className="text-xs text-center mt-4" style={{ color: 'var(--danger)' }}>Backend offline</p>}
        {!isLoading && !error && flights.length === 0 && (
          <p className="text-xs text-center mt-4" style={{ color: 'var(--muted)' }}>No flights today</p>
        )}
        {flights.map(leg => (
          <FlightRow key={leg.leg_id} leg={leg} hasProposal={disruptedLegs.has(leg.leg_id)} />
        ))}
      </div>
    </div>
  );
}
