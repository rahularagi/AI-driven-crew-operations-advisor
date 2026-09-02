"""
Flight Schedule Client — API 4 (Aviationstack)

Mock mode  : reads from database (seeded from mock legs)
Real mode  : calls Aviationstack API

Switch: set MOCK_FLIGHT_SCHEDULE=False in .env to use real API.
"""

from datetime import date
from typing import Optional
from crew_ops_backend.config.settings import settings
from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.models.flight_leg import FlightLeg
from crew_ops_backend.db.repositories import leg_repository


def get_all_scheduled_legs() -> list[FlightLeg]:
    if settings.mock_flight_schedule:
        return _get_all_legs_from_database()
    return _get_all_legs_from_aviationstack_api()


def get_legs_for_date_range(start: date, end: date) -> list[FlightLeg]:
    if settings.mock_flight_schedule:
        with SessionLocal() as session:
            return leg_repository.get_flight_legs_for_date_range(session, start, end)
    raise NotImplementedError("Real Aviationstack API not implemented yet.")


def get_flight_leg(leg_id: str) -> Optional[FlightLeg]:
    if settings.mock_flight_schedule:
        return _get_leg_from_database(leg_id)
    return _get_leg_from_aviationstack_api(leg_id)


# ─── Mock (database) implementations ─────────────────────────────────────────

def _get_all_legs_from_database() -> list[FlightLeg]:
    with SessionLocal() as session:
        return leg_repository.get_all_flight_legs(session)


def _get_leg_from_database(leg_id: str) -> Optional[FlightLeg]:
    with SessionLocal() as session:
        return leg_repository.get_flight_leg_by_id(session, leg_id)


# ─── Real API implementations (fill in when going live) ──────────────────────

def _get_all_legs_from_aviationstack_api() -> list[FlightLeg]:
    # TODO: implement real Aviationstack API call
    # GET https://api.aviationstack.com/v1/flights
    #   ?access_key={settings.aviationstack_api_key}
    #   &airline_iata=AI&flight_status=scheduled&limit=100
    raise NotImplementedError("Real Aviationstack API not implemented yet. Set MOCK_FLIGHT_SCHEDULE=True in .env")


def _get_leg_from_aviationstack_api(leg_id: str) -> Optional[FlightLeg]:
    raise NotImplementedError("Real Aviationstack API not implemented yet. Set MOCK_FLIGHT_SCHEDULE=True in .env")
