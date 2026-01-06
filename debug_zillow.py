#!/usr/bin/env python3
"""Debug Zillow HTML structure"""

import requests
from bs4 import BeautifulSoup

url = "https://www.zillow.com/homedetails/94-Chalet-Cir-Murphy-NC-28906/127239006_zpid/"

headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
}

print("Fetching Zillow page...")
response = requests.get(url, headers=headers, timeout=10)
print(f"Status: {response.status_code}")

soup = BeautifulSoup(response.text, 'html.parser')

# Try different price selectors
print("\n=== Searching for price ===")
selectors = [
    'span[data-test="price"]',
    'span[data-testid="price"]',
    'h2.ds-home-details-chip',
    'div.ds-summary-row span',
    'span.ds-price',
    'div[data-test="price"]',
]

for selector in selectors:
    elem = soup.select_one(selector)
    if elem:
        print(f"✓ Found with '{selector}': {elem.get_text()}")
    else:
        print(f"✗ Not found: '{selector}'")

# Search for price in text
print("\n=== Searching for '$' in page ===")
price_texts = soup.find_all(string=lambda text: text and '$' in text and any(c.isdigit() for c in text))
print(f"Found {len(price_texts)} elements with '$' and numbers")
for i, text in enumerate(price_texts[:5]):  # Show first 5
    print(f"{i+1}. {text.strip()[:100]}")

# Save HTML for inspection
with open('zillow_debug.html', 'w') as f:
    f.write(soup.prettify())
print("\n✓ Saved HTML to zillow_debug.html")
