"""
End-to-end cross-service flow tests.
Uses a real EventBus wired in-process. All clients and DB are mocked.
"""
from datetime import datetime, timezone, timedelta, date
from unittest.mock import MagicMock, patch

from crew_ops_backend.services.event_bus import EventBus
from crew_ops_backend.services.observer.observer_service import FlightObserver
from crew_ops_backend.services.disruption_handler.disruption_handler_service import DisruptionHandler
from crew_ops_backend.services.weekly_planner.weekly_planner_service import DailyValidator
from crew_ops_backend.services.flight_time_limits.flight_time_limits_service import FlightTimeLimitsService
from crew_ops_backend.models.events import (
    FlightDisruptedEvent, CrewDisruptedEvent,
    LegCompletedEvent, RosterModifiedEvent,
)
from crew_ops_backend.models.crew_member import CrewMember
from crew_ops_backend.models.flight_leg import FlightLeg
from crew_ops_backend.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState

_DH  = "crew_ops.services.disruption_handler.disruption_handler_service"
_WP  = "crew_ops.services.weekly_planner.weekly_planner_service"
_FTL = "crew_ops.services.flight_time_limits.flight_time_limits_service"
_OBS = "crew_ops.services.observer.observer_service"


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


def _make_crew(crew_id="C-001", role="PILOT"):
    return CrewMember(
        crew_id=crew_id, employee_id="E-001", full_name="Test Crew",
        designation="Captain", role=role, home_base="VABB",
        date_of_joining="2020-01-01", seniority_number=1,
        employment_status="ACTIVE",
    )


def _make_ftl(crew_id="C-001", status="AVAILABLE"):
    return CrewFlightTimeLimitsState(
        crew_id=crew_id, role="PILOT", status=status,
        home_base="VABB", current_airport="VABB",
        flight_hours_current_duty=0.0, sectors_current_duty=0,
        flight_hours_28_day=0.0, duty_hours_7_day=0.0,
        duty_hours_28_day=0.0, consecutive_duty_days=0,
    )


def _mock_session_ctx():
    ctx = MagicMock()
    mock_sl = MagicMock()
    mock_sl.return_value.__enter__ = lambda s: ctx
    mock_sl.return_value.__exit__ = MagicMock(return_value=False)
    return mock_sl, ctx


# ── E1: Observer cancellation → roster invalidated ────────────────────────────

def test_e2e_observer_cancellation_to_roster_invalidated():
    bus     = EventBus()
    handler = DisruptionHandler()
    bus.subscribe(FlightDisruptedEvent, handler.handle_flight_disrupted)

    leg = _make_leg(assigned_crew=["C-001"])
    mock_sl, ctx = _mock_session_ctx()

    with patch(f"{_DH}.get_flight_leg", return_value=leg), \
         patch(f"{_DH}.SessionLocal", mock_sl), \
         patch(f"{_DH}.roster_repository") as mock_repo, \
         patch(f"{_DH}.event_bus", bus):

        dep = _now() + timedelta(hours=3)
        bus.publish(FlightDisruptedEvent(
            leg_id="L-001", flight_number="AI305",
            origin="BOM", destination="DEL",
            disruption_type="CANCELLATION", severity="CRITICAL",
            scheduled_departure=dep, assigned_crew=["C-001"],
            detected_at=_now(),
        ))

    mock_repo.invalidate_roster_leg.assert_called_once_with(ctx, "L-001", "FLIGHT_CANCELLED")


# ── E2: Observer delay + FTL breach → proposal created ───────────────────────

def test_e2e_observer_delay_ftl_breach_creates_proposal():
    bus     = EventBus()
    handler = DisruptionHandler()
    bus.subscribe(FlightDisruptedEvent, handler.handle_flight_disrupted)

    leg = _make_leg(assigned_crew=["C-001"])
    mock_sl, ctx = _mock_session_ctx()

    with patch(f"{_DH}.get_flight_leg", return_value=leg), \
         patch(f"{_DH}.get_crew_member", return_value=_make_crew()), \
         patch(f"{_DH}.get_crew_duty_state", return_value=_make_ftl()), \
         patch(f"{_DH}.get_licenses_for_crew_member", return_value=[]), \
         patch(f"{_DH}.get_leave_records_for_crew", return_value=[]), \
         patch(f"{_DH}.check_legality", return_value=(False, "DUTY_PERIOD_BREACH")), \
         patch(f"{_DH}.get_all_crew_members", return_value=[]), \
         patch(f"{_DH}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_DH}.SessionLocal", mock_sl), \
         patch(f"{_DH}.disruption_repository") as mock_repo, \
         patch(f"{_DH}.roster_repository"):
        mock_repo.pending_proposal_exists.return_value = False
        dep = _now() + timedelta(hours=3)
        bus.publish(FlightDisruptedEvent(
            leg_id="L-001", flight_number="AI305",
            origin="BOM", destination="DEL",
            disruption_type="DELAY", severity="HIGH",
            scheduled_departure=dep, delay_minutes=240,
            assigned_crew=["C-001"], detected_at=_now(),
        ))

    mock_repo.insert_proposal.assert_called_once()


# ── E3: Validator illegal assignment → proposal created ───────────────────────

def test_e2e_validator_illegal_assignment_creates_proposal():
    bus       = EventBus()
    validator = DailyValidator()
    handler   = DisruptionHandler()
    bus.subscribe(CrewDisruptedEvent, handler.handle_crew_disrupted)

    leg  = _make_leg()
    crew = _make_crew()
    ftl  = _make_ftl()
    mock_sl_wp, ctx_wp = _mock_session_ctx()
    mock_sl_dh, ctx_dh = _mock_session_ctx()

    with patch(f"{_WP}.get_all_crew_members", return_value=[crew]), \
         patch(f"{_WP}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_WP}.get_all_licenses", return_value=[]), \
         patch(f"{_WP}.get_all_leave_records", return_value=[]), \
         patch(f"{_WP}.get_flight_leg", return_value=leg), \
         patch(f"{_WP}.check_legality", return_value=(False, "FTL_UNAVAILABLE")), \
         patch(f"{_WP}.SessionLocal", mock_sl_wp), \
         patch(f"{_WP}.roster_repository") as mock_repo_wp, \
         patch(f"{_WP}.event_bus", bus), \
         patch(f"{_DH}.get_flight_leg", return_value=leg), \
         patch(f"{_DH}.get_crew_member", return_value=crew), \
         patch(f"{_DH}.get_all_crew_members", return_value=[]), \
         patch(f"{_DH}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_DH}.SessionLocal", mock_sl_dh), \
         patch(f"{_DH}.disruption_repository") as mock_repo_dh, \
         patch(f"{_DH}.roster_repository"):
        mock_repo_wp.get_future_assignments.return_value = [
            {"leg_id": "L-001", "crew_id": "C-001"}
        ]
        mock_repo_dh.pending_proposal_exists.return_value = False
        validator.validate()

    mock_repo_dh.insert_proposal.assert_called_once()


# ── E4: Accept proposal → FTL updated ────────────────────────────────────────

def test_e2e_accept_proposal_updates_ftl():
    bus         = EventBus()
    ftl_service = FlightTimeLimitsService()
    bus.subscribe(RosterModifiedEvent, ftl_service.on_roster_modified)

    ftl_removed = _make_ftl("C-001", status="AVAILABLE")
    ftl_added   = _make_ftl("C-002", status="UNAVAILABLE")
    updated = []

    with patch(f"{_FTL}.get_crew_duty_state",
               side_effect=[ftl_removed, ftl_added]), \
         patch(f"{_FTL}.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        bus.publish(RosterModifiedEvent(
            leg_id="L-001",
            removed_crew_id="C-001",
            added_crew_id="C-002",
            modified_at=_now(),
        ))

    statuses = {f.crew_id: f.status for f in updated}
    assert statuses["C-001"] == "UNAVAILABLE"
    assert statuses["C-002"] == "AVAILABLE"


# ── E5: Leg completed → FTL hours updated ────────────────────────────────────

def test_e2e_leg_completed_updates_ftl():
    bus         = EventBus()
    ftl_service = FlightTimeLimitsService()
    bus.subscribe(LegCompletedEvent, ftl_service.on_leg_completed)

    leg = _make_leg()
    ftl = _make_ftl("C-001")
    mock_crew = MagicMock()
    mock_crew.home_base = "VABB"
    updated = []

    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=leg), \
         patch(f"{_FTL}.get_crew_duty_state", return_value=ftl), \
         patch(f"{_FTL}.get_crew_member", return_value=mock_crew), \
         patch(f"{_FTL}.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        bus.publish(LegCompletedEvent(
            leg_id="L-001", actual_arrival=_now(),
            destination="VIDP", crew=["C-001"], delay_minutes=0,
        ))

    assert updated[0].status == "RESTING"
    assert updated[0].flight_hours_current_duty > 0


# ── E6: Duplicate proposal guard ─────────────────────────────────────────────

def test_e2e_duplicate_proposal_guard():
    bus     = EventBus()
    handler = DisruptionHandler()
    bus.subscribe(CrewDisruptedEvent, handler.handle_crew_disrupted)

    leg  = _make_leg()
    crew = _make_crew()
    mock_sl, ctx = _mock_session_ctx()

    with patch(f"{_DH}.get_flight_leg", return_value=leg), \
         patch(f"{_DH}.get_crew_member", return_value=crew), \
         patch(f"{_DH}.get_all_crew_members", return_value=[]), \
         patch(f"{_DH}.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops.clients.license_client.get_all_licenses", return_value=[]), \
         patch("crew_ops.clients.leave_client.get_all_leave_records", return_value=[]), \
         patch(f"{_DH}.SessionLocal", mock_sl), \
         patch(f"{_DH}.disruption_repository") as mock_repo, \
         patch(f"{_DH}.roster_repository"):
        # first event: no existing proposal
        mock_repo.pending_proposal_exists.return_value = False
        event = CrewDisruptedEvent(
            crew_id="C-001", crew_name="Test", leg_id="L-001",
            reason="SICK_CALL", days_until_departure=3,
            severity="HIGH", source="OPS_DESK", detected_at=_now(),
        )
        bus.publish(event)

        # second event: proposal now exists
        mock_repo.pending_proposal_exists.return_value = True
        bus.publish(event)

    # insert_proposal called only once despite two events
    assert mock_repo.insert_proposal.call_count == 1
