# crew_tools.py
# These are the tools the LLM can call to fetch crew member data from the DB.
# Each function is decorated with @tool so LangGraph can register it.
# The docstring of each function is what the LLM reads to decide when to use it.

from langchain_core.tools import tool
from sqlalchemy import text

# get_db_session gives us a database session to run queries
from crew_ops.db.database import get_db_session


# ── Tool 1: Get Available Crew ────────────────────────────────────────────────
# Returns all crew members who are currently available for assignment.
# "Available" means their status in the DB is set to 'available'.

@tool
def get_available_crew() -> str:
    """Get all crew members who are currently available for flight assignment."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                c.employee_id,
                c.first_name,
                c.last_name,
                c.role,
                c.base_airport
            FROM crew_members c
            WHERE c.status = 'available'
            ORDER BY c.role, c.last_name
        """))
        rows = result.fetchall()

    if not rows:
        return "No crew members are currently available."

    # Format each row into a readable line
    lines = [
        f"{r.employee_id} | {r.first_name} {r.last_name} | {r.role} | Base: {r.base_airport}"
        for r in rows
    ]
    return "\n".join(lines)


# ── Tool 2: Get Crew By Role ──────────────────────────────────────────────────
# Filters crew by their role — e.g. Captain, First Officer, Cabin Crew.
# The LLM passes the role string based on what the manager asked.

@tool
def get_crew_by_role(role: str) -> str:
    """Get all crew members with a specific role. Role examples: Captain, First Officer, Cabin Crew."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                c.employee_id,
                c.first_name,
                c.last_name,
                c.status,
                c.base_airport
            FROM crew_members c
            WHERE LOWER(c.role) = LOWER(:role)
            ORDER BY c.last_name
        """), {"role": role})
        rows = result.fetchall()

    if not rows:
        return f"No crew members found with role: {role}"

    lines = [
        f"{r.employee_id} | {r.first_name} {r.last_name} | Status: {r.status} | Base: {r.base_airport}"
        for r in rows
    ]
    return "\n".join(lines)


# ── Tool 3: Get Crew Qualifications ──────────────────────────────────────────
# Returns what aircraft types a specific crew member is qualified to fly.
# The LLM passes the employee_id from a previous tool result.

@tool
def get_crew_qualifications(employee_id: str) -> str:
    """Get the aircraft qualifications for a specific crew member by their employee ID."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                q.aircraft_type,
                q.valid_until
            FROM qualifications q
            WHERE q.employee_id = :employee_id
            ORDER BY q.aircraft_type
        """), {"employee_id": employee_id})
        rows = result.fetchall()

    if not rows:
        return f"No qualifications found for employee {employee_id}"

    lines = [
        f"{r.aircraft_type} — valid until {r.valid_until}"
        for r in rows
    ]
    return f"Qualifications for {employee_id}:\n" + "\n".join(lines)


# ── Tool 4: Get Crew By Base ──────────────────────────────────────────────────
# Returns all crew members based at a specific airport.
# Useful when a manager asks "who do we have at LHR?" or similar.

@tool
def get_crew_by_base(base_airport: str) -> str:
    """Get all crew members based at a specific airport. Pass the IATA airport code e.g. LHR, DXB."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                c.employee_id,
                c.first_name,
                c.last_name,
                c.role,
                c.status
            FROM crew_members c
            WHERE UPPER(c.base_airport) = UPPER(:base_airport)
            ORDER BY c.role, c.last_name
        """), {"base_airport": base_airport})
        rows = result.fetchall()

    if not rows:
        return f"No crew members found based at {base_airport.upper()}"

    lines = [
        f"{r.employee_id} | {r.first_name} {r.last_name} | {r.role} | Status: {r.status}"
        for r in rows
    ]
    return f"Crew at {base_airport.upper()}:\n" + "\n".join(lines)


# ── Tool 5: Get Crew Contact ──────────────────────────────────────────────────
# Returns contact details for a specific crew member.
# Useful when a manager needs to reach someone quickly.

@tool
def get_crew_contact(employee_id: str) -> str:
    """Get contact details (phone, email) for a specific crew member by their employee ID."""
    with get_db_session() as db:
        result = db.execute(text("""
            SELECT
                c.first_name,
                c.last_name,
                c.phone,
                c.email
            FROM crew_members c
            WHERE c.employee_id = :employee_id
        """), {"employee_id": employee_id})
        row = result.fetchone()

    if not row:
        return f"No contact details found for employee {employee_id}"

    return (
        f"{row.first_name} {row.last_name}\n"
        f"Phone: {row.phone}\n"
        f"Email: {row.email}"
    )