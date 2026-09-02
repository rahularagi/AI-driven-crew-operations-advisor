"""
Flight Status Client — API 5 (Aviationstack live polling)

Mock mode  : returns next poll from mock_observer sequences
Real mode  : calls Aviationstack live flight status API

Switch: set MOCK_FLIGHT_STATUS=False in .env to use real API.
"""

from typing import Optional
from crew_ops.config.settings import settings
from crew_ops.data.mock_observer import get_poll_sequence

# In-memory poll index tracker — tracks which poll we are on per leg
_poll_index_tracker: dict[str, int] = {}


def get_next_live_status_poll(leg_id: str) -> Optional[dict]:
    if settings.mock_flight_status:
        return _get_next_mock_poll(leg_id)
    return _get_live_status_from_aviationstack_api(leg_id)


def reset_poll_index_for_leg(leg_id: str) -> None:
    """Call this when a leg completes or is cancelled to clean up tracker."""
    _poll_index_tracker.pop(leg_id, None)


# ─── Mock implementation ──────────────────────────────────────────────────────

def _get_next_mock_poll(leg_id: str) -> Optional[dict]:
    sequence = get_poll_sequence(leg_id)
    if not sequence:
        return None
    current_index = _poll_index_tracker.get(leg_id, 0)
    if current_index >= len(sequence):
        return None
    _poll_index_tracker[leg_id] = current_index + 1
    return sequence[current_index]


# ─── Real API implementation (fill in when going live) ────────────────────────

def _get_live_status_from_aviationstack_api(leg_id: str) -> Optional[dict]:
    # TODO: implement real Aviationstack live status call
    # Parse leg_id to extract flight_iata and flight_date
    # GET https://api.aviationstack.com/v1/flights
    #   ?access_key={settings.aviationstack_api_key}
    #   &flight_iata={flight_iata}&flight_date={flight_date}
    raise NotImplementedError("Real Aviationstack API not implemented yet. Set MOCK_FLIGHT_STATUS=True in .env")
