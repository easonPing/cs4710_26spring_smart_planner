from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from planner.models import CalendarEvent, Task, UserProfile


class Command(BaseCommand):
    help = "Seed a lightweight demo dataset for UVA Smart Planner."

    def handle(self, *args, **options):
        UserProfile.objects.all().delete()
        profile = UserProfile.objects.create(
            display_name="Demo Student",
            preferred_study_start=time(9, 0),
            preferred_study_end=time(21, 0),
            sleep_start=time(23, 30),
            sleep_end=time(7, 30),
        )
        today = timezone.localdate()
        tz = timezone.get_current_timezone()
        CalendarEvent.objects.all().delete()
        CalendarEvent.objects.create(
            title="CS4710 Lecture",
            start_datetime=timezone.make_aware(datetime.combine(today, time(11, 0)), tz),
            end_datetime=timezone.make_aware(datetime.combine(today, time(12, 15)), tz),
            event_type="class",
            is_fixed=True,
            source="seed",
            external_uid="seed-lecture-1",
        )
        CalendarEvent.objects.create(
            title="Office Hours",
            start_datetime=timezone.make_aware(datetime.combine(today, time(15, 0)), tz),
            end_datetime=timezone.make_aware(datetime.combine(today, time(16, 0)), tz),
            event_type="meeting",
            is_fixed=True,
            source="seed",
            external_uid="seed-office-hours-1",
        )
        Task.objects.all().delete()
        Task.objects.create(
            title="Project milestone draft",
            course_name="CS4710",
            due_datetime=timezone.now() + timedelta(days=1),
            estimated_minutes=180,
            priority="urgent",
            category="project",
            status="todo",
            source="seed",
        )
        Task.objects.create(
            title="Read HCI paper",
            course_name="CS6501",
            due_datetime=timezone.now() + timedelta(days=2),
            estimated_minutes=90,
            priority="medium",
            category="reading",
            status="todo",
            source="seed",
        )
        self.stdout.write(self.style.SUCCESS(f"Seeded demo data for {profile.display_name}"))
