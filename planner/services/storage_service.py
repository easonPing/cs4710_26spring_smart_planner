import json

from django.conf import settings


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _read_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_schedule_version(date, version, payload):
    path = settings.BASE_DIR / "data" / "schedule_versions" / f"{date}_v{version}.json"
    return _write_json(path, payload)


def load_schedule_version(date, version):
    path = settings.BASE_DIR / "data" / "schedule_versions" / f"{date}_v{version}.json"
    return _read_json(path)


def latest_schedule_version(date):
    schedule_dir = settings.BASE_DIR / "data" / "schedule_versions"
    versions = []
    for path in schedule_dir.glob(f"{date}_v*.json"):
        try:
            versions.append((int(path.stem.split("_v")[-1]), path))
        except ValueError:
            continue
    if not versions:
        return None
    version, path = sorted(versions, key=lambda item: item[0])[-1]
    return {"version": version, "payload": _read_json(path), "path": path}


def save_conflict_report(date, payload):
    path = settings.BASE_DIR / "data" / "conflict_reports" / f"{date}.json"
    return _write_json(path, payload)


def save_debug_snapshot(name, payload):
    path = settings.BASE_DIR / "data" / "debug_snapshots" / f"{name}.json"
    return _write_json(path, payload)


def mirror_codex_auth(auth_payload):
    path = settings.BASE_DIR / "data" / "oauth_cache" / "codex_auth.json"
    return _write_json(path, auth_payload)
