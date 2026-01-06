#!/usr/bin/env python3
"""
myDREAMS Property Monitor
Checks Zillow listings daily for changes (price, status, views, saves)
Uses ScraperAPI to avoid blocking
"""

import os
import sys
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup
from notion_client import Client

import os
import sys
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
import requests
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
DATA_SOURCE_ID = '54df6a1e-390d-43c6-8023-3e0dc9b87c23'

# ScraperAPI configuration
SCRAPERAPI_KEY = os.getenv('SCRAPERAPI_KEY')

# Rate limiting
RATE_LIMIT_DELAY = 2  # seconds between requests


class ZillowScraper:
    """Scrapes property data from Zillow using ScraperAPI"""
    
    @staticmethod
    def extract_price(soup: BeautifulSoup) -> Optional[float]:
        """Extract current list price"""
        try:
            # Method 1: Look for price in spans
            spans = soup.find_all('span')
            for span in spans:
                text = span.get_text().strip()
                if text.startswith('$') and len(text) > 4 and ',' in text:
                    # Extract: "$749,000" -> 749000
                    price = int(''.join(filter(str.isdigit, text)))
                    if 10000 < price < 10000000:  # Reasonable range
                        return float(price)
            
            # Method 2: Search body text for price pattern
            body_text = soup.get_text()
            import re
            price_match = re.search(r'\$(\d{1,3}(?:,\d{3})+)', body_text)
            if price_match:
                price = int(price_match.group(1).replace(',', ''))
                if 10000 < price < 10000000:
                    return float(price)
            
            logger.warning("Could not extract price")
            return None
        except Exception as e:
            logger.error(f"Error extracting price: {e}")
            return None
    
    @staticmethod
    def extract_status(soup: BeautifulSoup) -> Optional[str]:
        """Extract listing status"""
        try:
            text_lower = soup.get_text().lower()
            
            if 'pending' in text_lower:
                return 'Pending'
            elif 'sold' in text_lower and 'last sold' not in text_lower:
                return 'Sold'
            elif 'off market' in text_lower:
                return 'Off Market'
            elif 'for sale' in text_lower or 'buy' in text_lower:
                return 'Active'
            
            return 'Active'  # Default
        except Exception as e:
            logger.error(f"Error extracting status: {e}")
            return None
    
    @staticmethod
    def extract_dom(soup: BeautifulSoup) -> Optional[int]:
        """Extract Days on Zillow"""
        try:
            text = soup.get_text()
            import re
            
            # Look for "X days on Zillow"
            match = re.search(r'(\d+)\s*days?\s*on\s*zillow', text, re.IGNORECASE)
            if match:
                return int(match.group(1))
            
            return None
        except Exception as e:
            logger.error(f"Error extracting DOM: {e}")
            return None
    
    @staticmethod
    def extract_views(soup: BeautifulSoup) -> Optional[int]:
        """Extract view count"""
        try:
            text = soup.get_text()
            import re
            
            # Look for "X,XXX views" - handle commas
            match = re.search(r'([\d,]+)\s*views?(?!\s*:)', text, re.IGNORECASE)
            if match:
                views = int(match.group(1).replace(',', ''))
                if views > 0:
                    return views
            
            return None
        except Exception as e:
            logger.error(f"Error extracting views: {e}")
            return None
    
    @staticmethod
    def extract_saves(soup: BeautifulSoup) -> Optional[int]:
        """Extract save count"""
        try:
            text = soup.get_text()
            import re
            
            # Look for "XX saves"
            match = re.search(r'(\d+)\s*saves?(?!\s*:)', text, re.IGNORECASE)
            if match:
                saves = int(match.group(1))
                if saves > 0:
                    return saves
            
            return None
        except Exception as e:
            logger.error(f"Error extracting saves: {e}")
            return None
    
    @classmethod
    def fetch_property_data(cls, url: str) -> Optional[Dict]:
        """Fetch all property data from Zillow using ScraperAPI"""
        
        if not SCRAPERAPI_KEY:
            logger.error("SCRAPERAPI_KEY not set")
            return None
        
        try:
            logger.info(f"Fetching via ScraperAPI: {url}")
            
            # Use ScraperAPI
            api_url = f'http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={url}'
            response = requests.get(api_url, timeout=60)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            data = {
                'price': cls.extract_price(soup),
                'status': cls.extract_status(soup),
                'dom': cls.extract_dom(soup),
                'views': cls.extract_views(soup),
                'saves': cls.extract_saves(soup),
            }
            
            logger.info(f"Extracted: {data}")
            return data
            
        except requests.Timeout:
            logger.error(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None


class PropertyMonitor:
    """Monitors properties in Notion data source"""
    
    def __init__(self):
        if not NOTION_API_KEY:
            raise ValueError("NOTION_API_KEY not set")
        
        self.notion = Client(auth=NOTION_API_KEY)
        self.changes_detected = []
    
    def fetch_monitored_properties(self) -> List[Dict]:
        """Fetch all properties with monitoring enabled"""
        try:
            query_filter = {
                "property": "Monitoring Active",
                "checkbox": {
                    "equals": True
                }
            }
            
            response = self.notion.data_sources.query(
                data_source_id=DATA_SOURCE_ID,
                filter=query_filter
            )
            
            properties = []
            for page in response['results']:
                props = page['properties']
                
                property_data = {
                    'id': page['id'],
                    'url': page['url'],
                    'address': self._extract_title(props.get('Address')),
                    'zillow_url': self._extract_url(props.get('Zillow URL')),
                    'current_price': self._extract_number(props.get('Price')),
                    'current_status': self._extract_select(props.get('Status')),
                    'current_dom': self._extract_number(props.get('Days on Zillow')),
                    'current_views': self._extract_number(props.get('Zillow Views')),
                    'current_saves': self._extract_number(props.get('Zillow Saves')),
                }
                
                if property_data['zillow_url']:
                    properties.append(property_data)
                else:
                    logger.warning(f"No Zillow URL for {property_data['address']}")
            
            logger.info(f"Found {len(properties)} properties to monitor")
            return properties
            
        except Exception as e:
            logger.error(f"Error fetching properties: {e}")
            return []
    
    def check_property(self, property_data: Dict) -> Optional[Dict]:
        """Check a single property for changes"""
        logger.info(f"Checking: {property_data['address']}")
        
        # Fetch current Zillow data
        new_data = ZillowScraper.fetch_property_data(property_data['zillow_url'])
        if not new_data:
            logger.warning(f"Failed to fetch data for {property_data['address']}")
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
        
        # Views change
        if new_data['views'] and new_data['views'] != property_data['current_views']:
            changes['views'] = {
                'old': property_data['current_views'],
                'new': new_data['views']
            }
        
        # Saves change
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
            from datetime import datetime, timezone
            from zoneinfo import ZoneInfo
            
            # Get current time in Eastern timezone
            eastern = ZoneInfo('America/New_York')
            now_eastern = datetime.now(eastern)
            
            properties_to_update = {
                'Last Checked': {
                    'date': {
                        'start': now_eastern.isoformat(),
                    }
                }
            }
            
            # Update price
            if new_data.get('price'):
                properties_to_update['Price'] = {'number': new_data['price']}
                
                if 'price' in changes:
                    properties_to_update['Price Change'] = {'number': changes['price']['change']}
                    properties_to_update['Status Change Date'] = {
                        'date': {'start': now_eastern.date().isoformat()}
                    }
            
            # Update status
            if new_data.get('status'):
                properties_to_update['Status'] = {'select': {'name': new_data['status']}}
                
                if 'status' in changes:
                    properties_to_update['Status Change Date'] = {
                        'date': {'start': now_eastern.date().isoformat()}
                    }
            
            # Update DOM
            if new_data.get('dom'):
                properties_to_update['Days on Zillow'] = {'number': new_data['dom']}
            
            # Update views
            if new_data.get('views'):
                properties_to_update['Zillow Views'] = {'number': new_data['views']}
            
            # Update saves
            if new_data.get('saves'):
                properties_to_update['Zillow Saves'] = {'number': new_data['saves']}
            
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
                report += f"• {prop['address']} - {direction} ${abs(pc['change']):,.0f} "
                report += f"({old_price} → {new_price})\n"
            report += "\n"

        
        # Status changes
        status_changes = [c for c in self.changes_detected if 'status' in c['changes']]
        if status_changes:
            report += "📍 STATUS CHANGES:\n"
            for change in status_changes:
                prop = change['property']
                sc = change['changes']['status']
                report += f"• {prop['address']} - {sc['old']} → {sc['new']}\n"
            report += "\n"
        
        return report
    
    def run(self):
        """Main monitoring loop"""
        logger.info("=" * 60)
        logger.info("Starting Property Monitor")
        logger.info("=" * 60)
        
        # Fetch properties to monitor
        properties = self.fetch_monitored_properties()
        
        if not properties:
            logger.warning("No properties to monitor")
            return
        
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
                # Still update Last Checked
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
