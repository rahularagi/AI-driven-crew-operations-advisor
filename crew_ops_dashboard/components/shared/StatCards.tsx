'use client';
import { useFlights } from '@/hooks/useFlights';
import { useProposals } from '@/hooks/useProposals';

export function StatCards() {
  const { data: flights = [] } = useFlights();
  const { data: proposals = [] } = useProposals();

  const pending = proposals.filter(p => p.status === 'PENDING').length;
  const disrupted = new Set(proposals.map(p => p.leg_id)).size;

  const cards = [
    { label: 'Flights Today',      value: flights.length,  color: '#3B82F6' },
    { label: 'Disruptions',        value: disrupted,        color: '#EF4444' },
    { label: 'Pending Proposals',  value: pending,          color: '#F59E0B' },
    { label: 'Legs Monitored',     value: flights.length,  color: '#10B981' },
  ];

  return (
    <div className="grid grid-cols-4 gap-3 px-3 py-2 shrink-0">
      {cards.map(c => (
        <div
          key={c.label}
          className="rounded-lg px-3 py-2"
          style={{ background: 'var(--surface)', border: `1px solid ${c.color}33` }}
        >
          <div className="text-xl font-bold" style={{ color: c.color }}>{c.value}</div>
          <div className="text-[10px] mt-0.5" style={{ color: 'var(--muted)' }}>{c.label}</div>
        </div>
      ))}
    </div>
  );
}
