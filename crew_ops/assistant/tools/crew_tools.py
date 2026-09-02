# crew_tools.py
# These are the tools the LLM can call to fetch crew member data from the DB.
# Each function is decorated with @tool so LangGraph can register it.
# The docstring of each function is what the LLM reads to decide when to use it.
#
# Tables used:
#   - crew_members        → core crew info (full_name, role, home_base, employment_status)
#   - crew_licenses       → aircraft type ratings and medical validity
#   - crew_leave_records  → approved leave periods
#   - crew_unavailability → ad-hoc unavailability windows (sick, training, etc.)
#
# NOTE: crew_id is VARCHAR in all tables — always pass as string e.g. "C001"

from langchain_core.tools import tool
from sqlalchemy import text
from crew_ops.db.database import get_db_session


# ── Tool 1: Get Available Crew ────────────────────────────────────────────────
# Returns all crew members whose employment_status is 'available'.
# Used when a manager asks "who is free?" or "who can I assign?".

@tool
def get_available_crew() -> str:
    """Get all crew members who are currently available for flight assignment."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                c.employee_id,
                c.full_name,
                c.role,
                c.home_base
            FROM crew_members c
            WHERE c.employment_status = 'available'
            ORDER BY c.role, c.full_name
        """))
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return "No crew members are currently available."

    lines = [
        f"{r.employee_id} | {r.full_name} | {r.role} | Base: {r.home_base}"
        for r in rows
    ]
    return "\n".join(lines)


# ── Tool 2: Get Crew By Role ──────────────────────────────────────────────────
# Filters crew by role string. LLM passes the role based on what the manager asked.
# Case-insensitive match so "captain" and "Captain" both work.

@tool
def get_crew_by_role(role: str) -> str:
    """Get all crew members with a specific role. Examples: Captain, First Officer, Cabin Crew."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                c.employee_id,
                c.full_name,
                c.employment_status,
                c.home_base
            FROM crew_members c
            WHERE LOWER(c.role) = LOWER(:role)
            ORDER BY c.full_name
        """), {"role": role})
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return f"No crew members found with role: {role}"

    lines = [
        f"{r.employee_id} | {r.full_name} | Status: {r.employment_status} | Base: {r.home_base}"
        for r in rows
    ]
    return "\n".join(lines)


# ── Tool 3: Get Crew By Base Airport ─────────────────────────────────────────
# Returns all crew based at a given airport.
# Useful for "who do we have at DXB?" type queries.

@tool
def get_crew_by_base(base_airport: str) -> str:
    """Get all crew members based at a specific airport. Pass the IATA code e.g. LHR, DXB."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT
                c.employee_id,
                c.full_name,
                c.role,
                c.employment_status
            FROM crew_members c
            WHERE UPPER(c.home_base) = UPPER(:base_airport)
            ORDER BY c.role, c.full_name
        """), {"base_airport": base_airport})
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return f"No crew members found based at {base_airport.upper()}"

    lines = [
        f"{r.employee_id} | {r.full_name} | {r.role} | Status: {r.employment_status}"
        for r in rows
    ]
    return f"Crew at {base_airport.upper()}:\n" + "\n".join(lines)


# ── Tool 4: Get Crew Contact ──────────────────────────────────────────────────
# Returns phone and email for a specific crew member.
# LLM uses this after identifying who to contact from a previous tool result.

@tool
def get_crew_contact(employee_id: str) -> str:
    """Get contact details (phone, email) for a specific crew member by their employee ID."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT full_name, phone, email
            FROM crew_members
            WHERE employee_id = :employee_id
        """), {"employee_id": employee_id})
        row = result.fetchone()
    finally:
        db.close()

    if not row:
        return f"No contact details found for employee {employee_id}"

    return f"{row.full_name}\nPhone: {row.phone}\nEmail: {row.email}"


# ── Tool 5: Get Crew Licenses ─────────────────────────────────────────────────
# Returns aircraft type ratings, medical expiry, and simulator check dates.
# Used to verify if a crew member is qualified and current for a given aircraft.

@tool
def get_crew_licenses(crew_id: str) -> str:
    """Get aircraft licenses and medical validity for a crew member by their crew ID e.g. C001."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT aircraft_type, expiry_date, medical_expiry, simulator_check_due
            FROM crew_licenses
            WHERE crew_id = :crew_id
            ORDER BY aircraft_type
        """), {"crew_id": crew_id})
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return f"No licenses found for crew ID {crew_id}"

    lines = [
        f"{r.aircraft_type} | Expires: {r.expiry_date} | Medical: {r.medical_expiry} | Sim check due: {r.simulator_check_due}"
        for r in rows
    ]
    return f"Licenses for crew {crew_id}:\n" + "\n".join(lines)


# ── Tool 6: Get Crew Leave ────────────────────────────────────────────────────
# Returns approved leave records for a crew member.
# Useful when checking why someone is unavailable or planning coverage.

@tool
def get_crew_leave(crew_id: str) -> str:
    """Get leave records for a crew member by their crew ID e.g. C001."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT leave_type, start_date, end_date
            FROM crew_leave_records
            WHERE crew_id = :crew_id
            ORDER BY start_date DESC
        """), {"crew_id": crew_id})
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return f"No leave records found for crew ID {crew_id}"

    lines = [f"{r.leave_type} | {r.start_date} → {r.end_date}" for r in rows]
    return f"Leave records for crew {crew_id}:\n" + "\n".join(lines)


# ── Tool 7: Get Crew Unavailability ──────────────────────────────────────────
# Returns ad-hoc unavailability windows — sick calls, training blocks, etc.
# Different from leave records which are planned and approved in advance.

@tool
def get_crew_unavailability(crew_id: str) -> str:
    """Get unavailability periods for a crew member by their crew ID e.g. C001."""
    db = get_db_session()
    try:
        result = db.execute(text("""
            SELECT reason, from_datetime, to_datetime
            FROM crew_unavailability
            WHERE crew_id = :crew_id
            ORDER BY from_datetime DESC
        """), {"crew_id": crew_id})
        rows = result.fetchall()
    finally:
        db.close()

    if not rows:
        return f"No unavailability records found for crew ID {crew_id}"

    lines = [
        f"{r.reason} | {r.from_datetime} → {r.to_datetime}"
        for r in rows
    ]
    return f"Unavailability for crew {crew_id}:\n" + "\n".join(lines)