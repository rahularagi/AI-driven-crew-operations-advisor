export const SEVERITY_COLORS: Record<string, { border: string; header: string; badge: string }> = {
  CRITICAL: { border: 'rgba(239,68,68,0.5)',   header: 'rgba(127,29,29,0.6)',  badge: '#EF4444' },
  HIGH:     { border: 'rgba(249,115,22,0.4)',  header: 'rgba(124,45,18,0.5)',  badge: '#F97316' },
  MEDIUM:   { border: 'rgba(245,158,11,0.35)', header: 'rgba(120,53,15,0.45)', badge: '#F59E0B' },
  LOW:      { border: '#374151',               header: '#1F2937',              badge: '#6B7280' },
};

export const SEVERITY_WINDOWS: Record<string, number> = {
  CRITICAL: 15,
  HIGH:     60,
  MEDIUM:   240,
  LOW:      0,
};

export const CREW_REQUIRED: Record<string, number> = {
  A320: 5,
  B737: 5,
  B787: 8,
};

export const MODE_COLORS: Record<string, string> = {
  QUERY:    '#1E3A5F',
  SIMULATE: '#3B82F6',
  ACTION:   '#F59E0B',
  CONFIRM:  '#EF4444',
  CLARIFY:  '#374151',
};

export const STATUS_COLORS: Record<string, string> = {
  PUBLISHED:   '#10B981',
  DRAFT:       '#F59E0B',
  INVALIDATED: '#6B7280',
  DISRUPTED:   '#EF4444',
  CONFIRMED:   '#10B981',
  REPLACED:    '#EF4444',
  PENDING:     '#F59E0B',
};

export const FTL_CAPS = {
  flight_hours_28_day:      100,
  duty_hours_7_day:         60,
  consecutive_duty_days:    6,
  flight_hours_current_duty: 13,
};

export const SCHEDULED_JOBS = [
  { id: 'observer_poll',      label: 'Observer Poll',       schedule: 'Every 5 min',  endpoint: null },
  { id: 'roster_build',       label: 'Roster Build',        schedule: 'Sun 23:00',    endpoint: '/planner/build' },
  { id: 'daily_validation',   label: 'Daily Validation',    schedule: 'Daily 03:00',  endpoint: '/planner/validate' },
  { id: 'ftl_alert_scan',     label: 'FTL Alert Scan',      schedule: 'Every 15 min', endpoint: '/ftl/scan' },
  { id: 'ftl_midnight_recalc',label: 'FTL Midnight Recalc', schedule: 'Daily 00:00',  endpoint: '/ftl/recalculate' },
  { id: 'expire_proposals',   label: 'Expire Proposals',    schedule: 'Daily 00:30',  endpoint: null },
  { id: 'auto_resolve_low',   label: 'Auto-Resolve LOW',    schedule: 'Every 30 min', endpoint: null },
  { id: 'push_proposals',     label: 'Push Proposals',      schedule: 'Every 60s',    endpoint: null },
];

export const ALL_ENDPOINTS = [
  { method: 'GET',  path: '/health' },
  { method: 'GET',  path: '/observer/legs/today' },
  { method: 'GET',  path: '/observer/legs?target_date=YYYY-MM-DD' },
  { method: 'POST', path: '/planner/build' },
  { method: 'POST', path: '/planner/validate' },
  { method: 'GET',  path: '/planner/roster?start=&end=' },
  { method: 'POST', path: '/planner/roster/{leg_id}/approve' },
  { method: 'POST', path: '/planner/roster/{leg_id}/reassign' },
  { method: 'GET',  path: '/disruptions/proposals' },
  { method: 'POST', path: '/disruptions/proposals/{id}/accept' },
  { method: 'POST', path: '/disruptions/proposals/{id}/reject' },
  { method: 'POST', path: '/crew/{id}/unavailable' },
  { method: 'GET',  path: '/crew/{id}/ftl' },
  { method: 'POST', path: '/ftl/scan' },
  { method: 'POST', path: '/ftl/recalculate' },
  { method: 'POST', path: '/chat' },
];

export const MOCK_CREW = [
  { crew_id: 'C-001', full_name: 'Capt Arjun Mehta',   designation: 'CAPTAIN',       role: 'PILOT',  home_base: 'VIDP' },
  { crew_id: 'C-002', full_name: 'FO Priya Sharma',     designation: 'FIRST_OFFICER', role: 'PILOT',  home_base: 'VIDP' },
  { crew_id: 'C-003', full_name: 'Capt Ravi Singh',     designation: 'CAPTAIN',       role: 'PILOT',  home_base: 'VABB' },
  { crew_id: 'C-004', full_name: 'FO Anita Nair',       designation: 'FIRST_OFFICER', role: 'PILOT',  home_base: 'VABB' },
  { crew_id: 'C-005', full_name: 'Capt Suresh Kumar',   designation: 'CAPTAIN',       role: 'PILOT',  home_base: 'VOBL' },
  { crew_id: 'C-006', full_name: 'FO Deepa Rao',        designation: 'FIRST_OFFICER', role: 'PILOT',  home_base: 'VIDP' },
  { crew_id: 'C-007', full_name: 'Capt Vikram Joshi',   designation: 'CAPTAIN',       role: 'PILOT',  home_base: 'VIDP' },
  { crew_id: 'C-008', full_name: 'FO Neha Patel',       designation: 'FIRST_OFFICER', role: 'PILOT',  home_base: 'VABB' },
  { crew_id: 'C-009', full_name: 'Capt Arun Iyer',      designation: 'CAPTAIN',       role: 'PILOT',  home_base: 'VOBL' },
  { crew_id: 'C-010', full_name: 'FO Kavya Menon',      designation: 'FIRST_OFFICER', role: 'PILOT',  home_base: 'VIDP' },
  { crew_id: 'C-011', full_name: 'SP Sunita Kapoor',    designation: 'SENIOR_PURSER', role: 'CABIN', home_base: 'VIDP' },
  { crew_id: 'C-012', full_name: 'CC Rahul Verma',      designation: 'CABIN_CREW',    role: 'CABIN', home_base: 'VIDP' },
  { crew_id: 'C-013', full_name: 'CC Pooja Gupta',      designation: 'CABIN_CREW',    role: 'CABIN', home_base: 'VABB' },
  { crew_id: 'C-014', full_name: 'CC Amit Shah',        designation: 'CABIN_CREW',    role: 'CABIN', home_base: 'VABB' },
  { crew_id: 'C-015', full_name: 'SP Divya Krishnan',   designation: 'SENIOR_PURSER', role: 'CABIN', home_base: 'VOBL' },
  { crew_id: 'C-016', full_name: 'CC Rohit Malhotra',   designation: 'CABIN_CREW',    role: 'CABIN', home_base: 'VIDP' },
  { crew_id: 'C-017', full_name: 'CC Sneha Desai',      designation: 'CABIN_CREW',    role: 'CABIN', home_base: 'VIDP' },
  { crew_id: 'C-018', full_name: 'CC Kiran Reddy',      designation: 'CABIN_CREW',    role: 'CABIN', home_base: 'VABB' },
  { crew_id: 'C-019', full_name: 'SP Meera Pillai',     designation: 'SENIOR_PURSER', role: 'CABIN', home_base: 'VIDP' },
  { crew_id: 'C-020', full_name: 'CC Ajay Tiwari',      designation: 'CABIN_CREW',    role: 'CABIN', home_base: 'VOBL' },
  { crew_id: 'C-021', full_name: 'Capt Nisha Bose',     designation: 'CAPTAIN',       role: 'PILOT',  home_base: 'VIDP' },
  { crew_id: 'C-022', full_name: 'FO Sanjay Kulkarni',  designation: 'FIRST_OFFICER', role: 'PILOT',  home_base: 'VABB' },
  { crew_id: 'C-023', full_name: 'CC Lakshmi Nair',     designation: 'CABIN_CREW',    role: 'CABIN', home_base: 'VIDP' },
  { crew_id: 'C-024', full_name: 'Capt Mohan Das',      designation: 'CAPTAIN',       role: 'PILOT',  home_base: 'VABB' },
  { crew_id: 'C-025', full_name: 'FO Tanya Mishra',     designation: 'FIRST_OFFICER', role: 'PILOT',  home_base: 'VOBL' },
];
