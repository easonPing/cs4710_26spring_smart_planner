from datetime import datetime
from pathlib import Path

from django.conf import settings

from planner.models import Task
from planner.utils import ensure_aware, normalize_title

from .codex_provider import CodexProvider
from .syllabus_text import extract_document_text, split_into_chunks, write_extracted_cache

NOISE_KEYWORDS = {
    "accommodation",
    "grading",
    "policy",
    "attendance",
    "office hour",
    "office hours",
    "textbook",
    "prerequisite",
    "prerequisites",
    "disability",
    "integrity",
    "honor code",
    "wellness",
    "email",
    "contact",
    "zoom",
}

DELIVERABLE_KEYWORDS = {
    "assignment",
    "homework",
    "lab",
    "project",
    "exam",
    "quiz",
    "midterm",
    "final",
    "presentation",
    "writeup",
    "report",
    "paper",
    "milestone",
    "deliverable",
    "reading response",
    "prep",
    "submission",
}


def extract_tasks_from_document(file_path, file_type=None):
    document_path = Path(file_path)
    text = extract_document_text(document_path)
    chunks = split_into_chunks(text)
    write_extracted_cache(document_path.name, text, chunks, settings.MEDIA_ROOT / "extracted_text")
    return extract_tasks_from_chunks(chunks, document_name=document_path.name)


def extract_tasks_from_chunks(chunks, document_name=""):
    provider = CodexProvider()
    raw_candidates = provider.extract_tasks([chunk["text"] for chunk in chunks], document_name=document_name)
    merged = merge_task_candidates(raw_candidates)
    deduped = deduplicate_tasks(merged)
    refined = refine_task_candidates(deduped)
    return flag_low_confidence(refined)


def merge_task_candidates(candidates):
    merged = []
    seen = {}
    for candidate in candidates:
        key = (normalize_title(candidate.get("title")), candidate.get("due_datetime"))
        if key in seen:
            existing = seen[key]
            existing["confidence"] = max(existing["confidence"], candidate.get("confidence", 0.5))
            existing["raw_excerpt"] = existing["raw_excerpt"] or candidate.get("raw_excerpt", "")
        else:
            seen[key] = candidate
            merged.append(candidate)
    return merged


def deduplicate_tasks(tasks):
    deduped = []
    seen = set()
    for task in tasks:
        key = (
            normalize_title(task.get("title")),
            task.get("course_name", "").strip().lower(),
            task.get("due_datetime"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(task)
    return deduped


def _candidate_text(candidate):
    return " ".join(
        [
            str(candidate.get("title", "")),
            str(candidate.get("raw_excerpt", "")),
        ]
    ).lower()


def _has_deliverable_keyword(candidate):
    text = _candidate_text(candidate)
    return any(keyword in text for keyword in DELIVERABLE_KEYWORDS)


def _is_probable_non_task(candidate):
    text = _candidate_text(candidate)
    has_noise = any(keyword in text for keyword in NOISE_KEYWORDS)
    return has_noise and not _has_deliverable_keyword(candidate)


def refine_task_candidates(tasks):
    refined = []
    for task in tasks:
        confidence = float(task.get("confidence", 0.0))
        has_due = bool(task.get("due_datetime"))
        if _is_probable_non_task(task):
            continue
        if has_due:
            refined.append(task)
            continue
        if confidence >= 0.97 and _has_deliverable_keyword(task):
            task["needs_review"] = True
            refined.append(task)
    return refined


def flag_low_confidence(tasks, threshold=0.7):
    for task in tasks:
        task["needs_review"] = task.get("needs_review", False) or task.get("confidence", 0.0) < threshold or not task.get("due_datetime")
    return tasks


def save_tasks(tasks):
    saved = []
    for task_data in tasks:
        due_datetime = task_data.get("due_datetime")
        aware_due = ensure_aware(datetime.fromisoformat(due_datetime)) if due_datetime else None
        task, _ = Task.objects.update_or_create(
            title=task_data["title"],
            document_name=task_data.get("document_name", ""),
            defaults={
                "course_name": task_data.get("course_name", ""),
                "due_datetime": aware_due,
                "estimated_minutes": task_data.get("estimated_minutes", 60),
                "priority": task_data.get("priority", "medium"),
                "category": task_data.get("category", "assignment"),
                "status": "draft" if task_data.get("needs_review") else "todo",
                "source": "syllabus",
                "extraction_confidence": task_data.get("confidence", 0.5),
                "raw_excerpt": task_data.get("raw_excerpt", ""),
                "needs_review": task_data.get("needs_review", False),
                "is_confirmed": not task_data.get("needs_review", False),
            },
        )
        saved.append(task)
    return saved
