#!/usr/bin/env python3
"""
Targeted gallery download for Zone 1-3 Active/Pending listings.

Downloads full photo galleries ONLY for listings that:
1. Are in Zone 1, 2, or 3
2. Have status Active or Pending
3. Are missing gallery photos (no _02.jpg on disk)

Run: python3 scripts/download-missing-galleries.py [--dry-run] [--source canopy|navica] [--zone 1|2|3]
"""

import argparse
import json
import logging
import os
import sys
import time
import requests
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))

DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
MLSGRID_DIR = PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid'
NAVICA_DIR = PROJECT_ROOT / 'data' / 'photos' / 'navica'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)


def get_missing_listings(source_filter=None, zone_filter=None):
    """Find Zone 1-3 Active/Pending listings missing gallery photos."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    query = '''
        SELECT mls_number, mls_source, zone, address, city
        FROM listings
        WHERE zone IN (1, 2, 3)
          AND status IN ('ACTIVE', 'Active', 'PENDING', 'Pending')
    '''
    params = []
    if zone_filter:
        query += ' AND zone = ?'
        params.append(zone_filter)
    if source_filter:
        query += ' AND mls_source = ?'
        params.append(source_filter)

    query += ' ORDER BY zone, mls_number'
    rows = conn.execute(query, params).fetchall()
    conn.close()

    missing = []
    for r in rows:
        mls = r['mls_number']
        # Check if gallery exists
        has_gallery = False
        for d in [MLSGRID_DIR, NAVICA_DIR]:
            if (d / f'{mls}_02.jpg').exists():
                has_gallery = True
                break
        if not has_gallery:
            missing.append(dict(r))

    return missing


def download_canopy_galleries(listings, dry_run=False):
    """Download galleries from MLS Grid API for CanopyMLS listings."""
    token = os.environ.get('MLSGRID_TOKEN')
    if not token:
        logger.error("MLSGRID_TOKEN not set in .env")
        return

    base_url = 'https://api.mlsgrid.com/v2'
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
    }
    session = requests.Session()
    session.headers.update(headers)

    downloaded = 0
    errors = 0

    for i, listing in enumerate(listings):
        mls = listing['mls_number']
        logger.info(f"[{i+1}/{len(listings)}] {mls} - {listing.get('address', '')} ({listing.get('city', '')})")

        if dry_run:
            continue

        try:
            # Fetch listing with media (with 429 retry/backoff)
            resp = None
            for attempt in range(3):
                resp = session.get(
                    f'{base_url}/Property',
                    params={
                        '$filter': f"ListingId eq '{mls}'",
                        '$expand': 'Media',
                    },
                    timeout=30,
                )
                if resp.status_code == 429:
                    wait = 60 * (attempt + 1)  # 60s, 120s, 180s
                    logger.warning(f"  Rate limited (429). Waiting {wait}s before retry...")
                    time.sleep(wait)
                    continue
                break
            time.sleep(2.0)  # Conservative: 0.5 RPS

            if resp.status_code != 200:
                logger.warning(f"  API error {resp.status_code} for {mls}")
                errors += 1
                continue

            data = resp.json()
            records = data.get('value', [])
            if not records:
                logger.warning(f"  No data returned for {mls}")
                errors += 1
                continue

            media = records[0].get('Media', [])
            if not media:
                logger.info(f"  No photos for {mls}")
                continue

            # Download each photo
            photo_num = 0
            for m in sorted(media, key=lambda x: x.get('Order', 999)):
                url = m.get('MediaURL')
                if not url:
                    continue
                photo_num += 1
                suffix = f'_{photo_num:02d}' if photo_num > 1 else ''
                fname = f'{mls}{suffix}.jpg'
                fpath = MLSGRID_DIR / fname

                if fpath.exists():
                    continue

                try:
                    img_resp = session.get(url, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        fpath.write_bytes(img_resp.content)
                        downloaded += 1
                    time.sleep(0.5)  # Pause between photo downloads
                except Exception as e:
                    logger.warning(f"  Photo download error: {e}")

            logger.info(f"  Downloaded {photo_num} photos for {mls}")

        except Exception as e:
            logger.error(f"  Error processing {mls}: {e}")
            errors += 1

    logger.info(f"Done. Downloaded {downloaded} photos, {errors} errors")


def download_navica_galleries(listings, dry_run=False):
    """Download galleries from Navica API for NavicaMLS listings."""
    token = os.environ.get('NAVICA_BBO_TOKEN') or os.environ.get('NAVICA_IDX_TOKEN')
    if not token:
        logger.error("NAVICA_TOKEN not set in .env")
        return

    base_url = 'https://navapi.navicamls.net/api/v2/nav27'
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
    }
    session = requests.Session()
    session.headers.update(headers)

    downloaded = 0
    errors = 0

    for i, listing in enumerate(listings):
        mls = listing['mls_number']
        logger.info(f"[{i+1}/{len(listings)}] {mls} - {listing.get('address', '')} ({listing.get('city', '')})")

        if dry_run:
            continue

        try:
            resp = session.get(
                f'{base_url}/listing',
                params={'ListingId': mls, 'fields': 'ListingId,Media'},
                timeout=30,
            )
            time.sleep(1.1)

            if resp.status_code != 200:
                logger.warning(f"  API error {resp.status_code} for {mls}")
                errors += 1
                continue

            data = resp.json()
            bundle = data.get('bundle', [])
            if not bundle:
                logger.warning(f"  No data for {mls}")
                errors += 1
                continue

            media = bundle[0].get('Media', [])
            if not media:
                logger.info(f"  No photos for {mls}")
                continue

            photo_num = 0
            for m in sorted(media, key=lambda x: x.get('Order', 999)):
                url = m.get('MediaURL')
                if not url:
                    continue
                photo_num += 1
                suffix = f'_{photo_num:02d}' if photo_num > 1 else ''
                fname = f'{mls}{suffix}.jpg'
                fpath = NAVICA_DIR / fname

                if fpath.exists():
                    continue

                try:
                    img_resp = session.get(url, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        fpath.write_bytes(img_resp.content)
                        downloaded += 1
                    time.sleep(0.3)
                except Exception as e:
                    logger.warning(f"  Photo download error: {e}")

            logger.info(f"  Downloaded {photo_num} photos for {mls}")

        except Exception as e:
            logger.error(f"  Error processing {mls}: {e}")
            errors += 1

    logger.info(f"Done. Downloaded {downloaded} photos, {errors} errors")


def main():
    parser = argparse.ArgumentParser(description='Download missing galleries for Zone 1-3 Active/Pending')
    parser.add_argument('--dry-run', action='store_true', help='List missing without downloading')
    parser.add_argument('--source', choices=['canopy', 'navica', 'mountainlakes'], help='Filter by MLS source')
    parser.add_argument('--zone', type=int, choices=[1, 2, 3], help='Filter by zone')
    args = parser.parse_args()

    source_map = {
        'canopy': 'CanopyMLS',
        'navica': 'NavicaMLS',
        'mountainlakes': 'MountainLakesMLS',
    }
    source_filter = source_map.get(args.source)

    missing = get_missing_listings(source_filter=source_filter, zone_filter=args.zone)

    # Group by source
    by_source = {}
    for m in missing:
        src = m['mls_source'] or 'Unknown'
        by_source.setdefault(src, []).append(m)

    print(f"\nMissing galleries: {len(missing)} total")
    for src, items in sorted(by_source.items()):
        zones = {}
        for item in items:
            zones[item['zone']] = zones.get(item['zone'], 0) + 1
        zone_str = ', '.join(f'Z{z}:{c}' for z, c in sorted(zones.items()))
        print(f"  {src}: {len(items)} ({zone_str})")
    print()

    if args.dry_run:
        print("Dry run complete. No downloads.")
        return

    if not missing:
        print("All galleries present. Nothing to download.")
        return

    # Download by source
    if 'CanopyMLS' in by_source:
        logger.info(f"Downloading {len(by_source['CanopyMLS'])} CanopyMLS galleries...")
        download_canopy_galleries(by_source['CanopyMLS'], dry_run=args.dry_run)

    if 'NavicaMLS' in by_source:
        logger.info(f"Downloading {len(by_source['NavicaMLS'])} NavicaMLS galleries...")
        download_navica_galleries(by_source['NavicaMLS'], dry_run=args.dry_run)

    if 'MountainLakesMLS' in by_source:
        logger.info(f"Downloading {len(by_source['MountainLakesMLS'])} MountainLakesMLS galleries (via MLS Grid API)...")
        download_canopy_galleries(by_source['MountainLakesMLS'], dry_run=args.dry_run)


if __name__ == '__main__':
    main()
