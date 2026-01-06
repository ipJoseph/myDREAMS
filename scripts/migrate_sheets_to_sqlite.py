#!/usr/bin/env python3
"""
Migrate Google Sheets Lead Data to SQLite

This script imports leads from your existing "FUB Contacts" Google Sheet
into the DREAMS SQLite database.

Usage:
    python scripts/migrate_sheets_to_sqlite.py

Run from your myDREAMS repository root.
"""

import sys
import os
import json
import uuid
from pathlib import Path
from datetime import datetime

# Repo root
REPO_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

import gspread
from google.oauth2.service_account import Credentials

from src.core.database import DREAMSDatabase
from src.utils.config import load_config


# =========================================================================
# CONFIGURATION - Update these to match your setup
# =========================================================================

# Path to service account JSON (relative to repo root)
SERVICE_ACCOUNT_FILE = "service_account.json"

# Your Google Sheet name or ID
SPREADSHEET_NAME = "FUB Contacts - Integrity Pursuits"
# Or use SPREADSHEET_ID if you prefer:
# SPREADSHEET_ID = "your-spreadsheet-id-here"

# Sheet/tab name within the spreadsheet
WORKSHEET_NAME = "Contacts"  # Update if different

# =========================================================================
# FIELD MAPPING: Google Sheet Column → SQLite Field
# =========================================================================

FIELD_MAP = {
    # Direct mappings
    "id": "external_id",
    "firstName": "first_name",
    "lastName": "last_name",
    "stage": "stage",
    "source": "source",
    "primaryEmail": "email",
    "primaryPhone": "phone",
    "ownerId": "assigned_agent",
    
    # Scores (direct)
    "heat_score": "heat_score",
    "value_score": "value_score",
    "relationship_score": "relationship_score",
    "priority_score": "priority_score",
    
    # These go into tags (JSON array)
    "leadTypeTags": "_tags",
    
    # Timestamps
    "created": "created_at",
    "updated": "updated_at",
    
    # Behavioral signals - we'll store these in a JSON notes field
    # to preserve them for the matching engine
    "lastActivity": "_last_activity",
    "last_website_visit": "_last_website_visit",
    "avg_price_viewed": "_avg_price_viewed",
    "website_visits": "_website_visits",
    "properties_viewed": "_properties_viewed",
    "properties_favorited": "_properties_favorited",
    "properties_shared": "_properties_shared",
    "calls_outbound": "_calls_outbound",
    "calls_inbound": "_calls_inbound",
    "texts_total": "_texts_total",
    "texts_inbound": "_texts_inbound",
    "emails_received": "_emails_received",
    "emails_sent": "_emails_sent",
    
    # Intent signals
    "intent_repeat_views": "_intent_repeat_views",
    "intent_high_favorites": "_intent_high_favorites",
    "intent_activity_burst": "_intent_activity_burst",
    "intent_sharing": "_intent_sharing",
    
    # Action items
    "next_action": "_next_action",
    "next_action_date": "_next_action_date",
    
    # Other
    "company": "_company",
    "website": "_website",
}


def connect_to_sheets():
    """Connect to Google Sheets API."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
    
    sa_path = REPO_ROOT / SERVICE_ACCOUNT_FILE
    if not sa_path.exists():
        # Try apps/fub-to-sheets location
        sa_path = REPO_ROOT / "apps" / "fub-to-sheets" / "service_account.json"
    
    if not sa_path.exists():
        print(f"ERROR: Service account file not found at {sa_path}")
        sys.exit(1)
    
    print(f"Using service account: {sa_path}")
    
    credentials = Credentials.from_service_account_file(str(sa_path), scopes=scopes)
    client = gspread.authorize(credentials)
    
    return client


def get_sheet_data(client):
    """Fetch all data from the Google Sheet."""
    try:
        # Try by name first
        spreadsheet = client.open(SPREADSHEET_NAME)
        print(f"Opened spreadsheet: {SPREADSHEET_NAME}")
    except gspread.SpreadsheetNotFound:
        print(f"ERROR: Spreadsheet '{SPREADSHEET_NAME}' not found")
        print("Make sure the service account has access to the sheet.")
        sys.exit(1)
    
    # Get the worksheet
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        # Try first worksheet
        worksheet = spreadsheet.sheet1
        print(f"Using first worksheet: {worksheet.title}")
    
    # Get all data
    all_data = worksheet.get_all_records()
    print(f"Found {len(all_data)} rows")
    
    return all_data


def parse_score(value):
    """Safely parse a score value to integer."""
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def parse_tags(value):
    """Parse leadTypeTags into a JSON array."""
    if not value:
        return "[]"
    
    # Handle various formats
    if isinstance(value, list):
        return json.dumps(value)
    
    # Comma-separated string
    if isinstance(value, str):
        tags = [t.strip() for t in value.split(",") if t.strip()]
        return json.dumps(tags)
    
    return "[]"


def infer_lead_type(tags_str, source):
    """Infer lead type (buyer/seller/both) from tags and source."""
    tags_lower = tags_str.lower() if tags_str else ""
    source_lower = source.lower() if source else ""
    
    is_buyer = "buyer" in tags_lower or "buyer" in source_lower
    is_seller = "seller" in tags_lower or "seller" in source_lower
    
    if is_buyer and is_seller:
        return "both"
    elif is_seller:
        return "seller"
    else:
        return "buyer"  # Default assumption


def build_behavioral_notes(row, field_map):
    """Build a JSON object with behavioral signals."""
    behavioral = {}
    
    for sheet_col, mapped in field_map.items():
        if mapped.startswith("_"):
            value = row.get(sheet_col, "")
            if value not in (None, "", "0", 0):
                # Remove the underscore prefix for storage
                key = mapped[1:]
                behavioral[key] = value
    
    return json.dumps(behavioral) if behavioral else None


def infer_price_range(row):
    """Infer min/max price from avg_price_viewed."""
    avg_price = row.get("avg_price_viewed", "")
    if not avg_price:
        return None, None
    
    try:
        avg = float(avg_price)
        # Assume they'd look at properties within 20% of average viewed
        min_price = int(avg * 0.8)
        max_price = int(avg * 1.2)
        return min_price, max_price
    except (ValueError, TypeError):
        return None, None


def migrate_row(row, db):
    """Migrate a single row to SQLite."""
    
    # Generate internal DREAMS ID
    dreams_id = str(uuid.uuid4())
    
    # Get FUB ID
    fub_id = str(row.get("id", ""))
    if not fub_id:
        return False, "No ID"
    
    # Parse tags
    tags_json = parse_tags(row.get("leadTypeTags", ""))
    
    # Infer lead type
    lead_type = infer_lead_type(row.get("leadTypeTags", ""), row.get("source", ""))
    
    # Build behavioral notes
    behavioral_notes = build_behavioral_notes(row, FIELD_MAP)
    
    # Infer price range from viewing behavior
    min_price, max_price = infer_price_range(row)
    
    # Prepare the lead record
    from src.adapters.base_adapter import Lead
    
    lead = Lead(
        id=dreams_id,
        external_id=fub_id,
        external_source="followupboss",
        first_name=str(row.get("firstName", "")).strip(),
        last_name=str(row.get("lastName", "")).strip(),
        email=str(row.get("primaryEmail", "")).strip() or None,
        phone=str(row.get("primaryPhone", "")).strip() or None,
        stage=str(row.get("stage", "lead")).strip().lower(),
        type=lead_type,
        source=str(row.get("source", "")).strip() or None,
        assigned_agent=str(row.get("ownerId", "")).strip() or None,
        tags=json.loads(tags_json),
        notes=behavioral_notes,
        heat_score=parse_score(row.get("heat_score")),
        value_score=parse_score(row.get("value_score")),
        relationship_score=parse_score(row.get("relationship_score")),
        priority_score=parse_score(row.get("priority_score")),
        min_price=min_price,
        max_price=max_price,
    )
    
    # Parse timestamps
    created = row.get("created", "")
    updated = row.get("updated", "")
    
    if created:
        try:
            lead.created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except:
            pass
    
    if updated:
        try:
            lead.updated_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except:
            pass
    
    # Upsert to database
    db.upsert_lead(lead)
    
    return True, None


def main():
    print("=" * 60)
    print("DREAMS Platform - Google Sheets to SQLite Migration")
    print("=" * 60)
    print()
    
    # Load config and connect to database
    config = load_config()
    db_path = REPO_ROOT / "data" / "dreams.db"
    
    print(f"Database: {db_path}")
    db = DREAMSDatabase(str(db_path))
    
    # Connect to Google Sheets
    print()
    print("Connecting to Google Sheets...")
    client = connect_to_sheets()
    
    # Fetch data
    print()
    print("Fetching lead data...")
    rows = get_sheet_data(client)
    
    if not rows:
        print("No data found in sheet!")
        return 1
    
    # Show sample of columns found
    print()
    print(f"Columns found: {list(rows[0].keys())[:10]}...")
    
    # Migrate each row
    print()
    print("Migrating leads to SQLite...")
    
    success_count = 0
    error_count = 0
    errors = []
    
    for i, row in enumerate(rows):
        try:
            success, error = migrate_row(row, db)
            if success:
                success_count += 1
            else:
                error_count += 1
                errors.append(f"Row {i+1}: {error}")
        except Exception as e:
            error_count += 1
            errors.append(f"Row {i+1}: {str(e)}")
        
        # Progress indicator
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(rows)}...")
    
    # Summary
    print()
    print("=" * 60)
    print("Migration Complete!")
    print("=" * 60)
    print(f"  Total rows:    {len(rows)}")
    print(f"  Successful:    {success_count}")
    print(f"  Errors:        {error_count}")
    
    if errors and len(errors) <= 10:
        print()
        print("Errors:")
        for e in errors:
            print(f"  - {e}")
    elif errors:
        print(f"  (Showing first 10 of {len(errors)} errors)")
        for e in errors[:10]:
            print(f"  - {e}")
    
    # Verify
    print()
    print("Verifying migration...")
    leads = db.get_leads(limit=5)
    print(f"  Sample leads in database:")
    for lead in leads[:5]:
        name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
        score = lead.get('priority_score', 0)
        print(f"    - {name} (Priority: {score})")
    
    print()
    print("Next: Run property migration or test the matching engine.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
