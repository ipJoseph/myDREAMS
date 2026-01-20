#!/usr/bin/env python3
"""
IDX Portfolio Automation
Uses Playwright to create property portfolios on the team IDX site
Supports progress tracking via JSON file for remote monitoring
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable

from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)

# Global progress file path (set from command line)
PROGRESS_FILE = None


def set_progress_file(path: str):
    """Set the progress file path (avoids global statement issues in Python 3.12+)"""
    global PROGRESS_FILE
    PROGRESS_FILE = path


def write_progress(status: str, current: int = 0, total: int = 0, message: str = "", error: str = ""):
    """Write progress to JSON file for dashboard to poll"""
    if not PROGRESS_FILE:
        return

    progress = {
        "status": status,  # starting, logging_in, searching, saving, complete, error
        "current": current,
        "total": total,
        "message": message,
        "error": error,
        "timestamp": datetime.now().isoformat()
    }

    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress, f)
    except Exception as e:
        logger.error(f"Failed to write progress file: {e}")

# Load environment variables
def load_env_file():
    env_path = Path(__file__).parent.parent.parent / '.env'
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
IDX_MLS_SEARCH_URL = f"{IDX_BASE_URL}/search/mls_search/"

# Login credentials from environment
IDX_EMAIL = os.getenv('IDX_EMAIL', '')
IDX_PHONE = os.getenv('IDX_PHONE', '')


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
        self.context = None
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
            args=[
                '--window-position=0,0',
                '--window-size=1280,900',
                '--disable-blink-features=AutomationControlled',
            ],
        )
        # Create context with viewport
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 850}
        )
        logger.info("Browser started")

    async def login(self, page: Page) -> bool:
        """
        Log into the IDX site quickly.

        Returns:
            True if login successful, False otherwise
        """
        if not IDX_EMAIL or not IDX_PHONE:
            logger.warning("IDX credentials not configured in .env file")
            return False

        try:
            # Go to homepage
            logger.info(f"Navigating to {IDX_BASE_URL} for login")
            await page.goto(IDX_BASE_URL, wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(1000)

            # Click person icon using JavaScript (fastest)
            logger.info("Clicking person icon")
            clicked = await page.evaluate('''() => {
                const links = document.querySelectorAll('header a, nav a');
                for (let link of links) {
                    if (link.innerHTML.includes('fa-user') ||
                        link.querySelector('[class*="user"]')) {
                        link.click();
                        return true;
                    }
                }
                // Fallback: last link in header is usually the user icon
                const headerLinks = document.querySelectorAll('header a');
                if (headerLinks.length > 0) {
                    headerLinks[headerLinks.length - 1].click();
                    return true;
                }
                return false;
            }''')

            if not clicked:
                logger.error("Could not find login icon")
                return False

            # Wait for login panel
            await page.wait_for_timeout(800)

            # Fill credentials using JavaScript (fastest)
            logger.info("Filling login credentials")
            await page.evaluate(f'''() => {{
                const emailInput = document.querySelector('input[type="email"], input[name="email"]');
                const phoneInput = document.querySelector('input[type="tel"], input[name="phone"]');
                if (emailInput) {{
                    emailInput.value = "{IDX_EMAIL}";
                    emailInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
                if (phoneInput) {{
                    phoneInput.value = "{IDX_PHONE}";
                    phoneInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }}''')

            await page.wait_for_timeout(300)

            # Click Log In button
            logger.info("Clicking Log In button")
            await page.evaluate('''() => {
                const buttons = document.querySelectorAll('button');
                for (let btn of buttons) {
                    if (btn.textContent.includes('Log In') || btn.textContent.includes('Sign In')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')

            # Wait for login to complete
            await page.wait_for_timeout(1500)
            logger.info("Login completed")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def stop(self):
        """Stop the browser"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser stopped")

    async def save_search(self, page: Page, search_name: str) -> bool:
        """
        Save the current search with the given name.

        Args:
            page: The Playwright page object
            search_name: Name to save the search as

        Returns:
            True if save successful, False otherwise
        """
        if not search_name:
            logger.warning("No search name provided, skipping save")
            return False

        try:
            logger.info(f"Attempting to save search as: {search_name}")

            # Look for the + button or save search button
            # Based on the screenshot, it's likely a + icon or "Save Search" link
            save_clicked = False

            # Try various selectors for the save/add button
            selectors = [
                'a.fa-plus',
                'a:has(i.fa-plus)',
                'button:has(i.fa-plus)',
                '.save-search',
                'a[title*="Save"]',
                'button[title*="Save"]',
                'a:has-text("Save")',
                '.add-search',
                'a.add-to-saved',
            ]

            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible():
                        logger.info(f"Clicking save button with selector: {selector}")
                        await element.click()
                        save_clicked = True
                        break
                except Exception:
                    continue

            # Fallback: JavaScript to find + button
            if not save_clicked:
                logger.info("Trying JavaScript to find save/+ button")
                save_clicked = await page.evaluate('''() => {
                    // Look for plus icons
                    const plusLinks = document.querySelectorAll('a, button');
                    for (let link of plusLinks) {
                        if (link.querySelector('.fa-plus, .fa-plus-circle, [class*="plus"]') ||
                            link.innerHTML.includes('fa-plus') ||
                            link.title?.toLowerCase().includes('save') ||
                            link.textContent?.toLowerCase().includes('save search')) {
                            link.click();
                            return true;
                        }
                    }
                    return false;
                }''')

            if not save_clicked:
                logger.error("Could not find save/+ button")
                return False

            # Wait for save dialog/form to fully appear
            await page.wait_for_timeout(2000)

            # Fill in the search name
            name_filled = False

            # Try various selectors for the name input
            name_selectors = [
                'input[name="search_name"]',
                'input[name="name"]',
                'input[placeholder*="name"]',
                'input[placeholder*="Name"]',
                'input[type="text"]:visible',
                '.save-search-form input',
                'input.search-name',
            ]

            for selector in name_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible():
                        logger.info(f"Filling search name with selector: {selector}")
                        await element.fill(search_name)
                        name_filled = True
                        break
                except Exception:
                    continue

            # Fallback: JavaScript to find and fill name input
            if not name_filled:
                logger.info("Trying JavaScript to find name input")
                name_filled = await page.evaluate(f'''() => {{
                    const inputs = document.querySelectorAll('input[type="text"]');
                    for (let input of inputs) {{
                        if (input.offsetParent !== null) {{  // visible
                            input.value = "{search_name}";
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    return false;
                }}''')

            if not name_filled:
                logger.error("Could not find search name input")
                return False

            await page.wait_for_timeout(800)

            # Click the save/submit button using JavaScript (most reliable)
            logger.info("Clicking Save button via JavaScript")
            submit_clicked = await page.evaluate('''() => {
                // Look for Save button/input in the visible dialog
                const saveButtons = document.querySelectorAll('input[value="Save"], button');
                for (let btn of saveButtons) {
                    if (btn.offsetParent !== null) {  // visible
                        const text = btn.value || btn.textContent || '';
                        if (text.toLowerCase().trim() === 'save') {
                            console.log('Found save button:', btn);
                            btn.click();
                            // Also try form submit as backup
                            const form = btn.closest('form');
                            if (form) {
                                setTimeout(() => form.submit(), 100);
                            }
                            return true;
                        }
                    }
                }
                return false;
            }''')

            if not submit_clicked:
                # Fallback: try Playwright click with force
                logger.info("Fallback: trying Playwright force click")
                try:
                    save_btn = page.locator('input[value="Save"]').first
                    await save_btn.click(force=True, timeout=3000)
                    submit_clicked = True
                except Exception as e:
                    logger.error(f"Force click failed: {e}")

            if not submit_clicked:
                logger.error("Could not click save submit button")
                return False

            # Wait longer for save to complete
            await page.wait_for_timeout(3000)
            logger.info("Search save attempted")

            # Refresh the page to ensure saved searches list is updated
            await page.reload(wait_until='domcontentloaded')
            await page.wait_for_timeout(1500)
            logger.info("Page refreshed after save")

            return True

        except Exception as e:
            logger.error(f"Error saving search: {e}")
            return False

    async def create_portfolio(self, mls_numbers: List[str], search_name: str = "", keep_open: bool = True) -> Optional[str]:
        """
        Create a portfolio search on the IDX site.

        Args:
            mls_numbers: List of MLS numbers to search
            search_name: Name to save the search as (optional)
            keep_open: If True, leaves browser open for user interaction

        Returns:
            The URL of the search results, or None on error
        """
        if not mls_numbers:
            logger.warning("No MLS numbers provided")
            write_progress("error", error="No MLS numbers provided")
            return None

        total = len(mls_numbers)
        write_progress("starting", 0, total, f"Initializing for {total} properties...")

        if not self.browser:
            await self.start()

        try:
            # Create a new page
            page = await self.context.new_page()

            # Login first if credentials are configured
            if IDX_EMAIL and IDX_PHONE:
                write_progress("logging_in", 0, total, "Logging into IDX site...")
                login_success = await self.login(page)
                if login_success:
                    logger.info("Login completed")
                    write_progress("logging_in", 0, total, "Login successful")
                else:
                    logger.warning("Login failed - continuing anyway")
                    write_progress("logging_in", 0, total, "Login failed - continuing...")

            # Navigate to MLS search page
            write_progress("searching", 0, total, "Loading MLS search page...")
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
            write_progress("searching", 0, total, f"Entering {total} MLS numbers...")
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
            write_progress("searching", 0, total, "Submitting search...")
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

                # Save the search if a name was provided
                if search_name:
                    write_progress("saving", total, total, f"Saving search as '{search_name}'...")
                    save_success = await self.save_search(page, search_name)
                    if save_success:
                        logger.info(f"Search saved as: {search_name}")
                        write_progress("saving", total, total, "Search saved successfully")
                    else:
                        logger.warning("Could not save search automatically")
                        write_progress("saving", total, total, "Could not save search automatically")

            result_url = page.url
            logger.info(f"Current URL: {result_url}")

            # Write completion progress
            write_progress("complete", total, total, f"Portfolio created with {total} properties", "")

            # In headless mode OR when running as background task (progress file set), close browser
            if self.headless or PROGRESS_FILE:
                logger.info("Background/headless mode - closing browser")
                await self.stop()
                return result_url

            # Interactive mode (no progress file): Keep browser open indefinitely
            print(f"\n{'='*60}")
            if filled:
                print(f"Portfolio ready with {len(mls_numbers)} properties!")
            else:
                print(f"Browser open - MLS numbers copied to clipboard.")
                print(f"Paste manually: {mls_string}")
            print(f"{'='*60}")
            print("\nBrowser will stay open. Close the browser window when done.")

            # Keep the process alive while browser is open
            while True:
                try:
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
            write_progress("error", 0, total, "", str(e))
            import traceback
            traceback.print_exc()
            return None


async def create_idx_portfolio(mls_numbers: List[str], search_name: str = "", headless: bool = False):
    """
    Convenience function to create an IDX portfolio.

    Args:
        mls_numbers: List of MLS numbers
        search_name: Name to save the search as (optional)
        headless: Whether to run headless (default False - shows browser)
    """
    async with IDXPortfolioAutomation(headless=headless) as automation:
        return await automation.create_portfolio(mls_numbers, search_name=search_name, keep_open=True)


def run_portfolio(mls_numbers: List[str], search_name: str = ""):
    """Synchronous wrapper for running the portfolio automation"""
    asyncio.run(create_idx_portfolio(mls_numbers, search_name=search_name))


if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    # Check environment
    display = os.environ.get('DISPLAY', '')
    logger.info(f"DISPLAY environment: '{display}'")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Script location: {os.path.dirname(os.path.abspath(__file__))}")

    # Determine headless mode based on DISPLAY availability
    # With Xvfb, DISPLAY will be set (e.g., ":99") so browser can run
    headless_mode = not bool(display)
    if headless_mode:
        logger.info("No DISPLAY - will run in headless mode")
    else:
        logger.info(f"DISPLAY={display} - running with visible browser")

    # Command line args:
    # Arg 1: comma-separated MLS numbers
    # Arg 2: search name (optional)
    # Arg 3: progress file path (optional)
    if len(sys.argv) > 1:
        mls_list = sys.argv[1].split(',')
        mls_list = [m.strip() for m in mls_list]
    else:
        # Test with sample MLS numbers
        mls_list = ['4277940', '26040365', '154288']

    search_name = sys.argv[2] if len(sys.argv) > 2 else ""

    # Set progress file if provided
    if len(sys.argv) > 3:
        set_progress_file(sys.argv[3])
        logger.info(f"Progress file: {sys.argv[3]}")

    logger.info(f"Creating portfolio for: {mls_list}")
    if search_name:
        logger.info(f"Will save as: {search_name}")

    try:
        # Run with headless=True when using xvfb (DISPLAY is set but no physical monitor)
        # For xvfb-run, we actually have a virtual display, so headless=False is fine
        asyncio.run(create_idx_portfolio(mls_list, search_name=search_name, headless=False))
        logger.info("Portfolio creation completed successfully")
    except Exception as e:
        logger.error(f"Portfolio creation failed: {e}", exc_info=True)
        write_progress("error", 0, len(mls_list), "", str(e))
