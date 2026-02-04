#!/usr/bin/env python3
"""
Sync Requirements from Drive

Imports buyer requirements from markdown files back to the database.
Parses YAML frontmatter and updates intake_forms table.

Usage:
    python scripts/sync_requirements_from_drive.py [--file PATH] [--dry-run]
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Default paths
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))
CLIENTS_DIR = Path(os.getenv('DREAMS_CLIENTS_DIR', Path.home() / 'myDREAMS' / 'clients'))


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def parse_markdown_file(file_path):
    """Parse markdown file with YAML frontmatter."""
    content = Path(file_path).read_text()

    # Split frontmatter from body
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1].strip()
            body = parts[2].strip()

            try:
                frontmatter = yaml.safe_load(frontmatter_str)
                return frontmatter, body
            except yaml.YAMLError as e:
                print(f"Error parsing YAML in {file_path}: {e}")
                return None, content

    return None, content


def frontmatter_to_db_record(frontmatter):
    """Convert frontmatter dict to database record format."""
    def to_json(val):
        if isinstance(val, list):
            return json.dumps(val) if val else None
        return val

    return {
        'id': frontmatter.get('form_id'),
        'lead_id': frontmatter.get('lead_id'),
        'form_name': frontmatter.get('form_name'),
        'need_type': frontmatter.get('need_type', 'primary_home'),
        'status': frontmatter.get('status', 'active'),

        # Location (JSON arrays)
        'counties': to_json(frontmatter.get('counties')),
        'cities': to_json(frontmatter.get('cities')),
        'zip_codes': to_json(frontmatter.get('zip_codes')),

        # Property criteria
        'property_types': to_json(frontmatter.get('property_types')),
        'min_price': frontmatter.get('min_price'),
        'max_price': frontmatter.get('max_price'),
        'min_beds': frontmatter.get('min_beds'),
        'max_beds': frontmatter.get('max_beds'),
        'min_baths': frontmatter.get('min_baths'),
        'max_baths': frontmatter.get('max_baths'),
        'min_sqft': frontmatter.get('min_sqft'),
        'max_sqft': frontmatter.get('max_sqft'),
        'min_acreage': frontmatter.get('min_acreage'),
        'max_acreage': frontmatter.get('max_acreage'),
        'min_year_built': frontmatter.get('min_year_built'),
        'max_year_built': frontmatter.get('max_year_built'),

        # Timeline
        'urgency': frontmatter.get('urgency'),
        'financing_status': frontmatter.get('financing_status'),
        'pre_approval_amount': frontmatter.get('pre_approval_amount'),
        'move_in_date': frontmatter.get('move_in_date'),

        # Scoring
        'confidence_score': frontmatter.get('confidence_score'),

        'updated_at': datetime.now().isoformat(),
    }


def extract_agent_notes_from_body(body):
    """Extract agent notes section from markdown body."""
    # Look for ## Agent Notes section
    match = re.search(r'## Agent Notes\s*\n\s*>\s*(.+?)(?=\n---|\n##|$)', body, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def update_intake_form(conn, record, dry_run=False):
    """Update or insert intake form record."""
    form_id = record.get('id')

    if not form_id:
        print("  Warning: No form_id in frontmatter, skipping")
        return False

    # Check if record exists
    existing = conn.execute('SELECT id FROM intake_forms WHERE id = ?', (form_id,)).fetchone()

    if existing:
        # Update existing record
        fields = [k for k in record.keys() if k != 'id' and record[k] is not None]
        set_clause = ', '.join(f'{k} = ?' for k in fields)
        values = [record[k] for k in fields] + [form_id]

        if dry_run:
            print(f"  [DRY RUN] Would update form {form_id}")
            return True

        conn.execute(f'UPDATE intake_forms SET {set_clause} WHERE id = ?', values)
        print(f"  Updated form {form_id}")
    else:
        # Insert new record (need lead_id)
        if not record.get('lead_id'):
            print(f"  Warning: No lead_id for new form {form_id}, skipping")
            return False

        if dry_run:
            print(f"  [DRY RUN] Would insert new form {form_id}")
            return True

        fields = [k for k in record.keys() if record[k] is not None]
        placeholders = ', '.join(['?'] * len(fields))
        columns = ', '.join(fields)
        values = [record[k] for k in fields]

        conn.execute(f'INSERT INTO intake_forms ({columns}) VALUES ({placeholders})', values)
        print(f"  Inserted new form {form_id}")

    return True


def import_requirements_file(conn, file_path, dry_run=False):
    """Import a single requirements.md file."""
    print(f"Processing: {file_path}")

    frontmatter, body = parse_markdown_file(file_path)

    if not frontmatter:
        print("  Warning: No valid frontmatter found, skipping")
        return False

    # Convert to database record
    record = frontmatter_to_db_record(frontmatter)

    # Extract agent notes from body
    agent_notes = extract_agent_notes_from_body(body)
    if agent_notes:
        record['agent_notes'] = agent_notes

    # Update database
    return update_intake_form(conn, record, dry_run)


def find_requirements_files(base_dir):
    """Find all requirements.md files in the client folder structure."""
    files = []
    for phase_dir in ['01_QUALIFY', '02_CURATE', '03_CLOSE', '04_NURTURE']:
        phase_path = base_dir / phase_dir
        if phase_path.exists():
            for req_file in phase_path.glob('*/requirements.md'):
                files.append(req_file)
    return files


def main():
    parser = argparse.ArgumentParser(description='Import requirements from markdown files')
    parser.add_argument('--file', help='Import specific file')
    parser.add_argument('--all', action='store_true', help='Import all requirements.md files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be imported without writing')
    args = parser.parse_args()

    conn = get_db_connection()

    files_to_process = []

    if args.file:
        files_to_process = [Path(args.file)]
    elif args.all:
        files_to_process = find_requirements_files(CLIENTS_DIR)
    else:
        print("Specify --file PATH or --all to import requirements")
        print(f"Looking in: {CLIENTS_DIR}")
        return

    if not files_to_process:
        print("No requirements files found")
        return

    print(f"Found {len(files_to_process)} file(s) to process")
    print()

    success = 0
    failed = 0

    for file_path in files_to_process:
        if import_requirements_file(conn, file_path, dry_run=args.dry_run):
            success += 1
        else:
            failed += 1

    if not args.dry_run:
        conn.commit()

    conn.close()

    print()
    print(f"Results: {success} success, {failed} failed")


if __name__ == '__main__':
    main()
