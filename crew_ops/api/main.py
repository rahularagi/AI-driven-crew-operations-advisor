from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from crew_ops.db.database import check_database_connection
from crew_ops.config.settings import settings

from crew_ops.services.event_bus import event_bus
from crew_ops.services.weekly_planner.weekly_planner_service import RosterPlanner, DailyValidator
from crew_ops.services.disruption_handler.disruption_handler_service import DisruptionHandler
from crew_ops.services.flight_time_limits.flight_time_limits_service import FlightTimeLimitsService

from crew_ops.models.events import (
    LegCompletedEvent, RosterModifiedEvent, FlightDisruptedEvent, CrewDisruptedEvent
)

from crew_ops.api.routers import (
    planner_router, observer_router, crew_router, ftl_router
)

from crew_ops.api.routers.assistant_router import router as assistant_router

# ─── Service instances ────────────────────────────────────────────────────────

roster_planner     = RosterPlanner()
daily_validator    = DailyValidator()
disruption_handler = DisruptionHandler()
ftl_service        = FlightTimeLimitsService()

# ─── Event subscriptions ──────────────────────────────────────────────────────
# Only place in the codebase that connects services to each other.

event_bus.subscribe(FlightDisruptedEvent, disruption_handler.handle_flight_disrupted)
event_bus.subscribe(CrewDisruptedEvent,   disruption_handler.handle_crew_disrupted)
event_bus.subscribe(LegCompletedEvent,    ftl_service.on_leg_completed)
event_bus.subscribe(RosterModifiedEvent,  ftl_service.on_roster_modified)
event_bus.subscribe(RosterModifiedEvent,  daily_validator.on_roster_modified)

# ─── Scheduled jobs ───────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()

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

scheduler.start()

# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="CrewOps",
    description="Airline crew operations management system",
    version="0.1.0",
)

app.include_router(planner_router.router)
app.include_router(observer_router.router)
app.include_router(crew_router.router)
app.include_router(ftl_router.router)
app.include_router(assistant_router)

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
