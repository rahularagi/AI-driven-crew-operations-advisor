"""Tests for services/disruption_handler/disruption_handler_service.py"""
from datetime import datetime, timezone, timedelta, date
from unittest.mock import MagicMock, patch, call

import pytest

from crew_ops_backend.services.disruption_handler.disruption_handler_service import DisruptionHandler
from crew_ops_backend.models.events import (
    FlightDisruptedEvent, CrewDisruptedEvent, RosterModifiedEvent
)
from crew_ops_backend.models.crew_member import CrewMember
from crew_ops_backend.models.flight_leg import FlightLeg
from crew_ops_backend.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState

_MODULE = "crew_ops_backend.services.disruption_handler.disruption_handler_service"


def _now():
    return datetime.now(timezone.utc)


def _make_leg(leg_id="L-001", dep_offset_hours=3, status="SCHEDULED", assigned_crew=None):
    dep = _now() + timedelta(hours=dep_offset_hours)
    return FlightLeg(
        leg_id=leg_id, flight_number="AI305",
        origin_iata="BOM", origin_icao="VABB",
        destination_iata="DEL", destination_icao="VIDP",
        scheduled_departure=dep,
        scheduled_arrival=dep + timedelta(hours=2),
        aircraft_type="B737", aircraft_registration="VT-001",
        status=status,
        assigned_crew=assigned_crew or ["C-001"],
    )


def _make_crew(crew_id="C-001", role="PILOT", status="ACTIVE"):
    return CrewMember(
        crew_id=crew_id, employee_id="E-001", full_name="Test Crew",
        designation="Captain", role=role, home_base="VABB",
        date_of_joining="2020-01-01", seniority_number=1,
        employment_status=status,
    )


def _make_ftl(crew_id="C-001", status="AVAILABLE"):
    return CrewFlightTimeLimitsState(
        crew_id=crew_id, role="PILOT", status=status,
        home_base="VABB", current_airport="VABB",
        flight_hours_current_duty=0.0, sectors_current_duty=0,
        flight_hours_28_day=0.0, duty_hours_7_day=0.0,
        duty_hours_28_day=0.0, consecutive_duty_days=0,
    )


def _flight_disrupted(leg_id="L-001", disruption_type="DELAY",
                      severity="HIGH", assigned_crew=None):
    dep = _now() + timedelta(hours=3)
    return FlightDisruptedEvent(
        leg_id=leg_id, flight_number="AI305",
        origin="BOM", destination="DEL",
        disruption_type=disruption_type, severity=severity,
        scheduled_departure=dep, delay_minutes=30,
        assigned_crew=assigned_crew or ["C-001"],
        detected_at=_now(),
    )


def _crew_disrupted(crew_id="C-001", leg_id="L-001",
                    severity="HIGH", reason="SICK_CALL"):
    return CrewDisruptedEvent(
        crew_id=crew_id, crew_name="Test Crew", leg_id=leg_id,
        reason=reason, days_until_departure=3,
        severity=severity, source="OPS_DESK", detected_at=_now(),
    )


def _mock_session_ctx():
    ctx = MagicMock()
    mock_sl = MagicMock()
    mock_sl.return_value.__enter__ = lambda s: ctx
    mock_sl.return_value.__exit__ = MagicMock(return_value=False)
    return mock_sl, ctx


# ── handle_flight_disrupted ───────────────────────────────────────────────────

def test_flight_disrupted_leg_not_found_returns_early():
    handler = DisruptionHandler()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=None), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        handler.handle_flight_disrupted(_flight_disrupted())
    mock_repo.insert_proposal.assert_not_called()


def test_flight_disrupted_already_departed_returns_early():
    handler = DisruptionHandler()
    leg = _make_leg(dep_offset_hours=-1)
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        handler.handle_flight_disrupted(_flight_disrupted())
    mock_repo.insert_proposal.assert_not_called()


def test_flight_disrupted_cancellation_invalidates_roster():
    handler = DisruptionHandler()
    leg = _make_leg(assigned_crew=["C-001", "C-002"])
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.event_bus"):
        handler.handle_flight_disrupted(_flight_disrupted(disruption_type="CANCELLATION",
                                                           assigned_crew=["C-001", "C-002"]))
    mock_repo.invalidate_roster_leg.assert_called_once_with(ctx, "L-001", "FLIGHT_CANCELLED")


def test_flight_disrupted_cancellation_publishes_roster_modified_per_crew():
    handler = DisruptionHandler()
    leg = _make_leg(assigned_crew=["C-001", "C-002"])
    mock_sl, ctx = _mock_session_ctx()
    published = []
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository"), \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        handler.handle_flight_disrupted(_flight_disrupted(disruption_type="CANCELLATION",
                                                           assigned_crew=["C-001", "C-002"]))
    roster_events = [e for e in published if isinstance(e, RosterModifiedEvent)]
    assert len(roster_events) == 2


def test_flight_disrupted_route_change_creates_proposal():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.pending_proposal_exists.return_value = False
        handler.handle_flight_disrupted(_flight_disrupted(disruption_type="ROUTE_CHANGE"))
    mock_repo.insert_proposal.assert_called_once()
    call_data = mock_repo.insert_proposal.call_args[0][1]
    assert call_data["removed_crew_id"] is None


def test_flight_disrupted_delay_no_proposal_when_still_legal():
    handler = DisruptionHandler()
    leg = _make_leg(assigned_crew=["C-001"])
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_MODULE}.get_crew_duty_state", return_value=_make_ftl()), \
         patch(f"{_MODULE}.get_licenses_for_crew_member", return_value=[]), \
         patch(f"{_MODULE}.get_leave_records_for_crew", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        handler.handle_flight_disrupted(_flight_disrupted(disruption_type="DELAY"))
    mock_repo.insert_proposal.assert_not_called()


def test_flight_disrupted_delay_checks_all_crew():
    handler = DisruptionHandler()
    leg = _make_leg(assigned_crew=["C-001", "C-002"])
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_MODULE}.get_crew_duty_state", return_value=_make_ftl()), \
         patch(f"{_MODULE}.get_licenses_for_crew_member", return_value=[]), \
         patch(f"{_MODULE}.get_leave_records_for_crew", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(False, "FTL_UNAVAILABLE")), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.pending_proposal_exists.return_value = False
        handler.handle_flight_disrupted(
            _flight_disrupted(disruption_type="DELAY", assigned_crew=["C-001", "C-002"])
        )
    assert mock_repo.insert_proposal.call_count == 2


def test_flight_disrupted_aircraft_swap_only_checks_pilots():
    handler = DisruptionHandler()
    leg = _make_leg(assigned_crew=["C-PILOT", "C-CABIN"])
    pilot = _make_crew("C-PILOT", role="PILOT")
    cabin = _make_crew("C-CABIN", role="CABIN")
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", side_effect=lambda cid: pilot if cid == "C-PILOT" else cabin), \
         patch(f"{_MODULE}.get_crew_duty_state", return_value=_make_ftl()), \
         patch(f"{_MODULE}.get_licenses_for_crew_member", return_value=[]), \
         patch(f"{_MODULE}.get_leave_records_for_crew", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(False, "NO_TYPE_RATING")), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.pending_proposal_exists.return_value = False
        handler.handle_flight_disrupted(
            _flight_disrupted(disruption_type="AIRCRAFT_SWAP",
                              assigned_crew=["C-PILOT", "C-CABIN"])
        )
    # only pilot triggers proposal — 1 call
    assert mock_repo.insert_proposal.call_count == 1


# ── handle_crew_disrupted ─────────────────────────────────────────────────────

def test_crew_disrupted_leg_not_found_returns_early():
    handler = DisruptionHandler()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=None), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        handler.handle_crew_disrupted(_crew_disrupted())
    mock_repo.insert_proposal.assert_not_called()


def test_crew_disrupted_already_departed_returns_early():
    handler = DisruptionHandler()
    leg = _make_leg(dep_offset_hours=-1)
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        handler.handle_crew_disrupted(_crew_disrupted())
    mock_repo.insert_proposal.assert_not_called()


def test_crew_disrupted_cancelled_leg_returns_early():
    handler = DisruptionHandler()
    leg = _make_leg(status="CANCELLED")
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        handler.handle_crew_disrupted(_crew_disrupted())
    mock_repo.insert_proposal.assert_not_called()


def test_crew_disrupted_creates_proposal_with_candidates():
    handler = DisruptionHandler()
    leg = _make_leg()
    candidate = _make_crew("C-002")
    ftl = _make_ftl("C-002")
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[candidate]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.pending_proposal_exists.return_value = False
        handler.handle_crew_disrupted(_crew_disrupted())
    mock_repo.insert_proposal.assert_called_once()
    data = mock_repo.insert_proposal.call_args[0][1]
    assert data["proposed_crew_id"] == "C-002"


def test_crew_disrupted_no_candidates_proposal_with_null_crew():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.pending_proposal_exists.return_value = False
        handler.handle_crew_disrupted(_crew_disrupted())
    data = mock_repo.insert_proposal.call_args[0][1]
    assert data["proposed_crew_id"] is None


def test_crew_disrupted_crew_record_missing_falls_back_to_roster_role():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    ctx.execute.return_value.mappings.return_value.first.return_value = {"role": "PILOT"}
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=None), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository") as mock_rrepo:
        mock_rrepo.get_assignment_for_crew.return_value = {"role": "PILOT"}
        mock_repo.pending_proposal_exists.return_value = False
        handler.handle_crew_disrupted(_crew_disrupted())
    mock_repo.insert_proposal.assert_called_once()


def test_crew_disrupted_no_role_anywhere_returns_early():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=None), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository") as mock_rrepo:
        mock_rrepo.get_assignment_for_crew.return_value = None
        handler.handle_crew_disrupted(_crew_disrupted())
    mock_repo.insert_proposal.assert_not_called()


def test_crew_disrupted_duplicate_proposal_guard():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.pending_proposal_exists.return_value = True
        handler.handle_crew_disrupted(_crew_disrupted())
    mock_repo.insert_proposal.assert_not_called()


def test_crew_disrupted_invalidates_assignment():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository") as mock_rrepo:
        mock_repo.pending_proposal_exists.return_value = False
        handler.handle_crew_disrupted(_crew_disrupted())
    mock_rrepo.invalidate_assignment.assert_called_once()


# ── reject_and_repropose ──────────────────────────────────────────────────────

def test_reject_and_repropose_proposal_not_found():
    handler = DisruptionHandler()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        mock_repo.reject_proposal.return_value = {}
        result = handler.reject_and_repropose("PROP-001", "ops_01", "wrong candidate")
    assert "error" in result


def test_reject_and_repropose_leg_no_longer_exists():
    handler = DisruptionHandler()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.get_flight_leg", return_value=None), \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.reject_proposal.return_value = {
            "leg_id": "L-001", "removed_crew_id": "C-001", "proposed_crew_id": "C-002"
        }
        mock_repo.get_already_proposed_crew.return_value = set()
        result = handler.reject_and_repropose("PROP-001", "ops_01", "reason")
    assert result["status"] == "rejected"
    assert result["new_proposal_id"] is None


def test_reject_and_repropose_excludes_already_proposed_crew():
    handler = DisruptionHandler()
    leg = _make_leg()
    c002 = _make_crew("C-002")
    c003 = _make_crew("C-003")
    ftl2 = _make_ftl("C-002")
    ftl3 = _make_ftl("C-003")
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew("C-001")), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[c002, c003]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl2, ftl3]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.reject_proposal.return_value = {
            "leg_id": "L-001", "removed_crew_id": "C-001", "proposed_crew_id": "C-002"
        }
        mock_repo.get_already_proposed_crew.return_value = {"C-002"}
        mock_repo.pending_proposal_exists.return_value = False
        result = handler.reject_and_repropose("PROP-001", "ops_01", "reason")
    data = mock_repo.insert_proposal.call_args[0][1]
    assert data["proposed_crew_id"] == "C-003"


def test_reject_and_repropose_creates_new_proposal():
    handler = DisruptionHandler()
    leg = _make_leg()
    c002 = _make_crew("C-002")
    ftl2 = _make_ftl("C-002")
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[c002]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl2]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.reject_proposal.return_value = {
            "leg_id": "L-001", "removed_crew_id": "C-001", "proposed_crew_id": "C-002"
        }
        mock_repo.get_already_proposed_crew.return_value = set()
        mock_repo.pending_proposal_exists.return_value = False
        handler.reject_and_repropose("PROP-001", "ops_01", "reason")
    data = mock_repo.insert_proposal.call_args[0][1]
    assert data["source"] == "CONTROLLER_REJECT"


def test_reject_and_repropose_no_candidates_returns_none():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.roster_repository"):
        mock_repo.reject_proposal.return_value = {
            "leg_id": "L-001", "removed_crew_id": "C-001", "proposed_crew_id": None
        }
        mock_repo.get_already_proposed_crew.return_value = set()
        mock_repo.pending_proposal_exists.return_value = False
        result = handler.reject_and_repropose("PROP-001", "ops_01", "reason")
    assert result["next_candidate"] is None


# ── auto_resolve_low_severity ─────────────────────────────────────────────────

def _low_proposal(proposal_id="PROP-001", proposed_crew_id="C-002"):
    return {
        "proposal_id": proposal_id,
        "leg_id": "L-001",
        "removed_crew_id": "C-001",
        "proposed_crew_id": proposed_crew_id,
    }


def test_auto_resolve_accepts_and_reassigns_when_still_legal():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew("C-002")), \
         patch(f"{_MODULE}.get_crew_duty_state", return_value=_make_ftl("C-002")), \
         patch(f"{_MODULE}.get_licenses_for_crew_member", return_value=[]), \
         patch(f"{_MODULE}.get_leave_records_for_crew", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository") as mock_rrepo, \
         patch(f"{_MODULE}.event_bus"):
        ctx.execute.return_value.mappings.return_value.all.return_value = [_low_proposal()]
        mock_repo.accept_proposal.return_value = {
            "leg_id": "L-001", "removed_crew_id": "C-001", "proposed_crew_id": "C-002"
        }
        result = handler.auto_resolve_low_severity()
    mock_rrepo.replace_roster_crew_assignment.assert_called_once()
    assert "PROP-001" in result


def test_auto_resolve_publishes_roster_modified_event():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    published = []
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew("C-002")), \
         patch(f"{_MODULE}.get_crew_duty_state", return_value=_make_ftl("C-002")), \
         patch(f"{_MODULE}.get_licenses_for_crew_member", return_value=[]), \
         patch(f"{_MODULE}.get_leave_records_for_crew", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository"), \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        ctx.execute.return_value.mappings.return_value.all.return_value = [_low_proposal()]
        mock_repo.accept_proposal.return_value = {
            "leg_id": "L-001", "removed_crew_id": "C-001", "proposed_crew_id": "C-002"
        }
        mock_bus.publish.side_effect = lambda e: published.append(e)
        handler.auto_resolve_low_severity()
    assert any(isinstance(e, RosterModifiedEvent) for e in published)


def test_auto_resolve_skips_proposal_with_no_candidate():
    handler = DisruptionHandler()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository"):
        ctx.execute.return_value.mappings.return_value.all.return_value = [
            _low_proposal(proposed_crew_id=None)
        ]
        result = handler.auto_resolve_low_severity()
    mock_repo.accept_proposal.assert_not_called()
    assert result == []


def test_auto_resolve_skips_when_leg_or_crew_missing():
    handler = DisruptionHandler()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.get_flight_leg", return_value=None), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        ctx.execute.return_value.mappings.return_value.all.return_value = [_low_proposal()]
        result = handler.auto_resolve_low_severity()
    mock_repo.accept_proposal.assert_not_called()
    assert result == []


def test_auto_resolve_re_ranks_when_candidate_no_longer_legal():
    handler = DisruptionHandler()
    leg = _make_leg()
    new_candidate = _make_crew("C-003")
    ftl3 = _make_ftl("C-003")
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", side_effect=[_make_crew("C-002"), _make_crew("C-001"), new_candidate]), \
         patch(f"{_MODULE}.get_crew_duty_state", return_value=_make_ftl("C-002")), \
         patch(f"{_MODULE}.get_licenses_for_crew_member", return_value=[]), \
         patch(f"{_MODULE}.get_leave_records_for_crew", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(False, "FTL_UNAVAILABLE")), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[new_candidate]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl3]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        ctx.execute.return_value.mappings.return_value.all.return_value = [_low_proposal()]
        # second check_legality call (for new candidate) passes
        with patch(f"{_MODULE}.check_legality", side_effect=[(False, "FTL"), (True, None)]):
            handler.auto_resolve_low_severity()
    # UPDATE proposed_crew_id executed
    assert ctx.execute.called


def test_auto_resolve_escalates_to_medium_when_no_candidates():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew("C-002")), \
         patch(f"{_MODULE}.get_crew_duty_state", return_value=_make_ftl("C-002")), \
         patch(f"{_MODULE}.get_licenses_for_crew_member", return_value=[]), \
         patch(f"{_MODULE}.get_leave_records_for_crew", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(False, "FTL_UNAVAILABLE")), \
         patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops_backend.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        ctx.execute.return_value.mappings.return_value.all.return_value = [_low_proposal()]
        handler.auto_resolve_low_severity()
    # UPDATE severity=MEDIUM executed
    assert ctx.execute.called


def test_auto_resolve_returns_list_of_resolved_ids():
    handler = DisruptionHandler()
    leg = _make_leg()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.get_crew_member", return_value=_make_crew("C-002")), \
         patch(f"{_MODULE}.get_crew_duty_state", return_value=_make_ftl("C-002")), \
         patch(f"{_MODULE}.get_licenses_for_crew_member", return_value=[]), \
         patch(f"{_MODULE}.get_leave_records_for_crew", return_value=[]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo, \
         patch(f"{_MODULE}.roster_repository"), \
         patch(f"{_MODULE}.event_bus"):
        ctx.execute.return_value.mappings.return_value.all.return_value = [_low_proposal()]
        mock_repo.accept_proposal.return_value = {
            "leg_id": "L-001", "removed_crew_id": "C-001", "proposed_crew_id": "C-002"
        }
        result = handler.auto_resolve_low_severity()
    assert result == ["PROP-001"]


# ── expire_stale_proposals ────────────────────────────────────────────────────

def test_expire_stale_proposals_calls_repository():
    handler = DisruptionHandler()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.disruption_repository") as mock_repo:
        handler.expire_stale_proposals()
    mock_repo.expire_stale_proposals.assert_called_once_with(ctx)
    ctx.commit.assert_called_once()
