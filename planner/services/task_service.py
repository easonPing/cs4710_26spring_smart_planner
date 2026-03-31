from django.db.models import F

from planner.models import Task


def create_manual_task(data):
    task = Task.objects.create(
        source="manual",
        needs_review=False,
        is_confirmed=True,
        **data,
    )
    return task


def update_task(task_id, data):
    task = Task.objects.get(pk=task_id)
    for key, value in data.items():
        setattr(task, key, value)
    task.save()
    return task


def mark_task_done(task_id):
    task = Task.objects.get(pk=task_id)
    task.status = "done"
    task.save(update_fields=["status", "updated_at"])
    return task


def get_open_tasks():
    return Task.objects.exclude(status__in=["done", "cancelled"]).filter(is_confirmed=True)


def get_tasks_needing_review():
    return Task.objects.filter(needs_review=True).order_by("due_datetime", "title")


def increment_carry_over(task_queryset):
    task_queryset.update(carry_over_count=F("carry_over_count") + 1)
