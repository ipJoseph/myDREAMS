#!/usr/bin/env python3
"""
myDREAMS Property Monitor
Checks property listings daily for changes (price, status, views, saves)
Supports Zillow, Redfin, and Realtor.com via Playwright (replaces ScraperAPI)
"""

import os
import sys
import re
import time
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
import httpx
from notion_client import Client

# Import Playwright scrapers
from playwright_scraper import (
    PlaywrightScraper,
    RedfinPlaywrightScraper,
    ZillowPlaywrightScraper,
    get_scraper
)

# Load environment variables from .env file
def load_env_file():
    """Load environment variables from .env file"""
    env_path = '/home/bigeug/myDREAMS/.env'
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value

# Load .env before anything else
load_env_file()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/bigeug/myDREAMS/logs/property_monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Notion configuration
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DATABASE_ID = os.getenv('NOTION_PROPERTIES_DB_ID', '2eb02656b6a4432dbac17d681adbb640')

# Proxy configuration (optional - for residential proxies)
USE_PROXY = os.getenv('USE_PROXY', 'false').lower() == 'true'

# Rate limiting
RATE_LIMIT_DELAY = 3  # seconds between requests (be gentle on the sites)


class PropertyMonitor:
    """Monitors properties in Notion database using Playwright"""

    def __init__(self, use_proxy: bool = False, headless: bool = True):
        if not NOTION_API_KEY:
            raise ValueError("NOTION_API_KEY not set")

        self.notion = Client(auth=NOTION_API_KEY)
        # Format database ID as UUID with hyphens
        db_id = NOTION_DATABASE_ID.replace('-', '')
        self.database_id = f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"
        self.changes_detected = []
        self.use_proxy = use_proxy
        self.headless = headless

        # Playwright scrapers (instantiated per source)
        self.scraper_map = {
            'zillow': ZillowPlaywrightScraper,
            'redfin': RedfinPlaywrightScraper,
            # Realtor.com uses Redfin scraper as fallback (similar structure)
            'realtor': RedfinPlaywrightScraper,
        }

    def fetch_monitored_properties(self) -> List[Dict]:
        """Fetch all properties with monitoring enabled from Notion, then get URLs from SQLite"""
        try:
            # Query Notion for monitored properties
            headers = {
                'Authorization': f'Bearer {NOTION_API_KEY}',
                'Notion-Version': '2022-06-28',
                'Content-Type': 'application/json'
            }
            body = {
                'filter': {
                    'property': 'Monitoring Active',
                    'checkbox': {'equals': True}
                }
            }

            url = f'https://api.notion.com/v1/databases/{self.database_id}/query'
            resp = httpx.post(url, headers=headers, json=body, timeout=30)
            resp.raise_for_status()
            response = resp.json()

            # Get URL data from SQLite (more reliable than Notion for URLs)
            sqlite_urls = self._get_urls_from_sqlite()

            properties = []
            for page in response['results']:
                # Skip archived/trashed pages
                if page.get('archived', False) or page.get('in_trash', False):
                    continue

                props = page['properties']
                address = self._extract_title(props.get('Address'))

                # Look up URLs from SQLite by address
                url_data = sqlite_urls.get(address, {})

                property_data = {
                    'id': page['id'],
                    'url': page.get('url', ''),
                    'address': address,
                    # Get URLs from SQLite (fallback to Notion if not in SQLite)
                    'zillow_url': url_data.get('zillow_url') or self._extract_url(props.get('Zillow URL')),
                    'redfin_url': url_data.get('redfin_url') or self._extract_url(props.get('Redfin URL')),
                    'realtor_url': url_data.get('realtor_url') or self._extract_url(props.get('Realtor URL')),
                    # Get the source field
                    'source': url_data.get('source') or self._extract_select(props.get('Source')),
                    # Current values for comparison
                    'current_price': self._extract_number(props.get('Price')),
                    'current_status': self._extract_select(props.get('Status')),
                    'current_dom': self._extract_number(props.get('DOM')),
                    'current_views': self._extract_number(props.get('Page Views')),
                    'current_saves': self._extract_number(props.get('Favorites')),
                }

                # Determine which URL to use based on availability
                monitoring_url, monitoring_source = self._get_monitoring_url(property_data)
                property_data['monitoring_url'] = monitoring_url
                property_data['monitoring_source'] = monitoring_source

                if monitoring_url:
                    properties.append(property_data)
                else:
                    logger.warning(f"No URL available for {property_data['address']}")

            logger.info(f"Found {len(properties)} properties to monitor")
            return properties

        except Exception as e:
            logger.error(f"Error fetching properties: {e}")
            return []

    def _get_urls_from_sqlite(self) -> Dict[str, Dict]:
        """Fetch property URLs from SQLite database"""
        import sqlite3
        urls = {}
        try:
            db_path = '/home/bigeug/myDREAMS/data/dreams.db'
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT address, source, zillow_url, redfin_url, realtor_url
                FROM properties
                WHERE zillow_url IS NOT NULL OR redfin_url IS NOT NULL OR realtor_url IS NOT NULL
            ''')
            for row in cursor.fetchall():
                urls[row[0]] = {
                    'source': row[1],
                    'zillow_url': row[2],
                    'redfin_url': row[3],
                    'realtor_url': row[4],
                }
            conn.close()
            logger.info(f"Loaded {len(urls)} property URLs from SQLite")
        except Exception as e:
            logger.error(f"Error loading URLs from SQLite: {e}")
        return urls

    def _get_monitoring_url(self, prop: Dict) -> tuple:
        """
        Determine which URL to use for monitoring.
        Priority: Original source > Zillow > Redfin > Realtor
        Returns (url, source) tuple.
        """
        source = (prop.get('source') or '').lower()

        # First, try the original source
        if source == 'zillow' and prop.get('zillow_url'):
            return (prop['zillow_url'], 'zillow')
        elif source == 'redfin' and prop.get('redfin_url'):
            return (prop['redfin_url'], 'redfin')
        elif source == 'realtor' and prop.get('realtor_url'):
            return (prop['realtor_url'], 'realtor')

        # Fallback: try any available URL
        if prop.get('zillow_url'):
            return (prop['zillow_url'], 'zillow')
        if prop.get('redfin_url'):
            return (prop['redfin_url'], 'redfin')
        if prop.get('realtor_url'):
            return (prop['realtor_url'], 'realtor')

        return (None, None)

    async def check_property(self, property_data: Dict, scraper: PlaywrightScraper) -> Optional[Dict]:
        """Check a single property for changes using Playwright scraper"""
        address = property_data['address']
        monitoring_url = property_data['monitoring_url']
        monitoring_source = property_data['monitoring_source']

        logger.info(f"Checking: {address} via {monitoring_source}")

        # Fetch current data using the shared scraper instance
        new_data = await scraper.fetch_property_data(monitoring_url)
        if not new_data:
            logger.warning(f"Failed to fetch data for {address}")
            return None

        # Detect changes
        changes = {}

        # Price change
        if new_data.get('price') and new_data['price'] != property_data['current_price']:
            change_amount = new_data['price'] - (property_data['current_price'] or 0)
            changes['price'] = {
                'old': property_data['current_price'],
                'new': new_data['price'],
                'change': change_amount
            }

        # Status change
        if new_data.get('status') and new_data['status'] != property_data['current_status']:
            changes['status'] = {
                'old': property_data['current_status'],
                'new': new_data['status']
            }

        # DOM change
        if new_data.get('dom') and new_data['dom'] != property_data['current_dom']:
            changes['dom'] = {
                'old': property_data['current_dom'],
                'new': new_data['dom']
            }

        # Views change (if available for this source)
        if new_data.get('views') and new_data['views'] != property_data['current_views']:
            changes['views'] = {
                'old': property_data['current_views'],
                'new': new_data['views']
            }

        # Saves change (if available for this source)
        if new_data.get('saves') and new_data['saves'] != property_data['current_saves']:
            changes['saves'] = {
                'old': property_data['current_saves'],
                'new': new_data['saves']
            }

        if changes:
            logger.info(f"Changes detected: {changes}")
            return {
                'property': property_data,
                'new_data': new_data,
                'changes': changes
            }
        else:
            logger.info("No changes detected")
            return None

    def update_notion_property(self, property_id: str, new_data: Dict, changes: Dict):
        """Update Notion property with new data"""
        try:
            from zoneinfo import ZoneInfo

            # Get current time in Eastern timezone
            eastern = ZoneInfo('America/New_York')
            now_eastern = datetime.now(eastern)

            properties_to_update = {
                'Last Updated': {
                    'date': {
                        'start': now_eastern.isoformat(),
                    }
                }
            }

            # Update price
            if new_data.get('price'):
                properties_to_update['Price'] = {'number': new_data['price']}

            # Update status
            if new_data.get('status'):
                properties_to_update['Status'] = {'select': {'name': new_data['status']}}

            # Update DOM (Days on Market)
            if new_data.get('dom'):
                properties_to_update['DOM'] = {'number': new_data['dom']}

            # Update views (Page Views) - only if available
            if new_data.get('views'):
                properties_to_update['Page Views'] = {'number': new_data['views']}

            # Update saves (Favorites) - only if available
            if new_data.get('saves'):
                properties_to_update['Favorites'] = {'number': new_data['saves']}

            self.notion.pages.update(
                page_id=property_id,
                properties=properties_to_update
            )

            logger.info(f"Updated Notion property: {property_id}")

        except Exception as e:
            logger.error(f"Error updating Notion: {e}")

    def generate_report(self) -> str:
        """Generate report of changes"""
        if not self.changes_detected:
            return "No changes detected today."

        report = f"myDREAMS Property Monitor - {datetime.now().strftime('%B %d, %Y')}\n\n"
        report += f"Changes Detected: {len(self.changes_detected)}\n\n"


        # Price changes
        price_changes = [c for c in self.changes_detected if 'price' in c['changes']]
        if price_changes:
            report += "🚨 PRICE CHANGES:\n"
            for change in price_changes:
                prop = change['property']
                pc = change['changes']['price']
                direction = "REDUCED" if pc['change'] < 0 else "INCREASED"
                old_price = f"${pc['old']:,.0f}" if pc['old'] else "Unknown"
                new_price = f"${pc['new']:,.0f}" if pc['new'] else "Unknown"
                source = prop.get('monitoring_source', 'unknown').title()
                report += f"• {prop['address']} ({source}) - {direction} ${abs(pc['change']):,.0f} "
                report += f"({old_price} → {new_price})\n"
            report += "\n"


        # Status changes
        status_changes = [c for c in self.changes_detected if 'status' in c['changes']]
        if status_changes:
            report += "📍 STATUS CHANGES:\n"
            for change in status_changes:
                prop = change['property']
                sc = change['changes']['status']
                source = prop.get('monitoring_source', 'unknown').title()
                report += f"• {prop['address']} ({source}) - {sc['old']} → {sc['new']}\n"
            report += "\n"

        return report

    async def run_async(self):
        """Main monitoring loop (async version with Playwright)"""
        logger.info("=" * 60)
        logger.info("Starting Property Monitor (Playwright)")
        logger.info("=" * 60)

        # Fetch properties to monitor
        properties = self.fetch_monitored_properties()

        if not properties:
            logger.warning("No properties to monitor")
            return

        # Group properties by source for efficient scraper reuse
        by_source = {}
        for prop in properties:
            src = prop.get('monitoring_source', 'unknown')
            if src not in by_source:
                by_source[src] = []
            by_source[src].append(prop)

        logger.info(f"Properties by source: {dict((k, len(v)) for k, v in by_source.items())}")

        # Process each source group with a dedicated scraper
        for source, props in by_source.items():
            scraper_class = self.scraper_map.get(source)
            if not scraper_class:
                logger.warning(f"No scraper available for source: {source}")
                continue

            logger.info(f"\n--- Processing {len(props)} {source.title()} properties ---")

            # Use context manager for proper browser lifecycle
            async with scraper_class(use_proxy=self.use_proxy, headless=self.headless) as scraper:
                for prop in props:
                    try:
                        result = await self.check_property(prop, scraper)

                        if result:
                            self.changes_detected.append(result)
                            self.update_notion_property(
                                prop['id'],
                                result['new_data'],
                                result['changes']
                            )
                        else:
                            # Still update Last Updated timestamp
                            self.update_notion_property(
                                prop['id'],
                                {'price': prop['current_price']},
                                {}
                            )
                    except Exception as e:
                        logger.error(f"Error checking {prop['address']}: {e}")

                    # Rate limiting between requests
                    await asyncio.sleep(RATE_LIMIT_DELAY)

        # Generate report
        report = self.generate_report()
        logger.info("\n" + report)

        logger.info("Monitor complete")
        logger.info("=" * 60)

    def run(self):
        """Synchronous entry point that runs the async monitor"""
        asyncio.run(self.run_async())

    # Helper methods
    @staticmethod
    def _extract_title(prop):
        if prop and prop.get('title'):
            return prop['title'][0]['plain_text'] if prop['title'] else None
        return None

    @staticmethod
    def _extract_url(prop):
        return prop.get('url') if prop else None

    @staticmethod
    def _extract_number(prop):
        return prop.get('number') if prop else None

    @staticmethod
    def _extract_select(prop):
        if prop and prop.get('select'):
            return prop['select']['name']
        return None

    @staticmethod
    def _extract_rich_text(prop):
        if prop and prop.get('rich_text') and len(prop['rich_text']) > 0:
            return prop['rich_text'][0]['plain_text']
        return None


def main():
    """Entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='myDREAMS Property Monitor')
    parser.add_argument('--proxy', action='store_true', help='Use proxy for requests')
    parser.add_argument('--visible', action='store_true', help='Show browser (non-headless)')
    args = parser.parse_args()

    try:
        monitor = PropertyMonitor(
            use_proxy=args.proxy or USE_PROXY,
            headless=not args.visible
        )
        monitor.run()
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
