from crew_ops_backend.config.settings import settings


def _get_llm():
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key, max_tokens=512)
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-3-5-sonnet-20241022", api_key=settings.anthropic_api_key, max_tokens=512)
    if settings.llm_provider == "bedrock":
        from langchain_aws import ChatBedrock
        return ChatBedrock(model_id=settings.bedrock_model_id, region_name=settings.aws_region,
                           model_kwargs={"max_tokens": 512})
    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=settings.gemini_model, google_api_key=settings.gemini_api_key, max_output_tokens=512)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")


def build_confirmation_package(action_type: str, action_args: dict, legality_result: dict) -> str:
    prompt = (
        f"The controller wants to: {action_type}\n"
        f"Details: {action_args}\n"
        f"Legality check result: {legality_result}\n\n"
        "Write a concise confirmation message (3-5 lines) that:\n"
        "1. States exactly what will change\n"
        "2. Names the crew members and flight affected\n"
        "3. Mentions any FTL or legality notes\n"
        '4. Ends with: "Confirm? [YES / NO]"\n\n'
        "Do not add any information not present in the details above."
    )
    return _get_llm().invoke(prompt).content


def format_response(mode: str, tool_result: dict | list, raw_message: str) -> str:
    prompt = (
        f"Mode: {mode}\n"
        f"Original request: {raw_message}\n"
        f"Result data: {tool_result}\n\n"
        "Write a concise plain-English response (2-4 lines) summarising the result.\n"
        "Do not invent data not present in the result."
    )
    return _get_llm().invoke(prompt).content


def format_push_notification(proposal: dict, leg: dict, candidates: list[dict]) -> str:
    prompt = (
        "A new disruption proposal requires your attention.\n"
        f"Proposal: {proposal}\n"
        f"Flight: {leg}\n"
        f"Top candidates: {candidates[:2]}\n\n"
        "Write a concise alert (3-5 lines) that:\n"
        "1. States the flight and departure time\n"
        "2. Names the disrupted crew member and reason\n"
        "3. Names the top replacement candidate with their FTL status\n"
        '4. Ends with: "Confirm? [YES / NO / SHOW MORE OPTIONS]"\n\n'
        "Do not add any information not present above."
    )
    return _get_llm().invoke(prompt).content
