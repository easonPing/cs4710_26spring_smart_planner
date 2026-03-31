import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .storage_service import mirror_codex_auth

logger = logging.getLogger("planner.oauth")


class CodexCredentialStore:
    @staticmethod
    def candidate_paths():
        explicit = settings.CODEX_AUTH_PATH
        paths = []
        if explicit:
            paths.append(Path(explicit).expanduser())
        paths.extend(
            [
                Path.home() / ".codex" / "auth.json",
                Path.home() / ".openai" / "codex" / "auth.json",
            ]
        )
        return paths

    @classmethod
    def load_from_codex_cli(cls):
        for path in cls.candidate_paths():
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                logger.info("Loaded Codex credentials from %s", path)
                return {"path": str(path), "data": data}
        return None

    @staticmethod
    def load_from_local_cache():
        path = settings.BASE_DIR / "data" / "oauth_cache" / "codex_auth.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def save_local_cache(data):
        mirror_codex_auth(data)
        return data


class CodexAuthManager:
    @staticmethod
    def is_expired(credentials):
        if not credentials:
            return True
        expires_at = credentials.get("expires_at")
        if not expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        return expiry <= timezone.now() + timedelta(minutes=5)

    @classmethod
    def refresh_if_needed(cls, credentials):
        if not credentials:
            return None
        if not cls.is_expired(credentials):
            return credentials
        credentials = credentials.copy()
        credentials["refresh_required"] = True
        credentials["refreshed_at"] = timezone.now().isoformat()
        logger.warning("Codex credentials appear expired; manual `codex --login` may be required.")
        return credentials


class CodexOAuthProvider:
    def __init__(self):
        self.store = CodexCredentialStore()
        self.auth_manager = CodexAuthManager()

    def ensure_ready(self):
        source = self.store.load_from_codex_cli()
        credentials = None
        if source:
            credentials = source["data"]
            self.store.save_local_cache(credentials)
        else:
            credentials = self.store.load_from_local_cache()
        if not credentials:
            return {"ready": False, "reason": "No Codex CLI credentials found."}
        credentials = self.auth_manager.refresh_if_needed(credentials)
        return {
            "ready": not credentials.get("refresh_required", False),
            "reason": "" if not credentials.get("refresh_required") else "Credentials need refresh.",
            "credentials": credentials,
        }
