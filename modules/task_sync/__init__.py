"""
Task Sync Module - Todoist ↔ Follow Up Boss

Bidirectional task synchronization with Deal-aware mapping.
"""

__version__ = "0.1.0"

# Dashboard integration exports
from .dashboard import (
    get_todoist_tasks_for_dashboard,
    get_task_stats,
    get_grouped_tasks,
    get_tasks_by_project,
)
