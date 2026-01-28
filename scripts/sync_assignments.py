#!/usr/bin/env python3
"""
Sync Assignments - Fetch current assignments from FUB and populate database

This script:
1. Fetches all users from FUB and caches them
2. Fetches all contacts and their current ownerId
3. Updates the assigned_user_id/assigned_user_name in the leads table
4. Records initial assignment history entries

Run this once to backfill assignment data, then the regular FUB sync will track changes.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from src.core.database import DREAMSDatabase
from fub_core import FUBClient

# Configuration
FUB_API_KEY = os.getenv("FUB_API_KEY")
DB_PATH = os.getenv("DREAMS_DB_PATH", str(PROJECT_ROOT / "data" / "dreams.db"))


def main():
    print("=" * 60)
    print("Assignment Sync - Backfill FUB assignments")
    print("=" * 60)

    # Initialize database
    print("\n📊 Initializing database...")
    db = DREAMSDatabase(DB_PATH)
    print(f"   Database: {DB_PATH}")

    # Initialize FUB client
    print("\n🔌 Connecting to FUB API...")
    fub = FUBClient(api_key=FUB_API_KEY)

    # Fetch users
    print("\n👥 Fetching team members...")
    users = fub.fetch_users()
    print(f"   Found {len(users)} users")

    # Build user lookup
    user_lookup = {u['id']: u['name'] for u in users if u.get('id') and u.get('name')}

    # Sync users to database
    print("\n💾 Syncing users to database cache...")
    count = db.sync_fub_users(users)
    print(f"   Synced {count} users")

    # Print user list
    print("\n   Team Members:")
    for u in users:
        print(f"   - {u.get('id')}: {u.get('name')} ({u.get('email')})")

    # Fetch all contacts
    print("\n📋 Fetching contacts from FUB...")
    people = fub.fetch_people()
    print(f"   Found {len(people)} contacts")

    # Update assignments
    print("\n🔄 Updating contact assignments...")
    updated = 0
    new_assignments = 0
    skipped = 0

    for person in people:
        fub_id = str(person.get('id'))
        # FUB API returns assignedUserId, not ownerId
        owner_id = person.get('assignedUserId')
        owner_name_from_api = person.get('assignedTo')  # Pre-resolved name from FUB

        if not owner_id:
            skipped += 1
            continue

        # Use FUB-provided name if available, otherwise look up
        owner_name = owner_name_from_api or user_lookup.get(owner_id, f"User {owner_id}")

        # Check if contact exists in our database (look up by fub_id, not id)
        contact = db.get_contact_by_fub_id(fub_id)
        if not contact:
            skipped += 1
            continue

        # Get the actual contact ID (may be UUID or fub_id depending on when created)
        contact_id = contact.get('id')

        # Check if assignment is different
        current_owner_id = contact.get('assigned_user_id')
        if current_owner_id != owner_id:
            # Update assignment (this will also record in history)
            changed = db.update_contact_assignment(
                contact_id=contact_id,  # Use the actual ID from the record
                new_user_id=owner_id,
                new_user_name=owner_name,
                source='backfill'
            )
            if changed:
                new_assignments += 1
            else:
                # First time assignment - update directly
                with db._get_connection() as conn:
                    now = datetime.now().isoformat()
                    conn.execute('''
                        UPDATE leads SET
                            assigned_user_id = ?,
                            assigned_user_name = ?,
                            assigned_at = ?,
                            updated_at = ?
                        WHERE id = ?
                    ''', (owner_id, owner_name, now, now, contact_id))

                    # Record initial assignment
                    conn.execute('''
                        INSERT INTO assignment_history
                        (contact_id, assigned_from_user_id, assigned_from_user_name,
                         assigned_to_user_id, assigned_to_user_name, assigned_at, source)
                        VALUES (?, NULL, NULL, ?, ?, ?, 'backfill')
                    ''', (contact_id, owner_id, owner_name, now))
                    conn.commit()
                    new_assignments += 1

            updated += 1

    print(f"\n✅ Assignment sync complete!")
    print(f"   - Contacts processed: {len(people)}")
    print(f"   - Assignments updated: {updated}")
    print(f"   - New history entries: {new_assignments}")
    print(f"   - Skipped (no owner or not in DB): {skipped}")

    # Show current stats for the configured user
    my_user_id = int(os.getenv('FUB_MY_USER_ID', 8))
    my_user = db.get_fub_user(my_user_id)
    stats = db.get_user_assignment_stats(my_user_id)

    print(f"\n📈 Your Stats ({my_user.get('name') if my_user else 'Unknown'}, ID: {my_user_id}):")
    print(f"   - Currently assigned: {stats['current_count']}")
    print(f"   - Received (30 days): {stats['received_30d']}")
    print(f"   - Transferred out (30 days): {stats['transferred_30d']}")


if __name__ == "__main__":
    main()
