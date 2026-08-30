"""
Fetch live Air India scheduled flights from Aviationstack and save as raw_flights.json.

Usage:
    python -m crew_ops.data.fetch_flights
    python -m crew_ops.data.fetch_flights --status active
    python -m crew_ops.data.fetch_flights --limit 50
"""

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ACCESS_KEY = "5c5bc4bb14dbfd783a9926aa38a42d6a"
BASE_URL = "http://api.aviationstack.com/v1/flights"
DATA_DIR = Path(__file__).parent


def fetch(status: str = "scheduled", limit: int = 100) -> dict:
    url = f"{BASE_URL}?access_key={ACCESS_KEY}&airline_iata=AI&flight_status={status}&limit={limit}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


def to_leg(record: dict) -> dict:
    dep = record.get("departure") or {}
    arr = record.get("arrival") or {}
    flight = record.get("flight") or {}
    aircraft = record.get("aircraft") or {}

    origin = dep.get("iata", "")
    destination = arr.get("iata", "")
    flight_iata = flight.get("iata", "")
    flight_date = record.get("flight_date", "")

    # delay_minutes: prefer arrival delay, fall back to departure delay
    delay_minutes = arr.get("delay") or dep.get("delay") or 0

    # scheduled_arr may be null for some records
    sched_arr = arr.get("scheduled")
    est_arr = arr.get("estimated") or sched_arr

    return {
        "leg_id": f"{flight_iata}-{origin}-{destination}-{flight_date.replace('-', '')}",
        "flight_number": flight_iata,
        "flight_id": flight_iata,
        "origin_iata": origin,
        "origin_icao": dep.get("icao"),
        "destination_iata": destination,
        "destination_icao": arr.get("icao"),
        "scheduled_departure": dep.get("scheduled"),
        "scheduled_arrival": sched_arr,
        "estimated_arrival": est_arr,
        "actual_departure": dep.get("actual"),
        "actual_arrival": arr.get("actual"),
        "aircraft_type": aircraft.get("iata"),
        "aircraft_registration": aircraft.get("registration"),
        # lifecycle status mapped from Aviationstack values
        "status": _map_status(record.get("flight_status")),
        "delay_status": "DELAYED" if delay_minutes and delay_minutes > 0 else "ON_TIME",
        "delay_minutes": delay_minutes or 0,
        "assigned_crew": [],
    }


def _map_status(raw: str | None) -> str:
    return {
        "scheduled": "SCHEDULED",
        "active": "AIRBORNE",
        "landed": "LANDED",
        "cancelled": "CANCELLED",
        "diverted": "DIVERTED",
        "incident": "DIVERTED",
    }.get(raw or "", "SCHEDULED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", default="scheduled", choices=["scheduled", "active", "landed", "cancelled"])
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    print(f"Fetching Air India {args.status} flights (limit={args.limit})...")
    raw = fetch(args.status, args.limit)

    if "error" in raw:
        print(f"API error: {raw['error']}")
        return

    records = raw.get("data", [])
    print(f"  Got {len(records)} records from API")

    # Save raw response for reference
    raw_path = DATA_DIR / "raw_flights.json"
    raw_path.write_text(json.dumps(raw, indent=2))
    print(f"  Raw response → {raw_path}")

    # Map to our roster_leg schema
    legs = [to_leg(r) for r in records]

    legs_path = DATA_DIR / "legs.json"
    legs_path.write_text(json.dumps(legs, indent=2))
    print(f"  Mapped legs   → {legs_path}  ({len(legs)} legs)")

    # Summary
    statuses = {}
    for leg in legs:
        statuses[leg["status"]] = statuses.get(leg["status"], 0) + 1
    print(f"  Status breakdown: {statuses}")

    delayed = sum(1 for l in legs if l["delay_minutes"] > 0)
    print(f"  Delayed: {delayed}")

    fetched_at = datetime.now(timezone.utc).isoformat()
    meta = {"fetched_at": fetched_at, "status_filter": args.status, "count": len(legs)}
    (DATA_DIR / "fetch_meta.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
