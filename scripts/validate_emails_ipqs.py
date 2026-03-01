"""
Validate FUB contacts (no phone) via IPQualityScore Email Validation API.

Pulls contacts with no phone number from FUB, excludes Dawn Nichols and
Nicholas Vincent, then runs each email through IPQS for deliverability,
fraud scoring, and phone number discovery.

Usage:
    python3 scripts/validate_emails_ipqs.py
    python3 scripts/validate_emails_ipqs.py --dry-run    # list contacts only
    python3 scripts/validate_emails_ipqs.py --output csv  # save CSV report

Requires IPQS_API_KEY and FUB_API_KEY in .env
"""

import argparse
import base64
import csv
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Contacts to exclude (Dawn Nichols, Nicholas Vincent)
EXCLUDE_IDS = {25130, 12944}

# IPQS rate limit: be polite (free tier = ~100/day)
REQUEST_DELAY = 1.0


def get_fub_no_phone_contacts() -> list[dict]:
    """Fetch all FUB contacts that have no phone number."""
    api_key = os.getenv('FUB_API_KEY')
    if not api_key:
        logger.error("FUB_API_KEY not set in .env")
        sys.exit(1)

    creds = base64.b64encode(f'{api_key}:'.encode()).decode()
    contacts = []
    offset = 0

    logger.info("Fetching contacts from FUB...")
    while True:
        url = f'https://api.followupboss.com/v1/people?limit=100&offset={offset}'
        req = urllib.request.Request(url, headers={
            'Authorization': f'Basic {creds}',
            'Accept': 'application/json'
        })

        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        people = data.get('people', [])
        if not people:
            break

        for p in people:
            # Skip excluded contacts
            if p['id'] in EXCLUDE_IDS:
                continue

            # Check if contact has any phone number
            phones = p.get('phones', [])
            has_phone = any(ph.get('value', '').strip() for ph in phones) if phones else False
            if has_phone:
                continue

            # Must have an email to validate
            emails = p.get('emails', [])
            email = emails[0].get('value', '').strip() if emails else ''
            if not email:
                continue

            name = f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
            contacts.append({
                'fub_id': p['id'],
                'name': name,
                'email': email,
                'stage': p.get('stage', ''),
                'source': p.get('source', ''),
                'created': p.get('created', '')[:10],
                'tags': p.get('tags', []),
            })

        offset += len(people)
        if len(people) < 100:
            break

    logger.info(f"Found {len(contacts)} contacts with email but no phone (excluding 2)")
    return contacts


def validate_email_ipqs(email: str, api_key: str) -> dict:
    """Validate a single email via IPQS Email Validation API."""
    encoded_email = urllib.parse.quote(email, safe='')
    url = (
        f'https://www.ipqualityscore.com/api/json/email/{api_key}/{encoded_email}'
        f'?timeout=10&abuse_strictness=1'
    )

    req = urllib.request.Request(url, headers={'Accept': 'application/json'})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error(f"IPQS API error for {email}: {e}")
        return {'success': False, 'error': str(e)}


def classify_result(result: dict) -> str:
    """Classify an IPQS result into an actionable category."""
    if not result.get('success'):
        return 'ERROR'

    fraud_score = result.get('fraud_score', 0)

    if result.get('disposable'):
        return 'TRASH'
    if result.get('honeypot') or result.get('spam_trap_score', 'none') == 'high':
        return 'TRASH'
    if not result.get('valid'):
        return 'INVALID'
    if not result.get('dns_valid'):
        return 'INVALID'
    if fraud_score >= 85:
        return 'TRASH'
    if result.get('recent_abuse') or fraud_score >= 75:
        return 'RISKY'
    if result.get('deliverability') == 'low' or result.get('smtp_score', 0) == 0:
        return 'LOW_QUALITY'
    if result.get('catch_all'):
        return 'CATCH_ALL'
    if result.get('deliverability') == 'high' and fraud_score < 50:
        return 'VALID'

    return 'REVIEW'


def format_report(contacts: list[dict], results: list[dict]) -> str:
    """Format validation results as a readable report."""
    lines = []
    lines.append("=" * 90)
    lines.append("FUB CONTACT EMAIL VALIDATION REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Contacts validated: {len(results)}")
    lines.append("=" * 90)
    lines.append("")

    # Summary counts
    categories = {}
    for r in results:
        cat = r['classification']
        categories[cat] = categories.get(cat, 0) + 1

    lines.append("SUMMARY")
    lines.append("-" * 40)
    for cat in ['VALID', 'CATCH_ALL', 'REVIEW', 'LOW_QUALITY', 'RISKY', 'INVALID', 'TRASH', 'ERROR']:
        count = categories.get(cat, 0)
        if count:
            lines.append(f"  {cat:<15} {count:>3}")
    lines.append(f"  {'TOTAL':<15} {len(results):>3}")
    lines.append("")

    # Detailed results grouped by classification
    for cat in ['TRASH', 'INVALID', 'RISKY', 'LOW_QUALITY', 'CATCH_ALL', 'REVIEW', 'VALID']:
        group = [r for r in results if r['classification'] == cat]
        if not group:
            continue

        label_map = {
            'VALID': 'VALID (keep, worth pursuing)',
            'CATCH_ALL': 'CATCH-ALL DOMAIN (keep, lower priority)',
            'REVIEW': 'NEEDS REVIEW (manual check)',
            'LOW_QUALITY': 'LOW QUALITY (unlikely to deliver)',
            'RISKY': 'RISKY (abuse history or high fraud score)',
            'INVALID': 'INVALID (bad email, remove)',
            'TRASH': 'TRASH (disposable/spam trap, remove)',
        }

        lines.append(f"--- {label_map.get(cat, cat)} ({len(group)}) ---")
        lines.append("")

        for r in group:
            lines.append(f"  [{r['fub_id']:>5}] {r['name']:<28} {r['email']}")
            detail_parts = []
            detail_parts.append(f"fraud={r.get('fraud_score', '?')}")
            detail_parts.append(f"deliver={r.get('deliverability', '?')}")
            detail_parts.append(f"smtp={r.get('smtp_score', '?')}")
            if r.get('disposable'):
                detail_parts.append("DISPOSABLE")
            if r.get('honeypot'):
                detail_parts.append("HONEYPOT")
            if r.get('recent_abuse'):
                detail_parts.append("RECENT_ABUSE")
            if r.get('catch_all'):
                detail_parts.append("CATCH_ALL")
            if r.get('leaked'):
                detail_parts.append("LEAKED")
            if r.get('suggested_domain'):
                detail_parts.append(f"typo? -> {r['suggested_domain']}")

            # Phone numbers found
            phones = r.get('associated_phone_numbers', {})
            if phones and phones.get('status') == 'Success':
                phone_list = phones.get('phone_numbers', [])
                if phone_list:
                    detail_parts.append(f"PHONES_FOUND: {', '.join(str(p) for p in phone_list[:3])}")

            lines.append(f"         {' | '.join(detail_parts)}")

            # Associated names
            names = r.get('associated_names', {})
            if names and names.get('status') == 'Success':
                name_list = names.get('names', [])
                if name_list:
                    lines.append(f"         names: {', '.join(name_list[:3])}")

            lines.append("")

    # Action summary
    trash_count = categories.get('TRASH', 0) + categories.get('INVALID', 0)
    keep_count = categories.get('VALID', 0) + categories.get('CATCH_ALL', 0)
    review_count = categories.get('REVIEW', 0) + categories.get('LOW_QUALITY', 0) + categories.get('RISKY', 0)

    lines.append("=" * 90)
    lines.append("RECOMMENDED ACTIONS")
    lines.append(f"  Remove from FUB:  {trash_count} contacts (TRASH + INVALID)")
    lines.append(f"  Keep and nurture: {keep_count} contacts (VALID + CATCH_ALL)")
    lines.append(f"  Manual review:    {review_count} contacts (RISKY + LOW_QUALITY + REVIEW)")
    lines.append("=" * 90)

    return "\n".join(lines)


def save_csv(results: list[dict], filepath: str):
    """Save results to CSV."""
    fields = [
        'fub_id', 'name', 'email', 'stage', 'source', 'created',
        'classification', 'fraud_score', 'deliverability', 'smtp_score',
        'valid', 'disposable', 'catch_all', 'honeypot', 'recent_abuse',
        'leaked', 'dns_valid', 'suggested_domain', 'domain_age_days',
        'phone_numbers_found',
    ]

    with open(filepath, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for r in results:
            row = {k: r.get(k, '') for k in fields}
            # Flatten phone numbers
            phones = r.get('associated_phone_numbers', {})
            if phones and phones.get('status') == 'Success':
                row['phone_numbers_found'] = '; '.join(
                    str(p) for p in phones.get('phone_numbers', [])[:5]
                )
            # Domain age
            domain_age = r.get('domain_age', {})
            if isinstance(domain_age, dict):
                row['domain_age_days'] = domain_age.get('days', '')
            writer.writerow(row)

    logger.info(f"CSV saved to {filepath}")


def main():
    parser = argparse.ArgumentParser(description='Validate FUB no-phone contacts via IPQS')
    parser.add_argument('--dry-run', action='store_true', help='List contacts only, no API calls')
    parser.add_argument('--output', choices=['csv', 'json', 'both'], default='csv',
                        help='Output format (default: csv)')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of contacts to validate')
    args = parser.parse_args()

    ipqs_key = os.getenv('IPQS_API_KEY', '').strip()
    if not ipqs_key and not args.dry_run:
        logger.error("IPQS_API_KEY not set in .env. Add your key and try again.")
        sys.exit(1)

    # Fetch contacts
    contacts = get_fub_no_phone_contacts()

    if not contacts:
        logger.info("No contacts to validate.")
        return

    # Dry run: just list them
    if args.dry_run:
        print(f"\n{len(contacts)} contacts to validate:\n")
        for i, c in enumerate(contacts, 1):
            print(f"{i:3}. [{c['fub_id']:>5}] {c['name']:<28} {c['email']:<40} {c['stage']}")
        return

    # Apply limit
    if args.limit:
        contacts = contacts[:args.limit]
        logger.info(f"Limited to {args.limit} contacts")

    # Validate each email
    results = []
    total = len(contacts)

    for i, contact in enumerate(contacts, 1):
        email = contact['email']
        logger.info(f"[{i}/{total}] Validating {email}...")

        result = validate_email_ipqs(email, ipqs_key)

        # Merge contact info with IPQS result
        merged = {**contact, **result}
        merged['classification'] = classify_result(result)
        results.append(merged)

        # Rate limit
        if i < total:
            time.sleep(REQUEST_DELAY)

    # Print report
    report = format_report(contacts, results)
    print("\n" + report)

    # Save outputs
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    reports_dir = PROJECT_ROOT / 'reports'
    reports_dir.mkdir(exist_ok=True)

    if args.output in ('csv', 'both'):
        csv_path = reports_dir / f'email_validation_{timestamp}.csv'
        save_csv(results, str(csv_path))

    if args.output in ('json', 'both'):
        json_path = reports_dir / f'email_validation_{timestamp}.json'
        with open(json_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"JSON saved to {json_path}")

    # Save report text
    report_path = reports_dir / f'email_validation_{timestamp}.txt'
    with open(report_path, 'w') as f:
        f.write(report)
    logger.info(f"Report saved to {report_path}")


if __name__ == '__main__':
    main()
