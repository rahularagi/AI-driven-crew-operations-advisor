_REQUIREMENTS = {
    # aircraft_type → (pilots, cabin)
    # pilots: always 2 — 1 Captain + 1 First Officer, fixed by regulation
    # cabin: minimum per aircraft exits — A320/B737 have 4 exits, B787 has 8
    "A320": (2, 3),
    "B737": (2, 3),
    "B787": (2, 6),
}


def required_pilots(aircraft_type: str) -> int:
    return _REQUIREMENTS.get(aircraft_type, (2, 3))[0]


def required_cabin(aircraft_type: str) -> int:
    return _REQUIREMENTS.get(aircraft_type, (2, 3))[1]
