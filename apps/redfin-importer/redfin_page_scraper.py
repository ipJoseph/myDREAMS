#!/usr/bin/env python3
"""
Redfin Page Scraper

Uses Playwright to scrape additional property details from Redfin URLs:
- Agent Name, Company, Phone, Email
- Views and Favorites counts
- Primary photo URL

Processes URLs from the redfin_scrape_queue table.

Usage:
    python redfin_page_scraper.py              # Process all pending
    python redfin_page_scraper.py --limit 10   # Process up to 10
    python redfin_page_scraper.py --url <url>  # Scrape single URL (test)
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))


class RedfinPageScraper:
    """Scrapes additional property data from Redfin property pages."""

    def __init__(self, db_path: str = DB_PATH, headless: bool = True):
        self.db_path = db_path
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.stats = {
            'scraped': 0,
            'errors': 0,
            'skipped': 0,
        }

    def _get_connection(self):
        """Get database connection."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def start(self):
        """Start the browser."""
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        logger.info("Browser started")

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

    async def scrape_url(self, url: str) -> Optional[Dict]:
        """Scrape a single Redfin URL for agent/engagement data."""
        logger.info(f"Scraping: {url}")

        context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)  # Let JS render

            html = await page.content()
            text = await page.inner_text('body')

            data = {
                'agent_name': self._extract_agent_name(html, text),
                'agent_company': self._extract_agent_company(html, text),
                'agent_phone': self._extract_agent_phone(html, text),
                'agent_email': self._extract_agent_email(html, text),
                'page_views': self._extract_views(html, text),
                'favorites_count': self._extract_favorites(html, text),
                'primary_photo': self._extract_photo(html),
            }

            logger.info(f"Extracted: agent={data['agent_name']}, views={data['page_views']}, favorites={data['favorites_count']}")
            return data

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None
        finally:
            await context.close()

    def _extract_agent_name(self, html: str, text: str) -> Optional[str]:
        """Extract listing agent name."""
        patterns = [
            r'Listing Agent[:\s]*([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'"agentName"[:\s]*"([^"]+)"',
            r'Listed by[:\s]*([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'class="agent-name"[^>]*>([^<]+)<',
        ]
        for pattern in patterns:
            match = re.search(pattern, html + text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name) > 3 and ' ' in name:
                    return name
        return None

    def _extract_agent_company(self, html: str, text: str) -> Optional[str]:
        """Extract listing agent's brokerage/company."""
        patterns = [
            r'"brokerageName"[:\s]*"([^"]+)"',
            r'Brokerage[:\s]*([^<\n]+)',
            r'class="agent-brokerage"[^>]*>([^<]+)<',
            r'Listing Provided By[:\s]*([^<\n]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html + text, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                if len(company) > 2:
                    return company
        return None

    def _extract_agent_phone(self, html: str, text: str) -> Optional[str]:
        """Extract listing agent phone number."""
        # Look for phone patterns near "agent" or "listing"
        phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'

        # Try to find phone in agent context
        agent_section = re.search(r'(listing\s*agent|listed\s*by)[^<]{0,500}', html + text, re.IGNORECASE)
        if agent_section:
            phone_match = re.search(phone_pattern, agent_section.group(0))
            if phone_match:
                return self._format_phone(phone_match.group(0))

        # Fallback: look for any phone near agent keywords
        patterns = [
            r'"agentPhone"[:\s]*"([^"]+)"',
            r'tel:([0-9-]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return self._format_phone(match.group(1))

        return None

    def _format_phone(self, phone: str) -> str:
        """Format phone number consistently."""
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        return phone

    def _extract_agent_email(self, html: str, text: str) -> Optional[str]:
        """Extract listing agent email."""
        # Look for email pattern
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

        # Try to find email in agent context
        agent_section = re.search(r'(listing\s*agent|listed\s*by)[^<]{0,500}', html + text, re.IGNORECASE)
        if agent_section:
            email_match = re.search(email_pattern, agent_section.group(0))
            if email_match:
                return email_match.group(0).lower()

        # Fallback patterns
        patterns = [
            r'"agentEmail"[:\s]*"([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).lower()

        return None

    def _extract_views(self, html: str, text: str) -> Optional[int]:
        """Extract page views count."""
        patterns = [
            r'([\d,]+)\s*views?\s*in',
            r'([\d,]+)\s*people\s*viewed',
            r'"viewCount"[:\s]*(\d+)',
            r'Viewed\s*([\d,]+)\s*times',
        ]
        for pattern in patterns:
            match = re.search(pattern, html + text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1).replace(',', ''))
                except ValueError:
                    continue
        return None

    def _extract_favorites(self, html: str, text: str) -> Optional[int]:
        """Extract favorites/saves count."""
        patterns = [
            r'([\d,]+)\s*(?:people\s*)?(?:favorited|saved)',
            r'"favoriteCount"[:\s]*(\d+)',
            r'(\d+)\s*favorites?',
        ]
        for pattern in patterns:
            match = re.search(pattern, html + text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1).replace(',', ''))
                except ValueError:
                    continue
        return None

    def _extract_photo(self, html: str) -> Optional[str]:
        """Extract primary photo URL."""
        patterns = [
            r'<meta\s+property="og:image"\s+content="([^"]+)"',
            r'"primaryPhotoUrl"[:\s]*"([^"]+)"',
            r'<img[^>]+src="(https://ssl\.cdn-redfin\.com/[^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                if url.startswith('http') and 'thumb' not in url.lower():
                    return url
        return None

    def _update_property(self, conn, property_id: str, data: Dict):
        """Update property with scraped data."""
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute('''
            UPDATE properties SET
                listing_agent_name = COALESCE(?, listing_agent_name),
                listing_brokerage = COALESCE(?, listing_brokerage),
                listing_agent_phone = COALESCE(?, listing_agent_phone),
                listing_agent_email = COALESCE(?, listing_agent_email),
                page_views = COALESCE(?, page_views),
                favorites_count = COALESCE(?, favorites_count),
                primary_photo = COALESCE(?, primary_photo),
                updated_at = ?
            WHERE id = ?
        ''', (
            data.get('agent_name'),
            data.get('agent_company'),
            data.get('agent_phone'),
            data.get('agent_email'),
            data.get('page_views'),
            data.get('favorites_count'),
            data.get('primary_photo'),
            now,
            property_id
        ))

    def _mark_queue_complete(self, conn, queue_id: str, error: str = None):
        """Mark queue item as complete or failed."""
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        if error:
            cursor.execute('''
                UPDATE redfin_scrape_queue
                SET status = 'error', error = ?, scraped_at = ?
                WHERE id = ?
            ''', (error, now, queue_id))
        else:
            cursor.execute('''
                UPDATE redfin_scrape_queue
                SET status = 'complete', scraped_at = ?
                WHERE id = ?
            ''', (now, queue_id))

    async def process_queue(self, limit: int = None):
        """Process pending URLs from the scrape queue."""
        conn = self._get_connection()

        try:
            cursor = conn.cursor()

            # Get pending items
            query = '''
                SELECT id, property_id, url
                FROM redfin_scrape_queue
                WHERE status = 'pending'
                ORDER BY created_at
            '''
            if limit:
                query += f' LIMIT {limit}'

            cursor.execute(query)
            pending = cursor.fetchall()

            if not pending:
                logger.info("No pending URLs to scrape")
                return self.stats

            logger.info(f"Processing {len(pending)} URLs")

            for row in pending:
                queue_id, property_id, url = row['id'], row['property_id'], row['url']

                try:
                    data = await self.scrape_url(url)

                    if data:
                        self._update_property(conn, property_id, data)
                        self._mark_queue_complete(conn, queue_id)
                        self.stats['scraped'] += 1
                    else:
                        self._mark_queue_complete(conn, queue_id, "No data extracted")
                        self.stats['errors'] += 1

                    conn.commit()

                    # Rate limiting - be nice to Redfin
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Error processing {url}: {e}")
                    self._mark_queue_complete(conn, queue_id, str(e))
                    self.stats['errors'] += 1
                    conn.commit()

        finally:
            conn.close()

        return self.stats


async def main():
    parser = argparse.ArgumentParser(description='Scrape Redfin property pages for agent/engagement data')
    parser.add_argument('--limit', type=int, help='Max URLs to process')
    parser.add_argument('--url', help='Single URL to test scrape')
    parser.add_argument('--db', default=DB_PATH, help='Database path')
    parser.add_argument('--headed', action='store_true', help='Run browser in headed mode (visible)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    async with RedfinPageScraper(db_path=args.db, headless=not args.headed) as scraper:
        if args.url:
            # Test single URL
            data = await scraper.scrape_url(args.url)
            if data:
                print("\n" + "=" * 50)
                print("SCRAPED DATA")
                print("=" * 50)
                for key, value in data.items():
                    print(f"{key}: {value}")
            else:
                print("No data extracted")
        else:
            # Process queue
            stats = await scraper.process_queue(limit=args.limit)

            print("\n" + "=" * 50)
            print("SCRAPE SUMMARY")
            print("=" * 50)
            print(f"Scraped:  {stats['scraped']}")
            print(f"Errors:   {stats['errors']}")
            print(f"Skipped:  {stats['skipped']}")
            print("=" * 50)


if __name__ == '__main__':
    asyncio.run(main())
