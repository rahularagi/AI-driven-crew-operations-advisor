"""
Service 3 — Disruption Handler

Subscribes to : FlightDisruptedEvent, CrewDisruptedEvent
Publishes      : RosterModifiedEvent

Never imports or calls any other service directly.
Registered at startup:
    event_bus.subscribe(FlightDisruptedEvent, disruption_handler.handle_flight_disrupted)
    event_bus.subscribe(CrewDisruptedEvent, disruption_handler.handle_crew_disrupted)
"""

from datetime import datetime, timezone
from sqlalchemy import text
from crew_ops_backend.clients.crew_profile_client import get_all_crew_members, get_crew_member
from crew_ops_backend.clients.ftl_client import get_all_crew_duty_states, get_crew_duty_state
from crew_ops_backend.clients.flight_schedule_client import get_flight_leg
from crew_ops_backend.clients.license_client import get_licenses_for_crew_member
from crew_ops_backend.clients.leave_client import get_leave_records_for_crew
from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.db.repositories import roster_repository, disruption_repository
from crew_ops_backend.models.events import FlightDisruptedEvent, CrewDisruptedEvent, RosterModifiedEvent
from crew_ops_backend.rules.legality import check_legality
from crew_ops_backend.services.event_bus import event_bus


class DisruptionHandler:

    def handle_flight_disrupted(self, event: FlightDisruptedEvent) -> None:
        leg = get_flight_leg(event.leg_id)

        # Leg not found — already cancelled or removed from schedule, nothing to do
        if not leg:
            return

        # Leg already departed — too late to act
        now = datetime.now(timezone.utc)
        dep = leg.scheduled_departure
        if dep.tzinfo is None:
            dep = dep.replace(tzinfo=timezone.utc)
        if dep <= now:
            return

        if event.disruption_type == "CANCELLATION":
            # Invalidate roster leg and all crew assignments in one transaction
            with SessionLocal() as session:
                roster_repository.invalidate_roster_leg(session, event.leg_id, "FLIGHT_CANCELLED")
                session.commit()
            # Publish RosterModifiedEvent per released crew so FTL Service updates their state
            for crew_id in event.assigned_crew:
                event_bus.publish(RosterModifiedEvent(
                    leg_id          = event.leg_id,
                    removed_crew_id = crew_id,
                    added_crew_id   = None,
                    modified_at     = datetime.now(timezone.utc),
                ))
            return

        if event.disruption_type == "ROUTE_CHANGE":
            # Too complex to auto-handle — create manual review proposal
            self._create_proposal(
                leg_id            = event.leg_id,
                disruption_type   = "FLIGHT_DISRUPTED",
                disruption_reason = "ROUTE_CHANGE",
                removed_crew_id   = None,
                candidates        = [],
                severity          = event.severity,
                source            = event.event,
            )
            return

        if event.disruption_type in ("DELAY", "SCHEDULE_CHANGE"):
            # Re-check legality for all assigned crew against updated departure time
            # Any delay can breach FTL — no minimum threshold
            for crew_id in event.assigned_crew:
                self._check_and_propose(crew_id, leg, reason="DELAY_FTL_BREACH", source=event.event)

        if event.disruption_type == "AIRCRAFT_SWAP":
            # Cabin crew have no type ratings — only re-check pilots
            for crew_id in event.assigned_crew:
                crew = get_crew_member(crew_id)
                if crew and crew.role == "PILOT":
                    self._check_and_propose(crew_id, leg, reason="AIRCRAFT_TYPE_CHANGED", source=event.event)

    def handle_crew_disrupted(self, event: CrewDisruptedEvent) -> None:
        # Leave-period unavailability — no specific leg, find all affected assignments
        if not event.leg_id and event.start_date and event.end_date:
            from datetime import date
            start = date.fromisoformat(event.start_date)
            end   = date.fromisoformat(event.end_date)
            with SessionLocal() as session:
                assignments = roster_repository.get_future_assignments(
                    session, from_date=start, to_date=end, crew_id=event.crew_id
                )
            for assignment in assignments:
                leg_id = assignment.get("leg_id") if isinstance(assignment, dict) else getattr(assignment, "leg_id", None)
                if not leg_id:
                    continue
                leg = get_flight_leg(leg_id)
                if not leg:
                    continue
                now = datetime.now(timezone.utc)
                dep = leg.scheduled_departure
                if dep.tzinfo is None:
                    dep = dep.replace(tzinfo=timezone.utc)
                if dep <= now or leg.status == "CANCELLED":
                    continue
                crew = get_crew_member(event.crew_id)
                role = crew.role if crew else None
                if not role:
                    with SessionLocal() as session:
                        a = roster_repository.get_assignment_for_crew(session, leg_id, event.crew_id)
                    role = (a.get("role") if isinstance(a, dict) else None) if a else None
                if not role:
                    continue
                candidates = self._find_and_rank_candidates(role, leg)
                self._create_proposal(
                    leg_id            = leg_id,
                    disruption_type   = "CREW_DISRUPTED",
                    disruption_reason = event.reason,
                    removed_crew_id   = event.crew_id,
                    candidates        = candidates,
                    severity          = event.severity,
                    source            = event.source,
                )
            return

        # Single-leg disruption (legacy path)
        leg = get_flight_leg(event.leg_id)

        # Leg not found — removed from schedule entirely, skip
        if not leg:
            return

        # Leg already departed or landed — too late to act
        now = datetime.now(timezone.utc)
        dep = leg.scheduled_departure
        if dep.tzinfo is None:
            dep = dep.replace(tzinfo=timezone.utc)
        if dep <= now:
            return

        # Leg cancelled — no point finding a replacement
        if leg.status == "CANCELLED":
            return

        # crew is None — crew record missing but leg still needs coverage
        # do not skip — check the roster assignment status and find a replacement
        crew = get_crew_member(event.crew_id)
        role = crew.role if crew else None

        if role is None:
            # crew record gone — look up role from the existing roster assignment
            with SessionLocal() as session:
                assignment = roster_repository.get_assignment_for_crew(
                    session, event.leg_id, event.crew_id
                )
            if not assignment:
                return  # no assignment record either — nothing to replace
            role = assignment.get("role")
            if not role:
                return

        candidates = self._find_and_rank_candidates(role, leg)
        self._create_proposal(
            leg_id            = event.leg_id,
            disruption_type   = "CREW_DISRUPTED",
            disruption_reason = event.reason,
            removed_crew_id   = event.crew_id,
            candidates        = candidates,
            severity          = event.severity,
            source            = event.source,
        )

    def reject_and_repropose(self, proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
        with SessionLocal() as session:
            result = disruption_repository.reject_proposal(session, proposal_id, decided_by, rejection_reason)
            if not result:
                return {"error": "proposal not found"}
            leg_id           = result["leg_id"]
            removed_crew_id  = result["removed_crew_id"]
            already_proposed = disruption_repository.get_already_proposed_crew(session, leg_id, removed_crew_id)
            session.commit()

        leg = get_flight_leg(leg_id)
        if not leg:
            return {"status": "rejected", "new_proposal_id": None, "reason": "leg no longer exists"}

        removed_crew = get_crew_member(removed_crew_id)
        role = removed_crew.role if removed_crew else None
        if not role:
            with SessionLocal() as session:
                assignment = roster_repository.get_assignment_for_crew(session, leg_id, removed_crew_id)
            role = assignment.get("role") if assignment else None
        if not role:
            return {"status": "rejected", "new_proposal_id": None, "reason": "cannot determine role"}

        candidates = self._find_and_rank_candidates(role, leg)
        candidates = [c for c in candidates if c["crew"].crew_id not in already_proposed]

        self._create_proposal(
            leg_id            = leg_id,
            disruption_type   = "CREW_DISRUPTED",
            disruption_reason = rejection_reason,
            removed_crew_id   = removed_crew_id,
            candidates        = candidates,
            severity          = "HIGH",
            source            = "CONTROLLER_REJECT",
        )
        next_candidate = candidates[0]["crew"].crew_id if candidates else None
        return {"status": "rejected", "leg_id": leg_id, "next_candidate": next_candidate}

    def auto_resolve_low_severity(self) -> list[str]:
        """Scheduled every 30 min. Auto-accepts LOW proposals if candidate is still legal."""
        from crew_ops_backend.clients.license_client import get_licenses_for_crew_member
        from crew_ops_backend.clients.leave_client import get_leave_records_for_crew
        resolved = []
        with SessionLocal() as session:
            rows = session.execute(
                text(
                    "SELECT proposal_id, leg_id, removed_crew_id, proposed_crew_id "
                    "FROM disruption_proposals WHERE status='PENDING' AND severity='LOW'"
                )
            ).mappings().all()
            proposals = [dict(r) for r in rows]

        for p in proposals:
            if not p["proposed_crew_id"]:
                continue
            leg  = get_flight_leg(p["leg_id"])
            crew = get_crew_member(p["proposed_crew_id"])
            ftl  = get_crew_duty_state(p["proposed_crew_id"])
            if not leg or not crew or not ftl:
                continue
            licenses = get_licenses_for_crew_member(p["proposed_crew_id"])
            leave    = get_leave_records_for_crew(p["proposed_crew_id"])
            passed, _ = check_legality(crew, leg, ftl, licenses, leave, leg.scheduled_departure.date())
            if passed:
                with SessionLocal() as session:
                    result = disruption_repository.accept_proposal(session, p["proposal_id"], "AUTO_RESOLVE")
                    if result and result.get("proposed_crew_id"):
                        roster_repository.replace_roster_crew_assignment(
                            session, p["leg_id"], p["removed_crew_id"], p["proposed_crew_id"], "AUTO_RESOLVE"
                        )
                    session.commit()
                event_bus.publish(RosterModifiedEvent(
                    leg_id          = p["leg_id"],
                    removed_crew_id = p["removed_crew_id"],
                    added_crew_id   = p["proposed_crew_id"],
                    modified_at     = datetime.now(timezone.utc),
                ))
                resolved.append(p["proposal_id"])
            else:
                # Re-rank; if no candidate escalate to MEDIUM
                removed_crew = get_crew_member(p["removed_crew_id"])
                role = removed_crew.role if removed_crew else None
                if role:
                    new_candidates = self._find_and_rank_candidates(role, leg)
                    if new_candidates:
                        with SessionLocal() as session:
                            session.execute(
                                text(
                                    "UPDATE disruption_proposals SET proposed_crew_id=:cid, proposal_score=:sc "
                                    "WHERE proposal_id=:pid"
                                ),
                                {"cid": new_candidates[0]["crew"].crew_id,
                                 "sc":  new_candidates[0]["score"],
                                 "pid": p["proposal_id"]},
                            )
                            session.commit()
                    else:
                        with SessionLocal() as session:
                            session.execute(
                                text(
                                    "UPDATE disruption_proposals SET severity='MEDIUM' WHERE proposal_id=:pid"
                                ),
                                {"pid": p["proposal_id"]},
                            )
                            session.commit()
        return resolved

    def get_proposals_for_push(self) -> list[dict]:
        """Returns PENDING proposals not yet pushed (pushed_at IS NULL)."""
        with SessionLocal() as session:
            return disruption_repository.get_unpushed_proposals(session)

    def expire_stale_proposals(self) -> None:
        with SessionLocal() as session:
            disruption_repository.expire_stale_proposals(session)
            session.commit()

    # ─── Internal pipeline ────────────────────────────────────────────────────

    def _check_and_propose(self, crew_id: str, leg, reason: str, source: str) -> None:
        crew     = get_crew_member(crew_id)
        ftl      = get_crew_duty_state(crew_id)
        licenses = get_licenses_for_crew_member(crew_id)
        leave    = get_leave_records_for_crew(crew_id)
        if not crew or not ftl:
            return
        dep = leg.scheduled_departure
        if dep.tzinfo is None:
            dep = dep.replace(tzinfo=timezone.utc)
        passed, fail_reason = check_legality(crew, leg, ftl, licenses, leave, dep.date())
        if not passed:
            # Skip if a proposal already exists for this crew+leg (any non-expired status)
            with SessionLocal() as session:
                if disruption_repository.pending_proposal_exists(session, leg.leg_id, crew_id):
                    return
            candidates = self._find_and_rank_candidates(crew.role, leg)
            self._create_proposal(
                leg_id            = leg.leg_id,
                disruption_type   = "FLIGHT_DISRUPTED",
                disruption_reason = fail_reason or reason,
                removed_crew_id   = crew_id,
                candidates        = candidates,
                severity          = "HIGH",
                source            = source,
            )

    def _find_and_rank_candidates(self, role: str, leg) -> list[dict]:
        from collections import defaultdict
        from crew_ops_backend.clients.license_client import get_all_licenses
        from crew_ops_backend.clients.leave_client import get_all_leave_records

        all_crew   = get_all_crew_members()
        ftl_states = {s.crew_id: s for s in get_all_crew_duty_states()}

        all_licenses = get_all_licenses()
        all_leave    = get_all_leave_records()
        licenses_by_crew: dict = defaultdict(list)
        for lic in all_licenses:
            licenses_by_crew[lic.crew_id].append(lic)
        leave_by_crew: dict = defaultdict(list)
        for leave in all_leave:
            leave_by_crew[leave.crew_id].append(leave)

        dep = leg.scheduled_departure
        if dep.tzinfo is None:
            dep = dep.replace(tzinfo=timezone.utc)
        leg_date = dep.date()

        candidates = []
        for crew in all_crew:
            if crew.role != role or crew.employment_status != "ACTIVE":
                continue
            ftl = ftl_states.get(crew.crew_id)
            if not ftl:
                continue
            passed, _ = check_legality(
                crew, leg, ftl,
                licenses_by_crew.get(crew.crew_id, []),
                leave_by_crew.get(crew.crew_id, []),
                leg_date,
            )
            if passed:
                score = _score_candidate(crew, ftl, leg)
                candidates.append({"crew": crew, "ftl": ftl, "score": score})

        return sorted(candidates, key=lambda x: x["score"], reverse=True)

    def _create_proposal(
        self,
        leg_id: str,
        disruption_type: str,
        disruption_reason: str,
        removed_crew_id: str | None,
        candidates: list[dict],
        severity: str,
        source: str,
    ) -> None:
        with SessionLocal() as session:
            # Guard — do not create duplicate PENDING proposal for same leg + removed crew
            if removed_crew_id and disruption_repository.pending_proposal_exists(session, leg_id, removed_crew_id):
                return

            # Invalidate the disrupted crew's assignment so they no longer appear assigned
            if removed_crew_id:
                roster_repository.invalidate_assignment(session, leg_id, removed_crew_id, disruption_reason)

            proposed_crew_id = candidates[0]["crew"].crew_id if candidates else None
            proposal_score   = candidates[0]["score"] if candidates else 0.0
            proposal_id      = f"PROP-{leg_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

            disruption_repository.insert_proposal(session, {
                "proposal_id":       proposal_id,
                "leg_id":            leg_id,
                "disruption_type":   disruption_type,
                "disruption_reason": disruption_reason,
                "removed_crew_id":   removed_crew_id,
                "proposed_crew_id":  proposed_crew_id,
                "proposal_score":    proposal_score,
                "status":            "PENDING",
                "severity":          severity,
                "source":            source,
            })
            session.commit()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _score_candidate(crew, ftl, leg) -> float:
    fatigue = _fatigue_score(ftl)
    score   = 0.0
    score  += 40.0 if ftl.current_airport == leg.origin_icao else 0
    score  += 30.0 * (1 - fatigue / 100)
    score  += 20.0 if ftl.current_airport == crew.home_base else 0
    score  += 10.0 if leg.destination_icao == crew.home_base else 0
    if ftl.current_airport != crew.home_base and leg.destination_icao != crew.home_base:
        score -= 10.0
    return score


def _fatigue_score(ftl) -> float:
    score  = min(ftl.flight_hours_current_duty * 5, 55)
    score += min(ftl.consecutive_duty_days * 10,    20)
    score += min(ftl.flight_hours_28_day / 5,       25)
    return min(score, 100.0)
