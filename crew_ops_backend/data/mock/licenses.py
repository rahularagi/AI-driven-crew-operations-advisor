"""
Mock license data — one or more licenses per pilot crew member.
Cabin crew have no aircraft type licenses.
Used by pipeline/load_licenses.py to seed the database on first startup.
"""

MOCK_CREW_LICENSES = [
    # Pilots — each entry is one aircraft type rating
    {"crew_id": "C-001", "aircraft_type": "A320", "expiry_date": "2025-06-30", "medical_expiry": "2025-08-15", "simulator_check_due": "2025-04-01"},
    {"crew_id": "C-001", "aircraft_type": "B787", "expiry_date": "2025-08-01", "medical_expiry": "2025-08-15", "simulator_check_due": "2025-04-01"},
    {"crew_id": "C-002", "aircraft_type": "A320", "expiry_date": "2025-03-01", "medical_expiry": "2025-09-10", "simulator_check_due": "2025-03-15"},
    {"crew_id": "C-003", "aircraft_type": "B737", "expiry_date": "2025-05-15", "medical_expiry": "2025-06-30", "simulator_check_due": "2025-02-28"},
    {"crew_id": "C-003", "aircraft_type": "A320", "expiry_date": "2025-07-20", "medical_expiry": "2025-06-30", "simulator_check_due": "2025-02-28"},
    {"crew_id": "C-004", "aircraft_type": "A320", "expiry_date": "2025-11-30", "medical_expiry": "2025-10-20", "simulator_check_due": "2025-06-01"},
    {"crew_id": "C-005", "aircraft_type": "A320", "expiry_date": "2025-09-15", "medical_expiry": "2025-07-01", "simulator_check_due": "2025-05-10"},
    {"crew_id": "C-005", "aircraft_type": "B737", "expiry_date": "2025-04-30", "medical_expiry": "2025-07-01", "simulator_check_due": "2025-05-10"},
    {"crew_id": "C-006", "aircraft_type": "A320", "expiry_date": "2025-12-01", "medical_expiry": "2025-11-15", "simulator_check_due": "2025-07-20"},
    {"crew_id": "C-007", "aircraft_type": "A320", "expiry_date": "2025-10-31", "medical_expiry": "2025-09-30", "simulator_check_due": "2025-04-15"},
    {"crew_id": "C-007", "aircraft_type": "B737", "expiry_date": "2025-08-15", "medical_expiry": "2025-09-30", "simulator_check_due": "2025-04-15"},
    {"crew_id": "C-008", "aircraft_type": "A320", "expiry_date": "2026-01-15", "medical_expiry": "2025-12-20", "simulator_check_due": "2025-08-01"},
    {"crew_id": "C-009", "aircraft_type": "A320", "expiry_date": "2025-06-01", "medical_expiry": "2025-08-01", "simulator_check_due": "2025-03-20"},
    {"crew_id": "C-009", "aircraft_type": "B787", "expiry_date": "2025-09-30", "medical_expiry": "2025-08-01", "simulator_check_due": "2025-03-20"},
    {"crew_id": "C-010", "aircraft_type": "A320", "expiry_date": "2025-10-01", "medical_expiry": "2025-09-15", "simulator_check_due": "2025-06-30"},
    {"crew_id": "C-021", "aircraft_type": "A320", "expiry_date": "2025-08-31", "medical_expiry": "2025-07-10", "simulator_check_due": "2025-05-01"},
    {"crew_id": "C-021", "aircraft_type": "B737", "expiry_date": "2025-06-15", "medical_expiry": "2025-07-10", "simulator_check_due": "2025-05-01"},
    {"crew_id": "C-022", "aircraft_type": "B737", "expiry_date": "2025-12-31", "medical_expiry": "2025-10-15", "simulator_check_due": "2025-07-01"},
    {"crew_id": "C-024", "aircraft_type": "A320", "expiry_date": "2025-07-01", "medical_expiry": "2025-08-05", "simulator_check_due": "2025-04-30"},
    {"crew_id": "C-024", "aircraft_type": "B737", "expiry_date": "2025-09-20", "medical_expiry": "2025-08-05", "simulator_check_due": "2025-04-30"},
    {"crew_id": "C-025", "aircraft_type": "A320", "expiry_date": "2025-05-31", "medical_expiry": "2025-06-01", "simulator_check_due": "2025-03-01"},
]
