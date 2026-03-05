#!/usr/bin/env python3
"""
Smart Collections: Pattern Detection Engine

Analyzes contact browsing activity (property views, favorites, shares)
to detect clusters and auto-generate draft collections for agent review.

Usage:
    python3 -m apps.automation.smart_collections --detect
    python3 -m apps.automation.smart_collections --detect --contact-id 5894
    python3 -m apps.automation.smart_collections --dry-run
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

# Minimum thresholds for pattern detection
MIN_VIEWS_FOR_PATTERN = 5       # Need at least 5 property views in a cluster
MIN_CONFIDENCE = 40             # Minimum confidence score (0-100)
PRICE_BUCKET_SIZE = 100_000     # Group properties into $100K price bands


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def detect_browsing_patterns(contact_id: str, days: int = 14) -> list[dict]:
    """
    Analyze contact_events + user_favorites to detect browsing clusters.

    Returns list of patterns:
    [{
        'contact_id': str,
        'cities': [str],
        'counties': [str],
        'price_range': (min, max),
        'beds_range': (min, max),
        'property_count': int,
        'confidence': int,    # 0-100
        'listing_ids': [str],
        'criteria': dict,     # JSON-serializable search criteria
    }]
    """
    conn = get_db()
    cutoff = (datetime.now(tz=None) - timedelta(days=days)).isoformat()

    # Get property views and favorites from contact_events
    # Join to listings via mls_number to get property attributes
    events = conn.execute('''
        SELECT ce.event_type, ce.property_mls, ce.property_price,
               l.id as listing_id, l.city, l.county, l.list_price,
               l.beds, l.baths, l.property_type, l.status
        FROM contact_events ce
        LEFT JOIN listings l ON l.mls_number = ce.property_mls
        WHERE ce.contact_id = ?
          AND ce.occurred_at >= ?
          AND ce.event_type IN ('property_view', 'property_favorite', 'property_share')
        ORDER BY ce.occurred_at DESC
    ''', (contact_id, cutoff)).fetchall()

    if not events:
        conn.close()
        return []

    # Also check user_favorites if there's a linked user
    user_row = conn.execute('''
        SELECT u.id FROM users u
        JOIN leads l ON l.email = u.email
        WHERE l.id = ? OR l.fub_id = ?
        LIMIT 1
    ''', (contact_id, contact_id)).fetchone()

    user_favorites = []
    if user_row:
        user_favorites = conn.execute('''
            SELECT uf.listing_id, l.city, l.county, l.list_price,
                   l.beds, l.baths, l.property_type, l.status
            FROM user_favorites uf
            JOIN listings l ON l.id = uf.listing_id
            WHERE uf.user_id = ? AND uf.created_at >= ?
        ''', (user_row['id'], cutoff)).fetchall()

    conn.close()

    # Combine events with listing data into analyzable records
    records = []
    seen_listings = set()

    for ev in events:
        lid = ev['listing_id']
        if not lid or lid in seen_listings:
            continue
        seen_listings.add(lid)
        records.append({
            'listing_id': lid,
            'city': ev['city'],
            'county': ev['county'],
            'price': ev['list_price'] or ev['property_price'] or 0,
            'beds': ev['beds'],
            'baths': ev['baths'],
            'property_type': ev['property_type'],
            'event_type': ev['event_type'],
            'weight': 3 if ev['event_type'] == 'property_favorite' else (
                2 if ev['event_type'] == 'property_share' else 1
            ),
        })

    for fav in user_favorites:
        lid = fav['listing_id']
        if lid in seen_listings:
            continue
        seen_listings.add(lid)
        records.append({
            'listing_id': lid,
            'city': fav['city'],
            'county': fav['county'],
            'price': fav['list_price'] or 0,
            'beds': fav['beds'],
            'baths': fav['baths'],
            'property_type': fav['property_type'],
            'event_type': 'favorite',
            'weight': 3,
        })

    if len(records) < MIN_VIEWS_FOR_PATTERN:
        return []

    # Cluster by geography (city/county) and price band
    clusters = defaultdict(list)
    for rec in records:
        city = (rec['city'] or 'Unknown').strip()
        county = (rec['county'] or 'Unknown').strip()
        price = rec['price'] or 0
        price_band = (price // PRICE_BUCKET_SIZE) * PRICE_BUCKET_SIZE

        # Primary cluster key: city + price band
        key = f"{city}|{price_band}"
        clusters[key].append(rec)

    patterns = []
    for key, cluster_records in clusters.items():
        if len(cluster_records) < MIN_VIEWS_FOR_PATTERN:
            continue

        cities = list(set(r['city'] for r in cluster_records if r['city']))
        counties = list(set(r['county'] for r in cluster_records if r['county']))
        prices = [r['price'] for r in cluster_records if r['price'] and r['price'] > 0]
        beds = [r['beds'] for r in cluster_records if r['beds']]
        listing_ids = [r['listing_id'] for r in cluster_records if r['listing_id']]

        # Calculate confidence based on multiple signals
        confidence = _calculate_confidence(cluster_records)

        if confidence < MIN_CONFIDENCE:
            continue

        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0
        min_beds = min(beds) if beds else None
        max_beds = max(beds) if beds else None

        criteria = {
            'cities': cities,
            'counties': counties,
            'min_price': min_price,
            'max_price': max_price,
        }
        if min_beds is not None:
            criteria['min_beds'] = min_beds
            criteria['max_beds'] = max_beds

        patterns.append({
            'contact_id': contact_id,
            'cities': cities,
            'counties': counties,
            'price_range': (min_price, max_price),
            'beds_range': (min_beds, max_beds) if min_beds else None,
            'property_count': len(listing_ids),
            'confidence': confidence,
            'listing_ids': listing_ids,
            'criteria': criteria,
        })

    # Sort by confidence descending
    patterns.sort(key=lambda p: p['confidence'], reverse=True)
    return patterns


def _calculate_confidence(records: list[dict]) -> int:
    """
    Calculate confidence score (0-100) for a browsing cluster.

    Factors:
    - Number of unique properties viewed (more = higher)
    - Presence of favorites/shares (weighted higher than views)
    - Recency of activity
    - Price consistency (tight range = higher confidence)
    """
    score = 0

    # Volume: more views = more confident
    count = len(records)
    if count >= 10:
        score += 30
    elif count >= 7:
        score += 20
    elif count >= 5:
        score += 10

    # Engagement depth: favorites and shares indicate stronger interest
    weighted_sum = sum(r['weight'] for r in records)
    avg_weight = weighted_sum / count if count else 0
    if avg_weight >= 2.0:
        score += 25
    elif avg_weight >= 1.5:
        score += 15
    elif avg_weight >= 1.2:
        score += 8

    # Price consistency: tight range = strong signal
    prices = [r['price'] for r in records if r['price'] and r['price'] > 0]
    if len(prices) >= 3:
        avg_price = sum(prices) / len(prices)
        if avg_price > 0:
            spread = (max(prices) - min(prices)) / avg_price
            if spread < 0.3:       # Within 30% range
                score += 25
            elif spread < 0.5:
                score += 15
            elif spread < 1.0:
                score += 8

    # Bedroom consistency
    beds = [r['beds'] for r in records if r['beds']]
    if len(beds) >= 3:
        bed_range = max(beds) - min(beds)
        if bed_range <= 1:
            score += 15
        elif bed_range <= 2:
            score += 8

    # Cap at 100
    return min(score, 100)


def create_smart_collection(
    contact_id: str,
    pattern: dict,
    dry_run: bool = False,
) -> str | None:
    """
    Auto-create a collection with status='pending_review', collection_type='smart'.
    Agent must accept before buyer sees it.
    Returns collection ID or None if dry run.
    """
    conn = get_db()

    # Check if there's already a smart collection for this contact with similar criteria
    existing = conn.execute('''
        SELECT id, criteria_json FROM property_packages
        WHERE lead_id = ? AND collection_type = 'smart'
          AND status NOT IN ('archived', 'deleted')
    ''', (contact_id,)).fetchall()

    for ex in existing:
        try:
            ex_criteria = json.loads(ex['criteria_json'] or '{}')
            # Check if cities overlap significantly
            ex_cities = set(ex_criteria.get('cities', []))
            new_cities = set(pattern['criteria'].get('cities', []))
            if ex_cities and new_cities and len(ex_cities & new_cities) / max(len(ex_cities), len(new_cities)) > 0.5:
                logger.info(
                    "Skipping: similar smart collection %s already exists for contact %s",
                    ex['id'], contact_id
                )
                conn.close()
                return None
        except (json.JSONDecodeError, TypeError):
            pass

    # Get lead info for naming
    lead = conn.execute(
        'SELECT first_name, last_name FROM leads WHERE id = ? OR fub_id = ?',
        (contact_id, contact_id)
    ).fetchone()

    # Generate descriptive name
    cities = pattern['cities']
    price_min, price_max = pattern['price_range']
    city_str = cities[0] if cities else 'Unknown Area'
    price_str = f"${price_min // 1000}K-${price_max // 1000}K" if price_min and price_max else ''
    name = f"{city_str} Properties"
    if price_str:
        name += f" ({price_str})"

    collection_id = str(uuid.uuid4())
    now = datetime.now(tz=None).isoformat()

    if dry_run:
        buyer_name = f"{lead['first_name'] or ''} {lead['last_name'] or ''}".strip() if lead else contact_id
        logger.info(
            "DRY RUN: Would create smart collection '%s' for %s "
            "(%d properties, confidence: %d%%)",
            name, buyer_name, pattern['property_count'], pattern['confidence']
        )
        conn.close()
        return None

    # Resolve lead_id (contact_id might be FUB ID)
    lead_id = contact_id
    lead_row = conn.execute(
        'SELECT id FROM leads WHERE id = ? OR fub_id = ?',
        (contact_id, contact_id)
    ).fetchone()
    if lead_row:
        lead_id = lead_row['id']

    conn.execute('''
        INSERT INTO property_packages
        (id, name, lead_id, status, collection_type,
         criteria_json, auto_refresh, created_by, created_at, updated_at)
        VALUES (?, ?, ?, 'pending_review', 'smart', ?, 0, 'system', ?, ?)
    ''', (
        collection_id, name, lead_id,
        json.dumps(pattern['criteria']),
        now, now,
    ))

    # Add properties
    for i, listing_id in enumerate(pattern['listing_ids']):
        conn.execute('''
            INSERT OR IGNORE INTO package_properties
            (id, package_id, listing_id, display_order, added_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), collection_id, listing_id, i + 1, now))

    conn.commit()
    conn.close()

    logger.info(
        "Created smart collection '%s' (id=%s) with %d properties for contact %s",
        name, collection_id, len(pattern['listing_ids']), contact_id
    )
    return collection_id


def detect_all_patterns(days: int = 14, min_events: int = 10, dry_run: bool = False) -> list[dict]:
    """
    Run pattern detection across all active contacts.
    Returns list of created/detected patterns.
    """
    conn = get_db()

    # Find contacts with significant recent activity
    cutoff = (datetime.now(tz=None) - timedelta(days=days)).isoformat()
    active_contacts = conn.execute('''
        SELECT contact_id, COUNT(*) as event_count
        FROM contact_events
        WHERE occurred_at >= ?
          AND event_type IN ('property_view', 'property_favorite', 'property_share')
        GROUP BY contact_id
        HAVING COUNT(*) >= ?
        ORDER BY COUNT(*) DESC
    ''', (cutoff, min_events)).fetchall()

    conn.close()

    results = []
    for contact in active_contacts:
        contact_id = contact['contact_id']
        patterns = detect_browsing_patterns(contact_id, days=days)

        for pattern in patterns:
            cid = create_smart_collection(contact_id, pattern, dry_run=dry_run)
            results.append({
                'contact_id': contact_id,
                'pattern': pattern,
                'collection_id': cid,
            })

    return results


def refresh_auto_collections():
    """
    For collections with auto_refresh=1, re-run criteria query and update listings.
    """
    conn = get_db()

    auto_collections = conn.execute('''
        SELECT id, criteria_json, lead_id
        FROM property_packages
        WHERE auto_refresh = 1
          AND status NOT IN ('archived', 'deleted')
          AND criteria_json IS NOT NULL
    ''').fetchall()

    refreshed = 0
    for coll in auto_collections:
        try:
            criteria = json.loads(coll['criteria_json'])
        except (json.JSONDecodeError, TypeError):
            continue

        # Build query from criteria
        query = 'SELECT id FROM listings WHERE status = ?'
        params: list[Any] = ['Active']

        cities = criteria.get('cities', [])
        if cities:
            placeholders = ','.join('?' * len(cities))
            query += f' AND city IN ({placeholders})'
            params.extend(cities)

        if criteria.get('min_price'):
            query += ' AND list_price >= ?'
            params.append(criteria['min_price'])
        if criteria.get('max_price'):
            query += ' AND list_price <= ?'
            params.append(criteria['max_price'])
        if criteria.get('min_beds'):
            query += ' AND beds >= ?'
            params.append(criteria['min_beds'])

        query += ' ORDER BY list_price DESC LIMIT 20'

        new_listings = conn.execute(query, params).fetchall()
        new_ids = {r['id'] for r in new_listings}

        # Get current listings
        current = conn.execute(
            'SELECT listing_id FROM package_properties WHERE package_id = ?',
            (coll['id'],)
        ).fetchall()
        current_ids = {r['listing_id'] for r in current}

        # Add new listings not already in collection
        now = datetime.now(tz=None).isoformat()
        added = 0
        max_order = conn.execute(
            'SELECT COALESCE(MAX(display_order), 0) FROM package_properties WHERE package_id = ?',
            (coll['id'],)
        ).fetchone()[0]

        for lid in new_ids - current_ids:
            max_order += 1
            conn.execute('''
                INSERT OR IGNORE INTO package_properties
                (id, package_id, listing_id, display_order, added_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (str(uuid.uuid4()), coll['id'], lid, max_order, now))
            added += 1

        if added > 0:
            conn.execute(
                'UPDATE property_packages SET last_refreshed_at = ?, updated_at = ? WHERE id = ?',
                (now, now, coll['id'])
            )
            refreshed += 1
            logger.info("Refreshed collection %s: added %d new listings", coll['id'], added)

    conn.commit()
    conn.close()
    logger.info("Refreshed %d auto-refresh collections", refreshed)
    return refreshed


def main():
    parser = argparse.ArgumentParser(description='Smart Collections: Pattern Detection')
    parser.add_argument('--detect', action='store_true', help='Run pattern detection')
    parser.add_argument('--refresh', action='store_true', help='Refresh auto-refresh collections')
    parser.add_argument('--contact-id', type=str, help='Detect patterns for a specific contact')
    parser.add_argument('--days', type=int, default=14, help='Look-back period in days')
    parser.add_argument('--dry-run', action='store_true', help='Preview without creating collections')
    parser.add_argument('--min-events', type=int, default=10, help='Min events for a contact to be analyzed')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    if args.detect and args.contact_id:
        patterns = detect_browsing_patterns(args.contact_id, days=args.days)
        if not patterns:
            print(f"No patterns detected for contact {args.contact_id}")
            return

        for i, p in enumerate(patterns):
            print(f"\nPattern {i+1}:")
            print(f"  Cities: {', '.join(p['cities'])}")
            if p['counties']:
                print(f"  Counties: {', '.join(p['counties'])}")
            print(f"  Price range: ${p['price_range'][0]:,.0f} - ${p['price_range'][1]:,.0f}")
            if p['beds_range']:
                print(f"  Beds: {p['beds_range'][0]} - {p['beds_range'][1]}")
            print(f"  Properties: {p['property_count']}")
            print(f"  Confidence: {p['confidence']}%")

            if not args.dry_run:
                cid = create_smart_collection(args.contact_id, p)
                if cid:
                    print(f"  Created collection: {cid}")
            else:
                create_smart_collection(args.contact_id, p, dry_run=True)

    elif args.detect:
        results = detect_all_patterns(
            days=args.days,
            min_events=args.min_events,
            dry_run=args.dry_run,
        )
        print(f"\nDetected {len(results)} patterns across all contacts")
        for r in results:
            p = r['pattern']
            print(f"  Contact {r['contact_id']}: {', '.join(p['cities'])} "
                  f"({p['property_count']} props, {p['confidence']}% confidence)"
                  f"{' -> ' + r['collection_id'] if r['collection_id'] else ''}")

    elif args.refresh:
        count = refresh_auto_collections()
        print(f"Refreshed {count} collections")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
