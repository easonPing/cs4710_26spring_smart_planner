from datetime import time, timedelta

from django.conf import settings

from planner.models import CalendarEvent
from planner.utils import combine_date_time

from .ics_parser import deduplicate_events, expand_recurring_events, parse_ics


def import_ics_events(user, file_path):
    parsed = parse_ics(file_path)
    expanded = expand_recurring_events(parsed, horizon_days=settings.RECURRING_HORIZON_DAYS)
    events = deduplicate_events(expanded)
    return save_calendar_events(events)


def save_calendar_events(events):
    saved = []
    for event_data in events:
        event, _ = CalendarEvent.objects.update_or_create(
            external_uid=event_data.get("external_uid", ""),
            start_datetime=event_data["start_datetime"],
            defaults={
                "title": event_data["title"],
                "end_datetime": event_data["end_datetime"],
                "event_type": event_data.get("event_type", "class"),
                "is_fixed": event_data.get("is_fixed", True),
                "source": event_data.get("source", "ics"),
                "location": event_data.get("location", ""),
                "description": event_data.get("description", ""),
            },
        )
        saved.append(event)
    return saved


def get_fixed_events_for_date(date):
    return CalendarEvent.objects.filter(start_datetime__date=date, is_fixed=True).order_by("start_datetime")


def build_blocked_slots(date, profile):
    blocked = [
        {
            "start": event.start_datetime,
            "end": event.end_datetime,
            "block_type": event.event_type,
            "title": event.title,
        }
        for event in get_fixed_events_for_date(date)
    ]
    day_start = combine_date_time(date, time(0, 0))
    day_end = day_start + timedelta(days=1)
    sleep_start = combine_date_time(date, profile.sleep_start)
    sleep_end = combine_date_time(date, profile.sleep_end)
    if profile.sleep_end <= profile.sleep_start:
        blocked.append(
            {
                "start": day_start,
                "end": sleep_end,
                "block_type": "sleep",
                "title": "Sleep",
            }
        )
        blocked.append(
            {
                "start": sleep_start,
                "end": day_end,
                "block_type": "sleep",
                "title": "Sleep",
            }
        )
    else:
        blocked.append(
            {
                "start": sleep_start,
                "end": sleep_end,
                "block_type": "sleep",
                "title": "Sleep",
            }
        )
    for meal_name, start_time, end_time in profile.get_meal_windows():
        blocked.append(
            {
                "start": combine_date_time(date, start_time),
                "end": combine_date_time(date, end_time),
                "block_type": "meal",
                "title": meal_name.title(),
            }
        )
    return blocked
