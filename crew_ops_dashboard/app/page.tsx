'use client';
import { useState, useCallback } from 'react';
import { Topbar } from '@/components/shared/Topbar';
import { LeftNav } from '@/components/shared/LeftNav';
import { StatCards } from '@/components/shared/StatCards';
import { ToastContainer } from '@/components/shared/Toast';
import { RosterPanel } from '@/components/roster/RosterPanel';
import { FlightMonitor } from '@/components/monitor/FlightMonitor';
import { DisruptionInbox } from '@/components/disruption/DisruptionInbox';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { CrewTable } from '@/components/crew/CrewTable';
import { AlertsPanel } from '@/components/crew/AlertsPanel';
import { AdminPanel } from '@/components/admin/AdminPanel';
import { useProposals } from '@/hooks/useProposals';
import type { ToastItem } from '@/components/shared/Toast';

let toastCounter = 0;

export default function Home() {
  const [page, setPage] = useState('dashboard');
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [chatInject, setChatInject] = useState('');
  const { data: proposals = [] } = useProposals();

  const addToast = useCallback((t: Omit<ToastItem, 'id'>) => {
    setToasts(prev => [...prev, { ...t, id: String(++toastCounter) }]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const handleAskAI = useCallback((msg: string) => {
    setPage('dashboard');
    setChatInject(msg);
    setTimeout(() => setChatInject(''), 100);
  }, []);

  const pendingCount = proposals.filter(p => p.status === 'PENDING').length;

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg)' }}>
      <Topbar pendingCount={pendingCount} onAlertsClick={() => setPage('dashboard')} />

      <div className="flex flex-1 overflow-hidden">
        <LeftNav active={page} onChange={setPage} />

        {/* Dashboard — 4 panel layout */}
        {page === 'dashboard' && (
          <div className="flex flex-col flex-1 overflow-hidden">
            <StatCards />
            <div className="flex flex-1 overflow-hidden gap-0">
              {/* Left: Roster + Flight Monitor stacked */}
              <div className="flex flex-col flex-1 overflow-hidden" style={{ borderRight: '1px solid var(--border)' }}>
                <div className="flex-1 overflow-hidden" style={{ borderBottom: '1px solid var(--border)' }}>
                  <RosterPanel addToast={addToast} />
                </div>
                <div className="h-64 overflow-hidden shrink-0">
                  <FlightMonitor />
                </div>
              </div>
              {/* Right: Disruption Inbox + Chat stacked */}
              <div className="flex flex-col w-96 shrink-0 overflow-hidden">
                <div className="flex-1 overflow-hidden" style={{ borderBottom: '1px solid var(--border)' }}>
                  <DisruptionInbox addToast={addToast} />
                </div>
                <div className="h-96 overflow-hidden shrink-0">
                  <ChatPanel addToast={addToast} injectMessage={chatInject} onAlertAction={() => setPage('dashboard')} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Flights page — full flight monitor */}
        {page === 'flights' && (
          <div className="flex-1 overflow-hidden">
            <FlightMonitor />
          </div>
        )}

        {/* Crew page */}
        {page === 'crew' && (
          <div className="flex-1 overflow-hidden">
            <CrewTable addToast={addToast} onAskAI={handleAskAI} />
          </div>
        )}

        {/* Alerts page */}
        {page === 'alerts' && (
          <div className="flex-1 overflow-auto">
            <AlertsPanel />
          </div>
        )}

        {/* Admin page */}
        {page === 'admin' && (
          <div className="flex-1 overflow-hidden">
            <AdminPanel addToast={addToast} />
          </div>
        )}
      </div>

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
