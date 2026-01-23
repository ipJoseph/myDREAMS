#!/usr/bin/env python3
"""
Backfill contact_daily_activity table from existing events and communications.

This script populates the contact_daily_activity table with historical data
aggregated from contact_events and contact_communications tables.

Usage:
    python scripts/backfill_daily_activity.py [--days 90] [--dry-run]

Options:
    --days N    Number of days to backfill (default: 90)
    --dry-run   Show what would be done without making changes
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import DREAMSDatabase


def get_distinct_dates_with_activity(db, days: int) -> list:
    """Get all dates that have activity data."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    with db._get_connection() as conn:
        # Get dates from events
        event_dates = conn.execute('''
            SELECT DISTINCT DATE(occurred_at) as activity_date
            FROM contact_events
            WHERE DATE(occurred_at) >= ?
        ''', (cutoff,)).fetchall()

        # Get dates from communications
        comm_dates = conn.execute('''
            SELECT DISTINCT DATE(occurred_at) as activity_date
            FROM contact_communications
            WHERE DATE(occurred_at) >= ?
        ''', (cutoff,)).fetchall()

        # Combine and deduplicate
        all_dates = set()
        for row in event_dates:
            all_dates.add(row['activity_date'])
        for row in comm_dates:
            all_dates.add(row['activity_date'])

        return sorted(all_dates)


def get_contacts_with_activity_on_date(db, activity_date: str) -> list:
    """Get all contacts that have activity on a specific date."""
    date_start = f"{activity_date}T00:00:00"
    date_end = f"{activity_date}T23:59:59"

    with db._get_connection() as conn:
        # Contacts with events
        event_contacts = conn.execute('''
            SELECT DISTINCT contact_id
            FROM contact_events
            WHERE occurred_at >= ? AND occurred_at <= ?
        ''', (date_start, date_end)).fetchall()

        # Contacts with communications
        comm_contacts = conn.execute('''
            SELECT DISTINCT contact_id
            FROM contact_communications
            WHERE occurred_at >= ? AND occurred_at <= ?
        ''', (date_start, date_end)).fetchall()

        # Combine and deduplicate
        all_contacts = set()
        for row in event_contacts:
            all_contacts.add(row['contact_id'])
        for row in comm_contacts:
            all_contacts.add(row['contact_id'])

        return list(all_contacts)


def get_contact_scores_on_date(db, contact_id: str, activity_date: str) -> dict:
    """Get the contact's scores closest to the given date."""
    with db._get_connection() as conn:
        # Try to get score from scoring history for that date
        row = conn.execute('''
            SELECT heat_score, value_score, relationship_score, priority_score
            FROM contact_scoring_history
            WHERE contact_id = ? AND DATE(recorded_at) <= ?
            ORDER BY recorded_at DESC
            LIMIT 1
        ''', (contact_id, activity_date)).fetchone()

        if row:
            return {
                'heat_score': row['heat_score'],
                'value_score': row['value_score'],
                'relationship_score': row['relationship_score'],
                'priority_score': row['priority_score']
            }

        # Fall back to current contact scores
        contact = conn.execute('''
            SELECT heat_score, value_score, relationship_score, priority_score
            FROM leads WHERE id = ?
        ''', (contact_id,)).fetchone()

        if contact:
            return {
                'heat_score': contact['heat_score'],
                'value_score': contact['value_score'],
                'relationship_score': contact['relationship_score'],
                'priority_score': contact['priority_score']
            }

        return {}


def backfill_daily_activity(db_path: str, days: int = 90, dry_run: bool = False):
    """
    Backfill the contact_daily_activity table.

    Args:
        db_path: Path to the SQLite database
        days: Number of days to backfill
        dry_run: If True, don't actually write data
    """
    db = DREAMSDatabase(db_path)

    print(f"Backfilling contact_daily_activity for the last {days} days...")
    if dry_run:
        print("DRY RUN - no changes will be made")
    print()

    # Get all dates with activity
    dates = get_distinct_dates_with_activity(db, days)
    print(f"Found {len(dates)} dates with activity")

    total_records = 0
    total_contacts = 0

    for activity_date in dates:
        contacts = get_contacts_with_activity_on_date(db, activity_date)
        date_records = 0

        for contact_id in contacts:
            # Aggregate activity from events/communications
            activity = db.aggregate_daily_activity_from_events(contact_id, activity_date)

            # Get scores for that date
            scores = get_contact_scores_on_date(db, contact_id, activity_date)

            # Record the daily activity
            if not dry_run:
                db.record_daily_activity(
                    contact_id=contact_id,
                    activity_date=activity_date,
                    website_visits=activity['website_visits'],
                    properties_viewed=activity['properties_viewed'],
                    properties_favorited=activity['properties_favorited'],
                    properties_shared=activity['properties_shared'],
                    calls_inbound=activity['calls_inbound'],
                    calls_outbound=activity['calls_outbound'],
                    texts_inbound=activity['texts_inbound'],
                    texts_outbound=activity['texts_outbound'],
                    emails_received=activity['emails_received'],
                    emails_sent=activity['emails_sent'],
                    heat_score=scores.get('heat_score'),
                    value_score=scores.get('value_score'),
                    relationship_score=scores.get('relationship_score'),
                    priority_score=scores.get('priority_score')
                )

            date_records += 1

        total_records += date_records
        total_contacts += len(contacts)
        print(f"  {activity_date}: {date_records} records ({len(contacts)} contacts)")

    print()
    print(f"Summary:")
    print(f"  Dates processed: {len(dates)}")
    print(f"  Total records: {total_records}")
    print(f"  Unique contact-days: {total_records}")

    if dry_run:
        print()
        print("DRY RUN completed - run without --dry-run to apply changes")


def main():
    parser = argparse.ArgumentParser(
        description='Backfill contact_daily_activity from existing events/communications'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=90,
        help='Number of days to backfill (default: 90)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Path to database (default: data/dreams.db)'
    )

    args = parser.parse_args()

    # Determine database path
    if args.db_path:
        db_path = args.db_path
    else:
        db_path = project_root / 'data' / 'dreams.db'

    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    backfill_daily_activity(str(db_path), args.days, args.dry_run)


if __name__ == '__main__':
    main()
