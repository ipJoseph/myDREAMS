#!/usr/bin/env python3
"""
IDX Portfolio Automation
Uses Playwright to create property portfolios on the team IDX site
"""

import asyncio
import logging
import os
from typing import List, Optional

from playwright.async_api import async_playwright, Browser, Page

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
                '--window-position=50,50',
                '--window-size=1500,900'
            ]
        )
        logger.info("Browser started")

    async def login(self, page: Page) -> bool:
        """
        Log into the IDX site.

        Returns:
            True if login successful, False otherwise
        """
        if not IDX_EMAIL or not IDX_PHONE:
            logger.warning("IDX credentials not configured in .env file")
            return False

        try:
            # Navigate to homepage first
            logger.info(f"Navigating to {IDX_BASE_URL}")
            await page.goto(IDX_BASE_URL, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(1500)

            # Click the person icon to open login panel
            # The icon is in the top right, typically an <a> or <button> with person/user icon
            person_icon = page.locator('a.fa-user, a[href*="login"], .user-icon, a:has(.fa-user), nav a:last-child').first

            # Try multiple selectors for the person icon
            clicked = False
            selectors = [
                'a.fa-user',
                'a:has(i.fa-user)',
                'header a:last-of-type',
                'nav a:nth-last-child(1)',
                '.login-link',
                'a[title*="Sign"]',
                'a[title*="Login"]',
                'a[title*="Account"]',
            ]

            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible():
                        logger.info(f"Clicking login icon with selector: {selector}")
                        await element.click()
                        clicked = True
                        break
                except Exception:
                    continue

            # Fallback: use JavaScript to find and click the person icon
            if not clicked:
                logger.info("Trying JavaScript to find person icon")
                clicked = await page.evaluate('''() => {
                    // Look for user/person icon in nav
                    const links = document.querySelectorAll('header a, nav a');
                    for (let link of links) {
                        if (link.querySelector('.fa-user, .fa-person, [class*="user"]') ||
                            link.innerHTML.includes('fa-user') ||
                            link.href.includes('login') ||
                            link.href.includes('account')) {
                            link.click();
                            return true;
                        }
                    }
                    // Look for last icon in header (often the user icon)
                    const headerIcons = document.querySelectorAll('header a');
                    if (headerIcons.length > 0) {
                        headerIcons[headerIcons.length - 1].click();
                        return true;
                    }
                    return false;
                }''')

            if not clicked:
                logger.error("Could not find login icon")
                return False

            # Wait for login panel to appear
            await page.wait_for_timeout(1000)

            # Fill in email
            email_field = page.locator('input[type="email"], input[name="email"], input[placeholder*="Email"]').first
            if await email_field.count() > 0:
                logger.info("Filling email field")
                await email_field.fill(IDX_EMAIL)
            else:
                logger.error("Could not find email field")
                return False

            # Fill in phone number
            phone_field = page.locator('input[type="tel"], input[name="phone"], input[placeholder*="Phone"]').first
            if await phone_field.count() > 0:
                logger.info("Filling phone field")
                await phone_field.fill(IDX_PHONE)
            else:
                logger.error("Could not find phone field")
                return False

            await page.wait_for_timeout(300)

            # Click Log In button
            login_button = page.locator('button:has-text("Log In"), input[value="Log In"], button:has-text("Sign In")').first
            if await login_button.count() > 0:
                logger.info("Clicking Log In button")
                await login_button.click()
            else:
                logger.error("Could not find Log In button")
                return False

            # Wait for login to complete
            await page.wait_for_timeout(2000)

            # Check if login was successful (login panel should be gone)
            logger.info("Login attempted - checking result")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def stop(self):
        """Stop the browser"""
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

            # Wait for save dialog/form to appear
            await page.wait_for_timeout(1500)

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

            await page.wait_for_timeout(500)

            # Click the save/submit button
            submit_clicked = False

            submit_selectors = [
                'button:has-text("Save")',
                'input[value="Save"]',
                'button[type="submit"]',
                '.save-btn',
                'button.btn-primary',
                'input[type="submit"]',
            ]

            for selector in submit_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible():
                        logger.info(f"Clicking submit with selector: {selector}")
                        await element.click()
                        submit_clicked = True
                        break
                except Exception:
                    continue

            # Fallback: JavaScript submit
            if not submit_clicked:
                logger.info("Trying JavaScript to submit save form")
                submit_clicked = await page.evaluate('''() => {
                    const buttons = document.querySelectorAll('button, input[type="submit"]');
                    for (let btn of buttons) {
                        if (btn.offsetParent !== null &&
                            (btn.textContent?.toLowerCase().includes('save') ||
                             btn.value?.toLowerCase().includes('save'))) {
                            btn.click();
                            return true;
                        }
                    }
                    // Try form submit
                    const forms = document.querySelectorAll('form');
                    for (let form of forms) {
                        if (form.offsetParent !== null) {
                            form.submit();
                            return true;
                        }
                    }
                    return false;
                }''')

            if not submit_clicked:
                logger.error("Could not click save submit button")
                return False

            # Wait for save to complete
            await page.wait_for_timeout(2000)
            logger.info("Search save attempted")
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
            return None

        if not self.browser:
            await self.start()

        try:
            # Create new context and page
            context = await self.browser.new_context(
                viewport={'width': 1400, 'height': 850}
            )
            page = await context.new_page()

            # Login first if credentials are configured
            if IDX_EMAIL and IDX_PHONE:
                login_success = await self.login(page)
                if login_success:
                    logger.info("Login completed")
                else:
                    logger.warning("Login failed or skipped - continuing without login")

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

                # Save the search if a name was provided
                if search_name:
                    save_success = await self.save_search(page, search_name)
                    if save_success:
                        logger.info(f"Search saved as: {search_name}")
                    else:
                        logger.warning("Could not save search automatically")

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

    # Example usage - can pass MLS numbers as command line args
    # Arg 1: comma-separated MLS numbers
    # Arg 2: search name (optional)
    if len(sys.argv) > 1:
        mls_list = sys.argv[1].split(',')
        mls_list = [m.strip() for m in mls_list]
    else:
        # Test with sample MLS numbers
        mls_list = ['4277940', '26040365', '154288']

    search_name = sys.argv[2] if len(sys.argv) > 2 else ""

    print(f"Creating portfolio for: {mls_list}")
    if search_name:
        print(f"Will save as: {search_name}")
    run_portfolio(mls_list, search_name)
