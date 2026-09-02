"""
Event Bus — decouples all services from each other.

Services never import or call each other directly.
They only publish events and subscribe to event types.

Usage:
    # subscribe (done once at startup in main.py)
    event_bus.subscribe(LegCompletedEvent, ftl_service.on_leg_completed)
    event_bus.subscribe(RosterModifiedEvent, ftl_service.on_roster_modified)
    event_bus.subscribe(RosterModifiedEvent, daily_validator.on_roster_modified)
    event_bus.subscribe(FlightDisruptedEvent, disruption_handler.handle_flight_disrupted)
    event_bus.subscribe(CrewDisruptedEvent, disruption_handler.handle_crew_disrupted)

    # publish (done inside each service)
    event_bus.publish(LegCompletedEvent(...))
    event_bus.publish(RosterModifiedEvent(...))
"""

from collections import defaultdict
from typing import Callable, Type
from pydantic import BaseModel


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[Type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: Type[BaseModel], handler: Callable) -> None:
        self._subscribers[event_type].append(handler)

    def publish(self, event: BaseModel) -> None:
        for handler in self._subscribers.get(type(event), []):
            handler(event)


event_bus = EventBus()
