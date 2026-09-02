# roster_tools.py
# These are the tools the LLM can call to fetch roster and assignment data from the DB.
# Each function is decorated with @tool so LangGraph can register it.
# The docstring of each function is what the LLM reads to decide when to use it.
#
# Tables used:
#   - roster_crew_assignment → which crew member is assigned to which leg and their status
#   - roster_leg             → planning metadata for each leg (plan status, trigger)
#   - flight_legs            → joined to get flight numbers, routes, and times
#   - crew_members           → joined to get crew names and roles
#
# NOTE: crew_id and leg_id are VARCHAR in all tables — always pass as strings

from langchain_core.tools import tool
from sqlalchemy import text
from crew_ops.db.database import get_db_session


# ── Tool 1: Get Crew Roster ───────────────────────────────────────────────────
# Returns the last 20 assignments for a specific crew member.
# Used when a manager asks "what is [name] flying this week?" or similar.

@tool
def get_crew_roster(crew_id: str) -> str:
    """Get the roster assignments for a specific crew member by their crew ID e.g. C001."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                fl.flight_number,
                fl.origin_iata,
                fl.destination_iata,
                fl.scheduled_departure,
                fl.scheduled_arrival,
                rca.status,
                rca.assigned_at
            FROM roster_crew_assignment rca
            JOIN flight_legs fl ON fl.leg_id = rca.leg_id
            WHERE rca.crew_id = :crew_id
            ORDER BY fl.scheduled_departure DESC
            LIMIT 20
        """), {"crew_id": crew_id})
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return f"No roster assignments found for crew ID {crew_id}"

    lines = [
        f"{r.flight_number} | {r.origin_iata}→{r.destination_iata} | "
        f"Dep: {r.scheduled_departure} | Status: {r.status}"
        for r in rows
    ]
    return f"Roster for crew {crew_id} (last 20):\n" + "\n".join(lines)


# ── Tool 2: Get Unassigned Legs ───────────────────────────────────────────────
# Returns upcoming flight legs with no crew assigned.
# Used for gap detection — "which flights still need crew?".

@tool
def get_unassigned_legs() -> str:
    """Get upcoming flight legs that have no crew assigned yet."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                fl.leg_id,
                fl.flight_number,
                fl.origin_iata,
                fl.destination_iata,
                fl.scheduled_departure,
                fl.aircraft_type,
                fl.status
            FROM flight_legs fl
            LEFT JOIN roster_crew_assignment rca ON rca.leg_id = fl.leg_id
            WHERE rca.id IS NULL
              AND fl.scheduled_departure >= NOW()
            ORDER BY fl.scheduled_departure
            LIMIT 50
        """))
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return "All upcoming flight legs have crew assigned."

    lines = [
        f"Leg {r.leg_id} | {r.flight_number} | {r.origin_iata}→{r.destination_iata} | "
        f"Dep: {r.scheduled_departure} | Aircraft: {r.aircraft_type}"
        for r in rows
    ]
    return f"Unassigned legs ({len(rows)}):\n" + "\n".join(lines)


# ── Tool 3: Get Roster Plan Status ───────────────────────────────────────────
# Returns a count breakdown of roster_leg plan statuses.
# Used for a quick health check: "how many legs are confirmed vs pending?".

@tool
def get_roster_plan_status() -> str:
    """Get a summary of roster leg plan statuses — confirmed, pending, failed, etc."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT status, COUNT(*) as count
            FROM roster_leg
            GROUP BY status
            ORDER BY count DESC
        """))
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return "No roster leg plans found."

    lines = [f"{r.status}: {r.count}" for r in rows]
    return "Roster plan status:\n" + "\n".join(lines)