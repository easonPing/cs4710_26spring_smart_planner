from datetime import timedelta

from django.db import models
from django.utils import timezone

from .constants import BLOCK_TYPE_CHOICES, EVENT_TYPE_CHOICES, PATCH_TYPE_CHOICES, PRIORITY_CHOICES, TASK_CATEGORY_CHOICES, TASK_STATUS_CHOICES
from .utils import combine_date_time


class UserProfile(models.Model):
    display_name = models.CharField(max_length=120, blank=True)
    preferred_study_start = models.TimeField(default='09:00')
    preferred_study_end = models.TimeField(default='21:00')
    sleep_start = models.TimeField(default='23:30')
    sleep_end = models.TimeField(default='07:30')
    breakfast_start = models.TimeField(default='08:00')
    breakfast_end = models.TimeField(default='08:30')
    lunch_start = models.TimeField(default='12:00')
    lunch_end = models.TimeField(default='13:00')
    dinner_start = models.TimeField(default='18:00')
    dinner_end = models.TimeField(default='19:00')
    max_continuous_work_minutes = models.PositiveIntegerField(default=120)
    default_break_minutes = models.PositiveIntegerField(default=15)
    freeze_horizon_minutes = models.PositiveIntegerField(default=60)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User profile'
        verbose_name_plural = 'User profiles'

    def __str__(self):
        return self.display_name or 'Default profile'

    def get_meal_windows(self):
        return [
            ('breakfast', self.breakfast_start, self.breakfast_end),
            ('lunch', self.lunch_start, self.lunch_end),
            ('dinner', self.dinner_start, self.dinner_end),
        ]


class CalendarEvent(models.Model):
    title = models.CharField(max_length=255)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default='class')
    is_fixed = models.BooleanField(default=True)
    source = models.CharField(max_length=30, default='ics')
    external_uid = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    recurrence_weekdays = models.JSONField(
        default=list,
        blank=True,
        help_text='0=Monday … 6=Sunday. Empty means a one-time event on start date.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_datetime']
        constraints = [
            models.UniqueConstraint(
                fields=['external_uid', 'start_datetime'],
                name='planner_unique_external_uid_start',
            )
        ]

    def __str__(self):
        return f'{self.title} ({self.start_datetime:%Y-%m-%d %H:%M})'

    @property
    def recurrence_weekday_labels(self):
        if not self.recurrence_weekdays:
            return []
        names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        return [names[d] for d in sorted(self.recurrence_weekdays) if isinstance(d, int) and 0 <= d < 7]

    def occurrence_on_date(self, target_date):
        """Return (start, end) aware datetimes on target_date, or None if this event does not occur."""
        if not self.is_fixed:
            return None
        local_start = timezone.localtime(self.start_datetime)
        local_end = timezone.localtime(self.end_datetime)
        if self.recurrence_weekdays:
            if target_date.weekday() not in self.recurrence_weekdays:
                return None
        else:
            if local_start.date() != target_date:
                return None
        start = combine_date_time(target_date, local_start.time())
        end = combine_date_time(target_date, local_end.time())
        if end <= start:
            end = end + timedelta(days=1)
        return start, end

    def to_fullcalendar_event(self, occurrence_start=None, occurrence_end=None):
        start = occurrence_start or self.start_datetime
        end = occurrence_end or self.end_datetime
        day_key = timezone.localtime(start).date().isoformat()
        return {
            'id': f'event-{self.pk}-{day_key}',
            'title': self.title,
            'start': start.isoformat(),
            'end': end.isoformat(),
            'extendedProps': {
                'eventType': self.event_type,
                'source': self.source,
                'isFixed': self.is_fixed,
            },
        }


class Task(models.Model):
    title = models.CharField(max_length=255)
    course_name = models.CharField(max_length=120, blank=True)
    due_datetime = models.DateTimeField(null=True, blank=True)
    estimated_minutes = models.PositiveIntegerField(default=60)
    scheduled_minutes = models.PositiveIntegerField(default=0)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    category = models.CharField(max_length=20, choices=TASK_CATEGORY_CHOICES, default='assignment')
    status = models.CharField(max_length=20, choices=TASK_STATUS_CHOICES, default='todo')
    source = models.CharField(max_length=30, default='manual')
    extraction_confidence = models.FloatField(default=1.0)
    raw_excerpt = models.TextField(blank=True)
    needs_review = models.BooleanField(default=False)
    is_confirmed = models.BooleanField(default=True)
    carry_over_count = models.PositiveIntegerField(default=0)
    document_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_datetime', '-priority', 'title']

    def __str__(self):
        return self.title

    @property
    def remaining_minutes(self):
        return max(self.estimated_minutes - self.scheduled_minutes, 0)

    def is_overdue(self):
        return bool(self.due_datetime and self.due_datetime < timezone.now() and self.status != 'done')

    def urgency_score(self, now=None):
        now = now or timezone.now()
        priority_weight = {'low': 1, 'medium': 2, 'high': 3, 'urgent': 4}[self.priority]
        if not self.due_datetime:
            return priority_weight * 10 + self.carry_over_count * 2
        delta = self.due_datetime - now
        hours = max(delta.total_seconds() / 3600, 1)
        return (priority_weight * 25) + (72 / hours) + (self.carry_over_count * 5)


class ScheduleBlock(models.Model):
    schedule_date = models.DateField()
    title = models.CharField(max_length=255)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    block_type = models.CharField(max_length=20, choices=BLOCK_TYPE_CHOICES, default='task')
    version = models.PositiveIntegerField(default=1)
    is_locked = models.BooleanField(default=False)
    source = models.CharField(max_length=30, default='scheduler')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_datetime']

    def __str__(self):
        return f'{self.title} ({self.start_datetime:%H:%M}-{self.end_datetime:%H:%M})'

    def duration_minutes(self):
        return int((self.end_datetime - self.start_datetime).total_seconds() // 60)


class ReplanLog(models.Model):
    schedule_date = models.DateField(default=timezone.localdate)
    trigger_type = models.CharField(max_length=20, choices=PATCH_TYPE_CHOICES, default='custom')
    trigger_payload_json = models.JSONField(default=dict, blank=True)
    old_version = models.PositiveIntegerField(default=0)
    new_version = models.PositiveIntegerField(default=0)
    moved_block_count = models.PositiveIntegerField(default=0)
    summary_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.trigger_type} ({self.old_version} -> {self.new_version})'
