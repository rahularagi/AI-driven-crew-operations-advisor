from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from crew_ops_backend.models.flight_leg import FlightLeg


def get_all_flight_legs(session: Session) -> list[FlightLeg]:
    rows = session.execute(
        text("SELECT * FROM flight_legs ORDER BY scheduled_departure")
    ).mappings().all()
    legs = []
    for row in rows:
        leg_data = dict(row)
        leg_data["assigned_crew"] = _get_assigned_crew_for_leg(session, leg_data["leg_id"])
        legs.append(FlightLeg(**leg_data))
    return legs


def get_flight_legs_for_date_range(session: Session, start: "date", end: "date") -> list[FlightLeg]:
    from datetime import date
    rows = session.execute(
        text("SELECT * FROM flight_legs WHERE scheduled_departure::date BETWEEN :start AND :end ORDER BY scheduled_departure"),
        {"start": start, "end": end}
    ).mappings().all()
    legs = []
    for row in rows:
        leg_data = dict(row)
        leg_data["assigned_crew"] = _get_assigned_crew_for_leg(session, leg_data["leg_id"])
        legs.append(FlightLeg(**leg_data))
    return legs


def get_flight_leg_by_id(session: Session, leg_id: str) -> Optional[FlightLeg]:
    row = session.execute(
        text("SELECT * FROM flight_legs WHERE leg_id = :leg_id"),
        {"leg_id": leg_id}
    ).mappings().first()
    if not row:
        return None
    leg_data = dict(row)
    leg_data["assigned_crew"] = _get_assigned_crew_for_leg(session, leg_id)
    return FlightLeg(**leg_data)


def upsert_flight_leg(session: Session, leg: FlightLeg) -> None:
    session.execute(text("""
        INSERT INTO flight_legs (
            leg_id, flight_number, origin_iata, origin_icao,
            destination_iata, destination_icao, scheduled_departure,
            scheduled_arrival, estimated_arrival, actual_departure,
            actual_arrival, aircraft_type, aircraft_registration,
            status, delay_status, delay_minutes, updated_at
        ) VALUES (
            :leg_id, :flight_number, :origin_iata, :origin_icao,
            :destination_iata, :destination_icao, :scheduled_departure,
            :scheduled_arrival, :estimated_arrival, :actual_departure,
            :actual_arrival, :aircraft_type, :aircraft_registration,
            :status, :delay_status, :delay_minutes, NOW()
        )
        ON CONFLICT (leg_id) DO UPDATE SET
            estimated_arrival       = EXCLUDED.estimated_arrival,
            actual_departure        = EXCLUDED.actual_departure,
            actual_arrival          = EXCLUDED.actual_arrival,
            status                  = EXCLUDED.status,
            delay_status            = EXCLUDED.delay_status,
            delay_minutes           = EXCLUDED.delay_minutes,
            updated_at              = NOW()
    """), leg.model_dump(exclude={"assigned_crew", "created_at", "updated_at"}))

    for crew_id in leg.assigned_crew:
        session.execute(text("""
            INSERT INTO leg_crew_assignments (leg_id, crew_id)
            VALUES (:leg_id, :crew_id)
            ON CONFLICT (leg_id, crew_id) DO NOTHING
        """), {"leg_id": leg.leg_id, "crew_id": crew_id})

    session.commit()


def _get_assigned_crew_for_leg(session: Session, leg_id: str) -> list[str]:
    rows = session.execute(
        text("SELECT crew_id FROM leg_crew_assignments WHERE leg_id = :leg_id"),
        {"leg_id": leg_id}
    ).mappings().all()
    return [row["crew_id"] for row in rows]
