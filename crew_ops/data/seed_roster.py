"""
Mock AIMS/HR leave records (API 5) and reserve schedule (API 6).
Base week: 2024-02-05 to 2024-02-11.
"""

# API 5 — Crew leave (external read-only from AIMS/HR)
CREW_LEAVE = [
    {"crew_id": "C-003", "leave_type": "ANNUAL",   "start_date": "2024-02-05", "end_date": "2024-02-07"},
    {"crew_id": "C-014", "leave_type": "SICK",      "start_date": "2024-02-05", "end_date": "2024-02-11"},
    {"crew_id": "C-009", "leave_type": "TRAINING",  "start_date": "2024-02-06", "end_date": "2024-02-06"},
    {"crew_id": "C-020", "leave_type": "ANNUAL",    "start_date": "2024-02-08", "end_date": "2024-02-10"},
    {"crew_id": "C-025", "leave_type": "SICK",      "start_date": "2024-02-09", "end_date": "2024-02-09"},
]

# API 6 — Reserve / standby schedule
RESERVE_SCHEDULE = [
    # D1 — VIDP
    {"reserve_id": "RSV-001", "crew_id": "C-007", "date": "2024-02-05", "standby_start": "2024-02-05T06:00:00+05:30", "standby_end": "2024-02-05T18:00:00+05:30", "base_airport": "VIDP", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
    {"reserve_id": "RSV-002", "crew_id": "C-010", "date": "2024-02-05", "standby_start": "2024-02-05T06:00:00+05:30", "standby_end": "2024-02-05T18:00:00+05:30", "base_airport": "VIDP", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
    # D1 — VABB
    {"reserve_id": "RSV-003", "crew_id": "C-019", "date": "2024-02-05", "standby_start": "2024-02-05T06:00:00+05:30", "standby_end": "2024-02-05T18:00:00+05:30", "base_airport": "VABB", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
    {"reserve_id": "RSV-004", "crew_id": "C-022", "date": "2024-02-05", "standby_start": "2024-02-05T08:00:00+05:30", "standby_end": "2024-02-05T20:00:00+05:30", "base_airport": "VABB", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
    # D2 — VIDP
    {"reserve_id": "RSV-005", "crew_id": "C-002", "date": "2024-02-06", "standby_start": "2024-02-06T06:00:00+05:30", "standby_end": "2024-02-06T18:00:00+05:30", "base_airport": "VIDP", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
    {"reserve_id": "RSV-006", "crew_id": "C-016", "date": "2024-02-06", "standby_start": "2024-02-06T06:00:00+05:30", "standby_end": "2024-02-06T18:00:00+05:30", "base_airport": "VIDP", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
    # D2 — VABB
    {"reserve_id": "RSV-007", "crew_id": "C-018", "date": "2024-02-06", "standby_start": "2024-02-06T07:00:00+05:30", "standby_end": "2024-02-06T19:00:00+05:30", "base_airport": "VABB", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
    # D3 — VIDP
    {"reserve_id": "RSV-008", "crew_id": "C-021", "date": "2024-02-07", "standby_start": "2024-02-07T06:00:00+05:30", "standby_end": "2024-02-07T18:00:00+05:30", "base_airport": "VIDP", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
    # D4 — VIDP
    {"reserve_id": "RSV-009", "crew_id": "C-006", "date": "2024-02-08", "standby_start": "2024-02-08T06:00:00+05:30", "standby_end": "2024-02-08T18:00:00+05:30", "base_airport": "VIDP", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
    # D5 — VOBL
    {"reserve_id": "RSV-010", "crew_id": "C-025", "date": "2024-02-09", "standby_start": "2024-02-09T06:00:00+05:30", "standby_end": "2024-02-09T18:00:00+05:30", "base_airport": "VOBL", "callable_within": 120, "status": "SCHEDULED", "activated_for": None},
]
