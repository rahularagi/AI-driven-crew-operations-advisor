'use client';
import { LayoutDashboard, Plane, Users, Zap, Settings } from 'lucide-react';

const NAV = [
  { id: 'dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { id: 'flights',   icon: Plane,           label: 'Flights' },
  { id: 'crew',      icon: Users,           label: 'Crew' },
  { id: 'alerts',    icon: Zap,             label: 'Alerts' },
  { id: 'admin',     icon: Settings,        label: 'Admin' },
];

interface Props {
  active: string;
  onChange: (id: string) => void;
}

export function LeftNav({ active, onChange }: Props) {
  return (
    <div
      className="flex flex-col items-center py-3 gap-1 shrink-0 w-12"
      style={{ background: 'var(--surface)', borderRight: '1px solid var(--border)' }}
    >
      {NAV.map(({ id, icon: Icon, label }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          title={label}
          className="w-9 h-9 rounded-lg flex items-center justify-center transition-colors"
          style={{
            background: active === id ? 'var(--brand-dim)' : 'transparent',
            color: active === id ? 'var(--brand)' : 'var(--muted)',
          }}
        >
          <Icon size={16} />
        </button>
      ))}
    </div>
  );
}
