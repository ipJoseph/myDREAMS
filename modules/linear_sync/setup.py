"""Setup wizard for Linear Sync module.

Configures Linear teams, workflow states, and labels.
"""

import logging
from typing import Optional

from .config import config
from .db import db
from .linear_client import linear_client
from .models import ProcessGroup

logger = logging.getLogger(__name__)


def discover_teams() -> list[dict]:
    """Discover available Linear teams."""
    teams = linear_client.get_teams()
    return [
        {
            'id': t.id,
            'name': t.name,
            'key': t.key,
            'states': [
                {'id': s.id, 'name': s.name, 'type': s.type}
                for s in t.workflow_states
            ]
        }
        for t in teams
    ]


def configure_team(
    team_key: str,
    team_id: str,
    process_group: ProcessGroup,
    default_state_name: Optional[str] = None,
    completed_state_name: Optional[str] = None,
) -> dict:
    """Configure a team for sync."""
    # Get team details
    team = linear_client.get_team(team_id)
    if not team:
        raise ValueError(f"Team not found: {team_id}")

    # Find default state
    default_state_id = None
    if default_state_name:
        for state in team.workflow_states:
            if state.name.lower() == default_state_name.lower():
                default_state_id = state.id
                break
    else:
        # Use first unstarted/backlog state
        default_state = linear_client.get_initial_state(team_id)
        default_state_id = default_state.id if default_state else None

    # Find completed state
    completed_state_id = None
    if completed_state_name:
        for state in team.workflow_states:
            if state.name.lower() == completed_state_name.lower():
                completed_state_id = state.id
                break
    else:
        completed_state = linear_client.get_completed_state(team_id)
        completed_state_id = completed_state.id if completed_state else None

    # Save to database
    db.set_team_config(
        team_key=team_key,
        team_id=team_id,
        team_name=team.name,
        process_group=process_group.value,
        default_state_id=default_state_id,
        completed_state_id=completed_state_id,
    )

    return {
        'team_key': team_key,
        'team_id': team_id,
        'team_name': team.name,
        'process_group': process_group.value,
        'default_state_id': default_state_id,
        'completed_state_id': completed_state_id,
    }


def setup_standard_labels() -> list[dict]:
    """Create standard labels for sync."""
    labels = []

    # Task type labels
    type_labels = [
        ('Call', '#E87B35'),
        ('Showing', '#5E6AD2'),
        ('Offer', '#E03E3E'),
        ('Document', '#4DA7B3'),
        ('Meeting', '#9B51E0'),
        ('Follow-up', '#F2C94C'),
    ]

    for name, color in type_labels:
        label = linear_client.get_or_create_label(name, color=color)
        labels.append({'id': label.id, 'name': label.name, 'color': label.color})

    # FUB-synced label (for tracking synced items)
    fub_synced = linear_client.get_or_create_label('FUB-synced', color='#888888')
    labels.append({'id': fub_synced.id, 'name': fub_synced.name, 'color': fub_synced.color})

    return labels


def auto_configure_teams() -> dict:
    """Auto-configure teams based on naming conventions.

    Looks for teams named DEVELOP/DEV, TRANSACT/TRX, GENERAL/GEN.
    """
    teams = linear_client.get_teams()
    configured = {}

    # Team name patterns to process groups
    patterns = {
        ProcessGroup.DEVELOP: ['develop', 'dev', 'development', 'leads'],
        ProcessGroup.TRANSACT: ['transact', 'trx', 'deals', 'closing'],
        ProcessGroup.GENERAL: ['general', 'gen', 'ops', 'operations', 'admin'],
    }

    for team in teams:
        team_lower = team.name.lower()
        team_key_lower = team.key.lower()

        for process, names in patterns.items():
            if team_lower in names or team_key_lower in names:
                result = configure_team(
                    team_key=process.value.upper(),
                    team_id=team.id,
                    process_group=process,
                )
                configured[process.value] = result
                logger.info(f"Auto-configured {process.value} → {team.name}")
                break

    return configured


def run_setup_wizard():
    """Interactive setup wizard."""
    print("\n=== Linear Sync Setup Wizard ===\n")

    # Test connection
    print("Testing Linear API connection...")
    try:
        viewer = linear_client.test_connection()
        print(f"  Connected as: {viewer.get('name')} ({viewer.get('email')})")
    except Exception as e:
        print(f"  ERROR: Could not connect to Linear API: {e}")
        print("  Please check your LINEAR_API_KEY in .env")
        return False

    # Discover teams
    print("\nDiscovering teams...")
    teams = discover_teams()

    if not teams:
        print("  No teams found. Please create teams in Linear first.")
        print("  Recommended: DEVELOP, TRANSACT, GENERAL")
        return False

    print(f"  Found {len(teams)} teams:")
    for t in teams:
        states = ', '.join(s['name'] for s in t['states'][:3])
        print(f"    - {t['name']} ({t['key']}): {states}...")

    # Try auto-configuration
    print("\nAttempting auto-configuration...")
    configured = auto_configure_teams()

    if configured:
        print(f"  Auto-configured {len(configured)} teams:")
        for name, cfg in configured.items():
            print(f"    - {name}: {cfg['team_name']}")
    else:
        print("  Could not auto-configure teams.")
        print("  Please manually configure teams or rename them to:")
        print("    - DEVELOP (or DEV) for lead development")
        print("    - TRANSACT (or TRX) for active deals")
        print("    - GENERAL (or GEN) for admin/ops")

    # Setup labels
    print("\nSetting up standard labels...")
    labels = setup_standard_labels()
    print(f"  Created/verified {len(labels)} labels")

    # Summary
    print("\n=== Setup Summary ===")
    team_configs = db.get_all_team_configs()
    if team_configs:
        print("Teams configured:")
        for tc in team_configs:
            print(f"  - {tc['team_key']}: {tc['team_name']} ({tc['process_group']})")
    else:
        print("No teams configured. Please run setup again after creating teams.")

    print("\nSetup complete!")
    return True


def show_current_config():
    """Show current configuration."""
    print("\n=== Linear Sync Configuration ===\n")

    # Team configs
    team_configs = db.get_all_team_configs()
    if team_configs:
        print("Teams:")
        for tc in team_configs:
            print(f"  {tc['team_key']}:")
            print(f"    ID: {tc['team_id']}")
            print(f"    Name: {tc['team_name']}")
            print(f"    Process: {tc['process_group']}")
            print(f"    Default State: {tc['default_state_id']}")
            print(f"    Completed State: {tc['completed_state_id']}")
    else:
        print("No teams configured.")

    # Person labels
    person_labels = db.get_all_person_labels()
    if person_labels:
        print(f"\nPerson Labels ({len(person_labels)}):")
        for pl in person_labels[:10]:
            print(f"  - {pl['fub_person_name']} → {pl['linear_label_name']}")
        if len(person_labels) > 10:
            print(f"  ... and {len(person_labels) - 10} more")
    else:
        print("\nNo person labels configured.")

    # Sync stats
    stats = db.get_sync_stats()
    print(f"\nSync Stats:")
    print(f"  Total mappings: {stats['total_mappings']}")
    print(f"  By origin: {stats['by_origin']}")
    print(f"  By status: {stats['by_status']}")
    if stats['today_actions']:
        print(f"  Today's actions: {stats['today_actions']}")
