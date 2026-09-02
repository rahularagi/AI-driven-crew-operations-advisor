from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from crew_ops_backend.models.crew_member import CrewMember


def get_all_crew_members(session: Session) -> list[CrewMember]:
    rows = session.execute(text("SELECT * FROM crew_members ORDER BY seniority_number")).mappings().all()
    return [CrewMember(**dict(row)) for row in rows]


def get_crew_member_by_id(session: Session, crew_id: str) -> Optional[CrewMember]:
    row = session.execute(
        text("SELECT * FROM crew_members WHERE crew_id = :crew_id"),
        {"crew_id": crew_id}
    ).mappings().first()
    return CrewMember(**dict(row)) if row else None


def upsert_crew_member(session: Session, crew_member: CrewMember) -> None:
    session.execute(text("""
        INSERT INTO crew_members (
            crew_id, employee_id, full_name, designation, role,
            home_base, date_of_joining, seniority_number,
            employment_status, phone, email, updated_at
        ) VALUES (
            :crew_id, :employee_id, :full_name, :designation, :role,
            :home_base, :date_of_joining, :seniority_number,
            :employment_status, :phone, :email, NOW()
        )
        ON CONFLICT (crew_id) DO UPDATE SET
            full_name           = EXCLUDED.full_name,
            designation         = EXCLUDED.designation,
            role                = EXCLUDED.role,
            home_base           = EXCLUDED.home_base,
            seniority_number    = EXCLUDED.seniority_number,
            employment_status   = EXCLUDED.employment_status,
            phone               = EXCLUDED.phone,
            email               = EXCLUDED.email,
            updated_at          = NOW()
    """), crew_member.model_dump(exclude={"created_at", "updated_at"}))
    session.commit()
