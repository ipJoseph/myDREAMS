#!/usr/bin/env python3
"""
Apify Configuration

Store API keys and actor IDs for Apify scrapers.
"""

import os
from pathlib import Path

# Load from environment or .env file
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Apify API Token - get from https://console.apify.com/account#/integrations
APIFY_TOKEN = os.getenv('APIFY_TOKEN', '')

# Database path
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

# Actor IDs for different scrapers
ACTORS = {
    # Redfin Scrapers
    'redfin_triangle': 'tri_angle/redfin-search',
    'redfin_epctex': 'epctex/redfin-scraper',
    'redfin_mantisus': 'mantisus/redfin-fast-scraper',

    # Zillow Scrapers
    'zillow_maxcopell': 'maxcopell/zillow-scraper',
    'zillow_detail': 'maxcopell/zillow-detail-scraper',
}

# Pricing info (for cost tracking)
PRICING = {
    'redfin_triangle': 0.001,      # $1 per 1,000 results
    'redfin_epctex': 0.001,        # Estimated ~$1 per 1,000
    'redfin_mantisus': 0.001,      # Estimated ~$1 per 1,000
    'zillow_maxcopell': 0.002,     # $2 per 1,000 results
    'zillow_detail': 0.002,        # Estimated
}

# WNC Counties and their Redfin region codes
WNC_COUNTIES = {
    'Buncombe': {'redfin_region': '1380', 'main_city': 'Asheville'},
    'Henderson': {'redfin_region': '1416', 'main_city': 'Hendersonville'},
    'Haywood': {'redfin_region': '1412', 'main_city': 'Waynesville'},
    'Madison': {'redfin_region': '1459', 'main_city': 'Marshall'},
    'Transylvania': {'redfin_region': '1535', 'main_city': 'Brevard'},
    'Jackson': {'redfin_region': '1426', 'main_city': 'Sylva'},
    'Macon': {'redfin_region': '1456', 'main_city': 'Franklin'},
    'Swain': {'redfin_region': '1522', 'main_city': 'Bryson City'},
    'Cherokee': {'redfin_region': '1388', 'main_city': 'Murphy'},
    'Clay': {'redfin_region': '1391', 'main_city': 'Hayesville'},
    'Graham': {'redfin_region': '1407', 'main_city': 'Robbinsville'},
}

# Required fields we need from scrapers
REQUIRED_FIELDS = {
    'must_have': [
        'address', 'city', 'state', 'zip',
        'price', 'status',
        'beds', 'baths', 'sqft',
        'photo_url',  # At least one photo
    ],
    'nice_to_have': [
        'days_on_market',
        'views', 'favorites',
        'listing_agent_name', 'listing_agent_phone',
        'price_history',
        'all_photos',
        'mls_number',
        'acreage', 'year_built',
    ]
}

# Validation thresholds for data quality
VALIDATION_RULES = {
    'beds_max': 10,
    'baths_max': 8,
    'price_min': 10000,
    'price_max': 50000000,
    'sqft_min': 100,
    'sqft_max': 20000,
    'acreage_max': 500,
}
