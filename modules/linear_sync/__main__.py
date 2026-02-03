"""CLI for Linear Sync module.

Usage:
    python -m modules.linear_sync test          Test API connections
    python -m modules.linear_sync status        Show sync status
    python -m modules.linear_sync setup         Run setup wizard
    python -m modules.linear_sync config        Show current config
    python -m modules.linear_sync create-teams  Create DEVELOP, TRANSACT, GENERAL teams
    python -m modules.linear_sync sync-once     Run single sync cycle
    python -m modules.linear_sync sync-all      Full sync of all FUB tasks
    python -m modules.linear_sync run           Start continuous sync service
    python -m modules.linear_sync create-test   Create a test issue in Linear
    python -m modules.linear_sync teams         List Linear teams
    python -m modules.linear_sync labels        List Linear labels
    python -m modules.linear_sync mappings      Show task mappings

Project Templates:
    python -m modules.linear_sync create-qualify "Person Name"           Create QUALIFY project
    python -m modules.linear_sync create-curate "Person Name"            Create CURATE project
    python -m modules.linear_sync create-acquire "Person Name" "Address" Create ACQUIRE project
    python -m modules.linear_sync create-close "Person Name" "Address"   Create CLOSE project
    python -m modules.linear_sync list-projects                          List all projects
    python -m modules.linear_sync templates                              Show available templates
"""

import argparse
import logging
import sys

from .config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_test() -> int:
    """Test API connections."""
    from .linear_client import linear_client
    from .fub_client import fub_client

    print("Testing Linear Sync connections...\n")
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        return 1

    # Test Linear
    print("Linear API:")
    try:
        viewer = linear_client.test_connection()
        print(f"  Connected as: {viewer.get('name')} ({viewer.get('email')})")

        teams = linear_client.get_teams()
        print(f"  Teams: {len(teams)}")
        for t in teams:
            print(f"    - {t.name} ({t.key})")
    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    # Test FUB
    print("\nFollow Up Boss API:")
    try:
        tasks = fub_client.get_tasks(limit=1)
        print(f"  Connected (found {len(tasks)} task(s))")
    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    print("\nAll connections successful!")
    return 0


def cmd_status() -> int:
    """Show sync status."""
    from .db import db

    print("=== Linear Sync Status ===\n")

    # Config status
    if not config.is_configured():
        print("WARNING: Not fully configured. Run 'setup' first.\n")

    # Team configs
    team_configs = db.get_all_team_configs()
    print(f"Teams configured: {len(team_configs)}")
    for tc in team_configs:
        print(f"  - {tc['team_key']}: {tc['team_name']}")

    # Mappings
    print()
    stats = db.get_sync_stats()
    print(f"Total mappings: {stats['total_mappings']}")
    if stats['by_origin']:
        print(f"  By origin: {stats['by_origin']}")
    if stats['by_status']:
        print(f"  By status: {stats['by_status']}")

    # Recent activity
    print()
    if stats['today_actions']:
        print(f"Today's sync actions: {stats['today_actions']}")
    else:
        print("No sync activity today.")

    # Recent logs
    logs = db.get_recent_logs(limit=5)
    if logs:
        print("\nRecent sync logs:")
        for log in logs:
            status = "✓" if log['status'] == 'success' else "✗"
            print(f"  {status} {log['timestamp']}: {log['direction']} {log['action']}")

    return 0


def cmd_setup() -> int:
    """Run setup wizard."""
    from .setup import run_setup_wizard

    success = run_setup_wizard()
    return 0 if success else 1


def cmd_config() -> int:
    """Show current configuration."""
    from .setup import show_current_config

    show_current_config()
    return 0


def cmd_create_teams() -> int:
    """Create DEVELOP, TRANSACT, GENERAL teams with workflow states."""
    from .create_teams import run_create_teams

    success = run_create_teams()
    return 0 if success else 1


def cmd_sync_once() -> int:
    """Run single sync cycle."""
    from .sync_engine import sync_engine

    print("Running sync cycle...\n")

    # Sync FUB → Linear
    print("Syncing FUB tasks to Linear...")
    fub_synced = sync_engine.poll_fub_changes()
    print(f"  Synced {fub_synced} tasks")

    # Sync Linear → FUB
    print("\nSyncing Linear issues to FUB...")
    linear_synced = sync_engine.poll_linear_changes()
    print(f"  Synced {linear_synced} issues")

    print(f"\nSync complete. Total: {fub_synced + linear_synced} items synced.")
    return 0


def cmd_sync_all() -> int:
    """Full sync of all FUB tasks."""
    from .sync_engine import sync_engine

    print("Running full sync of all FUB tasks to Linear...\n")

    synced = sync_engine.sync_all_fub_tasks()
    print(f"\nFull sync complete. {synced} tasks synced.")
    return 0


def cmd_run() -> int:
    """Start continuous sync service."""
    from .db import db

    # Check configuration
    team_configs = db.get_all_team_configs()
    if not team_configs:
        print("ERROR: No teams configured. Run 'setup' first.")
        return 1

    from .poller import run_poller

    print("Starting Linear Sync service...")
    print("Press Ctrl+C to stop.\n")

    run_poller()
    return 0


def cmd_create_test() -> int:
    """Create a test issue in Linear."""
    from .linear_client import linear_client
    from .db import db

    # Get first configured team
    team_configs = db.get_all_team_configs()
    if not team_configs:
        # Try to get any team
        teams = linear_client.get_teams()
        if not teams:
            print("ERROR: No teams found. Create teams in Linear first.")
            return 1
        team_id = teams[0].id
        team_name = teams[0].name
    else:
        team_id = team_configs[0]['team_id']
        team_name = team_configs[0]['team_name']

    print(f"Creating test issue in team: {team_name}")

    issue = linear_client.create_issue(
        title="Test issue from myDREAMS sync",
        team_id=team_id,
        description="This is a test issue created by the linear_sync module.\n\nYou can safely delete this.",
        priority=3,  # Medium
    )

    print(f"Created: {issue.identifier} - {issue.title}")
    print(f"  URL: https://linear.app/issue/{issue.identifier}")
    return 0


def cmd_teams() -> int:
    """List Linear teams."""
    from .linear_client import linear_client

    print("Linear Teams:\n")
    teams = linear_client.get_teams()

    for team in teams:
        print(f"{team.name} ({team.key}):")
        print(f"  ID: {team.id}")
        print("  Workflow states:")
        for state in sorted(team.workflow_states, key=lambda s: s.position):
            print(f"    - {state.name} ({state.type})")
        print()

    return 0


def cmd_labels() -> int:
    """List Linear labels."""
    from .linear_client import linear_client

    print("Linear Labels:\n")
    labels = linear_client.get_labels()

    for label in labels:
        parent = f" (parent: {label.parent_id})" if label.parent_id else ""
        print(f"  - {label.name} [{label.color}]{parent}")

    return 0


def cmd_mappings() -> int:
    """Show current mappings."""
    from .db import db

    mappings = db.get_all_mappings()

    if not mappings:
        print("No mappings found.")
        return 0

    print(f"=== Task Mappings ({len(mappings)}) ===\n")

    for m in mappings[:20]:
        origin_icon = "L→F" if m['origin'] == 'linear' else "F→L"
        status_icon = "✓" if m['sync_status'] == 'synced' else "?"
        print(f"{status_icon} {origin_icon} Linear:{m['linear_identifier']} ↔ FUB:{m['fub_task_id']} (person:{m['fub_person_id']})")

    if len(mappings) > 20:
        print(f"\n... and {len(mappings) - 20} more")

    return 0


# =============================================================================
# PROJECT TEMPLATE COMMANDS
# =============================================================================

def cmd_templates() -> int:
    """Show available project templates."""
    from .templates import PHASE_TEMPLATES

    print("=== Project Templates ===\n")

    for phase, template in PHASE_TEMPLATES.items():
        milestone_count = len(template.milestones)
        issue_count = sum(len(m.issues) for m in template.milestones)
        print(f"{template.name_suffix}:")
        print(f"  Team: {template.process_group.value.upper()}")
        print(f"  Milestones: {milestone_count}")
        print(f"  Issues: {issue_count}")
        print(f"  Description: {template.description}")
        print()

        for milestone in template.milestones:
            print(f"    {milestone.name}:")
            for issue in milestone.issues:
                priority_map = {1: '!', 2: '▲', 3: '●', 4: '○'}
                priority = priority_map.get(issue.priority, '●')
                print(f"      {priority} {issue.title}")
        print()

    return 0


def cmd_create_qualify(args) -> int:
    """Create a QUALIFY project for a person."""
    from .project_factory import create_qualify_project

    person_name = args.person_name

    print(f"Creating QUALIFY project for: {person_name}\n")

    result = create_qualify_project(person_name)

    if result.error:
        print(f"ERROR: {result.error}")
        return 1

    print(f"Created: {result.project.name}")
    print(f"  ID: {result.project.id}")
    print(f"  Milestones: {len(result.milestones)}")
    print(f"  Issues: {len(result.issues)}")

    if result.milestones:
        print("\nMilestones:")
        for m in result.milestones:
            print(f"  - {m.name}")

    return 0


def cmd_create_curate(args) -> int:
    """Create a CURATE project for a person."""
    from .project_factory import create_curate_project

    person_name = args.person_name

    print(f"Creating CURATE project for: {person_name}\n")

    result = create_curate_project(person_name)

    if result.error:
        print(f"ERROR: {result.error}")
        return 1

    print(f"Created: {result.project.name}")
    print(f"  ID: {result.project.id}")
    print(f"  Milestones: {len(result.milestones)}")
    print(f"  Issues: {len(result.issues)}")

    return 0


def cmd_create_acquire(args) -> int:
    """Create an ACQUIRE project for a person and property."""
    from .project_factory import create_acquire_project

    person_name = args.person_name
    property_address = args.property_address

    print(f"Creating ACQUIRE project for: {person_name}")
    print(f"  Property: {property_address}\n")

    result = create_acquire_project(person_name, property_address)

    if result.error:
        print(f"ERROR: {result.error}")
        return 1

    print(f"Created: {result.project.name}")
    print(f"  ID: {result.project.id}")
    print(f"  Milestones: {len(result.milestones)}")
    print(f"  Issues: {len(result.issues)}")

    return 0


def cmd_create_close(args) -> int:
    """Create a CLOSE project for a person and property."""
    from .project_factory import create_close_project

    person_name = args.person_name
    property_address = args.property_address

    print(f"Creating CLOSE project for: {person_name}")
    print(f"  Property: {property_address}\n")

    result = create_close_project(person_name, property_address)

    if result.error:
        print(f"ERROR: {result.error}")
        return 1

    print(f"Created: {result.project.name}")
    print(f"  ID: {result.project.id}")
    print(f"  Milestones: {len(result.milestones)}")
    print(f"  Issues: {len(result.issues)}")

    return 0


def cmd_list_projects() -> int:
    """List all project instances."""
    from .db import db

    projects = db.get_active_projects()

    if not projects:
        print("No active projects found.")
        stats = db.get_project_stats()
        if stats['total_completed'] > 0:
            print(f"({stats['total_completed']} completed projects)")
        return 0

    print(f"=== Active Projects ({len(projects)}) ===\n")

    # Group by phase
    by_phase = {}
    for p in projects:
        phase = p['phase'].upper()
        if phase not in by_phase:
            by_phase[phase] = []
        by_phase[phase].append(p)

    for phase in ['QUALIFY', 'CURATE', 'ACQUIRE', 'CLOSE']:
        if phase.lower() not in [p['phase'] for p in projects]:
            continue

        phase_projects = by_phase.get(phase, [])
        print(f"{phase} ({len(phase_projects)}):")
        for p in phase_projects:
            progress = f"{p['completed_count']}/{p['issue_count']}" if p['issue_count'] else "0/0"
            addr = f" - {p['property_address']}" if p['property_address'] else ""
            print(f"  {p['fub_person_name']}{addr} [{progress}]")
        print()

    # Stats
    stats = db.get_project_stats()
    if stats['total_completed'] > 0:
        print(f"Completed projects: {stats['total_completed']}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Linear Sync - Bidirectional Linear ↔ FUB sync with Project Templates',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Simple commands (no arguments)
    subparsers.add_parser('test', help='Test API connections')
    subparsers.add_parser('status', help='Show sync status')
    subparsers.add_parser('setup', help='Run setup wizard')
    subparsers.add_parser('config', help='Show current config')
    subparsers.add_parser('create-teams', help='Create DEVELOP, TRANSACT, GENERAL teams')
    subparsers.add_parser('sync-once', help='Run single sync cycle')
    subparsers.add_parser('sync-all', help='Full sync of all FUB tasks')
    subparsers.add_parser('run', help='Start continuous sync service')
    subparsers.add_parser('create-test', help='Create a test issue in Linear')
    subparsers.add_parser('teams', help='List Linear teams')
    subparsers.add_parser('labels', help='List Linear labels')
    subparsers.add_parser('mappings', help='Show task mappings')
    subparsers.add_parser('templates', help='Show available templates')
    subparsers.add_parser('list-projects', help='List all project instances')

    # Project creation commands
    create_qualify = subparsers.add_parser('create-qualify', help='Create QUALIFY project')
    create_qualify.add_argument('person_name', help='Person name')

    create_curate = subparsers.add_parser('create-curate', help='Create CURATE project')
    create_curate.add_argument('person_name', help='Person name')

    create_acquire = subparsers.add_parser('create-acquire', help='Create ACQUIRE project')
    create_acquire.add_argument('person_name', help='Person name')
    create_acquire.add_argument('property_address', help='Property address')

    create_close = subparsers.add_parser('create-close', help='Create CLOSE project')
    create_close.add_argument('person_name', help='Person name')
    create_close.add_argument('property_address', help='Property address')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Simple commands mapping
    simple_commands = {
        'test': cmd_test,
        'status': cmd_status,
        'setup': cmd_setup,
        'config': cmd_config,
        'create-teams': cmd_create_teams,
        'sync-once': cmd_sync_once,
        'sync-all': cmd_sync_all,
        'run': cmd_run,
        'create-test': cmd_create_test,
        'teams': cmd_teams,
        'labels': cmd_labels,
        'mappings': cmd_mappings,
        'templates': cmd_templates,
        'list-projects': cmd_list_projects,
    }

    # Commands with arguments
    arg_commands = {
        'create-qualify': cmd_create_qualify,
        'create-curate': cmd_create_curate,
        'create-acquire': cmd_create_acquire,
        'create-close': cmd_create_close,
    }

    if args.command in simple_commands:
        return simple_commands[args.command]()
    elif args.command in arg_commands:
        return arg_commands[args.command](args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
