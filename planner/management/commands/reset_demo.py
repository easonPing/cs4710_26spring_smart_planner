from django.core.management.base import BaseCommand

from planner.models import CalendarEvent, ReplanLog, ScheduleBlock, Task, UserProfile


class Command(BaseCommand):
    help = "Reset application data used for demos."

    def handle(self, *args, **options):
        ReplanLog.objects.all().delete()
        ScheduleBlock.objects.all().delete()
        CalendarEvent.objects.all().delete()
        Task.objects.all().delete()
        UserProfile.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("Demo data reset complete."))
