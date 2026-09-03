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

    # ─── LLM provider ────────────────────────────────────────────────────────────────────
    use_llm:           bool = True       # True = LLM graph, False = rule-based graph
    llm_provider:      str = "openai"   # openai / anthropic / bedrock / gemini
    openai_api_key:    str = ""
    anthropic_api_key: str = ""
    bedrock_model_id:  str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    aws_region:        str = "us-east-1"
    gemini_api_key:    str = ""
    gemini_model:      str = "gemini-2.5-flash"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
