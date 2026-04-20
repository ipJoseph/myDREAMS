#!/usr/bin/env python3
"""
FUB Smart List Generator

Reusable scripts to generate contact lists matching FUB smart list criteria.
Lists are saved as CSV files ready for Gmail Mail Merge.

Usage:
    python fub_smart_lists.py unresponsive_biweekly
    python fub_smart_lists.py cool_quarterly
    python fub_smart_lists.py --list-all

Available Lists:
    - unresponsive_biweekly: Stage=Lead, Created>14d, LastComm>14d
    - cool_quarterly: Stage=Nurture, LastComm>90d, Timeframe=12+mo/NoPlan/6-12mo
"""

import argparse
import base64
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# FUB Configuration
FUB_API_KEY = os.getenv('FUB_API_KEY')
FUB_MY_USER_ID = int(os.getenv('FUB_MY_USER_ID', 8))
FUB_BASE_URL = 'https://api.followupboss.com/v1'

# Output directory
OUTPUT_DIR = PROJECT_ROOT / 'data' / 'smart_lists'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_fub_headers() -> Dict[str, str]:
    """Get FUB API headers with authentication."""
    auth = base64.b64encode(f'{FUB_API_KEY}:'.encode()).decode()
    return {'Authorization': f'Basic {auth}'}


def fetch_people(stage: str, limit: int = 100) -> List[Dict]:
    """Fetch all people with a given stage from FUB."""
    headers = get_fub_headers()
    all_people = []
    offset = 0

    while True:
        params = {'stage': stage, 'limit': limit, 'offset': offset}
        resp = requests.get(f'{FUB_BASE_URL}/people', headers=headers, params=params)

        if not resp.ok:
            print(f"API Error: {resp.status_code} - {resp.text}")
            break

        people = resp.json().get('people', [])
        if not people:
            break

        all_people.extend(people)
        offset += limit

        if len(people) < limit:
            break

    return all_people


def extract_contact_info(person: Dict) -> Dict:
    """Extract standardized contact info from FUB person."""
    first_name = person.get('firstName', '')
    last_name = person.get('lastName', '')

    return {
        'id': person.get('id'),
        'first_name': first_name,
        'last_name': last_name,
        'name': f'{first_name} {last_name}'.strip(),
        'email': next((e.get('value') for e in person.get('emails', []) if e.get('value')), ''),
        'phone': next((p.get('value') for p in person.get('phones', []) if p.get('value')), ''),
        'stage': person.get('stage', ''),
        'created': person.get('created', '')[:10] if person.get('created') else '',
        'last_comm': (person.get('lastCommunication', {}) or {}).get('date', '')[:10] if person.get('lastCommunication') else 'Never',
        'assigned_user_id': person.get('assignedUserId'),
    }


def save_to_csv(leads: List[Dict], filename: str, extra_fields: List[str] = None) -> str:
    """Save leads to CSV file."""
    timestamp = datetime.now().strftime('%Y%m%d')
    filepath = OUTPUT_DIR / f'{filename}_{timestamp}.csv'

    fieldnames = ['id', 'first_name', 'last_name', 'name', 'email', 'phone', 'created', 'last_comm']
    if extra_fields:
        fieldnames.extend(extra_fields)

    with open(filepath, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(leads)

    return str(filepath)


# =============================================================================
# SMART LIST DEFINITIONS
# =============================================================================

def unresponsive_biweekly(dry_run: bool = False) -> List[Dict]:
    """
    UnresponsiveBiweekly Smart List

    Criteria:
        - Stage: Lead
        - Created: more than 14 days ago
        - Last Communication: more than 14 days ago (or never)
        - Assigned to: Me (FUB_MY_USER_ID)

    Purpose: Re-engage leads who haven't been contacted in 2 weeks
    Recommended frequency: Every 2 weeks
    """
    print("=" * 60)
    print("UNRESPONSIVE BIWEEKLY")
    print("=" * 60)

    cutoff_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    print(f"Criteria: Stage=Lead, Created<{cutoff_date}, LastComm<{cutoff_date}")
    print(f"Assigned to user ID: {FUB_MY_USER_ID}")
    print()

    # Fetch all leads
    people = fetch_people(stage='Lead')
    print(f"Total Lead stage contacts: {len(people)}")

    # Filter by criteria
    matching = []
    for person in people:
        contact = extract_contact_info(person)

        # Must be assigned to me
        if contact['assigned_user_id'] != FUB_MY_USER_ID:
            continue

        # Created more than 14 days ago
        if not contact['created'] or contact['created'] >= cutoff_date:
            continue

        # Last comm more than 14 days ago (or never)
        last_comm = contact['last_comm']
        if last_comm != 'Never' and last_comm >= cutoff_date:
            continue

        matching.append(contact)

    print(f"Matching contacts: {len(matching)}")
    print(f"  With email: {sum(1 for c in matching if c['email'])}")
    print(f"  With phone: {sum(1 for c in matching if c['phone'])}")

    if not dry_run and matching:
        filepath = save_to_csv(matching, 'unresponsive_biweekly')
        print(f"\nSaved to: {filepath}")

    return matching


def get_last_personal_comm(person_id: int, headers: Dict) -> Optional[str]:
    """
    Get the date of last PERSONAL communication for a contact.

    FUB's UI "Last Communication" counts only personal emails, calls, and texts.
    Bulk emails (campaignOrigin: "FUB Bulk") are excluded.

    Returns: Date string (YYYY-MM-DD) or None if never communicated.
    """
    last_comm_date = None

    # Check emails (exclude bulk/automated)
    resp = requests.get(
        f'{FUB_BASE_URL}/emails',
        headers=headers,
        params={'personId': person_id, 'limit': 50}
    )
    if resp.ok:
        for email in resp.json().get('emails', []):
            # Skip bulk/automated emails
            origin = (email.get('campaignOrigin') or '').lower()
            if 'bulk' in origin or 'drip' in origin or 'auto' in origin:
                continue

            created = email.get('created', '')[:10]
            if created and (not last_comm_date or created > last_comm_date):
                last_comm_date = created

    # Check calls
    resp = requests.get(
        f'{FUB_BASE_URL}/calls',
        headers=headers,
        params={'personId': person_id, 'limit': 50}
    )
    if resp.ok:
        for call in resp.json().get('calls', []):
            created = call.get('created', '')[:10]
            if created and (not last_comm_date or created > last_comm_date):
                last_comm_date = created

    # Check text messages
    resp = requests.get(
        f'{FUB_BASE_URL}/textMessages',
        headers=headers,
        params={'personId': person_id, 'limit': 50}
    )
    if resp.ok:
        for text in resp.json().get('textmessages', []):
            created = text.get('created', '')[:10]
            if created and (not last_comm_date or created > last_comm_date):
                last_comm_date = created

    return last_comm_date


def cool_quarterly(dry_run: bool = False) -> List[Dict]:
    """
    CoolQuarterly Smart List

    Criteria:
        - Stage: Nurture
        - Timeframe: includes "12+ Months", "No Plans", or "6-12 Months" (IDs: 3, 4, 5)
        - Last Communication: more than 90 days ago
        - IMPORTANT: Excludes contacts who have NEVER been communicated with
        - Assigned to: Me (FUB_MY_USER_ID)

    Purpose: Re-engage nurture contacts on a quarterly basis
    Recommended frequency: Every 90 days (quarterly)

    Note: FUB's "Last Communication" is calculated from actual email/call/text
    records, excluding bulk emails (campaignOrigin: "FUB Bulk").
    """
    print("=" * 60)
    print("COOL QUARTERLY")
    print("=" * 60)

    cutoff_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    print(f"Cutoff date: {cutoff_date}")
    print(f"Timeframe targets: 6-12 Months (ID 3), 12+ Months (ID 4), No Plans (ID 5)")
    print(f"Assigned to user ID: {FUB_MY_USER_ID}")
    print()

    headers = get_fub_headers()

    # Target timeframe IDs
    # FUB timeframes: 1=0-3mo, 2=3-6mo, 3=6-12mo, 4=12+mo, 5=No Plans
    target_timeframe_ids = [3, 4, 5]

    # Fetch Nurture contacts with target timeframes
    print("Fetching Nurture contacts with target timeframes...")
    all_people = {}  # Use dict to dedupe by ID

    for tf_id in target_timeframe_ids:
        offset = 0
        while True:
            params = {
                'stage': 'Nurture',
                'timeframeId': tf_id,
                'limit': 100,
                'offset': offset
            }
            resp = requests.get(f'{FUB_BASE_URL}/people', headers=headers, params=params)

            if not resp.ok:
                print(f"  API Error for timeframe {tf_id}: {resp.status_code}")
                break

            people = resp.json().get('people', [])
            if not people:
                break

            for person in people:
                all_people[person['id']] = person  # Dedupe by ID
            offset += 100

            if len(people) < 100:
                break

    all_people = list(all_people.values())
    print(f"Found {len(all_people)} contacts matching Stage/Timeframe")

    # Filter by assignment
    assigned_to_me = [p for p in all_people if p.get('assignedUserId') == FUB_MY_USER_ID]
    print(f"Assigned to me: {len(assigned_to_me)}")

    # Check actual communication records (this takes time)
    print("\nChecking actual communication records (this may take a minute)...")
    matching = []
    never_communicated = 0
    recent_comm = 0

    for i, person in enumerate(assigned_to_me):
        if i > 0 and i % 20 == 0:
            print(f"  Processed {i}/{len(assigned_to_me)}...")

        contact = extract_contact_info(person)

        # Get actual last personal communication date
        last_comm = get_last_personal_comm(person['id'], headers)

        if last_comm is None:
            # Never communicated - FUB excludes these from "more than X days" filter
            never_communicated += 1
            contact['last_comm'] = 'Never'
            continue

        if last_comm >= cutoff_date:
            # Recent communication - doesn't match
            recent_comm += 1
            continue

        # Has communication AND it was > 90 days ago
        contact['last_comm'] = last_comm

        # Get timeframe label
        timeframe = person.get('timeframe', '') or ''
        for cf in person.get('customFields', []):
            cf_name = cf.get('name', '').lower()
            if 'timeframe' in cf_name or 'timeline' in cf_name:
                timeframe = cf.get('value', '') or timeframe
        contact['timeframe'] = timeframe

        matching.append(contact)

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total checked: {len(assigned_to_me)}")
    print(f"  With comm > 90 days ago: {len(matching)}")
    print(f"  Never communicated (excluded): {never_communicated}")
    print(f"  Recent comm < 90 days: {recent_comm}")
    print()
    print(f"Final matching contacts: {len(matching)}")
    print(f"  With email: {sum(1 for c in matching if c['email'])}")
    print(f"  With phone: {sum(1 for c in matching if c['phone'])}")

    if not dry_run and matching:
        filepath = save_to_csv(matching, 'cool_quarterly', extra_fields=['timeframe'])
        print(f"\nSaved to: {filepath}")

    return matching


# =============================================================================
# CLI
# =============================================================================

SMART_LISTS = {
    'unresponsive_biweekly': unresponsive_biweekly,
    'cool_quarterly': cool_quarterly,
}


def main():
    parser = argparse.ArgumentParser(
        description='Generate FUB smart list CSVs for mail merge',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('list_name', nargs='?', help='Smart list to generate')
    parser.add_argument('--list-all', action='store_true', help='Show available lists')
    parser.add_argument('--dry-run', action='store_true', help='Query but do not save CSV')
    parser.add_argument('--all', action='store_true', help='Generate all lists')

    args = parser.parse_args()

    if args.list_all:
        print("Available Smart Lists:")
        print("-" * 40)
        for name, func in SMART_LISTS.items():
            doc = func.__doc__.strip().split('\n')[0] if func.__doc__ else 'No description'
            print(f"  {name}")
            print(f"    {doc}")
            print()
        return

    if args.all:
        for name, func in SMART_LISTS.items():
            print()
            func(dry_run=args.dry_run)
            print()
        return

    if not args.list_name:
        parser.print_help()
        print("\nAvailable lists:", ', '.join(SMART_LISTS.keys()))
        return

    if args.list_name not in SMART_LISTS:
        print(f"Unknown list: {args.list_name}")
        print(f"Available: {', '.join(SMART_LISTS.keys())}")
        sys.exit(1)

    SMART_LISTS[args.list_name](dry_run=args.dry_run)


if __name__ == '__main__':
    main()
