def build_task_extraction_prompt(text_chunk):
    return (
        "Extract only real academic tasks or deliverables from the syllabus chunk. "
        "A task should usually be something the student must do, submit, prepare, "
        "or attend for credit, such as homework, lab prep, project milestone, exam, "
        "quiz, presentation, report, reading response, or writeup. "
        "Ignore non-task content such as accommodation policies, grading policy, "
        "attendance policy, office hours, contact info, textbook notes, course goals, "
        "late policy, honor policy, and generic schedule prose. "
        "Only include items with an explicit deadline or scheduled date/time. "
        "If an item is clearly a real deliverable but has no explicit deadline, include "
        "it only when confidence is extremely high and set due_datetime to null so it can "
        "be reviewed manually. "
        "Return JSON fields title, course_name, due_datetime, estimated_minutes, priority, "
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
