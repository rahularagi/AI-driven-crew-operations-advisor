export interface AssignedCrew {
  crew_id: string;
  status: 'DRAFT' | 'CONFIRMED';
}

export interface FlightLeg {
  leg_id: string;
  flight_number: string;
  origin_iata: string;
  origin_icao: string;
  destination_iata: string;
  destination_icao: string;
  scheduled_departure: string;
  scheduled_arrival: string;
  estimated_arrival?: string;
  actual_departure?: string;
  actual_arrival?: string;
  aircraft_type: string;
  aircraft_registration: string;
  status: string;
  delay_status: string;
  delay_minutes: number;
  assigned_crew: AssignedCrew[];
}

export interface RosterRow {
  leg_id: string;
  crew_id: string;
  status: string;
  assigned_by: string;
  scheduled_departure: string;
  scheduled_arrival: string;
  origin_iata: string;
  destination_iata: string;
  aircraft_type: string;
  flight_number: string;
}

export interface Proposal {
  proposal_id: string;
  leg_id: string;
  disruption_type: string;
  disruption_reason: string;
  removed_crew_id: string;
  proposed_crew_id: string | null;
  proposal_score: number;
  status: string;
  severity: string;
  source: string;
  proposed_at: string;
  scheduled_departure?: string;
  scheduled_arrival?: string;
  origin_iata?: string;
  destination_iata?: string;
  flight_number?: string;
}

export interface FtlState {
  crew_id: string;
  role: string;
  status: string;
  duty_start_time?: string;
  duty_end_time?: string;
  projected_duty_period_end?: string;
  flight_hours_current_duty: number;
  sectors_current_duty: number;
  rest_start_time?: string;
  last_rest_end_time?: string;
  rest_hours_available: number;
  flight_hours_28_day: number;
  duty_hours_7_day: number;
  duty_hours_28_day: number;
  consecutive_duty_days: number;
  last_weekly_rest_end?: string;
  max_duty_period_hours: number;
  home_base: string;
  current_airport: string;
  at_home_base: boolean;
  last_updated?: string;
}

export interface HealthResponse {
  status: string;
  database: string;
  mock_flags: Record<string, boolean>;
  scheduled_jobs: string[];
}

export interface ChatResponse {
  session_id: string;
  response: string;
  mode: string;
  requires_confirmation: boolean;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  mode?: string;
  requires_confirmation?: boolean;
  timestamp: number;
}
