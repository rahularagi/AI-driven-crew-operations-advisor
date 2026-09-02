# ftl_tools.py
# These are the tools the LLM can call to fetch Flight Time Limitations (FTL) data.
# Each function is decorated with @tool so LangGraph can register it.
# The docstring of each function is what the LLM reads to decide when to use it.
#
# Tables used:
#   - crew_ftl_states       → live FTL counters per crew member (duty hours, rest, sectors)
#   - crew_reserve_schedule → standby/reserve roster for a given date
#   - crew_members          → joined to get crew names and roles
#
# NOTE: crew_id is VARCHAR in all tables — always pass as string e.g. "C001"

from langchain_core.tools import tool
from sqlalchemy import text
from crew_ops.db.database import get_db_session


# ── Tool 1: Get Crew FTL State ────────────────────────────────────────────────
# Returns the full FTL snapshot for one crew member.
# Used when a manager asks "is [name] legal to fly?" or "how many hours does X have left?".

@tool
def get_crew_ftl_state(crew_id: str) -> str:
    """Get the current Flight Time Limitations (FTL) state for a crew member by their crew ID e.g. C001."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                role,
                status,
                duty_start_time,
                duty_end_time,
                flight_hours_current_duty,
                sectors_current_duty,
                rest_hours_available,
                flight_hours_28_day,
                duty_hours_7_day,
                duty_hours_28_day,
                consecutive_duty_days,
                max_duty_period_hours,
                current_airport,
                home_base,
                at_home_base,
                earliest_checkout,
                last_updated
            FROM crew_ftl_states
            WHERE crew_id = :crew_id
        """), {"crew_id": crew_id})
        row = result.fetchone()
    finally:
        db.close()

    if not row:
        return f"No FTL state found for crew ID {crew_id}"

    return (
        f"FTL State — Crew {crew_id} ({row.role})\n"
        f"Status: {row.status}\n"
        f"Current airport: {row.current_airport} | Home base: {row.home_base} | At home: {row.at_home_base}\n"
        f"Duty start: {row.duty_start_time} | Duty end: {row.duty_end_time}\n"
        f"Flight hours (current duty): {row.flight_hours_current_duty}\n"
        f"Sectors (current duty): {row.sectors_current_duty}\n"
        f"Rest available: {row.rest_hours_available} hrs\n"
        f"Flight hours (28-day): {row.flight_hours_28_day}\n"
        f"Duty hours (7-day): {row.duty_hours_7_day} | (28-day): {row.duty_hours_28_day}\n"
        f"Consecutive duty days: {row.consecutive_duty_days}\n"
        f"Max duty period: {row.max_duty_period_hours} hrs\n"
        f"Earliest checkout: {row.earliest_checkout}\n"
        f"Last updated: {row.last_updated}"
    )


# ── Tool 2: Get Crew Near FTL Limit ──────────────────────────────────────────
# Returns all crew whose FTL status is near_limit, exceeded, or rest_required.
# Used for daily compliance checks or when a manager asks about FTL risk.

@tool
def get_crew_near_ftl_limit() -> str:
    """Get all crew members who are approaching or have exceeded FTL limits."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                f.crew_id,
                c.full_name,
                c.role,
                f.status,
                f.flight_hours_28_day,
                f.duty_hours_7_day,
                f.rest_hours_available,
                f.consecutive_duty_days
            FROM crew_ftl_states f
            JOIN crew_members c ON c.crew_id = f.crew_id
            WHERE f.status IN ('near_limit', 'exceeded', 'rest_required')
            ORDER BY f.flight_hours_28_day DESC
        """))
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return "No crew members are currently near or over FTL limits."

    lines = [
        f"{r.full_name} ({r.role}) | Status: {r.status} | "
        f"28-day hrs: {r.flight_hours_28_day} | 7-day duty: {r.duty_hours_7_day} | "
        f"Rest available: {r.rest_hours_available} hrs | Consecutive days: {r.consecutive_duty_days}"
        for r in rows
    ]
    return f"Crew near/over FTL limits ({len(rows)}):\n" + "\n".join(lines)


# ── Tool 3: Get Reserve Crew ──────────────────────────────────────────────────
# Returns crew on standby/reserve for a given date.
# Used when a manager needs to find cover quickly for a disrupted flight.

@tool
def get_reserve_crew(date: str) -> str:
    """Get crew members on reserve/standby for a given date. Date format: YYYY-MM-DD."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                r.crew_id,
                c.full_name,
                c.role,
                r.standby_start,
                r.standby_end,
                r.base_airport,
                r.callable_within,
                r.status
            FROM crew_reserve_schedule r
            JOIN crew_members c ON c.crew_id = r.crew_id
            WHERE r.date = :date
            ORDER BY r.standby_start
        """), {"date": date})
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return f"No reserve crew scheduled for {date}"

    lines = [
        f"{r.full_name} ({r.role}) | {r.standby_start}–{r.standby_end} | "
        f"Base: {r.base_airport} | Callable within: {r.callable_within} min | Status: {r.status}"
        for r in rows
    ]
    return f"Reserve crew for {date} ({len(rows)}):\n" + "\n".join(lines)