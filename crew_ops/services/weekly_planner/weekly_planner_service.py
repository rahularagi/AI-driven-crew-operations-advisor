"""
Service 1 — Weekly Planner

Job A: RosterPlanner   — builds crew roster for a given date window
  Scheduled trigger : build() — Sunday night, uses configured planning horizon
  Manual trigger    : build(requested_by="manager_01") — same as scheduled, on demand
  Date range        : build(start, end, requested_by) — manager specifies exact window
  Publishes         : CrewDisruptedEvent (if validation finds issues after build)

Job B: DailyValidator  — re-checks all future planned weeks against current reality
  Scheduled trigger : validate() — 3AM daily
  Manual trigger    : validate(requested_by) — manager forces a re-check on demand
  Subscribes to     : RosterModifiedEvent → on_roster_modified()
  Publishes         : CrewDisruptedEvent per affected leg
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, time, timezone
from typing import Optional

from crew_ops.clients.crew_profile_client import get_all_crew_members
from crew_ops.clients.flight_schedule_client import get_legs_for_date_range, get_flight_leg
from crew_ops.clients.ftl_client import get_all_crew_duty_states
from crew_ops.clients.license_client import get_all_licenses
from crew_ops.clients.leave_client import get_all_leave_records
from crew_ops.db.database import SessionLocal
from crew_ops.db.repositories import roster_repository, reserve_repository
from crew_ops.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops.models.crew_reserve import CrewReserveSchedule
from crew_ops.models.events import CrewDisruptedEvent, RosterModifiedEvent
from crew_ops.rules.crew_requirements import required_pilots, required_cabin
from crew_ops.rules.ftl_simulator import simulate_leg_assigned
from crew_ops.rules.legality import check_legality
from crew_ops.services.event_bus import event_bus
from crew_ops.config.settings import settings


class RosterPlanner:
    """
    Single build() method handles all trigger types.

    - No arguments         → scheduler call, uses today + settings.roster_planning_weeks
    - requested_by only    → manual full rebuild, same window as scheduler
    - start + end + requested_by → manager-specified date range
    """

    def build(
        self,
        start: date | None = None,
        end: date | None = None,
        requested_by: str = "SCHEDULER",
    ) -> None:
        resolved_start = start or date.today()
        resolved_end = end or (resolved_start + timedelta(weeks=settings.roster_planning_weeks))

        if resolved_end < resolved_start:
            raise ValueError(f"end date {resolved_end} cannot be before start date {resolved_start}")

        self._run_build(start=resolved_start, end=resolved_end, triggered_by=requested_by)

    def _run_build(self, start: date, end: date, triggered_by: str) -> None:
        all_crew     = get_all_crew_members()
        all_licenses = get_all_licenses()
        all_leave    = get_all_leave_records()

        # Pre-filter inactive crew — they never enter the candidate pool
        crew_by_id = {c.crew_id: c for c in all_crew if c.employment_status == "ACTIVE"}

        licenses_by_crew: dict = defaultdict(list)
        for lic in all_licenses:
            licenses_by_crew[lic.crew_id].append(lic)

        leave_by_crew: dict = defaultdict(list)
        for leave in all_leave:
            leave_by_crew[leave.crew_id].append(leave)

        # Simulated FTL starts from live state, carries forward week to week
        simulated_ftl = {f.crew_id: f.model_copy(deep=True) for f in get_all_crew_duty_states()}

        week_start = start
        while week_start <= end:
            week_end = min(week_start + timedelta(days=6), end)
            legs = get_legs_for_date_range(week_start, week_end)

            if not legs:
                week_start += timedelta(weeks=1)
                continue

            assignments   = _pass1_assign_crew(legs, crew_by_id, simulated_ftl, licenses_by_crew, leave_by_crew)
            reserve_slots = _pass2_fill_reserve(legs, assignments, crew_by_id, simulated_ftl, week_start, week_end)
            _pass3_validate(legs, assignments, crew_by_id, simulated_ftl, licenses_by_crew, leave_by_crew)

            with SessionLocal() as session:
                _write_roster(session, assignments, reserve_slots, week_start, week_end, triggered_by)

            # Advance simulated FTL for next week
            for leg in sorted(legs, key=lambda l: l.scheduled_departure):
                for crew_id in assignments.get(leg.leg_id, []):
                    if crew_id in simulated_ftl:
                        simulated_ftl[crew_id] = simulate_leg_assigned(simulated_ftl[crew_id], leg)

            week_start += timedelta(weeks=1)


class DailyValidator:

    def validate(self, requested_by: str = "SCHEDULER") -> None:
        self._run_validation(triggered_by=requested_by)

    def on_roster_modified(self, event: RosterModifiedEvent) -> None:
        crew_ids = [c for c in [event.added_crew_id, event.removed_crew_id] if c]
        for crew_id in crew_ids:
            self._run_validation(triggered_by="ROSTER_MODIFIED", crew_id=crew_id)

    def _run_validation(self, triggered_by: str, crew_id: Optional[str] = None) -> None:
        today = date.today()

        all_crew       = get_all_crew_members()
        all_licenses   = get_all_licenses()
        all_leave      = get_all_leave_records()
        all_ftl_states = get_all_crew_duty_states()

        crew_by_id = {c.crew_id: c for c in all_crew}
        ftl_by_id  = {f.crew_id: f for f in all_ftl_states}

        licenses_by_crew: dict = defaultdict(list)
        for lic in all_licenses:
            licenses_by_crew[lic.crew_id].append(lic)

        leave_by_crew: dict = defaultdict(list)
        for leave in all_leave:
            leave_by_crew[leave.crew_id].append(leave)

        # Fetch assignments 2 days at a time
        current = today
        with SessionLocal() as session:
            while True:
                batch_end = current + timedelta(days=1)
                batch = roster_repository.get_future_assignments(
                    session, from_date=current, to_date=batch_end, crew_id=crew_id
                )
                if not batch:
                    break

                for assignment in batch:
                    leg  = get_flight_leg(assignment["leg_id"])
                    crew = crew_by_id.get(assignment["crew_id"])
                    ftl  = ftl_by_id.get(assignment["crew_id"])

                    if not leg or not crew or not ftl:
                        continue

                    leg_date = leg.scheduled_departure.date()
                    passed, reason = check_legality(
                        crew, leg, ftl,
                        licenses_by_crew.get(assignment["crew_id"], []),
                        leave_by_crew.get(assignment["crew_id"], []),
                        leg_date,
                    )

                    if not passed:
                        days_until = (leg_date - today).days
                        event_bus.publish(CrewDisruptedEvent(
                            crew_id              = assignment["crew_id"],
                            crew_name            = crew.full_name,
                            leg_id               = assignment["leg_id"],
                            reason               = reason,
                            days_until_departure = days_until,
                            severity             = _classify_severity(days_until),
                            source               = "WEEKLY_PLANNER_VALIDATOR",
                            detected_at          = datetime.now(timezone.utc),
                        ))

                current = batch_end + timedelta(days=1)


# ─── Pass 1 — Assign operating crew to legs ───────────────────────────────────

def _pass1_assign_crew(
    legs: list,
    crew_by_id: dict,
    ftl_by_id: dict,
    licenses_by_crew: dict,
    leave_by_crew: dict,
) -> dict[str, list[str]]:
    assignments: dict[str, list[str]] = {}

    for leg in sorted(legs, key=lambda l: l.scheduled_departure):
        leg_date    = leg.scheduled_departure.date()
        need_pilots = required_pilots(leg.aircraft_type)
        need_cabin  = required_cabin(leg.aircraft_type)

        pilot_candidates = []
        cabin_candidates = []

        for crew in crew_by_id.values():
            ftl = ftl_by_id.get(crew.crew_id)
            if ftl is None:
                continue
            passed, _ = check_legality(
                crew, leg, ftl,
                licenses_by_crew.get(crew.crew_id, []),
                leave_by_crew.get(crew.crew_id, []),
                leg_date,
            )
            if passed:
                score = _score_candidate(crew, ftl, leg)
                if crew.role == "PILOT":
                    pilot_candidates.append((score, crew, ftl))
                else:
                    cabin_candidates.append((score, crew, ftl))

        pilot_candidates.sort(key=lambda x: x[0], reverse=True)
        cabin_candidates.sort(key=lambda x: x[0], reverse=True)

        assigned = []
        for _, crew, ftl in pilot_candidates[:need_pilots] + cabin_candidates[:need_cabin]:
            assigned.append(crew.crew_id)
            ftl_by_id[crew.crew_id] = simulate_leg_assigned(ftl, leg)

        assignments[leg.leg_id] = assigned

    return assignments


# ─── Pass 2 — Fill reserve slots ──────────────────────────────────────────────

def _pass2_fill_reserve(
    legs: list,
    assignments: dict[str, list[str]],
    crew_by_id: dict,
    ftl_by_id: dict,
    start: date,
    end: date,
) -> list[dict]:
    reserve_slots = []
    assigned_crew_by_date: dict[date, set[str]] = defaultdict(set)

    for leg in legs:
        leg_date = leg.scheduled_departure.date()
        for crew_id in assignments.get(leg.leg_id, []):
            assigned_crew_by_date[leg_date].add(crew_id)

    airports = {c.home_base for c in crew_by_id.values()}

    for current_date in _date_range(start, end):
        for airport in airports:
            on_duty = assigned_crew_by_date.get(current_date, set())
            for crew in crew_by_id.values():
                if crew.home_base != airport or crew.crew_id in on_duty:
                    continue
                ftl = ftl_by_id.get(crew.crew_id, CrewFlightTimeLimitsState(
                    crew_id=crew.crew_id, role=crew.role,
                    home_base=crew.home_base, current_airport=crew.home_base
                ))
                if ftl.status != "AVAILABLE":
                    continue
                reserve_slots.append({
                    "reserve_id":      f"RSV-{crew.crew_id}-{current_date.isoformat()}",
                    "crew_id":         crew.crew_id,
                    "date":            current_date,
                    "standby_start":   datetime.combine(current_date, time(6, 0)),
                    "standby_end":     datetime.combine(current_date, time(22, 0)),
                    "base_airport":    airport,
                    "callable_within": 120,
                    "status":          "SCHEDULED",
                })

    return reserve_slots


# ─── Pass 3 — Full horizon validation ─────────────────────────────────────────

def _pass3_validate(
    legs: list,
    assignments: dict[str, list[str]],
    crew_by_id: dict,
    ftl_by_id: dict,
    licenses_by_crew: dict,
    leave_by_crew: dict,
) -> list[dict]:
    failures = []

    for leg in sorted(legs, key=lambda l: l.scheduled_departure):
        leg_date = leg.scheduled_departure.date()
        for crew_id in assignments.get(leg.leg_id, []):
            crew = crew_by_id.get(crew_id)
            ftl  = ftl_by_id.get(crew_id)
            if not crew or not ftl:
                continue
            passed, reason = check_legality(
                crew, leg, ftl,
                licenses_by_crew.get(crew_id, []),
                leave_by_crew.get(crew_id, []),
                leg_date,
            )
            if not passed:
                failures.append({
                    "crew_id":  crew_id,
                    "leg_id":   leg.leg_id,
                    "reason":   reason,
                    "leg_date": leg_date,
                })

    return failures


# ─── Write roster to DB ───────────────────────────────────────────────────────

def _write_roster(session, assignments: dict, reserve_slots: list, start: date, end: date, triggered_by: str) -> None:
    for leg_id, crew_ids in assignments.items():
        roster_repository.upsert_roster_leg(session, {
            "leg_id":       leg_id,
            "plan_start":   start,
            "plan_end":     end,
            "status":       "DRAFT",
            "triggered_by": triggered_by,
        })
        for crew_id in crew_ids:
            roster_repository.upsert_roster_crew_assignment(session, {
                "leg_id":      leg_id,
                "crew_id":     crew_id,
                "status":      "DRAFT",
                "assigned_by": triggered_by,
            })

    for slot in reserve_slots:
        reserve_repository.insert_reserve_schedule(session, CrewReserveSchedule(**slot))

    session.commit()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _score_candidate(crew, ftl: CrewFlightTimeLimitsState, leg) -> float:
    fatigue = _fatigue_score(ftl)
    score   = 0.0
    score  += 40.0 if ftl.current_airport == leg.origin_icao else 0
    score  += 30.0 * (1 - fatigue / 100)
    score  += 20.0 if ftl.current_airport == crew.home_base else 0
    score  += 10.0 if leg.destination_icao == crew.home_base else 0
    if ftl.current_airport != crew.home_base and leg.destination_icao != crew.home_base:
        score -= 10.0
    return score


def _fatigue_score(ftl: CrewFlightTimeLimitsState) -> float:
    score  = min(ftl.flight_hours_current_duty * 5, 55)
    score += min(ftl.consecutive_duty_days * 10,    20)
    score += min(ftl.flight_hours_28_day / 5,       25)
    return min(score, 100.0)


def _classify_severity(days_until_departure: int) -> str:
    if days_until_departure < 2:  return "CRITICAL"
    if days_until_departure < 7:  return "HIGH"
    if days_until_departure < 14: return "MEDIUM"
    return "LOW"


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
