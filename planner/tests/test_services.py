import base64
import json
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from icalendar.prop import vRecur

from planner.models import Task, UserProfile
from planner.services.calendar_service import build_blocked_slots, filter_imported_events, summarize_course_meetings
from planner.services.candidate_selector import select_daily_candidates
from planner.services.codex_auth import CodexAuthManager
from planner.services.codex_provider import CodexProvider, CodexProviderError
from planner.services.ics_parser import expand_recurring_events
from planner.services.summary_service import generate_summary
from planner.services.scheduler_cp_sat import generate_daily_schedule
from planner.services.task_extractor import refine_task_candidates


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

    def test_expand_recurring_events_accepts_local_until_with_aware_dtstart(self):
        start = timezone.now().replace(hour=11, minute=0, second=0, microsecond=0)
        event = {
            "title": "Weekly Lecture",
            "start_datetime": start,
            "end_datetime": start + timedelta(hours=1),
            "event_type": "class",
            "is_fixed": True,
            "source": "ics",
            "external_uid": "lecture-1",
            "location": "",
            "description": "",
            "rrule": vRecur.from_ical("FREQ=WEEKLY;COUNT=3;UNTIL=20260429T235959"),
        }

        expanded = expand_recurring_events([event], horizon_days=60)

        self.assertEqual(len(expanded), 3)
        self.assertTrue(all(item["start_datetime"].tzinfo is not None for item in expanded))

    def test_filter_imported_events_drops_out_of_hours_and_all_day_events(self):
        tz = timezone.get_current_timezone()
        date = timezone.localdate()
        kept = {
            "title": "CS 6770",
            "start_datetime": timezone.make_aware(datetime.combine(date, time(14, 0)), tz),
            "end_datetime": timezone.make_aware(datetime.combine(date, time(15, 15)), tz),
            "event_type": "class",
            "is_fixed": True,
            "source": "ics",
            "external_uid": "1",
            "location": "",
            "description": "",
        }
        late = {
            **kept,
            "title": "Night Seminar",
            "start_datetime": timezone.make_aware(datetime.combine(date, time(19, 30)), tz),
            "end_datetime": timezone.make_aware(datetime.combine(date, time(20, 30)), tz),
            "external_uid": "2",
        }
        all_day = {
            **kept,
            "title": "CS 4993",
            "start_datetime": timezone.make_aware(datetime.combine(date, time(0, 0)), tz),
            "end_datetime": timezone.make_aware(datetime.combine(date, time(0, 0)), tz),
            "external_uid": "3",
        }

        filtered = filter_imported_events([kept, late, all_day])

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "CS 6770")

    def test_summarize_course_meetings_groups_by_title(self):
        tz = timezone.get_current_timezone()
        date = timezone.localdate()
        monday = timezone.make_aware(datetime.combine(date, time(14, 0)), tz)
        wednesday = monday + timedelta(days=2)
        event_one = type(
            "Event",
            (),
            {"title": "CS 6770", "start_datetime": monday, "end_datetime": monday + timedelta(hours=1, minutes=15)},
        )
        event_two = type(
            "Event",
            (),
            {"title": "CS 6770", "start_datetime": wednesday, "end_datetime": wednesday + timedelta(hours=1, minutes=15)},
        )

        summary = summarize_course_meetings([event_one, event_two])

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["title"], "CS 6770")
        self.assertEqual(len(summary[0]["times"]), 2)


class CodexAuthManagerTests(TestCase):
    @staticmethod
    def _jwt(payload):
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
        return f"header.{encoded}.signature"

    def test_is_expired_uses_nested_token_expiry(self):
        expired = {
            "tokens": {
                "access_token": self._jwt(
                    {"exp": int((timezone.now() - timedelta(minutes=10)).timestamp())}
                )
            }
        }
        fresh = {
            "tokens": {
                "access_token": self._jwt(
                    {"exp": int((timezone.now() + timedelta(hours=1)).timestamp())}
                )
            }
        }

        self.assertTrue(CodexAuthManager.is_expired(expired))
        self.assertFalse(CodexAuthManager.is_expired(fresh))

    def test_summarize_credentials_reads_email_and_plan(self):
        credentials = {
            "auth_mode": "chatgpt",
            "last_refresh": "2026-03-30T18:14:02.367150200Z",
            "tokens": {
                "account_id": "acct-123",
                "id_token": self._jwt(
                    {
                        "email": "student@example.edu",
                        "exp": int((timezone.now() + timedelta(hours=1)).timestamp()),
                        "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"},
                    }
                ),
            },
        }

        summary = CodexAuthManager.summarize_credentials(credentials)

        self.assertEqual(summary["email"], "student@example.edu")
        self.assertEqual(summary["plan_type"], "plus")
        self.assertEqual(summary["account_id"], "acct-123")
        self.assertEqual(summary["auth_mode"], "chatgpt")

    @patch("planner.services.codex_auth.urllib.request.urlopen")
    def test_refresh_credentials_updates_tokens(self, mock_urlopen):
        class MockResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "access_token": self._jwt(
                            {"exp": int((timezone.now() + timedelta(hours=3)).timestamp()), "client_id": "app_123"}
                        ),
                        "refresh_token": "new-refresh",
                    }
                ).encode("utf-8")

            def __init__(self, jwt_builder):
                self._jwt = jwt_builder

        mock_urlopen.return_value = MockResponse(self._jwt)
        credentials = {
            "tokens": {
                "access_token": self._jwt(
                    {"exp": int((timezone.now() - timedelta(minutes=1)).timestamp()), "client_id": "app_123"}
                ),
                "refresh_token": "old-refresh",
            }
        }

        refreshed = CodexAuthManager.refresh_credentials(credentials)

        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed["tokens"]["refresh_token"], "new-refresh")
        self.assertFalse(CodexAuthManager.is_expired(refreshed))


class CodexPriorityTests(TestCase):
    @patch.object(CodexProvider, "call_codex_json")
    def test_extract_tasks_prefers_codex_json(self, mock_call_codex_json):
        mock_call_codex_json.return_value = {
            "items": [
                {
                    "title": "Project Milestone",
                    "course_name": "CS4710",
                    "due_datetime": "2026-04-05T23:59:00-04:00",
                    "estimated_minutes": 180,
                    "priority": "high",
                    "category": "assignment",
                    "confidence": 0.92,
                    "raw_excerpt": "Project Milestone due April 5 at 11:59 PM",
                }
            ]
        }

        items = CodexProvider().extract_tasks(["Project Milestone due April 5 at 11:59 PM"], document_name="syllabus.pdf")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Project Milestone")
        self.assertEqual(items[0]["document_name"], "syllabus.pdf")
        mock_call_codex_json.assert_called_once()

    @patch.object(CodexProvider, "call_codex_json")
    def test_parse_patch_prefers_codex_json(self, mock_call_codex_json):
        mock_call_codex_json.return_value = {
            "trigger_type": "change_estimate",
            "payload": {"task_title": "Homework 3", "estimated_minutes": 90},
        }

        patch_payload = CodexProvider().parse_patch("Homework 3 now needs 90 minutes.")

        self.assertEqual(patch_payload["trigger_type"], "change_estimate")
        self.assertEqual(patch_payload["payload"]["estimated_minutes"], 90)
        mock_call_codex_json.assert_called_once()

    @patch.object(CodexProvider, "call_codex_text")
    def test_generate_summary_uses_codex_when_available(self, mock_call_codex_text):
        mock_call_codex_text.return_value = "Moved one block later and kept the rest stable."

        summary = generate_summary(
            [{"task_id": 1, "start_datetime": "2026-04-01T10:00:00-04:00"}],
            [{"task_id": 1, "start_datetime": "2026-04-01T11:00:00-04:00"}],
            "replan",
        )

        self.assertEqual(summary, "Moved one block later and kept the rest stable.")
        mock_call_codex_text.assert_called_once()

    @patch.object(CodexProvider, "call_codex_text")
    def test_generate_summary_falls_back_when_codex_fails(self, mock_call_codex_text):
        mock_call_codex_text.side_effect = CodexProviderError("backend unavailable")

        summary = generate_summary(
            [{"task_id": 1, "start_datetime": "2026-04-01T10:00:00-04:00"}],
            [{"task_id": 1, "start_datetime": "2026-04-01T11:00:00-04:00"}],
            "replan",
        )

        self.assertIn("Triggered by replan.", summary)


class TaskExtractionRefinementTests(TestCase):
    def test_refine_task_candidates_drops_policy_noise(self):
        tasks = [
            {
                "title": "Accommodation Policy",
                "course_name": "",
                "due_datetime": None,
                "estimated_minutes": 30,
                "priority": "medium",
                "category": "assignment",
                "confidence": 0.99,
                "raw_excerpt": "Accommodation policy and grading policy details.",
            },
            {
                "title": "Lab 1 report",
                "course_name": "",
                "due_datetime": "2026-04-10T23:59:00-04:00",
                "estimated_minutes": 90,
                "priority": "high",
                "category": "assignment",
                "confidence": 0.91,
                "raw_excerpt": "Lab 1 report due April 10 at 11:59 PM.",
            },
        ]

        refined = refine_task_candidates(tasks)

        self.assertEqual(len(refined), 1)
        self.assertEqual(refined[0]["title"], "Lab 1 report")
