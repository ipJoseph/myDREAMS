#!/usr/bin/env python3
"""
Redfin Automated Search + Download

Uses Playwright to:
1. Navigate to a Redfin search URL
2. Download the CSV export
3. Run the CSV importer
4. Optionally run the page scraper

Usage:
    # Download from a search URL
    python redfin_auto_download.py "https://www.redfin.com/county/2855/NC/Macon-County"

    # Download with price filter
    python redfin_auto_download.py "https://www.redfin.com/county/2855/NC/Macon-County/filter/min-price=500k,max-price=1M"

    # Download multiple counties
    python redfin_auto_download.py --counties "Macon,Jackson,Swain"

    # Use separate database (not DREAMS main)
    python redfin_auto_download.py --db /path/to/redfin_imports.db "https://..."
"""

import argparse
import asyncio
import logging
import os
import sys
import tempfile
import shutil
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright, Download

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Redfin credentials from environment
REDFIN_EMAIL = os.getenv('REDFIN_EMAIL')
REDFIN_PASSWORD = os.getenv('REDFIN_PASSWORD')

# Cookie storage for persistent login
COOKIE_FILE = PROJECT_ROOT / 'data' / '.redfin_cookies.json'

# Default database - separate from main DREAMS to avoid disruption
DEFAULT_DB = str(PROJECT_ROOT / 'data' / 'redfin_imports.db')

# NC County codes for Redfin URLs (verified from redfin.com)
NC_COUNTY_CODES = {
    # Primary WNC coverage (user's 11 counties)
    'cherokee': 2026,
    'clay': 2028,
    'graham': 2044,
    'macon': 2063,
    'swain': 2093,
    'jackson': 2056,
    'haywood': 2050,
    'transylvania': 2094,
    'madison': 2064,
    'buncombe': 2017,
    'henderson': 2051,
    # Additional WNC counties (codes need verification)
    # 'polk': ???,
    # 'yancey': ???,
    # 'mitchell': ???,
    # 'avery': ???,
    # 'watauga': ???,
    # 'ashe': ???,
    # 'alleghany': ???,
}


class RedfinAutoDownloader:
    """Automated Redfin search and CSV download."""

    def __init__(self, db_path: str = DEFAULT_DB, download_dir: str = None, headless: bool = True):
        self.db_path = db_path
        self.download_dir = download_dir or tempfile.mkdtemp(prefix='redfin_')
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None  # Persistent context for cookies
        self.downloaded_files = []
        self.logged_in = False

    async def start(self):
        """Start the browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled'],
            downloads_path=self.download_dir
        )

        # Create persistent context
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            accept_downloads=True
        )

        # Load saved cookies if available
        await self._load_cookies()

        logger.info(f"Browser started (downloads to: {self.download_dir})")

    async def _save_cookies(self):
        """Save cookies to file for persistent login."""
        if self.context:
            cookies = await self.context.cookies()
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(COOKIE_FILE, 'w') as f:
                json.dump(cookies, f)
            logger.info(f"Cookies saved to {COOKIE_FILE}")

    async def _load_cookies(self):
        """Load cookies from file if available."""
        if COOKIE_FILE.exists():
            try:
                with open(COOKIE_FILE, 'r') as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
                logger.info("Loaded saved cookies")
                self.logged_in = True
            except Exception as e:
                logger.warning(f"Could not load cookies: {e}")

    async def _handle_login_modal(self, page) -> bool:
        """Handle Redfin login modal if it appears. Returns True if login successful."""
        try:
            # Check if login modal is visible
            modal = await page.query_selector('div[data-rf-test-id="modal"]')
            if not modal:
                # Also check for the "Unlock" text
                unlock_text = await page.query_selector('text="Unlock the full experience"')
                if not unlock_text:
                    return True  # No modal, we're good

            logger.info("Login modal detected")

            # In headed mode, allow manual login (Google OAuth, etc.)
            if not self.headless:
                logger.info("=" * 50)
                logger.info("MANUAL LOGIN REQUIRED")
                logger.info("Please login in the browser window (Google, email, etc.)")
                logger.info("Waiting up to 2 minutes for login...")
                logger.info("=" * 50)

                # Wait for user to login manually (up to 2 minutes)
                for i in range(24):  # 24 * 5 = 120 seconds
                    await page.wait_for_timeout(5000)
                    # Check if modal is gone
                    modal = await page.query_selector('text="Unlock the full experience"')
                    if not modal:
                        logger.info("Login successful!")
                        await self._save_cookies()
                        self.logged_in = True
                        return True
                    if i % 4 == 0:  # Every 20 seconds
                        logger.info(f"Still waiting for login... ({(i+1)*5}s)")

                logger.error("Login timeout - modal still present")
                return False

            # Headless mode with credentials
            if not REDFIN_EMAIL or not REDFIN_PASSWORD:
                logger.error("Login required but REDFIN_EMAIL and REDFIN_PASSWORD not set")
                logger.info("Options:")
                logger.info("  1. Run with --headed flag and login manually (saves cookies for next time)")
                logger.info("  2. Set: export REDFIN_EMAIL='your@email.com' REDFIN_PASSWORD='yourpass'")
                return False

            # Click "Continue with email" button
            email_btn = await page.query_selector('button:has-text("Continue with email")')
            if email_btn:
                await email_btn.click()
                await page.wait_for_timeout(1000)

            # Fill email
            email_input = await page.query_selector('input[type="email"], input[name="email"], input[data-rf-test-id="email"]')
            if email_input:
                await email_input.fill(REDFIN_EMAIL)
                logger.info(f"Filled email: {REDFIN_EMAIL}")

            # Look for "Continue" or "Next" button after email
            continue_btn = await page.query_selector('button:has-text("Continue"), button:has-text("Next")')
            if continue_btn:
                await continue_btn.click()
                await page.wait_for_timeout(1500)

            # Fill password
            password_input = await page.query_selector('input[type="password"]')
            if password_input:
                await password_input.fill(REDFIN_PASSWORD)
                logger.info("Filled password")

            # Click sign in / login button
            signin_btn = await page.query_selector('button:has-text("Sign in"), button:has-text("Log in"), button[type="submit"]')
            if signin_btn:
                await signin_btn.click()
                await page.wait_for_timeout(3000)

            # Verify login succeeded (modal should be gone)
            await page.wait_for_timeout(2000)
            modal_check = await page.query_selector('text="Unlock the full experience"')
            if not modal_check:
                logger.info("Login successful!")
                await self._save_cookies()
                self.logged_in = True
                return True
            else:
                logger.error("Login failed - modal still present")
                return False

        except Exception as e:
            logger.error(f"Error handling login: {e}")
            return False

    async def _dismiss_modal(self, page):
        """Try to dismiss any modal by clicking outside or X button."""
        try:
            # Try clicking X/close button
            close_btns = ['button[aria-label="Close"]', 'button.close', '[data-rf-test-id="close"]', 'svg[data-rf-test-id="close"]']
            for selector in close_btns:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(500)
                    return

            # Try pressing Escape
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(500)
        except:
            pass

    async def stop(self):
        """Stop the browser."""
        # Save cookies before closing
        if self.context and self.logged_in:
            await self._save_cookies()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser stopped")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
        return False

    def _build_county_url(self, county: str, filters: dict = None) -> str:
        """Build a Redfin search URL for a county."""
        county_lower = county.lower().replace(' county', '').replace('-', '').strip()
        code = NC_COUNTY_CODES.get(county_lower)

        if not code:
            raise ValueError(f"Unknown county: {county}. Known: {list(NC_COUNTY_CODES.keys())}")

        county_name = county.replace(' ', '-').title()
        url = f"https://www.redfin.com/county/{code}/NC/{county_name}-County"

        if filters:
            filter_parts = []
            for key, value in filters.items():
                filter_parts.append(f"{key}={value}")
            url += "/filter/" + ",".join(filter_parts)

        return url

    async def download_search(self, url: str) -> Optional[str]:
        """
        Navigate to a Redfin search URL and download the CSV.
        Returns the path to the downloaded file.
        """
        logger.info(f"Downloading from: {url}")

        # Use persistent context (has cookies)
        page = await self.context.new_page()

        try:
            # Navigate to search page
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(3000)  # Let page fully render

            # Check for and handle login modal
            login_result = await self._handle_login_modal(page)
            if not login_result:
                logger.error("Login required but failed")
                await page.screenshot(path=str(Path(self.download_dir) / 'debug_login_failed.png'))
                return None

            # After login, refresh if needed
            if self.logged_in:
                await page.wait_for_timeout(1000)
                # Dismiss any remaining modals
                await self._dismiss_modal(page)

            # Look for the download button/link
            # Redfin has a "Download All" link in the results header
            download_selectors = [
                'a[href*="download-and-save"]',
                'a:has-text("Download All")',
                'button:has-text("Download")',
                '#download-and-save',
                'a.download-link',
            ]

            download_link = None
            for selector in download_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        download_link = element
                        logger.info(f"Found download link with selector: {selector}")
                        break
                except:
                    continue

            if not download_link:
                # Try to find by text content
                links = await page.query_selector_all('a')
                for link in links:
                    try:
                        text = await link.inner_text()
                        if 'download' in text.lower():
                            download_link = link
                            logger.info(f"Found download link by text: {text}")
                            break
                    except:
                        continue

            if not download_link:
                logger.error("Could not find download link on page")
                # Save screenshot for debugging
                await page.screenshot(path=str(Path(self.download_dir) / 'debug_no_download.png'))
                return None

            # Click download link - may trigger login modal
            await download_link.click()
            await page.wait_for_timeout(1500)

            # Handle potential login modal that appears on click
            modal_appeared = await page.query_selector('text="Unlock the full experience"')
            if modal_appeared:
                logger.info("Login modal appeared on download click")
                login_ok = await self._handle_login_modal(page)
                if not login_ok:
                    return None

                # Page may have reloaded after login - wait and re-find download link
                await page.wait_for_timeout(2000)

                # Re-find the download link after login
                download_link = None
                for selector in download_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element and await element.is_visible():
                            download_link = element
                            logger.info(f"Re-found download link with selector: {selector}")
                            break
                    except:
                        continue

                if not download_link:
                    logger.error("Could not re-find download link after login")
                    await page.screenshot(path=str(Path(self.download_dir) / 'debug_no_download_after_login.png'))
                    return None

            # Now click and wait for download
            async with page.expect_download(timeout=60000) as download_info:
                await download_link.click()

            download = await download_info.value

            # Save the file
            timestamp = datetime.now().strftime('%y%m%d_%H%M')
            filename = f"redfin_{timestamp}.csv"
            save_path = str(Path(self.download_dir) / filename)
            await download.save_as(save_path)

            logger.info(f"Downloaded: {save_path}")
            self.downloaded_files.append(save_path)

            # Save cookies after successful download
            await self._save_cookies()

            return save_path

        except Exception as e:
            logger.error(f"Error downloading: {e}")
            await page.screenshot(path=str(Path(self.download_dir) / 'debug_error.png'))
            return None
        finally:
            await page.close()

    async def download_counties(self, counties: List[str], filters: dict = None) -> List[str]:
        """Download CSVs for multiple counties."""
        downloaded = []

        for county in counties:
            try:
                url = self._build_county_url(county, filters)
                csv_path = await self.download_search(url)
                if csv_path:
                    downloaded.append(csv_path)
                # Rate limiting
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error downloading {county}: {e}")

        return downloaded

    def run_importer(self, csv_files: List[str]) -> dict:
        """Run the CSV importer on downloaded files."""
        from redfin_csv_importer import RedfinCSVImporter

        importer = RedfinCSVImporter(db_path=self.db_path)
        stats = importer.import_multiple(csv_files)
        return stats

    def init_database(self):
        """Initialize the separate Redfin imports database."""
        import sqlite3

        logger.info(f"Initializing database: {self.db_path}")

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create properties table matching DREAMS schema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS properties (
                id TEXT PRIMARY KEY,
                mls_number TEXT,
                original_mls_number TEXT,
                parcel_id TEXT,
                address TEXT,
                city TEXT,
                state TEXT DEFAULT 'NC',
                zip TEXT,
                county TEXT,
                price INTEGER,
                beds INTEGER,
                baths REAL,
                sqft INTEGER,
                acreage REAL,
                year_built INTEGER,
                property_type TEXT,
                subdivision TEXT,
                days_on_market INTEGER,
                status TEXT,
                hoa_fee INTEGER,
                mls_source TEXT,
                redfin_url TEXT,
                latitude REAL,
                longitude REAL,
                listing_agent_name TEXT,
                listing_agent_phone TEXT,
                listing_agent_email TEXT,
                listing_brokerage TEXT,
                page_views INTEGER,
                favorites_count INTEGER,
                primary_photo TEXT,
                source TEXT,
                created_at TEXT,
                updated_at TEXT,
                sync_status TEXT DEFAULT 'pending'
            )
        ''')

        # Create scrape queue table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS redfin_scrape_queue (
                id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL,
                url TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                scraped_at TEXT,
                error TEXT
            )
        ''')

        # Create download log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS download_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                csv_path TEXT,
                properties_imported INTEGER,
                properties_updated INTEGER,
                downloaded_at TEXT,
                imported_at TEXT
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("Database initialized")


async def main():
    parser = argparse.ArgumentParser(description='Automated Redfin search and CSV download')
    parser.add_argument('url', nargs='?', help='Redfin search URL to download')
    parser.add_argument('--counties', help='Comma-separated list of NC counties')
    parser.add_argument('--db', default=DEFAULT_DB, help='Database path (default: separate from DREAMS)')
    parser.add_argument('--download-dir', help='Directory for CSV downloads')
    parser.add_argument('--headed', action='store_true', help='Run browser in headed mode')
    parser.add_argument('--no-import', action='store_true', help='Download only, do not import')
    parser.add_argument('--init-db', action='store_true', help='Initialize database and exit')
    parser.add_argument('--min-price', help='Minimum price filter (e.g., 500k)')
    parser.add_argument('--max-price', help='Maximum price filter (e.g., 1M)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Build filters
    filters = {}
    if args.min_price:
        filters['min-price'] = args.min_price
    if args.max_price:
        filters['max-price'] = args.max_price

    async with RedfinAutoDownloader(
        db_path=args.db,
        download_dir=args.download_dir,
        headless=not args.headed
    ) as downloader:

        # Initialize database
        if args.init_db or not os.path.exists(args.db):
            downloader.init_database()
            if args.init_db:
                print(f"Database initialized: {args.db}")
                return

        downloaded_files = []

        if args.counties:
            # Download multiple counties
            counties = [c.strip() for c in args.counties.split(',')]
            downloaded_files = await downloader.download_counties(counties, filters)
        elif args.url:
            # Download single URL
            csv_path = await downloader.download_search(args.url)
            if csv_path:
                downloaded_files = [csv_path]
        else:
            parser.print_help()
            return

        if not downloaded_files:
            print("No files downloaded")
            return

        print(f"\nDownloaded {len(downloaded_files)} CSV file(s):")
        for f in downloaded_files:
            print(f"  - {f}")

        if not args.no_import:
            print("\nImporting to database...")
            stats = downloader.run_importer(downloaded_files)

            print("\n" + "=" * 50)
            print("IMPORT SUMMARY")
            print("=" * 50)
            print(f"Database:        {args.db}")
            print(f"Files imported:  {len(downloaded_files)}")
            print(f"Rows processed:  {stats['rows_processed']}")
            print(f"Rows imported:   {stats['rows_imported']}")
            print(f"Rows updated:    {stats['rows_updated']}")
            print(f"MLS merged:      {stats['mls_merged']}")
            print(f"Errors:          {stats['errors']}")
            print("=" * 50)


if __name__ == '__main__':
    asyncio.run(main())
