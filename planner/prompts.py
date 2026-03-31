def build_task_extraction_prompt(text_chunk):
    return (
        "Extract academic tasks from the syllabus chunk and return JSON with "
        "title, course_name, due_datetime, estimated_minutes, priority, "
        f"category, confidence, and raw_excerpt. Chunk:\n{text_chunk}"
    )


def build_patch_parsing_prompt(user_text):
    return (
        "Convert the user update into a JSON patch with a trigger_type and "
        f"payload. User text:\n{user_text}"
    )


def build_summary_prompt(old_blocks, new_blocks, trigger):
    return (
        "Summarize the schedule change in concise prose. "
        f"Trigger: {trigger}. Old blocks: {old_blocks}. New blocks: {new_blocks}."
    )
