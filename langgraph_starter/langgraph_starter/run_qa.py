import yaml
import logging
import pathlib
from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
from pydantic import BaseModel
from langgraph_starter.graph import graph
from langgraph_starter.state import initial_state
from langgraph_starter.tools.browser_tools import close_browser

app = FastAPI()

_agents_path = pathlib.Path(__file__).parent.parent / "agents.yaml"
AGENTS: dict = yaml.safe_load(_agents_path.read_text())


class QARequest(BaseModel):
    agent: str
    base_url: str
    credentials: dict = {}      # {"email": "...", "password": "..."}
    scenarios: list[str]        # list of plain English test descriptions


@app.post("/qa/run")
def run_qa(request: QARequest):
    if request.agent not in AGENTS:
        return {"error": f"Unknown agent '{request.agent}'. Registered: {list(AGENTS.keys())}"}

    agent_prompt = AGENTS[request.agent]["prompt"]

    result = graph.invoke(initial_state(
        agent=request.agent,
        agent_prompt=agent_prompt,
        base_url=request.base_url,
        credentials=request.credentials,
        scenarios=request.scenarios,
    ))
    close_browser()
    return {
        "agent": request.agent,
        "total_scenarios": len(result["all_reports"]),
        "reports": result["all_reports"],
    }
