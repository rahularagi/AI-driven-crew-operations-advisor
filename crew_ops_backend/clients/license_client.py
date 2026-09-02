"""
License Client — API 2 (License Management)

Mock mode  : reads from database (seeded from mock data)
Real mode  : calls License Management API

Switch: set MOCK_LICENSE=False in .env to use real API.
"""

from crew_ops_backend.config.settings import settings
from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.models.crew_license import CrewLicense
from crew_ops_backend.db.repositories import license_repository


def get_licenses_for_crew_member(crew_id: str) -> list[CrewLicense]:
    if settings.mock_license:
        return _get_licenses_from_database(crew_id)
    return _get_licenses_from_real_api(crew_id)


def get_all_licenses() -> list[CrewLicense]:
    if settings.mock_license:
        return _get_all_licenses_from_database()
    return _get_all_licenses_from_real_api()


# ─── Mock (database) implementations ─────────────────────────────────────────

def _get_licenses_from_database(crew_id: str) -> list[CrewLicense]:
    with SessionLocal() as session:
        return license_repository.get_licenses_for_crew_member(session, crew_id)


def _get_all_licenses_from_database() -> list[CrewLicense]:
    with SessionLocal() as session:
        return license_repository.get_all_licenses(session)


# ─── Real API implementations (fill in when going live) ──────────────────────

def _get_licenses_from_real_api(crew_id: str) -> list[CrewLicense]:
    raise NotImplementedError("Real License API not implemented yet. Set MOCK_LICENSE=True in .env")


def _get_all_licenses_from_real_api() -> list[CrewLicense]:
    raise NotImplementedError("Real License API not implemented yet. Set MOCK_LICENSE=True in .env")
