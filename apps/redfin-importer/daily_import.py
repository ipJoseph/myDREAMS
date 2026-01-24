#!/usr/bin/env python3
"""
Daily Property Import CLI

Unified command for daily property data operations:
- Import Redfin CSVs with change detection
- Import PropStream bulk data
- Generate change reports

Usage:
    # Import Redfin CSVs with change detection
    python daily_import.py --redfin ~/Downloads/redfin_*.csv

    # Import PropStream bulk
    python daily_import.py --propstream ~/Downloads/propstream_*.xlsx

    # Generate change report for last 24 hours
    python daily_import.py --report

    # Generate change report since specific date
    python daily_import.py --report --since 2024-01-15

    # Combined: import and report
    python daily_import.py --redfin ~/Downloads/*.csv --report
"""

import argparse
import glob
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from redfin_csv_importer import RedfinCSVImporter
from propstream_importer import PropStreamImporter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.getenv('REDFIN_DB_PATH', str(PROJECT_ROOT / 'data' / 'redfin_imports.db'))


def expand_glob_patterns(patterns: List[str]) -> List[str]:
    """Expand glob patterns to actual file paths."""
    all_files = []
    for pattern in patterns:
        matches = glob.glob(os.path.expanduser(pattern))
        if matches:
            all_files.extend(sorted(matches))
        else:
            # If no glob match, add the pattern as-is (might be exact path)
            all_files.append(pattern)
    return all_files


def import_redfin(files: List[str], db_path: str, dry_run: bool = False) -> Dict:
    """Import Redfin CSV files."""
    logger.info(f"Importing {len(files)} Redfin CSV file(s)...")

    importer = RedfinCSVImporter(db_path=db_path, dry_run=dry_run, track_changes=True)
    stats = importer.import_multiple(files)

    return stats


def import_propstream(files: List[str], db_path: str, dry_run: bool = False) -> Dict:
    """Import PropStream Excel files."""
    logger.info(f"Importing {len(files)} PropStream Excel file(s)...")

    importer = PropStreamImporter(db_path=db_path, dry_run=dry_run)
    stats = importer.import_multiple(files)

    return stats


def generate_change_report(db_path: str, since: Optional[str] = None) -> Dict:
    """
    Generate a report of property changes.

    Args:
        db_path: Path to SQLite database
        since: ISO date string or 'yesterday', 'today', etc.

    Returns:
        Report dictionary with change summaries
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Parse 'since' parameter
    if since == 'yesterday':
        cutoff = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()
    elif since == 'today':
        cutoff = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
    elif since:
        cutoff = since
    else:
        # Default: last 24 hours
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()

    report = {
        'generated_at': datetime.now().isoformat(),
        'since': cutoff,
        'summary': {
            'total_changes': 0,
            'new_listings': 0,
            'price_changes': 0,
            'status_changes': 0,
            'dom_updates': 0,
        },
        'price_drops': [],
        'price_increases': [],
        'new_listings': [],
        'status_changes': [],
    }

    try:
        # Get change counts
        cursor = conn.cursor()

        # Summary counts
        cursor.execute('''
            SELECT change_type, COUNT(*) as count
            FROM property_changes
            WHERE detected_at >= ?
            GROUP BY change_type
        ''', (cutoff,))

        for row in cursor.fetchall():
            change_type = row['change_type']
            count = row['count']
            report['summary']['total_changes'] += count

            if change_type == 'new_listing':
                report['summary']['new_listings'] = count
            elif change_type == 'price_change':
                report['summary']['price_changes'] = count
            elif change_type == 'status_change':
                report['summary']['status_changes'] = count
            elif change_type == 'dom_update':
                report['summary']['dom_updates'] = count

        # Price drops (negative change_amount)
        cursor.execute('''
            SELECT pc.*, p.city, p.county, p.beds, p.baths
            FROM property_changes pc
            LEFT JOIN properties p ON pc.property_id = p.id
            WHERE pc.change_type = 'price_change'
            AND pc.change_amount < 0
            AND pc.detected_at >= ?
            ORDER BY pc.change_amount ASC
            LIMIT 20
        ''', (cutoff,))

        for row in cursor.fetchall():
            old_price = int(row['old_value']) if row['old_value'] else 0
            new_price = int(row['new_value']) if row['new_value'] else 0
            drop_pct = ((old_price - new_price) / old_price * 100) if old_price else 0

            report['price_drops'].append({
                'address': row['property_address'],
                'city': row['city'],
                'county': row['county'],
                'old_price': old_price,
                'new_price': new_price,
                'drop_amount': abs(row['change_amount'] or 0),
                'drop_pct': round(drop_pct, 1),
                'beds': row['beds'],
                'baths': row['baths'],
                'detected_at': row['detected_at'],
            })

        # Price increases
        cursor.execute('''
            SELECT pc.*, p.city, p.county
            FROM property_changes pc
            LEFT JOIN properties p ON pc.property_id = p.id
            WHERE pc.change_type = 'price_change'
            AND pc.change_amount > 0
            AND pc.detected_at >= ?
            ORDER BY pc.change_amount DESC
            LIMIT 10
        ''', (cutoff,))

        for row in cursor.fetchall():
            old_price = int(row['old_value']) if row['old_value'] else 0
            new_price = int(row['new_value']) if row['new_value'] else 0
            increase_pct = ((new_price - old_price) / old_price * 100) if old_price else 0

            report['price_increases'].append({
                'address': row['property_address'],
                'city': row['city'],
                'county': row['county'],
                'old_price': old_price,
                'new_price': new_price,
                'increase_amount': row['change_amount'],
                'increase_pct': round(increase_pct, 1),
                'detected_at': row['detected_at'],
            })

        # New listings
        cursor.execute('''
            SELECT pc.*, p.city, p.county, p.beds, p.baths, p.sqft, p.acreage
            FROM property_changes pc
            LEFT JOIN properties p ON pc.property_id = p.id
            WHERE pc.change_type = 'new_listing'
            AND pc.detected_at >= ?
            ORDER BY pc.detected_at DESC
            LIMIT 30
        ''', (cutoff,))

        for row in cursor.fetchall():
            price = int(row['new_value']) if row['new_value'] else None
            report['new_listings'].append({
                'address': row['property_address'],
                'city': row['city'],
                'county': row['county'],
                'price': price,
                'beds': row['beds'],
                'baths': row['baths'],
                'sqft': row['sqft'],
                'acreage': row['acreage'],
                'detected_at': row['detected_at'],
            })

        # Status changes
        cursor.execute('''
            SELECT pc.*, p.city, p.county, p.price
            FROM property_changes pc
            LEFT JOIN properties p ON pc.property_id = p.id
            WHERE pc.change_type = 'status_change'
            AND pc.detected_at >= ?
            ORDER BY pc.detected_at DESC
            LIMIT 20
        ''', (cutoff,))

        for row in cursor.fetchall():
            report['status_changes'].append({
                'address': row['property_address'],
                'city': row['city'],
                'county': row['county'],
                'old_status': row['old_value'],
                'new_status': row['new_value'],
                'price': row['price'],
                'detected_at': row['detected_at'],
            })

    finally:
        conn.close()

    return report


def print_report(report: Dict):
    """Print change report to console."""
    print("\n" + "=" * 70)
    print("PROPERTY CHANGE REPORT")
    print(f"Since: {report['since']}")
    print(f"Generated: {report['generated_at']}")
    print("=" * 70)

    summary = report['summary']
    print(f"\nTotal changes:    {summary['total_changes']}")
    print(f"  New listings:   {summary['new_listings']}")
    print(f"  Price changes:  {summary['price_changes']}")
    print(f"  Status changes: {summary['status_changes']}")
    print(f"  DOM updates:    {summary['dom_updates']}")

    # Price drops
    if report['price_drops']:
        print("\n" + "-" * 70)
        print("PRICE DROPS")
        print("-" * 70)
        for prop in report['price_drops'][:10]:
            print(f"  {prop['address']}, {prop['city']}")
            print(f"    ${prop['old_price']:,} -> ${prop['new_price']:,} (-${prop['drop_amount']:,}, -{prop['drop_pct']}%)")

    # New listings
    if report['new_listings']:
        print("\n" + "-" * 70)
        print("NEW LISTINGS")
        print("-" * 70)
        for prop in report['new_listings'][:15]:
            price_str = f"${prop['price']:,}" if prop['price'] else "Price N/A"
            specs = f"{prop['beds']}bd/{prop['baths']}ba" if prop['beds'] else ""
            print(f"  {prop['address']}, {prop['city']} ({prop['county']})")
            print(f"    {price_str} | {specs}")

    # Status changes
    if report['status_changes']:
        print("\n" + "-" * 70)
        print("STATUS CHANGES")
        print("-" * 70)
        for prop in report['status_changes'][:10]:
            price_str = f"${prop['price']:,}" if prop['price'] else ""
            print(f"  {prop['address']}: {prop['old_status']} -> {prop['new_status']} {price_str}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Daily property import CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python daily_import.py --redfin ~/Downloads/redfin_*.csv
  python daily_import.py --propstream ~/Downloads/propstream_*.xlsx
  python daily_import.py --report --since yesterday
  python daily_import.py --redfin ~/Downloads/*.csv --report
        """
    )

    # Import options
    parser.add_argument('--redfin', nargs='+', metavar='FILE',
                        help='Redfin CSV files to import')
    parser.add_argument('--propstream', nargs='+', metavar='FILE',
                        help='PropStream Excel files to import')

    # Report options
    parser.add_argument('--report', action='store_true',
                        help='Generate change report')
    parser.add_argument('--since', type=str, default=None,
                        help='Report changes since (date, "yesterday", "today")')

    # Common options
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse but do not import')
    parser.add_argument('--db', default=DB_PATH,
                        help='Database path')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Must specify at least one action
    if not args.redfin and not args.propstream and not args.report:
        parser.print_help()
        print("\nError: Must specify --redfin, --propstream, or --report")
        sys.exit(1)

    # Track overall stats
    all_stats = {
        'redfin': None,
        'propstream': None,
    }

    # Import Redfin CSVs
    if args.redfin:
        files = expand_glob_patterns(args.redfin)
        if not files:
            logger.error("No Redfin files found")
        else:
            all_stats['redfin'] = import_redfin(files, args.db, args.dry_run)

            print("\n" + "=" * 50)
            print("REDFIN IMPORT SUMMARY")
            print("=" * 50)
            stats = all_stats['redfin']
            print(f"Files imported:  {len(files)}")
            print(f"Rows processed:  {stats['rows_processed']}")
            print(f"New properties:  {stats['rows_imported']}")
            print(f"Updated:         {stats['rows_updated']}")
            print(f"Errors:          {stats['errors']}")
            print("-" * 50)
            changes = stats.get('changes_detected', {})
            print(f"New listings:    {changes.get('new_listing', 0)}")
            print(f"Price changes:   {changes.get('price_change', 0)}")
            print(f"Status changes:  {changes.get('status_change', 0)}")
            print("=" * 50)

    # Import PropStream Excel
    if args.propstream:
        files = expand_glob_patterns(args.propstream)
        if not files:
            logger.error("No PropStream files found")
        else:
            all_stats['propstream'] = import_propstream(files, args.db, args.dry_run)

            print("\n" + "=" * 50)
            print("PROPSTREAM IMPORT SUMMARY")
            print("=" * 50)
            stats = all_stats['propstream']
            print(f"Files imported:  {len(files)}")
            print(f"Rows processed:  {stats['rows_processed']}")
            print(f"New properties:  {stats['rows_imported']}")
            print(f"Updated/merged:  {stats['rows_updated']}")
            print(f"APNs added:      {stats['apn_added']}")
            print(f"Owner info:      {stats['owner_added']}")
            print(f"Errors:          {stats['errors']}")
            print("=" * 50)

    # Generate report
    if args.report:
        report = generate_change_report(args.db, args.since)
        print_report(report)

    if args.dry_run:
        print("\n[DRY RUN - No changes made]")


if __name__ == '__main__':
    main()
