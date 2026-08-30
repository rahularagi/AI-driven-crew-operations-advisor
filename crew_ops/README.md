# CrewOps

Airline crew operations management system.

---

## Prerequisites

Make sure these are installed on your machine before starting.

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | https://python.org |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker | latest | https://docker.com |
| Docker Compose | latest | included with Docker Desktop |

---

## Step 1 — Clone / open the project

```bash
cd crew_ops
```

All commands from here are run inside the `crew_ops` folder.

---

## Step 2 — Create environment file

```bash
cp .env.example .env
```

The default values in `.env` work out of the box for local development.
No changes needed to start.

---

## Step 3 — Install Python dependencies

```bash
uv sync
```

This creates a `.venv` folder inside `crew_ops` and installs all dependencies.

---

## Step 4 — Start PostgreSQL

```bash
docker-compose up -d
```

This starts a PostgreSQL container with:
- Host: `localhost`
- Port: `5432`
- Database: `crew_ops`
- User: `crew_ops_user`
- Password: `crew_ops_password`

Wait a few seconds for PostgreSQL to be ready. Check it is healthy:

```bash
docker-compose ps
```

You should see `crew_ops_postgres` with status `healthy`.

---

## Step 5 — Load mock data into database

This runs the initial pipeline that seeds all mock data into PostgreSQL.
Run this once after starting PostgreSQL for the first time.

```bash
uv run python -m crew_ops.data.pipeline.run_all
```

Expected output:
```
Checking database connection...
Database connected.

Loading crew members...     25 records
Loading licenses...         21 records
Loading FTL states...       25 records
Loading leave records...    5 records
Loading reserve schedule... 10 records
Loading flight legs...      15 records

All mock data loaded successfully.
```

---

## Step 6 — Start the API server

```bash
uv run uvicorn crew_ops.api.main:app --reload --port 8000
```

---

## Step 7 — Verify everything is working

**Health check:**
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "database": "connected",
  "mock_flags": {
    "crew_profile": true,
    "license": true,
    "flight_schedule": true,
    "flight_status": true,
    "ftl_state": true,
    "reserve_schedule": true
  }
}
```

**API docs (interactive):**
```
http://localhost:8000/docs
```

---

## Switching from mock to real API

Each data source has its own flag in `.env`.
You can switch them independently — for example use real flight status but keep crew data as mock.

```env
# .env

MOCK_CREW_PROFILE=False       ← now calls real SAP HR / Workday API
MOCK_LICENSE=True             ← still using mock
MOCK_FLIGHT_SCHEDULE=True     ← still using mock
MOCK_FLIGHT_STATUS=False      ← now calls real Aviationstack API
MOCK_FTL_STATE=True           ← always internal, this flag has no effect
MOCK_RESERVE_SCHEDULE=True    ← still using mock
```

When switching to real APIs, also add the credentials:
```env
AVIATIONSTACK_API_KEY=your_real_key
HRMS_API_BASE_URL=https://your-hrms.internal
HRMS_API_KEY=your_real_key
```

---

## Project structure

```
crew_ops/
├── api/                    FastAPI application
├── clients/                Swap point — mock vs real API
├── config/                 Settings and flags
├── data/
│   ├── mock/               Raw mock data (never changes)
│   └── pipeline/           One-time database seeding scripts
├── db/
│   ├── database.py         PostgreSQL connection
│   └── repositories/       Database read/write per data type
├── docker/
│   └── init.sql            Database schema
├── models/                 Pydantic data models
├── docker-compose.yml      PostgreSQL container
├── pyproject.toml          Project dependencies
└── .env                    Environment variables (gitignored)
```

---

## Stopping the database

```bash
docker-compose down
```

To also delete all data:
```bash
docker-compose down -v
```

---

## Re-seeding the database

If you want to reset and reload all mock data:

```bash
docker-compose down -v
docker-compose up -d
uv run python -m crew_ops.data.pipeline.run_all
```
