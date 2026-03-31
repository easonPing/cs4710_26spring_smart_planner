PRIORITY_CHOICES = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('urgent', 'Urgent'),
]

TASK_STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('todo', 'To Do'),
    ('in_progress', 'In Progress'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]

TASK_CATEGORY_CHOICES = [
    ('assignment', 'Assignment'),
    ('project', 'Project'),
    ('exam', 'Exam'),
    ('reading', 'Reading'),
    ('meeting', 'Meeting'),
    ('other', 'Other'),
]

EVENT_TYPE_CHOICES = [
    ('class', 'Class'),
    ('meeting', 'Meeting'),
    ('routine', 'Routine'),
    ('deadline', 'Deadline'),
    ('other', 'Other'),
]

BLOCK_TYPE_CHOICES = [
    ('task', 'Task'),
    ('class', 'Class'),
    ('meeting', 'Meeting'),
    ('sleep', 'Sleep'),
    ('meal', 'Meal'),
    ('break', 'Break'),
    ('other', 'Other'),
]

PATCH_TYPE_CHOICES = [
    ('add_event', 'Add Event'),
    ('task_done', 'Task Done'),
    ('change_estimate', 'Change Estimate'),
    ('custom', 'Custom'),
]
