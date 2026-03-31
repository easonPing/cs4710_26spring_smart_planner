import json
from collections import defaultdict
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    CalendarEventForm,
    ICSUploadForm,
    NaturalLanguageUpdateForm,
    ScheduleGenerationForm,
    SyllabusUploadForm,
    TaskManualForm,
    UserProfileForm,
)
from .models import CalendarEvent, ReplanLog, ScheduleBlock, Task, UserProfile
from .services.calendar_service import build_blocked_slots, import_ics_events, summarize_course_meetings
from .services.candidate_selector import select_daily_candidates
from .services.codex_auth import CodexOAuthProvider
from .services.metrics import (
    deadline_buffer_minutes,
    fragmentation_count,
    hard_conflict_count,
    weighted_completion_score,
)
from .services.replanner import parse_and_apply_patch, replan_from_now
from .services.scheduler_cp_sat import generate_daily_schedule
from .services.storage_service import latest_schedule_version, save_conflict_report, save_schedule_version
from .services.summary_service import fallback_summary
from .services.task_extractor import extract_tasks_from_document, save_tasks
from .services.task_service import create_manual_task, get_tasks_needing_review
from .utils import ensure_aware


def _get_profile():
    return UserProfile.objects.first() or UserProfile.objects.create()


def _serialize_schedule_events(schedule_blocks):
    return [
        {
            "id": f"block-{block.id}",
            "title": block.title,
            "start": block.start_datetime.isoformat(),
            "end": block.end_datetime.isoformat(),
            "extendedProps": {
                "blockType": block.block_type,
                "version": block.version,
                "taskId": block.task_id,
            },
        }
        for block in schedule_blocks
    ]


def dashboard_view(request):
    profile = _get_profile()
    today = timezone.localdate()
    auth_state = CodexOAuthProvider().ensure_ready()
    upcoming_tasks = Task.objects.exclude(status__in=["done", "cancelled"]).order_by("due_datetime")[:5]
    today_blocks = ScheduleBlock.objects.filter(schedule_date=today).order_by("start_datetime")
    context = {
        "profile": profile,
        "today": today,
        "upcoming_tasks": upcoming_tasks,
        "today_blocks": today_blocks,
        "calendar_count": CalendarEvent.objects.count(),
        "task_count": Task.objects.count(),
        "review_count": Task.objects.filter(needs_review=True).count(),
        "replan_count": ReplanLog.objects.count(),
        "auth_state": auth_state,
        "generate_form": ScheduleGenerationForm(initial={"target_date": today}),
        "update_form": NaturalLanguageUpdateForm(),
    }
    return render(request, "planner/dashboard.html", context)


def profile_view(request):
    profile = _get_profile()
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
    else:
        form = UserProfileForm(instance=profile)
    return render(request, "planner/profile.html", {"form": form})


def calendar_upload_view(request):
    edit_event = None
    if request.method == "POST":
        action = request.POST.get("action", "upload_ics")
        if action == "delete_event":
            event = get_object_or_404(CalendarEvent, pk=request.POST.get("event_id"))
            event.delete()
            messages.success(request, "Event deleted.")
            return redirect("calendar_upload")
        if action in {"create_event", "update_event"}:
            if request.POST.get("event_id"):
                edit_event = get_object_or_404(CalendarEvent, pk=request.POST["event_id"])
            event_form = CalendarEventForm(request.POST, instance=edit_event)
            upload_form = ICSUploadForm()
            if event_form.is_valid():
                event = event_form.save(commit=False)
                event.source = "manual" if action == "create_event" else event.source or "manual"
                event.is_fixed = True
                if action == "create_event":
                    event.external_uid = ""
                event.save()
                messages.success(request, "Event saved.")
                return redirect("calendar_upload")
        else:
            upload_form = ICSUploadForm(request.POST, request.FILES)
            event_form = CalendarEventForm()
            if upload_form.is_valid():
                uploaded = upload_form.cleaned_data["ics_file"]
                target_path = settings.MEDIA_ROOT / "ics" / uploaded.name
                with open(target_path, "wb") as handle:
                    for chunk in uploaded.chunks():
                        handle.write(chunk)
                try:
                    imported = import_ics_events(None, target_path)
                except Exception as exc:
                    messages.error(request, f"Unable to import this ICS file: {exc}")
                    return redirect("calendar_upload")
                messages.success(request, f"Imported {len(imported)} calendar events.")
                return redirect("calendar_upload")
    else:
        upload_form = ICSUploadForm()
        if request.GET.get("edit"):
            edit_event = get_object_or_404(CalendarEvent, pk=request.GET["edit"])
        event_form = CalendarEventForm(instance=edit_event)
    recent_events = CalendarEvent.objects.order_by("title", "start_datetime")
    course_summaries = summarize_course_meetings(recent_events)
    return render(
        request,
        "planner/calendar_upload.html",
        {
            "form": upload_form,
            "event_form": event_form,
            "recent_events": recent_events,
            "course_summaries": course_summaries,
            "edit_event": edit_event,
        },
    )


def syllabus_upload_view(request):
    if request.method == "POST":
        form = SyllabusUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["syllabus_file"]
            target_path = settings.MEDIA_ROOT / "syllabi" / uploaded.name
            with open(target_path, "wb") as handle:
                for chunk in uploaded.chunks():
                    handle.write(chunk)
            extracted = extract_tasks_from_document(target_path)
            saved = save_tasks(extracted)
            messages.success(request, f"Processed syllabus and created {len(saved)} task candidates.")
            return redirect("task_review")
    else:
        form = SyllabusUploadForm()
    return render(request, "planner/syllabus_upload.html", {"form": form})


def task_list_view(request):
    edit_task = None
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "delete":
            task = get_object_or_404(Task, pk=request.POST.get("task_id"))
            task.delete()
            messages.success(request, "Task deleted.")
            return redirect("task_list")
        if request.POST.get("task_id"):
            edit_task = get_object_or_404(Task, pk=request.POST["task_id"])
            form = TaskManualForm(request.POST, instance=edit_task)
            if form.is_valid():
                task = form.save(commit=False)
                task.source = edit_task.source or "manual"
                task.is_confirmed = True
                task.needs_review = False
                task.save()
                messages.success(request, "Task updated.")
                return redirect("task_list")
        else:
            form = TaskManualForm(request.POST)
            if form.is_valid():
                cleaned = form.cleaned_data
                create_manual_task(
                    {
                        "title": cleaned["title"],
                        "course_name": cleaned["course_name"],
                        "due_datetime": cleaned["due_datetime"],
                        "estimated_minutes": cleaned["estimated_minutes"],
                        "priority": cleaned["priority"],
                        "category": cleaned["category"],
                        "status": cleaned["status"],
                        "raw_excerpt": cleaned["raw_excerpt"],
                    }
                )
                messages.success(request, "Task created.")
                return redirect("task_list")
    else:
        if request.GET.get("edit"):
            edit_task = get_object_or_404(Task, pk=request.GET["edit"])
        form = TaskManualForm(instance=edit_task)
    tasks = Task.objects.order_by("needs_review", "due_datetime", "-priority")
    return render(request, "planner/task_list.html", {"tasks": tasks, "form": form, "edit_task": edit_task})


def task_review_view(request):
    if request.method == "POST":
        action = request.POST.get("action")
        task = get_object_or_404(Task, pk=request.POST.get("task_id"))
        if action == "approve":
            task.needs_review = False
            task.is_confirmed = True
            if task.status == "draft":
                task.status = "todo"
            task.save()
            messages.success(request, f"Approved task: {task.title}")
        elif action == "reject":
            task.delete()
            messages.success(request, "Task candidate removed.")
        elif action == "save":
            task.title = request.POST.get("title", task.title)
            task.course_name = request.POST.get("course_name", task.course_name)
            task.estimated_minutes = int(request.POST.get("estimated_minutes", task.estimated_minutes))
            due_raw = request.POST.get("due_datetime")
            task.due_datetime = ensure_aware(datetime.fromisoformat(due_raw)) if due_raw else None
            task.needs_review = False
            task.is_confirmed = True
            if task.status == "draft":
                task.status = "todo"
            task.save()
            messages.success(request, f"Updated and approved task: {task.title}")
        return redirect("task_review")
    review_tasks = get_tasks_needing_review()
    return render(request, "planner/task_review.html", {"review_tasks": review_tasks})


def generate_daily_schedule_view(request):
    if request.method != "POST":
        return redirect("daily_schedule")
    form = ScheduleGenerationForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please provide a valid schedule date.")
        return redirect("daily_schedule")
    target_date = form.cleaned_data["target_date"]
    profile = _get_profile()
    tasks = select_daily_candidates(target_date)
    fixed_events = build_blocked_slots(target_date, profile)
    result = generate_daily_schedule(target_date, profile, tasks, fixed_events)
    old_blocks = list(ScheduleBlock.objects.filter(schedule_date=target_date))
    current_version = max([block.version for block in old_blocks], default=0)
    ScheduleBlock.objects.filter(schedule_date=target_date).delete()
    if not result["feasible"]:
        save_conflict_report(target_date.isoformat(), result["conflict_report"])
        messages.error(request, "No feasible schedule was found. Conflict report saved.")
        return redirect(f"{redirect('daily_schedule').url}?date={target_date.isoformat()}")
    saved_blocks = []
    Task.objects.filter(id__in=[task.id for task in tasks]).update(scheduled_minutes=0)
    scheduled_minutes_by_task = defaultdict(int)
    for block_data in result["blocks"]:
        block = ScheduleBlock.objects.create(
            schedule_date=target_date,
            title=block_data["title"],
            task=block_data["task"],
            start_datetime=block_data["start_datetime"],
            end_datetime=block_data["end_datetime"],
            block_type=block_data["block_type"],
            version=current_version + 1,
            is_locked=False,
        )
        saved_blocks.append(block)
        if block.task_id:
            scheduled_minutes_by_task[block.task_id] += block.duration_minutes()
    for task_id, minutes in scheduled_minutes_by_task.items():
        Task.objects.filter(pk=task_id).update(scheduled_minutes=minutes)
    payload = {
        "date": target_date.isoformat(),
        "version": current_version + 1,
        "generated_at": timezone.now().isoformat(),
        "blocks": [
            {
                "title": block.title,
                "task_id": block.task_id,
                "start_datetime": block.start_datetime.isoformat(),
                "end_datetime": block.end_datetime.isoformat(),
                "block_type": block.block_type,
                "is_locked": block.is_locked,
            }
            for block in saved_blocks
        ],
    }
    save_schedule_version(target_date.isoformat(), current_version + 1, payload)
    messages.success(request, f"Generated {len(saved_blocks)} schedule blocks for {target_date}.")
    return redirect(f"{redirect('daily_schedule').url}?date={target_date.isoformat()}")


def daily_schedule_view(request):
    selected_date = request.GET.get("date")
    target_date = datetime.fromisoformat(selected_date).date() if selected_date else timezone.localdate()
    profile = _get_profile()
    schedule_blocks = list(ScheduleBlock.objects.filter(schedule_date=target_date).order_by("start_datetime"))
    fixed_events = list(CalendarEvent.objects.filter(start_datetime__date=target_date).order_by("start_datetime"))
    candidate_tasks = select_daily_candidates(target_date)
    scheduled_task_ids = {block.task_id for block in schedule_blocks if block.task_id}
    unscheduled_tasks = [task for task in candidate_tasks if task.id not in scheduled_task_ids]
    event_feed = [event.to_fullcalendar_event() for event in fixed_events] + _serialize_schedule_events(schedule_blocks)
    latest_version = latest_schedule_version(target_date.isoformat())
    metrics = {
        "hard_conflict_count": hard_conflict_count(schedule_blocks, fixed_events),
        "deadline_buffer_minutes": deadline_buffer_minutes(Task.objects.filter(id__in=[block.task_id for block in schedule_blocks if block.task_id]), schedule_blocks),
        "fragmentation_count": fragmentation_count(schedule_blocks),
        "weighted_completion_score": weighted_completion_score(Task.objects.all()),
    }
    summary = fallback_summary(
        {
            "trigger": "latest_schedule",
            "new_count": len(schedule_blocks),
            "moved_blocks": 0,
        }
    )
    return render(
        request,
        "planner/daily_schedule.html",
        {
            "target_date": target_date,
            "generate_form": ScheduleGenerationForm(initial={"target_date": target_date}),
            "update_form": NaturalLanguageUpdateForm(),
            "schedule_blocks": schedule_blocks,
            "fixed_events": fixed_events,
            "candidate_tasks": candidate_tasks,
            "unscheduled_tasks": unscheduled_tasks,
            "event_feed_json": json.dumps(event_feed),
            "latest_version": latest_version,
            "metrics": metrics,
            "summary": summary,
            "profile": profile,
        },
    )


def apply_patch_view(request):
    if request.method != "POST":
        return redirect("daily_schedule")
    form = NaturalLanguageUpdateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please provide an update.")
        return redirect("daily_schedule")
    patch = parse_and_apply_patch(form.cleaned_data["update_text"])
    result = replan_from_now(timezone.now())
    if result["feasible"]:
        messages.success(request, f"Applied patch `{patch['trigger_type']}` and replanned the schedule.")
    else:
        messages.error(request, "Patch applied, but replanning could not find a feasible schedule.")
    return redirect("daily_schedule")


def replan_logs_view(request):
    logs = ReplanLog.objects.order_by("-created_at")
    return render(request, "planner/replan_logs.html", {"logs": logs})
