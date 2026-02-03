"""Project factory for creating Linear projects from templates.

This module handles instantiating projects from phase templates, including:
- Creating the Linear project
- Creating milestones
- Creating issues within each milestone
- Applying person labels
- Recording in local database for tracking
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

from .config import config
from .db import db
from .linear_client import linear_client
from .fub_client import fub_client
from .models import (
    LinearProject,
    LinearMilestone,
    LinearIssue,
    BuyerPhase,
    ProcessGroup,
    FUBPerson,
)
from .templates import (
    ProjectTemplate,
    MilestoneTemplate,
    IssueTemplate,
    PHASE_TEMPLATES,
    get_template,
    get_template_by_name,
)

logger = logging.getLogger(__name__)


@dataclass
class ProjectCreationResult:
    """Result of project creation from template."""
    project: LinearProject
    milestones: list[LinearMilestone] = field(default_factory=list)
    issues: list[LinearIssue] = field(default_factory=list)
    person_label_id: Optional[str] = None
    error: Optional[str] = None


class ProjectFactory:
    """Factory for creating Linear projects from templates."""

    def __init__(self):
        self.linear = linear_client
        self.fub = fub_client
        self.db = db

    def get_team_id_for_process(self, process: ProcessGroup) -> Optional[str]:
        """Get Linear team ID for a process group."""
        team_key = process.value.upper()
        team_config = self.db.get_team_config(team_key)
        if team_config:
            return team_config['team_id']

        # Fallback to config
        if process == ProcessGroup.DEVELOP:
            return config.DEVELOP_TEAM_ID
        elif process == ProcessGroup.TRANSACT:
            return config.TRANSACT_TEAM_ID
        else:
            return config.GENERAL_TEAM_ID

    def get_or_create_person_label(self, person: FUBPerson) -> str:
        """Get or create a Linear label for a FUB person."""
        # Check cache first
        cached = self.db.get_person_label(person.id)
        if cached:
            return cached['linear_label_id']

        # Create label name (Last, First or just name)
        if person.last_name and person.first_name:
            label_name = f"{person.last_name}, {person.first_name}"
        else:
            label_name = person.name

        # Get or create in Linear (workspace-wide label)
        label = self.linear.get_or_create_label(label_name, color='#5E6AD2')

        # Cache mapping
        self.db.set_person_label(
            fub_person_id=person.id,
            fub_person_name=person.name,
            linear_label_id=label.id,
            linear_label_name=label.name,
        )

        return label.id

    def build_project_name(
        self,
        person_name: str,
        template: ProjectTemplate,
        property_address: Optional[str] = None,
    ) -> str:
        """Build the project name from person name, phase, and optional property."""
        name_parts = [person_name, template.name_suffix]
        if property_address:
            name_parts.append(property_address)
        return ' - '.join(name_parts)

    def check_existing_project(
        self,
        fub_person_id: int,
        phase: str,
        property_address: Optional[str] = None,
    ) -> Optional[dict]:
        """Check if a project already exists for this person/phase/property."""
        return self.db.get_project_for_person_phase(
            fub_person_id=fub_person_id,
            phase=phase,
            property_address=property_address,
        )

    def create_project_from_template(
        self,
        person: FUBPerson,
        phase: BuyerPhase,
        property_address: Optional[str] = None,
        skip_if_exists: bool = True,
    ) -> ProjectCreationResult:
        """Create a Linear project from a phase template.

        Args:
            person: FUB person to create project for
            phase: Buyer journey phase (QUALIFY, CURATE, ACQUIRE, CLOSE)
            property_address: Property address (required for ACQUIRE/CLOSE)
            skip_if_exists: If True, return existing project instead of creating new

        Returns:
            ProjectCreationResult with created project, milestones, and issues
        """
        template = get_template(phase)

        # Check if project already exists
        if skip_if_exists:
            existing = self.check_existing_project(
                fub_person_id=person.id,
                phase=phase.value,
                property_address=property_address,
            )
            if existing:
                logger.info(f"Project already exists for {person.name} - {phase.value}")
                # Fetch the actual project from Linear
                project = self.linear.get_project(existing['linear_project_id'])
                if project:
                    milestones = self.linear.get_milestones(project.id)
                    return ProjectCreationResult(
                        project=project,
                        milestones=milestones,
                        person_label_id=existing['person_label_id'],
                    )

        # Validate required fields for ACQUIRE/CLOSE
        if phase in (BuyerPhase.ACQUIRE, BuyerPhase.CLOSE) and not property_address:
            return ProjectCreationResult(
                project=None,
                error=f"Property address required for {phase.value} phase",
            )

        # Get team ID
        team_id = self.get_team_id_for_process(template.process_group)
        if not team_id:
            return ProjectCreationResult(
                project=None,
                error=f"No team configured for process group: {template.process_group.value}",
            )

        # Get or create person label
        person_label_id = self.get_or_create_person_label(person)

        # Build project name
        project_name = self.build_project_name(
            person_name=person.name,
            template=template,
            property_address=property_address,
        )

        logger.info(f"Creating project: {project_name}")

        # Create project in Linear
        project = self.linear.create_project(
            name=project_name,
            team_ids=[team_id],
            description=template.description,
            state='started',
        )

        # Store project instance in local DB FIRST (before milestones due to FK)
        self.db.create_project_instance(
            linear_project_id=project.id,
            linear_project_name=project_name,
            fub_person_id=person.id,
            fub_person_name=person.name,
            phase=phase.value,
            linear_team_id=team_id,
            property_address=property_address,
            person_label_id=person_label_id,
            issue_count=0,  # Will update after creating issues
        )

        # Track results
        milestones_created = []
        issues_created = []

        # Create milestones and issues
        for sort_order, milestone_template in enumerate(template.milestones):
            milestone = self.linear.create_milestone(
                project_id=project.id,
                name=milestone_template.name,
                description=milestone_template.description,
                sort_order=float(sort_order),
            )
            milestones_created.append(milestone)

            # Store milestone in local DB
            self.db.create_milestone_record(
                linear_milestone_id=milestone.id,
                linear_project_id=project.id,
                name=milestone.name,
                sort_order=float(sort_order),
            )

            # Create issues for this milestone
            for issue_template in milestone_template.issues:
                # Build label IDs
                label_ids = [person_label_id]

                # Add FUB-synced label if configured
                if config.FUB_SYNCED_LABEL_ID:
                    label_ids.append(config.FUB_SYNCED_LABEL_ID)

                issue = self.linear.create_issue(
                    title=issue_template.title,
                    team_id=team_id,
                    description=issue_template.description,
                    priority=issue_template.priority,
                    project_id=project.id,
                    project_milestone_id=milestone.id,
                    label_ids=label_ids,
                )
                issues_created.append(issue)

        # Update issue count in project instance
        self.db.update_project_instance(
            linear_project_id=project.id,
            completed_count=0,  # Just to trigger the update with correct issue_count
        )
        # Need to update issue_count separately since update_project_instance doesn't handle it
        with self.db.connection() as conn:
            conn.execute(
                "UPDATE project_instances SET issue_count = ? WHERE linear_project_id = ?",
                (len(issues_created), project.id)
            )

        # Log the creation
        self.db.log_sync(
            direction='template',
            action='create_project',
            fub_person_id=person.id,
            details={
                'project_id': project.id,
                'project_name': project_name,
                'phase': phase.value,
                'milestones': len(milestones_created),
                'issues': len(issues_created),
            },
        )

        logger.info(
            f"Created project {project_name} with "
            f"{len(milestones_created)} milestones and {len(issues_created)} issues"
        )

        return ProjectCreationResult(
            project=project,
            milestones=milestones_created,
            issues=issues_created,
            person_label_id=person_label_id,
        )

    def create_project_by_name(
        self,
        person_name: str,
        phase_name: str,
        property_address: Optional[str] = None,
        fub_person_id: Optional[int] = None,
    ) -> ProjectCreationResult:
        """Create a project by person name and phase name (convenience method).

        This is useful for CLI commands where we have the person's name but not
        their FUB record.

        Args:
            person_name: Person's name to search for in FUB
            phase_name: Phase name (QUALIFY, CURATE, ACQUIRE, CLOSE)
            property_address: Property address (required for ACQUIRE/CLOSE)
            fub_person_id: Optional FUB person ID (skip search if provided)

        Returns:
            ProjectCreationResult
        """
        # Get template
        template = get_template_by_name(phase_name)
        if not template:
            return ProjectCreationResult(
                project=None,
                error=f"Unknown phase: {phase_name}. Valid: QUALIFY, CURATE, ACQUIRE, CLOSE",
            )

        # Find person in FUB
        if fub_person_id:
            person = self.fub.get_person(fub_person_id)
        else:
            person = self.fub.find_person_by_name(person_name)

        if not person:
            # Create a minimal person object for project creation
            # This allows creating projects without a FUB person
            logger.warning(f"Person '{person_name}' not found in FUB, creating project without FUB link")
            person = FUBPerson(
                id=0,
                name=person_name,
                first_name=person_name.split()[0] if ' ' in person_name else person_name,
                last_name=person_name.split()[-1] if ' ' in person_name else '',
            )

        return self.create_project_from_template(
            person=person,
            phase=template.phase,
            property_address=property_address,
        )

    def get_person_journey(self, fub_person_id: int) -> list[dict]:
        """Get all projects for a person (their full journey).

        Returns list of project instances ordered by creation date.
        """
        return self.db.get_all_projects_for_person(fub_person_id)

    def complete_project(self, linear_project_id: str) -> bool:
        """Mark a project as completed.

        Updates both Linear and local database.
        """
        try:
            # Update in Linear
            self.linear.update_project(linear_project_id, state='completed')

            # Update in local DB
            self.db.update_project_instance(linear_project_id, status='completed')

            logger.info(f"Marked project {linear_project_id} as completed")
            return True
        except Exception as e:
            logger.error(f"Failed to complete project {linear_project_id}: {e}")
            return False


# Module-level singleton
project_factory = ProjectFactory()


# Convenience functions for CLI
def create_qualify_project(person_name: str, fub_person_id: int = None) -> ProjectCreationResult:
    """Create a QUALIFY project for a person."""
    return project_factory.create_project_by_name(
        person_name=person_name,
        phase_name='QUALIFY',
        fub_person_id=fub_person_id,
    )


def create_curate_project(person_name: str, fub_person_id: int = None) -> ProjectCreationResult:
    """Create a CURATE project for a person."""
    return project_factory.create_project_by_name(
        person_name=person_name,
        phase_name='CURATE',
        fub_person_id=fub_person_id,
    )


def create_acquire_project(
    person_name: str,
    property_address: str,
    fub_person_id: int = None,
) -> ProjectCreationResult:
    """Create an ACQUIRE project for a person and property."""
    return project_factory.create_project_by_name(
        person_name=person_name,
        phase_name='ACQUIRE',
        property_address=property_address,
        fub_person_id=fub_person_id,
    )


def create_close_project(
    person_name: str,
    property_address: str,
    fub_person_id: int = None,
) -> ProjectCreationResult:
    """Create a CLOSE project for a person and property."""
    return project_factory.create_project_by_name(
        person_name=person_name,
        phase_name='CLOSE',
        property_address=property_address,
        fub_person_id=fub_person_id,
    )
