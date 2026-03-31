from datetime import timedelta

from dateutil.rrule import rrulestr
from icalendar import Calendar

from planner.utils import ensure_aware


def _normalize_datetime(value):
    if hasattr(value, "dt"):
        value = value.dt
    return ensure_aware(value)


def _event_duration(event):
    start = _normalize_datetime(event.get("dtstart"))
    end = _normalize_datetime(event.get("dtend"))
    if end:
        return end - start
    duration = event.get("duration")
    return duration.dt if duration else timedelta(hours=1)


def parse_ics(file_path):
    with open(file_path, "rb") as handle:
        payload = handle.read()
    calendar = Calendar.from_ical(payload)
    events = []
    for component in calendar.walk():
        if component.name != "VEVENT":
            continue
        start = _normalize_datetime(component.get("dtstart"))
        if not start:
            continue
        duration = _event_duration(component)
        events.append(
            {
                "title": str(component.get("summary", "Untitled event")),
                "start_datetime": start,
                "end_datetime": start + duration,
                "event_type": "class",
                "is_fixed": True,
                "source": "ics",
                "external_uid": str(component.get("uid", "")),
                "location": str(component.get("location", "")),
                "description": str(component.get("description", "")),
                "rrule": component.get("rrule"),
            }
        )
    return events


def _build_rrule_iterator(rule_text, dtstart):
    try:
        return rrulestr(rule_text, dtstart=dtstart)
    except ValueError as exc:
        message = str(exc)
        if "UNTIL values must be specified in UTC when DTSTART is timezone-aware" not in message:
            raise
        # Many university ICS exports store local UNTIL values without UTC even
        # when DTSTART is timezone-aware. Fall back to a floating DTSTART so
        # dateutil can expand the recurrence, then localize each occurrence.
        return rrulestr(rule_text, dtstart=dtstart.replace(tzinfo=None))


def expand_recurring_events(events, horizon_days=84):
    expanded = []
    for event in events:
        horizon_end = event["start_datetime"] + timedelta(days=horizon_days)
        rrule_value = event.get("rrule")
        if not rrule_value:
            expanded.append({key: value for key, value in event.items() if key != "rrule"})
            continue
        until_values = rrule_value.get("UNTIL") if hasattr(rrule_value, "get") else None
        if until_values:
            until_value = until_values[0] if isinstance(until_values, (list, tuple)) else until_values
            until_dt = _normalize_datetime(until_value)
            if until_dt:
                horizon_end = max(horizon_end, until_dt)
        rule_text = rrule_value.to_ical().decode("utf-8")
        duration = event["end_datetime"] - event["start_datetime"]
        for occurrence in _build_rrule_iterator(rule_text, event["start_datetime"]):
            occurrence = ensure_aware(occurrence)
            if occurrence > horizon_end:
                break
            expanded.append(
                {
                    "title": event["title"],
                    "start_datetime": occurrence,
                    "end_datetime": occurrence + duration,
                    "event_type": event["event_type"],
                    "is_fixed": event["is_fixed"],
                    "source": event["source"],
                    "external_uid": event["external_uid"],
                    "location": event["location"],
                    "description": event["description"],
                }
            )
    return expanded


def deduplicate_events(events):
    deduped = []
    seen = set()
    for event in events:
        key = (event.get("external_uid", ""), event["start_datetime"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped
