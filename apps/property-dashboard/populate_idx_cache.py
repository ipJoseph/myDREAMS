#!/usr/bin/env python3
"""
IDX Property Cache Populator

Scrapes the IDX site to populate the idx_property_cache table
with address information for MLS numbers from FUB events.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment
def load_env():
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip().strip('"').strip("'")

load_env()

IDX_BASE_URL = "https://www.smokymountainhomes4sale.com"
IDX_PROPERTY_URL = f"{IDX_BASE_URL}/property"


async def scrape_idx_property(page, mls_number: str) -> dict:
    """Scrape property details from IDX page."""
    try:
        url = f"{IDX_PROPERTY_URL}/{mls_number}"
        response = await page.goto(url, wait_until='domcontentloaded', timeout=15000)

        if not response or response.status != 200:
            return None

        await page.wait_for_timeout(1500)

        # Extract property info from page
        data = await page.evaluate('''() => {
            const result = { address: null, city: null, price: null, status: null, photo_url: null };

            // Try various selectors for address
            const addressSelectors = [
                '.property-address', '.listing-address', '[class*="address"]',
                'h1', '.property-title', '[data-address]'
            ];
            for (let sel of addressSelectors) {
                const el = document.querySelector(sel);
                if (el && el.textContent.trim()) {
                    const text = el.textContent.trim();
                    // Filter out non-address text
                    if (text.match(/\\d+.*(?:St|Ave|Rd|Dr|Ln|Way|Ct|Blvd|Hwy|Trail|Loop)/i)) {
                        result.address = text.split('\\n')[0].trim();
                        break;
                    }
                }
            }

            // Try to extract city from address or separate element
            if (result.address) {
                const cityMatch = result.address.match(/,\\s*([^,]+),\\s*NC/i);
                if (cityMatch) {
                    result.city = cityMatch[1].trim();
                }
            }

            // Try various selectors for price
            const priceSelectors = [
                '.property-price', '.listing-price', '[class*="price"]',
                '[data-price]'
            ];
            for (let sel of priceSelectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const priceText = el.textContent.replace(/[^0-9]/g, '');
                    if (priceText && priceText.length >= 5) {
                        result.price = parseInt(priceText);
                        break;
                    }
                }
            }

            // Try to get status
            const statusSelectors = [
                '.property-status', '.listing-status', '[class*="status"]'
            ];
            for (let sel of statusSelectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const text = el.textContent.trim().toLowerCase();
                    if (text.includes('active')) result.status = 'Active';
                    else if (text.includes('pending')) result.status = 'Pending';
                    else if (text.includes('sold')) result.status = 'Sold';
                    break;
                }
            }

            // Try to get property photo
            const photoSelectors = [
                '.property-photo img', '.listing-photo img', '.property-image img',
                '.gallery img', '.carousel img', '.slider img',
                '[class*="photo"] img', '[class*="image"] img',
                'img[src*="property"]', 'img[src*="listing"]', 'img[src*="photo"]',
                '.main-image img', '#main-photo img'
            ];
            for (let sel of photoSelectors) {
                const el = document.querySelector(sel);
                if (el && el.src && !el.src.includes('placeholder') && !el.src.includes('no-image')) {
                    // Prefer larger images
                    const src = el.src;
                    if (src.startsWith('http') && (src.includes('.jpg') || src.includes('.jpeg') || src.includes('.png') || src.includes('.webp') || src.includes('resize'))) {
                        result.photo_url = src;
                        break;
                    }
                }
            }

            // Fallback: find any reasonable property image
            if (!result.photo_url) {
                const allImages = document.querySelectorAll('img');
                for (let img of allImages) {
                    const src = img.src || '';
                    const width = img.naturalWidth || img.width || 0;
                    if (src.startsWith('http') && width > 200 &&
                        !src.includes('logo') && !src.includes('icon') && !src.includes('avatar') &&
                        !src.includes('placeholder') && !src.includes('no-image')) {
                        result.photo_url = src;
                        break;
                    }
                }
            }

            return result;
        }''')

        if data and data.get('address'):
            return data
        return None

    except Exception as e:
        logger.debug(f"Error scraping {mls_number}: {e}")
        return None


async def populate_cache(limit: int = 50, batch_size: int = 10):
    """Populate IDX cache for uncached MLS numbers."""
    from src.core.database import DREAMSDatabase

    db_path = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))
    db = DREAMSDatabase(db_path)

    # Get uncached MLS numbers
    uncached = db.get_uncached_mls_numbers(limit=limit)

    if not uncached:
        logger.info("No uncached MLS numbers found")
        return 0

    logger.info(f"Found {len(uncached)} uncached MLS numbers to look up")

    cached_count = 0
    not_found_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context()
        page = await context.new_page()

        for i, mls in enumerate(uncached):
            try:
                logger.info(f"[{i+1}/{len(uncached)}] Looking up MLS# {mls}...")

                data = await scrape_idx_property(page, mls)

                if data and data.get('address'):
                    db.upsert_idx_cache(
                        mls_number=mls,
                        address=data['address'],
                        city=data.get('city'),
                        price=data.get('price'),
                        status=data.get('status'),
                        photo_url=data.get('photo_url')
                    )
                    photo_msg = " (with photo)" if data.get('photo_url') else ""
                    logger.info(f"  ✓ Cached: {data['address']}{photo_msg}")
                    cached_count += 1
                else:
                    # Cache as "not found" to avoid re-checking
                    db.upsert_idx_cache(
                        mls_number=mls,
                        address="[Not found on IDX]"
                    )
                    logger.info(f"  ✗ Not found on IDX")
                    not_found_count += 1

                # Rate limiting
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Error processing MLS# {mls}: {e}")

        await browser.close()

    logger.info(f"\nComplete! Cached: {cached_count}, Not found: {not_found_count}")
    return cached_count


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Populate IDX property cache')
    parser.add_argument('--limit', type=int, default=50, help='Max MLS numbers to process')
    args = parser.parse_args()

    asyncio.run(populate_cache(limit=args.limit))
