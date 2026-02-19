#!/usr/bin/env python3
"""
CSMLS Portal Photo Enrichment

Automates the Carolina Smokies MLS member portal to extract photos
for listings we have MLS numbers for but no photos.

SETUP REQUIRED:
1. Add to .env:
   CSMLS_USERNAME=your_mls_username
   CSMLS_PASSWORD=your_mls_password

2. Update the URLs below after inspecting the portal:
   - CSMLS_LOGIN_URL
   - CSMLS_LISTING_URL_TEMPLATE

Usage:
    # Test with Macon County (14 listings)
    python scripts/enrich_csmls_portal.py --county Macon --dry-run

    # Run on specific MLS numbers
    python scripts/enrich_csmls_portal.py --mls 4323174 4291858

    # Run on all listings needing photos (with limit)
    python scripts/enrich_csmls_portal.py --limit 50

    # Interactive mode - pauses for you to inspect
    python scripts/enrich_csmls_portal.py --interactive --mls 4323174
"""

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

# Add project root for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from playwright.async_api import async_playwright, Page, Browser
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# Paths
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos'

# =============================================================================
# CONFIGURATION - UPDATE THESE AFTER INSPECTING THE PORTAL
# =============================================================================

# CSMLS Portal URLs (PLACEHOLDER - update after logging in manually)
CSMLS_LOGIN_URL = "https://csmls.paragonrels.com/ParagonLS/Login.aspx"  # Example - verify this
CSMLS_SEARCH_URL = "https://csmls.paragonrels.com/ParagonLS/Search.aspx"  # Example - verify this

# URL template for direct listing access (if available)
# Use {mls_number} as placeholder
# Example: "https://csmls.paragonrels.com/ParagonLS/Listing/{mls_number}"
CSMLS_LISTING_URL_TEMPLATE = None  # Set after discovering the URL pattern

# CSS Selectors (PLACEHOLDER - update after inspecting page structure)
SELECTORS = {
    # Login page
    'username_input': 'input[name="username"], input[id*="username"], input[type="text"]',
    'password_input': 'input[name="password"], input[id*="password"], input[type="password"]',
    'login_button': 'button[type="submit"], input[type="submit"], button:has-text("Login")',

    # Search page
    'mls_search_input': 'input[name*="mls"], input[id*="mls"], input[placeholder*="MLS"]',
    'search_button': 'button:has-text("Search"), input[value="Search"]',

    # Listing detail page
    'photo_container': '.photo-gallery, .listing-photos, [class*="photo"], [class*="image"]',
    'photo_images': 'img[src*="photo"], img[src*="image"], .gallery img',
    'listing_price': '.price, [class*="price"], [class*="Price"]',
    'listing_address': '.address, [class*="address"], [class*="Address"]',
}

# Rate limiting
REQUEST_DELAY = 3  # Seconds between requests
MAX_RETRIES = 2

# =============================================================================


def load_env():
    """Load environment variables from .env file."""
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def get_credentials() -> tuple:
    """Get CSMLS credentials from environment."""
    load_env()
    username = os.environ.get('CSMLS_USERNAME')
    password = os.environ.get('CSMLS_PASSWORD')

    if not username or not password:
        raise ValueError(
            "CSMLS credentials not found.\n"
            "Add to .env file:\n"
            "  CSMLS_USERNAME=your_username\n"
            "  CSMLS_PASSWORD=your_password"
        )
    return username, password


def get_listings_needing_photos(
    conn: sqlite3.Connection,
    county: str = None,
    mls_numbers: List[str] = None,
    limit: int = None
) -> List[Dict]:
    """Get listings that have MLS numbers but no photos."""

    conditions = [
        "mls_number IS NOT NULL",
        "mls_number != ''",
        "(primary_photo IS NULL OR primary_photo = '')"
    ]
    params = []

    if county:
        conditions.append("county = ?")
        params.append(county)

    if mls_numbers:
        placeholders = ','.join(['?' for _ in mls_numbers])
        conditions.append(f"mls_number IN ({placeholders})")
        params.extend(mls_numbers)

    query = f"""
        SELECT id, mls_number, address, city, county, list_price, beds, baths
        FROM listings
        WHERE {' AND '.join(conditions)}
        ORDER BY list_price DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


class CSMLSEnricher:
    """Playwright-based CSMLS portal automation."""

    def __init__(self, headless: bool = True, interactive: bool = False):
        self.headless = headless
        self.interactive = interactive
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.logged_in = False

    async def start(self):
        """Start browser."""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            slow_mo=100 if self.interactive else 0
        )
        context = await self.browser.new_context(
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        self.page = await context.new_page()

    async def stop(self):
        """Stop browser."""
        if self.browser:
            await self.browser.close()

    async def login(self, username: str, password: str) -> bool:
        """Login to CSMLS portal."""
        print(f"Navigating to login page: {CSMLS_LOGIN_URL}")

        try:
            await self.page.goto(CSMLS_LOGIN_URL, wait_until='networkidle', timeout=30000)
            await self.page.wait_for_timeout(2000)

            if self.interactive:
                print("\n[INTERACTIVE] Inspect the login page.")
                print("  - Find the username input selector")
                print("  - Find the password input selector")
                print("  - Find the login button selector")
                print("  Press Enter to continue...")
                input()

            # Try to find and fill username
            username_input = await self.page.query_selector(SELECTORS['username_input'])
            if not username_input:
                print("  ERROR: Could not find username input")
                print(f"  Tried selector: {SELECTORS['username_input']}")
                return False

            await username_input.fill(username)
            print("  Filled username")

            # Try to find and fill password
            password_input = await self.page.query_selector(SELECTORS['password_input'])
            if not password_input:
                print("  ERROR: Could not find password input")
                return False

            await password_input.fill(password)
            print("  Filled password")

            # Click login button
            login_button = await self.page.query_selector(SELECTORS['login_button'])
            if not login_button:
                print("  ERROR: Could not find login button")
                return False

            await login_button.click()
            print("  Clicked login button")

            # Wait for navigation
            await self.page.wait_for_timeout(3000)

            # Check if login succeeded (look for logout link or dashboard element)
            current_url = self.page.url
            if 'login' not in current_url.lower() or 'dashboard' in current_url.lower():
                print("  Login appears successful!")
                self.logged_in = True
                return True
            else:
                print(f"  Login may have failed. Current URL: {current_url}")
                return False

        except Exception as e:
            print(f"  Login error: {e}")
            return False

    async def search_listing(self, mls_number: str) -> Optional[str]:
        """
        Search for a listing by MLS number.
        Returns the listing detail page URL if found.
        """
        # If we have a direct URL template, use it
        if CSMLS_LISTING_URL_TEMPLATE:
            url = CSMLS_LISTING_URL_TEMPLATE.format(mls_number=mls_number)
            await self.page.goto(url, wait_until='networkidle', timeout=30000)
            return url

        # Otherwise, use search
        print(f"  Searching for MLS# {mls_number}")

        try:
            await self.page.goto(CSMLS_SEARCH_URL, wait_until='networkidle', timeout=30000)
            await self.page.wait_for_timeout(1000)

            if self.interactive:
                print("\n[INTERACTIVE] Inspect the search page.")
                print("  - Find the MLS number search input")
                print("  - Find the search button")
                print("  Press Enter to continue...")
                input()

            # Find MLS search input
            mls_input = await self.page.query_selector(SELECTORS['mls_search_input'])
            if not mls_input:
                print(f"    Could not find MLS search input")
                return None

            await mls_input.fill(mls_number)

            # Click search
            search_btn = await self.page.query_selector(SELECTORS['search_button'])
            if search_btn:
                await search_btn.click()
            else:
                await self.page.keyboard.press('Enter')

            await self.page.wait_for_timeout(3000)

            return self.page.url

        except Exception as e:
            print(f"    Search error: {e}")
            return None

    async def extract_photos(self) -> List[str]:
        """
        Extract photo URLs from the current listing page.
        Returns list of photo URLs.
        """
        photos = []

        if self.interactive:
            print("\n[INTERACTIVE] Inspect the listing detail page.")
            print("  - Find where photos are displayed")
            print("  - Note the img tag selectors")
            print("  Press Enter to continue...")
            input()

        try:
            # Try to find photo images
            img_elements = await self.page.query_selector_all(SELECTORS['photo_images'])

            for img in img_elements:
                src = await img.get_attribute('src')
                if src and not self._is_placeholder(src):
                    # Make absolute URL if relative
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(self.page.url, src)
                    photos.append(src)

            # Deduplicate while preserving order
            seen = set()
            unique_photos = []
            for p in photos:
                if p not in seen:
                    seen.add(p)
                    unique_photos.append(p)

            return unique_photos

        except Exception as e:
            print(f"    Error extracting photos: {e}")
            return []

    def _is_placeholder(self, url: str) -> bool:
        """Check if URL is a placeholder/default image."""
        placeholders = ['placeholder', 'default', 'no-image', 'noimage', 'blank']
        url_lower = url.lower()
        return any(p in url_lower for p in placeholders)

    async def extract_listing_data(self) -> Dict:
        """Extract additional listing data from the page."""
        data = {}

        try:
            # Price
            price_el = await self.page.query_selector(SELECTORS['listing_price'])
            if price_el:
                price_text = await price_el.text_content()
                data['price'] = price_text.strip() if price_text else None

            # Address
            addr_el = await self.page.query_selector(SELECTORS['listing_address'])
            if addr_el:
                addr_text = await addr_el.text_content()
                data['address'] = addr_text.strip() if addr_text else None

        except Exception as e:
            print(f"    Error extracting listing data: {e}")

        return data


async def enrich_listing(
    enricher: CSMLSEnricher,
    conn: sqlite3.Connection,
    listing: Dict,
    dry_run: bool = False
) -> bool:
    """Enrich a single listing with photos from CSMLS portal."""

    mls_number = listing['mls_number']
    print(f"\nProcessing: MLS# {mls_number} - {listing['address']}, {listing['city']}")

    # Search for the listing
    url = await enricher.search_listing(mls_number)
    if not url:
        print(f"  Could not find listing")
        return False

    # Extract photos
    photos = await enricher.extract_photos()

    if not photos:
        print(f"  No photos found")
        return False

    print(f"  Found {len(photos)} photos")
    for i, p in enumerate(photos[:3]):
        print(f"    {i+1}. {p[:80]}...")
    if len(photos) > 3:
        print(f"    ... and {len(photos) - 3} more")

    if dry_run:
        print(f"  [DRY RUN] Would update database")
        return True

    # Update database
    try:
        primary_photo = photos[0]
        photos_json = json.dumps(photos)
        now = datetime.now().isoformat()

        conn.execute("""
            UPDATE listings SET
                primary_photo = ?,
                photos = ?,
                photo_count = ?,
                photo_source = 'csmls_portal',
                photo_verified_at = ?,
                photo_review_status = 'verified',
                updated_at = ?
            WHERE id = ?
        """, [
            primary_photo,
            photos_json,
            len(photos),
            now,
            now,
            listing['id']
        ])
        conn.commit()
        print(f"  Updated database with {len(photos)} photos")
        return True

    except Exception as e:
        print(f"  Database error: {e}")
        return False


async def main_async(args):
    """Async main function."""

    # Get credentials
    try:
        username, password = get_credentials()
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get listings to process
    listings = get_listings_needing_photos(
        conn,
        county=args.county,
        mls_numbers=args.mls,
        limit=args.limit
    )

    if not listings:
        print("No listings found matching criteria")
        return 0

    print(f"Found {len(listings)} listings to process")

    if args.dry_run:
        print("\n*** DRY RUN - No database changes will be made ***\n")

    # Initialize enricher
    enricher = CSMLSEnricher(
        headless=not args.visible,
        interactive=args.interactive
    )

    stats = {'success': 0, 'failed': 0, 'skipped': 0}

    try:
        await enricher.start()

        # Login
        if not await enricher.login(username, password):
            print("\nLogin failed. Please check:")
            print("  1. Credentials in .env are correct")
            print("  2. CSMLS_LOGIN_URL is correct")
            print("  3. Login selectors match the page")
            print("\nTry running with --interactive to debug")
            return 1

        # Process each listing
        for i, listing in enumerate(listings):
            print(f"\n[{i+1}/{len(listings)}]", end="")

            success = await enrich_listing(enricher, conn, listing, dry_run=args.dry_run)

            if success:
                stats['success'] += 1
            else:
                stats['failed'] += 1

            # Rate limiting
            if i < len(listings) - 1:
                await asyncio.sleep(REQUEST_DELAY)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        await enricher.stop()
        conn.close()

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"  Success:  {stats['success']}")
    print(f"  Failed:   {stats['failed']}")
    print(f"  Total:    {len(listings)}")

    return 0 if stats['failed'] == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Enrich listings with photos from CSMLS portal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test with Macon County listings
    python scripts/enrich_csmls_portal.py --county Macon --dry-run

    # Test with specific MLS numbers
    python scripts/enrich_csmls_portal.py --mls 4323174 4291858 --dry-run

    # Interactive mode to debug selectors
    python scripts/enrich_csmls_portal.py --interactive --mls 4323174 --visible

    # Process 50 listings
    python scripts/enrich_csmls_portal.py --limit 50
        """
    )

    parser.add_argument('--county', type=str, help='Filter by county')
    parser.add_argument('--mls', nargs='+', help='Specific MLS numbers to process')
    parser.add_argument('--limit', type=int, help='Maximum listings to process')
    parser.add_argument('--dry-run', action='store_true', help='Preview without database changes')
    parser.add_argument('--visible', action='store_true', help='Show browser window')
    parser.add_argument('--interactive', action='store_true',
                        help='Pause at each step for manual inspection')

    args = parser.parse_args()

    # Run async main
    return asyncio.run(main_async(args))


if __name__ == '__main__':
    sys.exit(main())
