#!/usr/bin/env python3
"""
Photo Enrichment Script

Enriches listings with photos from Redfin by:
1. Searching Redfin for the property address
2. Scraping photos from the property page
3. Updating the listings table

Usage:
    python scripts/enrich_photos.py [--limit N] [--headless]

Requires: playwright
"""

import argparse
import asyncio
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'


class PhotoEnricher:
    """Enriches listings with photos from Redfin."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.stats = {
            'processed': 0,
            'enriched': 0,
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

    async def search_redfin(self, address: str, city: str, state: str, zip_code: str) -> Optional[str]:
        """Search Redfin for a property using the search box."""
        query = f"{address}, {city}, {state}"
        if zip_code:
            query += f" {zip_code}"

        context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            # Go to Redfin homepage
            await page.goto('https://www.redfin.com/', wait_until='domcontentloaded', timeout=20000)
            await page.wait_for_timeout(1000)

            # Find and click the search box
            search_input = await page.query_selector('input[type="search"], input[placeholder*="Address"], #search-box-input, [data-rf-test-id="search-box-input"]')
            if not search_input:
                search_input = await page.query_selector('input[type="text"]')

            if search_input:
                await search_input.click()
                await page.wait_for_timeout(500)

                # Type the address
                await search_input.fill(query)
                await page.wait_for_timeout(1500)  # Wait for autocomplete

                # Look for autocomplete suggestion with our state
                state_lower = state.lower()
                suggestions = await page.query_selector_all('[class*="suggestion"], [class*="SearchInputSuggestion"], [role="option"]')

                for suggestion in suggestions:
                    text = await suggestion.text_content()
                    if text and state_lower in text.lower():
                        await suggestion.click()
                        await page.wait_for_timeout(2000)
                        break
                else:
                    # No matching suggestion, try pressing Enter
                    await page.keyboard.press('Enter')
                    await page.wait_for_timeout(2000)

            # Check current URL
            current_url = page.url
            state_lower = state.lower()

            if '/home/' in current_url and f'/{state_lower}/' in current_url.lower():
                await context.close()
                return current_url

            # Not found
            await context.close()
            return None

        except Exception as e:
            print(f"    Search error: {e}")
            await context.close()
            return None

    async def scrape_photos(self, url: str) -> Dict:
        """Scrape photos and additional data from a Redfin property page."""
        context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=20000)
            await page.wait_for_timeout(2000)

            html = await page.content()

            data = {
                'redfin_url': url,
                'primary_photo': None,
                'photos': []
            }

            # Extract all photo URLs from page
            photo_patterns = [
                r'"url":"(https://ssl\.cdn-redfin\.com/photo/[^"]+)"',
                r'src="(https://ssl\.cdn-redfin\.com/photo/[^"]+)"',
                r'"photoUrl":"(https://[^"]+\.jpg)"',
            ]

            photos = set()
            for pattern in photo_patterns:
                for match in re.finditer(pattern, html):
                    photo_url = match.group(1)
                    # Filter: must be a photo URL, not thumbnail, prefer genMid size
                    if ('cdn-redfin.com/photo/' in photo_url and
                        'thumb' not in photo_url.lower() and
                        '.jpg' in photo_url.lower()):
                        photos.add(photo_url)

            data['photos'] = list(photos)[:20]  # Limit to 20 photos

            # Primary photo: prefer first real property photo over og:image
            if data['photos']:
                data['primary_photo'] = data['photos'][0]
            else:
                # Fallback to og:image if no photos found
                og_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+\.jpg)"', html)
                if og_match and 'cdn-redfin.com/photo/' in og_match.group(1):
                    data['primary_photo'] = og_match.group(1)

            # Extract Redfin ID from URL
            redfin_id_match = re.search(r'/home/(\d+)', url)
            if redfin_id_match:
                data['redfin_id'] = redfin_id_match.group(1)

            await context.close()
            return data

        except Exception as e:
            print(f"    Scrape error: {e}")
            await context.close()
            return {}

    async def enrich_listing(self, listing: Dict) -> bool:
        """Enrich a single listing with photos."""
        listing_id = listing['id']
        address = listing['address']
        city = listing['city']
        state = listing.get('state', 'NC')
        zip_code = listing.get('zip', '')

        print(f"  Processing: {address}, {city}")

        # Search for the property on Redfin
        redfin_url = await self.search_redfin(address, city, state, zip_code)

        if not redfin_url:
            print(f"    Not found on Redfin")
            self.stats['not_found'] += 1
            return False

        # Scrape photos from the page
        data = await self.scrape_photos(redfin_url)

        if not data.get('primary_photo'):
            print(f"    No photos found")
            self.stats['not_found'] += 1
            return False

        # Update the listing
        conn = sqlite3.connect(DB_PATH)
        try:
            photos_json = json.dumps(data.get('photos', [])) if data.get('photos') else None

            conn.execute("""
                UPDATE listings SET
                    redfin_url = ?,
                    redfin_id = ?,
                    primary_photo = ?,
                    photos = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                data.get('redfin_url'),
                data.get('redfin_id'),
                data.get('primary_photo'),
                photos_json,
                datetime.now().isoformat(),
                listing_id
            ))
            conn.commit()

            photo_count = len(data.get('photos', []))
            print(f"    Enriched: {photo_count} photos")
            self.stats['enriched'] += 1
            return True

        finally:
            conn.close()


async def main():
    parser = argparse.ArgumentParser(description='Enrich listings with photos from Redfin')
    parser.add_argument('--limit', type=int, default=50, help='Max listings to process (default: 50)')
    parser.add_argument('--headless', action='store_true', default=True, help='Run browser headless')
    parser.add_argument('--visible', action='store_true', help='Show browser window')
    parser.add_argument('--county', type=str, help='Filter by county')
    parser.add_argument('--status', type=str, default='ACTIVE', help='Filter by MLS status (default: ACTIVE)')

    args = parser.parse_args()

    headless = not args.visible

    print("=" * 60)
    print("PHOTO ENRICHMENT")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Mode: {'Headless' if headless else 'Visible'}")
    print(f"Limit: {args.limit}")
    print()

    # Get listings needing photos
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT l.id, l.status, p.address, p.city, p.state, p.zip, p.county
        FROM listings l
        JOIN parcels p ON l.parcel_id = p.id
        WHERE l.primary_photo IS NULL
        AND p.address IS NOT NULL
        AND p.address != ''
    """
    params = []

    if args.status:
        query += " AND l.status = ?"
        params.append(args.status)

    if args.county:
        query += " AND p.county = ?"
        params.append(args.county)

    query += f" LIMIT {args.limit}"

    cursor = conn.execute(query, params)
    listings = [dict(row) for row in cursor.fetchall()]
    conn.close()

    print(f"Listings to enrich: {len(listings)}")

    if not listings:
        print("No listings need photo enrichment.")
        return

    async with PhotoEnricher(headless=headless) as enricher:
        for i, listing in enumerate(listings):
            enricher.stats['processed'] += 1

            try:
                await enricher.enrich_listing(listing)
            except Exception as e:
                print(f"    Error: {e}")
                enricher.stats['errors'] += 1

            # Small delay between requests
            if i < len(listings) - 1:
                await asyncio.sleep(2)

            # Progress update
            if (i + 1) % 10 == 0:
                print(f"\nProgress: {i + 1}/{len(listings)}")
                print(f"  Enriched: {enricher.stats['enriched']}, Not found: {enricher.stats['not_found']}, Errors: {enricher.stats['errors']}")
                print()

    print()
    print("=" * 60)
    print("ENRICHMENT COMPLETE")
    print("=" * 60)
    print(f"Processed: {enricher.stats['processed']}")
    print(f"Enriched: {enricher.stats['enriched']}")
    print(f"Not found: {enricher.stats['not_found']}")
    print(f"Errors: {enricher.stats['errors']}")


if __name__ == '__main__':
    asyncio.run(main())
