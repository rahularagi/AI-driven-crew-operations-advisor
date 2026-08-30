# Setup — Follow In Exact Order

Do not skip steps or run them out of order. Each step lists the exact
command and the exact output you should see before moving to the next
step. If your output does not match, stop and fix it before continuing —
do not proceed with a broken step.

## Prerequisites

- Python 3.12 installed (check with `python3.12 --version`).
- A terminal open in the `langgraph_starter/` folder (this folder — the one
  containing `pyproject.toml`).

## Step 1 — Get a Gemini API key

1. Go to https://aistudio.google.com/apikey
2. Click "Create API key"
3. Copy the key (starts with `AIza...`)

Checkpoint: you have a key string copied to your clipboard.

## Step 2 — Create the virtual environment

```bash
python3.12 -m venv .venv
```

Checkpoint: a new `.venv/` folder now exists in this directory. No output
is expected from this command.

## Step 3 — Activate the virtual environment

```bash
source .venv/bin/activate
```

Checkpoint: your terminal prompt now starts with `(.venv)`.

Run this every time you open a new terminal to work on this project. If
your prompt does not show `(.venv)`, none of the following steps will
work correctly.

## Step 4 — Install dependencies

```bash
pip install --prefer-binary -e .
```

Checkpoint: the last line of output says
`Successfully installed ... langgraph-starter-0.1.0`.

Do not omit `--prefer-binary` — without it, this command can fail with a
`cryptography` build error on some machines/networks.

## Step 5 — Add your API key

```bash
cp .env.example .env
```

Then open `.env` in your editor and replace the placeholder line:

```
GOOGLE_API_KEY=your-google-ai-studio-key-here
```

with your real key from Step 1:

```
GOOGLE_API_KEY=AIza...your-actual-key...
```

Save the file. Leave the `GEMINI_MODEL=gemini-2.5-flash` line as is.

Checkpoint: `cat .env` shows your real key, not the placeholder text.

## Step 6 — Verify the connection

```bash
python -m langgraph_starter.connection
```

Checkpoint: output is exactly `OK`.

If you see an error instead:
- `GOOGLE_API_KEY is not set` → Step 5 was not done correctly. Re-check
  `.env`.
- `404 NOT_FOUND` mentioning the model name → the model in `.env` is no
  longer available. Go to Step 7 (troubleshooting) below, then come back
  here and re-run this command.
- Any other error → stop and share the exact error message before
  continuing.

## Step 7 — Run the example agent

```bash
python -m langgraph_starter.example_agent
```

Checkpoint: output ends with:

```
--- Final answer ---
Order 123 has already shipped and will be arriving in 2 days. Therefore, it cannot be cancelled.
```

(Exact wording may vary slightly since it's LLM-generated, but the
meaning — order 123 shipped, so it was not cancelled — must match.)

If this checkpoint matches, setup is complete and correct.

---

## Troubleshooting: model not found (404 error)

Only follow this section if Step 6 or Step 7 gave a `404 NOT_FOUND` error
about the model. Otherwise skip it entirely.

Gemini model names get deprecated over time. List the models your key
currently supports:

```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
from google import genai
client = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])
for m in client.models.list():
    print(m.name)
"
```

Pick a current flash model from the printed list (e.g.
`models/gemini-2.5-flash` → use `gemini-2.5-flash`), open `.env`, and set:

```
GEMINI_MODEL=gemini-2.5-flash
```

Then return to Step 6 and re-run the verification command.

---

## What each file is (reference, not setup steps)

| File | Purpose |
|---|---|
| `pyproject.toml` | Declares dependencies; makes `pip install -e .` work |
| `.env.example` | Template showing which variables are needed (safe to share) |
| `.env` | Your real key (never share, never commit — already gitignored) |
| `langgraph_starter/connection.py` | Sets up the Gemini client once, reused everywhere |
| `langgraph_starter/example_agent.py` | A complete working LangGraph agent example |
| `README.md` | Explains the LangGraph concepts used in the example |

## Extending this into a multi-stage agent

Once Step 7 passes, to add more stages (e.g. planner → executor →
verifier → healer for a QA pipeline):

1. Write each stage as its own function with the same shape as
   `call_model` in `example_agent.py` — takes the current state dict,
   returns a partial update to merge into it.
2. Register it: `builder.add_node("stage_name", stage_function)`.
3. Connect it: `add_edge("from_stage", "to_stage")` for a fixed transition,
   or `add_conditional_edges("from_stage", routing_function, {...})` when
   the next stage depends on what happened (e.g. verification passed vs.
   failed).
4. For a stage that needs to inspect a screenshot, call
   `ask_with_image(...)` from `connection.py` instead of `llm.invoke(...)`.
5. Run with `graph.invoke({...})`, or `graph.stream({...})` to see each
   stage's output as it happens.
