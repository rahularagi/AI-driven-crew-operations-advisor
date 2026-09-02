# flight_tools.py
# These are the tools the LLM can call to fetch flight leg data from the DB.
# Each function is decorated with @tool so LangGraph can register it.
# The docstring of each function is what the LLM reads to decide when to use it.
#
# Tables used:
#   - flight_legs             → core flight schedule and status data
#   - roster_crew_assignment  → which crew are assigned to which leg
#   - crew_members            → joined to get crew names and roles
#
# NOTE: leg_id is VARCHAR in all tables — always pass as string e.g. "LEG-001"

from langchain_core.tools import tool
from sqlalchemy import text
from crew_ops.db.database import get_db_session


# ── Tool 1: Get Flights Today ─────────────────────────────────────────────────
# Returns all flight legs scheduled for today.
# This is the most common starting point for operational queries.

@tool
def get_flights_today() -> str:
    """Get all flight legs scheduled for today."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                leg_id,
                flight_number,
                origin_iata,
                destination_iata,
                scheduled_departure,
                scheduled_arrival,
                status,
                aircraft_type
            FROM flight_legs
            WHERE DATE(scheduled_departure) = CURRENT_DATE
            ORDER BY scheduled_departure
        """))
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return "No flights scheduled for today."

    lines = [
        f"{r.flight_number} | {r.origin_iata}→{r.destination_iata} | "
        f"Dep: {r.scheduled_departure} | Arr: {r.scheduled_arrival} | "
        f"Status: {r.status} | Aircraft: {r.aircraft_type}"
        for r in rows
    ]
    return f"Today's flights ({len(rows)}):\n" + "\n".join(lines)


# ── Tool 2: Get Flight By Number ──────────────────────────────────────────────
# Looks up a specific flight by its number. Returns the 5 most recent legs
# for that flight number to handle recurring daily flights.

@tool
def get_flight_by_number(flight_number: str) -> str:
    """Get details for a specific flight by its flight number e.g. EK101."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                leg_id,
                flight_number,
                origin_iata,
                destination_iata,
                scheduled_departure,
                scheduled_arrival,
                actual_departure,
                actual_arrival,
                status,
                delay_status,
                delay_minutes,
                aircraft_type,
                aircraft_registration
            FROM flight_legs
            WHERE UPPER(flight_number) = UPPER(:flight_number)
            ORDER BY scheduled_departure DESC
            LIMIT 5
        """), {"flight_number": flight_number})
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return f"No flight found with number {flight_number}"

    lines = [
        f"{r.flight_number} | {r.origin_iata}→{r.destination_iata} | "
        f"Dep: {r.scheduled_departure} | Status: {r.status} | "
        f"Delay: {r.delay_minutes or 0} min | Aircraft: {r.aircraft_registration}"
        for r in rows
    ]
    return "\n".join(lines)


# ── Tool 3: Get Delayed Flights ───────────────────────────────────────────────
# Returns all flights today with a delay. Sorted by worst delay first.
# Used when a manager asks about disruptions or delay overview.

@tool
def get_delayed_flights() -> str:
    """Get all flights that are currently delayed today."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                flight_number,
                origin_iata,
                destination_iata,
                scheduled_departure,
                delay_minutes,
                delay_status,
                status
            FROM flight_legs
            WHERE delay_minutes > 0
              AND DATE(scheduled_departure) = CURRENT_DATE
            ORDER BY delay_minutes DESC
        """))
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return "No delayed flights today."

    lines = [
        f"{r.flight_number} | {r.origin_iata}→{r.destination_iata} | "
        f"Delay: {r.delay_minutes} min | Reason: {r.delay_status}"
        for r in rows
    ]
    return f"Delayed flights ({len(rows)}):\n" + "\n".join(lines)


# ── Tool 4: Get Flight Crew ───────────────────────────────────────────────────
# Returns the crew assigned to a specific flight leg.
# LLM uses this after getting a leg_id from get_flights_today or get_flight_by_number.

@tool
def get_flight_crew(leg_id: str) -> str:
    """Get the crew assigned to a specific flight leg by its leg ID e.g. LEG-001."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                c.employee_id,
                c.full_name,
                c.role,
                rca.status
            FROM roster_crew_assignment rca
            JOIN crew_members c ON c.crew_id = rca.crew_id
            WHERE rca.leg_id = :leg_id
            ORDER BY c.role
        """), {"leg_id": leg_id})
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return f"No crew assigned to leg {leg_id}"

    lines = [
        f"{r.employee_id} | {r.full_name} | {r.role} | Assignment: {r.status}"
        for r in rows
    ]
    return f"Crew for leg {leg_id}:\n" + "\n".join(lines)