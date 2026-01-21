#!/usr/bin/env python3
"""
MLS Opener - Canopy MLS Automation

Opens Canopy MLS Matrix with saved credentials and retrieves listing data by MLS#.
Uses Playwright for browser automation with cookie-based persistent login.

Features:
- Cookie-based persistent login (login once, reuse session)
- Search by MLS number
- Extract detailed listing data (remarks, showing info, agent details)
- Export listing data as JSON

Usage:
    python mls_opener.py --login                     # Initial login (headed mode)
    python mls_opener.py --mls 12345678              # Get listing by MLS#
    python mls_opener.py --mls 12345678 --headed     # View in browser
    python mls_opener.py --mls 12345678 --json       # Output as JSON
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
from typing import Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = PROJECT_ROOT / 'data'
COOKIES_FILE = DATA_DIR / '.canopy_mls_cookies.json'

# Canopy MLS URLs
MLS_LOGIN_URL = "https://matrix.canopymls.com/"
MLS_SEARCH_URL = "https://matrix.canopymls.com/Matrix/Search/ResidentialActive"


class CanopyMLSOpener:
    """Automates Canopy MLS Matrix for listing data retrieval."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        """Start the browser."""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )

        # Create context with saved cookies if available
        if COOKIES_FILE.exists():
            logger.info("Loading saved cookies...")
            with open(COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
            self.context = await self.browser.new_context(
                viewport={'width': 1400, 'height': 900},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            await self.context.add_cookies(cookies)
        else:
            self.context = await self.browser.new_context(
                viewport={'width': 1400, 'height': 900},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

        self.page = await self.context.new_page()
        logger.info("Browser started")

    async def stop(self):
        """Stop the browser."""
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

    async def save_cookies(self):
        """Save current session cookies."""
        cookies = await self.context.cookies()
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f, indent=2)
        logger.info(f"Cookies saved to {COOKIES_FILE}")

    async def login_interactive(self):
        """
        Interactive login - opens browser for user to login manually.
        After login, saves cookies for future headless use.
        """
        logger.info("Opening Canopy MLS login page...")
        logger.info("Please log in manually in the browser window.")
        logger.info("You have 5 minutes to complete login.")

        await self.page.goto(MLS_LOGIN_URL, wait_until='load')

        # Wait for user to complete login
        # Detect successful login by checking for Matrix elements or URL change
        logger.info("Waiting for login completion...")

        try:
            # Poll for login success - check URL and page content
            for _ in range(60):  # Check every 5 seconds for 5 minutes
                await self.page.wait_for_timeout(5000)

                url = self.page.url
                logger.info(f"Current URL: {url}")

                # If we're on a Matrix page (not login), we're logged in
                if 'matrix.canopymls.com/Matrix' in url and 'login' not in url.lower():
                    logger.info("Login successful! Detected Matrix page.")
                    await self.save_cookies()
                    return True

                # Check for common post-login elements
                try:
                    content = await self.page.content()
                    if any(x in content for x in ['Logout', 'Sign Out', 'My Matrix', 'Quick Search', 'Search/Res']):
                        logger.info("Login successful! Detected logged-in content.")
                        await self.save_cookies()
                        return True
                except:
                    pass

            logger.error("Login timeout - 5 minutes elapsed")
            # Save screenshot for debugging
            await self.page.screenshot(path=str(DATA_DIR / 'mls_login_timeout.png'))
            return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            try:
                await self.page.screenshot(path=str(DATA_DIR / 'mls_login_error.png'))
            except:
                pass
            return False

    async def check_login(self) -> bool:
        """Check if we're logged in by visiting the MLS."""
        logger.info("Checking login status...")

        await self.page.goto(MLS_LOGIN_URL, wait_until='load')
        await self.page.wait_for_timeout(3000)

        # Check if we're on the login page or the dashboard
        url = self.page.url
        content = await self.page.content()

        # If we see login form elements, we're not logged in
        if 'login' in url.lower() and 'password' in content.lower():
            logger.info("Not logged in - login required")
            return False

        # If we see Matrix elements, we're logged in
        if 'Matrix' in content or 'Search' in content:
            logger.info("Already logged in")
            return True

        return False

    async def search_by_mls(self, mls_number: str) -> Optional[Dict]:
        """
        Search for a listing by MLS number and extract data.
        """
        logger.info(f"Searching for MLS# {mls_number}...")

        # First check if logged in
        is_logged_in = await self.check_login()
        if not is_logged_in:
            logger.error("Not logged in. Run with --login first.")
            return None

        # Navigate to search page
        await self.page.goto(MLS_SEARCH_URL, wait_until='load')
        await self.page.wait_for_timeout(2000)

        # Look for MLS# search field
        # Matrix typically has a quick search or MLS# field
        try:
            # Try to find and fill MLS number field
            # Common selectors for Matrix MLS search
            mls_selectors = [
                'input[name*="MLSNumber"]',
                'input[name*="mls"]',
                'input[id*="MLSNumber"]',
                'input[id*="mls"]',
                '#Fm1_Ctrl21_LB',  # Common Matrix listing ID field
                'input[placeholder*="MLS"]',
            ]

            mls_input = None
            for selector in mls_selectors:
                try:
                    mls_input = await self.page.wait_for_selector(selector, timeout=3000)
                    if mls_input:
                        break
                except:
                    continue

            if not mls_input:
                # Try using the quick search
                logger.info("Trying quick search...")
                quick_search = await self.page.query_selector('input[id*="QuickSearch"], input[name*="quick"]')
                if quick_search:
                    await quick_search.fill(mls_number)
                    await self.page.keyboard.press('Enter')
                else:
                    logger.error("Could not find MLS search field")
                    # Take screenshot for debugging
                    await self.page.screenshot(path=str(DATA_DIR / 'mls_debug.png'))
                    logger.info(f"Screenshot saved to {DATA_DIR / 'mls_debug.png'}")
                    return None
            else:
                await mls_input.fill(mls_number)

                # Find and click search button
                search_btn = await self.page.query_selector('button[type="submit"], input[type="submit"], .SearchButton, #m_ucSearchButtons_m_lbSearch')
                if search_btn:
                    await search_btn.click()
                else:
                    await self.page.keyboard.press('Enter')

            # Wait for results
            await self.page.wait_for_timeout(3000)

            # Check if we got a single result (listing detail page) or multiple results
            content = await self.page.content()

            # If on listing detail page, extract data
            if 'listing' in self.page.url.lower() or 'detail' in self.page.url.lower():
                return await self._extract_listing_data()

            # If on results page, click first result
            result_link = await self.page.query_selector('.d-text a, .listing-link, .j-ResultsTable a')
            if result_link:
                await result_link.click()
                await self.page.wait_for_timeout(3000)
                return await self._extract_listing_data()

            logger.warning(f"No results found for MLS# {mls_number}")
            return None

        except Exception as e:
            logger.error(f"Error searching MLS: {e}")
            await self.page.screenshot(path=str(DATA_DIR / 'mls_error.png'))
            return None

    async def _extract_listing_data(self) -> Dict:
        """Extract listing data from the current page."""
        logger.info("Extracting listing data...")

        html = await self.page.content()
        text = await self.page.inner_text('body')

        data = {
            'extracted_at': datetime.utcnow().isoformat(),
            'url': self.page.url,
            'mls_number': self._extract_field(html, text, ['MLS#', 'MLS Number', 'Listing ID']),
            'status': self._extract_field(html, text, ['Status']),
            'price': self._extract_price(html, text),
            'address': self._extract_field(html, text, ['Address', 'Property Address']),
            'city': self._extract_field(html, text, ['City']),
            'county': self._extract_field(html, text, ['County']),
            'zip': self._extract_field(html, text, ['Zip', 'Postal Code']),
            'beds': self._extract_field(html, text, ['Beds', 'Bedrooms', 'BR']),
            'baths': self._extract_field(html, text, ['Baths', 'Bathrooms', 'BA']),
            'sqft': self._extract_field(html, text, ['Sq Ft', 'SqFt', 'Square Feet', 'Living Area']),
            'lot_size': self._extract_field(html, text, ['Lot Size', 'Lot Acres', 'Acres']),
            'year_built': self._extract_field(html, text, ['Year Built', 'Yr Built']),
            'property_type': self._extract_field(html, text, ['Property Type', 'Type']),
            'style': self._extract_field(html, text, ['Style', 'Architecture']),
            'subdivision': self._extract_field(html, text, ['Subdivision', 'Community']),

            # Agent/Listing info
            'listing_agent': self._extract_field(html, text, ['Listing Agent', 'Agent Name']),
            'listing_office': self._extract_field(html, text, ['Listing Office', 'Office', 'Brokerage']),
            'agent_phone': self._extract_phone(html, text),
            'agent_email': self._extract_email(html, text),

            # Dates
            'list_date': self._extract_field(html, text, ['List Date', 'Listed']),
            'dom': self._extract_field(html, text, ['DOM', 'Days on Market']),

            # Remarks
            'public_remarks': self._extract_remarks(html, text, 'public'),
            'agent_remarks': self._extract_remarks(html, text, 'agent'),

            # Showing info
            'showing_instructions': self._extract_field(html, text, ['Showing Instructions', 'Showing Info', 'Lockbox']),
            'lockbox_type': self._extract_field(html, text, ['Lockbox Type', 'Lockbox']),

            # Photos
            'photo_count': self._extract_photo_count(html, text),
            'primary_photo': self._extract_primary_photo(html),
        }

        # Clean up None values
        data = {k: v for k, v in data.items() if v is not None}

        return data

    def _extract_field(self, html: str, text: str, labels: List[str]) -> Optional[str]:
        """Extract a field value by its label."""
        for label in labels:
            # Try common patterns
            patterns = [
                rf'{label}[:\s]*([^\n<]+)',
                rf'>{label}</[^>]+>\s*<[^>]+>([^<]+)',
                rf'{label}["\s:]+([^"<\n]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, html + text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value and len(value) < 500:  # Sanity check
                        return value
        return None

    def _extract_price(self, html: str, text: str) -> Optional[str]:
        """Extract listing price."""
        patterns = [
            r'\$[\d,]+(?:\.\d{2})?',
            r'Price[:\s]*\$?([\d,]+)',
            r'List Price[:\s]*\$?([\d,]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html + text)
            if match:
                return match.group(0) if '$' in match.group(0) else f"${match.group(1)}"
        return None

    def _extract_phone(self, html: str, text: str) -> Optional[str]:
        """Extract phone number."""
        pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None

    def _extract_email(self, html: str, text: str) -> Optional[str]:
        """Extract email address."""
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        match = re.search(pattern, html)
        if match:
            return match.group(0).lower()
        return None

    def _extract_remarks(self, html: str, text: str, remark_type: str) -> Optional[str]:
        """Extract remarks/description."""
        patterns = [
            rf'{remark_type}[_\s]*remarks?[:\s]*([^<]+)',
            rf'description[:\s]*([^<]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html + text, re.IGNORECASE)
            if match:
                remarks = match.group(1).strip()
                if len(remarks) > 20:  # Must be substantial
                    return remarks[:2000]  # Limit length
        return None

    def _extract_photo_count(self, html: str, text: str) -> Optional[int]:
        """Extract number of photos."""
        patterns = [
            r'(\d+)\s*photos?',
            r'photos?[:\s]*(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html + text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _extract_primary_photo(self, html: str) -> Optional[str]:
        """Extract primary photo URL."""
        patterns = [
            r'<img[^>]+src="([^"]+)"[^>]*class="[^"]*photo',
            r'<meta\s+property="og:image"\s+content="([^"]+)"',
            r'"primaryPhoto"[:\s]*"([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                if url.startswith('http'):
                    return url
        return None


async def main():
    parser = argparse.ArgumentParser(description='Canopy MLS listing opener and data extractor')
    parser.add_argument('--login', action='store_true', help='Interactive login to save session')
    parser.add_argument('--mls', help='MLS number to search for')
    parser.add_argument('--headed', action='store_true', help='Run browser in visible mode')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Login mode requires headed browser
    headless = not args.headed and not args.login

    async with CanopyMLSOpener(headless=headless) as mls:
        if args.login:
            # Interactive login
            success = await mls.login_interactive()
            if success:
                print("\nLogin successful! Cookies saved.")
                print("You can now use --mls to search listings.")
            else:
                print("\nLogin failed or timed out.")
                sys.exit(1)

        elif args.mls:
            # Search for listing
            data = await mls.search_by_mls(args.mls)

            if data:
                if args.json:
                    print(json.dumps(data, indent=2))
                else:
                    print("\n" + "=" * 60)
                    print(f"MLS# {args.mls} - LISTING DATA")
                    print("=" * 60)
                    for key, value in data.items():
                        if value:
                            # Truncate long values
                            display_val = str(value)[:100] + "..." if len(str(value)) > 100 else value
                            print(f"{key:25} {display_val}")
                    print("=" * 60)
            else:
                print(f"No listing found for MLS# {args.mls}")
                sys.exit(1)

        else:
            parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())
