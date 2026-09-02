# CrewOps Dashboard — UI/UX Design & Implementation Plan

> Last updated after full cross-reference audit against:
> `CONVERSATION_LAYER.md`, `WEEKLY_PLANNER.md`, `OBSERVER_HANDLER.md`,
> `DISRUPTION_HANDLER.md`, `CREWOPS_COMPLETE_IMPLEMENTATION_PLAN.md`,
> all source files in `services/`, `api/`, `conversation/`, `rules/`, `db/`,
> and the live `dashboard_preview/index.html`.

---

## Audit Findings — Issues Fixed in This Document

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| 1 | Dashboard `APIS` list | Missing `GET /planner/roster`, `POST /planner/roster/{leg_id}/approve`, `POST /planner/roster/{leg_id}/reassign`, `GET /observer/legs` | Added all 4 to API Explorer |
| 2 | Proposal PROP-002 data | HIGH proposal with no candidates and "no action required" — a proposal with no candidates only exists when all candidates are exhausted, not when crew pass legality. A delay where all crew pass legality produces **no proposal at all** | Corrected: PROP-002 now shows a real FTL-breach candidate scenario |
| 3 | `_classify_severity` boundary | `WEEKLY_PLANNER.md` doc says `< 2 days → CRITICAL` but actual code in `tools.py` and `weekly_planner_service.py` uses `< 1 day → CRITICAL` | Dashboard uses the implemented values: `<1=CRITICAL, ≤2=HIGH, ≤7=MEDIUM, >7=LOW` |
| 4 | Chat confirm flow | "Apply it" must route through `DisruptionHandler` pipeline, not directly assign. Dashboard correctly shows "Approve from your Disruption Inbox" | Confirmed correct — documented explicitly |
| 5 | FTL alert `CUMULATIVE_HOURS_WARNING` threshold | Service fires at `> 90h` (not `>= 90h`). Dashboard shows `88h` which correctly triggers it | Confirmed correct |
| 6 | `pushed_at` column | Present in `init.sql`, used by `get_unpushed_proposals()` and `mark_proposal_pushed()` | Confirmed aligned |
| 7 | Observer poll schedule | `main.py` uses `CronTrigger(minute="*/5")` not `IntervalTrigger` | Admin panel job list corrected |
| 8 | B737 crew requirement | `crew_requirements.py`: B737 = 2 pilots + 3 cabin = 5 total. AI305 shows `3/5` (2 crew missing after Capt Ravi sick + CC Amit on leave) | Confirmed correct |
| 9 | Conversation layer `POST /chat` response shape | `ChatResponse` has `session_id`, `response`, `mode`, `requires_confirmation`. Dashboard chat panel must handle `requires_confirmation=true` to show confirm/cancel buttons | Documented in chat panel spec |
| 10 | `auto_resolve_low` job | Runs every 30 min via `CronTrigger(minute="*/30")`. Dashboard shows correct schedule | Confirmed |

---

## Overview

Single-page application. Dark theme. Four panels visible simultaneously on a 1440px wide screen.

**Backend:** FastAPI on `localhost:8000`. All data comes from real API endpoints — no mock data in production UI.

**Tech stack:** Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui, Recharts, TanStack Query.

**Color system:**
- Background: `#0A0E1A`
- Surface: `#111827`
- Border: `#1F2937` / `#374151`
- Blue accent: `#3B82F6`
- Success: `#10B981`
- Warning: `#F59E0B`
- Danger: `#EF4444`
- Critical pulse: `#EF4444` with animated ring
- Text primary: `#F9FAFB`
- Text muted: `#6B7280`

---

## Backend API Alignment — Complete Endpoint Map

Every UI action maps to exactly one backend endpoint. No UI action writes data without going through the API.

| UI Action | HTTP | Endpoint | Backend handler |
|-----------|------|----------|-----------------|
| Load today's flights | GET | `/observer/legs/today` | `FlightObserver.get_todays_active_legs()` |
| Load legs by date/offset | GET | `/observer/legs?target_date=` or `?offset=` | `FlightObserver.get_legs()` |
| Load roster for week | GET | `/planner/roster?start=&end=` | `roster_repository.get_roster_for_date_range()` |
| Approve roster leg | POST | `/planner/roster/{leg_id}/approve` | `roster_repository.approve_roster_leg()` → status=PUBLISHED |
| Manual crew reassign | POST | `/planner/roster/{leg_id}/reassign` | legality check → `replace_roster_crew_assignment()` → `RosterModifiedEvent` |
| Trigger roster build | POST | `/planner/build` | `RosterPlanner.build()` |
| Trigger validation | POST | `/planner/validate` | `DailyValidator.validate()` |
| Load proposals | GET | `/disruptions/proposals` | `disruption_repository.get_pending_proposals()` |
| Accept proposal | POST | `/disruptions/proposals/{id}/accept` | `accept_proposal()` → `replace_roster_crew_assignment()` → `RosterModifiedEvent` |
| Reject proposal | POST | `/disruptions/proposals/{id}/reject` | `DisruptionHandler.reject_and_repropose()` |
| Mark crew unavailable | POST | `/crew/{id}/unavailable` | publishes `CrewDisruptedEvent` → `DisruptionHandler` pipeline |
| Get crew FTL state | GET | `/crew/{id}/ftl` | `ftl_repository.get_ftl_state_by_crew_id()` |
| Trigger FTL scan | POST | `/ftl/scan` | `FlightTimeLimitsService.run_proactive_alert_scan()` |
| Trigger FTL recalc | POST | `/ftl/recalculate` | `FlightTimeLimitsService.run_midnight_recalculation()` |
| Chat message | POST | `/chat` | LangGraph agent → classify → route → execute → format |
| Health check | GET | `/health` | DB check + mock flags + scheduler jobs |

---

## Event Bus → UI Update Chain

The UI never subscribes to the event bus directly. It polls the API. The event bus drives backend state changes which the UI picks up on the next poll.

```
Observer detects delay
    → publishes FlightDisruptedEvent
    → DisruptionHandler.handle_flight_disrupted()
    → _find_and_rank_candidates()
    → disruption_repository.insert_proposal()  ← DB write
    → UI polls GET /disruptions/proposals every 10s
    → new PENDING card appears in Disruption Inbox
```

```
Controller clicks Confirm in Disruption Inbox
    → POST /disruptions/proposals/{id}/accept
    → disruption_repository.accept_proposal()
    → roster_repository.replace_roster_crew_assignment()
    → event_bus.publish(RosterModifiedEvent)
    → ftl_service.on_roster_modified()  ← FTL state updated
    → daily_validator.on_roster_modified()  ← future legs re-validated
    → UI polls GET /planner/roster every 60s
    → roster row updates to show new crew
```

---

## Polling Strategy

| Data | Endpoint | Interval | TanStack Query key |
|------|----------|----------|--------------------|
| Disruption proposals | `GET /disruptions/proposals` | 10s | `['proposals']` |
| Today's flights | `GET /observer/legs/today` | 30s | `['flights-today']` |
| Roster | `GET /planner/roster?start=&end=` | 60s | `['roster', start, end]` |
| FTL state (per visible crew) | `GET /crew/{id}/ftl` | 60s | `['ftl', crew_id]` |
| Push notifications | drained from `POST /chat` response | on each message | — |

Push notifications (`_push_queue` in `main.py`) are prepended to the `POST /chat` response body when `_push_queue` is non-empty. The `useChat` hook checks `response` for `[ALERT]` prefix and surfaces it as a toast + inbox update.


---

## Layout — Full Dashboard (1440 x 900)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  TOPBAR  [✈ CrewOps]  [Mon 05 Feb 2024]  [●LIVE]          [🔔]  [OC ops_01 ▾] │
├──────────┬──────────────────────────────────────────────┬────────────────────────┤
│          │  [stat][stat][stat][stat]                    │                        │
│  LEFT    │  ─────────────────────────────────────────  │  DISRUPTION INBOX      │
│  NAV     │  ROSTER  [Week Grid●][Timeline][List] ◀ ▶   │  (top half, 376px)     │
│  52px    │  ─────────────────────────────────────────  │                        │
│          │  week grid / timeline / list view            │  ────────────────────  │
│  📋      │                                              │                        │
│  ✈       │  ─────────────────────────────────────────  │  AI ASSISTANT          │
│  👥      │  FLIGHT MONITOR  ●LIVE  polls every 5 min   │  (bottom half)         │
│  ⚡      │  flight rows with left-border color coding   │                        │
│  ─       │                                              │                        │
│  ⚙       │                                              │                        │
└──────────┴──────────────────────────────────────────────┴────────────────────────┘
```

---

## Stat Cards Row

Four cards always visible at the top of the dashboard. Values come from aggregating the polling data client-side — no dedicated endpoint.

| Card | Value source | Color |
|------|-------------|-------|
| Flights Today | `count(GET /observer/legs/today)` | Blue `#3B82F6` |
| Disruptions | `count(GET /disruptions/proposals WHERE status=PENDING)` | Red `#EF4444` |
| Crew Available | `count(GET /crew/*/ftl WHERE status=AVAILABLE)` | Green `#10B981` |
| Pending Proposals | `count(GET /disruptions/proposals)` | Amber `#F59E0B` |

---

## Panel 1 — Roster View

### Data source
`GET /planner/roster?start=YYYY-MM-DD&end=YYYY-MM-DD`

Returns `list[dict]` from `roster_repository.get_roster_for_date_range()`:
```json
{
  "leg_id": "AI854",
  "crew_id": "C-001",
  "status": "CONFIRMED",
  "assigned_by": "SCHEDULER",
  "scheduled_departure": "2024-02-05T06:00:00Z",
  "origin_iata": "PNQ",
  "destination_iata": "DEL",
  "aircraft_type": "B737",
  "flight_number": "AI854"
}
```

The UI groups rows by `leg_id` to build the week grid. `roster_leg.status` (DRAFT/PUBLISHED/INVALIDATED) is fetched separately or inferred from `roster_crew_assignment.status`.

### Status badge mapping

| `roster_leg.status` | Badge | Color | Extra |
|--------------------|-------|-------|-------|
| `PUBLISHED` | ✓ PUBLISHED | Green `#10B981` | — |
| `DRAFT` | ⚠ DRAFT | Amber `#F59E0B` | [Approve] button inline |
| `INVALIDATED` | ✗ INVALIDATED | Grey, strikethrough row | — |
| Any leg with PENDING proposal | 🔴 DISRUPTED | Red `#EF4444` + pulse ring | — |

### Week Grid View

```
FLIGHT      MON 05    TUE 06    WED 07    THU 08    FRI 09   SAT 10  SUN 11
──────────────────────────────────────────────────────────────────────────────
AI854       [published block]  ·         ·         ·         ·       ·
PNQ→DEL     C-001, C-004
AI101       [draft block]      ·         ·         ·         ·       ·
DEL→LHR     C-001, C-002
AI305       [disrupted block]  ·         ·         ·         ·       ·
BOM→CCU     C-004, C-013  ⚠ C-003 SICK
AI501       ·         [published]  ·      ·         ·         ·       ·
DEL→BLR     ·         C-007, C-008
```

Click any block → opens Leg Detail Modal.

**Block colors:**
- Published: `rgba(16,185,129,0.1)` border `rgba(16,185,129,0.3)`
- Draft: `rgba(245,158,11,0.1)` border `rgba(245,158,11,0.3)`
- Disrupted: `rgba(239,68,68,0.12)` border `rgba(239,68,68,0.4)` + pulse ring

### Timeline View

Gantt-style. X-axis = hours 06:00–22:00. Y-axis = crew members.

```
06:00  08:00  10:00  12:00  14:00  16:00  18:00  20:00
──────────────────────────────────────────────────────
C-001  [══AI854══]         [══════AI101══════════]
C-002                      [══════AI101══════════]
C-003  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  SICK
C-004              [══AI305══]
C-007  [RESERVE ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
C-008  [RESERVE ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
```

Block colors: published=blue `#3B82F6`, disrupted=red `#EF4444`, reserve=grey `#374151` dashed, sick=red-tinted with red left border.

### List View

One row per leg. Shows flight, route, time, status badge, crew chips, Approve button for DRAFT.

### Leg Detail Modal

Triggered by clicking any roster block. Calls no additional API — uses data already in the roster query.

```
AI305 · BOM→CCU                              [✓ PUBLISHED / ⚠ DRAFT]  [✕]
──────────────────────────────────────────────────────────────────────────
TIME        10:00–12:30
AIRCRAFT    B737
REG         VT-SJL
──────────────────────────────────────────────────────────────────────────
ASSIGNED CREW
PILOT   FO Anita Nair (C-004)        ✓ CONFIRMED
CABIN   CC Pooja Gupta (C-013)       ✓ CONFIRMED
──────────────────────────────────────────────────────────────────────────
⚠ Capt Ravi Singh (C-003) — SICK · Replacement pending in Disruption Inbox
──────────────────────────────────────────────────────────────────────────
[✓ Approve Leg]  [View Proposals]  [Close]
```

Approve button calls `POST /planner/roster/{leg_id}/approve` with `body: { approved_by: user_id }`.


---

## Panel 2 — Flight Monitor

### Data source
`GET /observer/legs/today` — polls every 30s via TanStack Query.

Returns `list[FlightLeg]` from `FlightObserver.get_todays_active_legs()`. The UI derives `status` from `FlightLeg.status` and `delay_minutes` from `FlightLeg.delay_minutes`.

### Row color coding

| `FlightLeg.status` | Left border | Badge |
|-------------------|-------------|-------|
| `SCHEDULED` | none | ✓ SCHEDULED (grey) |
| airborne (status=SCHEDULED, actual_departure set) | Blue `#3B82F6` | ✈ AIRBORNE |
| `DELAYED` (delay_minutes > 0) | Amber `#F59E0B` | ⏱ DELAYED |
| Has PENDING proposal | Red `#EF4444` | ⚠ DISRUPTED |
| `CANCELLED` | Grey, strikethrough | ✗ CANCELLED |

Delay badge pulses if `delay_minutes >= 120`.

Crew count shows `filled/required` in red when `len(assigned_crew) < required`. Required count comes from `crew_requirements.py`: A320/B737=5, B787=8.

### Expanded row

Click any row to expand. Shows aircraft, registration, scheduled vs actual times, assigned crew with FTL status from `GET /crew/{id}/ftl`.

```
AI202  DEL→BOM  A320  VT-PPM
Scheduled: 09:00  Actual: 11:30  Delay: +150 min  ⚠ MEDIUM
──────────────────────────────────────────────────────────────
ASSIGNED CREW
C-007  Capt Vikram Joshi    PILOT    ✓ FTL OK  (4.5h / 13h)
C-008  FO Kavya Menon       PILOT    ✓ FTL OK  (4.5h / 13h)
C-010  SP Sunita Kapoor     CABIN    ✓ OK
C-013  CC Pooja Gupta       CABIN    ✓ OK
──────────────────────────────────────────────────────────────
[View Proposals]  [Re-check FTL]
```

"Re-check FTL" calls `POST /ftl/scan` and refreshes the FTL data.

### Delay severity — matches Observer exactly

| `delay_minutes` | Severity | Source |
|----------------|----------|--------|
| ≥ 240 | HIGH | `_SEVERITY_THRESHOLDS` in `observer_service.py` |
| ≥ 120 | MEDIUM | same |
| ≥ 30 | LOW | same |
| < 30 | — | no event published, no badge |
| CANCELLATION | CRITICAL | always |

---

## Panel 3 — Disruption Inbox

### Data source
`GET /disruptions/proposals` — polls every 10s.

Returns `list[dict]` from `disruption_repository.get_pending_proposals()`, sorted by severity (CRITICAL→HIGH→MEDIUM→LOW) then `proposed_at ASC`.

Each row includes: `proposal_id`, `leg_id`, `disruption_type`, `disruption_reason`, `removed_crew_id`, `proposed_crew_id`, `proposal_score`, `status`, `severity`, `source`, `proposed_at`, `scheduled_departure`, `origin_iata`, `destination_iata`, `flight_number`.

### Proposal card structure

```
┌─────────────────────────────────────────────────────┐
│ 🔴 CRITICAL  •  AI305 BOM→CCU  •  departs 47m      │  ← prop-head.crit
├─────────────────────────────────────────────────────┤
│ Capt Ravi Singh called sick. (SICK_CALL)            │
│                                                     │
│ ● Capt Vikram Joshi  C-007  At VABB ✓   Score: 87  │  ← top candidate
│ ○ Capt Nisha Bose    C-009  At VIDP ✓   Score: 74  │  ← alt candidate
├─────────────────────────────────────────────────────┤
│ [✓ Confirm Vikram]  [✗ Reject]  [More ▾]  14:32   │
└─────────────────────────────────────────────────────┘
```

**Card border + header colors by severity:**

| Severity | Border | Header bg |
|----------|--------|-----------|
| CRITICAL | `rgba(239,68,68,0.5)` + pulse ring | `rgba(127,29,29,0.6)` |
| HIGH | `rgba(249,115,22,0.4)` | `rgba(124,45,18,0.5)` |
| MEDIUM | `rgba(245,158,11,0.35)` | `rgba(120,53,15,0.45)` |
| LOW | `#374151` | `#1F2937` |

**Countdown timer:** computed from `proposed_at` + severity window:
- CRITICAL: 15 min
- HIGH: 60 min
- MEDIUM: 240 min
- LOW: no countdown (auto-resolved by `auto_resolve_low_severity()`)

Timer turns red when < 5 min remaining. Card auto-removes when `status` changes from PENDING on next poll.

### Confirm action

`POST /disruptions/proposals/{proposal_id}/accept`
```json
{ "decided_by": "ops_controller_01" }
```

Backend: `disruption_repository.accept_proposal()` → `roster_repository.replace_roster_crew_assignment()` → `event_bus.publish(RosterModifiedEvent)` → FTL Service + DailyValidator react.

Card animates out (green flash, translateX). Toast: "✓ Capt Vikram assigned to AI305."

### Reject action

`POST /disruptions/proposals/{proposal_id}/reject`
```json
{ "decided_by": "ops_controller_01", "rejection_reason": "crew not available" }
```

Backend: `DisruptionHandler.reject_and_repropose()` — marks REJECTED, excludes already-proposed crew, creates new PENDING proposal with next candidate. New card appears on next 10s poll.

### More ▾ dropdown

Shows next ranked candidates from the same `_find_and_rank_candidates()` result. All shown candidates have passed all 11 legality gates. Clicking any candidate calls accept with that `proposed_crew_id`.

### Proposal with no candidate

When `proposed_crew_id = NULL` (all candidates exhausted):
```
⚠ No replacement found. Manual handling required.
[Reassign manually via chat or roster panel]
```

---

## Panel 4 — AI Chat

### Data source
`POST /chat` — called on each user message.

Request:
```json
{ "session_id": "sess-abc123", "message": "Who can replace Capt Ravi on AI305?", "user_id": "ops_controller_01" }
```

Response (`ChatResponse`):
```json
{ "session_id": "sess-abc123", "response": "...", "mode": "SIMULATE", "requires_confirmation": false }
```

`session_id` is generated client-side (UUID) and persisted in `localStorage`. Same session across page refreshes.

### Mode badge mapping

| `mode` in response | Badge color | Left border |
|-------------------|-------------|-------------|
| `QUERY` | Grey | `#1E3A5F` (dim blue) |
| `SIMULATE` | Blue `#3B82F6` | `#3B82F6` |
| `ACTION` | Amber `#F59E0B` | `#F59E0B` |
| `CONFIRM` | Red `#EF4444` | `#EF4444` |
| `CLARIFY` | Grey | `#374151` |

### `requires_confirmation: true` handling

When `requires_confirmation=true`, the chat bubble renders CONFIRM/CANCEL buttons instead of plain text:

```
🤖  ACTION — confirmation required:

    Capt Ravi Singh (C-003) will be marked unavailable
    for AI305 BOM→CCU (10:00). DisruptionHandler will
    find the best replacement and create a PENDING
    proposal. Approve from your Disruption Inbox —
    no direct assignment happens yet.

    [✓ CONFIRM]  [✗ CANCEL]
```

CONFIRM sends `POST /chat` with `message: "YES"`. CANCEL sends `message: "NO"`.

### SIMULATE → "Apply it" flow

1. User asks "Who can replace Capt Ravi on AI305?"
2. Agent returns `mode=SIMULATE`, lists candidates, appends "Want me to raise this as a disruption?"
3. Session stores `pending_simulation = {crew_id, leg_id, reason, severity}`
4. User clicks "Apply it" or types "yes"
5. Agent detects `pending_simulation` in session, classifies as `ACTION / APPLY_SIMULATION`
6. Agent calls `action_mark_crew_unavailable()` → publishes `CrewDisruptedEvent`
7. `DisruptionHandler.handle_crew_disrupted()` runs full pipeline → PENDING proposal created
8. Response: "Disruption raised. Proposal PROP-xxx is now PENDING in your Disruption Inbox."
9. Disruption Inbox picks up new card on next 10s poll

**Key rule:** "Apply it" does NOT directly assign a crew member. It triggers the DisruptionHandler pipeline. The proposal must be approved from the Disruption Inbox.

### Push notification drain

When `_push_queue` in `main.py` is non-empty, the `POST /chat` response prepends:
```
[ALERT]
AI305 BOM→CCU departs in 47 min. Capt Ravi called sick.
Best replacement: Capt Vikram (C-007) at VABB, FTL legal.
Confirm? [YES / NO / SHOW MORE OPTIONS]

---
{normal response}
```

The `useChat` hook detects `[ALERT]` prefix, splits it out, and shows it as a CRITICAL toast + highlights the Disruption Inbox badge.

### Quick action chips

Context-aware chips above the input. Updated based on active disruptions and pending proposals:

```
[Who's on AI305?]  [Show today's delays]  [FTL status C-007]  [Pending proposals]
```

Chips call `injectChat(text)` which sets the input value and submits.


---

## Crew Page

### Data source
`GET /crew/{id}/ftl` per visible crew member — polls every 60s.
Crew list itself comes from the roster data (no dedicated `GET /crew` endpoint exists — crew are surfaced through roster assignments and FTL state).

### Crew table

```
NAME                  ROLE    BASE   STATUS         FTL TODAY    ACTIONS
──────────────────────────────────────────────────────────────────────────────
Capt Arjun Mehta      PILOT   VIDP   ✓ AVAILABLE    0h / 13h    [View] [Mark]
FO Priya Sharma       PILOT   VIDP   ✓ AVAILABLE    0h / 13h    [View] [Mark]
Capt Ravi Singh       PILOT   VABB   🔴 SICK         —           [View]
FO Anita Nair         PILOT   VABB   ✓ AVAILABLE    2.5h / 13h  [View] [Mark]
Capt Suresh Kumar     PILOT   VOBL   💤 RESTING      —           [View]
FO Deepa Rao          PILOT   VIDP   ✗ UNAVAILABLE  —           [View]
Capt Vikram Joshi     PILOT   VIDP   ✓ AVAILABLE    0h / 13h    [View] [Mark]
SP Sunita Kapoor      CABIN   VIDP   ✓ AVAILABLE    —           [View] [Mark]
CC Amit Shah          CABIN   VABB   📅 ON LEAVE     —           [View]
```

FTL bar: `flight_hours_current_duty / max_duty_period_hours`. Color: green < 60%, amber 60–84%, red ≥ 85%.

[Mark] button → `POST /crew/{id}/unavailable` via chat confirmation flow (not direct API call — goes through conversation layer to ensure confirmation).

### Crew Detail Drawer

Slides in from right. Data from `GET /crew/{id}/ftl`.

```
Capt Vikram Joshi  C-007                              [✕ Close]
CAPTAIN · PILOT · VIDP
✓ AVAILABLE
──────────────────────────────────────────────────────
FTL STATE
Current duty:   0.0h / 13.0h   ░░░░░░░░░░░░  0%
28-day hours:  30.0h / 100h    ████░░░░░░░░  30%
7-day hours:   12.0h / 60h     ███░░░░░░░░░  20%
Consec. days:   1 / 6          ██░░░░░░░░░░  17%
Location:       VIDP (home base)
──────────────────────────────────────────────────────
LICENSES
A320  expires 2025-10-31  ✓ Medical OK
B737  expires 2025-08-15  ✓ Medical OK
──────────────────────────────────────────────────────
THIS WEEK
Mon 05  AI202 DEL→BOM  09:00  ✓ CONFIRMED
Tue 06  AI703 DEL→BOM  08:00  ✓ CONFIRMED
Wed–Sun  RESERVE VIDP
──────────────────────────────────────────────────────
[Mark Unavailable]  [Ask AI about this crew]
```

"Ask AI" injects `"FTL status for C-007"` into the chat input and submits.

---

## FTL Alerts Page

### Data source
Derived from `GET /crew/*/ftl` polling. The `FlightTimeLimitsAlertEvent` is published by `FlightTimeLimitsService` but not stored in DB — the UI re-derives alerts from live FTL state.

Alert conditions (matching `flight_time_limits_service.py` exactly):

| Alert type | Condition | Severity |
|-----------|-----------|----------|
| `DUTY_PERIOD_APPROACHING` | `status=AVAILABLE` AND `projected_duty_period_end` within 2h | HIGH |
| `CUMULATIVE_HOURS_WARNING` | `flight_hours_28_day > 90` | MEDIUM |
| `WEEKLY_REST_OVERDUE` | `last_weekly_rest_end` more than 6 days ago | HIGH |

Each alert card shows: alert type, crew name, message, [Acknowledge] and [View Crew] buttons.

---

## Admin Page

Full-page takeover via left nav ⚙.

### Data Pipeline panel

Buttons call the seed scripts via `POST /planner/build` (for roster) or direct DB seed endpoints. Each button shows a toast on completion.

Seed items: Crew Members, Licenses, FTL States, Flight Legs, Leave Records, Reserve Schedule.

### Mock Flags panel

Each flag is a pill toggle. Current state comes from `GET /health` response `mock_flags` object:
```json
{
  "crew_profile": true,
  "license": true,
  "flight_schedule": true,
  "flight_status": true,
  "ftl_state": true,
  "reserve_schedule": true
}
```

Toggling OFF shows warning: "This will call the real API. Ensure credentials are set in .env."

### Scheduled Jobs panel

Jobs list matches `api/main.py` APScheduler registrations exactly:

| Job ID | Label | Schedule |
|--------|-------|----------|
| `observer_poll` | Observer Poll | Every 5 min (`CronTrigger(minute="*/5")`) |
| `roster_build` | Roster Build | Sun 23:00 |
| `daily_validation` | Daily Validation | Daily 03:00 |
| `ftl_alert_scan` | FTL Alert Scan | Every 15 min |
| `ftl_midnight_recalc` | FTL Midnight Recalc | Daily 00:00 |
| `expire_proposals` | Expire Proposals | Daily 00:30 |
| `auto_resolve_low` | Auto-Resolve LOW | Every 30 min (`CronTrigger(minute="*/30")`) |
| `push_proposals` | Push Proposals | Every 60s (`IntervalTrigger(seconds=60)`) |

[▶ Run Now] calls the corresponding endpoint and shows a toast.

### API Health panel

Data from `GET /health`:
```json
{
  "status": "ok",
  "database": "connected",
  "mock_flags": { ... },
  "scheduled_jobs": ["observer_poll", "roster_build", ...]
}
```

| Service | Indicator | Connected = green dot, Mock = grey dot |
|---------|-----------|----------------------------------------|
| Database | `database == "connected"` | green |
| Aviationstack | `mock_flags.flight_status == false` | green (real) / grey (mock) |
| HRMS / Workday | `mock_flags.crew_profile == false` | green (real) / grey (mock) |
| Event Bus | always running if server up | green |
| APScheduler | `len(scheduled_jobs) > 0` | green |
| FastAPI | server responding | green |

### API Explorer panel

All 16 endpoints listed. Each row: method badge (GET=blue, POST=amber), path in monospace, [▶ Send] button.

Complete endpoint list (corrected from dashboard_preview):

```
GET   /health
GET   /observer/legs/today
GET   /observer/legs?target_date= or ?offset=
POST  /planner/build              body: { requested_by, start?, end? }
POST  /planner/validate           body: { requested_by }
GET   /planner/roster?start=&end=
POST  /planner/roster/{leg_id}/approve    body: { approved_by }
POST  /planner/roster/{leg_id}/reassign   body: { crew_id, replaced_by, reason, requested_by }
GET   /disruptions/proposals
POST  /disruptions/proposals/{id}/accept  body: { decided_by }
POST  /disruptions/proposals/{id}/reject  body: { decided_by, rejection_reason }
POST  /crew/{id}/unavailable      body: { reason, affected_leg_id, days_until_departure }
GET   /crew/{id}/ftl
POST  /ftl/scan
POST  /ftl/recalculate
POST  /chat                       body: { session_id, message, user_id }
```

---

## Toast Notification System

Toasts appear bottom-right. Stack up to 3. Auto-dismiss after 5s except CRITICAL (manual dismiss required).

| Type | Left border | Icon | Auto-dismiss |
|------|-------------|------|-------------|
| CRITICAL | Red `#EF4444` | 🔴 | No — requires [✕] |
| SUCCESS | Green `#10B981` | ✅ | 5s |
| INFO | Blue `#3B82F6` | ℹ | 5s |

CRITICAL toast always includes a [View] button that switches to the dashboard page and highlights the Disruption Inbox.

---

## Component File Structure

```
dashboard/
├── app/
│   ├── layout.tsx              root layout — Topbar + LeftNav
│   ├── page.tsx                main 4-panel grid (Dashboard page)
│   ├── admin/page.tsx          Admin full page
│   └── crew/page.tsx           Crew list page
├── components/
│   ├── roster/
│   │   ├── RosterPanel.tsx     panel container + view switcher
│   │   ├── WeekGrid.tsx        week grid — groups roster rows by leg_id
│   │   ├── TimelineView.tsx    Gantt-style timeline
│   │   ├── LegRow.tsx          single leg row + expand
│   │   └── LegDetailModal.tsx  modal — approve/view crew/view proposals
│   ├── monitor/
│   │   ├── FlightMonitor.tsx   panel container — polls /observer/legs/today
│   │   ├── FlightRow.tsx       single flight row with left-border color
│   │   └── FlightDetail.tsx    expanded row — FTL per crew
│   ├── disruption/
│   │   ├── DisruptionInbox.tsx panel container — polls /disruptions/proposals
│   │   ├── ProposalCard.tsx    single card — severity header, candidates, actions
│   │   ├── CountdownTimer.tsx  live countdown from proposed_at + severity window
│   │   └── CandidateDropdown.tsx  More ▾ — next ranked candidates
│   ├── chat/
│   │   ├── ChatPanel.tsx       panel container — POST /chat
│   │   ├── MessageBubble.tsx   AI/user bubble with mode badge
│   │   ├── ConfirmationCard.tsx  requires_confirmation=true UI
│   │   └── QuickChips.tsx      context-aware quick action chips
│   ├── crew/
│   │   ├── CrewTable.tsx       searchable/filterable crew list
│   │   ├── CrewDrawer.tsx      slide-in detail — FTL bars + licenses + schedule
│   │   └── FtlBar.tsx          progress bar green→amber→red at 85%
│   ├── admin/
│   │   ├── PipelinePanel.tsx   seed buttons
│   │   ├── MockFlagToggles.tsx pill toggles from /health mock_flags
│   │   ├── ScheduledJobs.tsx   job list with Run Now buttons
│   │   └── ApiExplorer.tsx     collapsible endpoint rows
│   └── shared/
│       ├── StatusBadge.tsx     PUBLISHED/DRAFT/DISRUPTED/CANCELLED/INVALIDATED
│       ├── SeverityBadge.tsx   CRITICAL/HIGH/MEDIUM/LOW
│       ├── Toast.tsx           toast with auto-dismiss
│       └── Topbar.tsx          logo, date, live pill, alerts, user chip
├── hooks/
│   ├── useProposals.ts         TanStack Query — GET /disruptions/proposals, 10s
│   ├── useRoster.ts            TanStack Query — GET /planner/roster, 60s
│   ├── useFlights.ts           TanStack Query — GET /observer/legs/today, 30s
│   ├── useCrewFtl.ts           TanStack Query — GET /crew/{id}/ftl, 60s
│   ├── useHealth.ts            TanStack Query — GET /health, 30s
│   ├── useChat.ts              POST /chat, manages session_id in localStorage
│   └── usePushQueue.ts         detects [ALERT] prefix in chat response
├── lib/
│   ├── api.ts                  typed fetch wrappers for all 16 endpoints
│   └── constants.ts            severity colors, status labels, FTL thresholds
└── types/
    ├── roster.ts               RosterRow, RosterLeg
    ├── disruption.ts           Proposal, Candidate
    ├── flight.ts               FlightLeg
    ├── crew.ts                 CrewMember, FtlState
    └── chat.ts                 ChatRequest, ChatResponse
```

---

## Key Interaction Flows

### Flow 1 — Controller confirms CRITICAL proposal from inbox

```
1. DisruptionInbox polls GET /disruptions/proposals every 10s
2. New CRITICAL card appears at top with pulsing red border
3. Toast fires: "AI305 — Capt Ravi sick. Proposal ready."
4. Countdown starts: 15:00
5. Controller reads: "Best: Capt Vikram (C-007) at VABB, score 87"
6. Controller clicks [✓ Confirm Vikram]
7. POST /disruptions/proposals/PROP-001/accept  { decided_by: "ops_controller_01" }
8. Backend: accept_proposal() → replace_roster_crew_assignment() → RosterModifiedEvent
9. FTL Service: C-003 → UNAVAILABLE, C-007 → AVAILABLE + duty_start_time=now
10. DailyValidator: re-validates future legs for both crew
11. Card animates out (green flash)
12. Toast: "✓ Capt Vikram assigned to AI305"
13. Roster panel updates on next 60s poll: AI305 shows C-007 CONFIRMED
14. Flight Monitor: AI305 crew count updates from 3/5 to 4/5
```

### Flow 2 — Chat simulate then apply

```
1. Controller types: "If Capt Ravi is not available for AI305, who can cover?"
2. POST /chat → agent classifies SIMULATE
3. SimulationService.simulate_crew_removal("C-003", "AI305")
4. Response: mode=SIMULATE, lists top 3 candidates with scores
5. Chat appends: "Want me to raise this as a disruption? [YES / NO]"
6. Session stores pending_simulation = {crew_id: "C-003", leg_id: "AI305", ...}
7. Controller clicks "Apply it"
8. POST /chat { message: "Apply it" }
9. Agent detects pending_simulation, classifies ACTION/APPLY_SIMULATION
10. Response: mode=ACTION, requires_confirmation=true
11. Chat shows CONFIRM/CANCEL buttons
12. Controller clicks CONFIRM
13. POST /chat { message: "YES" }
14. action_mark_crew_unavailable("C-003", "AI305", "UNAVAILABLE")
15. event_bus.publish(CrewDisruptedEvent)
16. DisruptionHandler.handle_crew_disrupted() → PENDING proposal created
17. Response: "Disruption raised. Proposal PROP-xxx is now PENDING in your inbox."
18. Disruption Inbox: new card on next 10s poll
```

### Flow 3 — Weekly roster approval

```
1. Admin triggers POST /planner/build { requested_by: "admin" }
2. RosterPlanner.build() runs 3-pass algorithm
3. Roster written to DB as DRAFT
4. UI polls GET /planner/roster — DRAFT rows appear with amber badges
5. Controller clicks [Approve] on each leg (or uses List view bulk approve)
6. POST /planner/roster/{leg_id}/approve { approved_by: "ops_controller_01" }
7. roster_leg.status → PUBLISHED, all roster_crew_assignment.status → CONFIRMED
8. Row flips to green PUBLISHED badge
```

### Flow 4 — FTL alert → proactive action

```
1. FTL scan runs every 15 min (APScheduler)
2. Capt Nisha Bose: flight_hours_28_day = 91 > 90 threshold
3. FlightTimeLimitsAlertEvent published (CUMULATIVE_HOURS_WARNING)
4. UI derives alert from GET /crew/C-009/ftl on next 60s poll
5. Alert card appears in FTL Alerts page
6. Controller types in chat: "FTL status C-009"
7. POST /chat → QUERY → get_crew_ftl("C-009")
8. Response shows 91h/100h, 3 consecutive days, near cap
9. Controller decides to remove C-009 from a future leg
10. POST /planner/roster/{leg_id}/reassign with replacement crew
```

---

## Responsive Breakpoints

| Breakpoint | Layout |
|-----------|--------|
| 1440px+ | Full 4-panel layout |
| 1280px | Right panel collapses to icon strip, expands on click |
| 1024px | Roster and Flight Monitor stack vertically, right panel becomes bottom drawer |
| 768px (tablet) | Single panel view, nav becomes bottom tab bar, chat becomes full-screen modal |
| < 768px | Not supported — ops desk is always desktop |

---

## Design Tokens (Tailwind config)

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        surface:  { DEFAULT: '#111827', raised: '#1F2937', overlay: '#374151' },
        brand:    { DEFAULT: '#3B82F6', dim: '#1E3A5F' },
        success:  '#10B981',
        warning:  '#F59E0B',
        danger:   '#EF4444',
        critical: '#DC2626',
      },
      animation: {
        'pulse-ring': 'pulse-ring 1.5s cubic-bezier(0.4,0,0.6,1) infinite',
        'blink':      'blink 2s ease infinite',
      },
      keyframes: {
        'pulse-ring': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(239,68,68,0.4)' },
          '50%':       { boxShadow: '0 0 0 8px rgba(239,68,68,0)' },
        },
        'blink': {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.3' },
        },
      },
    },
  },
}
```

---

## Bootstrap Commands

```bash
# from /Desktop/setup/
npx create-next-app@latest dashboard \
  --typescript --tailwind --eslint --app --src-dir=no --import-alias="@/*"

cd dashboard
npx shadcn@latest init          # choose dark theme, slate base
npx shadcn@latest add card badge sheet drawer popover toast progress tabs toggle

npm install @tanstack/react-query recharts
```

Backend URL in `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Severity Classification — Single Source of Truth

The `_classify_severity` function is implemented identically in three places. The UI must use the same thresholds:

```
days_until_departure < 1  → CRITICAL
days_until_departure ≤ 2  → HIGH
days_until_departure ≤ 7  → MEDIUM
days_until_departure > 7  → LOW
```

Source: `conversation/tools.py` `_classify_severity()` and `weekly_planner_service.py` `_classify_severity()`.

Note: `WEEKLY_PLANNER.md` doc incorrectly states `< 2 days → CRITICAL`. The implemented code uses `< 1 day → CRITICAL`. The dashboard and this document use the implemented values.

---

## FTL Thresholds — Single Source of Truth

All thresholds come from `flight_time_limits_service.py` and `rules/legality.py`:

| Counter | Cap | Alert threshold |
|---------|-----|----------------|
| `flight_hours_28_day` | 100h | > 90h (`_CUMULATIVE_HOURS_WARNING = 90.0`) |
| `duty_hours_7_day` | 60h | — |
| `consecutive_duty_days` | 6 | ≥ 6 days (`_WEEKLY_REST_OVERDUE_DAYS = 6`) |
| `projected_duty_period_end` | varies | within 2h (`_FDP_ALERT_BUFFER_HOURS = 2.0`) |

FTL bar in crew drawer turns red at 85% of any cap.
