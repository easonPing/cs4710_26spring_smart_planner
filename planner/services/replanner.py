from datetime import datetime

from django.utils import timezone

from planner.models import CalendarEvent, ReplanLog, ScheduleBlock, Task, UserProfile
from planner.utils import ensure_aware

from .calendar_service import build_blocked_slots
from .candidate_selector import select_daily_candidates
from .codex_provider import CodexProvider
from .metrics import moved_block_count
from .scheduler_cp_sat import generate_daily_schedule
from .storage_service import latest_schedule_version, save_schedule_version
from .summary_service import generate_summary


def parse_and_apply_patch(user_text_or_patch):
    provider = CodexProvider()
    patch = user_text_or_patch if isinstance(user_text_or_patch, dict) else provider.parse_patch(user_text_or_patch)
    trigger_type = patch.get("trigger_type", "custom")
    payload = patch.get("payload", {})
    if trigger_type == "add_event" and payload.get("start_datetime") and payload.get("end_datetime"):
        CalendarEvent.objects.create(
            title=payload.get("title", "New Event"),
            start_datetime=ensure_aware(datetime.fromisoformat(payload["start_datetime"])),
            end_datetime=ensure_aware(datetime.fromisoformat(payload["end_datetime"])),
            event_type="meeting",
            is_fixed=True,
            source="manual",
            external_uid="",
        )
    elif trigger_type == "task_done":
        task = Task.objects.filter(title__icontains=payload.get("task_title", "")[:50]).first()
        if task:
            task.status = "done"
            task.save(update_fields=["status", "updated_at"])
    elif trigger_type == "change_estimate":
        task = Task.objects.filter(title__icontains=payload.get("task_title", "")[:50]).first()
        if task:
            task.estimated_minutes = payload.get("estimated_minutes", task.estimated_minutes)
            task.save(update_fields=["estimated_minutes", "updated_at"])
    return patch


def lock_past_blocks(schedule_blocks, now):
    return [block for block in schedule_blocks if block.end_datetime <= now]


def lock_near_future_blocks(schedule_blocks, now, freeze_minutes=60):
    freeze_end = now + timezone.timedelta(minutes=freeze_minutes)
    return [block for block in schedule_blocks if block.start_datetime < freeze_end]


def create_new_schedule_version(old_version, new_blocks):
    if not new_blocks:
        return old_version + 1
    schedule_date = new_blocks[0].schedule_date
    payload = {
        "date": schedule_date.isoformat(),
        "version": old_version + 1,
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
            for block in new_blocks
        ],
    }
    save_schedule_version(schedule_date.isoformat(), old_version + 1, payload)
    return old_version + 1


def diff_schedule_versions(old_blocks, new_blocks):
    return {"moved_block_count": moved_block_count(old_blocks, new_blocks)}


def log_replan(trigger, old_version, new_version, summary, schedule_date, moved_blocks=0, payload=None):
    return ReplanLog.objects.create(
        schedule_date=schedule_date,
        trigger_type=trigger,
        trigger_payload_json=payload or {},
        old_version=old_version,
        new_version=new_version,
        moved_block_count=moved_blocks,
        summary_text=summary,
    )


def replan_from_now(now):
    target_date = timezone.localtime(now).date()
    profile = UserProfile.objects.first() or UserProfile.objects.create()
    current_blocks = list(ScheduleBlock.objects.filter(schedule_date=target_date).order_by("start_datetime"))
    old_version_record = latest_schedule_version(target_date.isoformat())
    old_version = old_version_record["version"] if old_version_record else 0
    locked_ids = {block.id for block in lock_past_blocks(current_blocks, now)}
    locked_ids.update(block.id for block in lock_near_future_blocks(current_blocks, now, profile.freeze_horizon_minutes))
    locked_blocks = [block for block in current_blocks if block.id in locked_ids]
    tasks = select_daily_candidates(target_date, now=now)
    fixed_events = build_blocked_slots(target_date, profile)
    fixed_events.extend(
        {
            "start": block.start_datetime,
            "end": block.end_datetime,
            "block_type": block.block_type,
            "title": block.title,
        }
        for block in locked_blocks
    )
    result = generate_daily_schedule(target_date, profile, tasks, fixed_events, old_blocks=locked_blocks)
    if not result["feasible"]:
        return result
    ScheduleBlock.objects.filter(schedule_date=target_date).delete()
    saved_blocks = []
    for old_block in locked_blocks:
        old_block.pk = None
        old_block.version = old_version + 1
        old_block.save()
        saved_blocks.append(old_block)
    for block_data in result["blocks"]:
        saved_blocks.append(
            ScheduleBlock.objects.create(
                schedule_date=target_date,
                title=block_data["title"],
                task=block_data["task"],
                start_datetime=block_data["start_datetime"],
                end_datetime=block_data["end_datetime"],
                block_type=block_data["block_type"],
                version=old_version + 1,
                is_locked=False,
            )
        )
    summary = generate_summary(
        [{"task_id": block.task_id, "start_datetime": block.start_datetime.isoformat()} for block in current_blocks],
        [{"task_id": block.task_id, "start_datetime": block.start_datetime.isoformat()} for block in saved_blocks],
        "replan",
    )
    version = create_new_schedule_version(old_version, saved_blocks)
    diff = diff_schedule_versions(current_blocks, saved_blocks)
    log_replan("custom", old_version, version, summary, target_date, diff["moved_block_count"])
    return {"feasible": True, "blocks": saved_blocks, "summary": summary}
