from datetime import datetime, timedelta

from django.utils import timezone

from planner.models import Task


def score_task_for_daily(task, now):
    score = task.urgency_score(now=now)
    if task.carry_over_count:
        score += task.carry_over_count * 10
    if task.remaining_minutes <= 30:
        score += 5
    return score


def select_daily_candidates(date, now=None, max_tasks=8):
    now = now or timezone.now()
    horizon_end = timezone.make_aware(
        datetime.combine(date + timedelta(days=7), datetime.max.time().replace(microsecond=0)),
        timezone.get_current_timezone(),
    )
    base_queryset = Task.objects.exclude(status__in=["done", "cancelled"]).filter(is_confirmed=True)
    tasks = base_queryset.filter(due_datetime__isnull=True) | base_queryset.filter(due_datetime__lte=horizon_end)
    task_list = list(tasks.distinct())
    ranked = sorted(task_list, key=lambda task: score_task_for_daily(task, now), reverse=True)
    return ranked[:max_tasks]


def select_weekly_candidates(start_date, days=7):
    now = timezone.now()
    return select_daily_candidates(start_date, now=now, max_tasks=20)
