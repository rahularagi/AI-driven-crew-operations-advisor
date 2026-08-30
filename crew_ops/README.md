# CrewOps Advisor

Separate, self-contained package for AI-driven airline crew disruption handling.
Nothing here depends on `langgraph_starter`.

## Structure

```
crew_ops/
├── docs/                        # All design & implementation docs
│   ├── CREWOPS_ADVISOR.md       # Full system architecture & step-by-step build guide
│   ├── APPROACH_ANALYSIS.md     # Why each design decision was made
│   └── CREW_HANDLING_IMPLEMENTATION.md  # Roster planner implementation spec
│
├── models/                      # Dataclasses: CrewMember, CrewFTLState, Flight, Leg, etc.
├── rules/                       # Deterministic legality checker + FDP bracket table
├── data/                        # Seed data (25 crew, 15 legs, ftl_states, roster entries)
├── tools/                       # LangGraph @tool functions (find_crew, check_legality, etc.)
├── agent/                       # LangGraph graph wiring, state, nodes
├── ftl/                         # FTL service — reads/writes crew_ftl_state on duty events
├── roster/                      # Roster planner, validator, service (CRUD + change log)
├── notifications/               # Crew notification templates + sender
├── api/                         # FastAPI endpoints
├── config/                      # cost_config.json, planner_config.json
└── ui/                          # Streamlit dashboard
```

## Docs

Start with `docs/CREWOPS_ADVISOR.md` for the full system overview and build order.
