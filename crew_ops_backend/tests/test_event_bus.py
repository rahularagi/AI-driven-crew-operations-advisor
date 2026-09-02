"""Tests for services/event_bus.py"""
from crew_ops.services.event_bus import EventBus
from crew_ops.models.events import (
    LegCompletedEvent, RosterModifiedEvent, CrewDisruptedEvent
)
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc)


def _leg_completed():
    return LegCompletedEvent(
        leg_id="L-001", actual_arrival=_now(),
        destination="VIDP", crew=["C-001"], delay_minutes=0,
    )


def _roster_modified():
    return RosterModifiedEvent(
        leg_id="L-001", removed_crew_id="C-001",
        added_crew_id="C-002", modified_at=_now(),
    )


# ─── 143 ──────────────────────────────────────────────────────────────────────

def test_subscribe_and_publish_single_handler():
    bus = EventBus()
    received = []
    bus.subscribe(LegCompletedEvent, lambda e: received.append(e))
    event = _leg_completed()
    bus.publish(event)
    assert len(received) == 1
    assert received[0] is event


# ─── 144 ──────────────────────────────────────────────────────────────────────

def test_multiple_handlers_same_event_type():
    bus = EventBus()
    calls_a, calls_b = [], []
    bus.subscribe(LegCompletedEvent, lambda e: calls_a.append(e))
    bus.subscribe(LegCompletedEvent, lambda e: calls_b.append(e))
    bus.publish(_leg_completed())
    assert len(calls_a) == 1
    assert len(calls_b) == 1


# ─── 145 ──────────────────────────────────────────────────────────────────────

def test_publish_unknown_event_type_no_crash():
    bus = EventBus()
    # no subscribers registered — must not raise
    bus.publish(_leg_completed())


# ─── 146 ──────────────────────────────────────────────────────────────────────

def test_handler_receives_correct_event_instance():
    bus = EventBus()
    received = []
    bus.subscribe(RosterModifiedEvent, lambda e: received.append(e))
    event = _roster_modified()
    bus.publish(event)
    assert received[0].leg_id == "L-001"
    assert received[0].removed_crew_id == "C-001"


# ─── 147 ──────────────────────────────────────────────────────────────────────

def test_different_event_types_isolated():
    bus = EventBus()
    leg_calls, roster_calls = [], []
    bus.subscribe(LegCompletedEvent,  lambda e: leg_calls.append(e))
    bus.subscribe(RosterModifiedEvent, lambda e: roster_calls.append(e))
    bus.publish(_leg_completed())
    assert len(leg_calls) == 1
    assert len(roster_calls) == 0
