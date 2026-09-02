'use client';
import { useCrewFtl } from '@/hooks/useCrewFtl';
import { MOCK_CREW } from '@/lib/constants';
import type { FtlState } from '@/types';

interface Alert {
  crew_id: string;
  full_name: string;
  type: string;
  message: string;
  severity: 'HIGH' | 'MEDIUM';
}

function deriveAlerts(crewId: string, fullName: string, ftl: FtlState): Alert[] {
  const alerts: Alert[] = [];
  if (ftl.flight_hours_28_day > 90) {
    alerts.push({ crew_id: crewId, full_name: fullName, type: 'CUMULATIVE_HOURS_WARNING', severity: 'MEDIUM', message: `${ftl.flight_hours_28_day.toFixed(1)}h / 100h in last 28 days` });
  }
  if (ftl.consecutive_duty_days >= 6) {
    alerts.push({ crew_id: crewId, full_name: fullName, type: 'WEEKLY_REST_OVERDUE', severity: 'HIGH', message: `${ftl.consecutive_duty_days} consecutive duty days — rest overdue` });
  }
  if (ftl.projected_duty_period_end && ftl.status === 'AVAILABLE') {
    const hoursLeft = (new Date(ftl.projected_duty_period_end).getTime() - Date.now()) / 3_600_000;
    if (hoursLeft > 0 && hoursLeft <= 2) {
      alerts.push({ crew_id: crewId, full_name: fullName, type: 'DUTY_PERIOD_APPROACHING', severity: 'HIGH', message: `Duty period ends in ${hoursLeft.toFixed(1)}h` });
    }
  }
  return alerts;
}

function CrewAlertRow({ crew }: { crew: typeof MOCK_CREW[0] }) {
  const { data: ftl } = useCrewFtl(crew.crew_id);
  if (!ftl) return null;
  const alerts = deriveAlerts(crew.crew_id, crew.full_name, ftl);
  if (alerts.length === 0) return null;

  return (
    <>
      {alerts.map((a, i) => (
        <div
          key={i}
          className="flex items-start gap-3 px-4 py-3 rounded-lg mb-2"
          style={{ background: 'var(--surface)', border: `1px solid ${a.severity === 'HIGH' ? 'rgba(249,115,22,0.4)' : 'rgba(245,158,11,0.35)'}` }}
        >
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-xs font-semibold" style={{ color: 'var(--text)' }}>{a.full_name}</span>
              <span className="text-[10px]" style={{ color: 'var(--muted)' }}>{a.crew_id}</span>
              <span
                className="text-[9px] font-bold px-1.5 py-0.5 rounded uppercase"
                style={{ background: a.severity === 'HIGH' ? 'rgba(249,115,22,0.15)' : 'rgba(245,158,11,0.15)', color: a.severity === 'HIGH' ? '#F97316' : '#F59E0B' }}
              >
                {a.severity}
              </span>
            </div>
            <div className="text-[10px]" style={{ color: 'var(--muted)' }}>{a.type.replace(/_/g, ' ')}</div>
            <div className="text-xs mt-0.5" style={{ color: 'var(--muted2)' }}>{a.message}</div>
          </div>
        </div>
      ))}
    </>
  );
}

export function AlertsPanel() {
  return (
    <div className="p-4 overflow-auto h-full">
      <div className="mb-4">
        <h2 className="text-sm font-bold" style={{ color: 'var(--text)' }}>FTL Alerts</h2>
        <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>Derived from live FTL state — polls every 60s</p>
      </div>
      {MOCK_CREW.map(c => <CrewAlertRow key={c.crew_id} crew={c} />)}
    </div>
  );
}
