import json
import logging
import re

from dateutil import parser as date_parser
from django.utils import timezone

from planner.prompts import (
    build_patch_parsing_prompt,
    build_summary_prompt,
    build_task_extraction_prompt,
)
from planner.utils import normalize_title

from .codex_auth import CodexOAuthProvider

logger = logging.getLogger("planner.llm")


class CodexProviderError(RuntimeError):
    pass


class CodexProvider:
    def __init__(self):
        self.oauth_provider = CodexOAuthProvider()

    def call_codex_json(self, prompt, schema_name):
        auth_state = self.oauth_provider.ensure_ready()
        if not auth_state["ready"]:
            raise CodexProviderError(auth_state["reason"] or "Codex provider is unavailable.")
        raise CodexProviderError(
            f"Codex structured call for {schema_name} is not wired to a remote API yet. "
            "The application will use deterministic fallbacks instead."
        )

    def call_codex_text(self, prompt):
        auth_state = self.oauth_provider.ensure_ready()
        if not auth_state["ready"]:
            raise CodexProviderError(auth_state["reason"] or "Codex provider is unavailable.")
        raise CodexProviderError("Codex text call is not wired to a remote API yet.")

    def extract_tasks(self, chunks, document_name=""):
        tasks = []
        for chunk in chunks:
            tasks.extend(self._fallback_extract_from_chunk(chunk, document_name=document_name))
        return tasks

    def parse_patch(self, user_text):
        _ = build_patch_parsing_prompt(user_text)
        try:
            payload = json.loads(user_text)
            if isinstance(payload, dict) and "trigger_type" in payload:
                return payload
        except json.JSONDecodeError:
            pass

        lowered = user_text.lower()
        if "done" in lowered or "completed" in lowered:
            return {"trigger_type": "task_done", "payload": {"task_title": user_text}}
        if "estimate" in lowered or "minutes" in lowered or "hours" in lowered:
            minutes_match = re.search(r"(\d+)\s*(minute|minutes|min|hour|hours)", lowered)
            minutes = None
            if minutes_match:
                value = int(minutes_match.group(1))
                minutes = value * 60 if "hour" in minutes_match.group(2) else value
            return {
                "trigger_type": "change_estimate",
                "payload": {"task_title": user_text, "estimated_minutes": minutes or 60},
            }
        datetime_match = re.search(
            r"(?P<start>\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}).*?(?P<end>\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2})",
            user_text,
        )
        if datetime_match:
            return {
                "trigger_type": "add_event",
                "payload": {
                    "title": user_text[:80],
                    "start_datetime": datetime_match.group("start"),
                    "end_datetime": datetime_match.group("end"),
                },
            }
        return {"trigger_type": "custom", "payload": {"text": user_text}}

    def summarize_diff(self, old_blocks, new_blocks, trigger):
        _ = build_summary_prompt(old_blocks, new_blocks, trigger)
        old_count = len(old_blocks)
        new_count = len(new_blocks)
        return f"Replanned after {trigger}. Block count changed from {old_count} to {new_count}."

    def _fallback_extract_from_chunk(self, chunk, document_name=""):
        prompt = build_task_extraction_prompt(chunk)
        logger.info("Using fallback task extraction for chunk of length %s", len(chunk))
        tasks = []
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        for line in lines:
            if "due" not in line.lower() and "exam" not in line.lower() and "project" not in line.lower():
                continue
            due_datetime = None
            try:
                due_datetime = date_parser.parse(line, fuzzy=True)
                if timezone.is_naive(due_datetime):
                    due_datetime = timezone.make_aware(due_datetime, timezone.get_current_timezone())
            except (ValueError, TypeError, OverflowError):
                due_datetime = None
            title = re.split(r"due|on|by", line, maxsplit=1, flags=re.IGNORECASE)[0].strip(" :-") or line[:80]
            normalized = normalize_title(title)
            if not normalized:
                continue
            confidence = 0.9 if due_datetime else 0.55
            tasks.append(
                {
                    "title": title[:255],
                    "course_name": "",
                    "due_datetime": due_datetime.isoformat() if due_datetime else None,
                    "estimated_minutes": 120 if "project" in line.lower() else 60,
                    "priority": "high" if "exam" in line.lower() or "project" in line.lower() else "medium",
                    "category": "exam" if "exam" in line.lower() else "assignment",
                    "confidence": confidence,
                    "raw_excerpt": line,
                    "document_name": document_name,
                    "debug_prompt": prompt[:200],
                }
            )
        return tasks
