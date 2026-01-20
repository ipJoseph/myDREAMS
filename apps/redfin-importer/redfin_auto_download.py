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

# Default database - separate from main DREAMS to avoid disruption
DEFAULT_DB = str(PROJECT_ROOT / 'data' / 'redfin_imports.db')

# NC County codes for Redfin URLs
NC_COUNTY_CODES = {
    'macon': 2855,
    'jackson': 2847,
    'swain': 2930,
    'cherokee': 2790,
    'graham': 2827,
    'clay': 2793,
    'haywood': 2836,
    'buncombe': 2779,
    'henderson': 2839,
    'transylvania': 2934,
    'polk': 2896,
    'madison': 2864,
    'yancey': 2952,
    'mitchell': 2876,
    'avery': 2768,
    'watauga': 2944,
    'ashe': 2766,
    'alleghany': 2761,
}


class RedfinAutoDownloader:
    """Automated Redfin search and CSV download."""

    def __init__(self, db_path: str = DEFAULT_DB, download_dir: str = None, headless: bool = True):
        self.db_path = db_path
        self.download_dir = download_dir or tempfile.mkdtemp(prefix='redfin_')
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.downloaded_files = []

    async def start(self):
        """Start the browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled'],
            downloads_path=self.download_dir
        )
        logger.info(f"Browser started (downloads to: {self.download_dir})")

    async def stop(self):
        """Stop the browser."""
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

        context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            accept_downloads=True
        )
        page = await context.new_page()

        try:
            # Navigate to search page
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(3000)  # Let page fully render

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
                    text = await link.inner_text()
                    if 'download' in text.lower():
                        download_link = link
                        logger.info(f"Found download link by text: {text}")
                        break

            if not download_link:
                logger.error("Could not find download link on page")
                # Save screenshot for debugging
                await page.screenshot(path=str(Path(self.download_dir) / 'debug_no_download.png'))
                return None

            # Click and wait for download
            async with page.expect_download(timeout=30000) as download_info:
                await download_link.click()

            download = await download_info.value

            # Save the file
            timestamp = datetime.now().strftime('%y%m%d_%H%M')
            filename = f"redfin_{timestamp}.csv"
            save_path = str(Path(self.download_dir) / filename)
            await download.save_as(save_path)

            logger.info(f"Downloaded: {save_path}")
            self.downloaded_files.append(save_path)
            return save_path

        except Exception as e:
            logger.error(f"Error downloading: {e}")
            await page.screenshot(path=str(Path(self.download_dir) / 'debug_error.png'))
            return None
        finally:
            await context.close()

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
