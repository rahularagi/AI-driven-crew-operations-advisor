from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from crew_ops_backend.db.database import check_database_connection
from crew_ops_backend.config.settings import settings

from crew_ops_backend.services.event_bus import event_bus
from crew_ops_backend.services.weekly_planner.weekly_planner_service import RosterPlanner, DailyValidator
from crew_ops_backend.services.disruption_handler.disruption_handler_service import DisruptionHandler
from crew_ops_backend.services.flight_time_limits.flight_time_limits_service import FlightTimeLimitsService
from crew_ops_backend.services.observer.observer_service import FlightObserver

from crew_ops_backend.models.events import (
    LegCompletedEvent, RosterModifiedEvent, FlightDisruptedEvent, CrewDisruptedEvent
)

from crew_ops_backend.api.routers import (
    planner_router, observer_router, crew_router, ftl_router, disruption_router
)

# ─── Push notification queue ────────────────────────────────────────────────────────────────────
# Drained on each POST /chat response
from crew_ops_backend.conversation.push_queue import _push_queue

# ─── Service instances ────────────────────────────────────────────────────────

roster_planner     = RosterPlanner()
daily_validator    = DailyValidator()
disruption_handler = DisruptionHandler()
ftl_service        = FlightTimeLimitsService()
flight_observer    = FlightObserver()

# ─── Event subscriptions ──────────────────────────────────────────────────────
# Only place in the codebase that connects services to each other.

event_bus.subscribe(FlightDisruptedEvent, disruption_handler.handle_flight_disrupted)
event_bus.subscribe(CrewDisruptedEvent,   disruption_handler.handle_crew_disrupted)
event_bus.subscribe(LegCompletedEvent,    ftl_service.on_leg_completed)
event_bus.subscribe(RosterModifiedEvent,  ftl_service.on_roster_modified)
event_bus.subscribe(RosterModifiedEvent,  daily_validator.on_roster_modified)

# ─── Scheduled jobs ───────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()

# Observer polling — every 5 minutes, polls all of today's active legs
scheduler.add_job(
    flight_observer.poll_all_today,
    CronTrigger(minute="*/5"),
    id="observer_poll",
)

# Job A — roster build every Sunday at 23:00
scheduler.add_job(
    roster_planner.build,
    CronTrigger(day_of_week="sun", hour=23, minute=0),
    id="roster_build",
)

# Job B — daily validation every morning at 03:00
scheduler.add_job(
    daily_validator.validate,
    CronTrigger(hour=3, minute=0),
    id="daily_validation",
)

# FTL proactive alert scan every 15 minutes
scheduler.add_job(
    ftl_service.run_proactive_alert_scan,
    CronTrigger(minute="*/15"),
    id="ftl_alert_scan",
)

# FTL rolling counter recalculation every midnight
scheduler.add_job(
    ftl_service.run_midnight_recalculation,
    CronTrigger(hour=0, minute=0),
    id="ftl_midnight_recalc",
)

# Proposal expiry — every night at 00:30
scheduler.add_job(
    disruption_handler.expire_stale_proposals,
    CronTrigger(hour=0, minute=30),
    id="expire_proposals",
)

# LOW severity auto-resolve — every 30 minutes
scheduler.add_job(
    disruption_handler.auto_resolve_low_severity,
    CronTrigger(minute="*/30"),
    id="auto_resolve_low",
)

# Push notification polling — every 60 seconds
def _push_pending_proposals() -> None:
    from crew_ops_backend.db.database import SessionLocal
    from crew_ops_backend.db.repositories import disruption_repository
    from crew_ops_backend.clients.flight_schedule_client import get_flight_leg
    from crew_ops_backend.clients.crew_profile_client import get_crew_member
    from crew_ops_backend.conversation.formatter import format_push_notification
    with SessionLocal() as session:
        proposals = disruption_repository.get_unpushed_proposals(session)
        for p in proposals:
            leg = get_flight_leg(p["leg_id"])
            # Build a minimal candidate list from the top proposed crew member
            candidates = []
            if p.get("proposed_crew_id"):
                crew = get_crew_member(p["proposed_crew_id"])
                if crew:
                    candidates = [{"crew_id": crew.crew_id, "full_name": crew.full_name, "role": crew.role}]
            msg = format_push_notification(p, leg.model_dump() if leg else {}, candidates)
            _push_queue.append(msg)
            disruption_repository.mark_proposal_pushed(session, p["proposal_id"])
        session.commit()

scheduler.add_job(
    _push_pending_proposals,
    IntervalTrigger(seconds=60),
    id="push_proposals",
)

scheduler.start()

# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="CrewOps",
    description="Airline crew operations management system",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(planner_router.router)
app.include_router(observer_router.router)
app.include_router(crew_router.router)
app.include_router(ftl_router.router)
app.include_router(disruption_router.router)

from crew_ops_backend.conversation.router import router as conversation_router
app.include_router(conversation_router)


@app.get("/health", tags=["Health"])
def health_check():
    database_is_connected = check_database_connection()
    return {
        "status": "ok" if database_is_connected else "degraded",
        "database": "connected" if database_is_connected else "unreachable",
        "mock_flags": {
            "crew_profile":     settings.mock_crew_profile,
            "license":          settings.mock_license,
            "flight_schedule":  settings.mock_flight_schedule,
            "flight_status":    settings.mock_flight_status,
            "ftl_state":        settings.mock_ftl_state,
            "reserve_schedule": settings.mock_reserve_schedule,
        },
        "scheduled_jobs": [job.id for job in scheduler.get_jobs()],
    }
