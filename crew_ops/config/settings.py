from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ─── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql://crew_ops_user:crew_ops_password@localhost:5432/crew_ops"

    # ─── Mock flags ───────────────────────────────────────────────────────────
    # True  = read from database (seeded from mock data)
    # False = call real external API
    mock_crew_profile: bool = True
    mock_license: bool = True
    mock_flight_schedule: bool = True
    mock_flight_status: bool = True
    mock_ftl_state: bool = True
    mock_reserve_schedule: bool = True

    # ─── Roster planning ──────────────────────────────────────────────────────
    roster_planning_weeks: int = 7          # how many weeks ahead the planner builds

    # ─── Real API credentials (only used when mock flag is False) ─────────────
    aviationstack_api_key: str = ""
    hrms_api_base_url: str = ""
    hrms_api_key: str = ""
    google_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
