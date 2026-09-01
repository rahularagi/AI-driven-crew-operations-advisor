# roster_tools.py
# These are the tools the LLM can call to fetch roster and assignment data from the DB.
# Rosters define which crew member is assigned to which flight on which date.
# These tools help OCC managers see the full picture of crew scheduling.

from langchain_core.tools import tool
from sqlalchemy import text

# get_db_session gives us a database session to run queries
from crew_ops.db.database import get_db_session


# ── Tool 1: Get Roster By Date ────────────────────────────────────────────────
# Returns the full crew roster for a specific date.
# Shows every crew member assigned to every flight on that day.
# This is the most common tool an OCC manager will use first thing in the morning.

@tool
def get_roster_by_date(date: str) -> str:
    """Get the full crew roster for a specific date. Pass date in YYYY-MM-DD format.
    Shows all crew assignments across all flights for that day."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                r.flight_number,
                f.origin,
                f.destination,
                f.scheduled_departure,
                c.employee_id,
                c.first_name,
                c.last_name,
                c.role
            FROM roster_assignments r
            JOIN flights f ON f.flight_number = r.flight_number
            JOIN crew_members c ON c.employee_id = r.employee_id
            WHERE DATE(r.duty_date) = :date
            ORDER BY f.scheduled_departure, c.role
        """), {"date": date})
        rows = result.fetchall()

    if not rows:
        return f"No roster assignments found for {date}"

    # Group assignments by flight number for a cleaner output
    flights = {}
    for r in rows:
        key = r.flight_number
        if key not in flights:
            # First time seeing this flight — create its entry
            flights[key] = {
                "header": f"{r.flight_number} | {r.origin} → {r.destination} | Dep: {r.scheduled_departure}",
                "crew": []
            }
        # Add this crew member to the flight's crew list
        flights[key]["crew"].append(f"  - {r.employee_id} | {r.first_name} {r.last_name} | {r.role}")

    # Build the final output string flight by flight
    lines = []
    for flight in flights.values():
        lines.append(flight["header"])
        lines.extend(flight["crew"])
        lines.append("")  # blank line between flights for readability

    return f"Roster for {date}:\n" + "\n".join(lines)


# ── Tool 2: Get Crew Roster ───────────────────────────────────────────────────
# Returns the upcoming roster for a specific crew member.
# Shows all flights they are assigned to in the next 7 days.
# Useful when a manager asks "what is John Smith flying this week?"

@tool
def get_crew_roster(employee_id: str) -> str:
    """Get the upcoming 7-day roster for a specific crew member by their employee ID.
    Shows all flights they are assigned to in the next 7 days."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                r.duty_date,
                r.flight_number,
                f.origin,
                f.destination,
                f.scheduled_departure,
                f.scheduled_arrival,
                f.aircraft_type
            FROM roster_assignments r
            JOIN flights f ON f.flight_number = r.flight_number
            WHERE r.employee_id = :employee_id
              AND r.duty_date >= CURRENT_DATE
              AND r.duty_date <= CURRENT_DATE + INTERVAL '7 days'
            ORDER BY r.duty_date, f.scheduled_departure
        """), {"employee_id": employee_id})
        rows = result.fetchall()

    if not rows:
        return f"No upcoming roster assignments found for employee {employee_id} in the next 7 days."

    lines = [
        f"{r.duty_date} | {r.flight_number} | {r.origin} → {r.destination} | "
        f"Dep: {r.scheduled_departure} | Arr: {r.scheduled_arrival} | Aircraft: {r.aircraft_type}"
        for r in rows
    ]
    return f"Upcoming roster for {employee_id}:\n" + "\n".join(lines)


# ── Tool 3: Get Open Positions ────────────────────────────────────────────────
# Returns all flights that still have unfilled crew positions on a given date.
# An open position means a required crew role (e.g. Captain) has no one assigned yet.
# This is critical for OCC managers to identify and fill gaps before departure.

@tool
def get_open_positions(date: str) -> str:
    """Get all flights with unfilled crew positions on a specific date. Pass date in YYYY-MM-DD format.
    Returns flights where a required crew role has no one assigned."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                op.flight_number,
                f.origin,
                f.destination,
                f.scheduled_departure,
                op.required_role,
                op.positions_required,
                op.positions_filled
            FROM open_positions op
            JOIN flights f ON f.flight_number = op.flight_number
            WHERE DATE(f.scheduled_departure) = :date
              AND op.positions_filled < op.positions_required
            ORDER BY f.scheduled_departure, op.required_role
        """), {"date": date})
        rows = result.fetchall()

    if not rows:
        return f"No open positions found for {date}. All flights are fully crewed."

    lines = [
        f"⚠️ {r.flight_number} | {r.origin} → {r.destination} | Dep: {r.scheduled_departure} | "
        f"Role needed: {r.required_role} | "
        f"Filled: {r.positions_filled}/{r.positions_required}"
        for r in rows
    ]
    return f"Open positions on {date}:\n" + "\n".join(lines)


# ── Tool 4: Get Roster Conflicts ──────────────────────────────────────────────
# Returns all scheduling conflicts in the roster for a given date.
# A conflict means a crew member has been assigned to two overlapping duties,
# or has been assigned a flight that violates their rest or FTL limits.
# These must be resolved before the flights depart.

@tool
def get_roster_conflicts(date: str) -> str:
    """Get all roster conflicts on a specific date. Pass date in YYYY-MM-DD format.
    A conflict means overlapping duties, FTL violations, or rest violations in the roster."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                rc.employee_id,
                c.first_name,
                c.last_name,
                rc.conflict_type,
                rc.flight_number_1,
                rc.flight_number_2,
                rc.conflict_description
            FROM roster_conflicts rc
            JOIN crew_members c ON c.employee_id = rc.employee_id
            WHERE DATE(rc.conflict_date) = :date
            ORDER BY rc.conflict_type, rc.employee_id
        """), {"date": date})
        rows = result.fetchall()

    if not rows:
        return f"No roster conflicts found for {date}. Roster is clean."

    lines = [
        f"🔴 {r.employee_id} | {r.first_name} {r.last_name} | "
        f"Conflict: {r.conflict_type} | "
        f"Flights: {r.flight_number_1} / {r.flight_number_2} | "
        f"Detail: {r.conflict_description}"
        for r in rows
    ]
    return f"Roster conflicts on {date}:\n" + "\n".join(lines)