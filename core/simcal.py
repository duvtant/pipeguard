"""Simulated calendar. sim_day 0 is Monday Oct 5, 2026 (same as scenario.json)."""
from datetime import date, timedelta

CALENDAR_START = date(2026, 10, 5)


def day_date(day: int) -> date:
    return CALENDAR_START + timedelta(days=day)


def weekday(day: int) -> str:
    return day_date(day).strftime("%A")


def today_text(day: int) -> str:
    """'Tuesday, October 6': what the voice agent gets as sim_today."""
    d = day_date(day)
    return f"{d.strftime('%A, %B')} {d.day}"
