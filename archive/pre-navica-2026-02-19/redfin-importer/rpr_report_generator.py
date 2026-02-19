#!/usr/bin/env python3
"""
RPR Report Generator - Realtors Property Resource Automation

Automates RPR (narrpr.com) to generate buyer reports and property information packages.
Uses Playwright for browser automation with cookie-based persistent login.

Features:
- Cookie-based persistent login (login once, reuse session)
- Search by address or MLS number
- Generate Buyer Tour reports
- Generate Property Reports
- Download reports as PDF

Usage:
    python rpr_report_generator.py --login                           # Initial login
    python rpr_report_generator.py --address "123 Main St, Franklin NC"  # Search by address
    python rpr_report_generator.py --address "123 Main St" --report buyer  # Generate buyer report
    python rpr_report_generator.py --headed                          # View in browser
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
REPORTS_DIR = DATA_DIR / 'rpr_reports'
COOKIES_FILE = DATA_DIR / '.rpr_cookies.json'

# RPR URLs
RPR_LOGIN_URL = "https://www.narrpr.com/"
RPR_SEARCH_URL = "https://www.narrpr.com/home"


class RPRReportGenerator:
    """Automates RPR for property reports and buyer packages."""

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
            logger.info("Loading saved RPR cookies...")
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

        # Ensure reports directory exists
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

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
        RPR uses NAR SSO (NRDS ID login).
        After login, saves cookies for future headless use.
        """
        logger.info("Opening RPR login page...")
        logger.info("Please log in with your NAR/NRDS credentials.")
        logger.info("The script will save your session after login.")

        await self.page.goto(RPR_LOGIN_URL, wait_until='load')

        # Wait for user to complete login
        # RPR redirects to dashboard after successful login
        logger.info("Waiting for login completion...")
        logger.info("(Looking for RPR dashboard or search box)")

        try:
            # Wait for the search box or dashboard elements that indicate login
            await self.page.wait_for_selector(
                'input[placeholder*="Search"], input[id*="search"], .rpr-search, #searchInput',
                timeout=300000  # 5 minutes to login
            )
            logger.info("Login successful!")

            # Save cookies
            await self.save_cookies()

            return True

        except Exception as e:
            logger.error(f"Login timeout or error: {e}")
            return False

    async def check_login(self) -> bool:
        """Check if we're logged in to RPR."""
        logger.info("Checking RPR login status...")

        await self.page.goto(RPR_SEARCH_URL, wait_until='load')
        await self.page.wait_for_timeout(3000)

        url = self.page.url
        content = await self.page.content()

        # If redirected to login page, we're not logged in
        if 'login' in url.lower() or 'signin' in url.lower():
            logger.info("Not logged in - login required")
            return False

        # If we see search elements, we're logged in
        if 'search' in content.lower() and ('property' in content.lower() or 'rpr' in content.lower()):
            logger.info("Already logged in to RPR")
            return True

        return False

    async def search_property(self, address: str) -> Optional[Dict]:
        """
        Search for a property by address and get property details.
        """
        logger.info(f"Searching RPR for: {address}")

        # Check login
        is_logged_in = await self.check_login()
        if not is_logged_in:
            logger.error("Not logged in to RPR. Run with --login first.")
            return None

        try:
            # Find and use the search box
            search_selectors = [
                'input[placeholder*="Search"]',
                'input[id*="search"]',
                '#searchInput',
                '.rpr-search input',
                'input[type="text"][class*="search"]',
            ]

            search_input = None
            for selector in search_selectors:
                try:
                    search_input = await self.page.wait_for_selector(selector, timeout=5000)
                    if search_input:
                        break
                except:
                    continue

            if not search_input:
                logger.error("Could not find RPR search box")
                await self.page.screenshot(path=str(DATA_DIR / 'rpr_debug.png'))
                return None

            # Clear and type address
            await search_input.click()
            await search_input.fill('')
            await search_input.type(address, delay=50)

            # Wait for autocomplete suggestions
            await self.page.wait_for_timeout(2000)

            # Try to click first suggestion or press Enter
            suggestion = await self.page.query_selector('.autocomplete-suggestion, .search-suggestion, [class*="suggestion"]')
            if suggestion:
                await suggestion.click()
            else:
                await self.page.keyboard.press('Enter')

            # Wait for property page to load
            await self.page.wait_for_timeout(3000)

            # Extract property data
            return await self._extract_property_data()

        except Exception as e:
            logger.error(f"Error searching RPR: {e}")
            await self.page.screenshot(path=str(DATA_DIR / 'rpr_error.png'))
            return None

    async def _extract_property_data(self) -> Dict:
        """Extract property data from RPR property page."""
        logger.info("Extracting RPR property data...")

        html = await self.page.content()
        text = await self.page.inner_text('body')

        data = {
            'extracted_at': datetime.utcnow().isoformat(),
            'source': 'RPR',
            'url': self.page.url,

            # Property basics
            'address': self._extract_field(html, text, ['Address', 'Property Address']),
            'city': self._extract_field(html, text, ['City']),
            'state': self._extract_field(html, text, ['State']),
            'zip': self._extract_field(html, text, ['Zip', 'ZIP']),
            'county': self._extract_field(html, text, ['County']),

            # Property details
            'beds': self._extract_field(html, text, ['Beds', 'Bedrooms']),
            'baths': self._extract_field(html, text, ['Baths', 'Bathrooms']),
            'sqft': self._extract_field(html, text, ['Sq Ft', 'SqFt', 'Living Area']),
            'lot_size': self._extract_field(html, text, ['Lot Size', 'Lot']),
            'year_built': self._extract_field(html, text, ['Year Built']),
            'property_type': self._extract_field(html, text, ['Property Type', 'Type']),

            # Values
            'estimated_value': self._extract_field(html, text, ['Estimated Value', 'RVM', 'Value']),
            'assessed_value': self._extract_field(html, text, ['Assessed Value', 'Tax Value']),
            'last_sale_price': self._extract_field(html, text, ['Last Sale', 'Sale Price']),
            'last_sale_date': self._extract_field(html, text, ['Sale Date']),

            # Owner info
            'owner_name': self._extract_field(html, text, ['Owner', 'Owner Name']),
            'owner_occupied': self._extract_field(html, text, ['Owner Occupied']),

            # APN
            'apn': self._extract_field(html, text, ['APN', 'Parcel', 'Parcel Number']),

            # MLS info if listed
            'mls_status': self._extract_field(html, text, ['MLS Status', 'Status']),
            'list_price': self._extract_field(html, text, ['List Price']),
            'dom': self._extract_field(html, text, ['DOM', 'Days on Market']),
        }

        # Clean up None values
        data = {k: v for k, v in data.items() if v is not None}

        return data

    def _extract_field(self, html: str, text: str, labels: List[str]) -> Optional[str]:
        """Extract a field value by its label."""
        for label in labels:
            patterns = [
                rf'{label}[:\s]*([^\n<]+)',
                rf'>{label}</[^>]+>\s*<[^>]+>([^<]+)',
                rf'{label}["\s:]+([^"<\n]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, html + text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value and len(value) < 200:
                        return value
        return None

    async def generate_buyer_report(self, address: str, buyer_name: str = None) -> Optional[str]:
        """
        Generate a Buyer Report for a property.
        Returns path to downloaded PDF if successful.
        """
        logger.info(f"Generating Buyer Report for: {address}")

        # First search for the property
        property_data = await self.search_property(address)
        if not property_data:
            logger.error("Could not find property")
            return None

        try:
            # Look for "Create Report" or similar button
            report_buttons = [
                'button:has-text("Report")',
                'a:has-text("Report")',
                'button:has-text("Create")',
                '[class*="report"]',
                '#createReport',
            ]

            report_btn = None
            for selector in report_buttons:
                try:
                    report_btn = await self.page.wait_for_selector(selector, timeout=3000)
                    if report_btn:
                        break
                except:
                    continue

            if not report_btn:
                logger.warning("Could not find report button - taking screenshot")
                await self.page.screenshot(path=str(DATA_DIR / 'rpr_report_btn.png'))
                logger.info(f"Screenshot saved to {DATA_DIR / 'rpr_report_btn.png'}")
                logger.info("Please check the screenshot to find the report button manually")
                return None

            await report_btn.click()
            await self.page.wait_for_timeout(2000)

            # Look for "Buyer" report option
            buyer_option = await self.page.query_selector(
                'button:has-text("Buyer"), a:has-text("Buyer"), [class*="buyer"]'
            )
            if buyer_option:
                await buyer_option.click()
                await self.page.wait_for_timeout(2000)

            # Fill buyer name if provided
            if buyer_name:
                name_input = await self.page.query_selector('input[name*="buyer"], input[placeholder*="Buyer"]')
                if name_input:
                    await name_input.fill(buyer_name)

            # Look for generate/download button
            generate_btn = await self.page.query_selector(
                'button:has-text("Generate"), button:has-text("Create"), button:has-text("Download")'
            )
            if generate_btn:
                # Set up download handler
                async with self.page.expect_download(timeout=60000) as download_info:
                    await generate_btn.click()

                download = await download_info.value

                # Save to reports directory
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_address = re.sub(r'[^\w\s-]', '', address)[:50]
                filename = f"RPR_Buyer_{safe_address}_{timestamp}.pdf"
                filepath = REPORTS_DIR / filename

                await download.save_as(str(filepath))
                logger.info(f"Report saved to: {filepath}")

                return str(filepath)

            logger.warning("Could not complete report generation")
            return None

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            await self.page.screenshot(path=str(DATA_DIR / 'rpr_report_error.png'))
            return None

    async def generate_property_report(self, address: str) -> Optional[str]:
        """
        Generate a standard Property Report.
        Returns path to downloaded PDF if successful.
        """
        logger.info(f"Generating Property Report for: {address}")

        # Similar to buyer report but selects "Property" type
        property_data = await self.search_property(address)
        if not property_data:
            return None

        try:
            # Look for report options
            report_btn = await self.page.query_selector(
                'button:has-text("Report"), a:has-text("Report")'
            )
            if report_btn:
                await report_btn.click()
                await self.page.wait_for_timeout(2000)

            # Select Property report
            property_option = await self.page.query_selector(
                'button:has-text("Property"), [class*="property-report"]'
            )
            if property_option:
                await property_option.click()

            # Download
            generate_btn = await self.page.query_selector(
                'button:has-text("Generate"), button:has-text("Download")'
            )
            if generate_btn:
                async with self.page.expect_download(timeout=60000) as download_info:
                    await generate_btn.click()

                download = await download_info.value

                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_address = re.sub(r'[^\w\s-]', '', address)[:50]
                filename = f"RPR_Property_{safe_address}_{timestamp}.pdf"
                filepath = REPORTS_DIR / filename

                await download.save_as(str(filepath))
                logger.info(f"Report saved to: {filepath}")

                return str(filepath)

            return None

        except Exception as e:
            logger.error(f"Error generating property report: {e}")
            return None


async def main():
    parser = argparse.ArgumentParser(description='RPR Report Generator - automates buyer/property reports')
    parser.add_argument('--login', action='store_true', help='Interactive login to save session')
    parser.add_argument('--address', help='Property address to search')
    parser.add_argument('--report', choices=['buyer', 'property'], help='Type of report to generate')
    parser.add_argument('--buyer-name', help='Buyer name for personalized report')
    parser.add_argument('--headed', action='store_true', help='Run browser in visible mode')
    parser.add_argument('--json', action='store_true', help='Output property data as JSON')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Login mode requires headed browser
    headless = not args.headed and not args.login

    async with RPRReportGenerator(headless=headless) as rpr:
        if args.login:
            success = await rpr.login_interactive()
            if success:
                print("\nRPR login successful! Cookies saved.")
                print("You can now use --address to search properties.")
            else:
                print("\nLogin failed or timed out.")
                sys.exit(1)

        elif args.address:
            if args.report == 'buyer':
                filepath = await rpr.generate_buyer_report(args.address, args.buyer_name)
                if filepath:
                    print(f"\nBuyer Report saved: {filepath}")
                else:
                    print("\nCould not generate buyer report")
                    sys.exit(1)

            elif args.report == 'property':
                filepath = await rpr.generate_property_report(args.address)
                if filepath:
                    print(f"\nProperty Report saved: {filepath}")
                else:
                    print("\nCould not generate property report")
                    sys.exit(1)

            else:
                # Just search and show data
                data = await rpr.search_property(args.address)
                if data:
                    if args.json:
                        print(json.dumps(data, indent=2))
                    else:
                        print("\n" + "=" * 60)
                        print("RPR PROPERTY DATA")
                        print("=" * 60)
                        for key, value in data.items():
                            if value:
                                print(f"{key:25} {value}")
                        print("=" * 60)
                else:
                    print(f"No property found for: {args.address}")
                    sys.exit(1)

        else:
            parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())
