# CrewOps Dashboard — UI/UX Design Document

---

## Overview

Single-page application. Dark theme. Four panels visible simultaneously on a 1440px wide screen. No page navigation — everything is always visible and live-updating.

**Tech stack:** React 18, TypeScript, Tailwind CSS, shadcn/ui, Recharts, TanStack Query.

**Color system:**
- Background: `#0A0E1A` (near-black navy)
- Surface: `#111827` (dark card)
- Border: `#1F2937`
- Primary accent: `#3B82F6` (blue)
- Success: `#10B981` (green)
- Warning: `#F59E0B` (amber)
- Danger: `#EF4444` (red)
- Critical pulse: `#EF4444` with animated ring
- Text primary: `#F9FAFB`
- Text muted: `#6B7280`

---

## Layout — Full Dashboard (1440 x 900)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  TOPBAR  [CrewOps logo]  [Date: Mon 05 Feb 2024]  [●LIVE]  [ops_controller_01▾] │
├──────────────┬──────────────────────────────────────┬──────────────────────────┤
│              │                                      │                          │
│  LEFT NAV    │         MAIN CONTENT AREA            │    RIGHT PANEL           │
│  (64px)      │         (flex, fills space)          │    (380px fixed)         │
│              │                                      │                          │
│  [≡] Menu    │  ┌──────────────────────────────┐   │  ┌──────────────────────┐│
│              │  │   ROSTER VIEW (top half)     │   │  │  DISRUPTION INBOX    ││
│  [📋] Roster │  │   Week grid / Timeline       │   │  │  (notification panel)││
│              │  └──────────────────────────────┘   │  └──────────────────────┘│
│  [⚡] Alerts │  ┌──────────────────────────────┐   │  ┌──────────────────────┐│
│              │  │   FLIGHT MONITOR (bot half)  │   │  │  AI CHAT             ││
│  [✈] Flights │  │   Today's legs live status   │   │  │  (conversation layer)││
│              │  └──────────────────────────────┘   │  └──────────────────────┘│
│  [👥] Crew   │                                      │                          │
│              │                                      │                          │
│  [⚙] Admin  │                                      │                          │
│              │                                      │                          │
└──────────────┴──────────────────────────────────────┴──────────────────────────┘
```

---

## Panel 1 — Roster View

### Visual — Week Grid (default view)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ROSTER                    [Week Grid ●] [Timeline] [List]    Feb 05–11 ◀ ▶ │
│  ─────────────────────────────────────────────────────────────────────────  │
│  FLIGHT      MON 05    TUE 06    WED 07    THU 08    FRI 09   SAT 10  SUN 11│
│  ──────────────────────────────────────────────────────────────────────────  │
│  AI854       ████████  ·         ·         ·         ·        ·       ·     │
│  PNQ→DEL     C-001     ·         ·         ·         ·        ·       ·     │
│              C-006     ·         ·         ·         ·        ·       ·     │
│              ✓ PUBL    ·         ·         ·         ·        ·       ·     │
│  ──────────────────────────────────────────────────────────────────────────  │
│  AI101       ████████  ·         ·         ·         ·        ·       ·     │
│  DEL→LHR     C-001     ·         ·         ·         ·        ·       ·     │
│              C-002     ·         ·         ·         ·        ·       ·     │
│              ⚠ DRAFT   ·         ·         ·         ·        ·       ·     │
│  ──────────────────────────────────────────────────────────────────────────  │
│  AI305       ░░░░░░░░  ·         ·         ·         ·        ·       ·     │
│  BOM→CCU     C-004     ·         ·         ·         ·        ·       ·     │
│              [!] C-003 SICK — replacement pending                           │
│              🔴 DISRUPTED                                                   │
│  ──────────────────────────────────────────────────────────────────────────  │
│  AI501       ·         ████████  ·         ·         ·        ·       ·     │
│  DEL→BLR     ·         C-021     ·         ·         ·        ·       ·     │
│              ·         C-006     ·         ·         ·        ·       ·     │
│              ·         ✓ PUBL    ·         ·         ·        ·       ·     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Status badge colors:**
- `✓ PUBLISHED` → green pill `#10B981`
- `⚠ DRAFT` → amber pill `#F59E0B` + [Approve] button inline
- `🔴 DISRUPTED` → red pill `#EF4444` + animated pulse ring
- `INVALIDATED` → grey strikethrough row, dimmed

**Leg row on hover — expands inline:**
```
┌──────────────────────────────────────────────────────────────────┐
│  AI305  BOM → CCU   B737   10:00 → 12:30                        │
│  ─────────────────────────────────────────────────────────────── │
│  PILOTS    Capt Ravi Singh (C-003)  🔴 SICK — INVALIDATED       │
│            FO Anita Nair (C-004)    ✓ CONFIRMED                  │
│  CABIN     CC Pooja Gupta (C-013)   ✓ CONFIRMED                  │
│            CC Amit Shah (C-014)     ✗ ON LEAVE                   │
│  ─────────────────────────────────────────────────────────────── │
│  [Approve Leg]  [Reassign Crew]  [View Proposals]                │
└──────────────────────────────────────────────────────────────────┘
```

### Visual — Timeline View (alternate)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ROSTER — TIMELINE VIEW                              Feb 05  ◀  TODAY  ▶    │
│                                                                             │
│  06:00   08:00   10:00   12:00   14:00   16:00   18:00   20:00             │
│  ──────────────────────────────────────────────────────────────────────     │
│  C-001  [══AI854══]         [══════AI101══════════════════]                 │
│  C-002                      [══════AI101══════════════════]                 │
│  C-003  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  SICK           │
│  C-004              [══AI305══]                                             │
│  C-007  [RESERVE ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]                │
│  C-010  [RESERVE ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]                │
│  ──────────────────────────────────────────────────────────────────────     │
│  Hover any block → shows leg details + FTL hours used                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Block colors:**
- Published leg: `#3B82F6` solid blue
- Draft leg: `#3B82F6` with diagonal stripe pattern
- Disrupted leg: `#EF4444` red
- Reserve slot: `#374151` grey with dashed border
- Sick/Leave: `#1F2937` dark grey with red left border

---

## Panel 2 — Flight Monitor (Live)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FLIGHT MONITOR — TODAY  ●LIVE (polls every 5 min)    [05 Feb 2024  09:42] │
│  ─────────────────────────────────────────────────────────────────────────  │
│  FLIGHT   ROUTE        DEP      STATUS        DELAY   CREW   ACTION        │
│  ─────────────────────────────────────────────────────────────────────────  │
│  AI854    PNQ → DEL    06:00    ✈ AIRBORNE    +2 min  4      —             │
│  AI202    DEL → BOM    09:00    ⏱ DELAYED     +150m   4      [View]        │
│  AI305    BOM → CCU    10:00    ⚠ DISRUPTED   ON TIME 3/5    [Proposals]   │
│  AI101    DEL → LHR    11:00    ✗ CANCELLED   —       0      [Released]    │
│  AI410    BOM → DEL    15:00    ⏱ DELAYED     +240m   4      [View]        │
│  ─────────────────────────────────────────────────────────────────────────  │
│  AI501    DEL → BLR    07:30    ✓ SCHEDULED   —       4      —             │
│  AI602    BLR → BOM    13:00    ✓ SCHEDULED   —       4      —             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Row color coding:**
- `AIRBORNE` → blue left border `#3B82F6`
- `DELAYED` → amber left border `#F59E0B`, delay badge pulses if > 120 min
- `DISRUPTED` → red left border `#EF4444`, crew count shows `3/5` (filled/required)
- `CANCELLED` → grey row, strikethrough flight number
- `SCHEDULED` → no color, muted text

**Expanded row on click:**
```
┌──────────────────────────────────────────────────────────────────┐
│  AI202  DEL → BOM  A320  VT-PPM                                  │
│  Scheduled: 09:00  Actual: 11:30  Delay: +150 min  ⚠ MEDIUM     │
│  ─────────────────────────────────────────────────────────────── │
│  ASSIGNED CREW                                                    │
│  C-007  Capt Vikram Joshi    PILOT    ✓ FTL OK  (4.5h / 13h)    │
│  C-010  FO Kavya Menon       PILOT    ✓ FTL OK  (4.5h / 13h)    │
│  C-019  SP Meera Pillai      CABIN    ✓ OK                       │
│  C-023  CC Lakshmi Nair      CABIN    ✓ OK                       │
│  ─────────────────────────────────────────────────────────────── │
│  Disruption Handler: re-checking FTL legality for all crew...    │
│  [View Proposals]                                                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## Panel 3 — Disruption Inbox (Right Panel, Top Half)

This is the most critical panel. New proposals push in from the top. CRITICAL items have a pulsing red border.

```
┌──────────────────────────────────────────────────────┐
│  DISRUPTION INBOX          3 pending  [Mark all read]│
│  ────────────────────────────────────────────────────│
│  ┌────────────────────────────────────────────────┐  │
│  │ 🔴 CRITICAL  •  AI305 BOM→CCU  •  departs 47m │  │
│  │ Capt Ravi Singh called sick.                   │  │
│  │ Best replacement:                              │  │
│  │   Capt Vikram Joshi (C-007)                   │  │
│  │   At VABB ✓  FTL legal ✓  Score: 87           │  │
│  │ Alt: Capt Nisha Bose (C-021) ✓ FTL legal Score: 74 │  │
│  │                                                │  │
│  │  [✓ CONFIRM VIKRAM]  [✗ REJECT]  [More ▾]    │  │
│  │                              expires in 14:32  │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │ 🟠 HIGH  •  AI410 BOM→DEL  •  departs 5h 18m  │  │
│  │ Delay +240 min. FTL re-check: all crew legal.  │  │
│  │ No action required.                            │  │
│  │                              [Dismiss]         │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │ 🟡 MEDIUM  •  AI111 DEL→LHR  •  departs 24h   │  │
│  │ C-009 near 28-day cap. Replacement proposed:   │  │
│  │   Capt Nisha Bose (C-021)  Score: 74           │  │
│  │                                                │  │
│  │  [✓ CONFIRM]  [✗ REJECT]  [More ▾]            │  │
│  │                              expires in 3h 52m │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**Card border colors by severity:**
- CRITICAL: `border-red-500` + `animate-pulse` ring, red header background `#7F1D1D`
- HIGH: `border-orange-500`, orange header `#7C2D12`
- MEDIUM: `border-yellow-500`, amber header `#78350F`
- LOW: `border-gray-500`, no animation — shown as small info row

**Countdown timer:** shown in bottom-right of each card. Turns red when < 5 min remaining. Auto-removes card when expired (proposal marked EXPIRED by backend).

**[More ▾] dropdown:** shows the next ranked candidates from the same `_find_and_rank_candidates()` result. All candidates shown have passed the full legality check (type rating, FTL, leave, medical). Candidates that fail any gate are excluded before they reach the UI.
```
┌─────────────────────────────────────┐
│  Option 2: FO Anita Nair (C-004)   │
│  At VABB ✓  FTL legal ✓  Score: 61  │
│  [Confirm FO Nair]                  │
│  ───────────────────────────────────  │
│  Option 3: Capt Nisha Bose (C-021) │
│  At VIDP ✓  FTL legal ✓  Score: 54  │
│  [Confirm Capt Bose]                │
│  ───────────────────────────────────  │
│  No more candidates available       │
└─────────────────────────────────────┘
```

---

## Panel 4 — AI Chat (Right Panel, Bottom Half)

```
┌──────────────────────────────────────────────────────┐
│  AI ASSISTANT              [QUERY] [SIMULATE] [ACTION]│
│  ────────────────────────────────────────────────────│
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ 🤖  Hello. I'm watching 5 active flights     │   │
│  │     today. 3 disruptions need your attention. │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│        ┌────────────────────────────────────────┐   │
│        │ Who can replace Capt Ravi on AI305?  👤│   │
│        └────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ 🤖  SIMULATE — AI305 BOM→CCU, B737, 10:00   │   │
│  │                                              │   │
│  │  Top 3 replacements for Capt Ravi (PILOT):  │   │
│  │                                              │   │
│  │  1. Capt Vikram Joshi (C-007)  Score: 87    │   │
│  │     ✓ At VABB  ✓ B737 rated  ✓ FTL legal   │   │
│  │     Duty after leg: 4.5h / 13h              │   │
│  │                                              │   │
│  │  2. Capt Nisha Bose (C-021)  Score: 74        │   │
│  │     ✓ At VIDP  ✓ B737 rated  ✓ FTL legal   │   │
│  │     Duty after leg: 6.1h / 13h              │   │
│  │                                              │   │
│  │  Want me to assign Capt Vikram? [Apply it]  │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│        ┌────────────────────────────────────────┐   │
│                                                      │
│        │ Yes, apply it                        👤│   │
│        └────────────────────────────────────────┘   │
│                                                      │
│  ┌────────────────────────────────────────────┐   │
│  │ 🤖  ACTION — confirmation required:          │   │
│  │                                              │   │
│  │  Capt Ravi Singh (C-003) will be marked      │   │
│  │  unavailable for AI305 BOM→CCU (10:00).      │   │
│  │  DisruptionHandler will find the best        │   │
│  │  replacement and create a PENDING proposal.  │   │
│  │  Approve from your Disruption Inbox —        │   │
│  │  no direct assignment happens yet.           │   │
│  │                                              │   │
│  │  ┌──────────────┐  ┌──────────────┐         │   │
│  │  │  ✓ CONFIRM   │  │   ✗ CANCEL   │         │   │
│  │  └──────────────┘  └──────────────┘         │   │
│  └────────────────────────────────────────────┘   │
│                                                      │
│  ┌────────────────────────────────────────────┐   │
│  │ 🤖  Done. Disruption raised for AI305.       │   │
│  │     Proposal PROP-L305-20240205103042 is     │   │
│  │     now PENDING in your Disruption Inbox.    │   │
│  │     Approve from the inbox to confirm        │   │
│  │     the replacement.                         │   │
│  └────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  Type a message...                    [Send] │   │
│  └──────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

**Message bubble styles:**
- AI messages: left-aligned, dark surface `#1F2937`, blue left border for SIMULATE, red for ACTION confirmation
- User messages: right-aligned, `#1E3A5F` blue tint
- Mode badge on AI messages: `QUERY` grey, `SIMULATE` blue, `ACTION` amber, `CONFIRM` red

**Quick action chips above input (context-aware):**
```
[Who's on AI305?]  [Show today's delays]  [FTL status C-007]  [Pending proposals]
```
These chips update based on what is currently happening (active disruptions, pending proposals).


---

## Admin Page

Accessed via `[⚙ Admin]` in the left nav. Full-page takeover, not a panel.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ADMIN                                                    ops_controller_01  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐ │
│  │  DATA PIPELINE      │  │  MOCK FLAGS          │  │  SCHEDULED JOBS     │ │
│  │  ─────────────────  │  │  ─────────────────   │  │  ─────────────────  │ │
│  │  [▶ Seed All Data]  │  │  Crew Profile  [ON●] │  │  observer_poll      │ │
│  │  [▶ Seed Crew]      │  │  License       [ON●] │  │  Every 5 min        │ │
│  │  [▶ Seed FTL]       │  │  Flight Sched  [ON●] │  │  [▶ Run Now]        │ │
│  │  [▶ Seed Legs]      │  │  Flight Status [ON●] │  │  ─────────────────  │ │
│  │  [▶ Seed Leave]     │  │  FTL State     [ON●] │  │  roster_build       │ │
│  │  [▶ Seed Reserve]   │  │  Reserve Sched [ON●] │  │  Next: Sun 23:00    │ │
│  │                     │  │                      │  │  [▶ Run Now]        │ │
│  │  Last run:          │  │  Toggle any flag to  │  │  ─────────────────  │ │
│  │  Today 08:14        │  │  switch mock ↔ real  │  │  daily_validation   │ │
│  │  ✓ 6/6 loaded       │  │                      │  │  Next: 03:00        │ │
│  └─────────────────────┘  └─────────────────────┘  │  [▶ Run Now]        │ │
│                                                     │  ─────────────────  │ │
│  ┌─────────────────────────────────────────────┐   │  ftl_alert_scan     │ │
│  │  API HEALTH                                 │   │  Every 15 min       │ │
│  │  ─────────────────────────────────────────  │   │  [▶ Run Now]        │ │
│  │  Database          ● Connected              │   │  ─────────────────  │ │
│  │  Aviationstack     ○ Mock (not called)      │   │  ftl_midnight_recalc│ │
│  │  HRMS / Workday    ○ Mock (not called)      │   │  Next: 00:00        │ │
│  │  Event Bus         ● Running                │   │  [▶ Run Now]        │ │
│  │  APScheduler       ● Running  9 jobs        │   │  ─────────────────  │ │
│  │                                             │   │  expire_proposals   │ │
│  │  GET /health  →  [Test]                     │   │  Next: 00:30        │ │
│  └─────────────────────────────────────────────┘   │  [▶ Run Now]        │ │
│                                                     │  ─────────────────  │ │
│                                                     │  auto_resolve_low   │ │
│                                                     │  Every 30 min       │ │
│                                                     │  [▶ Run Now]        │ │
│                                                     │  ─────────────────  │ │
│                                                     │  push_proposals     │ │
│                                                     │  Every 60s          │ │
│                                                     │  [▶ Run Now]        │ │
│                                                     └─────────────────────┘ │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  API EXPLORER                                                        │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │  [GET  /health ▶]                                                    │   │
│  │  [GET  /observer/legs/today ▶]                                       │   │
│  │  [GET  /observer/legs?target_date= ▶]                                │   │
│  │  [POST /planner/build ▶]  body: requested_by, start?, end?           │   │
│  │  [POST /planner/validate ▶]  body: requested_by                      │   │
│  │  [GET  /planner/roster?start=&end= ▶]                                │   │
│  │  [POST /planner/roster/{leg_id}/approve ▶]  body: approved_by        │   │
│  │  [POST /planner/roster/{leg_id}/reassign ▶]                          │   │
│  │        body: crew_id, replaced_by, reason, requested_by              │   │
│  │  [GET  /disruptions/proposals ▶]                                     │   │
│  │  [POST /disruptions/proposals/{id}/accept ▶]  body: decided_by       │   │
│  │  [POST /disruptions/proposals/{id}/reject ▶]                         │   │
│  │        body: decided_by, rejection_reason                            │   │
│  │  [POST /crew/{id}/unavailable ▶]                                     │   │
│  │        body: reason, affected_leg_id, days_until_departure            │   │
│  │  [GET  /crew/{id}/ftl ▶]                                             │   │
│  │  [POST /ftl/scan ▶]                                                  │   │
│  │  [POST /ftl/recalculate ▶]                                           │   │
│  │  [POST /chat ▶]  body: session_id, message, user_id                  │   │
│  │                                                                      │   │
│  │  Response:                                                           │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  {                                                           │   │   │
│  │  │    "status": "ok",                                           │   │   │
│  │  │    "database": "connected",                                  │   │   │
│  │  │    "mock_flags": {                                           │   │   │
│  │  │      "crew_profile": true, "license": true,                 │   │   │
│  │  │      "flight_schedule": true, "flight_status": true,        │   │   │
│  │  │      "ftl_state": true, "reserve_schedule": true            │   │   │
│  │  │    },                                                        │   │   │
│  │  │    "scheduled_jobs": ["observer_poll", "roster_build", ...]  │   │   │
│  │  │  }                                                           │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Mock flag toggles:** each is a pill toggle. Turning OFF shows a warning: "This will call the real API. Ensure credentials are set in .env."

**[▶ Run Now] buttons:** call the corresponding API endpoint and show a toast notification with the result.

**API Explorer:** each endpoint is a collapsible row. Clicking expands a form for body params and a [Send] button. Response shown in a syntax-highlighted JSON block.

---

## Crew Page

Accessed via `[👥 Crew]` in the left nav.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CREW                    [Search crew...]          [Filter: All ▾] [Base ▾] │
│  ─────────────────────────────────────────────────────────────────────────  │
│  NAME                  ROLE    BASE   STATUS      FTL TODAY    ACTIONS      │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Capt Arjun Mehta      PILOT   VIDP   ✓ AVAILABLE  0h / 13h   [View] [Mark]│
│  FO Priya Sharma       PILOT   VIDP   ✓ AVAILABLE  0h / 13h   [View] [Mark]│
│  Capt Ravi Singh       PILOT   VABB   🔴 SICK       —          [View]       │
│  FO Anita Nair         PILOT   VABB   ✓ AVAILABLE  2.5h / 13h [View] [Mark]│
│  Capt Suresh Kumar     PILOT   VOBL   💤 RESTING    —          [View]       │
│  FO Deepa Rao          PILOT   VIDP   ✗ UNAVAILABLE —          [View]       │
│  Capt Vikram Joshi     PILOT   VIDP   ✓ AVAILABLE  0h / 13h   [View] [Mark]│
│  ─────────────────────────────────────────────────────────────────────────  │
│  SP Sunita Kapoor      CABIN   VIDP   ✓ AVAILABLE  —          [View] [Mark]│
│  CC Rahul Verma        CABIN   VIDP   ✓ AVAILABLE  —          [View] [Mark]│
│  CC Amit Shah          CABIN   VABB   📅 ON LEAVE   —          [View]       │
└─────────────────────────────────────────────────────────────────────────────┘
```

**[View] → Crew Detail Drawer (slides in from right):**

```
┌──────────────────────────────────────────────────────┐
│  Capt Vikram Joshi  C-007              [✗ Close]     │
│  CAPTAIN · PILOT · VIDP                              │
│  ────────────────────────────────────────────────────│
│  FTL STATE                                           │
│  Status:        AVAILABLE                            │
│  Current duty:  0.0h / 13.0h  ████░░░░░░░░  0%     │
│  28-day hours:  45.0h / 100h  ████████░░░░  45%     │
│  7-day hours:   20.0h / 60h   ████████░░░░  33%     │
│  Consec. days:  1 / 6         ██░░░░░░░░░░  17%     │
│  Location:      VIDP (home base)                     │
│  ────────────────────────────────────────────────────│
│  LICENSES                                            │
│  A320  expires 2025-10-31  ✓ Medical OK              │
│  B737  expires 2025-08-15  ✓ Medical OK              │
│  ────────────────────────────────────────────────────│
│  THIS WEEK                                           │
│  Mon 05  AI202 DEL→BOM  09:00  ✓ CONFIRMED          │
│  Tue 06  AI703 DEL→BOM  08:00  ✓ CONFIRMED          │
│  Wed–Sun  RESERVE VIDP                               │
│  ────────────────────────────────────────────────────│
│  [Mark Unavailable]  [Ask AI about this crew]        │
└──────────────────────────────────────────────────────┘
```

**FTL bars:** color shifts from green → amber → red as percentage increases. Turns red at 85%.

---

## Notification Toast System

Toasts appear in the bottom-right corner. Stack up to 3. Auto-dismiss after 5s (except CRITICAL which requires manual dismiss).

```
                              ┌──────────────────────────────────┐
                              │ 🔴 CRITICAL DISRUPTION           │
                              │ AI305 — Capt Ravi Singh sick     │
                              │ Proposal ready for review        │
                              │                    [View] [✗]    │
                              └──────────────────────────────────┘
                              ┌──────────────────────────────────┐
                              │ ✓ Proposal ACCEPTED              │
                              │ Capt Vikram assigned to AI305    │
                              │                             [✗]  │
                              └──────────────────────────────────┘
                              ┌──────────────────────────────────┐
                              │ ℹ AUTO-RESOLVED (LOW)            │
                              │ AI555 — FO Tanya → FO Kavya      │
                              │                             [✗]  │
                              └──────────────────────────────────┘
```

---

## Responsive Breakpoints

| Breakpoint | Layout |
|-----------|--------|
| 1440px+ | Full 4-panel layout as described above |
| 1280px | Right panel collapses to icon strip, expands on click |
| 1024px | Roster and Flight Monitor stack vertically, right panel becomes bottom drawer |
| 768px (tablet) | Single panel view, nav becomes bottom tab bar, chat becomes full-screen modal |
| < 768px | Not supported — ops desk is always desktop |

---

## Component File Structure

```
dashboard/
├── app/
│   ├── layout.tsx              ← root layout, topbar, left nav
│   ├── page.tsx                ← main 4-panel grid
│   ├── admin/page.tsx          ← admin full page
│   └── crew/page.tsx           ← crew list page
├── components/
│   ├── roster/
│   │   ├── RosterPanel.tsx     ← panel container + view switcher
│   │   ├── WeekGrid.tsx        ← week grid view
│   │   ├── TimelineView.tsx    ← gantt-style timeline
│   │   ├── LegRow.tsx          ← single leg row + expand
│   │   └── LegDetailCard.tsx   ← expanded leg detail
│   ├── monitor/
│   │   ├── FlightMonitor.tsx   ← panel container
│   │   ├── FlightRow.tsx       ← single flight row
│   │   └── FlightDetail.tsx    ← expanded flight detail
│   ├── disruption/
│   │   ├── DisruptionInbox.tsx ← panel container
│   │   ├── ProposalCard.tsx    ← single proposal card
│   │   ├── CountdownTimer.tsx  ← expiry countdown
│   │   └── CandidateDropdown.tsx ← more options dropdown
│   ├── chat/
│   │   ├── ChatPanel.tsx       ← panel container
│   │   ├── MessageBubble.tsx   ← single message
│   │   ├── QuickChips.tsx      ← context-aware quick actions
│   │   └── ConfirmationCard.tsx ← action confirmation UI
│   ├── crew/
│   │   ├── CrewTable.tsx
│   │   ├── CrewDrawer.tsx      ← slide-in detail
│   │   └── FtlBar.tsx          ← progress bar with color shift
│   ├── admin/
│   │   ├── PipelinePanel.tsx
│   │   ├── MockFlagToggles.tsx
│   │   ├── ScheduledJobs.tsx
│   │   └── ApiExplorer.tsx
│   └── shared/
│       ├── StatusBadge.tsx     ← PUBLISHED / DRAFT / DISRUPTED / CANCELLED
│       ├── SeverityBadge.tsx   ← CRITICAL / HIGH / MEDIUM / LOW
│       ├── Toast.tsx
│       └── Topbar.tsx
├── hooks/
│   ├── useProposals.ts         ← polls GET /disruptions/proposals every 10s
│   ├── useRoster.ts            ← polls GET /planner/roster
│   ├── useFlights.ts           ← polls GET /observer/legs/today every 30s
│   ├── useChat.ts              ← POST /chat, manages session_id
│   └── usePushQueue.ts         ← drains push messages from POST /chat response
├── lib/
│   ├── api.ts                  ← typed fetch wrappers for all endpoints
│   └── constants.ts            ← severity colors, status labels
└── types/
    ├── roster.ts
    ├── disruption.ts
    ├── flight.ts
    └── crew.ts
```

---

## API Polling Strategy

| Data | Method | Interval | Endpoint |
|------|--------|----------|----------|
| Disruption proposals | TanStack Query | 10s | `GET /disruptions/proposals` |
| Today's flights | TanStack Query | 30s | `GET /observer/legs/today` |
| Roster | TanStack Query | 60s | `GET /planner/roster?start=&end=` |
| FTL states | TanStack Query | 60s | `GET /crew/{id}/ftl` (per visible crew) |
| Push notifications | drained from `/chat` | on each message | `POST /chat` response includes queued pushes |
| Chat responses | fetch | on send | `POST /chat` |

There is no WebSocket endpoint. Push notifications (CRITICAL/HIGH proposals) are queued in `_push_queue` in `main.py` by the `push_proposals` APScheduler job (every 60s). Each `POST /chat` response drains the queue and prepends any pending push messages before the normal response. The 10s `GET /disruptions/proposals` poll is the fallback for the Disruption Inbox panel when no chat session is active.

---

## Key Interaction Flows

### Flow 1 — Controller sees CRITICAL alert and confirms

```
1. Disruption Inbox polls GET /disruptions/proposals every 10s
2. New CRITICAL card appears at top with pulsing red border
3. Toast appears bottom-right: "AI305 — Capt Ravi sick. Proposal ready."
4. Countdown timer starts: 15:00
5. Controller reads: "Best: Capt Vikram (C-007) at VABB, score 87"
6. Controller clicks [✓ CONFIRM VIKRAM]
7. POST /disruptions/proposals/{id}/accept  body: { "decided_by": "ops_controller_01" }
8. Card animates out (green flash)
9. Toast: "✓ Capt Vikram assigned to AI305"
10. Roster panel updates: AI305 row now shows C-007 CONFIRMED
11. Flight Monitor: AI305 crew count updates from 3/5 to 4/5
```

### Flow 2 — Controller uses chat to simulate then apply

```
1. Controller types: "If Capt Ravi is not available for AI305, who can cover?"
2. Agent classifies as SIMULATE, calls SimulationService.simulate_crew_removal()
3. Chat shows SIMULATE badge, lists top 3 legal replacement candidates with scores
4. Chat appends: "Want me to raise this as a disruption? [YES / NO]"
5. Controller types: "Yes"
6. Agent detects pending_simulation in session, classifies as ACTION / APPLY_SIMULATION
7. Agent builds confirmation package, shows:
   "Capt Ravi Singh will be marked unavailable for AI305.
    DisruptionHandler will find the best replacement and create a PENDING proposal.
    Confirm? [YES / NO]"
8. Controller clicks [✓ CONFIRM] or types YES
9. POST /chat → action_mark_crew_unavailable() publishes CrewDisruptedEvent
10. DisruptionHandler.handle_crew_disrupted() runs full pipeline:
    - finds and ranks candidates
    - creates PENDING proposal in disruption_proposals
11. Chat responds: "Disruption raised. Proposal PROP-xxx is now pending in your inbox."
12. Disruption Inbox: new PENDING card appears on next 10s poll
13. Controller approves from inbox as normal
```

Note: "Apply it" does NOT directly assign a crew member. It triggers the DisruptionHandler pipeline. The proposal must be approved from the Disruption Inbox.

### Flow 3 — Admin seeds data and triggers build

```
1. Admin navigates to Admin page
2. Clicks [▶ Seed All Data]
3. Progress bar shows: Crew ✓ → Licenses ✓ → FTL ✓ → Leave ✓ → Reserve ✓ → Legs ✓
4. Toast: "✓ All mock data loaded. 6/6 records."
5. Admin clicks [▶ Run Now] next to roster_build
6. POST /planner/build { requested_by: "admin" }
7. Toast: "Build started. Check roster panel in ~10s."
8. Admin switches to Roster panel — DRAFT rows appear
9. Admin approves each leg via [Approve] inline button
```

---

## Design Tokens (Tailwind config)

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        surface:   { DEFAULT: '#111827', raised: '#1F2937', overlay: '#374151' },
        brand:     { DEFAULT: '#3B82F6', dim: '#1E3A5F' },
        success:   '#10B981',
        warning:   '#F59E0B',
        danger:    '#EF4444',
        critical:  '#DC2626',
      },
      animation: {
        'pulse-ring': 'pulse-ring 1.5s cubic-bezier(0.4,0,0.6,1) infinite',
      },
      keyframes: {
        'pulse-ring': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(239,68,68,0.4)' },
          '50%':       { boxShadow: '0 0 0 8px rgba(239,68,68,0)' },
        },
      },
    },
  },
}
```

---

## Sample Screen Descriptions

### Sample A — Quiet day (no disruptions)

All flights SCHEDULED or AIRBORNE. Disruption Inbox shows "No pending proposals". Roster panel shows a clean week grid with all legs PUBLISHED (green). Chat shows "All systems normal. 5 flights operating today."

### Sample B — Active disruption (CRITICAL)

AI305 row in Roster panel is red with pulse. Disruption Inbox has one CRITICAL card at top with 14-minute countdown. Flight Monitor shows AI305 with crew count 3/5. Chat has auto-pushed the alert: "AI305 BOM→CCU departs in 47 min. Capt Ravi called sick. Confirm Capt Vikram?"

### Sample C — Multiple simultaneous disruptions

Disruption Inbox has 3 cards stacked: CRITICAL (AI305), HIGH (AI410 delay FTL breach), MEDIUM (AI111 28-day cap). Roster panel shows 3 red rows. Flight Monitor shows 2 delayed rows and 1 disrupted row. Chat shows the CRITICAL alert auto-pushed. Controller works top-to-bottom through the inbox.

### Sample D — Admin seeding and building

Admin page open. All 6 seed buttons visible. Mock flags all ON. API health shows all green. API Explorer open on GET /health showing live JSON response with all 6 mock flags. Scheduled jobs panel shows all 9 jobs with next run times.

### Sample E — Weekly roster approval workflow

Roster panel in List view. All legs show DRAFT status with amber badges. Controller clicks [Approve] on each leg inline. Each row flips to PUBLISHED (green) with a brief flash animation. After all approved, a summary toast: "7 legs published for week Feb 05–11."
