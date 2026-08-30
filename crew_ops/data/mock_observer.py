"""
Mock Observer responses — API 2 (single flight live status).

Simulates what Aviationstack would return when Observer polls a specific flight.
Each entry is a sequence of poll responses showing how a flight evolves over time.

Usage:
    from crew_ops.data.mock_observer import get_poll_sequence
    responses = get_poll_sequence("AI202-DEL-BOM-20240205")
    for poll in responses:
        print(poll)
"""

from typing import Any

# Raw Aviationstack-shaped responses per flight, in poll order
_SEQUENCES: dict[str, list[dict[str, Any]]] = {

    # AI202 DEL→BOM — delay scenario (grows from 0 → 45 → 150 min)
    "AI202-DEL-BOM-20240205": [
        # Poll 1 — on time, not yet departed
        {"flight_date": "2024-02-05", "flight_status": "scheduled",
         "departure": {"iata": "DEL", "scheduled": "2024-02-05T09:00:00+05:30", "actual": None, "delay": None},
         "arrival":   {"iata": "BOM", "scheduled": "2024-02-05T11:00:00+05:30", "estimated": "2024-02-05T11:00:00+05:30", "actual": None, "delay": None},
         "flight": {"iata": "AI202"}, "aircraft": {"registration": "VT-PPM"}},
        # Poll 2 — small delay at gate
        {"flight_date": "2024-02-05", "flight_status": "scheduled",
         "departure": {"iata": "DEL", "scheduled": "2024-02-05T09:00:00+05:30", "actual": None, "delay": 45},
         "arrival":   {"iata": "BOM", "scheduled": "2024-02-05T11:00:00+05:30", "estimated": "2024-02-05T11:45:00+05:30", "actual": None, "delay": 45},
         "flight": {"iata": "AI202"}, "aircraft": {"registration": "VT-PPM"}},
        # Poll 3 — airborne, delay grown to 150 min → triggers FlightDisrupted MEDIUM
        {"flight_date": "2024-02-05", "flight_status": "active",
         "departure": {"iata": "DEL", "scheduled": "2024-02-05T09:00:00+05:30", "actual": "2024-02-05T11:30:00+05:30", "delay": 150},
         "arrival":   {"iata": "BOM", "scheduled": "2024-02-05T11:00:00+05:30", "estimated": "2024-02-05T13:30:00+05:30", "actual": None, "delay": 150},
         "flight": {"iata": "AI202"}, "aircraft": {"registration": "VT-PPM"}},
        # Poll 4 — landed
        {"flight_date": "2024-02-05", "flight_status": "landed",
         "departure": {"iata": "DEL", "scheduled": "2024-02-05T09:00:00+05:30", "actual": "2024-02-05T11:30:00+05:30", "delay": 150},
         "arrival":   {"iata": "BOM", "scheduled": "2024-02-05T11:00:00+05:30", "estimated": "2024-02-05T13:30:00+05:30", "actual": "2024-02-05T13:28:00+05:30", "delay": 148},
         "flight": {"iata": "AI202"}, "aircraft": {"registration": "VT-PPM"}},
    ],

    # AI305 BOM→CCU — sick call scenario, flight runs normally (disruption is crew-side)
    "AI305-BOM-CCU-20240205": [
        {"flight_date": "2024-02-05", "flight_status": "scheduled",
         "departure": {"iata": "BOM", "scheduled": "2024-02-05T10:00:00+05:30", "actual": None, "delay": None},
         "arrival":   {"iata": "CCU", "scheduled": "2024-02-05T12:30:00+05:30", "estimated": "2024-02-05T12:30:00+05:30", "actual": None, "delay": None},
         "flight": {"iata": "AI305"}, "aircraft": {"registration": "VT-SVB"}},
        {"flight_date": "2024-02-05", "flight_status": "active",
         "departure": {"iata": "BOM", "scheduled": "2024-02-05T10:00:00+05:30", "actual": "2024-02-05T10:05:00+05:30", "delay": 5},
         "arrival":   {"iata": "CCU", "scheduled": "2024-02-05T12:30:00+05:30", "estimated": "2024-02-05T12:35:00+05:30", "actual": None, "delay": 5},
         "flight": {"iata": "AI305"}, "aircraft": {"registration": "VT-SVB"}},
        {"flight_date": "2024-02-05", "flight_status": "landed",
         "departure": {"iata": "BOM", "scheduled": "2024-02-05T10:00:00+05:30", "actual": "2024-02-05T10:05:00+05:30", "delay": 5},
         "arrival":   {"iata": "CCU", "scheduled": "2024-02-05T12:30:00+05:30", "estimated": "2024-02-05T12:35:00+05:30", "actual": "2024-02-05T12:33:00+05:30", "delay": 3},
         "flight": {"iata": "AI305"}, "aircraft": {"registration": "VT-SVB"}},
    ],

    # AI410 BOM→DEL — cascade scenario, delay grows to 240 min → FlightDisrupted HIGH
    "AI410-BOM-DEL-20240205": [
        {"flight_date": "2024-02-05", "flight_status": "scheduled",
         "departure": {"iata": "BOM", "scheduled": "2024-02-05T15:00:00+05:30", "actual": None, "delay": None},
         "arrival":   {"iata": "DEL", "scheduled": "2024-02-05T17:00:00+05:30", "estimated": "2024-02-05T17:00:00+05:30", "actual": None, "delay": None},
         "flight": {"iata": "AI410"}, "aircraft": {"registration": "VT-PPL"}},
        {"flight_date": "2024-02-05", "flight_status": "scheduled",
         "departure": {"iata": "BOM", "scheduled": "2024-02-05T15:00:00+05:30", "actual": None, "delay": 240},
         "arrival":   {"iata": "DEL", "scheduled": "2024-02-05T17:00:00+05:30", "estimated": "2024-02-05T21:00:00+05:30", "actual": None, "delay": 240},
         "flight": {"iata": "AI410"}, "aircraft": {"registration": "VT-PPL"}},
        {"flight_date": "2024-02-05", "flight_status": "active",
         "departure": {"iata": "BOM", "scheduled": "2024-02-05T15:00:00+05:30", "actual": "2024-02-05T19:00:00+05:30", "delay": 240},
         "arrival":   {"iata": "DEL", "scheduled": "2024-02-05T17:00:00+05:30", "estimated": "2024-02-05T21:05:00+05:30", "actual": None, "delay": 245},
         "flight": {"iata": "AI410"}, "aircraft": {"registration": "VT-PPL"}},
        {"flight_date": "2024-02-05", "flight_status": "landed",
         "departure": {"iata": "BOM", "scheduled": "2024-02-05T15:00:00+05:30", "actual": "2024-02-05T19:00:00+05:30", "delay": 240},
         "arrival":   {"iata": "DEL", "scheduled": "2024-02-05T17:00:00+05:30", "estimated": "2024-02-05T21:05:00+05:30", "actual": "2024-02-05T21:02:00+05:30", "delay": 242},
         "flight": {"iata": "AI410"}, "aircraft": {"registration": "VT-PPL"}},
    ],

    # AI101 DEL→LHR — cancelled → FlightDisrupted CRITICAL
    "AI101-DEL-LHR-20240205": [
        {"flight_date": "2024-02-05", "flight_status": "scheduled",
         "departure": {"iata": "DEL", "scheduled": "2024-02-05T11:00:00+05:30", "actual": None, "delay": None},
         "arrival":   {"iata": "LHR", "scheduled": "2024-02-05T20:15:00+05:30", "estimated": "2024-02-05T20:15:00+05:30", "actual": None, "delay": None},
         "flight": {"iata": "AI101"}, "aircraft": {"registration": "VT-ANX"}},
        {"flight_date": "2024-02-05", "flight_status": "cancelled",
         "departure": {"iata": "DEL", "scheduled": "2024-02-05T11:00:00+05:30", "actual": None, "delay": None},
         "arrival":   {"iata": "LHR", "scheduled": "2024-02-05T20:15:00+05:30", "estimated": None, "actual": None, "delay": None},
         "flight": {"iata": "AI101"}, "aircraft": {"registration": "VT-ANX"}},
    ],

    # AI854 PNQ→DEL — normal, no disruption
    "AI854-PNQ-DEL-20240205": [
        {"flight_date": "2024-02-05", "flight_status": "scheduled",
         "departure": {"iata": "PNQ", "scheduled": "2024-02-05T06:00:00+05:30", "actual": None, "delay": None},
         "arrival":   {"iata": "DEL", "scheduled": "2024-02-05T08:15:00+05:30", "estimated": "2024-02-05T08:15:00+05:30", "actual": None, "delay": None},
         "flight": {"iata": "AI854"}, "aircraft": {"registration": "VT-PPL"}},
        {"flight_date": "2024-02-05", "flight_status": "active",
         "departure": {"iata": "PNQ", "scheduled": "2024-02-05T06:00:00+05:30", "actual": "2024-02-05T06:02:00+05:30", "delay": 2},
         "arrival":   {"iata": "DEL", "scheduled": "2024-02-05T08:15:00+05:30", "estimated": "2024-02-05T08:17:00+05:30", "actual": None, "delay": 2},
         "flight": {"iata": "AI854"}, "aircraft": {"registration": "VT-PPL"}},
        {"flight_date": "2024-02-05", "flight_status": "landed",
         "departure": {"iata": "PNQ", "scheduled": "2024-02-05T06:00:00+05:30", "actual": "2024-02-05T06:02:00+05:30", "delay": 2},
         "arrival":   {"iata": "DEL", "scheduled": "2024-02-05T08:15:00+05:30", "estimated": "2024-02-05T08:17:00+05:30", "actual": "2024-02-05T08:16:00+05:30", "delay": 1},
         "flight": {"iata": "AI854"}, "aircraft": {"registration": "VT-PPL"}},
    ],
}


def get_poll_sequence(leg_id: str) -> list[dict[str, Any]]:
    """Return the mock poll sequence for a given leg_id. Returns [] if not mocked."""
    return _SEQUENCES.get(leg_id, [])


def get_all_leg_ids() -> list[str]:
    return list(_SEQUENCES.keys())
