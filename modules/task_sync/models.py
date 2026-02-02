"""
Data models for Task Sync module.

Unified task representation that bridges Todoist and FUB.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class TaskOrigin(str, Enum):
    """Where the task was originally created."""
    TODOIST = 'todoist'
    FUB = 'fub'


class SyncStatus(str, Enum):
    """Current sync status of a task mapping."""
    SYNCED = 'synced'
    PENDING_TO_TODOIST = 'pending_to_todoist'
    PENDING_TO_FUB = 'pending_to_fub'
    CONFLICT = 'conflict'
    ERROR = 'error'


@dataclass
class FUBTask:
    """Task from Follow Up Boss."""
    id: int
    person_id: int
    name: str
    type: str  # Call, Email, Follow Up, etc.
    is_completed: bool
    due_date: Optional[str] = None
    due_datetime: Optional[str] = None
    assigned_user_id: Optional[int] = None
    assigned_to: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    completed: Optional[str] = None
    created_by: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> 'FUBTask':
        """Create from FUB API response."""
        return cls(
            id=data['id'],
            person_id=data['personId'],
            name=data['name'],
            type=data.get('type', 'Follow Up'),
            is_completed=bool(data.get('isCompleted', 0)),
            due_date=data.get('dueDate'),
            due_datetime=data.get('dueDateTime'),
            assigned_user_id=data.get('assignedUserId'),
            assigned_to=data.get('AssignedTo'),
            created=data.get('created'),
            updated=data.get('updated'),
            completed=data.get('completed'),
            created_by=data.get('createdBy'),
        )


@dataclass
class TodoistTask:
    """Task from Todoist."""
    id: str
    content: str
    description: str = ''
    project_id: Optional[str] = None
    section_id: Optional[str] = None
    parent_id: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    priority: int = 1  # 1-4, 4 being highest
    due_date: Optional[str] = None
    due_datetime: Optional[str] = None
    is_completed: bool = False
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> 'TodoistTask':
        """Create from Todoist API response."""
        due = data.get('due', {}) or {}
        return cls(
            id=str(data['id']),
            content=data['content'],
            description=data.get('description', ''),
            project_id=str(data['project_id']) if data.get('project_id') else None,
            section_id=str(data['section_id']) if data.get('section_id') else None,
            parent_id=str(data['parent_id']) if data.get('parent_id') else None,
            labels=data.get('labels', []),
            priority=data.get('priority', 1),
            due_date=due.get('date'),
            due_datetime=due.get('datetime'),
            is_completed=data.get('is_completed', False),
            created_at=data.get('created_at'),
            completed_at=data.get('completed_at'),
        )


@dataclass
class UnifiedTask:
    """
    Internal task representation that both systems map to/from.

    This is the canonical format used during sync operations.
    """
    title: str
    description: str = ''
    due_date: Optional[str] = None
    due_datetime: Optional[str] = None
    is_completed: bool = False
    priority: int = 1  # 1-4
    labels: list[str] = field(default_factory=list)

    # FUB-specific
    fub_task_id: Optional[int] = None
    fub_person_id: Optional[int] = None
    fub_deal_id: Optional[int] = None
    fub_task_type: str = 'Follow Up'

    # Todoist-specific
    todoist_task_id: Optional[str] = None
    todoist_project_id: Optional[str] = None
    todoist_section_id: Optional[str] = None

    # Sync metadata
    origin: TaskOrigin = TaskOrigin.FUB
    fub_updated_at: Optional[str] = None
    todoist_updated_at: Optional[str] = None

    @classmethod
    def from_fub(cls, task: FUBTask, deal_id: Optional[int] = None) -> 'UnifiedTask':
        """Create from FUB task."""
        # Map FUB task type to priority
        priority_map = {
            'Call': 4,
            'Appointment': 4,
            'Follow Up': 2,
            'Email': 2,
            'Text': 2,
            'Other': 1,
        }
        priority = priority_map.get(task.type, 2)

        return cls(
            title=task.name,
            due_date=task.due_date,
            due_datetime=task.due_datetime,
            is_completed=task.is_completed,
            priority=priority,
            fub_task_id=task.id,
            fub_person_id=task.person_id,
            fub_deal_id=deal_id,
            fub_task_type=task.type,
            origin=TaskOrigin.FUB,
            fub_updated_at=task.updated,
        )

    @classmethod
    def from_todoist(cls, task: TodoistTask, fub_person_id: Optional[int] = None, fub_deal_id: Optional[int] = None) -> 'UnifiedTask':
        """Create from Todoist task."""
        return cls(
            title=task.content,
            description=task.description,
            due_date=task.due_date,
            due_datetime=task.due_datetime,
            is_completed=task.is_completed,
            priority=task.priority,
            labels=task.labels,
            todoist_task_id=task.id,
            todoist_project_id=task.project_id,
            todoist_section_id=task.section_id,
            fub_person_id=fub_person_id,
            fub_deal_id=fub_deal_id,
            origin=TaskOrigin.TODOIST,
            todoist_updated_at=task.created_at,  # Todoist doesn't expose updated_at easily
        )


@dataclass
class FUBDeal:
    """Deal from Follow Up Boss."""
    id: int
    person_id: int
    pipeline_id: Optional[int] = None
    stage_id: Optional[int] = None
    stage_name: Optional[str] = None
    name: Optional[str] = None
    deal_value: Optional[float] = None
    property_address: Optional[str] = None
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> 'FUBDeal':
        """Create from FUB API response."""
        return cls(
            id=data['id'],
            person_id=data['personId'],
            pipeline_id=data.get('pipelineId'),
            stage_id=data.get('stageId'),
            stage_name=data.get('stageName'),
            name=data.get('name'),
            deal_value=data.get('dealValue'),
            property_address=data.get('propertyAddress'),
            property_city=data.get('propertyCity'),
            property_state=data.get('propertyState'),
            property_zip=data.get('propertyZip'),
            created=data.get('created'),
            updated=data.get('updated'),
        )


@dataclass
class FUBPipeline:
    """Pipeline from Follow Up Boss."""
    id: int
    name: str
    description: str = ''
    stages: list[dict] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict) -> 'FUBPipeline':
        """Create from FUB API response."""
        return cls(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            stages=data.get('stages', []),
        )
