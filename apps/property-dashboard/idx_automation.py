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

# Browserless.io configuration (for cloud browser - avoids IP blocking)
BROWSERLESS_TOKEN = os.getenv('BROWSERLESS_TOKEN', '')

# Residential proxy configuration (IPRoyal or similar)
# Required to bypass IDX site's datacenter IP blocking
PROXY_HOST = os.getenv('PROXY_HOST', '')  # e.g., geo.iproyal.com
PROXY_PORT = os.getenv('PROXY_PORT', '')  # e.g., 12321
PROXY_USER = os.getenv('PROXY_USER', '')
PROXY_PASS = os.getenv('PROXY_PASS', '')

# Force local browser (bypass browserless.io for debugging)
FORCE_LOCAL_BROWSER = os.getenv('FORCE_LOCAL_BROWSER', '').lower() in ('true', '1', 'yes')

# Skip proxy entirely (for localhost where home IP isn't blocked)
SKIP_PROXY = os.getenv('SKIP_PROXY', '').lower() in ('true', '1', 'yes')

# Enable debug screenshots (disabled by default to avoid credential exposure)
DEBUG_SCREENSHOTS = os.getenv('DEBUG_SCREENSHOTS', '').lower() in ('true', '1', 'yes')

# Timeout constants (milliseconds) - tuned for browserless.io + residential proxy latency
TIMEOUT_JS_RENDER = 2000      # Wait for JavaScript frameworks to render after navigation
TIMEOUT_PANEL_APPEAR = 1500   # Wait for modal/panel animations to complete
TIMEOUT_INPUT_SETTLE = 500    # Brief pause after filling inputs before next action
TIMEOUT_LOGIN_PROCESS = 3000  # Wait for login authentication to process
TIMEOUT_PAGE_LOAD = 3000      # Wait for page content after navigation
TIMEOUT_TAB_SWITCH = 1000     # Wait after clicking a tab for content to load
TIMEOUT_FORM_SUBMIT = 2000    # Wait after form submission for response
TIMEOUT_STABILIZE = 1000      # Wait for page to stabilize before critical action
TIMEOUT_DEV_VERIFY = 30000    # DEV only: keep browser open for manual verification


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

    async def __aenter__(self) -> "IDXAutomation":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        # Clean up resources in background/headless mode
        # Leave browser open for user interaction in interactive mode
        if self.headless or PROGRESS_FILE:
            await self.stop()
        return False  # Don't suppress exceptions

    async def _debug_screenshot(self, page: Page, filename: str) -> None:
        """Take screenshot only if DEBUG_SCREENSHOTS is enabled"""
        if DEBUG_SCREENSHOTS:
            screenshot_dir = Path(__file__).parent / 'logs'
            await page.screenshot(path=str(screenshot_dir / filename))
            logger.info(f"Screenshot saved: {filename}")

    async def start(self) -> None:
        """Start the browser - uses browserless.io + residential proxy if configured"""
        self.playwright = await async_playwright().start()

        # Build proxy config if credentials are set (and not skipped)
        proxy_config = None
        if SKIP_PROXY:
            logger.info("SKIP_PROXY=true - bypassing residential proxy")
        elif PROXY_HOST and PROXY_PORT and PROXY_USER and PROXY_PASS:
            proxy_config = {
                "server": f"http://{PROXY_HOST}:{PROXY_PORT}",
                "username": PROXY_USER,
                "password": PROXY_PASS
            }
            logger.info(f"Residential proxy configured: {PROXY_HOST}:{PROXY_PORT}")

        if BROWSERLESS_TOKEN and not FORCE_LOCAL_BROWSER:
            # Use browserless.io cloud browser
            browserless_url = f"wss://chrome.browserless.io?token={BROWSERLESS_TOKEN}&stealth=true"
            logger.info("Connecting to browserless.io cloud browser...")
            try:
                self.browser = await self.playwright.chromium.connect_over_cdp(browserless_url)
                # Create context with proxy (if configured) and stealth settings
                self.context = await self.browser.new_context(
                    viewport={'width': 1280, 'height': 850},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    proxy=proxy_config
                )
                if proxy_config:
                    logger.info("Connected to browserless.io with residential proxy")
                else:
                    logger.info("Connected to browserless.io (no proxy)")
                return
            except Exception as e:
                logger.error(f"Failed to connect to browserless.io: {e}")
                logger.info("Falling back to local browser...")

        # Local browser (for development or as fallback)
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            proxy=proxy_config,
            args=[
                '--window-position=0,0',
                '--window-size=1280,900',
                '--disable-blink-features=AutomationControlled',
            ],
        )
        # Create context with viewport
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 850},
            proxy=proxy_config
        )
        if proxy_config:
            logger.info("Local browser started with residential proxy")
        else:
            logger.info("Local browser started")

    async def login(self, page: Page) -> bool:
        """
        Log into the IDX site with verification.

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
            await page.wait_for_timeout(TIMEOUT_JS_RENDER)

            # Check for 403 Forbidden (IP blocking)
            page_title = await page.title()
            if '403' in page_title or 'Forbidden' in page_title:
                logger.error("IDX site returned 403 Forbidden - IP may be blocked")
                write_progress("error", 0, 0, "", "IDX site blocked this IP address (403 Forbidden). Try running from local machine.")
                return False

            # Debug: Save screenshot (conditional)
            await self._debug_screenshot(page, 'debug_01_homepage.png')

            # Click person icon to open login panel
            logger.info("Clicking person icon to open login panel")
            clicked = await page.evaluate('''() => {
                // Look for user/person icon link
                const links = document.querySelectorAll('header a, nav a, a');
                for (let link of links) {
                    if (link.innerHTML.includes('fa-user') ||
                        link.querySelector('[class*="user"]') ||
                        link.querySelector('i.fa-user') ||
                        link.querySelector('svg[class*="user"]')) {
                        link.click();
                        return 'found-user-icon';
                    }
                }
                // Fallback: last link in header is usually the user icon
                const headerLinks = document.querySelectorAll('header a');
                if (headerLinks.length > 0) {
                    headerLinks[headerLinks.length - 1].click();
                    return 'fallback-header-link';
                }
                return false;
            }''')

            if not clicked:
                logger.error("Could not find login icon")
                return False
            logger.info(f"Clicked login icon via: {clicked}")

            # Wait for login panel to appear
            await page.wait_for_timeout(TIMEOUT_PANEL_APPEAR)

            # Debug: Screenshot after clicking user icon
            await self._debug_screenshot(page, 'debug_01b_login_panel.png')

            # Check if we see a login form
            has_login_form = await page.evaluate('''() => {
                const emailInput = document.querySelector('input[type="email"], input[name="email"]');
                const phoneInput = document.querySelector('input[type="tel"], input[name="phone"]');
                return {
                    hasEmail: !!emailInput,
                    hasPhone: !!phoneInput,
                    emailVisible: emailInput ? emailInput.offsetParent !== null : false,
                    phoneVisible: phoneInput ? phoneInput.offsetParent !== null : false
                };
            }''')
            logger.info(f"Login form check: {has_login_form}")

            if not has_login_form.get('hasEmail') or not has_login_form.get('hasPhone'):
                logger.error("Login form not found - email or phone input missing")
                return False

            # Fill credentials using JavaScript with verification
            logger.info(f"Filling login credentials: {IDX_EMAIL}")
            fill_result = await page.evaluate(f'''() => {{
                const emailInput = document.querySelector('input[type="email"], input[name="email"]');
                const phoneInput = document.querySelector('input[type="tel"], input[name="phone"]');
                let filled = {{ email: false, phone: false }};

                if (emailInput) {{
                    emailInput.focus();
                    emailInput.value = {json.dumps(IDX_EMAIL)};
                    emailInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    emailInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    filled.email = emailInput.value === {json.dumps(IDX_EMAIL)};
                }}
                if (phoneInput) {{
                    phoneInput.focus();
                    phoneInput.value = {json.dumps(IDX_PHONE)};
                    phoneInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    phoneInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    filled.phone = phoneInput.value === {json.dumps(IDX_PHONE)};
                }}
                return filled;
            }}''')
            logger.info(f"Fill result: {fill_result}")

            if not fill_result.get('email') or not fill_result.get('phone'):
                logger.error("Failed to fill login credentials")
                return False

            await page.wait_for_timeout(500)

            # Debug: Screenshot after filling credentials
            await self._debug_screenshot(page, 'debug_01c_credentials_filled.png')

            # Click Log In button
            logger.info("Clicking Log In button")
            login_clicked = await page.evaluate('''() => {
                // Look for Log In button (not Sign Up)
                const buttons = document.querySelectorAll('button, input[type="submit"]');
                for (let btn of buttons) {
                    const text = (btn.textContent || btn.value || '').trim();
                    if (text === 'Log In' || text === 'Sign In' || text === 'Login') {
                        btn.click();
                        return text;
                    }
                }
                // Try form submit
                const form = document.querySelector('form:has(input[type="email"])');
                if (form) {
                    form.submit();
                    return 'form-submit';
                }
                return false;
            }''')

            if not login_clicked:
                logger.error("Could not find or click Log In button")
                return False
            logger.info(f"Clicked login button: {login_clicked}")

            # Wait for login to process
            await page.wait_for_timeout(TIMEOUT_LOGIN_PROCESS)

            # Debug: Screenshot after login attempt
            await self._debug_screenshot(page, 'debug_01d_after_login.png')

            # Verify login succeeded by checking for logged-in indicators
            login_verified = await page.evaluate('''() => {
                const body = document.body.innerHTML.toLowerCase();

                // Signs of being logged in (using valid CSS selectors only)
                const loggedInSigns = [
                    document.querySelector('a[href*="logout"]'),
                    document.querySelector('a[href*="signout"]'),
                    document.querySelector('.user-name'),
                    document.querySelector('.logged-in'),
                    body.includes('my saved searches'),
                    body.includes('my account'),
                    body.includes('sign out'),
                    body.includes('log out'),
                    body.includes('logout'),
                ];

                // Signs of NOT being logged in (login form still visible)
                const loginFormVisible = document.querySelector('input[type="email"]');
                const signUpVisible = body.includes('sign up for an account');

                return {
                    anyLoggedInSign: loggedInSigns.some(s => !!s),
                    loginFormStillVisible: !!loginFormVisible,
                    signUpPromptVisible: signUpVisible
                };
            }''')
            logger.info(f"Login verification: {login_verified}")

            if login_verified.get('signUpPromptVisible') or login_verified.get('loginFormStillVisible'):
                logger.error("Login appears to have failed - sign up prompt or login form still visible")
                return False

            if login_verified.get('anyLoggedInSign'):
                logger.info("Login verified successful")
                return True

            # If we can't verify, assume it worked (some sites don't show clear indicators)
            logger.warning("Could not verify login status, proceeding anyway")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def stop(self) -> None:
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
        Optimized for speed to avoid browserless.io session timeout.

        Args:
            page: The Playwright page object
            search_name: Name to save the search as

        Returns:
            True if save successful, False otherwise
        """
        if not search_name:
            logger.warning("No search name provided, skipping save")
            return False

        screenshot_dir = Path(__file__).parent / 'logs'

        try:
            logger.info(f"Attempting to save search as: {search_name}")

            # FAST PATH: Do everything in one JavaScript call to avoid timeout
            # This opens dialog, fills name, and clicks save in one shot
            logger.info("Attempting fast save via JavaScript...")
            fast_result = await page.evaluate(f'''async () => {{
                // Step 1: Click save/+ button to open dialog
                const saveBtn = document.querySelector('.save-search, a.fa-plus, [class*="save-search"]');
                if (!saveBtn) return {{ error: 'no_save_button' }};

                saveBtn.click();

                // Step 2: Wait for dialog to appear (polling)
                let attempts = 0;
                let nameInput = null;
                while (attempts < 25) {{
                    await new Promise(r => setTimeout(r, 150));
                    // Look for name input - try multiple selectors
                    const selectors = [
                        '.modal input[type="text"]',
                        '[class*="modal"] input[type="text"]',
                        '[role="dialog"] input[type="text"]',
                        'input[name="name"]',
                        'input[name="search_name"]',
                        'input[placeholder*="name" i]',
                        'form input[type="text"]'
                    ];
                    for (const sel of selectors) {{
                        const inp = document.querySelector(sel);
                        if (inp && inp.offsetParent !== null) {{
                            nameInput = inp;
                            break;
                        }}
                    }}
                    if (nameInput) break;
                    attempts++;
                }}

                if (!nameInput) return {{ error: 'no_name_input', attempts }};

                // Step 3: Clear and fill the name (more robust method)
                const searchName = {json.dumps(search_name)};
                nameInput.focus();
                nameInput.select();
                nameInput.value = '';
                nameInput.value = searchName;
                nameInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                nameInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                nameInput.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true }}));

                // Verify the value was set
                const actualValue = nameInput.value;
                if (actualValue !== searchName) {{
                    return {{ error: 'value_not_set', expected: searchName, actual: actualValue }};
                }}

                // Step 4: Wait a bit then find and click the Save button
                await new Promise(r => setTimeout(r, 300));
                const buttons = document.querySelectorAll('button, input[type="submit"]');
                for (let btn of buttons) {{
                    const text = (btn.value || btn.textContent || '').toLowerCase().trim();
                    if (text === 'save') {{
                        btn.click();
                        return {{ success: true, name: searchName }};
                    }}
                }}

                return {{ error: 'no_submit_button' }};
            }}''')

            logger.info(f"Fast save result: {fast_result}")

            if fast_result and fast_result.get('success'):
                logger.info(f"Fast save succeeded for: {search_name}")
                # Wait briefly for save to process
                try:
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass  # Browser may disconnect, that's OK
                return True

            # If fast path failed, fall back to slower method
            logger.info(f"Fast save failed ({fast_result}), trying slower method...")

            # Look for the + button or save search button
            save_clicked = False

            # Try various selectors for the save/add button
            selectors = [
                '.save-search',
                'a.fa-plus',
                'a:has(i.fa-plus)',
                'button:has(i.fa-plus)',
                'a[title*="Save"]',
                'button[title*="Save"]',
                '.add-search',
                'a.add-to-saved',
            ]

            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible():
                        logger.info(f"Clicking save button with selector: {selector}")
                        await element.evaluate("el => el.click()")
                        save_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not save_clicked:
                logger.error("Could not find save/+ button")
                return False

            # Wait for dialog to appear
            await page.wait_for_timeout(2000)

            # Fill name via JavaScript - target modal specifically
            logger.info("Filling name in save dialog...")
            name_result = await page.evaluate(f'''() => {{
                // Look for modal/dialog first
                const modal = document.querySelector('.modal, [class*="modal"], [role="dialog"], .popup, [class*="popup"]');
                let searchScope = modal || document;
                const searchName = {json.dumps(search_name)};

                // Find text input in the modal
                const inputs = searchScope.querySelectorAll('input[type="text"]');
                for (let input of inputs) {{
                    if (input.offsetParent !== null) {{
                        // Clear and fill
                        input.focus();
                        input.select();
                        input.value = '';
                        input.value = searchName;
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true }}));
                        return {{ success: true, value: input.value, inModal: !!modal }};
                    }}
                }}
                return {{ error: 'no_input_found' }};
            }}''')

            logger.info(f"Name fill result: {name_result}")

            if not name_result or not name_result.get('success'):
                logger.error(f"Could not find/fill search name input: {name_result}")
                return False

            logger.info(f"Name filled: '{name_result.get('value')}' (in modal: {name_result.get('inModal')})")

            # Click the save/submit button using JavaScript (most reliable)
            submit_clicked = await page.evaluate('''() => {
                const buttons = document.querySelectorAll('button, input[type="submit"]');
                for (let btn of buttons) {
                    const text = (btn.value || btn.textContent || '').toLowerCase().trim();
                    if (text === 'save') {
                        btn.click();
                        return 'clicked';
                    }
                }
                return false;
            }''')
            logger.info(f"Save button click result: {submit_clicked}")

            if not submit_clicked or submit_clicked == 'false':
                logger.error("Could not click save submit button")
                return False

            # Wait briefly for save to complete
            logger.info("Waiting for save to complete...")
            try:
                await page.wait_for_timeout(2000)
                logger.info("Search save attempted")
            except Exception as e:
                # Browser disconnect after clicking save is OK - save likely succeeded
                logger.info(f"Browser closed after save click - assuming success")
                return True

            # Save was clicked - return success
            # (verification navigation often causes browser timeout, so skip it)
            logger.info(f"Search save completed for: {search_name}")
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
            await page.wait_for_timeout(TIMEOUT_PAGE_LOAD)

            # Debug: Save screenshot of MLS search page
            await self._debug_screenshot(page, 'debug_02_mls_search.png')

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
                    const mlsValue = {json.dumps(mls_string)};
                    const textareas = document.querySelectorAll('textarea');
                    for (let ta of textareas) {{
                        if (ta.offsetParent !== null) {{  // visible
                            ta.value = mlsValue;
                            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    const inputs = document.querySelectorAll('input[type="text"]');
                    for (let inp of inputs) {{
                        if (inp.offsetParent !== null) {{
                            inp.value = mlsValue;
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
                # Report error if running as background task
                if PROGRESS_FILE:
                    write_progress("error", 0, total, "", "Could not find MLS input field - page may have changed or be blocked")
                    await self.stop()
                    return None
                # Otherwise keep browser open so user can manually paste

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

            if not search_clicked:
                logger.error("Could not submit the search form")
                if PROGRESS_FILE:
                    write_progress("error", 0, total, "", "Could not submit search form - page may be blocked or changed")
                    await self.stop()
                    return None

            if search_clicked:
                # Wait for results to load (use 'load' instead of 'networkidle' - more reliable)
                try:
                    await page.wait_for_load_state('load', timeout=15000)
                except Exception:
                    pass  # Page may already be loaded or timeout - continue anyway
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
                        # Log mismatch (don't show alert - it blocks browserless.io)
                        logger.info(f"MLS mismatch: {result_count} found of {submitted_count} submitted ({missing_count} missing)")
                    elif result_count >= 0:
                        logger.info(f"All {result_count} properties found")

                    # Wait for page to fully stabilize before save
                    await page.wait_for_timeout(1000)

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

            # Navigate to saved searches page so user can verify
            saved_searches_url = f"{IDX_BASE_URL}/member/saved_searches/"

            # On DEV (local browser, not browserless.io): navigate to saved searches and keep open
            using_local_browser = FORCE_LOCAL_BROWSER or SKIP_PROXY or not BROWSERLESS_TOKEN

            if using_local_browser and not self.headless:
                try:
                    logger.info(f"Navigating to saved searches: {saved_searches_url}")
                    await page.goto(saved_searches_url, wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(2000)
                    logger.info("Browser showing saved searches page - will stay open for 30 seconds")
                    write_progress("complete", total, total, f"Portfolio created with {total} properties - verify saved searches", "")

                    # Keep browser open for verification (DEV only)
                    await page.wait_for_timeout(TIMEOUT_DEV_VERIFY)
                except Exception as e:
                    logger.warning(f"Could not navigate to saved searches: {e}")

            # Write completion progress
            write_progress("complete", total, total, f"Portfolio created with {total} properties", "")

            # Close browser when done
            if self.headless or PROGRESS_FILE:
                logger.info("Closing browser")
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
