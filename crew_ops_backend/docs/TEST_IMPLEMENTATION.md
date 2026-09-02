# Test Implementation Plan

## Status

| File | Tests | Status |
|------|-------|--------|
| `test_event_bus.py` | 5 | ✅ Done |
| `test_legality_rules.py` | 14 | ✅ Done |
| `test_ftl_simulator.py` | 11 | ✅ Done |
| `test_ftl_service.py` | 22 | ✅ Done |
| `test_observer.py` | 19 | ✅ Done |
| `test_disruption_handler.py` | 30 | ⬜ Pending |
| `test_weekly_planner.py` | 34 | ⬜ Pending |
| `test_daily_validator.py` | 12 | ⬜ Pending |
| `test_e2e_flows.py` | 6 | ⬜ Pending |
| **Total** | **153** | |

---

## File: test_disruption_handler.py

### Shared fixtures
- `_make_leg(leg_id, dep_offset_hours, status, assigned_crew)` — returns `FlightLeg` with tz-aware departure
- `_make_crew(crew_id, role, status)` — returns `CrewMember`
- `_make_ftl(crew_id, status)` — returns `CrewFlightTimeLimitsState`
- `_make_flight_disrupted_event(leg_id, disruption_type, severity, assigned_crew)` — returns `FlightDisruptedEvent`
- `_make_crew_disrupted_event(crew_id, leg_id, severity, reason)` — returns `CrewDisruptedEvent`

### Patch targets (all in `crew_ops.services.disruption_handler.disruption_handler_service`)
- `get_flight_leg`
- `get_crew_member`
- `get_crew_duty_state`
- `get_all_crew_members`
- `get_all_crew_duty_states`
- `get_licenses_for_crew_member`
- `get_leave_records_for_crew`
- `get_all_licenses`
- `get_all_leave_records`
- `check_legality`
- `event_bus`
- `SessionLocal`
- `roster_repository`
- `disruption_repository`

### handle_flight_disrupted — 8 tests

| # | Name | Setup | Assert |
|---|------|-------|--------|
| 66 | `test_flight_disrupted_leg_not_found_returns_early` | `get_flight_leg=None` | `insert_proposal` not called, no event |
| 67 | `test_flight_disrupted_already_departed_returns_early` | leg dep = now-1h | no action |
| 68 | `test_flight_disrupted_cancellation_invalidates_roster` | CANCELLATION, 2 crew | `invalidate_roster_leg` called once |
| 69 | `test_flight_disrupted_cancellation_publishes_roster_modified_per_crew` | CANCELLATION, 2 crew | `event_bus.publish` called twice with `RosterModifiedEvent` |
| 70 | `test_flight_disrupted_route_change_creates_proposal` | ROUTE_CHANGE | `insert_proposal` called with `removed_crew_id=None` |
| 71 | `test_flight_disrupted_delay_checks_all_crew` | DELAY, 2 crew, legality fails | `insert_proposal` called for each crew that fails |
| 72 | `test_flight_disrupted_aircraft_swap_only_checks_pilots` | AIRCRAFT_SWAP, 1 pilot + 1 cabin | only pilot's `_check_and_propose` triggers proposal |
| 73 | `test_flight_disrupted_delay_no_proposal_when_still_legal` | DELAY, crew passes legality | `insert_proposal` not called |

### handle_crew_disrupted — 9 tests

| # | Name | Setup | Assert |
|---|------|-------|--------|
| 74 | `test_crew_disrupted_leg_not_found_returns_early` | `get_flight_leg=None` | no proposal |
| 75 | `test_crew_disrupted_already_departed_returns_early` | dep <= now | no proposal |
| 76 | `test_crew_disrupted_cancelled_leg_returns_early` | `leg.status=CANCELLED` | no proposal |
| 77 | `test_crew_disrupted_creates_proposal_with_candidates` | 1 legal candidate | `insert_proposal` called, `proposed_crew_id` set |
| 78 | `test_crew_disrupted_no_candidates_proposal_with_null_crew` | no legal candidates | `insert_proposal` called with `proposed_crew_id=None` |
| 79 | `test_crew_disrupted_crew_record_missing_falls_back_to_roster_role` | `get_crew_member=None`, roster has role | proposal created |
| 80 | `test_crew_disrupted_no_role_anywhere_returns_early` | `get_crew_member=None`, no roster assignment | no proposal |
| 81 | `test_crew_disrupted_duplicate_proposal_guard` | `pending_proposal_exists=True` | `insert_proposal` not called |
| 82 | `test_crew_disrupted_invalidates_assignment` | normal flow | `invalidate_assignment` called |

### reject_and_repropose — 5 tests

| # | Name | Setup | Assert |
|---|------|-------|--------|
| 83 | `test_reject_and_repropose_proposal_not_found` | `reject_proposal` returns `{}` | returns `{"error": ...}` |
| 84 | `test_reject_and_repropose_leg_no_longer_exists` | `get_flight_leg=None` | returns `{"status": "rejected", "new_proposal_id": None}` |
| 85 | `test_reject_and_repropose_excludes_already_proposed_crew` | `already_proposed={"C-002"}` | C-002 not in new proposal candidates |
| 86 | `test_reject_and_repropose_creates_new_proposal` | normal flow | `insert_proposal` called with `source=CONTROLLER_REJECT` |
| 87 | `test_reject_and_repropose_no_candidates_returns_none` | no remaining candidates | `next_candidate=None` |

### auto_resolve_low_severity — 7 tests

| # | Name | Setup | Assert |
|---|------|-------|--------|
| 88 | `test_auto_resolve_accepts_and_reassigns_when_still_legal` | 1 LOW proposal, candidate legal | `accept_proposal` + `replace_roster_crew_assignment` called |
| 89 | `test_auto_resolve_publishes_roster_modified_event` | same as 88 | `RosterModifiedEvent` published |
| 90 | `test_auto_resolve_skips_proposal_with_no_candidate` | `proposed_crew_id=None` | `accept_proposal` not called |
| 91 | `test_auto_resolve_skips_when_leg_or_crew_missing` | `get_flight_leg=None` | skipped silently |
| 92 | `test_auto_resolve_re_ranks_when_candidate_no_longer_legal` | candidate illegal, new candidate exists | UPDATE proposed_crew_id executed |
| 93 | `test_auto_resolve_escalates_to_medium_when_no_candidates` | candidate illegal, no new candidates | UPDATE severity=MEDIUM executed |
| 94 | `test_auto_resolve_returns_list_of_resolved_ids` | 1 resolved | returns `["PROP-001"]` |

### expire_stale_proposals — 1 test

| # | Name | Assert |
|---|------|--------|
| 95 | `test_expire_stale_proposals_calls_repository` | `expire_stale_proposals` on repo called + commit |

---

## File: test_weekly_planner.py

### Shared fixtures
- `_make_leg(leg_id, aircraft_type, dep_offset_days)` — FlightLeg with tz-aware datetimes
- `_make_crew(crew_id, role, status, home_base)` — CrewMember
- `_make_ftl(crew_id, status, airport, **kwargs)` — CrewFlightTimeLimitsState
- `_make_license(crew_id, aircraft_type)` — valid CrewLicense

### Patch targets (all in `crew_ops.services.weekly_planner.weekly_planner_service`)
- `get_all_crew_members`
- `get_all_crew_duty_states`
- `get_all_licenses`
- `get_all_leave_records`
- `get_legs_for_date_range`
- `get_flight_leg`
- `check_legality`
- `simulate_leg_assigned`
- `SessionLocal`
- `roster_repository`
- `reserve_repository`
- `event_bus`

### RosterPlanner.build — 9 tests

| # | Name | Assert |
|---|------|--------|
| 1 | `test_build_no_args_uses_today_and_settings_horizon` | `_run_build` called with `start=today` |
| 2 | `test_build_requested_by_only_uses_same_window` | same window as scheduler |
| 3 | `test_build_explicit_start_end` | exact start/end passed through |
| 4 | `test_build_end_before_start_raises` | `ValueError` raised |
| 5 | `test_build_empty_legs_skips_week` | `upsert_roster_leg` not called |
| 6 | `test_build_writes_roster_to_db` | `upsert_roster_leg` + `upsert_roster_crew_assignment` called |
| 7 | `test_build_advances_simulated_ftl_across_weeks` | `simulate_leg_assigned` called after week 1 |
| 8 | `test_build_inactive_crew_excluded` | inactive crew never in assignments |
| 9 | `test_build_multi_week_range` | `get_legs_for_date_range` called for each week |

### RosterPlanner.simulate_build — 3 tests

| # | Name | Assert |
|---|------|--------|
| 10 | `test_simulate_build_returns_assignments_and_failures` | dict has `assignments` and `failures` keys |
| 11 | `test_simulate_build_no_db_write` | `SessionLocal` never called |
| 12 | `test_simulate_build_failures_populated_when_legality_fails` | failures list non-empty |

### _pass1_assign_crew — 8 tests

| # | Name | Assert |
|---|------|--------|
| 13 | `test_pass1_assigns_correct_pilot_count` | B737 → 2 pilots |
| 14 | `test_pass1_assigns_correct_cabin_count` | B737 → 3 cabin |
| 15 | `test_pass1_picks_highest_scored_candidates` | top score wins |
| 16 | `test_pass1_skips_crew_with_no_ftl` | crew without FTL skipped |
| 17 | `test_pass1_skips_illegal_crew` | legality=False → not assigned |
| 18 | `test_pass1_updates_ftl_after_assignment` | `simulate_leg_assigned` called |
| 19 | `test_pass1_legs_sorted_by_departure` | earlier leg processed first |
| 20 | `test_pass1_partial_fill_when_not_enough_crew` | assigns what's available |

### _pass2_fill_reserve — 5 tests

| # | Name | Assert |
|---|------|--------|
| 21 | `test_pass2_creates_reserve_slots_for_unassigned_crew` | unassigned crew gets slot |
| 22 | `test_pass2_excludes_crew_already_on_duty` | assigned crew not in reserve |
| 23 | `test_pass2_excludes_unavailable_ftl_crew` | `status!=AVAILABLE` → no slot |
| 24 | `test_pass2_reserve_slot_fields` | `standby_start=06:00`, `callable_within=120` |
| 25 | `test_pass2_covers_all_dates_in_range` | 3-day range → slots for each day |

### _pass3_validate — 3 tests

| # | Name | Assert |
|---|------|--------|
| 26 | `test_pass3_returns_empty_when_all_legal` | `[]` returned |
| 27 | `test_pass3_returns_failure_for_illegal_assignment` | failure dict has `crew_id`, `leg_id`, `reason` |
| 28 | `test_pass3_skips_missing_crew_or_ftl` | no crash |

### _score_candidate / _fatigue_score — 6 tests

| # | Name | Assert |
|---|------|--------|
| 29 | `test_score_at_origin_airport_adds_40` | score includes +40 |
| 30 | `test_score_at_home_base_adds_20` | score includes +20 |
| 31 | `test_score_destination_is_home_adds_10` | score includes +10 |
| 32 | `test_score_away_from_home_both_ends_subtracts_10` | score includes -10 |
| 33 | `test_fatigue_score_caps_at_100` | extreme values → 100.0 |
| 34 | `test_fatigue_score_zero_for_fresh_crew` | all zeros → 0.0 |

---

## File: test_daily_validator.py

### Patch targets (all in `crew_ops.services.weekly_planner.weekly_planner_service`)
- `get_all_crew_members`
- `get_all_crew_duty_states`
- `get_all_licenses`
- `get_all_leave_records`
- `get_flight_leg`
- `check_legality`
- `event_bus`
- `SessionLocal`
- `roster_repository`

### DailyValidator.validate — 8 tests

| # | Name | Assert |
|---|------|--------|
| 35 | `test_validate_publishes_crew_disrupted_for_illegal_assignment` | `CrewDisruptedEvent` published |
| 36 | `test_validate_no_event_when_all_legal` | event_bus.publish not called |
| 37 | `test_validate_skips_missing_leg` | no crash, no event |
| 38 | `test_validate_skips_missing_crew` | skipped silently |
| 39 | `test_validate_skips_missing_ftl` | skipped silently |
| 40 | `test_validate_severity_critical_for_today` | `days_until=0` → `CRITICAL` |
| 41 | `test_validate_severity_low_for_far_future` | `days_until=30` → `LOW` |
| 42 | `test_validate_source_is_weekly_planner_validator` | `source == "WEEKLY_PLANNER_VALIDATOR"` |

### DailyValidator.on_roster_modified — 4 tests

| # | Name | Assert |
|---|------|--------|
| 43 | `test_on_roster_modified_triggers_validation_for_added_crew` | `_run_validation` called with added crew_id |
| 44 | `test_on_roster_modified_triggers_validation_for_removed_crew` | `_run_validation` called with removed crew_id |
| 45 | `test_on_roster_modified_both_crew_ids` | `_run_validation` called twice |
| 46 | `test_on_roster_modified_none_crew_ids_no_call` | `_run_validation` not called |

---

## File: test_e2e_flows.py

Uses real `EventBus` instance wired in-process. All clients and DB mocked.

| # | Scenario | Flow |
|---|----------|------|
| E1 | `test_e2e_observer_cancellation_to_roster_invalidated` | `poll(CANCELLATION)` → `FlightDisruptedEvent` → `handle_flight_disrupted` → `invalidate_roster_leg` |
| E2 | `test_e2e_observer_delay_ftl_breach_creates_proposal` | `poll(DELAY)` → `FlightDisruptedEvent` → `_check_and_propose` → legality fails → `insert_proposal` |
| E3 | `test_e2e_validator_illegal_assignment_creates_proposal` | `validate()` → `CrewDisruptedEvent` → `handle_crew_disrupted` → `insert_proposal` |
| E4 | `test_e2e_accept_proposal_updates_ftl` | `accept_proposal` → `RosterModifiedEvent` → `ftl_service.on_roster_modified` → removed=UNAVAILABLE, added=AVAILABLE |
| E5 | `test_e2e_leg_completed_updates_ftl` | `poll(landed)` → `LegCompletedEvent` → `ftl_service.on_leg_completed` → hours incremented, status=RESTING |
| E6 | `test_e2e_duplicate_proposal_guard` | validator fires twice for same crew+leg → only 1 proposal created |

---

## Implementation Order

1. `test_disruption_handler.py`
2. `test_weekly_planner.py`
3. `test_daily_validator.py`
4. `test_e2e_flows.py`
