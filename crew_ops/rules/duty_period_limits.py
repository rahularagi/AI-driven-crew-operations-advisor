_MAX_DUTY_HOURS = {
    "night":     {1: 11.0, 2: 10.5, 3: 10.0, 4: 9.5},
    "morning":   {1: 13.0, 2: 12.5, 3: 12.0, 4: 11.5},
    "afternoon": {1: 12.0, 2: 11.5, 3: 11.0, 4: 10.5},
    "evening":   {1: 11.5, 2: 11.0, 3: 10.5, 4: 10.0},
}


def _duty_start_window(report_hour: int) -> str:
    if report_hour < 6:   return "night"
    if report_hour < 14:  return "morning"
    if report_hour < 18:  return "afternoon"
    return "evening"


def max_duty_hours(report_hour: int, sectors: int) -> float:
    window = _duty_start_window(report_hour)
    capped_sectors = min(max(sectors, 1), 4)
    return _MAX_DUTY_HOURS[window][capped_sectors]
