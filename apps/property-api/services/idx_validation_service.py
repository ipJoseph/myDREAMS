"""
IDX Validation Service

Background service that validates property MLS numbers against the IDX site.
Falls back to address search if MLS# not found.
"""

import asyncio
import threading
import time
import logging
import os
import re
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

from playwright.async_api import async_playwright, Browser

logger = logging.getLogger(__name__)

# Load environment variables
def load_env_file():
    env_path = '/home/bigeug/myDREAMS/.env'
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value

load_env_file()

# IDX Site configuration
IDX_BASE_URL = "https://www.smokymountainhomes4sale.com"
IDX_PROPERTY_URL = f"{IDX_BASE_URL}/property"


class IDXValidationService:
    """
    Validates property MLS numbers against the IDX site.
    Runs as a background thread.
    """

    def __init__(self, db):
        """
        Initialize the validation service.

        Args:
            db: DREAMSDatabase instance
        """
        self.db = db
        self._validation_thread = None
        self._stop_event = threading.Event()
        self._loop = None

    def start_background_validation(self, interval_seconds: int = 300):
        """Start background validation thread (default: every 5 minutes)."""
        def validation_loop():
            # Create event loop for this thread
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            while not self._stop_event.is_set():
                try:
                    count = self._loop.run_until_complete(self.validate_pending_properties())
                    if count > 0:
                        logger.info(f"Validated {count} properties on IDX")
                except Exception as e:
                    logger.error(f"IDX validation error: {e}")

                # Wait for interval or stop signal
                self._stop_event.wait(interval_seconds)

            self._loop.close()

        self._validation_thread = threading.Thread(target=validation_loop, daemon=True)
        self._validation_thread.start()
        logger.info(f"IDX validation service started (interval: {interval_seconds}s)")

    def stop(self):
        """Stop the background validation thread."""
        self._stop_event.set()
        if self._validation_thread:
            self._validation_thread.join(timeout=10)

    async def validate_pending_properties(self, limit: int = 10) -> int:
        """
        Validate all pending properties against IDX.

        Args:
            limit: Maximum number of properties to process per cycle

        Returns:
            Number of properties processed
        """
        pending = self.db.get_properties_by_idx_validation_status('pending', limit=limit)

        if not pending:
            return 0

        processed_count = 0
        playwright = None
        browser = None

        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context()
            page = await context.new_page()

            for prop in pending:
                try:
                    result = await self._validate_property(page, prop)

                    if result['found']:
                        self.db.update_idx_validation(
                            property_id=prop['id'],
                            status='validated',
                            idx_mls_number=result.get('idx_mls_number'),
                            idx_mls_source=result.get('idx_mls_source'),
                            original_mls_number=prop.get('mls_number')
                        )
                        logger.info(f"Validated property {prop['id']}: {prop.get('address')} - IDX MLS# {result.get('idx_mls_number')}")
                    else:
                        self.db.update_idx_validation(
                            property_id=prop['id'],
                            status='not_found'
                        )
                        logger.info(f"Property not found on IDX: {prop['id']}: {prop.get('address')}")

                    processed_count += 1

                except Exception as e:
                    logger.error(f"Error validating property {prop['id']}: {e}")
                    self.db.update_idx_validation(
                        property_id=prop['id'],
                        status='error'
                    )

                # Rate limiting between requests
                await asyncio.sleep(2)

        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

        return processed_count

    async def _validate_property(self, page, prop: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a single property against IDX.

        First tries MLS# lookup, then falls back to address search.

        Args:
            page: Playwright page object
            prop: Property dict from database

        Returns:
            Dict with 'found', 'idx_mls_number', 'idx_mls_source'
        """
        mls_number = prop.get('mls_number')
        address = prop.get('address')
        city = prop.get('city')

        # Strategy 1: Try direct MLS# lookup
        if mls_number:
            result = await self._check_mls_number(page, mls_number)
            if result['found']:
                return result

        # Strategy 2: Fall back to address search
        if address:
            result = await self._search_by_address(page, address, city)
            if result['found']:
                return result

        return {'found': False}

    async def _check_mls_number(self, page, mls_number: str) -> Dict[str, Any]:
        """
        Check if an MLS# exists on the IDX site.

        Args:
            page: Playwright page object
            mls_number: MLS number to check

        Returns:
            Dict with 'found', 'idx_mls_number', 'idx_mls_source'
        """
        try:
            url = f"{IDX_PROPERTY_URL}/{mls_number}"
            response = await page.goto(url, wait_until='domcontentloaded', timeout=15000)

            # Check if page loaded successfully (not a 404 or redirect to search)
            if response and response.status == 200:
                # Wait for page to render
                await page.wait_for_timeout(1000)

                # Check if we're on a valid property page
                is_property_page = await page.evaluate('''() => {
                    // Check for property-specific elements
                    const hasPrice = document.querySelector('[class*="price"], .listing-price, .property-price');
                    const hasAddress = document.querySelector('[class*="address"], .property-address');
                    const hasDetails = document.querySelector('[class*="detail"], .property-info, .listing-detail');

                    // Check we're not on a search/error page
                    const isSearchPage = window.location.pathname.includes('search');
                    const is404 = document.body.innerText.includes('not found') ||
                                 document.body.innerText.includes('no longer available');

                    return (hasPrice || hasAddress || hasDetails) && !isSearchPage && !is404;
                }''')

                if is_property_page:
                    # Try to extract MLS source from the page
                    idx_mls_source = await self._extract_mls_source(page)

                    return {
                        'found': True,
                        'idx_mls_number': mls_number,
                        'idx_mls_source': idx_mls_source
                    }

            return {'found': False}

        except Exception as e:
            logger.debug(f"MLS check failed for {mls_number}: {e}")
            return {'found': False}

    async def _search_by_address(self, page, address: str, city: str = None) -> Dict[str, Any]:
        """
        Search for a property by address on the IDX site.

        Args:
            page: Playwright page object
            address: Property street address
            city: Property city (optional)

        Returns:
            Dict with 'found', 'idx_mls_number', 'idx_mls_source'
        """
        try:
            # Build search query
            search_query = address
            if city:
                search_query = f"{address}, {city}"

            # Navigate to the search page
            search_url = f"{IDX_BASE_URL}/search?q={search_query.replace(' ', '+')}"
            await page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(2000)

            # Try to find an exact address match in results
            result = await page.evaluate(f'''() => {{
                const searchAddress = "{address.lower()}";

                // Look for property cards/links
                const propertyLinks = document.querySelectorAll('a[href*="/property/"]');

                for (let link of propertyLinks) {{
                    // Check if address text matches
                    const linkText = (link.textContent || '').toLowerCase();
                    const parentText = (link.closest('.property-card, .listing, [class*="property"]')?.textContent || '').toLowerCase();

                    if (linkText.includes(searchAddress) || parentText.includes(searchAddress)) {{
                        // Extract MLS number from URL
                        const href = link.href || link.getAttribute('href');
                        const mlsMatch = href.match(/\\/property\\/([A-Za-z0-9]+)/);
                        if (mlsMatch) {{
                            return {{ found: true, mlsNumber: mlsMatch[1] }};
                        }}
                    }}
                }}

                return {{ found: false }};
            }}''')

            if result.get('found'):
                idx_mls_number = result.get('mlsNumber')

                # Visit the property page to get MLS source
                await page.goto(f"{IDX_PROPERTY_URL}/{idx_mls_number}", wait_until='domcontentloaded', timeout=15000)
                await page.wait_for_timeout(1000)

                idx_mls_source = await self._extract_mls_source(page)

                return {
                    'found': True,
                    'idx_mls_number': idx_mls_number,
                    'idx_mls_source': idx_mls_source
                }

            return {'found': False}

        except Exception as e:
            logger.debug(f"Address search failed for {address}: {e}")
            return {'found': False}

    async def _extract_mls_source(self, page) -> Optional[str]:
        """
        Extract the MLS source (CSAOR, Canopy, HCMLS) from a property page.

        Args:
            page: Playwright page object on a property detail page

        Returns:
            MLS source name or None
        """
        try:
            source = await page.evaluate('''() => {
                const text = document.body.innerText;

                // Common MLS sources for the region
                const sources = [
                    { name: 'CSAOR', patterns: ['CSAOR', 'Cherokee/Smoky Mountain', 'Cherokee Smoky'] },
                    { name: 'Canopy', patterns: ['Canopy MLS', 'Canopy Realtor'] },
                    { name: 'HCMLS', patterns: ['HCMLS', 'Highlands-Cashiers'] },
                    { name: 'GAMLS', patterns: ['GAMLS', 'Georgia MLS'] },
                    { name: 'NGMLS', patterns: ['NGMLS', 'Northeast Georgia'] }
                ];

                for (let source of sources) {
                    for (let pattern of source.patterns) {
                        if (text.includes(pattern)) {
                            return source.name;
                        }
                    }
                }

                // Try to find it in meta tags or data attributes
                const mlsElement = document.querySelector('[data-mls-source], [class*="mls-source"]');
                if (mlsElement) {
                    return mlsElement.textContent || mlsElement.getAttribute('data-mls-source');
                }

                return null;
            }''')

            return source

        except Exception:
            return None

    async def validate_single_property(self, property_id: str) -> Dict[str, Any]:
        """
        Validate a single property by ID (for manual triggering).

        Args:
            property_id: Property ID to validate

        Returns:
            Dict with validation result
        """
        prop = self.db.get_property(property_id)
        if not prop:
            return {'success': False, 'error': 'Property not found'}

        playwright = None
        browser = None

        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context()
            page = await context.new_page()

            result = await self._validate_property(page, prop)

            if result['found']:
                self.db.update_idx_validation(
                    property_id=property_id,
                    status='validated',
                    idx_mls_number=result.get('idx_mls_number'),
                    idx_mls_source=result.get('idx_mls_source'),
                    original_mls_number=prop.get('mls_number')
                )
                return {
                    'success': True,
                    'status': 'validated',
                    'idx_mls_number': result.get('idx_mls_number'),
                    'idx_mls_source': result.get('idx_mls_source')
                }
            else:
                self.db.update_idx_validation(
                    property_id=property_id,
                    status='not_found'
                )
                return {
                    'success': True,
                    'status': 'not_found'
                }

        except Exception as e:
            logger.error(f"Error validating property {property_id}: {e}")
            self.db.update_idx_validation(
                property_id=property_id,
                status='error'
            )
            return {'success': False, 'error': str(e)}

        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
