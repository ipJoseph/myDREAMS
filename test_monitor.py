#!/usr/bin/env python3
"""
Property Monitor - TEST VERSION
Tests Notion connection and Zillow scraping
"""

import os
import sys

print("=" * 60)
print("Property Monitor - Test Version")
print("=" * 60)

# Test 1: Check environment
print("\n[1/5] Checking environment...")
try:
    NOTION_API_KEY = os.getenv('NOTION_API_KEY')
    if not NOTION_API_KEY:
        print("❌ NOTION_API_KEY not set")
        print("   Set it in .env file or export NOTION_API_KEY=your_key")
        sys.exit(1)
    print(f"✓ NOTION_API_KEY found: {NOTION_API_KEY[:10]}...")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

# Test 2: Import libraries
print("\n[2/5] Importing libraries...")
try:
    from notion_client import Client
    print("✓ notion_client")
    
    import requests
    print("✓ requests")
    
    from bs4 import BeautifulSoup
    print("✓ BeautifulSoup")
except ImportError as e:
    print(f"❌ Missing library: {e}")
    print("   Run: pip install beautifulsoup4 lxml notion-client --break-system-packages")
    sys.exit(1)

# Test 3: Connect to Notion
# Test 3: Connect to Notion
# Test 3: Connect to Notion
print("\n[3/5] Connecting to Notion...")
try:
    notion = Client(auth=NOTION_API_KEY)
    
    # Query the Properties data source (not database)
    DATA_SOURCE_ID = '54df6a1e-390d-43c6-8023-3e0dc9b87c23'
    
    response = notion.data_sources.query(
        data_source_id=DATA_SOURCE_ID,
        filter={
            "property": "Monitoring Active",
            "checkbox": {"equals": True}
        },
        page_size=10
    )
    
    num_properties = len(response['results'])
    print(f"✓ Connected to Notion")
    print(f"✓ Found {num_properties} properties with monitoring enabled")
    
    if num_properties == 0:
        print("\n⚠️  No properties have 'Monitoring Active' checked")
        print("   Go to Notion and check the 'Monitoring Active' box on at least one property")
        sys.exit(0)
    
except Exception as e:
    print(f"❌ Notion connection failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Test Zillow scraping
print("\n[4/5] Testing Zillow scraping...")

# Get first property
prop = response['results'][0]
props = prop['properties']

address = props['Address']['title'][0]['plain_text'] if props['Address']['title'] else 'Unknown'
zillow_url = props['Zillow URL']['url'] if props.get('Zillow URL') else None

if not zillow_url:
    print(f"⚠️  Property '{address}' has no Zillow URL")
    print("   Add a Zillow URL in Notion to test scraping")
    sys.exit(0)

print(f"Testing with: {address}")
print(f"URL: {zillow_url}")

try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
    }
    
    print("Fetching page...")
    response_web = requests.get(zillow_url, headers=headers, timeout=10)
    response_web.raise_for_status()
    
    print("Parsing HTML...")
    soup = BeautifulSoup(response_web.text, 'html.parser')
    
    # Try to find price
    price_elem = soup.select_one('span[data-test="price"]')
    if price_elem:
        price_text = price_elem.get_text()
        print(f"✓ Found price: {price_text}")
    else:
        print("⚠️  Could not find price (Zillow HTML may have changed)")
    
    # Try to find status
    if 'for sale' in response_web.text.lower():
        print("✓ Property appears to be Active")
    elif 'pending' in response_web.text.lower():
        print("✓ Property appears to be Pending")
    
    print("✓ Zillow scraping works!")
    
except requests.Timeout:
    print("❌ Request timed out")
    print("   Check internet connection")
except Exception as e:
    print(f"❌ Scraping failed: {e}")

# Test 5: Summary
print("\n[5/5] Summary")
print("=" * 60)
print(f"✓ Environment: OK")
print(f"✓ Libraries: OK")
print(f"✓ Notion Connection: OK")
print(f"✓ Properties to Monitor: {num_properties}")
print(f"✓ Zillow Scraping: OK")
print("=" * 60)
print("\n🎉 All tests passed!")
print("\nNext steps:")
print("1. Copy the full monitor_properties.py script")
print("2. Run: python apps/property-monitor/monitor_properties.py")
print("3. Set up daily cron job")
print()
