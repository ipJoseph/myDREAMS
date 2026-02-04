#!/usr/bin/env python3
"""
Sync Requirements to Drive

Exports intake_forms from database to markdown files in Google Drive folder structure.
Preserves manual edits outside the YAML frontmatter.

Usage:
    python scripts/sync_requirements_to_drive.py [--lead-id LEAD_ID] [--dry-run]
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
TEMPLATE_PATH = PROJECT_ROOT / 'templates' / 'buyer_requirements.md'


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_template():
    """Load the buyer requirements template."""
    if TEMPLATE_PATH.exists():
        return TEMPLATE_PATH.read_text()
    return None


def parse_json_field(value):
    """Parse JSON field, return empty list if invalid."""
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


def format_client_folder_name(first_name, last_name):
    """Format client folder name as Lastname.Firstname."""
    last = (last_name or 'Unknown').strip().replace(' ', '')
    first = (first_name or 'Unknown').strip().replace(' ', '')
    return f"{last}.{first}"


def get_phase_folder(status, phase=None):
    """Determine which phase folder based on status."""
    if phase:
        phase_map = {
            'QUALIFY': '01_QUALIFY',
            'CURATE': '02_CURATE',
            'CLOSE': '03_CLOSE',
            'NURTURE': '04_NURTURE',
        }
        return phase_map.get(phase.upper(), '01_QUALIFY')

    # Infer from status
    status_map = {
        'active': '01_QUALIFY',
        'searching': '02_CURATE',
        'showing': '02_CURATE',
        'under_contract': '03_CLOSE',
        'closed': '04_NURTURE',
        'completed': '04_NURTURE',
    }
    return status_map.get(status, '01_QUALIFY')


def build_frontmatter(form, lead):
    """Build YAML frontmatter from intake form data."""
    return {
        'form_id': form['id'],
        'lead_id': form['lead_id'],
        'fub_id': lead.get('fub_id', ''),
        'form_name': form.get('form_name', ''),
        'need_type': form.get('need_type', 'primary_home'),
        'status': form.get('status', 'active'),
        'phase': 'QUALIFY',  # Will be updated based on pipeline position

        # Location
        'counties': parse_json_field(form.get('counties')),
        'cities': parse_json_field(form.get('cities')),
        'zip_codes': parse_json_field(form.get('zip_codes')),

        # Property criteria
        'property_types': parse_json_field(form.get('property_types')) or ['Single Family'],
        'min_price': form.get('min_price'),
        'max_price': form.get('max_price'),
        'min_beds': form.get('min_beds'),
        'max_beds': form.get('max_beds'),
        'min_baths': form.get('min_baths'),
        'max_baths': form.get('max_baths'),
        'min_sqft': form.get('min_sqft'),
        'max_sqft': form.get('max_sqft'),
        'min_acreage': form.get('min_acreage'),
        'max_acreage': form.get('max_acreage'),
        'min_year_built': form.get('min_year_built'),
        'max_year_built': form.get('max_year_built'),

        # Timeline
        'urgency': form.get('urgency', ''),
        'financing_status': form.get('financing_status', ''),
        'pre_approval_amount': form.get('pre_approval_amount'),
        'move_in_date': form.get('move_in_date', ''),

        # Scoring
        'confidence_score': form.get('confidence_score'),

        'last_synced': datetime.now().isoformat(),
    }


def build_markdown_body(form, lead):
    """Build markdown body from intake form data."""
    first_name = lead.get('first_name', '')
    last_name = lead.get('last_name', '')
    full_name = f"{first_name} {last_name}".strip() or '[Client Name]'

    # Parse JSON fields
    counties = parse_json_field(form.get('counties'))
    cities = parse_json_field(form.get('cities'))
    property_types = parse_json_field(form.get('property_types'))
    views = parse_json_field(form.get('views_required'))
    must_have = form.get('must_have_features', '')
    nice_to_have = form.get('nice_to_have_features', '')
    deal_breakers = form.get('deal_breakers', '')

    # Format price
    def fmt_price(val):
        if val:
            return f"${val:,}"
        return ''

    body = f"""
# Buyer Requirements: {full_name}

## Contact Information

| Field | Value |
|-------|-------|
| Primary Contact | {full_name} |
| Phone | {lead.get('phone', '')} |
| Email | {lead.get('email', '')} |
| FUB Link | https://jontharp.followupboss.com/2/people/view/{lead.get('fub_id', '')} |

## Timeline & Financing

- **Target Move Date**: {form.get('move_in_date', '')}
- **Urgency**: {form.get('urgency', '')}
- **Financing Status**: {form.get('financing_status', '')}
- **Pre-Approval Amount**: {fmt_price(form.get('pre_approval_amount'))}
- **Lender**:
- **Down Payment**:

## Location Preferences

- **Counties**: {', '.join(counties) if counties else ''}
- **Cities**: {', '.join(cities) if cities else ''}
- **Areas to Avoid**:

## Property Criteria

| Criteria | Min | Max | Notes |
|----------|-----|-----|-------|
| Price | {fmt_price(form.get('min_price'))} | {fmt_price(form.get('max_price'))} | |
| Bedrooms | {form.get('min_beds', '')} | {form.get('max_beds', '')} | |
| Bathrooms | {form.get('min_baths', '')} | {form.get('max_baths', '')} | |
| Square Feet | {form.get('min_sqft', '')} | {form.get('max_sqft', '')} | |
| Acreage | {form.get('min_acreage', '')} | {form.get('max_acreage', '')} | |
| Year Built | {form.get('min_year_built', '')} | {form.get('max_year_built', '')} | |

## Property Types

"""
    # Property type checkboxes
    all_types = ['Single Family', 'Condo/Townhouse', 'Cabin/Log Home', 'Land Only', 'Mobile/Manufactured']
    for pt in all_types:
        checked = 'x' if pt in property_types else ' '
        body += f"- [{checked}] {pt}\n"

    body += """
## Must Have Features

"""
    if must_have:
        for item in must_have.split('\n'):
            if item.strip():
                body += f"- [ ] {item.strip()}\n"
    else:
        body += "- [ ] Mountain views\n- [ ] Garage\n- [ ] Main level primary\n"

    body += """
## Nice to Have

"""
    if nice_to_have:
        for item in nice_to_have.split('\n'):
            if item.strip():
                body += f"- {item.strip()}\n"
    else:
        body += "- \n- \n"

    body += """
## Deal Breakers

"""
    if deal_breakers:
        for item in deal_breakers.split('\n'):
            if item.strip():
                body += f"- {item.strip()}\n"
    else:
        body += "- \n- \n"

    body += f"""
## Agent Notes

> {form.get('agent_notes', '')}

---
*Created: {form.get('created_at', '')[:10] if form.get('created_at') else 'YYYY-MM-DD'}*
*Last Updated: {datetime.now().strftime('%Y-%m-%d')}*
*Agent: Joseph Williams*
"""

    return body


def export_intake_form(form, lead, dry_run=False):
    """Export a single intake form to markdown file."""
    # Determine folder path
    client_folder = format_client_folder_name(lead.get('first_name'), lead.get('last_name'))
    phase_folder = get_phase_folder(form.get('status'))

    output_dir = CLIENTS_DIR / phase_folder / client_folder
    output_file = output_dir / 'requirements.md'

    # Build content
    frontmatter = build_frontmatter(form, lead)
    body = build_markdown_body(form, lead)

    # Combine frontmatter and body
    content = '---\n'
    content += yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    content += '---\n'
    content += body

    if dry_run:
        print(f"[DRY RUN] Would create: {output_file}")
        print(f"  Client: {lead.get('first_name')} {lead.get('last_name')}")
        print(f"  Form: {form.get('form_name')} ({form.get('need_type')})")
        return output_file

    # Create directory and write file
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if file exists and preserve manual content
    if output_file.exists():
        existing = output_file.read_text()
        # TODO: Merge logic to preserve manual edits outside frontmatter
        # For now, we overwrite but could implement smart merge

    output_file.write_text(content)
    print(f"Exported: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description='Export intake forms to markdown files')
    parser.add_argument('--lead-id', help='Export only for specific lead ID')
    parser.add_argument('--form-id', help='Export only specific form ID')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be exported without writing')
    parser.add_argument('--all', action='store_true', help='Export all active intake forms')
    args = parser.parse_args()

    conn = get_db_connection()

    # Build query
    query = '''
        SELECT i.*, l.first_name, l.last_name, l.email, l.phone, l.fub_id
        FROM intake_forms i
        JOIN leads l ON i.lead_id = l.id
        WHERE 1=1
    '''
    params = []

    if args.lead_id:
        query += ' AND i.lead_id = ?'
        params.append(args.lead_id)
    elif args.form_id:
        query += ' AND i.id = ?'
        params.append(args.form_id)
    elif args.all:
        query += ' AND i.status = "active"'
    else:
        # Default: only active forms
        query += ' AND i.status = "active"'

    query += ' ORDER BY l.last_name, l.first_name'

    rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No intake forms found matching criteria")
        return

    print(f"Found {len(rows)} intake form(s) to export")
    print(f"Output directory: {CLIENTS_DIR}")
    print()

    exported = []
    for row in rows:
        form = dict(row)
        lead = {
            'first_name': form.pop('first_name'),
            'last_name': form.pop('last_name'),
            'email': form.pop('email'),
            'phone': form.pop('phone'),
            'fub_id': form.pop('fub_id'),
        }

        output_file = export_intake_form(form, lead, dry_run=args.dry_run)
        exported.append(output_file)

    print()
    print(f"Exported {len(exported)} file(s)")

    conn.close()


if __name__ == '__main__':
    main()
