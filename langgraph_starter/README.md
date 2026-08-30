# LangGraph + Gemini Starter

Minimal setup for a LangGraph agent connected to Gemini, plus one complete
working example of a multi-stage, tool-calling agent.

## Setup

```bash
cd langgraph_starter
python -m venv .venv && source .venv/bin/activate
pip install -e .

cp .env.example .env
# edit .env and paste your key from https://aistudio.google.com/apikey
```

## Files

- `langgraph_starter/connection.py` — sets up the Gemini LLM client (`get_llm()`)
  and a helper for sending an image + prompt (`ask_with_image()`), used for any
  vision-based node later.
- `langgraph_starter/example_agent.py` — a complete, runnable LangGraph agent
  with tool calling. Start here.

## Run the example

```bash
python -m langgraph_starter.example_agent
```

This runs an agent that can look up and cancel a fake order, calling tools as
needed and looping until it has a final answer.

## Core LangGraph concepts (in the order you'll use them)

**State** — the data passed between every step of the graph. The simplest
built-in state is `MessagesState`, which is just `{"messages": [...]}`. Nodes
receive the current state and return a partial update; for `messages`
specifically, LangGraph appends rather than overwrites.

**Tools** — plain Python functions decorated with `@tool`. The function's
docstring is sent to the LLM as the tool's description — the LLM decides
when and how to call it based on that description and the argument types.

**Nodes** — functions that do one step of work: read state in, return an
update. In the example, `call_model` (asks the LLM what to do) and
`ToolNode` (a prebuilt node that executes whatever tool calls the LLM
requested) are the two nodes.

**Edges** — fixed transitions (`add_edge("tools", "agent")`: always go back
to the agent after tools run).

**Conditional edges** — branching logic based on current state
(`add_conditional_edges("agent", route_after_agent, {...})`: if the LLM's
last message requested a tool call, go run it; otherwise stop).

**Compiling** — `builder.compile()` turns the node/edge definitions into a
runnable graph. `graph.invoke(initial_state)` runs it to completion;
`graph.stream(initial_state)` yields intermediate steps if you want to show
progress live.

## The pattern this example implements (ReAct loop)

```
START -> agent -> [LLM requests a tool?] -> yes -> tools -> back to agent
                                          -> no  -> END
```

This is the same loop you'd extend for a multi-stage agent (e.g. a QA agent
with planner -> executor -> verifier -> healer stages) — each stage is just
another node, and conditional edges decide which stage runs next based on
what happened in the previous one.

## Using Gemini's vision input directly

For any node that needs to look at a screenshot (not just call tools), use
`ask_with_image` from `connection.py`:

```python
from langgraph_starter.connection import ask_with_image

result = ask_with_image(
    "Does this UI have any layout or contrast issues?",
    "screenshot.png",
)
```

That result can then feed into your graph's state as a normal message.
