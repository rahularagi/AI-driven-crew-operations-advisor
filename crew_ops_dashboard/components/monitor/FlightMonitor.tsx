'use client';
import { useState } from 'react';
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import { useFlights } from '@/hooks/useFlights';
import { useProposals } from '@/hooks/useProposals';
import { CREW_REQUIRED } from '@/lib/constants';
import type { FlightLeg, AssignedCrew } from '@/types';

function flightStatus(leg: FlightLeg, hasProposal: boolean): { label: string; color: string } {
  if (hasProposal)                          return { label: '⚠ DISRUPTED',  color: '#EF4444' };
  if (leg.status === 'CANCELLED')           return { label: '✗ CANCELLED',  color: '#6B7280' };
  if (leg.delay_minutes >= 30)              return { label: `⏱ DELAYED +${leg.delay_minutes}m`, color: '#F59E0B' };
  if (leg.actual_departure)                 return { label: '✈ AIRBORNE',   color: '#3B82F6' };
  return                                           { label: '✓ SCHEDULED',  color: '#6B7280' };
}

function crewStatusColor(status: string): string {
  if (status === 'CONFIRMED') return '#10B981';
  if (status === 'DRAFT')     return '#F59E0B';
  return '#6B7280';
}

function CrewBadge({ crew }: { crew: AssignedCrew }) {
  const color = crewStatusColor(crew.status);
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono font-semibold"
      style={{ background: `${color}22`, border: `1px solid ${color}55`, color }}
    >
      {crew.crew_id}
      <span style={{ fontSize: '8px', opacity: 0.85 }}>{crew.status}</span>
    </span>
  );
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
        <span className="text-xs w-24" style={{ color: 'var(--muted)' }}>{dep} – {arr}</span>
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
        <div className="px-8 pb-3" style={{ background: 'var(--raised)' }}>
          <table className="w-full mt-2" style={{ borderCollapse: 'collapse' }}>
            <tbody>
              <tr>
                <td className="text-[10px] pr-4 py-0.5 w-20" style={{ color: 'var(--muted)' }}>Aircraft</td>
                <td className="text-[10px] py-0.5" style={{ color: 'var(--text)' }}>{leg.aircraft_type} · {leg.aircraft_registration}</td>
              </tr>
              <tr>
                <td className="text-[10px] pr-4 py-0.5" style={{ color: 'var(--muted)' }}>Departure</td>
                <td className="text-[10px] py-0.5" style={{ color: 'var(--text)' }}>{dep}</td>
              </tr>
              <tr>
                <td className="text-[10px] pr-4 py-0.5" style={{ color: 'var(--muted)' }}>Arrival</td>
                <td className="text-[10px] py-0.5" style={{ color: 'var(--text)' }}>{arr}</td>
              </tr>
              <tr>
                <td className="text-[10px] pr-4 py-0.5" style={{ color: 'var(--muted)' }}>Flight Status</td>
                <td className="text-[10px] py-0.5 font-semibold" style={{ color }}>{label}</td>
              </tr>
              <tr>
                <td className="text-[10px] pr-4 py-0.5" style={{ color: 'var(--muted)' }}>Roster Status</td>
                <td className="text-[10px] py-0.5">
                  {leg.assigned_crew.length === 0
                    ? <span style={{ color: 'var(--muted)' }}>No roster</span>
                    : leg.assigned_crew.every(c => c.status === 'CONFIRMED')
                      ? <span style={{ color: '#10B981' }}>✓ CONFIRMED</span>
                      : <span style={{ color: '#F59E0B' }}>~ DRAFT</span>
                  }
                </td>
              </tr>
              {leg.actual_departure && (
                <tr>
                  <td className="text-[10px] pr-4 py-0.5" style={{ color: 'var(--muted)' }}>Actual dep</td>
                  <td className="text-[10px] py-0.5" style={{ color: 'var(--text)' }}>
                    {new Date(leg.actual_departure).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                  </td>
                </tr>
              )}
              {leg.delay_minutes > 0 && (
                <tr>
                  <td className="text-[10px] pr-4 py-0.5" style={{ color: 'var(--muted)' }}>Delay</td>
                  <td className="text-[10px] py-0.5" style={{ color: 'var(--warning)' }}>+{leg.delay_minutes} min</td>
                </tr>
              )}
              <tr>
                <td className="text-[10px] pr-4 py-0.5 align-top" style={{ color: 'var(--muted)' }}>Crew ({filled}/{required})</td>
                <td className="py-0.5">
                  {leg.assigned_crew.length === 0
                    ? <span className="text-[10px]" style={{ color: 'var(--muted)' }}>No crew assigned</span>
                    : <div className="flex flex-wrap gap-1">
                        {leg.assigned_crew.map(c => <CrewBadge key={c.crew_id} crew={c} />)}
                      </div>
                  }
                </td>
              </tr>
            </tbody>
          </table>
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
    <div className="flex flex-col h-full" style={{ background: '#0D0A1A' }}>
      <div
        className="flex items-center justify-between px-3 py-2 shrink-0"
        style={{ borderBottom: '1px solid #2D1B4E', background: '#150F2A' }}
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
