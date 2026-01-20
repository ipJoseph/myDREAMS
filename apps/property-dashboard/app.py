#!/usr/bin/env python3
"""
DREAMS Property Dashboard
A web-based summary view of properties and contacts from SQLite (source of truth)
"""

import json
import logging
import os
import sys
import subprocess
import statistics
import re
from functools import wraps
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from flask import Flask, render_template, render_template_string, request, jsonify, Response, redirect, url_for
import httpx

# Module logger
logger = logging.getLogger(__name__)

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.database import DREAMSDatabase

# Initialize database connection
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))
db = DREAMSDatabase(DB_PATH)

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

app = Flask(__name__)

# Basic Auth Configuration
DASHBOARD_USERNAME = os.getenv('DASHBOARD_USERNAME')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD')

# Environment detection (dev/prd) - defaults to 'dev'
DREAMS_ENV = os.getenv('DREAMS_ENV', 'dev').lower()

# Client Portfolio Password (simple key-based access)
CLIENT_PORTFOLIO_KEY = os.getenv('CLIENT_PORTFOLIO_KEY', 'dreams2026')


@app.context_processor
def inject_globals():
    """Inject global variables into all templates"""
    return {
        'dreams_env': DREAMS_ENV,
        'favicon': f'/static/favicon-{DREAMS_ENV}.svg'
    }


# Simple password form for client portfolio
CLIENT_PASSWORD_FORM = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Access Property Portfolio | Jon Tharp Homes</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .login-card {
            background: white;
            border-radius: 16px;
            padding: 40px;
            max-width: 400px;
            width: 100%;
            box-shadow: 0 25px 50px rgba(0,0,0,0.25);
            text-align: center;
        }
        .login-card h1 {
            color: #1e3a5f;
            font-size: 24px;
            margin-bottom: 8px;
        }
        .login-card .subtitle {
            color: #64748b;
            font-size: 14px;
            margin-bottom: 32px;
        }
        .login-card .client-name {
            color: #0ea5e9;
            font-weight: 600;
        }
        .login-card input[type="password"] {
            width: 100%;
            padding: 14px 16px;
            font-size: 16px;
            border: 2px solid #e2e8f0;
            border-radius: 8px;
            margin-bottom: 16px;
            outline: none;
            transition: border-color 0.2s;
        }
        .login-card input[type="password"]:focus {
            border-color: #0ea5e9;
        }
        .login-card button {
            width: 100%;
            padding: 14px 16px;
            font-size: 16px;
            font-weight: 600;
            color: white;
            background: #1e3a5f;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .login-card button:hover {
            background: #0f172a;
        }
        .error {
            color: #dc2626;
            font-size: 14px;
            margin-bottom: 16px;
        }
        .branding {
            margin-top: 24px;
            font-size: 12px;
            color: #94a3b8;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <h1>Property Portfolio</h1>
        <p class="subtitle">Curated properties for <span class="client-name">{{ client_name }}</span></p>
        {% if error %}
        <p class="error">{{ error }}</p>
        {% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="Enter access code" autofocus required>
            <button type="submit">View Properties</button>
        </form>
        <p class="branding">Jon Tharp Homes | Keller Williams</p>
    </div>
</body>
</html>
'''


def check_auth(username, password):
    """Check if a username/password combination is valid."""
    return username == DASHBOARD_USERNAME and password == DASHBOARD_PASSWORD


def authenticate():
    """Send a 401 response to prompt for credentials."""
    return Response(
        'Authentication required. Please log in.',
        401,
        {'WWW-Authenticate': 'Basic realm="DREAMS Dashboard"'}
    )


def requires_auth(f):
    """Decorator to require HTTP Basic Auth for a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Skip auth if credentials not configured (local development)
        if not DASHBOARD_USERNAME or not DASHBOARD_PASSWORD:
            return f(*args, **kwargs)

        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# Notion configuration
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DATABASE_ID = os.getenv('NOTION_PROPERTIES_DB_ID', '2eb02656b6a4432dbac17d681adbb640')

# Format database ID
db_id = NOTION_DATABASE_ID.replace('-', '')
DATABASE_ID = f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"

# Notion API headers
NOTION_HEADERS = {
    'Authorization': f'Bearer {NOTION_API_KEY}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}


# Database helper
def get_db():
    """Get database instance."""
    from src.core.database import DREAMSDatabase
    db_path = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))
    return DREAMSDatabase(db_path)


def enrich_properties_with_idx_photos(properties: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add IDX photo URLs to properties that don't have photos from Notion."""
    # Collect MLS numbers for properties without photos
    mls_without_photos = {}
    for prop in properties:
        if not prop.get('photo_url') and prop.get('mls_number'):
            mls_without_photos[prop['mls_number']] = prop

    if not mls_without_photos:
        return properties

    # Query IDX cache for photo URLs
    try:
        db = get_db()
        with db._get_connection() as conn:
            placeholders = ','.join('?' * len(mls_without_photos))
            rows = conn.execute(f'''
                SELECT mls_number, photo_url FROM idx_property_cache
                WHERE mls_number IN ({placeholders}) AND photo_url IS NOT NULL
            ''', list(mls_without_photos.keys())).fetchall()

            for row in rows:
                mls_number, photo_url = row
                if mls_number in mls_without_photos and photo_url:
                    mls_without_photos[mls_number]['photo_url'] = photo_url
    except Exception as e:
        # Log but don't fail if IDX lookup fails
        logger.warning(f"IDX photo lookup failed: {e}")

    return properties


def extract_property(prop: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract property data from Notion page properties"""
    def get_title(p):
        if p and p.get('title') and len(p['title']) > 0:
            return p['title'][0].get('plain_text', '')
        return ''

    def get_number(p):
        return p.get('number') if p else None

    def get_url(p):
        return p.get('url') if p else None

    def get_select(p):
        if p and p.get('select'):
            return p['select'].get('name', '')
        return ''

    def get_rich_text(p):
        if p and p.get('rich_text') and len(p['rich_text']) > 0:
            return p['rich_text'][0].get('plain_text', '')
        return ''

    def clean_county_name(name):
        """Remove 'County' suffix from county names"""
        if name:
            return re.sub(r'\s+County$', '', name, flags=re.IGNORECASE).strip()
        return ''

    def get_date(p):
        if p and p.get('date') and p['date'].get('start'):
            return p['date']['start']
        return None

    def get_files(p):
        """Extract first image URL from files property"""
        if p and p.get('files') and len(p['files']) > 0:
            file_obj = p['files'][0]
            if file_obj.get('type') == 'external':
                return file_obj.get('external', {}).get('url')
            elif file_obj.get('type') == 'file':
                return file_obj.get('file', {}).get('url')
        return None

    props = prop['properties']

    # Calculate price per sqft
    price = get_number(props.get('Price'))
    sqft = get_number(props.get('Sqft'))
    price_per_sqft = round(price / sqft, 2) if price and sqft and sqft > 0 else None

    return {
        'id': prop['id'],
        'notion_url': prop.get('url', ''),
        'address': get_title(props.get('Address')),
        'city': get_select(props.get('City')),
        'county': clean_county_name(get_rich_text(props.get('County'))),
        'state': get_rich_text(props.get('State')),
        'zip': get_rich_text(props.get('Zip')),
        'price': price,
        'sqft': sqft,
        'price_per_sqft': price_per_sqft,
        'beds': get_number(props.get('Bedrooms')),
        'baths': get_number(props.get('Bathrooms')),
        'lot_acres': get_number(props.get('Acreage')),
        'year_built': get_number(props.get('Year Built')),
        'dom': get_number(props.get('DOM')),
        'status': get_select(props.get('Status')),
        'property_type': get_select(props.get('Style')),
        'source': get_select(props.get('Source')),
        'added_for': get_rich_text(props.get('Added For')),
        'added_by': get_select(props.get('Added By')),
        'url': get_url(props.get('URL')),
        'mls_number': get_rich_text(props.get('MLS #')),
        'page_views': get_number(props.get('Page Views')),
        'favorites': get_number(props.get('Favorites')),
        'zestimate': get_number(props.get('Zestimate')),
        'tax_annual': get_number(props.get('Tax Annual')),
        'hoa': get_number(props.get('HOA')),
        'date_saved': get_date(props.get('Date Saved')),
        'last_updated': get_date(props.get('Last Updated')),
        'photo_url': get_files(props.get('Photos')),
        'stories': get_number(props.get('Stories')),
        # IDX validation fields
        'idx_mls_number': get_rich_text(props.get('IDX MLS #')),
        'original_mls_number': get_rich_text(props.get('Original MLS #')),
        'idx_validation_status': get_select(props.get('IDX Status')),
        'idx_mls_source': get_rich_text(props.get('IDX MLS Source')),
    }


def fetch_properties(added_for: Optional[str] = None, status: Optional[str] = None,
                      city: Optional[str] = None, county: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch properties from SQLite with optional filters"""
    with db._get_connection() as conn:
        query = 'SELECT * FROM properties WHERE 1=1'
        params = []

        if added_for:
            query += ' AND added_for LIKE ?'
            params.append(f'%{added_for}%')

        if status:
            query += ' AND LOWER(status) = LOWER(?)'
            params.append(status)

        if city:
            query += ' AND LOWER(city) = LOWER(?)'
            params.append(city)

        if county:
            query += ' AND county LIKE ?'
            params.append(f'%{county}%')

        query += ' ORDER BY created_at DESC'

        rows = conn.execute(query, params).fetchall()

        # Convert to list of dicts and normalize field names for templates
        properties = []
        for row in rows:
            prop = dict(row)
            # Calculate price per sqft
            price = prop.get('price')
            sqft = prop.get('sqft')
            prop['price_per_sqft'] = round(price / sqft, 2) if price and sqft and sqft > 0 else None

            # Normalize field names for template compatibility
            prop['beds'] = prop.get('beds')
            prop['baths'] = prop.get('baths')
            prop['lot_acres'] = prop.get('acreage')
            prop['dom'] = prop.get('days_on_market')
            prop['tax_annual'] = prop.get('tax_annual_amount')
            prop['hoa'] = prop.get('hoa_fee')
            prop['date_saved'] = prop.get('created_at')
            prop['last_updated'] = prop.get('updated_at')
            prop['photo_url'] = prop.get('primary_photo')
            prop['favorites'] = prop.get('favorites_count')
            prop['notion_url'] = f"https://notion.so/{prop.get('notion_page_id', '').replace('-', '')}" if prop.get('notion_page_id') else None

            # Clean county name (remove 'County' suffix)
            if prop.get('county'):
                prop['county'] = re.sub(r'\s+County$', '', prop['county'], flags=re.IGNORECASE).strip()

            properties.append(prop)

        return properties


def calculate_metrics(properties: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate summary metrics for a list of properties"""
    if not properties:
        return {}

    prices = [p['price'] for p in properties if p['price']]
    sqfts = [p['sqft'] for p in properties if p['sqft']]
    price_per_sqfts = [p['price_per_sqft'] for p in properties if p['price_per_sqft']]
    doms = [p['dom'] for p in properties if p['dom'] is not None]
    beds = [p['beds'] for p in properties if p['beds']]
    baths = [p['baths'] for p in properties if p['baths']]
    taxes = [p['tax_annual'] for p in properties if p['tax_annual']]
    lot_acres = [p['lot_acres'] for p in properties if p['lot_acres']]

    return {
        'total_count': len(properties),
        'avg_price': round(statistics.mean(prices)) if prices else None,
        'median_price': round(statistics.median(prices)) if prices else None,
        'min_price': min(prices) if prices else None,
        'max_price': max(prices) if prices else None,
        'avg_sqft': round(statistics.mean(sqfts)) if sqfts else None,
        'avg_price_per_sqft': round(statistics.mean(price_per_sqfts)) if price_per_sqfts else None,
        'avg_dom': round(statistics.mean(doms)) if doms else None,
        'avg_beds': round(statistics.mean(beds), 1) if beds else None,
        'avg_baths': round(statistics.mean(baths), 1) if baths else None,
        'avg_taxes': round(statistics.mean(taxes)) if taxes else None,
        'avg_lot_acres': round(statistics.mean(lot_acres), 2) if lot_acres else None,
        # Status breakdown
        'status_counts': {}
    }


def get_unique_values(properties: List[Dict[str, Any]], key: str) -> List[str]:
    """Extract and sort unique values for a given property key."""
    return sorted({p[key] for p in properties if p.get(key)})


def calculate_status_counts(properties: List[Dict[str, Any]]) -> Dict[str, int]:
    """Calculate count of properties by status."""
    counts: Dict[str, int] = {}
    for p in properties:
        status = p.get('status') or 'Unknown'
        counts[status] = counts.get(status, 0) + 1
    return counts


@app.route('/')
@requires_auth
def home():
    """Unified dashboard home (requires authentication)"""
    db = get_db()

    # Get property stats
    all_properties = fetch_properties()
    property_metrics = calculate_metrics(all_properties)

    property_stats = {
        'total': len(all_properties),
        'status_counts': calculate_status_counts(all_properties),
        'avg_price': "${:,.0f}".format(property_metrics.get('avg_price', 0)) if property_metrics.get('avg_price') else '--'
    }

    # Get contact stats
    contact_stats = db.get_contact_stats()

    # Get top priority contacts
    top_contacts = db.get_contacts_by_priority(min_priority=0, limit=10)

    # Count actions due (simplified - contacts with next_action set)
    actions_due = sum(1 for c in top_contacts if c.get('next_action'))

    # Get today's property changes
    todays_changes = db.get_todays_changes()
    change_summary = db.get_change_summary(hours=24)

    return render_template('home.html',
                         property_stats=property_stats,
                         contact_stats=contact_stats,
                         top_contacts=top_contacts,
                         actions_due=actions_due,
                         todays_changes=todays_changes,
                         change_summary=change_summary,
                         refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


@app.route('/properties')
@requires_auth
def properties_list():
    """Property list view (requires authentication)"""
    # Get filter parameters
    added_for = request.args.get('client', '')
    status = request.args.get('status', '')
    city = request.args.get('city', '')
    county = request.args.get('county', '')

    # Fetch all properties first to get dropdown options
    all_properties = fetch_properties()
    clients = get_unique_values(all_properties, 'added_for')
    cities = get_unique_values(all_properties, 'city')
    counties = get_unique_values(all_properties, 'county')
    statuses = get_unique_values(all_properties, 'status')

    # Apply filters
    properties = fetch_properties(
        added_for=added_for if added_for else None,
        status=status if status else None,
        city=city if city else None,
        county=county if county else None
    )

    # Enrich with IDX photos for properties without Notion photos
    properties = enrich_properties_with_idx_photos(properties)

    # Calculate metrics
    metrics = calculate_metrics(properties)
    metrics['status_counts'] = calculate_status_counts(properties)

    # Sort by price descending
    properties.sort(key=lambda x: x['price'] or 0, reverse=True)

    return render_template('dashboard.html',
                         properties=properties,
                         metrics=metrics,
                         clients=clients,
                         cities=cities,
                         counties=counties,
                         statuses=statuses,
                         selected_client=added_for,
                         selected_status=status,
                         selected_city=city,
                         selected_county=county,
                         refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


@app.route('/lead/<client_name>')
def lead_dashboard_redirect(client_name):
    """Redirect old /lead/ URLs to new /client/ URLs"""
    return redirect(url_for('client_dashboard', client_name=client_name), code=301)


@app.route('/client/<client_name>', methods=['GET', 'POST'])
def client_dashboard(client_name):
    """Client-facing dashboard view - personalized property portal with simple password protection"""
    # Check for key-based access
    key = request.args.get('key', '')

    # Handle POST form submission for password
    if request.method == 'POST':
        submitted_key = request.form.get('password', '')
        if submitted_key == CLIENT_PORTFOLIO_KEY:
            # Redirect with key in URL so they can bookmark it
            return redirect(url_for('client_dashboard', client_name=client_name, key=submitted_key))
        else:
            return render_template_string(CLIENT_PASSWORD_FORM, client_name=client_name, error="Invalid password. Please try again.")

    # Check if key is valid
    if key != CLIENT_PORTFOLIO_KEY:
        return render_template_string(CLIENT_PASSWORD_FORM, client_name=client_name, error=None)

    # Get filter parameters
    status = request.args.get('status', '')
    city = request.args.get('city', '')
    county = request.args.get('county', '')

    # Fetch properties for this client
    all_client_properties = fetch_properties(added_for=client_name)

    # Get filter options from this client's properties only
    cities = get_unique_values(all_client_properties, 'city')
    counties = get_unique_values(all_client_properties, 'county')
    statuses = get_unique_values(all_client_properties, 'status')

    # Apply additional filters
    properties = fetch_properties(
        added_for=client_name,
        status=status if status else None,
        city=city if city else None,
        county=county if county else None
    )

    # Enrich with IDX photos for properties without Notion photos
    properties = enrich_properties_with_idx_photos(properties)

    # Calculate metrics
    metrics = calculate_metrics(properties)
    metrics['status_counts'] = calculate_status_counts(properties)

    # Sort by price descending
    properties.sort(key=lambda x: x['price'] or 0, reverse=True)

    return render_template('lead_dashboard.html',
                         properties=properties,
                         metrics=metrics,
                         client_name=client_name,
                         cities=cities,
                         counties=counties,
                         statuses=statuses,
                         selected_status=status,
                         selected_city=city,
                         selected_county=county,
                         refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


@app.route('/api/properties')
@requires_auth
def api_properties():
    """API endpoint for properties data (requires authentication)"""
    added_for = request.args.get('client', '')
    status = request.args.get('status', '')

    properties = fetch_properties(
        added_for=added_for if added_for else None,
        status=status if status else None
    )
    metrics = calculate_metrics(properties)

    return jsonify({
        'properties': properties,
        'metrics': metrics
    })


# =========================================================================
# CONTACTS ROUTES
# =========================================================================

@app.route('/contacts')
@requires_auth
def contacts_list():
    """Contacts list view (requires authentication)"""
    db = get_db()

    # Get filter parameters
    min_heat = request.args.get('min_heat', 0, type=float)
    min_value = request.args.get('min_value', 0, type=float)
    stage = request.args.get('stage', '')
    sort_by = request.args.get('sort', 'priority')  # priority, heat, value, name
    filter_type = request.args.get('filter', '')  # hot_leads, high_value, active_week

    # Get all contacts (no artificial limit - let the database handle it)
    contacts = db.get_contacts_by_priority(min_priority=0, limit=2000)

    # Apply quick filter from metric card clicks
    if filter_type == 'hot_leads':
        contacts = [c for c in contacts if (c.get('heat_score') or 0) >= 75]
    elif filter_type == 'high_value':
        contacts = [c for c in contacts if (c.get('value_score') or 0) >= 60]
    elif filter_type == 'active_week':
        contacts = [c for c in contacts if (c.get('days_since_activity') or 999) <= 7]

    # Apply min_heat filter
    if min_heat > 0:
        contacts = [c for c in contacts if (c.get('heat_score') or 0) >= min_heat]

    # Apply min_value filter
    if min_value > 0:
        contacts = [c for c in contacts if (c.get('value_score') or 0) >= min_value]

    # Apply stage filter
    if stage:
        contacts = [c for c in contacts if c.get('stage') == stage]

    # Apply sorting
    if sort_by == 'heat':
        contacts.sort(key=lambda c: c.get('heat_score') or 0, reverse=True)
    elif sort_by == 'value':
        contacts.sort(key=lambda c: c.get('value_score') or 0, reverse=True)
    elif sort_by == 'name':
        contacts.sort(key=lambda c: f"{c.get('first_name', '')} {c.get('last_name', '')}".lower())
    # Default: priority (already sorted)

    # Get unique stages for filter dropdown (from full list)
    all_contacts = db.get_contacts_by_priority(min_priority=0, limit=2000)
    stages = sorted(set(c.get('stage') for c in all_contacts if c.get('stage')))

    # Get aggregate stats
    stats = db.get_contact_stats()

    return render_template('contacts.html',
                         contacts=contacts,
                         stats=stats,
                         stages=stages,
                         selected_stage=stage,
                         selected_min_heat=min_heat,
                         selected_sort=sort_by,
                         selected_filter=filter_type,
                         refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


def populate_idx_cache_for_contact(db, contact_id: str, limit: int = 20):
    """
    Auto-populate IDX cache for a contact's uncached MLS numbers.
    Called when viewing contact detail to ensure addresses are available.
    """
    import asyncio
    from playwright.async_api import async_playwright

    uncached = db.get_uncached_mls_numbers(limit=limit, contact_id=contact_id)
    if not uncached:
        return 0

    IDX_PROPERTY_URL = "https://www.smokymountainhomes4sale.com/property"

    async def scrape_batch():
        cached_count = 0
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                for mls in uncached:
                    try:
                        url = f"{IDX_PROPERTY_URL}/{mls}"
                        response = await page.goto(url, wait_until='domcontentloaded', timeout=10000)

                        if response and response.status == 200:
                            await page.wait_for_timeout(1000)

                            # Extract address from page
                            data = await page.evaluate('''() => {
                                const selectors = ['.property-address', '.listing-address', '[class*="address"]', 'h1'];
                                for (let sel of selectors) {
                                    const el = document.querySelector(sel);
                                    if (el) {
                                        const text = el.textContent.trim();
                                        if (text.match(/\\d+.*(?:St|Ave|Rd|Dr|Ln|Way|Ct|Blvd|Hwy|Trail|Loop|Knob|Estates)/i)) {
                                            return { address: text.split('\\n')[0].trim() };
                                        }
                                    }
                                }
                                return null;
                            }''')

                            if data and data.get('address'):
                                db.upsert_idx_cache(mls, data['address'])
                                cached_count += 1
                            else:
                                db.upsert_idx_cache(mls, '[Not found on IDX]')
                        else:
                            db.upsert_idx_cache(mls, '[Not found on IDX]')

                    except Exception:
                        db.upsert_idx_cache(mls, '[Not found on IDX]')

                await browser.close()
        except Exception as e:
            app.logger.error(f"IDX cache population error: {e}")

        return cached_count

    # Run async scraping
    try:
        return asyncio.run(scrape_batch())
    except Exception as e:
        app.logger.error(f"Error running IDX cache: {e}")
        return 0


@app.route('/contacts/<contact_id>')
@requires_auth
def contact_detail(contact_id):
    """Contact detail view (requires authentication)"""
    db = get_db()

    # Get contact
    contact = db.get_lead(contact_id)
    if not contact:
        return "Contact not found", 404

    # Auto-populate IDX cache for this contact's uncached MLS numbers
    populate_idx_cache_for_contact(db, contact_id, limit=20)

    # Get linked properties (from contact_properties table)
    properties = db.get_contact_properties(contact_id)

    # Get property view summary (aggregated from contact_events)
    property_summary = db.get_contact_property_summary(contact_id)

    # Get activity timeline (communications + events from last 30 days)
    timeline = db.get_activity_timeline(contact_id, days=30, limit=50)

    # Get trend summary (scoring history, 7d avg, trend direction)
    trend_summary = db.get_contact_trend_summary(contact_id)

    return render_template('contact_detail.html',
                         contact=contact,
                         properties=properties,
                         property_summary=property_summary,
                         timeline=timeline,
                         trend_summary=trend_summary,
                         refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


# =========================================================================
# IDX VALIDATION ROUTES
# =========================================================================

@app.route('/api/validate-idx', methods=['POST'])
@requires_auth
def validate_idx_properties():
    """
    Validate properties against IDX on-demand (requires authentication).
    Accepts list of properties with address/mls_number, returns validated MLS numbers.
    """
    data = request.get_json()
    properties = data.get('properties', [])

    if not properties:
        return jsonify({'success': False, 'error': 'No properties provided'}), 400

    # Import validation logic
    import asyncio
    from playwright.async_api import async_playwright

    IDX_BASE_URL = "https://www.smokymountainhomes4sale.com"
    IDX_PROPERTY_URL = f"{IDX_BASE_URL}/property"

    async def check_mls_on_idx(page, mls_number):
        """Check if MLS# exists on IDX site."""
        try:
            url = f"{IDX_PROPERTY_URL}/{mls_number}"
            response = await page.goto(url, wait_until='domcontentloaded', timeout=10000)

            if response and response.status == 200:
                await page.wait_for_timeout(500)
                # Check if we're on a valid property page
                is_valid = await page.evaluate('''() => {
                    const hasPrice = document.querySelector('[class*="price"], .listing-price, .property-price');
                    const hasAddress = document.querySelector('[class*="address"], .property-address');
                    const isSearchPage = window.location.pathname.includes('search');
                    const is404 = document.body.innerText.includes('not found') ||
                                 document.body.innerText.includes('no longer available');
                    return (hasPrice || hasAddress) && !isSearchPage && !is404;
                }''')
                return is_valid
            return False
        except Exception:
            return False

    async def search_by_address(page, address):
        """Search for property by address, return MLS# if found."""
        try:
            search_query = address.replace(' ', '+')
            search_url = f"{IDX_BASE_URL}/search?q={search_query}"
            await page.goto(search_url, wait_until='domcontentloaded', timeout=10000)
            await page.wait_for_timeout(1500)

            # Find property link matching address
            result = await page.evaluate(f'''() => {{
                const searchAddress = "{address.lower().split(',')[0]}";
                const propertyLinks = document.querySelectorAll('a[href*="/property/"]');

                for (let link of propertyLinks) {{
                    const card = link.closest('.property-card, .listing, [class*="property"], [class*="listing"]');
                    const text = (card ? card.textContent : link.textContent).toLowerCase();

                    if (text.includes(searchAddress)) {{
                        const href = link.href || link.getAttribute('href');
                        const match = href.match(/\\/property\\/([A-Za-z0-9]+)/);
                        if (match) return match[1];
                    }}
                }}
                return null;
            }}''')
            return result
        except Exception:
            return None

    async def validate_all(props):
        """Validate all properties."""
        results = []
        playwright = None
        browser = None

        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            for prop in props:
                mls = prop.get('mls_number')
                address = prop.get('address')
                original_mls = mls
                idx_mls = None
                status = 'not_found'

                # First try the original MLS#
                if mls:
                    if await check_mls_on_idx(page, mls):
                        idx_mls = mls
                        status = 'validated'

                # If not found, try address search
                if not idx_mls and address:
                    found_mls = await search_by_address(page, address)
                    if found_mls:
                        idx_mls = found_mls
                        status = 'validated'

                results.append({
                    'address': address,
                    'original_mls': original_mls,
                    'idx_mls': idx_mls,
                    'status': status
                })

        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

        return results

    # Run validation
    try:
        results = asyncio.run(validate_all(properties))
        validated_count = sum(1 for r in results if r['status'] == 'validated')

        return jsonify({
            'success': True,
            'results': results,
            'validated_count': validated_count,
            'total_count': len(results)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/idx-portfolio', methods=['POST'])
@requires_auth
def create_idx_portfolio():
    """Launch IDX portfolio automation with selected MLS numbers (requires authentication)"""
    import time

    data = request.get_json()
    mls_numbers = data.get('mls_numbers', [])
    search_name = data.get('search_name', '')

    if not mls_numbers:
        return jsonify({'success': False, 'error': 'No MLS numbers provided'}), 400

    # Path to the launch script and progress file
    launch_script = os.path.join(os.path.dirname(__file__), 'launch_idx.sh')
    progress_file = os.path.join(os.path.dirname(__file__), 'logs', 'idx-progress.json')
    mls_string = ','.join(mls_numbers)

    # Clear old progress file to avoid race condition with polling
    try:
        with open(progress_file, 'w') as f:
            json.dump({
                "status": "initializing",
                "current": 0,
                "total": len(mls_numbers),
                "message": "Starting automation...",
                "error": ""
            }, f)
        logger.debug(f"Progress file initialized with {len(mls_numbers)} properties")
    except Exception as e:
        logger.error(f"Could not write progress file: {e}", exc_info=True)

    try:
        # Use shell script to properly detach the process
        # Pass search_name as second argument
        result = subprocess.run(
            [launch_script, mls_string, search_name],
            capture_output=True,
            text=True,
            timeout=5
        )

        pid = result.stdout.strip()

        # Wait briefly for automation to start and update progress
        time.sleep(0.5)

        # Build client portfolio URL if search_name looks like a client name
        client_url = None
        if search_name:
            # Extract client name from search_name (format: YYMMDD.HHMM.ClientName)
            parts = search_name.split('.')
            client_name = parts[-1] if len(parts) >= 3 else search_name
            # Build the shareable URL with the access key
            base_url = request.host_url.rstrip('/')
            client_url = f"{base_url}/client/{client_name}?key={CLIENT_PORTFOLIO_KEY}"

        return jsonify({
            'success': True,
            'message': f'Opening IDX portfolio with {len(mls_numbers)} properties',
            'mls_count': len(mls_numbers),
            'pid': pid,
            'client_url': client_url
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/idx-progress')
@requires_auth
def get_idx_progress():
    """Get current IDX portfolio automation progress (requires authentication)"""
    progress_file = os.path.join(os.path.dirname(__file__), 'logs', 'idx-progress.json')

    try:
        if os.path.exists(progress_file):
            with open(progress_file, 'r') as f:
                progress = json.load(f)
            return jsonify(progress)
        else:
            return jsonify({
                'status': 'idle',
                'message': 'No active portfolio creation'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
