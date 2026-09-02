const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  health:              ()                                    => req('/health'),
  flightsToday:        ()                                    => req('/observer/legs/today'),
  flightsByDate:       (d: string)                          => req(`/observer/legs?target_date=${d}`),
  roster:              (start: string, end: string)         => req(`/planner/roster?start=${start}&end=${end}`),
  approveLeg:          (legId: string, approvedBy: string)  => req(`/planner/roster/${legId}/approve`, { method: 'POST', body: JSON.stringify(approvedBy) }),
  reassignCrew:        (legId: string, body: object)        => req(`/planner/roster/${legId}/reassign`, { method: 'POST', body: JSON.stringify(body) }),
  buildRoster:         (body: object)                       => req('/planner/build', { method: 'POST', body: JSON.stringify(body) }),
  validateRoster:      (requestedBy: string)                => req('/planner/validate', { method: 'POST', body: JSON.stringify(requestedBy) }),
  proposals:           ()                                    => req('/disruptions/proposals'),
  acceptProposal:      (id: string, decidedBy: string)      => req(`/disruptions/proposals/${id}/accept`, { method: 'POST', body: JSON.stringify(decidedBy) }),
  rejectProposal:      (id: string, body: object)           => req(`/disruptions/proposals/${id}/reject`, { method: 'POST', body: JSON.stringify(body) }),
  crewFtl:             (id: string)                         => req(`/crew/${id}/ftl`),
  markUnavailable:     (id: string, body: object)           => req(`/crew/${id}/unavailable`, { method: 'POST', body: JSON.stringify(body) }),
  ftlScan:             ()                                    => req('/ftl/scan', { method: 'POST' }),
  ftlRecalculate:      ()                                    => req('/ftl/recalculate', { method: 'POST' }),
  chat:                (body: object)                       => req('/chat', { method: 'POST', body: JSON.stringify(body) }),
};
