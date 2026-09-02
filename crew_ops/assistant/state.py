# state.py
# This file defines the shape of the data that flows through the LangGraph graph.
# Every node (agent, tools, synthesizer) reads from and writes to this state.
# Think of it as the shared memory for one conversation turn.

from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


def _last_value(current, update):
    # Reducer that always keeps the latest value — replaces instead of appending.
    # Used for final_answer so synthesizer overwrites, not accumulates.
    return update


class AssistantState(TypedDict):
    # The conversation — add_messages handles append-only updates
    messages: Annotated[list, add_messages]

    # Raw structured data collected by tools — synthesizer reads this
    tool_results: dict[str, Any]

    # Final plain-English answer written by synthesizer.
    # Annotated with _last_value so it stays a string, never becomes a list.
    final_answer: Annotated[str, _last_value]