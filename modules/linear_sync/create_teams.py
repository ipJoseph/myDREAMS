#!/usr/bin/env python3
"""Create Linear teams and workflow states for myDREAMS.

Teams (Process Groups):
- DEVELOP: Lead development (Qualify + Curate phases)
- TRANSACT: Active deals (Acquire + Close phases)
- GENERAL: Admin, marketing, operations
"""

import logging
import time

from .linear_client import linear_client
from .db import db

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Color palette for workflow states
COLORS = {
    'triage': '#95a2b3',      # Gray - new/unprocessed
    'backlog': '#bec2c8',     # Light gray
    'unstarted': '#e2e2e2',   # Lighter gray
    'started_early': '#5e6ad2',  # Blue - early progress
    'started_mid': '#0f783c',    # Green - active work
    'started_late': '#f2c94c',   # Yellow - nearing completion
    'completed': '#5e6ad2',   # Blue - done
    'canceled': '#95a2b3',    # Gray - canceled
}

# Team definitions with workflow states
TEAMS = {
    'DEVELOP': {
        'key': 'DEV',
        'description': 'Lead Development - Qualify and Curate phases of buyer journey',
        'states': [
            # Triage/Backlog
            ('New Lead', 'triage', '#95a2b3', 0),
            # Unstarted
            ('Contacted', 'unstarted', '#bec2c8', 1),
            # Started states (the journey)
            ('Qualifying', 'started', '#5e6ad2', 2),
            ('Requirements', 'started', '#5e6ad2', 3),
            ('Searching', 'started', '#0f783c', 4),
            ('Showing', 'started', '#f2c94c', 5),
            # Completed
            ('Ready', 'completed', '#5e6ad2', 6),
            # Canceled
            ('Disqualified', 'canceled', '#95a2b3', 7),
        ]
    },
    'TRANSACT': {
        'key': 'TRX',
        'description': 'Active Deals - Acquire and Close phases of buyer journey',
        'states': [
            # Backlog
            ('Drafting', 'backlog', '#95a2b3', 0),
            # Unstarted
            ('Submitted', 'unstarted', '#bec2c8', 1),
            # Started states (the deal journey)
            ('Countering', 'started', '#5e6ad2', 2),
            ('Under Contract', 'started', '#5e6ad2', 3),
            ('Inspection', 'started', '#0f783c', 4),
            ('Appraisal', 'started', '#0f783c', 5),
            ('Title', 'started', '#f2c94c', 6),
            ('Walkthrough', 'started', '#f2c94c', 7),
            # Completed
            ('Closed', 'completed', '#5e6ad2', 8),
            # Canceled
            ('Lost', 'canceled', '#95a2b3', 9),
        ]
    },
    'GENERAL': {
        'key': 'GEN',
        'description': 'General operations - Admin, marketing, and non-client work',
        'states': [
            ('Backlog', 'backlog', '#95a2b3', 0),
            ('Todo', 'unstarted', '#bec2c8', 1),
            ('In Progress', 'started', '#5e6ad2', 2),
            ('In Review', 'started', '#f2c94c', 3),
            ('Done', 'completed', '#5e6ad2', 4),
            ('Canceled', 'canceled', '#95a2b3', 5),
        ]
    },
}


def create_team_with_states(name: str, config: dict) -> dict:
    """Create a team and configure its workflow states."""
    key = config['key']
    description = config['description']
    states_config = config['states']

    logger.info(f"\n{'='*60}")
    logger.info(f"Creating team: {name} ({key})")
    logger.info(f"{'='*60}")

    # Check if team already exists
    existing = linear_client.get_team_by_key(key)
    if existing:
        logger.info(f"  Team {name} already exists (ID: {existing.id})")
        team = existing
    else:
        # Create the team
        logger.info(f"  Creating team...")
        team = linear_client.create_team(name, key, description)
        logger.info(f"  Created team: {team.name} (ID: {team.id})")
        time.sleep(0.5)  # Rate limiting

    # Get existing states
    existing_states = linear_client.get_workflow_states(team.id)
    existing_state_names = {s.name.lower(): s for s in existing_states}

    logger.info(f"\n  Configuring workflow states...")

    # Track states for database config
    default_state_id = None
    completed_state_id = None

    for state_name, state_type, color, position in states_config:
        if state_name.lower() in existing_state_names:
            state = existing_state_names[state_name.lower()]
            logger.info(f"    ✓ {state_name} (exists)")
        else:
            try:
                state = linear_client.create_workflow_state(
                    team_id=team.id,
                    name=state_name,
                    state_type=state_type,
                    color=color,
                    position=position,
                )
                logger.info(f"    + {state_name} ({state_type})")
                time.sleep(0.3)  # Rate limiting
            except Exception as e:
                logger.warning(f"    ! {state_name} - {e}")
                continue

        # Track default and completed states
        if state_type in ('triage', 'backlog') and default_state_id is None:
            default_state_id = state.id
        elif state_type == 'completed':
            completed_state_id = state.id

    # Archive default states we don't need (if they exist)
    default_states_to_archive = ['Todo', 'In Progress', 'Done', 'Canceled', 'Duplicate', 'In Review']
    if name != 'GENERAL':  # Keep these for GENERAL
        for state_name in default_states_to_archive:
            if state_name.lower() in existing_state_names:
                state = existing_state_names[state_name.lower()]
                # Only archive if it's a default Linear state
                if state.name in default_states_to_archive:
                    try:
                        # Can't archive states with issues, so just leave them
                        pass
                    except:
                        pass

    # Save team config to database
    process_group = name.lower()
    db.set_team_config(
        team_key=name,
        team_id=team.id,
        team_name=team.name,
        process_group=process_group,
        default_state_id=default_state_id,
        completed_state_id=completed_state_id,
    )

    return {
        'team_id': team.id,
        'team_name': team.name,
        'team_key': key,
        'default_state_id': default_state_id,
        'completed_state_id': completed_state_id,
    }


def create_standard_labels():
    """Create standard labels for sync."""
    logger.info(f"\n{'='*60}")
    logger.info("Creating standard labels")
    logger.info(f"{'='*60}")

    labels = [
        ('Call', '#E87B35'),
        ('Showing', '#5E6AD2'),
        ('Offer', '#E03E3E'),
        ('Document', '#4DA7B3'),
        ('Meeting', '#9B51E0'),
        ('Follow-up', '#F2C94C'),
        ('FUB-synced', '#888888'),
    ]

    created = []
    for name, color in labels:
        try:
            label = linear_client.get_or_create_label(name, color=color)
            logger.info(f"  ✓ {name}")
            created.append(label)
            time.sleep(0.2)
        except Exception as e:
            logger.warning(f"  ! {name} - {e}")

    return created


def run_create_teams():
    """Main function to create all teams and workflows."""
    logger.info("\n" + "="*60)
    logger.info("  myDREAMS Linear Setup - Creating Teams & Workflows")
    logger.info("="*60)

    # Test connection first
    logger.info("\nTesting Linear API connection...")
    try:
        viewer = linear_client.test_connection()
        logger.info(f"  Connected as: {viewer.get('name')} ({viewer.get('email')})")
    except Exception as e:
        logger.error(f"  ERROR: {e}")
        return False

    # Create teams
    results = {}
    for team_name, config in TEAMS.items():
        try:
            result = create_team_with_states(team_name, config)
            results[team_name] = result
        except Exception as e:
            logger.error(f"\nERROR creating {team_name}: {e}")

    # Create labels
    try:
        create_standard_labels()
    except Exception as e:
        logger.error(f"\nERROR creating labels: {e}")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("  Setup Summary")
    logger.info(f"{'='*60}")

    for team_name, result in results.items():
        logger.info(f"\n  {team_name}:")
        logger.info(f"    ID: {result['team_id']}")
        logger.info(f"    Key: {result['team_key']}")

    # Show teams command
    logger.info("\n\nVerify with: python -m modules.linear_sync teams")
    logger.info("Run setup to configure sync: python -m modules.linear_sync setup")

    return True


if __name__ == '__main__':
    run_create_teams()
