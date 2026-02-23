#!/usr/bin/env python3
"""
Playwright-based Property Scraper

Replaces ScraperAPI with self-hosted Playwright for better reliability
and full data capture similar to the Chrome extension.
"""

import os
import re
import json
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from playwright.async_api import async_playwright, Page, Browser
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)

# Proxy configuration (set via environment or config)
PROXY_HOST = os.getenv('PROXY_HOST', '')
PROXY_PORT = os.getenv('PROXY_PORT', '')
PROXY_USER = os.getenv('PROXY_USER', '')
PROXY_PASS = os.getenv('PROXY_PASS', '')


class PlaywrightScraper:
    """Base class for Playwright-based property scrapers"""

    def __init__(self, use_proxy: bool = False, headless: bool = True):
        self.use_proxy = use_proxy
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.playwright = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self):
        """Start the browser"""
        self.playwright = await async_playwright().start()

        launch_options = {
            'headless': self.headless,
        }

        # Add proxy if configured
        if self.use_proxy and PROXY_HOST and PROXY_PORT:
            launch_options['proxy'] = {
                'server': f'http://{PROXY_HOST}:{PROXY_PORT}',
            }
            if PROXY_USER and PROXY_PASS:
                launch_options['proxy']['username'] = PROXY_USER
                launch_options['proxy']['password'] = PROXY_PASS
            logger.info(f"Using proxy: {PROXY_HOST}:{PROXY_PORT}")

        self.browser = await self.playwright.chromium.launch(**launch_options)
        logger.info("Playwright browser started")

    async def stop(self):
        """Stop the browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Playwright browser stopped")

    async def fetch_page(self, url: str, wait_for: str = 'networkidle') -> Optional[tuple]:
        """
        Fetch a page and return (page_content, page_text).

        Args:
            url: URL to fetch
            wait_for: Wait condition ('networkidle', 'load', 'domcontentloaded')

        Returns:
            Tuple of (html_content, text_content) or None on error
        """
        if not self.browser:
            await self.start()

        page = None
        try:
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            page = await context.new_page()

            # Apply stealth to avoid detection
            stealth = Stealth()
            await stealth.apply_stealth_async(page)

            logger.info(f"Fetching: {url}")
            response = await page.goto(url, wait_until=wait_for, timeout=60000)

            if response and response.status >= 400:
                logger.error(f"HTTP {response.status} for {url}")
                return None

            # Wait a bit for JavaScript to execute
            await page.wait_for_timeout(2000)

            html_content = await page.content()
            text_content = await page.evaluate('() => document.body.innerText')

            return (html_content, text_content)

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

        finally:
            if page:
                await page.close()


class RedfinPlaywrightScraper(PlaywrightScraper):
    """Scrapes property data from Redfin using Playwright"""

    async def fetch_property_data(self, url: str) -> Optional[Dict]:
        """Fetch all property data from Redfin"""
        result = await self.fetch_page(url)
        if not result:
            return None

        html_content, text_content = result

        data = {
            'price': self._extract_price(html_content, text_content),
            'status': self._extract_status(html_content, text_content),
            'dom': self._extract_dom(text_content),
            'views': self._extract_views(text_content),
            'saves': self._extract_saves(text_content),
            # Extended fields (same as extension)
            'beds': self._extract_beds(text_content),
            'baths': self._extract_baths(text_content),
            'sqft': self._extract_sqft(text_content),
            'address': self._extract_address(html_content),
            'mls_number': self._extract_mls(text_content),
            'primary_photo': self._extract_photo(html_content),
        }

        logger.info(f"Redfin extracted: price={data['price']}, status={data['status']}, dom={data['dom']}, photo={'yes' if data['primary_photo'] else 'no'}")
        return data

    def _extract_price(self, html: str, text: str) -> Optional[float]:
        """Extract current list price"""
        # Method 1: Look for price patterns in text
        patterns = [
            r'\$(\d{1,3}(?:,\d{3})+)(?:\s|$)',  # $XXX,XXX
            r'Price\s*[:\s]*\$(\d{1,3}(?:,\d{3})+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                price = int(match.group(1).replace(',', ''))
                if 10000 < price < 50000000:  # Reasonable price range
                    return float(price)

        return None

    def _extract_status(self, html: str, text: str) -> Optional[str]:
        """
        Extract listing status from Redfin.
        Carefully avoids false positives from 'pending homes nearby' sections.
        """
        # Method 1: Check page title (most reliable)
        title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).lower()
            if 'pending' in title:
                return 'Pending'
            if 'sold' in title:
                return 'Sold'

        # Method 2: Look for status banners in HTML
        status_patterns = [
            r'class="[^"]*(?:listing-status|status)[^"]*"[^>]*>([^<]+)',
            r'data-rf-test-id="listing-status"[^>]*>([^<]+)',
        ]

        for pattern in status_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                status_text = match.group(1).lower().strip()
                if 'pending' in status_text:
                    return 'Pending'
                if 'sold' in status_text:
                    return 'Sold'
                if 'contingent' in status_text:
                    return 'Contingent'
                if 'off market' in status_text:
                    return 'Off Market'

        # Method 3: Check header area only (first 3000 chars of text)
        header_text = text[:3000].lower()

        # Look for explicit status, excluding "pending homes" sections
        if re.search(r'\bpending\b(?!\s+homes|\s+properties|\s+listings|\s+nearby)', header_text):
            return 'Pending'
        if re.search(r'\bsold\b(?!\s+homes|\s+history|\s+properties)', header_text):
            return 'Sold'
        if 'contingent' in header_text:
            return 'Contingent'
        if 'off market' in header_text:
            return 'Off Market'

        # Default to Active (active listings don't usually show status banner)
        return 'Active'

    def _extract_dom(self, text: str) -> Optional[int]:
        """Extract Days on Redfin/Market"""
        patterns = [
            r'(\d+)\s*days?\s*on\s*redfin',
            r'(\d+)\s*days?\s*on\s*market',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                dom = int(match.group(1))
                if 0 < dom < 2000:
                    return dom
        return None

    def _extract_views(self, text: str) -> Optional[int]:
        """Extract view count"""
        match = re.search(r'(\d+)\s*views?', text, re.IGNORECASE)
        if match:
            views = int(match.group(1))
            if views > 0:
                return views
        return None

    def _extract_saves(self, text: str) -> Optional[int]:
        """Extract favorites/saves count"""
        match = re.search(r'(\d+)\s*favorites?', text, re.IGNORECASE)
        if match:
            saves = int(match.group(1))
            if saves > 0:
                return saves
        return None

    def _extract_beds(self, text: str) -> Optional[int]:
        """Extract bedroom count"""
        match = re.search(r'(\d+)\s*(?:beds?|br|bedrooms?)', text, re.IGNORECASE)
        if match:
            beds = int(match.group(1))
            if 0 < beds < 50:
                return beds
        return None

    def _extract_baths(self, text: str) -> Optional[float]:
        """Extract bathroom count"""
        match = re.search(r'([\d.]+)\s*(?:baths?|ba|bathrooms?)', text, re.IGNORECASE)
        if match:
            baths = float(match.group(1))
            if 0 < baths < 50:
                return baths
        return None

    def _extract_sqft(self, text: str) -> Optional[int]:
        """Extract square footage"""
        match = re.search(r'([\d,]+)\s*(?:sq\.?\s*ft|sqft|square\s*feet)', text, re.IGNORECASE)
        if match:
            sqft = int(match.group(1).replace(',', ''))
            if 100 < sqft < 100000:
                return sqft
        return None

    def _extract_address(self, html: str) -> Optional[str]:
        """Extract property address"""
        # Try title first
        match = re.search(r'<title>([^|<]+)', html)
        if match:
            title = match.group(1).strip()
            # Remove "Pending" or "Sold" prefix
            title = re.sub(r'^(Pending|Sold)\s*[-–]\s*', '', title).strip()
            if title and ',' in title:
                return title
        return None

    def _extract_mls(self, text: str) -> Optional[str]:
        """Extract MLS number"""
        patterns = [
            r'MLS[#:\s]+([A-Z0-9]{5,})',  # MLS# followed by 5+ alphanumeric
            r'Source:\s*\w+\s*#([A-Z0-9]{5,})',  # Source: XYZ #12345
            r'Listing\s+ID[#:\s]+([A-Z0-9]{5,})',  # Listing ID: 12345
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                mls = match.group(1)
                # Verify it's likely an MLS number (at least 5 chars)
                if len(mls) >= 5:
                    return mls
        return None

    def _extract_photo(self, html: str) -> Optional[str]:
        """Extract primary photo URL from Redfin property page"""
        # Method 1: Look for og:image meta tag (most reliable for primary photo)
        og_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html, re.IGNORECASE)
        if og_match:
            url = og_match.group(1)
            if url.startswith('http') and 'redfin' in url.lower():
                return url

        # Method 2: Look for main photo in JSON-LD data
        json_ld_match = re.search(r'<script type="application/ld\+json">([^<]+)</script>', html)
        if json_ld_match:
            try:
                ld_data = json.loads(json_ld_match.group(1))
                if isinstance(ld_data, dict):
                    photo = ld_data.get('image') or ld_data.get('photo')
                    if isinstance(photo, str) and photo.startswith('http'):
                        return photo
                    elif isinstance(photo, list) and photo:
                        return photo[0] if isinstance(photo[0], str) else photo[0].get('url')
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

        # Method 3: Look for Redfin CDN image URLs in img tags
        img_patterns = [
            r'<img[^>]+src="(https://ssl\.cdn-redfin\.com/[^"]+)"',
            r'<img[^>]+src="(https://[^"]*redfin[^"]*photos[^"]+)"',
        ]
        for pattern in img_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                # Skip thumbnails and icons
                if 'thumb' not in url.lower() and 'icon' not in url.lower():
                    return url

        # Method 4: Look for background-image style with Redfin URL
        bg_match = re.search(r'background-image:\s*url\(["\']?(https://[^"\')]+redfin[^"\')]+)["\']?\)', html, re.IGNORECASE)
        if bg_match:
            return bg_match.group(1)

        return None


class ZillowPlaywrightScraper(PlaywrightScraper):
    """Scrapes property data from Zillow using Playwright"""

    async def fetch_property_data(self, url: str) -> Optional[Dict]:
        """Fetch all property data from Zillow"""
        result = await self.fetch_page(url)
        if not result:
            return None

        html_content, text_content = result

        # Try to extract from NEXT_DATA JSON first (most reliable)
        json_data = self._extract_json_data(html_content)

        data = {
            'price': self._extract_price(json_data, text_content),
            'status': self._extract_status(json_data, text_content),
            'dom': self._extract_dom(json_data, text_content),
            'views': self._extract_views(json_data, text_content),
            'saves': self._extract_saves(json_data, text_content),
            'primary_photo': self._extract_photo(json_data, html_content),
        }

        logger.info(f"Zillow extracted: price={data['price']}, status={data['status']}, dom={data['dom']}, photo={'yes' if data['primary_photo'] else 'no'}")
        return data

    def _extract_json_data(self, html: str) -> Dict:
        """Extract JSON data from Zillow's NEXT_DATA script"""
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', html)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return {}

    def _extract_price(self, json_data: Dict, text: str) -> Optional[float]:
        """Extract price from JSON or text"""
        # Try JSON first
        try:
            # Navigate through Zillow's nested structure
            props = json_data.get('props', {}).get('pageProps', {})
            # Various paths where price might be
            price = props.get('property', {}).get('price')
            if price:
                return float(price)
        except (KeyError, TypeError, ValueError):
            pass

        # Fallback to text pattern
        match = re.search(r'\$(\d{1,3}(?:,\d{3})+)', text)
        if match:
            price = int(match.group(1).replace(',', ''))
            if 10000 < price < 50000000:
                return float(price)
        return None

    def _extract_status(self, json_data: Dict, text: str) -> Optional[str]:
        """Extract status from JSON or text"""
        text_lower = text.lower()

        # Check for status keywords in text
        if 'pending' in text_lower[:2000]:
            return 'Pending'
        if 'sold' in text_lower[:2000] and 'last sold' not in text_lower[:2000]:
            return 'Sold'
        if 'off market' in text_lower:
            return 'Off Market'
        if 'for sale' in text_lower or 'active' in text_lower:
            return 'Active'

        return 'Active'

    def _extract_dom(self, json_data: Dict, text: str) -> Optional[int]:
        """Extract days on Zillow"""
        match = re.search(r'(\d+)\s*days?\s*on\s*zillow', text, re.IGNORECASE)
        if match:
            dom = int(match.group(1))
            if 0 < dom < 2000:
                return dom
        return None

    def _extract_views(self, json_data: Dict, text: str) -> Optional[int]:
        """Extract view count"""
        match = re.search(r'([\d,]+)\s*views?', text, re.IGNORECASE)
        if match:
            views = int(match.group(1).replace(',', ''))
            if views > 0:
                return views
        return None

    def _extract_saves(self, json_data: Dict, text: str) -> Optional[int]:
        """Extract save count"""
        match = re.search(r'(\d+)\s*saves?', text, re.IGNORECASE)
        if match:
            saves = int(match.group(1))
            if saves > 0:
                return saves
        return None

    def _extract_photo(self, json_data: Dict, html: str) -> Optional[str]:
        """Extract primary photo URL from Zillow property page"""
        # Method 1: Try NEXT_DATA JSON structure (most reliable)
        try:
            props = json_data.get('props', {}).get('pageProps', {})
            # Path 1: property.media or property.photos
            property_data = props.get('property', {}) or props.get('initialData', {}).get('property', {})

            # Check media array
            media = property_data.get('media', {})
            if isinstance(media, dict):
                photos = media.get('propertyPhotoLinks', []) or media.get('photos', [])
                if photos and isinstance(photos, list) and len(photos) > 0:
                    first_photo = photos[0]
                    if isinstance(first_photo, str):
                        return first_photo
                    elif isinstance(first_photo, dict):
                        url = first_photo.get('url') or first_photo.get('mixedSources', {}).get('jpeg', [{}])[0].get('url')
                        if url:
                            return url

            # Path 2: Check hdpData structure
            hdp_data = props.get('initialReduxState', {}).get('gdp', {}).get('building', {})
            if not hdp_data:
                hdp_data = props.get('componentProps', {}).get('gdpClientCache', {})
                # gdpClientCache is often JSON string keyed by property ID
                if hdp_data:
                    for key, value in hdp_data.items():
                        if isinstance(value, str):
                            try:
                                parsed = json.loads(value)
                                if isinstance(parsed, dict) and 'property' in parsed:
                                    hdp_data = parsed.get('property', {})
                                    break
                            except json.JSONDecodeError:
                                continue

            # Check for responsivePhotos or photos in hdpData
            responsive_photos = hdp_data.get('responsivePhotos', [])
            if responsive_photos and isinstance(responsive_photos, list):
                first = responsive_photos[0]
                if isinstance(first, dict):
                    # Get highest resolution
                    mixed = first.get('mixedSources', {})
                    jpegs = mixed.get('jpeg', [])
                    if jpegs:
                        # Sort by width to get largest
                        jpegs_sorted = sorted(jpegs, key=lambda x: x.get('width', 0), reverse=True)
                        if jpegs_sorted:
                            return jpegs_sorted[0].get('url')
        except (KeyError, TypeError, IndexError, AttributeError):
            pass

        # Method 2: Look for og:image meta tag
        og_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html, re.IGNORECASE)
        if og_match:
            url = og_match.group(1)
            if url.startswith('http'):
                return url

        # Method 3: Look for Zillow CDN image URLs
        zillow_cdn_patterns = [
            r'<img[^>]+src="(https://[^"]*zillowstatic\.com/[^"]+)"',
            r'<img[^>]+data-src="(https://[^"]*zillowstatic\.com/[^"]+)"',
            r'"(https://photos\.zillowstatic\.com/[^"]+)"',
            r'"(https://[^"]*\.zillowstatic\.com/fp/[^"]+\.jpg)"',
        ]
        for pattern in zillow_cdn_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                # Skip thumbnails, icons, logos
                if not any(skip in url.lower() for skip in ['thumb', 'icon', 'logo', 'avatar', '50x50', '100x100']):
                    return url

        # Method 4: Look for JSON-LD structured data
        json_ld_match = re.search(r'<script type="application/ld\+json">([^<]+)</script>', html)
        if json_ld_match:
            try:
                ld_data = json.loads(json_ld_match.group(1))
                if isinstance(ld_data, dict):
                    photo = ld_data.get('image') or ld_data.get('photo')
                    if isinstance(photo, str) and photo.startswith('http'):
                        return photo
                    elif isinstance(photo, list) and photo:
                        first = photo[0]
                        return first if isinstance(first, str) else first.get('url')
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

        return None


# Factory function to get appropriate scraper
def get_scraper(source: str, use_proxy: bool = False, headless: bool = True) -> PlaywrightScraper:
    """Get the appropriate scraper for a source"""
    scrapers = {
        'redfin': RedfinPlaywrightScraper,
        'zillow': ZillowPlaywrightScraper,
    }
    scraper_class = scrapers.get(source.lower(), RedfinPlaywrightScraper)
    return scraper_class(use_proxy=use_proxy, headless=headless)


async def test_scraper():
    """Test the scraper with a sample URL"""
    test_url = "https://www.redfin.com/NC/Sylva/180-Paw-Paw-Cv-28779/home/131919567"

    async with RedfinPlaywrightScraper(use_proxy=False, headless=True) as scraper:
        data = await scraper.fetch_property_data(test_url)
        if data:
            print(f"\n=== Scraped Data ===")
            for key, value in data.items():
                print(f"  {key}: {value}")
        else:
            print("Failed to scrape data")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_scraper())
