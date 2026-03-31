from planner.services.codex_provider import CodexProvider, CodexProviderError


def build_diff_payload(old_blocks, new_blocks, trigger):
    old_lookup = {(block.get("task_id"), block.get("start_datetime")) for block in old_blocks}
    new_lookup = {(block.get("task_id"), block.get("start_datetime")) for block in new_blocks}
    moved = len(new_lookup - old_lookup)
    return {
        "trigger": trigger,
        "old_count": len(old_blocks),
        "new_count": len(new_blocks),
        "moved_blocks": moved,
    }


def fallback_summary(diff_payload):
    return (
        f"Triggered by {diff_payload['trigger']}. "
        f"Schedule now has {diff_payload['new_count']} blocks; "
        f"{diff_payload['moved_blocks']} blocks changed position."
    )


def generate_summary(old_blocks, new_blocks, trigger):
    diff_payload = build_diff_payload(old_blocks, new_blocks, trigger)
    provider = CodexProvider()
    try:
        return provider.summarize_diff(old_blocks, new_blocks, trigger)
    except CodexProviderError:
        return fallback_summary(diff_payload)
