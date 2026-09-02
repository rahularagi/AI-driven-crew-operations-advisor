"""
Crew Profile Client — API 1 (HRMS)

Mock mode  : reads from database (seeded from mock data)
Real mode  : calls SAP HR / Workday API

Switch: set MOCK_CREW_PROFILE=False in .env to use real API.
"""

from typing import Optional
from crew_ops_backend.config.settings import settings
from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.models.crew_member import CrewMember
from crew_ops_backend.db.repositories import crew_repository


def get_all_crew_members() -> list[CrewMember]:
    if settings.mock_crew_profile:
        return _get_all_crew_members_from_database()
    return _get_all_crew_members_from_hrms_api()


def get_crew_member(crew_id: str) -> Optional[CrewMember]:
    if settings.mock_crew_profile:
        return _get_crew_member_from_database(crew_id)
    return _get_crew_member_from_hrms_api(crew_id)


# ─── Mock (database) implementations ─────────────────────────────────────────

def _get_all_crew_members_from_database() -> list[CrewMember]:
    with SessionLocal() as session:
        return crew_repository.get_all_crew_members(session)


def _get_crew_member_from_database(crew_id: str) -> Optional[CrewMember]:
    with SessionLocal() as session:
        return crew_repository.get_crew_member_by_id(session, crew_id)


# ─── Real API implementations (fill in when going live) ──────────────────────

def _get_all_crew_members_from_hrms_api() -> list[CrewMember]:
    # TODO: implement real SAP HR / Workday API call
    # GET {settings.hrms_api_base_url}/crew
    # headers: {"Authorization": f"Bearer {settings.hrms_api_key}"}
    raise NotImplementedError("Real HRMS API not implemented yet. Set MOCK_CREW_PROFILE=True in .env")


def _get_crew_member_from_hrms_api(crew_id: str) -> Optional[CrewMember]:
    # TODO: implement real SAP HR / Workday API call
    # GET {settings.hrms_api_base_url}/crew/{crew_id}
    raise NotImplementedError("Real HRMS API not implemented yet. Set MOCK_CREW_PROFILE=True in .env")
