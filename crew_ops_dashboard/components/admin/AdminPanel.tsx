'use client';
import { useState } from 'react';
import { Play, CheckCircle, XCircle, Loader } from 'lucide-react';
import { useHealth } from '@/hooks/useHealth';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { SCHEDULED_JOBS, ALL_ENDPOINTS } from '@/lib/constants';
import type { ToastItem } from '@/components/shared/Toast';

interface Props {
  addToast: (t: Omit<ToastItem, 'id'>) => void;
}

export function AdminPanel({ addToast }: Props) {
  const { data: health, isLoading } = useHealth();
  const qc = useQueryClient();
  const [running, setRunning] = useState<string | null>(null);

  const runJob = async (jobId: string, endpoint: string | null) => {
    if (!endpoint) { addToast({ type: 'info', message: `${jobId} runs on schedule only` }); return; }
    setRunning(jobId);
    try {
      const endpointMap: Record<string, () => Promise<unknown>> = {
        '/planner/build':    () => api.buildRoster({ requested_by: 'admin' }),
        '/planner/validate': () => api.validateRoster('admin'),
        '/ftl/scan':         () => api.ftlScan(),
        '/ftl/recalculate':  () => api.ftlRecalculate(),
      };
      await (endpointMap[endpoint] ?? (() => Promise.resolve()))();
      addToast({ type: 'success', message: `✓ ${jobId} completed` });
      qc.invalidateQueries();
    } catch {
      addToast({ type: 'critical', message: `${jobId} failed` });
    } finally {
      setRunning(null);
    }
  };

  const services = [
    { label: 'Database',      ok: health?.database === 'connected' },
    { label: 'FastAPI',       ok: !!health },
    { label: 'Event Bus',     ok: !!health },
    { label: 'APScheduler',   ok: (health?.scheduled_jobs?.length ?? 0) > 0 },
    { label: 'Aviationstack', ok: health?.mock_flags?.flight_status === false },
    { label: 'HRMS / Workday',ok: health?.mock_flags?.crew_profile === false },
  ];

  return (
    <div className="p-4 grid grid-cols-2 gap-4 overflow-auto h-full">
      {/* API Health */}
      <div className="rounded-lg p-4" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-xs font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--muted)' }}>API Health</h3>
        {isLoading ? <p className="text-xs" style={{ color: 'var(--muted)' }}>Checking…</p> : (
          <div className="flex flex-col gap-2">
            {services.map(s => (
              <div key={s.label} className="flex items-center gap-2">
                {s.ok
                  ? <CheckCircle size={12} style={{ color: 'var(--success)' }} />
                  : <XCircle size={12} style={{ color: 'var(--muted)' }} />}
                <span className="text-xs" style={{ color: s.ok ? 'var(--text)' : 'var(--muted)' }}>{s.label}</span>
                <span className="text-[10px] ml-auto" style={{ color: s.ok ? 'var(--success)' : 'var(--muted)' }}>
                  {s.ok ? 'connected' : 'mock / offline'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Mock Flags */}
      <div className="rounded-lg p-4" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-xs font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--muted)' }}>Mock Flags</h3>
        {health?.mock_flags ? (
          <div className="flex flex-col gap-2">
            {Object.entries(health.mock_flags).map(([key, val]) => (
              <div key={key} className="flex items-center justify-between">
                <span className="text-xs" style={{ color: 'var(--text)' }}>{key.replace(/_/g, ' ')}</span>
                <span
                  className="px-2 py-0.5 rounded-full text-[10px] font-bold"
                  style={{ background: val ? 'rgba(245,158,11,0.15)' : 'rgba(16,185,129,0.15)', color: val ? '#F59E0B' : '#10B981' }}
                >
                  {val ? 'MOCK' : 'REAL'}
                </span>
              </div>
            ))}
          </div>
        ) : <p className="text-xs" style={{ color: 'var(--muted)' }}>Backend offline</p>}
      </div>

      {/* Scheduled Jobs */}
      <div className="rounded-lg p-4" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-xs font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--muted)' }}>Scheduled Jobs</h3>
        <div className="flex flex-col gap-1.5">
          {SCHEDULED_JOBS.map(job => {
            const isActive = health?.scheduled_jobs?.includes(job.id);
            return (
              <div key={job.id} className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full" style={{ background: isActive ? 'var(--success)' : 'var(--muted)' }} />
                <span className="text-xs flex-1" style={{ color: 'var(--text)' }}>{job.label}</span>
                <span className="text-[10px]" style={{ color: 'var(--muted)' }}>{job.schedule}</span>
                <button
                  onClick={() => runJob(job.id, job.endpoint)}
                  disabled={running === job.id}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] transition-colors"
                  style={{ background: 'var(--raised)', color: 'var(--muted2)', border: '1px solid var(--border2)' }}
                >
                  {running === job.id ? <Loader size={9} className="animate-spin" /> : <Play size={9} />}
                  Run
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* API Explorer */}
      <div className="rounded-lg p-4" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-xs font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--muted)' }}>API Explorer</h3>
        <div className="flex flex-col gap-1">
          {ALL_ENDPOINTS.map(ep => (
            <div key={ep.method + ep.path} className="flex items-center gap-2">
              <span
                className="text-[9px] font-bold w-8 text-center rounded px-1 py-0.5"
                style={{ background: ep.method === 'GET' ? 'rgba(59,130,246,0.15)' : 'rgba(245,158,11,0.15)', color: ep.method === 'GET' ? '#3B82F6' : '#F59E0B' }}
              >
                {ep.method}
              </span>
              <code className="text-[10px] flex-1 truncate" style={{ color: 'var(--muted2)', fontFamily: 'monospace' }}>{ep.path}</code>
              <a
                href={`http://localhost:8000${ep.path.split('?')[0].replace(/{[^}]+}/g, 'test')}`}
                target="_blank"
                rel="noreferrer"
                className="text-[9px] px-1.5 py-0.5 rounded transition-colors hover:opacity-80"
                style={{ background: 'var(--raised)', color: 'var(--muted)', border: '1px solid var(--border2)' }}
              >
                ↗
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
