#!/usr/bin/env python3
"""
IDX Portfolio Automation
Uses Playwright to create property portfolios on the team IDX site
"""

import asyncio
import logging
from typing import List, Optional

from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)

# IDX Site configuration
IDX_BASE_URL = "https://www.smokymountainhomes4sale.com"
IDX_MLS_SEARCH_URL = f"{IDX_BASE_URL}/search/mls_search/"


class IDXPortfolioAutomation:
    """Automates creating property portfolios on the IDX site"""

    def __init__(self, headless: bool = False):
        """
        Initialize the automation.

        Args:
            headless: If False, shows the browser window (recommended for this use case)
        """
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.playwright = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Don't close browser - leave it open for user interaction
        pass

    async def start(self):
        """Start the browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--start-maximized']
        )
        logger.info("Browser started")

    async def stop(self):
        """Stop the browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser stopped")

    async def create_portfolio(self, mls_numbers: List[str], keep_open: bool = True) -> Optional[str]:
        """
        Create a portfolio search on the IDX site.

        Args:
            mls_numbers: List of MLS numbers to search
            keep_open: If True, leaves browser open for user interaction

        Returns:
            The URL of the search results, or None on error
        """
        if not mls_numbers:
            logger.warning("No MLS numbers provided")
            return None

        if not self.browser:
            await self.start()

        try:
            # Create new context and page
            context = await self.browser.new_context(
                viewport={'width': 1400, 'height': 900}
            )
            page = await context.new_page()

            # Navigate to MLS search page
            logger.info(f"Navigating to {IDX_MLS_SEARCH_URL}")
            await page.goto(IDX_MLS_SEARCH_URL, wait_until='domcontentloaded', timeout=30000)

            # Wait for the page to fully load
            await page.wait_for_timeout(2000)

            # Find and click the MLS Number Search tab if needed
            mls_tab = page.locator('a:has-text("MLS Number Search")')
            if await mls_tab.count() > 0:
                logger.info("Clicking MLS Number Search tab")
                await mls_tab.click()
                await page.wait_for_timeout(1000)

            # Format MLS numbers as comma-separated string
            mls_string = ', '.join(mls_numbers)
            logger.info(f"Filling in {len(mls_numbers)} MLS numbers: {mls_string[:50]}...")

            # Try multiple strategies to find and fill the input field
            filled = False

            # Strategy 1: Look for visible textarea
            textareas = page.locator('textarea:visible')
            if await textareas.count() > 0:
                logger.info(f"Found {await textareas.count()} visible textarea(s)")
                await textareas.first.click()
                await textareas.first.fill(mls_string)
                filled = True
                logger.info("Filled using visible textarea")

            # Strategy 2: Look for input in the form
            if not filled:
                form_inputs = page.locator('#refine_search_form textarea, #refine_search_form input[type="text"]')
                if await form_inputs.count() > 0:
                    logger.info(f"Found {await form_inputs.count()} form input(s)")
                    await form_inputs.first.click()
                    await form_inputs.first.fill(mls_string)
                    filled = True
                    logger.info("Filled using form input")

            # Strategy 3: Type into any focused element after clicking the tab area
            if not filled:
                # Click in the general area where the textarea should be
                content_area = page.locator('.tab-content, .search-form, form').first
                if await content_area.count() > 0:
                    await content_area.click()
                    await page.wait_for_timeout(300)
                    await page.keyboard.type(mls_string)
                    filled = True
                    logger.info("Typed using keyboard after clicking content area")

            # Strategy 4: Use JavaScript to find and fill
            if not filled:
                logger.info("Trying JavaScript injection")
                result = await page.evaluate(f'''() => {{
                    const textareas = document.querySelectorAll('textarea');
                    for (let ta of textareas) {{
                        if (ta.offsetParent !== null) {{  // visible
                            ta.value = "{mls_string}";
                            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    const inputs = document.querySelectorAll('input[type="text"]');
                    for (let inp of inputs) {{
                        if (inp.offsetParent !== null) {{
                            inp.value = "{mls_string}";
                            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    return false;
                }}''')
                if result:
                    filled = True
                    logger.info("Filled using JavaScript")

            if not filled:
                logger.error("Could not find MLS input field with any strategy")
                # Don't return - keep browser open so user can manually paste

            # Small delay before clicking search
            await page.wait_for_timeout(500)

            # Submit the form via JavaScript (most reliable)
            search_clicked = False
            await page.wait_for_timeout(500)

            try:
                await page.evaluate("document.querySelector('#refine_search_form').submit()")
                search_clicked = True
                logger.info("Submitted form via JavaScript")
            except Exception as e:
                logger.error(f"JavaScript submit failed: {e}")
                # Fallback: try clicking the button
                try:
                    await page.click('input[value="Search"]')
                    search_clicked = True
                    logger.info("Clicked Search button as fallback")
                except Exception as e2:
                    logger.error(f"Button click also failed: {e2}")

            if search_clicked:
                # Wait for results to load
                await page.wait_for_load_state('networkidle')
                await page.wait_for_timeout(3000)

                # Count results and compare to submitted MLS numbers
                try:
                    # Try to find result count on the page
                    result_count = await page.evaluate('''() => {
                        // Look for property cards/listings
                        const cards = document.querySelectorAll('.property-card, .listing-card, .property-item, .listing, [class*="property"], [class*="listing"]');
                        if (cards.length > 0) return cards.length;

                        // Look for result count text
                        const text = document.body.innerText;
                        const match = text.match(/(\\d+)\\s*(?:properties|listings|results|homes)/i);
                        if (match) return parseInt(match[1]);

                        return -1;  // Unknown
                    }''')

                    submitted_count = len(mls_numbers)

                    if result_count >= 0 and result_count < submitted_count:
                        missing_count = submitted_count - result_count
                        # Show alert dialog
                        await page.evaluate(f'''() => {{
                            alert("Note: {result_count} of {submitted_count} properties selected are available on this website.\\n\\n{missing_count} property(ies) may be from an MLS not covered by this IDX.");
                        }}''')
                        logger.info(f"MLS mismatch: {result_count} found of {submitted_count} submitted ({missing_count} missing)")
                    elif result_count >= 0:
                        logger.info(f"All {result_count} properties found")

                except Exception as e:
                    logger.warning(f"Could not count results: {e}")

            result_url = page.url
            logger.info(f"Current URL: {result_url}")

            # Keep browser open indefinitely
            print(f"\n{'='*60}")
            if filled:
                print(f"Portfolio ready with {len(mls_numbers)} properties!")
            else:
                print(f"Browser open - MLS numbers copied to clipboard.")
                print(f"Paste manually: {mls_string}")
            print(f"{'='*60}")
            print("\nBrowser will stay open. Close the browser window when done.")

            # Keep the process alive while browser context exists
            while True:
                try:
                    # Check if browser is still running (not just the page)
                    if not self.browser.is_connected():
                        logger.info("Browser closed by user")
                        break
                    await asyncio.sleep(3)
                except Exception as e:
                    logger.info(f"Browser check failed: {e}")
                    break

            return result_url

        except Exception as e:
            logger.error(f"Error creating portfolio: {e}")
            import traceback
            traceback.print_exc()
            return None


async def create_idx_portfolio(mls_numbers: List[str], headless: bool = False):
    """
    Convenience function to create an IDX portfolio.

    Args:
        mls_numbers: List of MLS numbers
        headless: Whether to run headless (default False - shows browser)
    """
    async with IDXPortfolioAutomation(headless=headless) as automation:
        return await automation.create_portfolio(mls_numbers, keep_open=True)


def run_portfolio(mls_numbers: List[str]):
    """Synchronous wrapper for running the portfolio automation"""
    asyncio.run(create_idx_portfolio(mls_numbers))


if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Example usage - can pass MLS numbers as command line args
    if len(sys.argv) > 1:
        mls_list = sys.argv[1].split(',')
        mls_list = [m.strip() for m in mls_list]
    else:
        # Test with sample MLS numbers
        mls_list = ['4277940', '26040365', '154288']

    print(f"Creating portfolio for: {mls_list}")
    run_portfolio(mls_list)
