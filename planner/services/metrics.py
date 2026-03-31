from collections import Counter


def hard_conflict_count(schedule_blocks, fixed_events):
    conflicts = 0
    for block in schedule_blocks:
        for event in fixed_events:
            if block.start_datetime < event.end_datetime and block.end_datetime > event.start_datetime:
                conflicts += 1
    return conflicts


def deadline_buffer_minutes(tasks, schedule_blocks):
    by_task_id = {block.task_id: block for block in schedule_blocks if block.task_id}
    total_buffer = 0
    for task in tasks:
        block = by_task_id.get(task.id)
        if not block or not task.due_datetime:
            continue
        total_buffer += int((task.due_datetime - block.end_datetime).total_seconds() // 60)
    return total_buffer


def moved_block_count(old_blocks, new_blocks):
    old_positions = {(block.task_id, block.start_datetime, block.end_datetime) for block in old_blocks if block.task_id}
    new_positions = {(block.task_id, block.start_datetime, block.end_datetime) for block in new_blocks if block.task_id}
    return len(new_positions - old_positions)


def fragmentation_count(schedule_blocks):
    counter = Counter(block.task_id for block in schedule_blocks if block.task_id)
    return sum(max(count - 1, 0) for count in counter.values())


def weighted_completion_score(tasks):
    weights = {"low": 1, "medium": 2, "high": 3, "urgent": 4}
    total_weight = sum(weights[task.priority] for task in tasks)
    if not total_weight:
        return 0
    completed_weight = sum(weights[task.priority] for task in tasks if task.status == "done")
    return round(completed_weight / total_weight, 2)


def run_baseline_edf(tasks):
    return sorted(tasks, key=lambda task: (task.due_datetime is None, task.due_datetime))


def run_baseline_no_replan(schedule_blocks):
    return list(schedule_blocks)


def run_baseline_todo_only(tasks):
    return [task.title for task in tasks if task.status != "done"]
