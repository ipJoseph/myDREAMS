#!/usr/bin/env python3
"""
Verified Photo Enrichment Script

Enriches listings with photos from aggregators (Redfin, Zillow, Realtor) using
multi-factor verification to ensure photos match the correct property.

Key Features:
- Multi-factor verification scoring (address, price, beds/baths, coordinates)
- Confidence thresholds for auto-accept, review queue, reject
- Audit trail in listing_photos table
- Priority-based enrichment queue
- Rate limiting to avoid blocking

Usage:
    python scripts/enrich_photos_verified.py [--limit N] [--headless]
    python scripts/enrich_photos_verified.py --process-queue  # Process enrichment queue

Requires: playwright
"""

import argparse
import asyncio
import json
import re
import sqlite3
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'

# Confidence thresholds
CONFIDENCE_AUTO_ACCEPT = 90    # Auto-accept if >= 90%
CONFIDENCE_ACCEPT_NOTE = 70    # Accept with note if 70-89%
CONFIDENCE_REVIEW = 50         # Queue for review if 50-69%
CONFIDENCE_REJECT = 50         # Reject if < 50%

# Rate limits per day
RATE_LIMITS = {
    'redfin': {'daily_limit': 100, 'delay_seconds': 3},
    'zillow': {'daily_limit': 50, 'delay_seconds': 5},
    'realtor': {'daily_limit': 75, 'delay_seconds': 3},
}


def similarity_ratio(a: str, b: str) -> float:
    """Calculate string similarity ratio (0-1)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def normalize_address(address: str) -> str:
    """Normalize address for comparison."""
    if not address:
        return ''

    addr = address.lower().strip()

    # Common abbreviations
    replacements = [
        (r'\bstreet\b', 'st'),
        (r'\broad\b', 'rd'),
        (r'\bdrive\b', 'dr'),
        (r'\blane\b', 'ln'),
        (r'\btrail\b', 'trl'),
        (r'\bcircle\b', 'cir'),
        (r'\bavenue\b', 'ave'),
        (r'\bcourt\b', 'ct'),
        (r'\bplace\b', 'pl'),
        (r'\bhighway\b', 'hwy'),
        (r'\bnorth\b', 'n'),
        (r'\bsouth\b', 's'),
        (r'\beast\b', 'e'),
        (r'\bwest\b', 'w'),
    ]

    for pattern, replacement in replacements:
        addr = re.sub(pattern, replacement, addr)

    # Remove extra whitespace
    addr = ' '.join(addr.split())

    return addr


def calculate_verification_score(listing: Dict, scraped: Dict) -> Tuple[float, Dict]:
    """
    Calculate verification confidence score using multiple factors.

    Returns:
        Tuple of (confidence_score, factor_breakdown)
    """
    factors = {}

    # Factor 1: Address match (30% weight)
    listing_addr = normalize_address(listing.get('address', ''))
    scraped_addr = normalize_address(scraped.get('address', ''))
    addr_similarity = similarity_ratio(listing_addr, scraped_addr) * 100
    factors['address_match'] = round(addr_similarity, 1)

    # Factor 2: Price match (25% weight)
    listing_price = listing.get('list_price') or listing.get('price')
    scraped_price = scraped.get('price')
    if listing_price and scraped_price:
        price_diff_pct = abs(listing_price - scraped_price) / max(listing_price, 1) * 100
        if price_diff_pct <= 5:
            price_score = 100
        elif price_diff_pct <= 10:
            price_score = 80
        elif price_diff_pct <= 20:
            price_score = 50
        else:
            price_score = 0
        factors['price_match'] = round(price_score, 1)
    else:
        factors['price_match'] = 50  # Neutral if can't compare

    # Factor 3: Beds/Baths match (25% weight)
    beds_match = True
    baths_match = True

    if listing.get('beds') and scraped.get('beds'):
        beds_match = listing['beds'] == scraped['beds']
    if listing.get('baths') and scraped.get('baths'):
        # Allow 0.5 bath difference
        baths_match = abs((listing['baths'] or 0) - (scraped['baths'] or 0)) <= 0.5

    if beds_match and baths_match:
        spec_score = 100
    elif beds_match or baths_match:
        spec_score = 50
    else:
        spec_score = 0
    factors['specs_match'] = spec_score

    # Factor 4: Coordinate proximity (20% weight)
    listing_lat = listing.get('latitude')
    listing_lng = listing.get('longitude')
    scraped_lat = scraped.get('latitude')
    scraped_lng = scraped.get('longitude')

    if all([listing_lat, listing_lng, scraped_lat, scraped_lng]):
        # Calculate approximate distance in miles
        lat_diff = abs(listing_lat - scraped_lat) * 69  # ~69 miles per degree lat
        lng_diff = abs(listing_lng - scraped_lng) * 54  # ~54 miles per degree lng at NC latitude
        distance = (lat_diff ** 2 + lng_diff ** 2) ** 0.5

        if distance <= 0.1:
            coord_score = 100
        elif distance <= 0.25:
            coord_score = 80
        elif distance <= 0.5:
            coord_score = 50
        else:
            coord_score = 0
        factors['coords_match'] = round(coord_score, 1)
    else:
        factors['coords_match'] = 50  # Neutral if can't compare

    # Calculate weighted score
    weights = {
        'address_match': 0.30,
        'price_match': 0.25,
        'specs_match': 0.25,
        'coords_match': 0.20,
    }

    total_score = sum(factors[k] * weights[k] for k in weights)
    factors['total'] = round(total_score, 1)

    return total_score, factors


class VerifiedPhotoEnricher:
    """Enriches listings with verified photos from aggregators."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.stats = {
            'processed': 0,
            'auto_accepted': 0,
            'accepted_with_note': 0,
            'queued_review': 0,
            'rejected': 0,
            'not_found': 0,
            'errors': 0
        }

    async def start(self):
        """Start the browser."""
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        print("Browser started")

    async def stop(self):
        """Stop the browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("Browser stopped")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
        return False

    async def search_redfin(self, address: str, city: str, state: str, zip_code: str = None) -> Optional[Dict]:
        """Search Redfin for a property and scrape photos."""
        query = f"{address}, {city}, {state}"
        if zip_code:
            query += f" {zip_code}"

        context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()

        try:
            # Go to Redfin homepage
            await page.goto('https://www.redfin.com/', wait_until='domcontentloaded', timeout=20000)
            await page.wait_for_timeout(1000)

            # Find and use search box
            search_input = await page.query_selector(
                'input[type="search"], input[placeholder*="Address"], '
                '#search-box-input, [data-rf-test-id="search-box-input"]'
            )
            if not search_input:
                search_input = await page.query_selector('input[type="text"]')

            if search_input:
                await search_input.click()
                await page.wait_for_timeout(500)
                await search_input.fill(query)
                await page.wait_for_timeout(1500)

                # Look for autocomplete suggestion
                state_lower = state.lower()
                suggestions = await page.query_selector_all(
                    '[class*="suggestion"], [class*="SearchInputSuggestion"], [role="option"]'
                )

                for suggestion in suggestions:
                    text = await suggestion.text_content()
                    if text and state_lower in text.lower():
                        await suggestion.click()
                        await page.wait_for_timeout(2000)
                        break
                else:
                    await page.keyboard.press('Enter')
                    await page.wait_for_timeout(2000)

            # Check if we landed on a property page
            current_url = page.url
            if '/home/' not in current_url or f'/{state.lower()}/' not in current_url.lower():
                await context.close()
                return None

            # Scrape the property page
            html = await page.content()

            data = {
                'source': 'redfin',
                'url': current_url,
                'address': None,
                'price': None,
                'beds': None,
                'baths': None,
                'latitude': None,
                'longitude': None,
                'photos': [],
                'primary_photo': None,
            }

            # Extract Redfin ID
            redfin_id_match = re.search(r'/home/(\d+)', current_url)
            if redfin_id_match:
                data['redfin_id'] = redfin_id_match.group(1)

            # Extract address from page title
            title_match = re.search(r'<title>([^|]+)', html)
            if title_match:
                data['address'] = title_match.group(1).strip()

            # Extract price
            price_match = re.search(r'"price":(\d+)', html)
            if price_match:
                data['price'] = int(price_match.group(1))

            # Extract beds/baths
            beds_match = re.search(r'"numBedrooms":(\d+)', html)
            if beds_match:
                data['beds'] = int(beds_match.group(1))
            baths_match = re.search(r'"numBathrooms":([\d.]+)', html)
            if baths_match:
                data['baths'] = float(baths_match.group(1))

            # Extract coordinates
            lat_match = re.search(r'"latitude":([\d.-]+)', html)
            lng_match = re.search(r'"longitude":([\d.-]+)', html)
            if lat_match and lng_match:
                data['latitude'] = float(lat_match.group(1))
                data['longitude'] = float(lng_match.group(1))

            # Extract photos
            photo_patterns = [
                r'"url":"(https://ssl\.cdn-redfin\.com/photo/[^"]+)"',
                r'src="(https://ssl\.cdn-redfin\.com/photo/[^"]+)"',
                r'"photoUrl":"(https://[^"]+\.jpg)"',
            ]

            photos = set()
            for pattern in photo_patterns:
                for match in re.finditer(pattern, html):
                    photo_url = match.group(1)
                    if ('cdn-redfin.com/photo/' in photo_url and
                        'thumb' not in photo_url.lower() and
                        '.jpg' in photo_url.lower()):
                        photos.add(photo_url)

            data['photos'] = list(photos)[:20]
            if data['photos']:
                data['primary_photo'] = data['photos'][0]

            await context.close()
            return data

        except Exception as e:
            print(f"    Redfin search error: {e}")
            await context.close()
            return None

    async def enrich_listing(self, listing: Dict) -> Optional[Dict]:
        """
        Enrich a single listing with verified photos.

        Returns enrichment result or None if failed.
        """
        listing_id = listing['id']
        address = listing.get('address', '')
        city = listing.get('city', '')
        state = listing.get('state', 'NC')
        zip_code = listing.get('zip', '')

        print(f"  Processing: {address}, {city}")

        # Try Redfin first
        scraped = await self.search_redfin(address, city, state, zip_code)

        if not scraped:
            print(f"    Not found on Redfin")
            self.stats['not_found'] += 1
            return None

        if not scraped.get('photos'):
            print(f"    No photos found")
            self.stats['not_found'] += 1
            return None

        # Calculate verification score
        confidence, factors = calculate_verification_score(listing, scraped)
        print(f"    Confidence: {confidence:.1f}% ({factors})")

        # Determine action based on confidence
        if confidence >= CONFIDENCE_AUTO_ACCEPT:
            status = 'verified'
            self.stats['auto_accepted'] += 1
            print(f"    AUTO ACCEPTED (confidence >= {CONFIDENCE_AUTO_ACCEPT}%)")
        elif confidence >= CONFIDENCE_ACCEPT_NOTE:
            status = 'verified'
            self.stats['accepted_with_note'] += 1
            print(f"    Accepted with note (confidence {CONFIDENCE_ACCEPT_NOTE}-{CONFIDENCE_AUTO_ACCEPT}%)")
        elif confidence >= CONFIDENCE_REVIEW:
            status = 'pending_review'
            self.stats['queued_review'] += 1
            print(f"    Queued for review (confidence {CONFIDENCE_REVIEW}-{CONFIDENCE_ACCEPT_NOTE}%)")
        else:
            status = 'rejected'
            self.stats['rejected'] += 1
            print(f"    REJECTED (confidence < {CONFIDENCE_REVIEW}%)")

        # Save results
        conn = sqlite3.connect(DB_PATH)
        try:
            now = datetime.now().isoformat()
            photos_json = json.dumps(scraped.get('photos', []))

            # Update listing
            if status in ('verified', 'pending_review'):
                conn.execute("""
                    UPDATE listings SET
                        redfin_url = ?,
                        redfin_id = ?,
                        primary_photo = ?,
                        photos = ?,
                        photo_source = ?,
                        photo_confidence = ?,
                        photo_verified_at = ?,
                        photo_verified_by = 'auto',
                        photo_review_status = ?,
                        photo_count = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    scraped.get('url'),
                    scraped.get('redfin_id'),
                    scraped.get('primary_photo'),
                    photos_json,
                    scraped.get('source', 'redfin'),
                    confidence,
                    now,
                    status,
                    len(scraped.get('photos', [])),
                    now,
                    listing_id
                ))

            # Create audit records for each photo
            for idx, photo_url in enumerate(scraped.get('photos', [])):
                conn.execute("""
                    INSERT OR REPLACE INTO listing_photos (
                        listing_id, photo_url, photo_source, photo_index,
                        confidence_score, verification_factors,
                        verified_at, verified_by, status, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    listing_id,
                    photo_url,
                    scraped.get('source', 'redfin'),
                    idx,
                    confidence,
                    json.dumps(factors),
                    now,
                    'auto',
                    status,
                    now
                ))

            conn.commit()

            return {
                'listing_id': listing_id,
                'source': scraped.get('source'),
                'photo_count': len(scraped.get('photos', [])),
                'confidence': confidence,
                'status': status,
                'factors': factors
            }

        finally:
            conn.close()


def get_enrichment_queue(limit: int = 50) -> List[Dict]:
    """Get listings from the enrichment queue by priority."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # First, try the explicit queue
    cursor = conn.execute("""
        SELECT l.*
        FROM enrichment_queue eq
        JOIN listings l ON eq.listing_id = l.id
        WHERE eq.enrichment_type = 'photos'
        AND eq.status = 'pending'
        ORDER BY eq.priority DESC, eq.queued_at ASC
        LIMIT ?
    """, (limit,))
    queued = [dict(row) for row in cursor.fetchall()]

    if queued:
        conn.close()
        return queued

    # Fallback: get listings without photos
    cursor = conn.execute("""
        SELECT *
        FROM listings
        WHERE (primary_photo IS NULL OR primary_photo = '')
        AND address IS NOT NULL AND address != ''
        AND status IN ('ACTIVE', 'Active', 'active')
        ORDER BY updated_at DESC
        LIMIT ?
    """, (limit,))
    listings = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return listings


def get_listings_for_review() -> List[Dict]:
    """Get listings with pending review status."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT l.*, lp.confidence_score, lp.verification_factors
        FROM listings l
        JOIN listing_photos lp ON l.id = lp.listing_id AND lp.photo_index = 0
        WHERE l.photo_review_status = 'pending_review'
        ORDER BY lp.confidence_score DESC
    """)
    listings = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return listings


async def main():
    parser = argparse.ArgumentParser(description='Enrich listings with verified photos')
    parser.add_argument('--limit', type=int, default=50, help='Max listings to process (default: 50)')
    parser.add_argument('--headless', action='store_true', default=True, help='Run browser headless')
    parser.add_argument('--visible', action='store_true', help='Show browser window')
    parser.add_argument('--county', type=str, help='Filter by county')
    parser.add_argument('--status', type=str, default='ACTIVE', help='Filter by MLS status (default: ACTIVE)')
    parser.add_argument('--process-queue', action='store_true', help='Process enrichment queue')
    parser.add_argument('--show-review', action='store_true', help='Show listings pending review')

    args = parser.parse_args()

    # Show review queue
    if args.show_review:
        listings = get_listings_for_review()
        print(f"\n{len(listings)} listings pending manual review:\n")
        for l in listings:
            print(f"  {l['address']}, {l['city']}")
            print(f"    Confidence: {l['confidence_score']:.1f}%")
            if l.get('verification_factors'):
                factors = json.loads(l['verification_factors'])
                print(f"    Factors: {factors}")
            print()
        return

    headless = not args.visible

    print("=" * 60)
    print("VERIFIED PHOTO ENRICHMENT")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Mode: {'Headless' if headless else 'Visible'}")
    print(f"Limit: {args.limit}")
    print(f"Confidence Thresholds:")
    print(f"  Auto-accept: >= {CONFIDENCE_AUTO_ACCEPT}%")
    print(f"  Accept with note: {CONFIDENCE_ACCEPT_NOTE}-{CONFIDENCE_AUTO_ACCEPT}%")
    print(f"  Queue for review: {CONFIDENCE_REVIEW}-{CONFIDENCE_ACCEPT_NOTE}%")
    print(f"  Reject: < {CONFIDENCE_REVIEW}%")
    print()

    # Get listings to process
    if args.process_queue:
        listings = get_enrichment_queue(args.limit)
        print(f"Processing enrichment queue...")
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        query = """
            SELECT *
            FROM listings
            WHERE (primary_photo IS NULL OR primary_photo = '')
            AND address IS NOT NULL AND address != ''
        """
        params = []

        if args.status:
            query += " AND status = ?"
            params.append(args.status)

        if args.county:
            query += " AND county = ?"
            params.append(args.county)

        query += f" LIMIT {args.limit}"

        cursor = conn.execute(query, params)
        listings = [dict(row) for row in cursor.fetchall()]
        conn.close()

    print(f"Listings to enrich: {len(listings)}")

    if not listings:
        print("No listings need photo enrichment.")
        return

    async with VerifiedPhotoEnricher(headless=headless) as enricher:
        for i, listing in enumerate(listings):
            enricher.stats['processed'] += 1

            try:
                await enricher.enrich_listing(listing)
            except Exception as e:
                print(f"    Error: {e}")
                enricher.stats['errors'] += 1

            # Respect rate limits
            if i < len(listings) - 1:
                await asyncio.sleep(RATE_LIMITS['redfin']['delay_seconds'])

            # Progress update
            if (i + 1) % 10 == 0:
                print(f"\nProgress: {i + 1}/{len(listings)}")
                print(f"  Auto-accepted: {enricher.stats['auto_accepted']}")
                print(f"  Accepted w/note: {enricher.stats['accepted_with_note']}")
                print(f"  Queued review: {enricher.stats['queued_review']}")
                print(f"  Rejected: {enricher.stats['rejected']}")
                print(f"  Not found: {enricher.stats['not_found']}")
                print(f"  Errors: {enricher.stats['errors']}")
                print()

    print()
    print("=" * 60)
    print("ENRICHMENT COMPLETE")
    print("=" * 60)
    print(f"Processed: {enricher.stats['processed']}")
    print(f"Auto-accepted: {enricher.stats['auto_accepted']}")
    print(f"Accepted with note: {enricher.stats['accepted_with_note']}")
    print(f"Queued for review: {enricher.stats['queued_review']}")
    print(f"Rejected: {enricher.stats['rejected']}")
    print(f"Not found: {enricher.stats['not_found']}")
    print(f"Errors: {enricher.stats['errors']}")

    # Show pending reviews count
    review_count = len(get_listings_for_review())
    if review_count > 0:
        print(f"\n{review_count} listings pending manual review.")
        print("Run with --show-review to see them.")


if __name__ == '__main__':
    asyncio.run(main())
