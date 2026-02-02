"""
Task Sync Setup - Process-based Project Routing.

Routes FUB tasks to Todoist projects based on the client's stage
in the sales process:

    BUYER JOURNEY:
    QUALIFY  → CURATE  → ACQUIRE → CLOSE
    (leads)    (search)   (offers)  (contract)

    SELLER JOURNEY:
    QUALIFY  → PRESENT → MARKET  → CLOSE
    (leads)    (listing)  (showings) (contract)

Projects:
    QUALIFY  - Lead → Client (calls, qualification) [Buyer & Seller]
    CURATE   - Buyer requirements, property search, showings
    ACQUIRE  - Buyer making offers, negotiating
    PRESENT  - Seller listing prep, CMA, photography
    MARKET   - Seller showings, receiving/reviewing offers
    CLOSE    - Contract → Close (inspections, due diligence) [Buyer & Seller]
"""

import logging
from typing import Optional

from .config import config
from .db import db
from .fub_client import fub_client
from .todoist_client import todoist_client

logger = logging.getLogger(__name__)

# Process project IDs (set after creation)
PROCESS_PROJECTS = {
    # Shared (Buyer & Seller)
    'QUALIFY': '6fvm9JfRGCx3J79G',
    'CLOSE': '6fvm9M28wGFj76Hr',
    # Buyer-specific
    'CURATE': '6fvm9Jq8qxgCrH3P',
    'ACQUIRE': '6fvm9JwFrM5hHCP3',
    # Seller-specific
    'PRESENT': '6fvmCWCGfvvvRMw3',
    'MARKET': '6fvmCWHJ9jCp2HGW',
}

# Map deal stage keywords to process
# Format: (keyword, pipeline_type) -> process
# pipeline_type: 'buyer', 'seller', or 'any'
STAGE_TO_PROCESS = {
    # QUALIFY - Lead to Buyer/Seller (shared)
    'new deal': 'QUALIFY',
    'lead': 'QUALIFY',

    # CURATE - Buyer requirements & property search
    'buyer contract': 'CURATE',

    # PRESENT - Seller listing preparation
    'listing contract': 'PRESENT',
    'listed': 'MARKET',  # Once listed, move to MARKET

    # ACQUIRE - Buyer making offers
    'offer': 'ACQUIRE',  # Buyer pipeline offer stage

    # MARKET - Seller receiving offers
    # (Seller "Offer" stage would also be MARKET - handled by pipeline detection)

    # CLOSE - Contract to Close (shared)
    'pending': 'CLOSE',
    'under contract': 'CLOSE',

    # Referrals default to QUALIFY
    'referral contract': 'QUALIFY',
}


def get_process_for_stage(stage_name: str) -> str:
    """
    Determine which process a deal stage belongs to.

    Returns process name: QUALIFY, CURATE, ACQUIRE, or CLOSE
    """
    if not stage_name:
        return 'QUALIFY'  # Default for no stage

    stage_lower = stage_name.lower()

    for keyword, process in STAGE_TO_PROCESS.items():
        if keyword in stage_lower:
            return process

    # Default to QUALIFY for unknown stages
    return 'QUALIFY'


def get_project_for_process(process: str) -> Optional[str]:
    """Get Todoist project ID for a process."""
    return PROCESS_PROJECTS.get(process)


def get_existing_todoist_projects() -> dict:
    """Get existing Todoist projects as a dict of name -> project."""
    projects = todoist_client.get_projects()
    return {p['name']: p for p in projects}


def get_existing_mappings() -> list[dict]:
    """Get existing pipeline-to-project mappings from database."""
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT * FROM todoist_projects
            WHERE project_type = 'pipeline_stage'
            ORDER BY fub_pipeline_id, fub_stage_id
        """).fetchall()
        return [dict(row) for row in rows]


def save_mapping(
    todoist_project_id: str,
    project_name: str,
    fub_pipeline_id: int,
    fub_stage_id: int
):
    """Save a pipeline stage to Todoist project mapping."""
    with db.connection() as conn:
        conn.execute("""
            INSERT INTO todoist_projects (
                todoist_project_id, project_name, fub_pipeline_id,
                fub_stage_id, project_type
            ) VALUES (?, ?, ?, ?, 'pipeline_stage')
            ON CONFLICT(todoist_project_id) DO UPDATE SET
                project_name = excluded.project_name,
                fub_pipeline_id = excluded.fub_pipeline_id,
                fub_stage_id = excluded.fub_stage_id
        """, (todoist_project_id, project_name, fub_pipeline_id, fub_stage_id))


def get_project_for_stage(pipeline_id: int, stage_id: int) -> Optional[str]:
    """Get the Todoist project ID for a FUB pipeline stage."""
    with db.connection() as conn:
        row = conn.execute("""
            SELECT todoist_project_id FROM todoist_projects
            WHERE fub_pipeline_id = ? AND fub_stage_id = ?
            AND project_type = 'pipeline_stage'
        """, (pipeline_id, stage_id)).fetchone()
        return row['todoist_project_id'] if row else None


def get_project_for_deal(deal_id: int) -> Optional[str]:
    """Get the Todoist project ID for a deal based on its stage."""
    # First check deal cache
    deal = db.get_cached_deal(deal_id)
    if deal and deal.get('pipeline_id') and deal.get('stage_id'):
        return get_project_for_stage(deal['pipeline_id'], deal['stage_id'])

    # If not cached, fetch from FUB
    try:
        deal_data = fub_client.get_deal(deal_id)
        if deal_data.pipeline_id and deal_data.stage_id:
            return get_project_for_stage(deal_data.pipeline_id, deal_data.stage_id)
    except Exception as e:
        logger.warning(f"Failed to fetch deal {deal_id}: {e}")

    return None


def run_setup_wizard(interactive: bool = True) -> dict:
    """
    Run the pipeline-to-project setup wizard.

    Args:
        interactive: If True, prompt for user input. If False, auto-create.

    Returns:
        Dict with setup results.
    """
    print("=" * 60)
    print("Task Sync Setup Wizard")
    print("Pipeline → Todoist Project Mapping")
    print("=" * 60)

    # Get FUB pipelines
    pipelines = fub_client.get_pipelines()
    print(f"\nFound {len(pipelines)} FUB pipelines")

    # Get existing Todoist projects
    existing_projects = get_existing_todoist_projects()
    print(f"Found {len(existing_projects)} existing Todoist projects")

    # Get existing mappings
    existing_mappings = get_existing_mappings()
    print(f"Found {len(existing_mappings)} existing mappings")

    results = {
        'projects_created': 0,
        'projects_mapped': 0,
        'stages_skipped': 0,
        'mappings': [],
    }

    # Define which stages to create projects for (skip closed/terminated)
    ACTIVE_STAGE_KEYWORDS = ['new', 'contract', 'offer', 'pending', 'listed', 'referral']
    SKIP_STAGE_KEYWORDS = ['closed', 'terminated', 'old']

    print("\n" + "-" * 60)
    print("Creating Todoist projects for active pipeline stages...")
    print("-" * 60)

    for pipeline in pipelines:
        print(f"\n📁 {pipeline.name}")

        for stage in pipeline.stages:
            stage_name = stage['name']
            stage_id = stage['id']
            stage_lower = stage_name.lower()

            # Skip closed/terminated stages
            if any(skip in stage_lower for skip in SKIP_STAGE_KEYWORDS):
                print(f"   ⏭️  {stage_name} (skipped - inactive stage)")
                results['stages_skipped'] += 1
                continue

            # Create project name: "Pipeline - Stage"
            project_name = f"{pipeline.name} - {stage_name}"

            # Check if project already exists
            if project_name in existing_projects:
                project = existing_projects[project_name]
                print(f"   ✓  {stage_name} → existing project '{project_name}'")

                # Save/update mapping
                save_mapping(project['id'], project_name, pipeline.id, stage_id)
                results['projects_mapped'] += 1
                results['mappings'].append({
                    'pipeline': pipeline.name,
                    'stage': stage_name,
                    'project': project_name,
                    'action': 'mapped',
                })
            else:
                # Create new project
                if interactive:
                    response = input(f"   Create project '{project_name}'? [Y/n]: ").strip().lower()
                    if response == 'n':
                        print(f"   ⏭️  {stage_name} (skipped by user)")
                        results['stages_skipped'] += 1
                        continue

                try:
                    color = get_color_for_stage(stage_name)
                    project = todoist_client.create_project(project_name)
                    print(f"   ✨ {stage_name} → created project '{project_name}'")

                    # Save mapping
                    save_mapping(project['id'], project_name, pipeline.id, stage_id)
                    results['projects_created'] += 1
                    results['mappings'].append({
                        'pipeline': pipeline.name,
                        'stage': stage_name,
                        'project': project_name,
                        'action': 'created',
                    })
                except Exception as e:
                    print(f"   ❌ {stage_name} → failed: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print(f"  Projects created: {results['projects_created']}")
    print(f"  Projects mapped:  {results['projects_mapped']}")
    print(f"  Stages skipped:   {results['stages_skipped']}")
    print()

    return results


def show_current_mappings():
    """Display current pipeline-to-project mappings."""
    mappings = get_existing_mappings()

    if not mappings:
        print("No pipeline-to-project mappings configured.")
        print("Run 'python -m modules.task_sync setup' to create them.")
        return

    print("=" * 60)
    print("Current Pipeline → Project Mappings")
    print("=" * 60)

    current_pipeline = None
    for m in mappings:
        # Group by pipeline (we'd need pipeline name, but we have ID)
        print(f"  Stage {m['fub_stage_id']} → {m['project_name']}")


def get_default_project() -> Optional[str]:
    """Get default Todoist project for tasks without deals.

    Returns QUALIFY project as default (new leads start here).
    """
    return PROCESS_PROJECTS.get('QUALIFY')
