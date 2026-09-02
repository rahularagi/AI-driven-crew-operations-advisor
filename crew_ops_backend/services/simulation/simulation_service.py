from collections import defaultdict
from datetime import timedelta, timezone
from typing import Optional

from crew_ops.clients.crew_profile_client import get_all_crew_members, get_crew_member
from crew_ops.clients.flight_schedule_client import get_flight_leg
from crew_ops.clients.ftl_client import get_all_crew_duty_states
from crew_ops.clients.license_client import get_all_licenses
from crew_ops.clients.leave_client import get_all_leave_records
from crew_ops.db.database import SessionLocal
from crew_ops.db.repositories import roster_repository
from crew_ops.rules.legality import check_legality
from crew_ops.services.disruption_handler.disruption_handler_service import _score_candidate


class SimulationService:

    def simulate_crew_removal(self, crew_id: str, leg_id: str) -> dict:
        leg  = get_flight_leg(leg_id)
        crew = get_crew_member(crew_id)
        if not leg or not crew:
            return {"error": "leg or crew not found"}
        candidates = self._find_and_rank_candidates_in_memory(crew.role, leg, exclude=[crew_id])
        cascade    = self._check_cascade_impact(crew_id, leg)
        return {
            "removed_crew":   crew.model_dump(),
            "leg":            leg.model_dump(),
            "candidates":     [{"crew_id": c["crew"].crew_id, "score": c["score"]} for c in candidates[:3]],
            "cascade_impact": cascade,
        }

    def simulate_crew_swap(
        self, crew_id_a: str, crew_id_b: str, leg_id_a: str, leg_id_b: str
    ) -> dict:
        leg_a  = get_flight_leg(leg_id_a)
        leg_b  = get_flight_leg(leg_id_b)
        crew_a = get_crew_member(crew_id_a)
        crew_b = get_crew_member(crew_id_b)
        if not leg_a or not leg_b or not crew_a or not crew_b:
            return {"error": "leg or crew not found"}

        ftl_states    = {s.crew_id: s for s in get_all_crew_duty_states()}
        ftl_a         = ftl_states.get(crew_id_a)
        ftl_b         = ftl_states.get(crew_id_b)
        if not ftl_a or not ftl_b:
            return {"error": "FTL state not found for one or both crew members"}

        all_licenses  = get_all_licenses()
        all_leave     = get_all_leave_records()
        lic_by_crew: dict = defaultdict(list)
        for lic in all_licenses:
            lic_by_crew[lic.crew_id].append(lic)
        leave_by_crew: dict = defaultdict(list)
        for lv in all_leave:
            leave_by_crew[lv.crew_id].append(lv)

        passed_a, reason_a = check_legality(
            crew_a, leg_b, ftl_a,
            lic_by_crew[crew_id_a], leave_by_crew[crew_id_a],
            leg_b.scheduled_departure.date(),
        )
        passed_b, reason_b = check_legality(
            crew_b, leg_a, ftl_b,
            lic_by_crew[crew_id_b], leave_by_crew[crew_id_b],
            leg_a.scheduled_departure.date(),
        )
        return {
            "crew_a_on_leg_b": {"passed": passed_a, "reason": reason_a},
            "crew_b_on_leg_a": {"passed": passed_b, "reason": reason_b},
            "swap_legal":      passed_a and passed_b,
        }

    def simulate_leg_cancellation(self, leg_id: str) -> dict:
        leg = get_flight_leg(leg_id)
        if not leg:
            return {"error": "leg not found"}

        scan_end     = leg.scheduled_departure.date() + timedelta(weeks=4)
        dep = leg.scheduled_departure
        arr = leg.scheduled_arrival
        # Normalise both to UTC-aware before subtracting to avoid TypeError
        if dep.tzinfo is None:
            dep = dep.replace(tzinfo=timezone.utc)
        if arr.tzinfo is None:
            arr = arr.replace(tzinfo=timezone.utc)
        leg_hours    = (arr - dep).total_seconds() / 3600
        next_assignments: dict = {}
        ftl_impact: dict       = {}

        with SessionLocal() as session:
            for crew_id in leg.assigned_crew:
                future = roster_repository.get_future_assignments(
                    session,
                    from_date=leg.scheduled_departure.date(),
                    to_date=scan_end,
                    crew_id=crew_id,
                )
                # exclude the leg being cancelled itself
                future = [a for a in future if a["leg_id"] != leg_id]
                next_assignments[crew_id] = future[0] if future else None
                ftl_impact[crew_id]       = round(leg_hours, 2)

        return {
            "cancelled_leg":    leg.model_dump(),
            "released_crew":    leg.assigned_crew,
            "next_assignments": next_assignments,
            "ftl_hours_freed":  ftl_impact,
        }

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _find_and_rank_candidates_in_memory(
        self, role: str, leg, exclude: Optional[list] = None
    ) -> list[dict]:
        exclude = exclude or []
        all_crew      = get_all_crew_members()
        ftl_states    = {s.crew_id: s for s in get_all_crew_duty_states()}
        all_licenses  = get_all_licenses()
        all_leave     = get_all_leave_records()
        lic_by_crew: dict = defaultdict(list)
        for lic in all_licenses:
            lic_by_crew[lic.crew_id].append(lic)
        leave_by_crew: dict = defaultdict(list)
        for lv in all_leave:
            leave_by_crew[lv.crew_id].append(lv)

        leg_date = leg.scheduled_departure.date()
        results  = []
        for crew in all_crew:
            if crew.crew_id in exclude or crew.role != role or crew.employment_status != "ACTIVE":
                continue
            ftl = ftl_states.get(crew.crew_id)
            if not ftl:
                continue
            passed, _ = check_legality(
                crew, leg, ftl,
                lic_by_crew.get(crew.crew_id, []),
                leave_by_crew.get(crew.crew_id, []),
                leg_date,
            )
            if passed:
                results.append({"crew": crew, "ftl": ftl, "score": _score_candidate(crew, ftl, leg)})
        return sorted(results, key=lambda x: x["score"], reverse=True)

    def _check_cascade_impact(self, crew_id: str, leg) -> list[dict]:
        scan_end = leg.scheduled_departure.date() + timedelta(weeks=4)
        with SessionLocal() as session:
            assignments = roster_repository.get_future_assignments(
                session,
                from_date=leg.scheduled_departure.date(),
                to_date=scan_end,
                crew_id=crew_id,
            )
        # exclude the current leg itself
        return [a for a in assignments if a["leg_id"] != leg.leg_id]
