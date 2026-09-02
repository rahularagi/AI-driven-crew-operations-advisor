from sqlalchemy.orm import Session
from sqlalchemy import text
from crew_ops_backend.models.crew_license import CrewLicense


def get_licenses_for_crew_member(session: Session, crew_id: str) -> list[CrewLicense]:
    rows = session.execute(
        text("SELECT * FROM crew_licenses WHERE crew_id = :crew_id"),
        {"crew_id": crew_id}
    ).mappings().all()
    return [CrewLicense(**dict(row)) for row in rows]


def get_all_licenses(session: Session) -> list[CrewLicense]:
    rows = session.execute(text("SELECT * FROM crew_licenses")).mappings().all()
    return [CrewLicense(**dict(row)) for row in rows]


def upsert_crew_license(session: Session, license: CrewLicense) -> None:
    session.execute(text("""
        INSERT INTO crew_licenses (
            crew_id, aircraft_type, expiry_date,
            medical_expiry, simulator_check_due, updated_at
        ) VALUES (
            :crew_id, :aircraft_type, :expiry_date,
            :medical_expiry, :simulator_check_due, NOW()
        )
        ON CONFLICT (crew_id, aircraft_type) DO UPDATE SET
            expiry_date             = EXCLUDED.expiry_date,
            medical_expiry          = EXCLUDED.medical_expiry,
            simulator_check_due     = EXCLUDED.simulator_check_due,
            updated_at              = NOW()
    """), license.model_dump(exclude={"created_at", "updated_at"}))
    session.commit()
