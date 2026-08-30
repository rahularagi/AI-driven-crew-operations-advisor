"""
Mock crew leave records.
Used by pipeline/load_leave_records.py to seed the database on first startup.
"""

MOCK_CREW_LEAVE_RECORDS = [
    {"crew_id": "C-003", "leave_type": "ANNUAL",   "start_date": "2024-02-05", "end_date": "2024-02-07"},
    {"crew_id": "C-014", "leave_type": "SICK",      "start_date": "2024-02-05", "end_date": "2024-02-11"},
    {"crew_id": "C-009", "leave_type": "TRAINING",  "start_date": "2024-02-06", "end_date": "2024-02-06"},
    {"crew_id": "C-020", "leave_type": "ANNUAL",    "start_date": "2024-02-08", "end_date": "2024-02-10"},
    {"crew_id": "C-025", "leave_type": "SICK",      "start_date": "2024-02-09", "end_date": "2024-02-09"},
]
