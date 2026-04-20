#!/usr/bin/env python3
"""
FUB Smart List Scraper

Uses Playwright to extract contacts from a FUB smart list.
Opens a visible browser for manual login, then scrapes the list.

Usage:
    python fub_smartlist_scraper.py <smart_list_url> <output_name>

Example:
    python fub_smartlist_scraper.py "https://jontharpteam.followupboss.com/2/people/list/61" cool_quarterly
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / 'data' / 'smart_lists'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_smart_list(url: str, output_name: str):
    """Extract contacts from a FUB smart list."""

    # Track API calls for analysis
    api_calls = []

    with sync_playwright() as p:
        # Launch visible browser
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1400, 'height': 900})
        page = context.new_page()

        # Intercept network requests
        def handle_response(response):
            if 'api.followupboss.com' in response.url or 'followupboss.com/v1' in response.url:
                try:
                    api_calls.append({
                        'url': response.url,
                        'status': response.status,
                        'method': response.request.method
                    })
                except:
                    pass

        page.on('response', handle_response)

        # Navigate to FUB
        print("Opening FUB...")
        page.goto('https://app.followupboss.com/login')

        print("\n" + "=" * 60)
        print("Please log in to FUB in the browser window.")
        print("Once logged in, press ENTER here to continue...")
        print("=" * 60 + "\n")
        input()

        # Navigate to smart list
        print(f"Navigating to smart list: {url}")
        page.goto(url)

        # Wait for the list to load
        print("Waiting for contact list to load...")
        time.sleep(3)

        # Try to find and click "Select All" or scroll to load all
        try:
            # Look for total count
            count_el = page.query_selector('[data-testid="people-count"], .people-count, .list-count')
            if count_el:
                print(f"List info: {count_el.text_content()}")
        except:
            pass

        # Scroll to load all contacts (FUB uses infinite scroll)
        print("Scrolling to load all contacts...")
        last_count = 0
        scroll_attempts = 0
        max_scrolls = 50

        while scroll_attempts < max_scrolls:
            # Count current contacts
            rows = page.query_selector_all('tr[data-person-id], [data-testid="person-row"], .person-row, tbody tr')
            current_count = len(rows)

            if current_count == last_count and scroll_attempts > 3:
                print(f"All contacts loaded: {current_count}")
                break

            last_count = current_count
            scroll_attempts += 1

            # Scroll down
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(0.5)

            if scroll_attempts % 10 == 0:
                print(f"  Loaded {current_count} contacts so far...")

        # Extract contact data
        print("\nExtracting contact data...")
        contacts = []

        # Try multiple selector strategies
        rows = page.query_selector_all('tbody tr')

        if not rows:
            rows = page.query_selector_all('[data-person-id]')

        if not rows:
            rows = page.query_selector_all('.person-row')

        print(f"Found {len(rows)} rows")

        for row in rows:
            try:
                # Extract name - try different selectors
                name = ''
                name_el = row.query_selector('a[href*="/people/view/"], .person-name, [data-testid="person-name"]')
                if name_el:
                    name = name_el.text_content().strip()

                if not name:
                    # Try first link or strong text
                    link = row.query_selector('a')
                    if link:
                        name = link.text_content().strip()

                # Extract email
                email = ''
                email_el = row.query_selector('a[href^="mailto:"], [data-testid="email"]')
                if email_el:
                    email = email_el.text_content().strip()

                if not email:
                    # Look for email pattern in row text
                    row_text = row.text_content()
                    import re
                    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', row_text)
                    if email_match:
                        email = email_match.group()

                # Extract phone
                phone = ''
                phone_el = row.query_selector('a[href^="tel:"], [data-testid="phone"]')
                if phone_el:
                    phone = phone_el.text_content().strip()

                if name and (email or phone):
                    # Parse first name
                    first_name = name.split()[0] if name else ''

                    contacts.append({
                        'full_name': name,
                        'first_name': first_name,
                        'email': email,
                        'phone': phone
                    })
            except Exception as e:
                print(f"  Error parsing row: {e}")
                continue

        # Dedupe by email
        seen_emails = set()
        unique_contacts = []
        for c in contacts:
            if c['email'] and c['email'].lower() not in seen_emails:
                seen_emails.add(c['email'].lower())
                unique_contacts.append(c)
            elif not c['email']:
                unique_contacts.append(c)

        contacts = unique_contacts
        print(f"Extracted {len(contacts)} unique contacts")

        # Save API calls for analysis
        if api_calls:
            api_log = OUTPUT_DIR / f'{output_name}_api_calls.json'
            with open(api_log, 'w') as f:
                json.dump(api_calls, f, indent=2)
            print(f"\nAPI calls logged to: {api_log}")
            print("Interesting endpoints found:")
            for call in api_calls:
                if 'people' in call['url'].lower() or 'list' in call['url'].lower():
                    print(f"  {call['method']} {call['url'][:100]}")

        # Save contacts
        if contacts:
            timestamp = datetime.now().strftime('%Y%m%d')
            output_file = OUTPUT_DIR / f'{output_name}_scraped_{timestamp}.csv'

            with open(output_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['full_name', 'first_name', 'email', 'phone'])
                writer.writeheader()
                writer.writerows(contacts)

            print(f"\nSaved to: {output_file}")
            print(f"Total contacts: {len(contacts)}")
            print(f"With email: {sum(1 for c in contacts if c['email'])}")
            print(f"With phone: {sum(1 for c in contacts if c['phone'])}")
        else:
            print("\nNo contacts extracted. The page structure may have changed.")
            print("Check the browser window to see what's displayed.")
            print("\nPress ENTER to close the browser...")
            input()

        browser.close()

    return contacts


def main():
    parser = argparse.ArgumentParser(description='Extract contacts from FUB smart list')
    parser.add_argument('url', help='FUB smart list URL')
    parser.add_argument('output_name', help='Output file name prefix')

    args = parser.parse_args()

    contacts = extract_smart_list(args.url, args.output_name)

    if contacts:
        print("\nFirst 5 contacts:")
        for c in contacts[:5]:
            print(f"  {c['full_name']} - {c['email']}")


if __name__ == '__main__':
    main()
