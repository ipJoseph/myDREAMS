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
from pathlib import Path
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
    env_path = Path(__file__).parent.parent.parent / '.env'
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
PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_DIR = PROJECT_ROOT / 'logs'
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'property_monitor.log'),
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
        """Fetch all properties with monitoring enabled from Notion"""
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

            properties = []
            for page in response['results']:
                # Skip archived/trashed pages
                if page.get('archived', False) or page.get('in_trash', False):
                    continue

                props = page['properties']
                address = self._extract_title(props.get('Address'))

                # Get the main listing URL and source from Notion
                listing_url = self._extract_url(props.get('URL'))
                source = self._extract_select(props.get('Source'))

                property_data = {
                    'id': page['id'],
                    'notion_url': page.get('url', ''),  # Link to Notion page
                    'address': address,
                    'source': source,
                    # The listing URL (Redfin/Zillow/Realtor page)
                    'monitoring_url': listing_url,
                    'monitoring_source': (source or '').lower() if source else self._detect_source_from_url(listing_url),
                    # Current values for comparison
                    'current_price': self._extract_number(props.get('Price')),
                    'current_status': self._extract_select(props.get('Status')),
                    'current_dom': self._extract_number(props.get('DOM')),
                    'current_views': self._extract_number(props.get('Page Views')),
                    'current_saves': self._extract_number(props.get('Favorites')),
                    # Track how many times we've checked this property
                    'current_view_count': self._extract_number(props.get('ViewCount')) or 0,
                    # Check if photo exists
                    'has_photo': self._has_files(props.get('Photos')),
                }

                if listing_url:
                    properties.append(property_data)
                else:
                    logger.warning(f"No URL available for {property_data['address']}")

            logger.info(f"Found {len(properties)} properties to monitor")
            return properties

        except Exception as e:
            logger.error(f"Error fetching properties: {e}")
            return []

    def _detect_source_from_url(self, url: str) -> str:
        """Detect the source (redfin/zillow/realtor) from a URL"""
        if not url:
            return 'unknown'
        url_lower = url.lower()
        if 'redfin.com' in url_lower:
            return 'redfin'
        elif 'zillow.com' in url_lower:
            return 'zillow'
        elif 'realtor.com' in url_lower:
            return 'realtor'
        return 'unknown'

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
        else:
            logger.info("No changes detected")

        # Always return new_data so views/saves can be updated even without price/status changes
        return {
            'property': property_data,
            'new_data': new_data,
            'changes': changes
        }

    def update_notion_property(self, property_id: str, new_data: Dict, changes: Dict, current_view_count: int = 0, has_photo: bool = True):
        """Update Notion property with new data"""
        try:
            from zoneinfo import ZoneInfo

            # Get current time in Eastern timezone
            eastern = ZoneInfo('America/New_York')
            now_eastern = datetime.now(eastern)

            # Increment ViewCount - tracks how many times we've visited this property
            new_view_count = current_view_count + 1

            properties_to_update = {
                'Last Updated': {
                    'date': {
                        'start': now_eastern.isoformat(),
                    }
                },
                # Increment our visit counter (for calculating real external views)
                'ViewCount': {'number': new_view_count}
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

            # Update photo if property doesn't have one and we found one
            if not has_photo and new_data.get('primary_photo'):
                logger.info(f"Adding photo to property: {new_data['primary_photo'][:60]}...")
                properties_to_update['Photos'] = {
                    'files': [{
                        'type': 'external',
                        'name': 'Primary Photo',
                        'external': {'url': new_data['primary_photo']}
                    }]
                }

            self.notion.pages.update(
                page_id=property_id,
                properties=properties_to_update
            )

            photo_status = " (added photo)" if not has_photo and new_data.get('primary_photo') else ""
            logger.info(f"Updated Notion property: {property_id} (ViewCount: {new_view_count}){photo_status}")

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

        # Views changes
        views_changes = [c for c in self.changes_detected if 'views' in c['changes']]
        if views_changes:
            report += "👁️ VIEWS CHANGES:\n"
            for change in views_changes:
                prop = change['property']
                vc = change['changes']['views']
                old_views = vc['old'] or 0
                new_views = vc['new'] or 0
                diff = new_views - old_views
                direction = "+" if diff > 0 else ""
                source = prop.get('monitoring_source', 'unknown').title()
                report += f"• {prop['address']} ({source}) - {old_views} → {new_views} ({direction}{diff})\n"
            report += "\n"

        # Saves/Favorites changes
        saves_changes = [c for c in self.changes_detected if 'saves' in c['changes']]
        if saves_changes:
            report += "❤️ FAVORITES CHANGES:\n"
            for change in saves_changes:
                prop = change['property']
                sc = change['changes']['saves']
                old_saves = sc['old'] or 0
                new_saves = sc['new'] or 0
                diff = new_saves - old_saves
                direction = "+" if diff > 0 else ""
                source = prop.get('monitoring_source', 'unknown').title()
                report += f"• {prop['address']} ({source}) - {old_saves} → {new_saves} ({direction}{diff})\n"
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

                        if result and result.get('new_data'):
                            # Track significant changes for the report
                            if result.get('changes'):
                                self.changes_detected.append(result)

                            # Always update Notion with fresh data (including views/saves)
                            self.update_notion_property(
                                prop['id'],
                                result['new_data'],
                                result.get('changes', {}),
                                prop.get('current_view_count', 0),
                                prop.get('has_photo', True)
                            )
                        else:
                            # Scrape failed - just update timestamp and ViewCount
                            logger.warning(f"No data fetched for {prop['address']}")
                            self.update_notion_property(
                                prop['id'],
                                {'price': prop['current_price']},
                                {},
                                prop.get('current_view_count', 0),
                                prop.get('has_photo', True)
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

    @staticmethod
    def _has_files(prop):
        """Check if a files property has any files"""
        if prop and prop.get('files') and len(prop['files']) > 0:
            return True
        return False


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
