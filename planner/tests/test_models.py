from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from planner.models import ScheduleBlock, Task


class TaskModelTests(TestCase):
    def test_is_overdue(self):
        task = Task.objects.create(
            title="Past Due Task",
            due_datetime=timezone.now() - timedelta(hours=1),
            estimated_minutes=60,
        )
        self.assertTrue(task.is_overdue())

    def test_urgency_score_favors_deadlines(self):
        near_task = Task.objects.create(
            title="Near",
            due_datetime=timezone.now() + timedelta(hours=2),
            estimated_minutes=60,
            priority="medium",
        )
        later_task = Task.objects.create(
            title="Later",
            due_datetime=timezone.now() + timedelta(days=5),
            estimated_minutes=60,
            priority="medium",
        )
        self.assertGreater(near_task.urgency_score(), later_task.urgency_score())


class ScheduleBlockTests(TestCase):
    def test_duration_minutes(self):
        now = timezone.now()
        block = ScheduleBlock(
            schedule_date=timezone.localdate(),
            title="Focus Block",
            start_datetime=now,
            end_datetime=now + timedelta(minutes=90),
        )
        self.assertEqual(block.duration_minutes(), 90)
