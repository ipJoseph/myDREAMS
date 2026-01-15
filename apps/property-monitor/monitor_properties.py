#!/usr/bin/env python3
"""
myDREAMS Property Monitor
Checks property listings daily for changes (price, status, views, saves)
Supports Zillow, Redfin, and Realtor.com via ScraperAPI
"""

import os
import sys
import re
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
import requests
import httpx
from bs4 import BeautifulSoup
from notion_client import Client

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

# ScraperAPI configuration
SCRAPERAPI_KEY = os.getenv('SCRAPERAPI_KEY')

# Rate limiting
RATE_LIMIT_DELAY = 2  # seconds between requests


class BaseScraper:
    """Base class for property scrapers"""

    @staticmethod
    def fetch_page(url: str) -> Optional[BeautifulSoup]:
        """Fetch page content via ScraperAPI"""
        if not SCRAPERAPI_KEY:
            logger.error("SCRAPERAPI_KEY not set")
            return None

        try:
            logger.info(f"Fetching via ScraperAPI: {url}")
            api_url = f'http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={url}'
            response = requests.get(api_url, timeout=60)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.Timeout:
            logger.error(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    @staticmethod
    def extract_price_from_text(text: str) -> Optional[float]:
        """Extract price from text using common patterns"""
        price_match = re.search(r'\$(\d{1,3}(?:,\d{3})+)', text)
        if price_match:
            price = int(price_match.group(1).replace(',', ''))
            if 10000 < price < 10000000:
                return float(price)
        return None


class ZillowScraper(BaseScraper):
    """Scrapes property data from Zillow"""

    @classmethod
    def fetch_property_data(cls, url: str) -> Optional[Dict]:
        """Fetch all property data from Zillow"""
        soup = cls.fetch_page(url)
        if not soup:
            return None

        text = soup.get_text()

        data = {
            'price': cls._extract_price(soup, text),
            'status': cls._extract_status(text),
            'dom': cls._extract_dom(text),
            'views': cls._extract_views(text),
            'saves': cls._extract_saves(text),
        }

        logger.info(f"Zillow extracted: {data}")
        return data

    @classmethod
    def _extract_price(cls, soup: BeautifulSoup, text: str) -> Optional[float]:
        """Extract current list price"""
        # Method 1: Look for price in spans
        spans = soup.find_all('span')
        for span in spans:
            span_text = span.get_text().strip()
            if span_text.startswith('$') and len(span_text) > 4 and ',' in span_text:
                price = int(''.join(filter(str.isdigit, span_text)))
                if 10000 < price < 10000000:
                    return float(price)

        # Method 2: Search body text
        return cls.extract_price_from_text(text)

    @staticmethod
    def _extract_status(text: str) -> Optional[str]:
        """Extract listing status"""
        text_lower = text.lower()
        if 'pending' in text_lower:
            return 'Pending'
        elif 'sold' in text_lower and 'last sold' not in text_lower:
            return 'Sold'
        elif 'off market' in text_lower:
            return 'Off Market'
        elif 'for sale' in text_lower or 'buy' in text_lower:
            return 'Active'
        return 'Active'

    @staticmethod
    def _extract_dom(text: str) -> Optional[int]:
        """Extract Days on Zillow"""
        match = re.search(r'(\d+)\s*days?\s*on\s*zillow', text, re.IGNORECASE)
        if match:
            dom = int(match.group(1))
            if 0 < dom < 1000:  # Sanity check
                return dom
        return None

    @staticmethod
    def _extract_views(text: str) -> Optional[int]:
        """Extract view count"""
        match = re.search(r'([\d,]+)\s*views?(?!\s*:)', text, re.IGNORECASE)
        if match:
            views = int(match.group(1).replace(',', ''))
            if views > 0:
                return views
        return None

    @staticmethod
    def _extract_saves(text: str) -> Optional[int]:
        """Extract save count"""
        match = re.search(r'(\d+)\s*saves?(?!\s*:)', text, re.IGNORECASE)
        if match:
            saves = int(match.group(1))
            if saves > 0:
                return saves
        return None


class RedfinScraper(BaseScraper):
    """Scrapes property data from Redfin"""

    @classmethod
    def fetch_property_data(cls, url: str) -> Optional[Dict]:
        """Fetch all property data from Redfin"""
        soup = cls.fetch_page(url)
        if not soup:
            return None

        text = soup.get_text()

        data = {
            'price': cls._extract_price(soup, text),
            'status': cls._extract_status(text),
            'dom': cls._extract_dom(text),
            'views': cls._extract_views(text),
            'saves': cls._extract_saves(text),
        }

        logger.info(f"Redfin extracted: {data}")
        return data

    @classmethod
    def _extract_price(cls, soup: BeautifulSoup, text: str) -> Optional[float]:
        """Extract current list price"""
        # Try specific Redfin selectors
        price_selectors = [
            '[data-rf-test-id="abp-price"]',
            '.statsValue',
            '.price-section .price',
            '.home-main-stats-variant .stat-value',
        ]
        for sel in price_selectors:
            el = soup.select_one(sel)
            if el:
                price_match = re.search(r'\$([\d,]+)', el.get_text())
                if price_match:
                    price = int(price_match.group(1).replace(',', ''))
                    if 10000 < price < 10000000:
                        return float(price)

        # Fallback to text search
        return cls.extract_price_from_text(text)

    @staticmethod
    def _extract_status(text: str) -> Optional[str]:
        """Extract listing status"""
        text_lower = text.lower()
        if 'pending' in text_lower:
            return 'Pending'
        elif 'sold' in text_lower and 'last sold' not in text_lower:
            return 'Sold'
        elif 'off market' in text_lower:
            return 'Off Market'
        elif 'contingent' in text_lower:
            return 'Contingent'
        elif 'for sale' in text_lower or 'active' in text_lower:
            return 'Active'
        return 'Active'

    @staticmethod
    def _extract_dom(text: str) -> Optional[int]:
        """Extract Days on Redfin"""
        match = re.search(r'(\d+)\s*days?\s*on\s*redfin', text, re.IGNORECASE)
        if match:
            dom = int(match.group(1))
            if 0 < dom < 1000:  # Sanity check - DOM should be < 1000 days
                return dom
        # Try generic days on market
        match = re.search(r'(\d+)\s*days?\s*on\s*market', text, re.IGNORECASE)
        if match:
            dom = int(match.group(1))
            if 0 < dom < 1000:
                return dom
        return None

    @staticmethod
    def _extract_views(text: str) -> Optional[int]:
        """Extract view count"""
        # Pattern: "208 views" in stats line
        match = re.search(r'(\d+)\s*views?', text, re.IGNORECASE)
        if match:
            views = int(match.group(1))
            if views > 0:
                return views
        return None

    @staticmethod
    def _extract_saves(text: str) -> Optional[int]:
        """Extract favorites count"""
        # Pattern: "6 favorites" in stats line
        match = re.search(r'(\d+)\s*favorites?', text, re.IGNORECASE)
        if match:
            saves = int(match.group(1))
            if saves > 0:
                return saves
        return None


class RealtorScraper(BaseScraper):
    """Scrapes property data from Realtor.com"""

    @classmethod
    def fetch_property_data(cls, url: str) -> Optional[Dict]:
        """Fetch all property data from Realtor.com"""
        soup = cls.fetch_page(url)
        if not soup:
            return None

        text = soup.get_text()

        data = {
            'price': cls._extract_price(soup, text),
            'status': cls._extract_status(text),
            'dom': cls._extract_dom(text),
            'views': None,  # Realtor.com doesn't typically show views
            'saves': None,  # Realtor.com doesn't typically show saves
        }

        logger.info(f"Realtor.com extracted: {data}")
        return data

    @classmethod
    def _extract_price(cls, soup: BeautifulSoup, text: str) -> Optional[float]:
        """Extract current list price"""
        # Try specific Realtor.com selectors
        price_selectors = [
            '[data-testid="list-price"]',
            '.list-price',
            '.price-section',
            '.ldp-header-price',
        ]
        for sel in price_selectors:
            el = soup.select_one(sel)
            if el:
                price_match = re.search(r'\$([\d,]+)', el.get_text())
                if price_match:
                    price = int(price_match.group(1).replace(',', ''))
                    if 10000 < price < 10000000:
                        return float(price)

        # Fallback to text search
        return cls.extract_price_from_text(text)

    @staticmethod
    def _extract_status(text: str) -> Optional[str]:
        """Extract listing status"""
        text_lower = text.lower()
        if 'pending' in text_lower:
            return 'Pending'
        elif 'sold' in text_lower and 'last sold' not in text_lower:
            return 'Sold'
        elif 'off market' in text_lower:
            return 'Off Market'
        elif 'contingent' in text_lower:
            return 'Contingent'
        elif 'for sale' in text_lower or 'active' in text_lower:
            return 'Active'
        return 'Active'

    @staticmethod
    def _extract_dom(text: str) -> Optional[int]:
        """Extract Days on Market"""
        # Various patterns for DOM
        patterns = [
            r'(\d+)\s*days?\s*on\s*realtor',
            r'(\d+)\s*days?\s*on\s*market',
            r'listed\s*(\d+)\s*days?\s*ago',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                dom = int(match.group(1))
                if 0 < dom < 1000:  # Sanity check
                    return dom
        return None


class PropertyMonitor:
    """Monitors properties in Notion database"""

    def __init__(self):
        if not NOTION_API_KEY:
            raise ValueError("NOTION_API_KEY not set")

        self.notion = Client(auth=NOTION_API_KEY)
        # Format database ID as UUID with hyphens
        db_id = NOTION_DATABASE_ID.replace('-', '')
        self.database_id = f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"
        self.changes_detected = []

        # Source to scraper mapping
        self.scrapers = {
            'zillow': ZillowScraper,
            'redfin': RedfinScraper,
            'realtor': RealtorScraper,
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

    def check_property(self, property_data: Dict) -> Optional[Dict]:
        """Check a single property for changes using appropriate scraper"""
        address = property_data['address']
        monitoring_url = property_data['monitoring_url']
        monitoring_source = property_data['monitoring_source']

        logger.info(f"Checking: {address} via {monitoring_source}")

        # Get the appropriate scraper
        scraper_class = self.scrapers.get(monitoring_source)
        if not scraper_class:
            logger.warning(f"No scraper available for source: {monitoring_source}")
            return None

        # Fetch current data
        new_data = scraper_class.fetch_property_data(monitoring_url)
        if not new_data:
            logger.warning(f"Failed to fetch data for {address}")
            return None

        # Detect changes
        changes = {}

        # Price change
        if new_data['price'] and new_data['price'] != property_data['current_price']:
            change_amount = new_data['price'] - (property_data['current_price'] or 0)
            changes['price'] = {
                'old': property_data['current_price'],
                'new': new_data['price'],
                'change': change_amount
            }

        # Status change
        if new_data['status'] and new_data['status'] != property_data['current_status']:
            changes['status'] = {
                'old': property_data['current_status'],
                'new': new_data['status']
            }

        # DOM change
        if new_data['dom'] and new_data['dom'] != property_data['current_dom']:
            changes['dom'] = {
                'old': property_data['current_dom'],
                'new': new_data['dom']
            }

        # Views change (if available for this source)
        if new_data['views'] and new_data['views'] != property_data['current_views']:
            changes['views'] = {
                'old': property_data['current_views'],
                'new': new_data['views']
            }

        # Saves change (if available for this source)
        if new_data['saves'] and new_data['saves'] != property_data['current_saves']:
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

    def run(self):
        """Main monitoring loop"""
        logger.info("=" * 60)
        logger.info("Starting Property Monitor (Multi-Source)")
        logger.info("=" * 60)

        # Fetch properties to monitor
        properties = self.fetch_monitored_properties()

        if not properties:
            logger.warning("No properties to monitor")
            return

        # Log source breakdown
        sources = {}
        for prop in properties:
            src = prop.get('monitoring_source', 'unknown')
            sources[src] = sources.get(src, 0) + 1
        logger.info(f"Properties by source: {sources}")

        # Check each property
        for prop in properties:
            result = self.check_property(prop)

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

            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)

        # Generate report
        report = self.generate_report()
        logger.info("\n" + report)

        logger.info("Monitor complete")
        logger.info("=" * 60)

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
    try:
        monitor = PropertyMonitor()
        monitor.run()
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
