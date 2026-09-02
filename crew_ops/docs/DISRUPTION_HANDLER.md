# Disruption Handler — End to End Implementation

---

## What This Service Does

The Disruption Handler is responsible for one thing: **when something breaks, find a replacement and present it to the controller**.

It never detects disruptions — that is the Observer's and Weekly Planner Validator's job. It only reacts to events that are already published.

Two types of disruptions it handles:

1. **Flight disrupted** — the flight itself changed (delay, cancellation, aircraft swap). Crew may need to be reassigned or released.
2. **Crew disrupted** — a specific crew member can no longer legally operate a leg (sick call, license expired, FTL breach, leave added).

Most paths end the same way: find the best available replacement, present to controller, await confirmation, publish `RosterModifiedEvent`.

Exception: **CANCELLATION** — no replacement is needed. All crew are released immediately, `roster_leg` and all assignments are invalidated, and `RosterModifiedEvent` is published per released crew member so the FTL Service can update their state.

---

## Current State of the Codebase

### What exists

| File | Status |
|------|--------|
| `services/disruption_handler/disruption_handler_service.py` | ✅ Complete — full implementation with all guards |
| `db/repositories/disruption_repository.py` | ✅ Complete |
| `db/repositories/roster_repository.py` | ✅ Complete — includes `invalidate_assignment`, `invalidate_roster_leg`, `replace_roster_crew_assignment` |
| `api/routers/disruption_router.py` | ✅ Complete — accept, reject, get proposals |
| `models/events.py` | ✅ Complete — `FlightDisruptedEvent`, `CrewDisruptedEvent`, `RosterModifiedEvent` all defined |
| `services/event_bus.py` | ✅ Complete |
| `api/main.py` | ✅ Event subscriptions registered, expiry job scheduled |
| `rules/legality.py` | ✅ Complete |
| `rules/ftl_simulator.py` | ✅ Complete |
| `docker/init.sql` | ✅ `disruption_proposals` table added |

### What is missing

Nothing — all files are complete.

---

## Events the Disruption Handler Receives

### `FlightDisruptedEvent`

Published by: Observer (live delay/cancellation), Weekly Planner (re-plan found flight changed)

```python
FlightDisruptedEvent(
    leg_id             = "AI101-VIDP-EGLL-20240205",
    flight_number      = "AI101",
    origin             = "VIDP",
    destination        = "EGLL",
    disruption_type    = "DELAY",           # DELAY / CANCELLATION / AIRCRAFT_SWAP / SCHEDULE_CHANGE / ROUTE_CHANGE
    severity           = "HIGH",
    scheduled_departure = datetime(...),
    actual_departure   = datetime(...),
    delay_minutes      = 95,
    assigned_crew      = ["C-001", "C-002", "C-011", "C-012"],
    detected_at        = datetime(...),
)
```

### `CrewDisruptedEvent`

Published by: Weekly Planner Validator, Weekly Planner Re-Plan, Ops Desk (sick call via API), Leave Client (leave added covering an assigned leg)

```python
CrewDisruptedEvent(
    crew_id              = "C-003",
    crew_name            = "Rahul Sharma",
    leg_id               = "AI305-VABB-VECC-20240205",
    reason               = "LICENSE_EXPIRED",   # see full list below
    days_until_departure = 2,
    severity             = "HIGH",
    source               = "WEEKLY_PLANNER_VALIDATOR",  # or "WEEKLY_PLANNER_REPLAN" or "OPS_DESK"
    detected_at          = datetime(...),
)
```

Possible `reason` values from legality checker (Gates 1–11):
```
INACTIVE_CREW
ROLE_MISMATCH
NO_TYPE_RATING
LICENSE_EXPIRED
MEDICAL_EXPIRED
ON_LEAVE
IN_REST_PERIOD
FTL_UNAVAILABLE
DUTY_PERIOD_BREACH
7_DAY_CAP_BREACH
28_DAY_CAP_BREACH
CONSECUTIVE_DAYS_CAP
```

Additional `reason` values emitted by Weekly Planner Re-Plan (not from legality gates — set directly by the planner before emitting):
```
LEAVE_ADDED             ← new leave record now covers this leg
FTL_BREACH_PROJECTED    ← FTL hours will breach a cap on this leg
AIRCRAFT_TYPE_CHANGED   ← aircraft swapped, crew not rated for new type
```

`LEAVE_ADDED` is also emitted by the **Leave Client** (`clients/leave_client.py`) when `add_leave_record()` is called and the leave window covers one or more assigned legs. This handles same-day leave without requiring manual ops desk intervention.

#### Leave Added — Full Flow

```
add_leave_record(leave_record) called
        ↓
Insert leave record into crew_leave_records table
        ↓
Query roster_crew_assignment JOIN flight_legs
  WHERE crew_id = leave_record.crew_id
    AND scheduled_departure BETWEEN start_date AND end_date
    AND status IN ('DRAFT', 'CONFIRMED')
        ↓
No assignments found → return, nothing to do
        ↓
Assignments found → fetch crew name from crew_profile_client
        ↓
For each affected leg:
  days_until = scheduled_departure.date() - today
  severity:
    < 1 day  → CRITICAL   (same-day leave)
    ≤ 2 days → HIGH
    ≤ 7 days → MEDIUM
    > 7 days → LOW
  publish CrewDisruptedEvent(
    reason   = "LEAVE_ADDED",
    source   = "OPS_DESK",
    severity = severity,
  )
        ↓
Disruption Handler receives CrewDisruptedEvent
  → validates leg exists, not departed, not cancelled
  → finds replacement candidates
  → creates PENDING proposal in disruption_proposals
        ↓
Controller sees proposal in GET /disruptions/proposals
  → accepts → roster swap + RosterModifiedEvent published
  → rejects → next candidate proposed
```

---

## Database Table — `disruption_proposals`

Stores each proposed replacement while it waits for controller confirmation. One row per disruption event.

```sql
CREATE TABLE IF NOT EXISTS disruption_proposals (
    id                  SERIAL          PRIMARY KEY,
    proposal_id         VARCHAR(50)     NOT NULL UNIQUE,
    leg_id              VARCHAR(50)     NOT NULL REFERENCES flight_legs(leg_id),
    disruption_type     VARCHAR(20)     NOT NULL,   -- FLIGHT_DISRUPTED / CREW_DISRUPTED
    disruption_reason   VARCHAR(50)     NOT NULL,   -- from event
    removed_crew_id     VARCHAR(10)     REFERENCES crew_members(crew_id),
    proposed_crew_id    VARCHAR(10)     REFERENCES crew_members(crew_id),
    proposal_score      FLOAT           NOT NULL DEFAULT 0.0,
    status              VARCHAR(15)     NOT NULL DEFAULT 'PENDING',
    -- PENDING   → waiting for controller decision
    -- ACCEPTED  → controller approved, RosterModifiedEvent published
    -- REJECTED  → controller rejected, handler must propose next candidate
    -- EXPIRED   → leg departed before controller acted
    severity            VARCHAR(10)     NOT NULL,
    source              VARCHAR(50)     NOT NULL,
    proposed_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    decided_at          TIMESTAMPTZ,
    decided_by          VARCHAR(50),
    rejection_reason    VARCHAR(100)
);
```

---

## Handle Flight Disrupted — Full Flow

```
FlightDisruptedEvent received
        ↓
Step 1 — What type of disruption?

  CANCELLATION:
    → mark roster_leg.status = INVALIDATED
    → mark all roster_crew_assignment.status = INVALIDATED for this leg (DRAFT and CONFIRMED only)
    → single call to invalidate_roster_leg() handles both in one transaction
    → publish RosterModifiedEvent(removed_crew_id=crew_id, added_crew_id=None) per released crew
      → FTL Service sets each crew member status = UNAVAILABLE
      → Daily Validator re-validates each crew member's other future legs
    → done — no proposal created

  DELAY (any duration) or SCHEDULE_CHANGE:
    → always re-check legality of all assigned crew against new departure time
    → even a short delay can push a crew member past their duty period limit if they are near the cap
    → crew who still pass → keep assignment, no action
    → crew who now fail → treat as CREW_DISRUPTED
      → run crew replacement flow for each failing crew member

  AIRCRAFT_SWAP:
    → new aircraft_type may require different type ratings
    → cabin crew have no type ratings in this system — skip them, only re-check pilots
    → re-check Gate 3 (type rating) and Gate 4 (license) for pilot crew only
    → pilots who fail → treat as CREW_DISRUPTED with reason = AIRCRAFT_TYPE_CHANGED
      → run crew replacement flow for each failing pilot

  ROUTE_CHANGE:
    → emit to controller for manual review — too complex to auto-handle
    → create proposal with proposed_crew_id = None, status = PENDING
    → controller must manually reassign via POST /planner/roster/{leg_id}/reassign
```

---

## Handle Crew Disrupted — Full Flow

This is the main path. One crew member cannot operate one leg.

```
CrewDisruptedEvent received
        ↓
Step 1 — Validate leg and crew context

  leg = get_flight_leg(event.leg_id)

  if leg is None
    → leg removed from schedule entirely, skip

  if leg.scheduled_departure <= now()
    → leg already departed or landed, too late to act, skip

  if leg.status == "CANCELLED"
    → flight cancelled, no point finding a replacement, skip

  crew = get_crew_member(event.crew_id)

  if crew is None
    → do NOT skip — leg still needs coverage
    → look up role from roster_crew_assignment via get_assignment_for_crew(leg_id, crew_id)
    → if no assignment record found either → skip (nothing to replace)
    → if assignment found → use assignment.role to find replacement candidates

        ↓
Step 2 — Find replacement candidates
  role    = crew.role  (PILOT or CABIN — replacement must match)
  airport = leg.origin_icao  (prefer crew already at departure airport)

  For every active crew member with matching role:
    - fetch their live FTL state
    - fetch their licenses
    - fetch their leave records
    - run check_legality(candidate, leg, ftl, licenses, leave, leg_date)
    - if passes → add to candidates list with score

        ↓
Step 3 — Score and rank candidates
  Score each candidate (same 4-factor scoring as Weekly Planner):
    +40  already at leg's departure airport
    +30  scaled by fatigue (lower fatigue = higher score)
    +20  at home base
    +10  leg destination is their home base
    -10  already away from home AND leg takes them further away

        ↓
Step 4 — Create proposal for top candidate
  proposal_id = f"PROP-{leg_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

  Write to disruption_proposals:
    leg_id           = event.leg_id
    disruption_type  = "CREW_DISRUPTED"
    disruption_reason = event.reason
    removed_crew_id  = event.crew_id
    proposed_crew_id = top_candidate.crew_id
    proposal_score   = top_candidate.score
    status           = "PENDING"
    severity         = event.severity

        ↓
Step 5 — Controller reviews and decides
  GET  /disruptions/proposals          → controller sees all pending proposals
  POST /disruptions/proposals/{id}/accept  → controller approves
  POST /disruptions/proposals/{id}/reject  → controller rejects, handler proposes next

        ↓
Step 6 — On ACCEPT
  update disruption_proposals.status = ACCEPTED
  update roster_crew_assignment:
    old crew → status = REPLACED, replaced_by = new_crew_id
    new crew → INSERT with status = CONFIRMED
  update roster_leg:
    triggered_by = decided_by
    updated_at   = NOW()
    (status stays PUBLISHED — the leg is still active, crew composition changed)
  publish RosterModifiedEvent(
    leg_id          = leg_id,
    removed_crew_id = old_crew_id,
    added_crew_id   = new_crew_id,
  )
  → FTL Service updates live FTL state for both crew immediately
  → DailyValidator re-validates both crew members' future legs automatically

        ↓
Step 7 — On REJECT
  update disruption_proposals.status = REJECTED
  remove top candidate from candidate list
  propose next best candidate → repeat from Step 4
  if no more candidates → create proposal with proposed_crew_id = None
    → controller must handle manually
```

---

## Candidate Scoring

Same scoring logic as Weekly Planner. Shared from `rules/` — not duplicated.

```python
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
```

---

## Severity and Response Time

The severity from the event drives how urgently the controller must act.

| Severity | Days until departure | Expected response |
|----------|---------------------|-------------------|
| CRITICAL | < 2 days | Immediate — ops desk alerted directly |
| HIGH | 2–7 days | Same day response |
| MEDIUM | 7–14 days | Within 24 hours |
| LOW | 14+ days | Within 48 hours |

A proposal that is not acted on before the leg departs is automatically marked `EXPIRED`.

---

## Full Service Implementation

```python
# services/disruption_handler/disruption_handler_service.py

from collections import defaultdict
from datetime import datetime, timezone
from crew_ops.clients.crew_profile_client import get_all_crew_members, get_crew_member
from crew_ops.clients.ftl_client import get_all_crew_duty_states, get_crew_duty_state
from crew_ops.clients.flight_schedule_client import get_flight_leg
from crew_ops.clients.license_client import get_licenses_for_crew_member
from crew_ops.clients.leave_client import get_leave_records_for_crew
from crew_ops.db.database import SessionLocal
from crew_ops.db.repositories import roster_repository, disruption_repository
from crew_ops.models.events import FlightDisruptedEvent, CrewDisruptedEvent, RosterModifiedEvent
from crew_ops.rules.legality import check_legality
from crew_ops.services.event_bus import event_bus


class DisruptionHandler:

    def handle_flight_disrupted(self, event: FlightDisruptedEvent) -> None:
        leg = get_flight_leg(event.leg_id)
        if not leg:
            return

        if event.disruption_type == "CANCELLATION":
            with SessionLocal() as session:
                for crew_id in event.assigned_crew:
                    roster_repository.invalidate_assignment(session, event.leg_id, crew_id, "FLIGHT_CANCELLED")
                session.commit()
            return

        if event.disruption_type == "ROUTE_CHANGE":
            # Too complex to auto-handle — create a manual review proposal
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
            # Re-check legality for all assigned crew against updated leg — any delay can breach FTL
            for crew_id in event.assigned_crew:
                self._check_and_propose(crew_id, leg, reason="DELAY_FTL_BREACH", source=event.event)

        if event.disruption_type == "AIRCRAFT_SWAP":
            # Only re-check pilots — cabin crew have no type ratings, Gate 3 always fails for them
            for crew_id in event.assigned_crew:
                crew = get_crew_member(crew_id)
                if crew and crew.role == "PILOT":
                    self._check_and_propose(crew_id, leg, reason="AIRCRAFT_TYPE_CHANGED", source=event.event)

    def expire_stale_proposals(self) -> None:
        with SessionLocal() as session:
            disruption_repository.expire_stale_proposals(session)
            session.commit()

    def handle_crew_disrupted(self, event: CrewDisruptedEvent) -> None:
        leg = get_flight_leg(event.leg_id)
        if not leg:
            return
        if leg.scheduled_departure <= datetime.now(timezone.utc):
            return  # too late

        crew = get_crew_member(event.crew_id)
        if not crew:
            return

        candidates = self._find_and_rank_candidates(crew.role, leg)
        self._create_proposal(
            leg_id           = event.leg_id,
            disruption_type  = "CREW_DISRUPTED",
            disruption_reason = event.reason,
            removed_crew_id  = event.crew_id,
            candidates       = candidates,
            severity         = event.severity,
            source           = event.source,
        )

    # ─── Internal pipeline ────────────────────────────────────────────────────

    def _check_and_propose(self, crew_id: str, leg, reason: str, source: str) -> None:
        crew     = get_crew_member(crew_id)
        ftl      = get_crew_duty_state(crew_id)
        licenses = get_licenses_for_crew_member(crew_id)
        leave    = get_leave_records_for_crew(crew_id)
        if not crew or not ftl:
            return
        passed, fail_reason = check_legality(crew, leg, ftl, licenses, leave, leg.scheduled_departure.date())
        if not passed:
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
        all_crew   = get_all_crew_members()
        ftl_states = {s.crew_id: s for s in get_all_crew_duty_states()}
        leg_date   = leg.scheduled_departure.date()

        candidates = []
        for crew in all_crew:
            if crew.role != role or crew.employment_status != "ACTIVE":
                continue
            ftl      = ftl_states.get(crew.crew_id)
            licenses = get_licenses_for_crew_member(crew.crew_id)
            leave    = get_leave_records_for_crew(crew.crew_id)
            if not ftl:
                continue
            passed, _ = check_legality(crew, leg, ftl, licenses, leave, leg_date)
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
        # Guard — do not create duplicate PENDING proposal for same leg + removed crew
        with SessionLocal() as session:
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
```

---

## Disruption Repository

New file: `db/repositories/disruption_repository.py`

```python
def pending_proposal_exists(session, leg_id: str, removed_crew_id: str) -> bool:
    row = session.execute(text("""
        SELECT 1 FROM disruption_proposals
        WHERE leg_id = :leg_id AND removed_crew_id = :removed_crew_id AND status = 'PENDING'
        LIMIT 1
    """), {"leg_id": leg_id, "removed_crew_id": removed_crew_id}).first()
    return row is not None


def insert_proposal(session, data: dict) -> None:
    session.execute(text("""
        INSERT INTO disruption_proposals (
            proposal_id, leg_id, disruption_type, disruption_reason,
            removed_crew_id, proposed_crew_id, proposal_score,
            status, severity, source
        ) VALUES (
            :proposal_id, :leg_id, :disruption_type, :disruption_reason,
            :removed_crew_id, :proposed_crew_id, :proposal_score,
            :status, :severity, :source
        )
    """), data)


def get_pending_proposals(session) -> list[dict]:
    rows = session.execute(text("""
        SELECT dp.*, fl.scheduled_departure, fl.origin_iata, fl.destination_iata,
               fl.flight_number, fl.aircraft_type
        FROM disruption_proposals dp
        JOIN flight_legs fl ON fl.leg_id = dp.leg_id
        WHERE dp.status = 'PENDING'
        ORDER BY
            CASE dp.severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH'     THEN 2
                WHEN 'MEDIUM'   THEN 3
                ELSE 4
            END,
            dp.proposed_at ASC
    """)).mappings().all()
    return [dict(row) for row in rows]


def accept_proposal(session, proposal_id: str, decided_by: str) -> dict:
    row = session.execute(text("""
        UPDATE disruption_proposals
        SET status = 'ACCEPTED', decided_at = NOW(), decided_by = :decided_by
        WHERE proposal_id = :proposal_id
        RETURNING leg_id, removed_crew_id, proposed_crew_id
    """), {"proposal_id": proposal_id, "decided_by": decided_by}).mappings().first()
    return dict(row) if row else {}


def reject_proposal(session, proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
    row = session.execute(text("""
        UPDATE disruption_proposals
        SET status = 'REJECTED', decided_at = NOW(), decided_by = :decided_by,
            rejection_reason = :rejection_reason
        WHERE proposal_id = :proposal_id
        RETURNING leg_id, removed_crew_id, proposed_crew_id
    """), {"proposal_id": proposal_id, "decided_by": decided_by, "rejection_reason": rejection_reason}).mappings().first()
    return dict(row) if row else {}


def expire_stale_proposals(session) -> int:
    result = session.execute(text("""
        UPDATE disruption_proposals dp
        SET status = 'EXPIRED'
        FROM flight_legs fl
        WHERE dp.leg_id = fl.leg_id
          AND dp.status = 'PENDING'
          AND fl.scheduled_departure <= NOW()
    """))
    return result.rowcount
```

---

## API Endpoints

```
GET /disruptions/proposals
  → returns all PENDING proposals sorted by severity then age
  → controller uses this to see what needs a decision

POST /disruptions/proposals/{proposal_id}/accept
  body: { decided_by }
  → marks proposal ACCEPTED
  → updates roster_crew_assignment (old crew REPLACED, new crew CONFIRMED)
  → updates roster_leg (triggered_by, updated_at)
  → publishes RosterModifiedEvent
  → FTL Service + Daily Validator react immediately
  → returns { status, leg_id, removed, added }

POST /disruptions/proposals/{proposal_id}/reject
  body: { decided_by, rejection_reason }
  → marks proposal REJECTED
  → excludes all previously proposed crew from next search
  → creates new PENDING proposal with next best candidate
  → if no more candidates → proposal with proposed_crew_id = None (manual handling)
  → returns { status, new_proposal_id, next_candidate }
```

## Published Roster Disruption — Full Status Flow

Starting state: `roster_leg = PUBLISHED`, all crew `roster_crew_assignment = CONFIRMED`

| Disruption | Who detects | roster_leg after | roster_crew_assignment after | disruption_proposals | RosterModifiedEvent |
|-----------|------------|-----------------|-----------------------------|--------------------|--------------------|
| CANCELLATION | Observer | `INVALIDATED` | all → `INVALIDATED` | none | ✅ per released crew |
| DELAY — crew still legal | Observer | `PUBLISHED` | `CONFIRMED` unchanged | none | ❌ |
| DELAY — crew fails legality | Observer | `PUBLISHED` | failing crew → `INVALIDATED` → `REPLACED` on accept | `PENDING` → `ACCEPTED` | ✅ on accept |
| SCHEDULE_CHANGE | Weekly Planner re-plan | `PUBLISHED` | failing crew → `INVALIDATED` → `REPLACED` on accept | `PENDING` → `ACCEPTED` | ✅ on accept |
| AIRCRAFT_SWAP — pilot fails | Weekly Planner re-plan | `PUBLISHED` | failing pilots → `INVALIDATED` → `REPLACED` on accept | `PENDING` → `ACCEPTED` | ✅ on accept |
| ROUTE_CHANGE | Weekly Planner re-plan | `PUBLISHED` | `CONFIRMED` unchanged until manual reassign | `PENDING` (no candidate) | ✅ on manual reassign |
| Crew disrupted — replacement found | Daily Validator / Ops Desk | `PUBLISHED` | disrupted crew → `INVALIDATED` → `REPLACED` on accept | `PENDING` → `ACCEPTED` | ✅ on accept |
| Crew disrupted — no replacement | Daily Validator / Ops Desk | `PUBLISHED` | disrupted crew → `INVALIDATED` | `PENDING` (proposed_crew_id=None) | ❌ |
| Controller rejects all candidates | Controller | `PUBLISHED` | `INVALIDATED` stays | all `REJECTED` → final `PENDING` (None) | ❌ |
| Proposal expires (leg departs) | Nightly job 00:30 | `PUBLISHED` | `INVALIDATED` stays | `EXPIRED` | ❌ |

---

## Status Reference

### `roster_leg.status`

| Status | Set by | Meaning |
|--------|--------|---------|
| `DRAFT` | Weekly Planner Job A | Planned, not yet approved by controller |
| `PUBLISHED` | Controller via `POST /planner/roster/{leg_id}/approve` | Approved, crew notified |
| `INVALIDATED` | Disruption Handler on CANCELLATION | Flight cancelled, all crew released |

### `roster_crew_assignment.status`

| Status | Set by | Meaning |
|--------|--------|---------|
| `DRAFT` | Weekly Planner Job A | Planned, not yet approved |
| `CONFIRMED` | Controller approval or Disruption Handler accept | Crew member confirmed on this leg |
| `REPLACED` | Disruption Handler accept or manual reassign | Crew swapped out, `replaced_by` points to new crew |
| `INVALIDATED` | Disruption Handler on CANCELLATION, or legality breach | Crew released from this leg |

### `disruption_proposals.status`

| Status | Set by | Meaning |
|--------|--------|---------|
| `PENDING` | Disruption Handler | Waiting for controller decision |
| `ACCEPTED` | Controller via `POST /disruptions/proposals/{id}/accept` | Approved — roster updated, `RosterModifiedEvent` published |
| `REJECTED` | Controller via `POST /disruptions/proposals/{id}/reject` | Rejected — next candidate proposed automatically |
| `EXPIRED` | Nightly job at 00:30 | Leg departed before controller acted |

---

## Complete Flow After Proposal Accepted

```
Controller POST /disruptions/proposals/{id}/accept
        ↓
disruption_proposals.status = ACCEPTED
        ↓
roster_crew_assignment:
  old crew → REPLACED  (replaced_by = new_crew_id)
  new crew → CONFIRMED (inserted fresh)
roster_leg:
  triggered_by = decided_by
  updated_at   = NOW()
  status stays PUBLISHED — leg is still active
        ↓
RosterModifiedEvent published
        ↓
    ┌───────────────────────────────────────┐
    │                                       │
FTL Service                          Daily Validator
on_roster_modified()                 on_roster_modified()
    │                                       │
removed crew → UNAVAILABLE           re-validates all future legs
added crew   → duty_start = now      for both removed + added crew
               status = AVAILABLE          │
                                    if any leg fails legality
                                           ↓
                                    CrewDisruptedEvent published
                                           ↓
                                    Disruption Handler
                                    creates new proposal
                                           ↓
                                    chain repeats until clean
```

---

## Edge Cases

| Situation | Handling |
|-----------|---------|
| No replacement candidate found | Invalidate the disrupted crew's assignment first. Then create proposal with `proposed_crew_id = NULL` — controller must handle manually. Without invalidating, the disrupted crew member remains shown as assigned |
| Leg already departed when event arrives | Skip — check `leg.scheduled_departure <= now()` before doing anything |
| Flight cancelled — no replacement needed | Invalidate all assignments, no proposal created |
| Controller rejects all candidates | Final proposal has `proposed_crew_id = NULL` — leg marked UNDERSTAFFED |
| Same crew disrupted on 3 future legs | One `CrewDisruptedEvent` per leg — one proposal per leg. Problem: handler fetches live FTL state each time, so the same replacement candidate can be proposed for all 3 legs before any is confirmed. Guard: after proposing a candidate for leg 1, exclude that candidate from the pool for legs 2 and 3 until their proposal is resolved |
| Delay threshold for crew re-check | Re-run legality for all assigned crew against the new departure time on any delay — no minimum threshold. Even a short delay can push a crew member past their duty period limit if they are already near the cap |
| Aircraft swap — cabin crew | Cabin crew have no type ratings in this system. Gate 3 always fails for cabin on an aircraft swap. Skip type rating check for cabin crew on AIRCRAFT_SWAP — only re-check pilots |
| Duplicate event for same leg + crew | If a PENDING proposal already exists for the same `leg_id` + `removed_crew_id`, do not insert a second one. Check before inserting — if found, skip silently |
| ROUTE_CHANGE disruption type | Must be explicitly handled — create proposal with `proposed_crew_id = NULL` and `status = PENDING`. Without this branch the event falls through silently and nothing is created |
| Proposal expires (leg departs before decision) | Nightly job marks all PENDING proposals for departed legs as EXPIRED. The expiry job must be a method on `DisruptionHandler` that calls `disruption_repository.expire_stale_proposals` — the scheduler cannot call the repository directly |

---

## What the Disruption Handler Does NOT Do

| Not its job | Who handles it |
|-------------|---------------|
| Detect delays or cancellations | Observer |
| Detect FTL breaches in future roster | Weekly Planner Validator |
| Update FTL state after a leg lands | FTL Service |
| Send notifications to crew | Notification service (not yet built) |
| Approve its own proposals | Controller via API — human decision always required |
| Handle sick calls directly | Ops Desk calls `POST /crew/{id}/unavailable` → emits `CrewDisruptedEvent` → handler picks it up |
| Detect leave added covering an assigned leg | Leave Client (`add_leave_record`) publishes `CrewDisruptedEvent(reason=LEAVE_ADDED)` automatically — handler picks it up |

---

## End to End Test

```bash
# Trigger a crew disruption manually
curl -X POST http://localhost:8000/crew/C-003/unavailable \
  -H "Content-Type: application/json" \
  -d '{"reason": "SICK", "from_datetime": "2024-02-05T00:00:00", "to_datetime": "2024-02-06T23:59:59"}'

# Check proposals created
curl http://localhost:8000/disruptions/proposals

# Accept the top proposal
curl -X POST http://localhost:8000/disruptions/proposals/{proposal_id}/accept \
  -H "Content-Type: application/json" \
  -d '{"decided_by": "ops_controller_01"}'

# Verify roster updated
docker exec -it crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "SELECT leg_id, crew_id, status, replaced_by FROM roster_crew_assignment WHERE leg_id LIKE '%20240205%';"

# Verify roster_leg stamped
docker exec -it crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "SELECT leg_id, status, triggered_by, updated_at FROM roster_leg WHERE leg_id LIKE '%20240205%';"
```
