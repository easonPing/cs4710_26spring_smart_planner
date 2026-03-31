from datetime import datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone

from planner.models import Task, UserProfile
from planner.services.calendar_service import build_blocked_slots
from planner.services.candidate_selector import select_daily_candidates
from planner.services.scheduler_cp_sat import generate_daily_schedule


class SchedulerServiceTests(TestCase):
    def setUp(self):
        self.profile = UserProfile.objects.create(
            preferred_study_start=time(9, 0),
            preferred_study_end=time(21, 0),
            sleep_start=time(23, 30),
            sleep_end=time(7, 30),
        )

    def test_select_daily_candidates_orders_tasks(self):
        today = timezone.localdate()
        near = Task.objects.create(
            title="Near deadline",
            due_datetime=timezone.now() + timedelta(hours=4),
            estimated_minutes=60,
            priority="high",
            is_confirmed=True,
        )
        Task.objects.create(
            title="Later deadline",
            due_datetime=timezone.now() + timedelta(days=4),
            estimated_minutes=60,
            priority="medium",
            is_confirmed=True,
        )
        candidates = select_daily_candidates(today)
        self.assertEqual(candidates[0].id, near.id)

    def test_generate_daily_schedule_returns_blocks(self):
        today = timezone.localdate()
        task = Task.objects.create(
            title="Finish reading",
            due_datetime=timezone.now() + timedelta(days=1),
            estimated_minutes=60,
            priority="high",
            is_confirmed=True,
        )
        fixed_events = build_blocked_slots(today, self.profile)
        result = generate_daily_schedule(today, self.profile, [task], fixed_events)
        self.assertTrue(result["feasible"])
        self.assertGreaterEqual(len(result["blocks"]), 1)
