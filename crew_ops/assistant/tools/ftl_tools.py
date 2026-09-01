# ftl_tools.py
# These are the tools the LLM can call to fetch Flight Time Limit (FTL)
# and rest compliance data from the DB.
# FTL rules define how many hours a crew member can fly in a given period.
# Violations are a serious safety and regulatory issue — always flag them clearly.

from langchain_core.tools import tool
from sqlalchemy import text

# get_db_session gives us a database session to run queries
from crew_ops.db.database import get_db_session


# ── Tool 1: Get FTL Status ────────────────────────────────────────────────────
# Returns the current FTL status for a specific crew member.
# Shows how many hours they have flown and how many they have remaining
# in the current duty period, week, and month.

@tool
def get_ftl_status(employee_id: str) -> str:
    """Get the current Flight Time Limit (FTL) status for a crew member by their employee ID.
    Shows hours flown and hours remaining in current duty period, week, and month."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                f.employee_id,
                f.duty_hours_today,
                f.duty_hours_limit_today,
                f.flight_hours_7_days,
                f.flight_hours_limit_7_days,
                f.flight_hours_28_days,
                f.flight_hours_limit_28_days,
                f.rest_hours_last,
                f.minimum_rest_required
            FROM ftl_records f
            WHERE f.employee_id = :employee_id
        """), {"employee_id": employee_id})
        row = result.fetchone()

    if not row:
        return f"No FTL records found for employee {employee_id}"

    # Calculate remaining hours for each period
    remaining_today = row.duty_hours_limit_today - row.duty_hours_today
    remaining_7_days = row.flight_hours_limit_7_days - row.flight_hours_7_days
    remaining_28_days = row.flight_hours_limit_28_days - row.flight_hours_28_days

    # Flag if any limit is breached or close to being breached (within 2 hours)
    today_flag = "🔴 LIMIT BREACHED" if remaining_today < 0 else ("⚠️ NEAR LIMIT" if remaining_today < 2 else "✅ OK")
    week_flag = "🔴 LIMIT BREACHED" if remaining_7_days < 0 else ("⚠️ NEAR LIMIT" if remaining_7_days < 2 else "✅ OK")
    month_flag = "🔴 LIMIT BREACHED" if remaining_28_days < 0 else ("⚠️ NEAR LIMIT" if remaining_28_days < 2 else "✅ OK")

    return (
        f"FTL Status for {employee_id}:\n"
        f"Today:   {row.duty_hours_today}h used / {row.duty_hours_limit_today}h limit — {remaining_today:.1f}h remaining {today_flag}\n"
        f"7 days:  {row.flight_hours_7_days}h used / {row.flight_hours_limit_7_days}h limit — {remaining_7_days:.1f}h remaining {week_flag}\n"
        f"28 days: {row.flight_hours_28_days}h used / {row.flight_hours_limit_28_days}h limit — {remaining_28_days:.1f}h remaining {month_flag}\n"
        f"Last rest: {row.rest_hours_last}h | Minimum required: {row.minimum_rest_required}h"
    )


# ── Tool 2: Get Crew Rest Compliance ─────────────────────────────────────────
# Checks whether a crew member has had sufficient rest before their next duty.
# Minimum rest periods are legally mandated — violations must be flagged immediately.

@tool
def get_crew_rest_compliance(employee_id: str) -> str:
    """Check if a crew member has had sufficient legally required rest before their next duty."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                r.employee_id,
                r.rest_start,
                r.rest_end,
                r.rest_hours,
                r.minimum_required,
                r.is_compliant,
                r.next_duty_start
            FROM rest_records r
            WHERE r.employee_id = :employee_id
            ORDER BY r.rest_end DESC
            LIMIT 1
        """), {"employee_id": employee_id})
        row = result.fetchone()

    if not row:
        return f"No rest records found for employee {employee_id}"

    # Clearly flag non-compliant rest — this is a regulatory violation
    if not row.is_compliant:
        return (
            f"🔴 REST VIOLATION for {employee_id}\n"
            f"Rest period: {row.rest_start} to {row.rest_end}\n"
            f"Rest received: {row.rest_hours}h | Minimum required: {row.minimum_required}h\n"
            f"Next duty starts: {row.next_duty_start}\n"
            f"This crew member is NOT compliant for their next duty."
        )

    return (
        f"✅ Rest compliant for {employee_id}\n"
        f"Rest period: {row.rest_start} to {row.rest_end}\n"
        f"Rest received: {row.rest_hours}h | Minimum required: {row.minimum_required}h\n"
        f"Next duty starts: {row.next_duty_start}"
    )


# ── Tool 3: Get Crew Hours Last 28 Days ───────────────────────────────────────
# Returns the total flight hours a crew member has logged in the last 28 days.
# The 28-day rolling limit is a core FTL regulation for most aviation authorities.

@tool
def get_crew_hours_last_28_days(employee_id: str) -> str:
    """Get the total flight hours logged by a crew member in the last 28 days."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                SUM(f.block_hours) AS total_hours,
                COUNT(f.flight_id) AS total_flights
            FROM flight_duties f
            WHERE f.employee_id = :employee_id
              AND f.duty_date >= NOW() - INTERVAL '28 days'
        """), {"employee_id": employee_id})
        row = result.fetchone()

    if not row or row.total_hours is None:
        return f"No flight duties found for employee {employee_id} in the last 28 days."

    return (
        f"Flight hours for {employee_id} — last 28 days:\n"
        f"Total hours: {row.total_hours:.1f}h\n"
        f"Total flights: {row.total_flights}"
    )


# ── Tool 4: Get Crew Approaching FTL Limit ────────────────────────────────────
# Returns all crew members who are within 5 hours of their 28-day FTL limit.
# This is a proactive tool — OCC managers use it to plan ahead and avoid
# last-minute coverage gaps caused by FTL exhaustion.

@tool
def get_crew_approaching_limit() -> str:
    """Get all crew members who are within 5 hours of their 28-day flight time limit."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                f.employee_id,
                c.first_name,
                c.last_name,
                c.role,
                f.flight_hours_28_days,
                f.flight_hours_limit_28_days,
                (f.flight_hours_limit_28_days - f.flight_hours_28_days) AS hours_remaining
            FROM ftl_records f
            JOIN crew_members c ON c.employee_id = f.employee_id
            WHERE (f.flight_hours_limit_28_days - f.flight_hours_28_days) <= 5
              AND (f.flight_hours_limit_28_days - f.flight_hours_28_days) >= 0
            ORDER BY hours_remaining ASC
        """))
        rows = result.fetchall()

    if not rows:
        return "No crew members are currently approaching their 28-day FTL limit."

    lines = [
        f"⚠️ {r.employee_id} | {r.first_name} {r.last_name} | {r.role} | "
        f"{r.flight_hours_28_days}h used / {r.flight_hours_limit_28_days}h limit | "
        f"{r.hours_remaining:.1f}h remaining"
        for r in rows
    ]
    return "Crew approaching 28-day FTL limit:\n" + "\n".join(lines)