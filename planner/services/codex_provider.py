import json
import logging
import re
import uuid
import urllib.error
import urllib.request
from urllib.parse import urlparse

from django.conf import settings
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

    @staticmethod
    def _build_request_id():
        return str(uuid.uuid4())

    @staticmethod
    def _resolve_codex_url():
        base = (settings.CODEX_API_BASE or "https://chatgpt.com/backend-api").rstrip("/")
        if base.endswith("/codex/responses"):
            return base
        if base.endswith("/codex"):
            return f"{base}/responses"
        return f"{base}/codex/responses"

    @staticmethod
    def _parse_sse_json_lines(raw_bytes):
        buffer = ""
        events = []
        for chunk in raw_bytes.decode("utf-8", "replace").split("\n\n"):
            if not chunk.strip():
                continue
            data_lines = []
            for line in chunk.splitlines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload and payload != "[DONE]":
                        data_lines.append(payload)
            if not data_lines:
                continue
            try:
                events.append(json.loads("\n".join(data_lines)))
            except json.JSONDecodeError:
                continue
        return events

    @staticmethod
    def _extract_output_text(events):
        message_text = []
        output_done_chunks = []
        deltas = []
        for event in events:
            event_type = event.get("type")
            if event_type == "response.output_text.done":
                text = event.get("text")
                if isinstance(text, str):
                    output_done_chunks.append(text)
            elif event_type == "response.output_text.delta":
                delta = event.get("delta")
                if isinstance(delta, str):
                    deltas.append(delta)
            elif event_type == "response.output_item.done":
                item = event.get("item") or {}
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                            message_text.append(content["text"])
        if message_text:
            return "".join(message_text).strip()
        if output_done_chunks:
            return "".join(output_done_chunks).strip()
        return "".join(deltas).strip()

    @staticmethod
    def _normalize_task_items(payload, document_name=""):
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise CodexProviderError("Codex task extraction returned an invalid payload.")
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "title": str(item.get("title", "")).strip()[:255],
                    "course_name": str(item.get("course_name", "")).strip()[:120],
                    "due_datetime": item.get("due_datetime"),
                    "estimated_minutes": int(item.get("estimated_minutes") or 60),
                    "priority": str(item.get("priority", "medium")).strip().lower() or "medium",
                    "category": str(item.get("category", "assignment")).strip().lower() or "assignment",
                    "confidence": float(item.get("confidence", 0.5)),
                    "raw_excerpt": str(item.get("raw_excerpt", "")).strip(),
                    "document_name": document_name,
                }
            )
        return normalized

    def _get_auth_state(self):
        auth_state = self.oauth_provider.ensure_ready()
        if not auth_state["ready"]:
            raise CodexProviderError(auth_state["reason"] or "Codex provider is unavailable.")
        if not auth_state.get("summary", {}).get("account_id"):
            raise CodexProviderError(
                "Codex OAuth is connected, but no ChatGPT account id was found in the token."
            )
        return auth_state

    def _post_response(self, payload):
        auth_state = self._get_auth_state()
        token = auth_state["credentials"]["tokens"]["access_token"]
        account_id = auth_state["summary"]["account_id"]
        session_id = self._build_request_id()
        endpoint = self._resolve_codex_url()
        parsed = urlparse(endpoint)
        user_agent = f"smart-planner ({parsed.scheme or 'https'} backend bridge)"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "chatgpt-account-id": account_id,
                "originator": "pi",
                "User-Agent": user_agent,
                "OpenAI-Beta": "responses=experimental",
                "accept": "text/event-stream",
                "Content-Type": "application/json",
                "session_id": session_id,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return self._parse_sse_json_lines(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            logger.warning("Codex backend response call failed with status %s: %s", exc.code, body)
            message = body
            try:
                error_payload = json.loads(body)
                if isinstance(error_payload, dict):
                    message = (
                        error_payload.get("detail")
                        or error_payload.get("message")
                        or error_payload.get("error", {}).get("message")
                        or body
                    )
            except json.JSONDecodeError:
                pass
            raise CodexProviderError(message) from exc
        except OSError as exc:
            raise CodexProviderError(f"Codex backend network error: {exc}") from exc

    def call_codex_json(self, prompt, schema_name):
        response = self._post_response(
            {
                "model": settings.CODEX_MODEL,
                "store": False,
                "stream": True,
                "instructions": "Return only valid JSON and no surrounding prose.",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    }
                ],
                "text": {"verbosity": "low"},
                "include": ["reasoning.encrypted_content"],
                "prompt_cache_key": f"smart-planner-{schema_name}",
                "tool_choice": "auto",
                "parallel_tool_calls": True,
            }
        )
        text = self._extract_output_text(response)
        if not text:
            raise CodexProviderError("Codex returned an empty structured response.")
        return json.loads(text)

    def call_codex_text(self, prompt):
        response = self._post_response(
            {
                "model": settings.CODEX_MODEL,
                "store": False,
                "stream": True,
                "instructions": "You are a concise assistant. Follow the prompt exactly.",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    }
                ],
                "text": {"verbosity": "medium"},
                "include": ["reasoning.encrypted_content"],
                "prompt_cache_key": "smart-planner-text",
                "tool_choice": "auto",
                "parallel_tool_calls": True,
            }
        )
        text = self._extract_output_text(response)
        if not text:
            raise CodexProviderError("Codex returned an empty text response.")
        return text

    def extract_tasks(self, chunks, document_name=""):
        tasks = []
        for chunk in chunks:
            prompt = build_task_extraction_prompt(chunk)
            try:
                payload = self.call_codex_json(
                    (
                        f"{prompt}\n\n"
                        'Return JSON with shape {"items":[{'
                        '"title": string, '
                        '"course_name": string, '
                        '"due_datetime": string|null, '
                        '"estimated_minutes": integer, '
                        '"priority": "low"|"medium"|"high"|"urgent", '
                        '"category": string, '
                        '"confidence": number, '
                        '"raw_excerpt": string'
                        "}]}."
                    ),
                    "task_extraction",
                )
                tasks.extend(self._normalize_task_items(payload, document_name=document_name))
            except (CodexProviderError, ValueError, TypeError):
                logger.info("Codex task extraction failed; using fallback extraction for %s", document_name or "chunk")
                tasks.extend(self._fallback_extract_from_chunk(chunk, document_name=document_name))
        return tasks

    def parse_patch(self, user_text):
        prompt = build_patch_parsing_prompt(user_text)
        try:
            payload = self.call_codex_json(
                (
                    f"{prompt}\n\n"
                    'Return JSON with shape {"trigger_type": string, "payload": object}. '
                    'Use trigger_type from: add_event, task_done, change_estimate, custom.'
                ),
                "patch_parse",
            )
            if isinstance(payload, dict) and "trigger_type" in payload:
                return payload
        except CodexProviderError:
            logger.info("Codex patch parsing failed; using deterministic fallback parser.")
            pass
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
        prompt = build_summary_prompt(old_blocks, new_blocks, trigger)
        return self.call_codex_text(prompt)

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
