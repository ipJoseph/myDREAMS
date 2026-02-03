"""Linear GraphQL API client."""

import logging
from typing import Optional
import httpx

from .config import config
from .models import (
    LinearIssue,
    LinearTeam,
    LinearProject,
    LinearLabel,
    LinearWorkflowState,
)

logger = logging.getLogger(__name__)


class LinearClient:
    """GraphQL client for Linear API."""

    def __init__(self):
        self.api_url = config.LINEAR_API_URL
        self.api_key = config.LINEAR_API_KEY

    def _get_headers(self) -> dict:
        """Get request headers."""
        return {
            'Content-Type': 'application/json',
            'Authorization': self.api_key,
        }

    def _request(self, query: str, variables: dict = None, timeout: int = 30) -> dict:
        """Make a GraphQL request to Linear API."""
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                self.api_url,
                json=payload,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            result = response.json()

            if 'errors' in result:
                errors = result['errors']
                logger.error(f"GraphQL errors: {errors}")
                raise Exception(f"GraphQL error: {errors[0].get('message', str(errors))}")

            return result.get('data', {})

    # =========================================================================
    # VIEWER / AUTH
    # =========================================================================

    def test_connection(self) -> dict:
        """Test API connection and return viewer info."""
        query = """
        query {
            viewer {
                id
                name
                email
            }
        }
        """
        data = self._request(query)
        return data.get('viewer', {})

    # =========================================================================
    # TEAMS
    # =========================================================================

    def get_teams(self) -> list[LinearTeam]:
        """Get all teams in the workspace."""
        query = """
        query {
            teams {
                nodes {
                    id
                    name
                    key
                    states {
                        nodes {
                            id
                            name
                            type
                            position
                        }
                    }
                }
            }
        }
        """
        data = self._request(query)
        nodes = data.get('teams', {}).get('nodes', [])
        return [LinearTeam.from_api(t) for t in nodes]

    def get_team(self, team_id: str) -> Optional[LinearTeam]:
        """Get a specific team by ID."""
        query = """
        query GetTeam($id: String!) {
            team(id: $id) {
                id
                name
                key
                states {
                    nodes {
                        id
                        name
                        type
                        position
                    }
                }
            }
        }
        """
        data = self._request(query, {'id': team_id})
        team_data = data.get('team')
        return LinearTeam.from_api(team_data) if team_data else None

    def get_team_by_key(self, key: str) -> Optional[LinearTeam]:
        """Get a team by its key (e.g., 'DEV', 'TRX')."""
        teams = self.get_teams()
        for team in teams:
            if team.key.upper() == key.upper():
                return team
        return None

    def create_team(self, name: str, key: str, description: str = '') -> LinearTeam:
        """Create a new team."""
        mutation = """
        mutation CreateTeam($input: TeamCreateInput!) {
            teamCreate(input: $input) {
                success
                team {
                    id
                    name
                    key
                    states {
                        nodes {
                            id
                            name
                            type
                            position
                        }
                    }
                }
            }
        }
        """
        input_data = {'name': name, 'key': key}
        if description:
            input_data['description'] = description

        data = self._request(mutation, {'input': input_data})
        result = data.get('teamCreate', {})
        if not result.get('success'):
            raise Exception(f"Failed to create team: {name}")

        return LinearTeam.from_api(result['team'])

    # =========================================================================
    # WORKFLOW STATES
    # =========================================================================

    def get_workflow_states(self, team_id: str) -> list[LinearWorkflowState]:
        """Get workflow states for a team."""
        query = """
        query GetStates($teamId: String!) {
            team(id: $teamId) {
                states {
                    nodes {
                        id
                        name
                        type
                        position
                        team {
                            id
                        }
                    }
                }
            }
        }
        """
        data = self._request(query, {'teamId': team_id})
        nodes = data.get('team', {}).get('states', {}).get('nodes', [])
        return [LinearWorkflowState.from_api(s) for s in nodes]

    def get_state_by_name(self, team_id: str, state_name: str) -> Optional[LinearWorkflowState]:
        """Get a workflow state by name within a team."""
        states = self.get_workflow_states(team_id)
        for state in states:
            if state.name.lower() == state_name.lower():
                return state
        return None

    def get_initial_state(self, team_id: str) -> Optional[LinearWorkflowState]:
        """Get the initial (unstarted/backlog) state for a team."""
        states = self.get_workflow_states(team_id)
        # Prefer 'unstarted' or 'backlog' type, lowest position
        candidates = [s for s in states if s.type in ('unstarted', 'backlog', 'triage')]
        if candidates:
            return min(candidates, key=lambda s: s.position)
        return states[0] if states else None

    def get_completed_state(self, team_id: str) -> Optional[LinearWorkflowState]:
        """Get the completed state for a team."""
        states = self.get_workflow_states(team_id)
        for state in states:
            if state.type == 'completed':
                return state
        return None

    def create_workflow_state(
        self,
        team_id: str,
        name: str,
        state_type: str,
        color: str = '#95a2b3',
        position: Optional[float] = None,
        description: str = '',
    ) -> LinearWorkflowState:
        """Create a new workflow state.

        state_type must be one of: 'triage', 'backlog', 'unstarted', 'started', 'completed', 'canceled'
        """
        mutation = """
        mutation CreateWorkflowState($input: WorkflowStateCreateInput!) {
            workflowStateCreate(input: $input) {
                success
                workflowState {
                    id
                    name
                    type
                    position
                    team {
                        id
                    }
                }
            }
        }
        """
        input_data = {
            'teamId': team_id,
            'name': name,
            'type': state_type,
            'color': color,
        }
        if position is not None:
            input_data['position'] = position
        if description:
            input_data['description'] = description

        data = self._request(mutation, {'input': input_data})
        result = data.get('workflowStateCreate', {})
        if not result.get('success'):
            raise Exception(f"Failed to create workflow state: {name}")

        return LinearWorkflowState.from_api(result['workflowState'])

    def update_workflow_state(
        self,
        state_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
        position: Optional[float] = None,
    ) -> LinearWorkflowState:
        """Update an existing workflow state."""
        mutation = """
        mutation UpdateWorkflowState($id: String!, $input: WorkflowStateUpdateInput!) {
            workflowStateUpdate(id: $id, input: $input) {
                success
                workflowState {
                    id
                    name
                    type
                    position
                    team {
                        id
                    }
                }
            }
        }
        """
        input_data = {}
        if name is not None:
            input_data['name'] = name
        if color is not None:
            input_data['color'] = color
        if position is not None:
            input_data['position'] = position

        data = self._request(mutation, {'id': state_id, 'input': input_data})
        result = data.get('workflowStateUpdate', {})
        if not result.get('success'):
            raise Exception(f"Failed to update workflow state: {state_id}")

        return LinearWorkflowState.from_api(result['workflowState'])

    def archive_workflow_state(self, state_id: str) -> bool:
        """Archive a workflow state."""
        mutation = """
        mutation ArchiveWorkflowState($id: String!) {
            workflowStateArchive(id: $id) {
                success
            }
        }
        """
        data = self._request(mutation, {'id': state_id})
        return data.get('workflowStateArchive', {}).get('success', False)

    # =========================================================================
    # LABELS
    # =========================================================================

    def get_labels(self, team_id: Optional[str] = None) -> list[LinearLabel]:
        """Get labels, optionally filtered by team."""
        if team_id:
            query = """
            query GetLabels($teamId: String!) {
                team(id: $teamId) {
                    labels {
                        nodes {
                            id
                            name
                            color
                            parent {
                                id
                            }
                        }
                    }
                }
            }
            """
            data = self._request(query, {'teamId': team_id})
            nodes = data.get('team', {}).get('labels', {}).get('nodes', [])
        else:
            # Workspace-wide labels
            query = """
            query {
                issueLabels {
                    nodes {
                        id
                        name
                        color
                        parent {
                            id
                        }
                    }
                }
            }
            """
            data = self._request(query)
            nodes = data.get('issueLabels', {}).get('nodes', [])

        return [LinearLabel.from_api(l) for l in nodes]

    def create_label(self, name: str, team_id: Optional[str] = None,
                     color: str = '#888888', parent_id: Optional[str] = None) -> LinearLabel:
        """Create a new label."""
        mutation = """
        mutation CreateLabel($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) {
                success
                issueLabel {
                    id
                    name
                    color
                    parent {
                        id
                    }
                }
            }
        }
        """
        input_data = {'name': name, 'color': color}
        if team_id:
            input_data['teamId'] = team_id
        if parent_id:
            input_data['parentId'] = parent_id

        data = self._request(mutation, {'input': input_data})
        result = data.get('issueLabelCreate', {})
        if not result.get('success'):
            raise Exception(f"Failed to create label: {name}")

        return LinearLabel.from_api(result['issueLabel'])

    def get_or_create_label(self, name: str, team_id: Optional[str] = None,
                            color: str = '#888888') -> LinearLabel:
        """Get existing label or create if not exists."""
        labels = self.get_labels(team_id)
        for label in labels:
            if label.name.lower() == name.lower():
                return label

        return self.create_label(name, team_id, color)

    # =========================================================================
    # PROJECTS
    # =========================================================================

    def get_projects(self, team_id: Optional[str] = None) -> list[LinearProject]:
        """Get projects, optionally filtered by team."""
        if team_id:
            query = """
            query GetProjects($teamId: String!) {
                team(id: $teamId) {
                    projects {
                        nodes {
                            id
                            name
                            state
                            targetDate
                            lead {
                                id
                            }
                            teams {
                                nodes {
                                    id
                                }
                            }
                        }
                    }
                }
            }
            """
            data = self._request(query, {'teamId': team_id})
            nodes = data.get('team', {}).get('projects', {}).get('nodes', [])
        else:
            query = """
            query {
                projects {
                    nodes {
                        id
                        name
                        state
                        targetDate
                        lead {
                            id
                        }
                        teams {
                            nodes {
                                id
                            }
                        }
                    }
                }
            }
            """
            data = self._request(query)
            nodes = data.get('projects', {}).get('nodes', [])

        return [LinearProject.from_api(p) for p in nodes]

    def create_project(self, name: str, team_ids: list[str],
                       target_date: Optional[str] = None) -> LinearProject:
        """Create a new project."""
        mutation = """
        mutation CreateProject($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project {
                    id
                    name
                    state
                    targetDate
                    teams {
                        nodes {
                            id
                        }
                    }
                }
            }
        }
        """
        input_data = {'name': name, 'teamIds': team_ids}
        if target_date:
            input_data['targetDate'] = target_date

        data = self._request(mutation, {'input': input_data})
        result = data.get('projectCreate', {})
        if not result.get('success'):
            raise Exception(f"Failed to create project: {name}")

        return LinearProject.from_api(result['project'])

    def get_or_create_project(self, name: str, team_id: str) -> LinearProject:
        """Get existing project or create if not exists."""
        projects = self.get_projects(team_id)
        for project in projects:
            if project.name.lower() == name.lower():
                return project

        return self.create_project(name, [team_id])

    # =========================================================================
    # ISSUES
    # =========================================================================

    def get_issue(self, issue_id: str) -> Optional[LinearIssue]:
        """Get a specific issue by ID."""
        query = """
        query GetIssue($id: String!) {
            issue(id: $id) {
                id
                identifier
                title
                description
                priority
                state {
                    id
                    name
                    type
                }
                team {
                    id
                    name
                }
                project {
                    id
                    name
                }
                assignee {
                    id
                }
                dueDate
                completedAt
                canceledAt
                createdAt
                updatedAt
                labels {
                    nodes {
                        id
                        name
                    }
                }
                parent {
                    id
                }
            }
        }
        """
        data = self._request(query, {'id': issue_id})
        issue_data = data.get('issue')
        return LinearIssue.from_api(issue_data) if issue_data else None

    def get_issues(
        self,
        team_id: Optional[str] = None,
        project_id: Optional[str] = None,
        state_type: Optional[str] = None,
        label_ids: Optional[list[str]] = None,
        updated_after: Optional[str] = None,
        include_completed: bool = False,
        limit: int = 50,
    ) -> list[LinearIssue]:
        """Query issues with filters."""
        # Build filter
        filters = []

        if team_id:
            filters.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')

        if project_id:
            filters.append(f'project: {{ id: {{ eq: "{project_id}" }} }}')

        if state_type:
            filters.append(f'state: {{ type: {{ eq: "{state_type}" }} }}')
        elif not include_completed:
            # Exclude completed and canceled by default
            filters.append('state: { type: { nin: ["completed", "canceled"] } }')

        if label_ids:
            label_filter = ', '.join(f'{{ id: {{ eq: "{lid}" }} }}' for lid in label_ids)
            filters.append(f'labels: {{ or: [{label_filter}] }}')

        if updated_after:
            filters.append(f'updatedAt: {{ gte: "{updated_after}" }}')

        filter_str = ', '.join(filters) if filters else ''

        query = f"""
        query GetIssues($first: Int!) {{
            issues(first: $first, filter: {{ {filter_str} }}, orderBy: updatedAt) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    priority
                    state {{
                        id
                        name
                        type
                    }}
                    team {{
                        id
                        name
                    }}
                    project {{
                        id
                        name
                    }}
                    assignee {{
                        id
                    }}
                    dueDate
                    completedAt
                    canceledAt
                    createdAt
                    updatedAt
                    labels {{
                        nodes {{
                            id
                            name
                        }}
                    }}
                    parent {{
                        id
                    }}
                }}
            }}
        }}
        """

        data = self._request(query, {'first': limit})
        nodes = data.get('issues', {}).get('nodes', [])
        return [LinearIssue.from_api(i) for i in nodes]

    def create_issue(
        self,
        title: str,
        team_id: str,
        description: str = '',
        priority: int = 0,
        state_id: Optional[str] = None,
        project_id: Optional[str] = None,
        label_ids: Optional[list[str]] = None,
        due_date: Optional[str] = None,
        assignee_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> LinearIssue:
        """Create a new issue."""
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    description
                    priority
                    state {
                        id
                        name
                        type
                    }
                    team {
                        id
                        name
                    }
                    project {
                        id
                        name
                    }
                    assignee {
                        id
                    }
                    dueDate
                    completedAt
                    createdAt
                    updatedAt
                    labels {
                        nodes {
                            id
                            name
                        }
                    }
                }
            }
        }
        """
        input_data = {
            'title': title,
            'teamId': team_id,
        }
        if description:
            input_data['description'] = description
        if priority:
            input_data['priority'] = priority
        if state_id:
            input_data['stateId'] = state_id
        if project_id:
            input_data['projectId'] = project_id
        if label_ids:
            input_data['labelIds'] = label_ids
        if due_date:
            input_data['dueDate'] = due_date
        if assignee_id:
            input_data['assigneeId'] = assignee_id
        if parent_id:
            input_data['parentId'] = parent_id

        data = self._request(mutation, {'input': input_data})
        result = data.get('issueCreate', {})
        if not result.get('success'):
            raise Exception(f"Failed to create issue: {title}")

        return LinearIssue.from_api(result['issue'])

    def update_issue(
        self,
        issue_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        state_id: Optional[str] = None,
        project_id: Optional[str] = None,
        label_ids: Optional[list[str]] = None,
        due_date: Optional[str] = None,
        assignee_id: Optional[str] = None,
    ) -> LinearIssue:
        """Update an existing issue."""
        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    description
                    priority
                    state {
                        id
                        name
                        type
                    }
                    team {
                        id
                        name
                    }
                    project {
                        id
                        name
                    }
                    assignee {
                        id
                    }
                    dueDate
                    completedAt
                    canceledAt
                    createdAt
                    updatedAt
                    labels {
                        nodes {
                            id
                            name
                        }
                    }
                }
            }
        }
        """
        input_data = {}
        if title is not None:
            input_data['title'] = title
        if description is not None:
            input_data['description'] = description
        if priority is not None:
            input_data['priority'] = priority
        if state_id is not None:
            input_data['stateId'] = state_id
        if project_id is not None:
            input_data['projectId'] = project_id
        if label_ids is not None:
            input_data['labelIds'] = label_ids
        if due_date is not None:
            input_data['dueDate'] = due_date
        if assignee_id is not None:
            input_data['assigneeId'] = assignee_id

        data = self._request(mutation, {'id': issue_id, 'input': input_data})
        result = data.get('issueUpdate', {})
        if not result.get('success'):
            raise Exception(f"Failed to update issue: {issue_id}")

        return LinearIssue.from_api(result['issue'])

    def complete_issue(self, issue_id: str) -> LinearIssue:
        """Mark an issue as completed."""
        issue = self.get_issue(issue_id)
        if not issue:
            raise Exception(f"Issue not found: {issue_id}")

        completed_state = self.get_completed_state(issue.team_id)
        if not completed_state:
            raise Exception(f"No completed state found for team: {issue.team_id}")

        return self.update_issue(issue_id, state_id=completed_state.id)

    def delete_issue(self, issue_id: str) -> bool:
        """Archive (delete) an issue."""
        mutation = """
        mutation ArchiveIssue($id: String!) {
            issueArchive(id: $id) {
                success
            }
        }
        """
        data = self._request(mutation, {'id': issue_id})
        return data.get('issueArchive', {}).get('success', False)

    # =========================================================================
    # SYNC HELPERS
    # =========================================================================

    def get_issues_updated_since(self, since: str, team_id: Optional[str] = None) -> list[LinearIssue]:
        """Get issues updated since a given timestamp."""
        return self.get_issues(
            team_id=team_id,
            updated_after=since,
            include_completed=True,
            limit=100,
        )


# Module-level singleton
linear_client = LinearClient()
