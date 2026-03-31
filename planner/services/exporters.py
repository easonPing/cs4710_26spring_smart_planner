import csv
import json
from pathlib import Path


def export_schedule_json(schedule_blocks, path):
    payload = []
    for block in schedule_blocks:
        payload.append(
            {
                "title": block.title,
                "start_datetime": block.start_datetime.isoformat(),
                "end_datetime": block.end_datetime.isoformat(),
                "block_type": block.block_type,
                "task_id": block.task_id,
            }
        )
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def export_conflict_report_json(report, path):
    Path(path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def export_metrics_csv(metrics, path):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics.keys()))
        writer.writeheader()
        writer.writerow(metrics)
    return path


def export_tasks_json(tasks, path):
    payload = []
    for task in tasks:
        payload.append(
            {
                "title": task.title,
                "due_datetime": task.due_datetime.isoformat() if task.due_datetime else None,
                "estimated_minutes": task.estimated_minutes,
                "priority": task.priority,
                "status": task.status,
            }
        )
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
