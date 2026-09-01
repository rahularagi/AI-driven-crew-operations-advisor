# flight_tools.py
# These are the tools the LLM can call to fetch flight data from the DB.
# Each function is decorated with @tool so LangGraph can register it.
# The docstring of each function is what the LLM reads to decide when to use it.

from langchain_core.tools import tool
from sqlalchemy import text

# get_db_session gives us a database session to run queries
from crew_ops.db.database import get_db_session


# ── Tool 1: Get Flights By Date ───────────────────────────────────────────────
# Returns all flights scheduled on a specific date.
# The LLM passes the date string in YYYY-MM-DD format.
# If the manager says "today" or "tomorrow", the agent node resolves
# that to an actual date before calling this tool.

@tool
def get_flights_by_date(date: str) -> str:
    """Get all flights scheduled on a specific date. Pass date in YYYY-MM-DD format."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                f.flight_number,
                f.origin,
                f.destination,
                f.scheduled_departure,
                f.scheduled_arrival,
                f.aircraft_type,
                f.status
            FROM flights f
            WHERE DATE(f.scheduled_departure) = :date
            ORDER BY f.scheduled_departure
        """), {"date": date})
        rows = result.fetchall()

    if not rows:
        return f"No flights found on {date}"

    # Format each flight into a readable line for the LLM to summarize
    lines = [
        f"{r.flight_number} | {r.origin} → {r.destination} | "
        f"Dep: {r.scheduled_departure} | Arr: {r.scheduled_arrival} | "
        f"Aircraft: {r.aircraft_type} | Status: {r.status}"
        for r in rows
    ]
    return f"Flights on {date}:\n" + "\n".join(lines)


# ── Tool 2: Get Flight By Number ──────────────────────────────────────────────
# Returns details for a single specific flight by its flight number.
# Useful when a manager asks about a specific flight e.g. "what is EK204?"

@tool
def get_flight_by_number(flight_number: str) -> str:
    """Get full details for a specific flight by its flight number e.g. EK204, BA101."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                f.flight_number,
                f.origin,
                f.destination,
                f.scheduled_departure,
                f.scheduled_arrival,
                f.aircraft_type,
                f.status,
                f.gate
            FROM flights f
            WHERE UPPER(f.flight_number) = UPPER(:flight_number)
            ORDER BY f.scheduled_departure DESC
            LIMIT 1
        """), {"flight_number": flight_number})
        row = result.fetchone()

    if not row:
        return f"No flight found with number {flight_number}"

    return (
        f"Flight {row.flight_number}\n"
        f"Route: {row.origin} → {row.destination}\n"
        f"Departure: {row.scheduled_departure}\n"
        f"Arrival: {row.scheduled_arrival}\n"
        f"Aircraft: {row.aircraft_type}\n"
        f"Gate: {row.gate}\n"
        f"Status: {row.status}"
    )


# ── Tool 3: Get Unassigned Flights ────────────────────────────────────────────
# Returns all flights that do not have a full crew assigned yet.
# Critical for OCC managers to identify coverage gaps quickly.

@tool
def get_unassigned_flights(date: str) -> str:
    """Get all flights on a specific date that do not have a complete crew assigned. Pass date in YYYY-MM-DD format."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                f.flight_number,
                f.origin,
                f.destination,
                f.scheduled_departure,
                f.aircraft_type
            FROM flights f
            WHERE DATE(f.scheduled_departure) = :date
              AND f.crew_status = 'unassigned'
            ORDER BY f.scheduled_departure
        """), {"date": date})
        rows = result.fetchall()

    if not rows:
        return f"All flights on {date} have crew assigned. No gaps found."

    lines = [
        f"{r.flight_number} | {r.origin} → {r.destination} | "
        f"Dep: {r.scheduled_departure} | Aircraft: {r.aircraft_type}"
        for r in rows
    ]
    return f"⚠️ Unassigned flights on {date}:\n" + "\n".join(lines)


# ── Tool 4: Get Flights By Route ──────────────────────────────────────────────
# Returns all flights between two airports.
# Useful when a manager asks "what flights do we have from LHR to DXB?"

@tool
def get_flights_by_route(origin: str, destination: str) -> str:
    """Get all upcoming flights between two airports. Pass IATA codes e.g. origin=LHR, destination=DXB."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                f.flight_number,
                f.scheduled_departure,
                f.scheduled_arrival,
                f.aircraft_type,
                f.status
            FROM flights f
            WHERE UPPER(f.origin) = UPPER(:origin)
              AND UPPER(f.destination) = UPPER(:destination)
              AND f.scheduled_departure >= NOW()
            ORDER BY f.scheduled_departure
            LIMIT 20
        """), {"origin": origin, "destination": destination})
        rows = result.fetchall()

    if not rows:
        return f"No upcoming flights found from {origin.upper()} to {destination.upper()}"

    lines = [
        f"{r.flight_number} | Dep: {r.scheduled_departure} | "
        f"Arr: {r.scheduled_arrival} | Aircraft: {r.aircraft_type} | Status: {r.status}"
        for r in rows
    ]
    return f"Flights from {origin.upper()} to {destination.upper()}:\n" + "\n".join(lines)