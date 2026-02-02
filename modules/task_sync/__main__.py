"""
Task Sync CLI entry point.

Usage:
    python -m modules.task_sync test       Test connections
    python -m modules.task_sync status     Show sync status
    python -m modules.task_sync sync-once  Run one sync cycle (changes only)
    python -m modules.task_sync sync-all   Sync ALL active FUB tasks to Todoist
    python -m modules.task_sync run        Start sync service
    python -m modules.task_sync setup      Setup pipeline → project mapping
    python -m modules.task_sync mappings   Show current mappings
"""

import argparse
import json
import logging
import sys

from .config import config
from .db import db

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_test():
    """Test connections to FUB and Todoist."""
    print("=" * 60)
    print("Task Sync Connection Test")
    print("=" * 60)

    # Validate config
    errors = config.validate()
    if errors:
        print("\n[CONFIG ERRORS]")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"\nEnvironment: {config.TASK_SYNC_ENV}")
    print(f"Database: {config.DB_PATH}")

    # Test FUB connection
    print("\n[FUB Connection]")
    try:
        from .fub_client import fub_client

        # Get test contact
        TEST_PERSON_ID = 12955  # Thebig Eug
        person = fub_client.get_person(TEST_PERSON_ID)
        name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
        print(f"  ✓ Connected to FUB")
        print(f"  ✓ Test contact: {name} (ID: {TEST_PERSON_ID})")

        # Get tasks for test contact
        tasks = fub_client.get_tasks(person_id=TEST_PERSON_ID)
        print(f"  ✓ Found {len(tasks)} tasks for test contact")
        for task in tasks[:3]:
            status = "✓" if task.is_completed else "○"
            print(f"    {status} [{task.id}] {task.name}")

        # Get pipelines
        pipelines = fub_client.get_pipelines()
        print(f"  ✓ Found {len(pipelines)} deal pipelines")
        for p in pipelines:
            print(f"    - {p.name} ({len(p.stages)} stages)")

    except Exception as e:
        print(f"  ✗ FUB connection failed: {e}")
        return 1

    # Test Todoist connection
    print("\n[Todoist Connection]")
    try:
        from .todoist_client import todoist_client

        projects = todoist_client.get_projects()
        print(f"  ✓ Connected to Todoist")
        print(f"  ✓ Found {len(projects)} projects")
        for p in projects[:5]:
            print(f"    - {p['name']}")

        labels = todoist_client.get_labels()
        print(f"  ✓ Found {len(labels)} labels")

    except Exception as e:
        print(f"  ✗ Todoist connection failed: {e}")
        return 1

    # Test database
    print("\n[Database]")
    try:
        state = db.get_state('test_key')
        db.set_state('test_key', 'test_value')
        state = db.get_state('test_key')
        print(f"  ✓ Database read/write working")
        print(f"  ✓ Path: {config.DB_PATH}")
    except Exception as e:
        print(f"  ✗ Database failed: {e}")
        return 1

    print("\n" + "=" * 60)
    print("All connections successful!")
    print("=" * 60)
    return 0


def cmd_status():
    """Show current sync status."""
    print("=" * 60)
    print("Task Sync Status")
    print("=" * 60)

    # Configuration
    print("\n[Configuration]")
    print(f"  Environment: {config.TASK_SYNC_ENV}")
    print(f"  FUB poll interval: {config.FUB_POLL_INTERVAL}s")
    print(f"  Todoist poll interval: {config.TODOIST_POLL_INTERVAL}s")
    print(f"  Deal cache refresh: {config.DEAL_CACHE_REFRESH}s")

    # Get sync state
    print("\n[Sync State]")
    last_fub_poll = db.get_state('fub_last_poll')
    last_todoist_sync = db.get_state('todoist_sync_token')

    print(f"  Last FUB poll: {last_fub_poll or 'Never'}")
    print(f"  Todoist sync token: {'Set' if last_todoist_sync else 'Not set'}")

    # Count mappings
    with db.connection() as conn:
        mapping_count = conn.execute("SELECT COUNT(*) FROM task_map").fetchone()[0]
        pending_count = conn.execute("SELECT COUNT(*) FROM task_map WHERE sync_status != 'synced'").fetchone()[0]
    print(f"  Task mappings: {mapping_count} total, {pending_count} pending")

    # Get recent logs
    print("\n[Recent Sync Activity]")
    logs = db.get_recent_logs(limit=10)
    if logs:
        for log in logs:
            status_icon = "✓" if log['status'] == 'success' else "✗"
            print(f"  {status_icon} {log['timestamp'][:16]} | {log['direction']:20} | {log['action']}")
    else:
        print("  No sync activity recorded yet")

    return 0


def cmd_sync_once():
    """Run a single sync cycle."""
    print("=" * 60)
    print("Running Single Sync Cycle")
    print("=" * 60)

    from .sync_engine import sync_engine

    # Poll FUB for changes
    print("\n[Polling FUB for changes...]")
    synced = sync_engine.poll_fub_changes()

    if synced:
        print(f"  ✓ Synced {len(synced)} tasks: {synced}")
    else:
        print("  No changes detected")

    # Show recent logs
    print("\n[Recent Sync Activity]")
    logs = db.get_recent_logs(limit=5)
    for log in logs:
        status_icon = "✓" if log['status'] == 'success' else "✗"
        print(f"  {status_icon} {log['timestamp'][:16]} | {log['direction']} | {log['action']}")
        if log.get('details'):
            print(f"      {log['details'][:60]}")

    return 0


def cmd_sync_all():
    """Sync all active FUB tasks to Todoist (full sync)."""
    print("=" * 60)
    print("Full Sync: All Active FUB Tasks → Todoist")
    print("=" * 60)

    from .sync_engine import sync_engine
    from .fub_client import fub_client

    # Get all active FUB tasks (not completed)
    print("\n[Fetching all FUB tasks...]")
    all_tasks = fub_client.get_tasks(limit=100)
    active_tasks = [t for t in all_tasks if not t.is_completed]
    print(f"  Found {len(all_tasks)} total tasks, {len(active_tasks)} active")

    # Sync each task
    print("\n[Syncing tasks...]")
    synced = []
    skipped = []
    errors = []

    for task in active_tasks:
        try:
            # Check if already mapped
            mapping = db.get_mapping_by_fub_id(task.id)
            if mapping:
                skipped.append(task.id)
                print(f"  ⏭️  [{task.type}] {task.name[:40]} (already synced)")
                continue

            result = sync_engine.sync_fub_task_to_todoist(task)
            if result:
                synced.append(task.id)
                print(f"  ✓  [{task.type}] {task.name[:40]}")
        except Exception as e:
            errors.append((task.id, str(e)))
            print(f"  ✗  [{task.type}] {task.name[:40]} - {e}")

    # Summary
    print("\n" + "=" * 60)
    print(f"Full Sync Complete")
    print("=" * 60)
    print(f"  Synced:  {len(synced)} new tasks")
    print(f"  Skipped: {len(skipped)} already synced")
    print(f"  Errors:  {len(errors)}")

    if errors:
        print("\n[Errors]")
        for task_id, error in errors[:5]:
            print(f"  Task {task_id}: {error[:60]}")

    return 0


def cmd_run():
    """Start the sync service (continuous polling)."""
    from .poller import run_poller

    print("=" * 60)
    print("Starting Task Sync Service")
    print("=" * 60)
    print(f"Environment: {config.TASK_SYNC_ENV}")
    print(f"FUB poll interval: {config.FUB_POLL_INTERVAL}s")
    print(f"Todoist poll interval: {config.TODOIST_POLL_INTERVAL}s")
    print(f"Deal cache refresh: {config.DEAL_CACHE_REFRESH}s")
    print("=" * 60)
    print("\nPress Ctrl+C to stop\n")

    try:
        run_poller()
    except KeyboardInterrupt:
        print("\nStopped by user")

    return 0


def cmd_setup():
    """Run the pipeline-to-project setup wizard."""
    from .setup import run_setup_wizard
    run_setup_wizard(interactive=True)
    return 0


def cmd_mappings():
    """Show current pipeline-to-project mappings."""
    from .setup import get_existing_mappings
    from .fub_client import fub_client

    mappings = get_existing_mappings()

    if not mappings:
        print("No pipeline-to-project mappings configured.")
        print("Run 'python -m modules.task_sync setup' to create them.")
        return 0

    # Get pipeline names for display
    pipelines = {p.id: p.name for p in fub_client.get_pipelines()}
    stages = {}
    for p in fub_client.get_pipelines():
        for s in p.stages:
            stages[s['id']] = s['name']

    print("=" * 60)
    print("Pipeline → Todoist Project Mappings")
    print("=" * 60)

    current_pipeline = None
    for m in mappings:
        pipeline_name = pipelines.get(m['fub_pipeline_id'], f"Pipeline {m['fub_pipeline_id']}")
        stage_name = stages.get(m['fub_stage_id'], f"Stage {m['fub_stage_id']}")

        if pipeline_name != current_pipeline:
            print(f"\n📁 {pipeline_name}")
            current_pipeline = pipeline_name

        print(f"   {stage_name} → {m['project_name']}")

    print()
    return 0


def main():
    parser = argparse.ArgumentParser(description='Task Sync - Todoist ↔ FUB')
    parser.add_argument('command', choices=['test', 'status', 'sync-once', 'sync-all', 'run', 'setup', 'mappings'],
                        help='Command to run')

    args = parser.parse_args()

    commands = {
        'test': cmd_test,
        'status': cmd_status,
        'sync-once': cmd_sync_once,
        'sync-all': cmd_sync_all,
        'run': cmd_run,
        'setup': cmd_setup,
        'mappings': cmd_mappings,
    }

    return commands[args.command]()


if __name__ == '__main__':
    sys.exit(main())
