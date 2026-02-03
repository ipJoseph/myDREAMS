"""Data models for Linear Sync module."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskOrigin(Enum):
    """Origin of a task/issue."""
    LINEAR = 'linear'
    FUB = 'fub'


class SyncStatus(Enum):
    """Sync status for mappings."""
    SYNCED = 'synced'
    PENDING_TO_LINEAR = 'pending_to_linear'
    PENDING_TO_FUB = 'pending_to_fub'
    CONFLICT = 'conflict'
    ERROR = 'error'


class LinearPriority(Enum):
    """Linear priority levels (0=none, 1=urgent, 2=high, 3=medium, 4=low)."""
    NONE = 0
    URGENT = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


# Real Estate Process Phases
class BuyerPhase(Enum):
    """Buyer journey phases."""
    QUALIFY = 'qualify'  # Lead qualification
    CURATE = 'curate'    # Property search & showings
    ACQUIRE = 'acquire'  # Making offers
    CLOSE = 'close'      # Under contract to closing


class ProcessGroup(Enum):
    """Linear team process groups."""
    DEVELOP = 'develop'    # Qualify + Curate
    TRANSACT = 'transact'  # Acquire + Close
    GENERAL = 'general'    # Admin, marketing, ops


@dataclass
class LinearLabel:
    """Linear label."""
    id: str
    name: str
    color: str = ''
    parent_id: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> 'LinearLabel':
        """Create from Linear API response."""
        return cls(
            id=data['id'],
            name=data['name'],
            color=data.get('color', ''),
            parent_id=data.get('parent', {}).get('id') if data.get('parent') else None,
        )


@dataclass
class LinearWorkflowState:
    """Linear workflow state."""
    id: str
    name: str
    type: str  # 'triage', 'backlog', 'unstarted', 'started', 'completed', 'canceled'
    position: float
    team_id: str

    @classmethod
    def from_api(cls, data: dict) -> 'LinearWorkflowState':
        """Create from Linear API response."""
        return cls(
            id=data['id'],
            name=data['name'],
            type=data['type'],
            position=data.get('position', 0),
            team_id=data.get('team', {}).get('id', ''),
        )


@dataclass
class LinearTeam:
    """Linear team."""
    id: str
    name: str
    key: str  # Short code like "DEV" or "TRX"
    workflow_states: list[LinearWorkflowState] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict) -> 'LinearTeam':
        """Create from Linear API response."""
        states = []
        if 'states' in data and 'nodes' in data['states']:
            states = [LinearWorkflowState.from_api(s) for s in data['states']['nodes']]

        return cls(
            id=data['id'],
            name=data['name'],
            key=data['key'],
            workflow_states=states,
        )


@dataclass
class LinearProject:
    """Linear project."""
    id: str
    name: str
    state: str  # 'planned', 'started', 'paused', 'completed', 'canceled'
    team_ids: list[str] = field(default_factory=list)
    target_date: Optional[str] = None
    lead_id: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> 'LinearProject':
        """Create from Linear API response."""
        team_ids = []
        if 'teams' in data and 'nodes' in data['teams']:
            team_ids = [t['id'] for t in data['teams']['nodes']]

        return cls(
            id=data['id'],
            name=data['name'],
            state=data.get('state', 'planned'),
            team_ids=team_ids,
            target_date=data.get('targetDate'),
            lead_id=data.get('lead', {}).get('id') if data.get('lead') else None,
        )


@dataclass
class LinearIssue:
    """Linear issue (task)."""
    id: str
    identifier: str  # e.g., "DEV-123"
    title: str
    description: str = ''
    priority: int = 0  # 0=none, 1=urgent, 2=high, 3=medium, 4=low
    state_id: str = ''
    state_name: str = ''
    state_type: str = ''
    team_id: str = ''
    team_name: str = ''
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    assignee_id: Optional[str] = None
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    canceled_at: Optional[str] = None
    created_at: str = ''
    updated_at: str = ''
    label_ids: list[str] = field(default_factory=list)
    label_names: list[str] = field(default_factory=list)
    parent_id: Optional[str] = None  # For sub-issues

    @classmethod
    def from_api(cls, data: dict) -> 'LinearIssue':
        """Create from Linear API response."""
        labels = data.get('labels', {}).get('nodes', [])

        return cls(
            id=data['id'],
            identifier=data.get('identifier', ''),
            title=data['title'],
            description=data.get('description', '') or '',
            priority=data.get('priority', 0),
            state_id=data.get('state', {}).get('id', ''),
            state_name=data.get('state', {}).get('name', ''),
            state_type=data.get('state', {}).get('type', ''),
            team_id=data.get('team', {}).get('id', ''),
            team_name=data.get('team', {}).get('name', ''),
            project_id=data.get('project', {}).get('id') if data.get('project') else None,
            project_name=data.get('project', {}).get('name') if data.get('project') else None,
            assignee_id=data.get('assignee', {}).get('id') if data.get('assignee') else None,
            due_date=data.get('dueDate'),
            completed_at=data.get('completedAt'),
            canceled_at=data.get('canceledAt'),
            created_at=data.get('createdAt', ''),
            updated_at=data.get('updatedAt', ''),
            label_ids=[l['id'] for l in labels],
            label_names=[l['name'] for l in labels],
            parent_id=data.get('parent', {}).get('id') if data.get('parent') else None,
        )

    @property
    def is_completed(self) -> bool:
        """Check if issue is in a completed state."""
        return self.state_type == 'completed' or bool(self.completed_at)

    @property
    def is_canceled(self) -> bool:
        """Check if issue is canceled."""
        return self.state_type == 'canceled' or bool(self.canceled_at)


@dataclass
class FUBTask:
    """Task from Follow Up Boss."""
    id: int
    person_id: int
    name: str
    type: str  # 'Call', 'Email', 'Todo', 'Showing', etc.
    is_completed: bool
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    note: str = ''
    assigned_user_id: Optional[int] = None
    created: str = ''
    updated: str = ''

    @classmethod
    def from_api(cls, data: dict) -> 'FUBTask':
        """Create from FUB API response."""
        return cls(
            id=data['id'],
            person_id=data.get('personId', 0),
            name=data.get('name', ''),
            type=data.get('type', 'Todo'),
            is_completed=data.get('isCompleted', False),
            due_date=data.get('dueDate'),
            due_time=data.get('dueTime'),
            note=data.get('note', '') or '',
            assigned_user_id=data.get('assignedUserId'),
            created=data.get('created', ''),
            updated=data.get('updated', ''),
        )


@dataclass
class FUBPerson:
    """Person from Follow Up Boss."""
    id: int
    name: str
    first_name: str = ''
    last_name: str = ''
    email: str = ''
    phone: str = ''
    stage: str = ''
    source: str = ''
    assigned_user_id: Optional[int] = None

    @classmethod
    def from_api(cls, data: dict) -> 'FUBPerson':
        """Create from FUB API response."""
        # Build display name
        first = data.get('firstName', '') or ''
        last = data.get('lastName', '') or ''
        name = f"{first} {last}".strip() or data.get('name', '')

        # Get primary email
        emails = data.get('emails', [])
        email = emails[0].get('value', '') if emails else ''

        # Get primary phone
        phones = data.get('phones', [])
        phone = phones[0].get('value', '') if phones else ''

        return cls(
            id=data['id'],
            name=name,
            first_name=first,
            last_name=last,
            email=email,
            phone=phone,
            stage=data.get('stage', ''),
            source=data.get('source', ''),
            assigned_user_id=data.get('assignedUserId'),
        )


@dataclass
class FUBDeal:
    """Deal from Follow Up Boss."""
    id: int
    person_id: int
    name: str = ''
    stage_id: Optional[int] = None
    stage_name: str = ''
    pipeline_id: Optional[int] = None
    pipeline_name: str = ''
    price: float = 0.0
    property_address: str = ''
    property_city: str = ''
    property_state: str = ''
    close_date: Optional[str] = None
    created: str = ''
    updated: str = ''

    @classmethod
    def from_api(cls, data: dict) -> 'FUBDeal':
        """Create from FUB API response."""
        return cls(
            id=data['id'],
            person_id=data.get('personId', 0),
            name=data.get('name', ''),
            stage_id=data.get('stageId'),
            stage_name=data.get('stageName', ''),
            pipeline_id=data.get('pipelineId'),
            pipeline_name=data.get('pipelineName', ''),
            price=float(data.get('price', 0) or 0),
            property_address=data.get('propertyStreet', ''),
            property_city=data.get('propertyCity', ''),
            property_state=data.get('propertyState', ''),
            close_date=data.get('closeDate'),
            created=data.get('created', ''),
            updated=data.get('updated', ''),
        )


# FUB Deal Stage to Linear Team/State Mapping
FUB_STAGE_TO_TEAM = {
    # =========================================================================
    # DEVELOP team (Qualify + Curate) - Lead nurturing, pre-offer
    # =========================================================================
    'new deal': ProcessGroup.DEVELOP,
    'lead': ProcessGroup.DEVELOP,
    'new': ProcessGroup.DEVELOP,
    'buyer contract': ProcessGroup.DEVELOP,
    'listing contract': ProcessGroup.DEVELOP,
    'listed': ProcessGroup.DEVELOP,
    'contract': ProcessGroup.DEVELOP,
    'qualified': ProcessGroup.DEVELOP,
    'searching': ProcessGroup.DEVELOP,
    'showing': ProcessGroup.DEVELOP,
    'referral contract': ProcessGroup.DEVELOP,

    # =========================================================================
    # TRANSACT team (Acquire + Close) - Active offers through closing
    # =========================================================================
    'offer': ProcessGroup.TRANSACT,
    'pending': ProcessGroup.TRANSACT,
    'under contract': ProcessGroup.TRANSACT,
    'inspection': ProcessGroup.TRANSACT,
    'appraisal': ProcessGroup.TRANSACT,
    'closing': ProcessGroup.TRANSACT,
    'closed': ProcessGroup.TRANSACT,
    'closed 2025': ProcessGroup.TRANSACT,
    'closed old': ProcessGroup.TRANSACT,

    # =========================================================================
    # GENERAL team - Non-active, admin
    # =========================================================================
    'terminated': ProcessGroup.GENERAL,
    'referral': ProcessGroup.GENERAL,
}


def get_team_for_stage(stage_name: str) -> ProcessGroup:
    """Get the Linear team for a FUB deal stage."""
    stage_lower = stage_name.lower().strip()
    return FUB_STAGE_TO_TEAM.get(stage_lower, ProcessGroup.DEVELOP)


# FUB Task Type to Linear Priority
FUB_TYPE_TO_PRIORITY = {
    'call': LinearPriority.HIGH,
    'showing': LinearPriority.HIGH,
    'offer': LinearPriority.URGENT,
    'email': LinearPriority.MEDIUM,
    'todo': LinearPriority.MEDIUM,
    'text': LinearPriority.MEDIUM,
    'follow-up': LinearPriority.MEDIUM,
    'appointment': LinearPriority.HIGH,
}


def get_priority_for_type(task_type: str) -> int:
    """Get Linear priority value for a FUB task type."""
    type_lower = task_type.lower().strip()
    priority = FUB_TYPE_TO_PRIORITY.get(type_lower, LinearPriority.MEDIUM)
    return priority.value
