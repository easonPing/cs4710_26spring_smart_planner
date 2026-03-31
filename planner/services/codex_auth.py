import base64
import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
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
        path = settings.CODEX_CACHE_DIR / "codex_auth.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def save_local_cache(data):
        mirror_codex_auth(data)
        return data


class CodexAuthManager:
    @staticmethod
    def _decode_jwt_payload(token):
        if not token or token.count(".") < 2:
            return {}
        try:
            payload = token.split(".")[1]
            padding = "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload + padding)
            return json.loads(decoded.decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return {}

    @classmethod
    def _resolve_expiry(cls, credentials):
        expires_at = credentials.get("expires_at")
        if expires_at:
            try:
                return datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                pass

        tokens = credentials.get("tokens") or {}
        for token_name in ("access_token", "id_token"):
            payload = cls._decode_jwt_payload(tokens.get(token_name))
            exp = payload.get("exp")
            if exp:
                try:
                    return datetime.fromtimestamp(exp, tz=UTC)
                except (TypeError, ValueError, OSError):
                    continue
        return None

    @classmethod
    def summarize_credentials(cls, credentials):
        tokens = credentials.get("tokens") or {}
        id_payload = cls._decode_jwt_payload(tokens.get("id_token"))
        access_payload = cls._decode_jwt_payload(tokens.get("access_token"))
        expiry = cls._resolve_expiry(credentials)
        auth_profile = (
            id_payload.get("https://api.openai.com/auth")
            or access_payload.get("https://api.openai.com/auth")
            or {}
        )
        return {
            "auth_mode": credentials.get("auth_mode", ""),
            "email": id_payload.get("email") or access_payload.get("https://api.openai.com/profile", {}).get("email", ""),
            "account_id": tokens.get("account_id") or auth_profile.get("chatgpt_account_id", ""),
            "plan_type": auth_profile.get("chatgpt_plan_type", ""),
            "expires_at": expiry.isoformat() if expiry else "",
            "last_refresh": credentials.get("last_refresh", ""),
            "scopes": access_payload.get("scp", []),
        }

    @staticmethod
    def is_expired(credentials):
        if not credentials:
            return True
        expiry = CodexAuthManager._resolve_expiry(credentials)
        if not expiry:
            return False
        return expiry <= timezone.now() + timedelta(minutes=5)

    @classmethod
    def refresh_if_needed(cls, credentials):
        if not credentials:
            return None
        if not cls.is_expired(credentials):
            return credentials
        refreshed = cls.refresh_credentials(credentials)
        if refreshed:
            return refreshed
        credentials = credentials.copy()
        credentials["refresh_required"] = True
        credentials["refreshed_at"] = timezone.now().isoformat()
        logger.warning("Codex credentials appear expired; manual `codex --login` may be required.")
        return credentials

    @classmethod
    def refresh_credentials(cls, credentials):
        tokens = (credentials or {}).get("tokens") or {}
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            return None
        access_payload = cls._decode_jwt_payload(tokens.get("access_token"))
        id_payload = cls._decode_jwt_payload(tokens.get("id_token"))
        client_id = access_payload.get("client_id")
        if not client_id:
            audience = id_payload.get("aud") or []
            client_id = audience[0] if isinstance(audience, list) and audience else audience
        if not client_id:
            logger.warning("Codex credentials are refreshable in principle, but no client_id was found.")
            return None
        body = json.dumps(
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://auth0.openai.com/oauth/token",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("Codex OAuth refresh failed with status %s.", exc.code)
            return None
        except OSError as exc:
            logger.warning("Codex OAuth refresh failed due to network or OS error: %s", exc)
            return None

        new_credentials = json.loads(json.dumps(credentials))
        new_tokens = new_credentials.setdefault("tokens", {})
        for key in ("access_token", "id_token", "refresh_token"):
            if payload.get(key):
                new_tokens[key] = payload[key]
        new_credentials["last_refresh"] = timezone.now().isoformat()
        new_credentials["refresh_required"] = False
        new_credentials["refreshed_at"] = timezone.now().isoformat()
        logger.info("Refreshed Codex OAuth credentials through the OpenAI OAuth token endpoint.")
        return new_credentials

    @classmethod
    def choose_best_credentials(cls, *candidates):
        best = None
        best_expiry = None
        for candidate in candidates:
            if not candidate:
                continue
            expiry = cls._resolve_expiry(candidate)
            if best is None:
                best = candidate
                best_expiry = expiry
                continue
            if best_expiry is None and expiry is not None:
                best = candidate
                best_expiry = expiry
                continue
            if best_expiry is not None and expiry is not None and expiry > best_expiry:
                best = candidate
                best_expiry = expiry
        return best


class CodexOAuthProvider:
    def __init__(self):
        self.store = CodexCredentialStore()
        self.auth_manager = CodexAuthManager()

    def ensure_ready(self):
        source = self.store.load_from_codex_cli()
        cache = self.store.load_from_local_cache()
        credentials = None
        source_path = ""
        if source:
            credentials = self.auth_manager.choose_best_credentials(source["data"], cache)
            source_path = source["path"] if credentials is source["data"] else str(settings.CODEX_CACHE_DIR / "codex_auth.json")
        elif cache:
            credentials = cache
            source_path = str(settings.CODEX_CACHE_DIR / "codex_auth.json")
        if not credentials:
            return {"ready": False, "reason": "No Codex CLI credentials found."}
        credentials = self.auth_manager.refresh_if_needed(credentials)
        self.store.save_local_cache(credentials)
        return {
            "ready": not credentials.get("refresh_required", False),
            "reason": "" if not credentials.get("refresh_required") else "Credentials need refresh.",
            "credentials": credentials,
            "source_path": source_path,
            "summary": self.auth_manager.summarize_credentials(credentials),
        }

    def get_bearer_token(self):
        auth_state = self.ensure_ready()
        if not auth_state["ready"]:
            raise RuntimeError(auth_state["reason"] or "Codex provider is unavailable.")
        return auth_state["credentials"]["tokens"]["access_token"]
