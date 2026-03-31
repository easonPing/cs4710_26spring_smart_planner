import math
from collections import defaultdict
from datetime import time, timedelta

from ortools.sat.python import cp_model

from django.conf import settings

from planner.utils import combine_date_time


def build_time_slots(date, slot_minutes=30):
    start = combine_date_time(date, time(0, 0))
    return [start + timedelta(minutes=slot_minutes * index) for index in range(int(24 * 60 / slot_minutes))]


def _blocked_slot_indexes(slots, fixed_events, slot_minutes):
    blocked = set()
    for fixed_event in fixed_events:
        for index, slot_start in enumerate(slots):
            slot_end = slot_start + timedelta(minutes=slot_minutes)
            if slot_start < fixed_event["end"] and slot_end > fixed_event["start"]:
                blocked.add(index)
    return blocked


def build_daily_model(tasks, fixed_events, profile, old_blocks=None):
    slot_minutes = settings.SLOT_MINUTES
    schedule_date = fixed_events[0]["start"].date()
    slots = build_time_slots(schedule_date, slot_minutes=slot_minutes)
    blocked = _blocked_slot_indexes(slots, fixed_events, slot_minutes)
    model = cp_model.CpModel()
    assignment = {}
    start_vars = {}
    for task in tasks:
        required_slots = max(1, math.ceil(task.remaining_minutes / slot_minutes))
        task_slot_vars = []
        for slot_index in range(len(slots)):
            if slot_index in blocked:
                continue
            variable = model.NewBoolVar(f"task_{task.id}_slot_{slot_index}")
            assignment[(task.id, slot_index)] = variable
            task_slot_vars.append(variable)
        if task_slot_vars:
            model.Add(sum(task_slot_vars) == required_slots)
        previous = None
        for slot_index in range(len(slots)):
            current = assignment.get((task.id, slot_index))
            if current is None:
                previous = None
                continue
            start_var = model.NewBoolVar(f"task_{task.id}_start_{slot_index}")
            start_vars[(task.id, slot_index)] = start_var
            if previous is None:
                model.Add(start_var == current)
            else:
                model.Add(start_var >= current - previous)
                model.Add(start_var <= current)
            previous = current
    for slot_index in range(len(slots)):
        slot_assignments = [assignment[(task.id, slot_index)] for task in tasks if (task.id, slot_index) in assignment]
        if slot_assignments:
            model.Add(sum(slot_assignments) <= 1)
    max_work_slots = max(1, profile.max_continuous_work_minutes // slot_minutes)
    for window_start in range(max(0, len(slots) - max_work_slots)):
        window_vars = []
        for slot_index in range(window_start, min(window_start + max_work_slots + 1, len(slots))):
            for task in tasks:
                variable = assignment.get((task.id, slot_index))
                if variable is not None:
                    window_vars.append(variable)
        if window_vars:
            model.Add(sum(window_vars) <= max_work_slots)
    objective_terms = []
    old_lookup = {(block.task_id, block.start_datetime) for block in (old_blocks or []) if block.task_id}
    preferred_start = profile.preferred_study_start.hour * 60 + profile.preferred_study_start.minute
    preferred_end = profile.preferred_study_end.hour * 60 + profile.preferred_study_end.minute
    for task in tasks:
        urgency = int(task.urgency_score())
        for slot_index, slot_start in enumerate(slots):
            variable = assignment.get((task.id, slot_index))
            if variable is None:
                continue
            slot_minutes_from_midnight = slot_start.hour * 60 + slot_start.minute
            earlier_bonus = len(slots) - slot_index
            preferred_bonus = 8 if preferred_start <= slot_minutes_from_midnight < preferred_end else 0
            stability_bonus = 12 if (task.id, slot_start) in old_lookup else 0
            objective_terms.append(variable * (urgency + earlier_bonus + preferred_bonus + stability_bonus))
    for start_var in start_vars.values():
        objective_terms.append(start_var * -5)
    model.Maximize(sum(objective_terms) if objective_terms else 0)
    return {
        "model": model,
        "slots": slots,
        "assignment": assignment,
        "blocked": blocked,
        "slot_minutes": slot_minutes,
    }


def add_fixed_event_constraints(model, slots, fixed_events):
    return model, slots, fixed_events


def add_sleep_constraints(model, slots, profile):
    return model, slots, profile


def add_meal_constraints(model, slots, profile):
    return model, slots, profile


def add_task_duration_constraints(model, task_vars, tasks):
    return model, task_vars, tasks


def add_non_overlap_constraints(model, task_intervals):
    return model, task_intervals


def add_break_constraints(model, slots, profile):
    return model, slots, profile


def add_preference_objective(model, *args, **kwargs):
    return model


def add_deadline_buffer_objective(model, *args, **kwargs):
    return model


def add_fragmentation_penalty(model, *args, **kwargs):
    return model


def add_movement_penalty(model, old_blocks, *args, **kwargs):
    return model, old_blocks


def solve_model(model, time_limit=None):
    solver = cp_model.CpSolver()
    if time_limit:
        solver.parameters.max_time_in_seconds = time_limit
    status = solver.Solve(model)
    return solver, status


def extract_schedule_blocks(solution, tasks, slots, assignment, slot_minutes):
    grouped = defaultdict(list)
    for task in tasks:
        for slot_index, slot_start in enumerate(slots):
            variable = assignment.get((task.id, slot_index))
            if variable is not None and solution.Value(variable):
                grouped[task].append(slot_start)
    blocks = []
    for task, task_slots in grouped.items():
        sorted_slots = sorted(task_slots)
        block_start = None
        previous = None
        for slot_start in sorted_slots:
            if block_start is None:
                block_start = slot_start
                previous = slot_start
                continue
            if slot_start - previous != timedelta(minutes=slot_minutes):
                blocks.append(
                    {
                        "title": f"Work on {task.title}",
                        "task": task,
                        "start_datetime": block_start,
                        "end_datetime": previous + timedelta(minutes=slot_minutes),
                        "block_type": "task",
                    }
                )
                block_start = slot_start
            previous = slot_start
        blocks.append(
            {
                "title": f"Work on {task.title}",
                "task": task,
                "start_datetime": block_start,
                "end_datetime": previous + timedelta(minutes=slot_minutes),
                "block_type": "task",
            }
        )
    return sorted(blocks, key=lambda block: block["start_datetime"])


def build_conflict_report(tasks, fixed_events, profile):
    return {
        "date": fixed_events[0]["start"].date().isoformat() if fixed_events else None,
        "feasible": False,
        "missing_minutes": sum(task.remaining_minutes for task in tasks),
        "unscheduled_tasks": [
            {
                "task_id": task.id,
                "title": task.title,
                "remaining_minutes": task.remaining_minutes,
            }
            for task in tasks
        ],
        "reason": "Insufficient free slots before due time or routine windows.",
    }


def generate_daily_schedule(date, profile, tasks, fixed_events, old_blocks=None):
    if not fixed_events:
        fixed_events = [
            {
                "start": combine_date_time(date, profile.sleep_start),
                "end": combine_date_time(date, profile.sleep_end) + timedelta(days=1 if profile.sleep_end <= profile.sleep_start else 0),
                "block_type": "sleep",
                "title": "Sleep",
            }
        ]
    bundle = build_daily_model(tasks, fixed_events, profile, old_blocks=old_blocks)
    solver, status = solve_model(bundle["model"], time_limit=10)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "feasible": False,
            "blocks": [],
            "conflict_report": build_conflict_report(tasks, fixed_events, profile),
        }
    blocks = extract_schedule_blocks(
        solver,
        tasks,
        bundle["slots"],
        bundle["assignment"],
        bundle["slot_minutes"],
    )
    return {
        "feasible": True,
        "blocks": blocks,
        "conflict_report": None,
    }
