import json
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def normalize_title(text):
    text = re.sub(r"\s+", " ", (text or "").strip().lower())
    return re.sub(r"[^a-z0-9 ]+", "", text)


def chunk_text(text, max_chars=4000):
    if not text:
        return []
    chunks = []
    current = []
    current_len = 0
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    for paragraph in paragraphs:
        if current and current_len + len(paragraph) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len += len(paragraph) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def round_to_slot(dt, slot_minutes=30):
    minute_bucket = (dt.minute // slot_minutes) * slot_minutes
    return dt.replace(minute=minute_bucket, second=0, microsecond=0)


def round_up_to_slot(dt, slot_minutes=30):
    rounded = round_to_slot(dt, slot_minutes=slot_minutes)
    if rounded < dt:
        rounded += timedelta(minutes=slot_minutes)
    return rounded


def now_local():
    return timezone.localtime()


def local_timezone():
    return ZoneInfo(settings.TIME_ZONE)


def ensure_aware(value):
    if value is None:
        return None
    if timezone.is_aware(value):
        return timezone.localtime(value)
    return timezone.make_aware(value, local_timezone())


def combine_date_time(target_date, target_time):
    if isinstance(target_time, str):
        target_time = time.fromisoformat(target_time)
    naive = datetime.combine(target_date, target_time)
    return timezone.make_aware(naive, local_timezone())


def daterange(start_date, end_date):
    day_count = (end_date - start_date).days + 1
    for offset in range(day_count):
        yield start_date + timedelta(days=offset)


def safe_json_loads(value, default=None):
    if not value:
        return {} if default is None else default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {} if default is None else default


def parse_time(value, fallback):
    if isinstance(value, time):
        return value
    if not value:
        return fallback
    return time.fromisoformat(str(value))
