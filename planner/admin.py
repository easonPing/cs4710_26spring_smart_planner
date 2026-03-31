from django.contrib import admin

from .models import CalendarEvent, ReplanLog, ScheduleBlock, Task, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'preferred_study_start', 'preferred_study_end', 'updated_at')


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_datetime', 'end_datetime', 'event_type', 'source', 'is_fixed')
    list_filter = ('event_type', 'source', 'is_fixed')
    search_fields = ('title', 'external_uid', 'location')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'course_name', 'due_datetime', 'estimated_minutes', 'priority', 'status', 'needs_review')
    list_filter = ('priority', 'status', 'category', 'source', 'needs_review')
    search_fields = ('title', 'course_name', 'document_name')


@admin.register(ScheduleBlock)
class ScheduleBlockAdmin(admin.ModelAdmin):
    list_display = ('title', 'schedule_date', 'start_datetime', 'end_datetime', 'block_type', 'version', 'is_locked')
    list_filter = ('schedule_date', 'block_type', 'version', 'is_locked')
    search_fields = ('title',)


@admin.register(ReplanLog)
class ReplanLogAdmin(admin.ModelAdmin):
    list_display = ('schedule_date', 'trigger_type', 'old_version', 'new_version', 'moved_block_count', 'created_at')
    list_filter = ('trigger_type', 'schedule_date')
