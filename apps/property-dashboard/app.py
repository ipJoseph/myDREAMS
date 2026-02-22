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
import urllib.parse
from functools import wraps
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
from pathlib import Path
from typing import Any, Dict, List, Optional
from flask import Flask, render_template, render_template_string, request, jsonify, Response, redirect, url_for, send_from_directory
from dotenv import load_dotenv

# Module logger
logger = logging.getLogger(__name__)

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
load_dotenv(PROJECT_ROOT / '.env')

from src.core.database import DREAMSDatabase

# Import intelligence briefing engine
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from intelligence import generate_briefings, group_by_urgency, generate_overnight_narrative, generate_eod_narrative, generate_morning_summary
    INTELLIGENCE_AVAILABLE = True
except ImportError:
    INTELLIGENCE_AVAILABLE = False
    logger.warning("Intelligence module not available — Mission Control v3 will fall back to v2")

# Initialize database connection
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))
db = DREAMSDatabase(DB_PATH)

# Import task sync dashboard integration (optional - graceful degradation if not available)
try:
    from modules.task_sync import get_grouped_tasks, get_task_stats, get_tasks_by_project, get_active_deals
    TASK_SYNC_AVAILABLE = True
except ImportError:
    TASK_SYNC_AVAILABLE = False
    get_grouped_tasks = None
    get_task_stats = None
    get_tasks_by_project = None
    get_active_deals = None

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

# County GIS parcel lookup URLs for WNC counties
# Counties with direct parcel linking use {parcel} placeholder.
# Counties without direct linking go to their search page.
COUNTY_GIS_URLS = {
    'Macon': 'https://gis2.maconnc.org/lightmap/Maps/default.htm?pid={parcel}',
    'Buncombe': 'https://gis.buncombecounty.org/buncomap/Default.aspx?PINN={parcel}',
    'Jackson': 'https://gis.jacksonnc.org/rpv/',
    'Henderson': 'https://henderson.roktech.net/gomaps4/',
    'Haywood': 'https://taxes.haywoodcountync.gov/itspublic/appraisalcard.aspx?id={parcel}',
    'Swain': 'https://www.bttaxpayerportal.com/ITSPublicSW/BasicSearch/Parcel?id={parcel}',
    'Cherokee': 'https://maps.cherokeecounty-nc.gov/GISweb/GISviewer/',
    'Clay': 'https://bttaxpayerportal.com/ITSPublicCL/BasicSearch/Parcel?id={parcel}',
    'Graham': 'https://bttaxpayerportal.com/itspublicgr/BasicSearch.aspx',
}


# Custom Jinja2 filter for phone number formatting
@app.template_filter('phone')
def format_phone(value):
    """Format phone number as (XXX) XXX-XXXX"""
    if not value:
        return ''
    # Remove any non-digits
    digits = re.sub(r'\D', '', str(value))
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return value


@app.template_filter('eastern_time')
def filter_eastern_time(utc_str):
    """Convert a UTC timestamp string to Eastern 12-hour time."""
    if not utc_str:
        return ''
    try:
        dt = datetime.fromisoformat(str(utc_str).rstrip('Z'))
        # Determine EST/EDT offset
        d = dt.date()
        year = d.year
        from datetime import date as date_type
        mar1 = date_type(year, 3, 1)
        dst_start = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7)
        nov1 = date_type(year, 11, 1)
        dst_end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
        offset = timedelta(hours=-4) if dst_start <= d < dst_end else timedelta(hours=-5)
        et_dt = dt + offset
        return et_dt.strftime('%-I:%M %p')
    except (ValueError, TypeError):
        return str(utc_str)


@app.template_filter('format_call_duration')
def filter_format_call_duration(seconds):
    """Format call duration in seconds to M:SS or H:MM:SS."""
    if not seconds or seconds == 0:
        return ''
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# Basic Auth Configuration
DASHBOARD_USERNAME = os.getenv('DASHBOARD_USERNAME')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD')

# Environment detection (dev/prd) - defaults to 'dev'
DREAMS_ENV = os.getenv('DREAMS_ENV', 'dev').lower()

if not DASHBOARD_USERNAME or not DASHBOARD_PASSWORD:
    if DREAMS_ENV == 'prd':
        logger.critical("DASHBOARD_USERNAME/PASSWORD not set! Dashboard is running WITHOUT authentication in PRODUCTION.")
    else:
        logger.warning("DASHBOARD_USERNAME/PASSWORD not set. Dashboard authentication is disabled (dev mode).")

# Client Portfolio Password (simple key-based access)
CLIENT_PORTFOLIO_KEY = os.getenv('CLIENT_PORTFOLIO_KEY', 'dreams2026')

# Current user configuration (for filtering contacts)
CURRENT_USER_ID = int(os.getenv('FUB_MY_USER_ID', 8))  # Default: Joseph Williams
CURRENT_USER_NAME = os.getenv('FUB_MY_USER_NAME', 'Joseph Williams')
FUB_APP_URL = os.getenv('FUB_APP_URL', 'https://jontharpteam.followupboss.com')

# View definitions for contact filtering
CONTACT_VIEWS = {
    'my_leads':       {'label': 'My Leads',        'description': 'Your scored contacts'},
    'brand_new':      {'label': 'Brand New',        'description': 'Brand new leads (Pond)'},
    'hand_raised':    {'label': 'Hand Raised',      'description': 'Made inquiry — needs action (Pond)'},
    'warm_pond':      {'label': 'Warm Pond',        'description': 'Slipped off radar (Pond)'},
    'agents_vendors': {'label': 'Agents/Vendors',   'description': 'Agents, vendors, and lenders (Pond)'},
    'all':            {'label': 'All Contacts',     'description': 'Everyone in the database'},
}


@app.context_processor
def inject_globals():
    """Inject global variables into all templates"""
    return {
        'dreams_env': DREAMS_ENV,
        'favicon': f'/static/favicon-{DREAMS_ENV}.svg',
        'current_user_name': CURRENT_USER_NAME,
        'contact_views': CONTACT_VIEWS,
        'fub_url': FUB_APP_URL,
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


def _calculate_dom(prop: Dict) -> Optional[int]:
    """
    Calculate Days on Market from list_date.

    Priority:
    1. Calculate from list_date if available
    2. Fall back to stored days_on_market
    3. Calculate from created_at as last resort

    For non-active statuses (Sold, Withdrawn, etc.), use stored DOM as final value.
    """
    from datetime import datetime

    status = (prop.get('status') or '').lower()
    stored_dom = prop.get('days_on_market')

    # For sold/withdrawn/terminated properties, use the stored DOM (final value)
    if status in ('sold', 'withdrawn', 'terminated', 'expired', 'off market'):
        return stored_dom

    # For active listings, calculate DOM
    list_date_str = prop.get('list_date')
    if list_date_str:
        try:
            # Parse the list date (handle various formats)
            if 'T' in str(list_date_str):
                list_date = datetime.fromisoformat(list_date_str.replace('Z', '+00:00'))
            else:
                list_date = datetime.strptime(str(list_date_str)[:10], '%Y-%m-%d')
            dom = (datetime.now() - list_date.replace(tzinfo=None)).days
            return max(0, dom)  # Ensure non-negative
        except (ValueError, TypeError):
            pass

    # Fall back to stored DOM
    if stored_dom is not None:
        return stored_dom

    # Last resort: calculate from created_at
    created_at_str = prop.get('created_at')
    if created_at_str:
        try:
            if 'T' in str(created_at_str):
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            else:
                created_at = datetime.strptime(str(created_at_str)[:10], '%Y-%m-%d')
            dom = (datetime.now() - created_at.replace(tzinfo=None)).days
            return max(0, dom)
        except (ValueError, TypeError):
            pass

    return None


def get_filter_options() -> Dict[str, Any]:
    """Get distinct values for filter dropdowns - efficient single query approach"""
    with db._get_connection() as conn:
        options: Dict[str, Any] = {}
        table = 'listings'

        # Use indexed columns with DISTINCT for fast retrieval
        options['clients'] = sorted([r[0] for r in conn.execute(
            f"SELECT DISTINCT added_for FROM {table} WHERE added_for IS NOT NULL AND added_for != ''"
        ).fetchall()])
        options['cities'] = sorted([r[0] for r in conn.execute(
            f"SELECT DISTINCT city FROM {table} WHERE city IS NOT NULL AND city != ''"
        ).fetchall()])
        options['counties'] = sorted([r[0] for r in conn.execute(
            f"SELECT DISTINCT county FROM {table} WHERE county IS NOT NULL AND county != ''"
        ).fetchall()])
        options['statuses'] = sorted([r[0] for r in conn.execute(
            f"SELECT DISTINCT status FROM {table} WHERE status IS NOT NULL AND status != ''"
        ).fetchall()])

        # County -> cities mapping for cascade filtering
        county_cities: Dict[str, List[str]] = {}
        rows = conn.execute(
            f"SELECT DISTINCT county, city FROM {table} "
            f"WHERE county IS NOT NULL AND county != '' AND city IS NOT NULL AND city != '' "
            f"ORDER BY county, city"
        ).fetchall()
        for county, city in rows:
            county_cities.setdefault(county, []).append(city)
        options['county_cities'] = county_cities

        return options


def _build_multi_where(query: str, params: list, column: str, value: str, use_like: bool = False) -> str:
    """Build WHERE clause for a potentially comma-separated multi-value filter.
    Returns updated query string; modifies params list in place."""
    if not value:
        return query
    values = [v.strip() for v in value.split(',') if v.strip()]
    if not values:
        return query
    if len(values) == 1:
        if use_like:
            query += f' AND {column} LIKE ?'
            params.append(f'%{values[0]}%')
        else:
            query += f' AND LOWER({column}) = LOWER(?)'
            params.append(values[0])
    else:
        if use_like:
            # Multiple LIKE conditions joined with OR
            likes = ' OR '.join([f'{column} LIKE ?' for _ in values])
            query += f' AND ({likes})'
            params.extend([f'%{v}%' for v in values])
        else:
            placeholders = ','.join(['LOWER(?)'] * len(values))
            query += f' AND LOWER({column}) IN ({placeholders})'
            params.extend(values)
    return query


def count_properties(added_for: Optional[str] = None, status: Optional[str] = None,
                     city: Optional[str] = None, county: Optional[str] = None,
                     q: Optional[str] = None, min_price: Optional[int] = None,
                     max_price: Optional[int] = None, min_beds: Optional[int] = None) -> int:
    """Count properties matching filters (for pagination)"""
    with db._get_connection() as conn:
        table = 'listings'

        query = f'SELECT COUNT(*) FROM {table} WHERE 1=1'
        params = []

        if added_for:
            query += ' AND added_for LIKE ?'
            params.append(f'%{added_for}%')
        if status:
            query += ' AND LOWER(status) = LOWER(?)'
            params.append(status)
        query = _build_multi_where(query, params, 'city', city)
        query = _build_multi_where(query, params, 'county', county, use_like=True)
        if q:
            query += ' AND (address LIKE ? OR mls_number LIKE ? OR city LIKE ? OR listing_agent_name LIKE ?)'
            q_param = f'%{q}%'
            params.extend([q_param, q_param, q_param, q_param])
        if min_price is not None:
            query += ' AND list_price >= ?'
            params.append(min_price)
        if max_price is not None:
            query += ' AND list_price <= ?'
            params.append(max_price)
        if min_beds is not None:
            query += ' AND beds >= ?'
            params.append(min_beds)

        return conn.execute(query, params).fetchone()[0]


def fetch_properties(added_for: Optional[str] = None, status: Optional[str] = None,
                      city: Optional[str] = None, county: Optional[str] = None,
                      sort_by: str = 'price', sort_order: str = 'desc',
                      limit: Optional[int] = None, offset: int = 0,
                      q: Optional[str] = None, min_price: Optional[int] = None,
                      max_price: Optional[int] = None, min_beds: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch properties from listings table with optional filters, sorting, and pagination"""
    # Whitelist of allowed sort columns (prevents SQL injection)
    ALLOWED_SORTS = {
        'price': 'list_price', 'address': 'address', 'city': 'city', 'county': 'county',
        'beds': 'beds', 'baths': 'baths', 'sqft': 'sqft', 'acreage': 'acreage',
        'status': 'status', 'dom': 'days_on_market', 'year_built': 'year_built',
        'created_at': 'captured_at', 'mls_number': 'mls_number'
    }
    sort_column = ALLOWED_SORTS.get(sort_by, 'list_price')
    sort_dir = 'ASC' if sort_order == 'asc' else 'DESC'

    with db._get_connection() as conn:
        table = 'listings'

        query = f'SELECT * FROM {table} WHERE 1=1'
        params = []

        if added_for:
            query += ' AND added_for LIKE ?'
            params.append(f'%{added_for}%')

        if status:
            query += ' AND LOWER(status) = LOWER(?)'
            params.append(status)

        query = _build_multi_where(query, params, 'city', city)
        query = _build_multi_where(query, params, 'county', county, use_like=True)

        if q:
            query += ' AND (address LIKE ? OR mls_number LIKE ? OR city LIKE ? OR listing_agent_name LIKE ?)'
            q_param = f'%{q}%'
            params.extend([q_param, q_param, q_param, q_param])

        if min_price is not None:
            query += ' AND list_price >= ?'
            params.append(min_price)

        if max_price is not None:
            query += ' AND list_price <= ?'
            params.append(max_price)

        if min_beds is not None:
            query += ' AND beds >= ?'
            params.append(min_beds)

        # Server-side sorting with NULLS LAST behavior
        query += f' ORDER BY {sort_column} IS NULL, {sort_column} {sort_dir}'

        # Pagination
        if limit:
            query += f' LIMIT {int(limit)} OFFSET {int(offset)}'

        rows = conn.execute(query, params).fetchall()

        # Convert to list of dicts and normalize field names for templates
        properties = []
        for row in rows:
            prop = dict(row)
            # Normalize list_price to price for template compatibility
            prop['price'] = prop.get('list_price')

            # Calculate price per sqft
            price = prop.get('price')
            sqft = prop.get('sqft')
            prop['price_per_sqft'] = round(price / sqft, 2) if price and sqft and sqft > 0 else None

            # Normalize field names for template compatibility
            prop['beds'] = prop.get('beds')
            prop['baths'] = prop.get('baths')
            prop['lot_acres'] = prop.get('acreage')

            # Calculate DOM from list_date (preferred) or fall back to stored days_on_market
            prop['dom'] = _calculate_dom(prop)

            prop['tax_annual'] = None
            prop['hoa'] = prop.get('hoa_fee')
            prop['date_saved'] = prop.get('captured_at')
            prop['last_updated'] = prop.get('updated_at')
            prop['photo_url'] = prop.get('primary_photo')
            prop['favorites'] = None

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

    # ===== VERSION TOGGLE =====
    # v3 (Mission Control) is default; ?v2=1 rolls back
    use_v2 = request.args.get('v2', '0') == '1'

    # ===== V3 MISSION CONTROL =====
    if not use_v2 and INTELLIGENCE_AVAILABLE:
        try:
            # Enriched contacts with subquery-computed intelligence fields
            contacts = db.get_morning_briefing_contacts(user_id=CURRENT_USER_ID, limit=30)

            # Generate intelligence briefings for each contact
            contacts = generate_briefings(contacts)
            contact_groups = group_by_urgency(contacts)

            # Overnight narrative (names, not counts)
            overnight_data = db.get_overnight_narrative(hours=24, user_id=CURRENT_USER_ID)
            narrative_items = generate_overnight_narrative(overnight_data)

            # Pipeline narrative
            pipeline = db.get_pipeline_narrative(user_id=CURRENT_USER_ID)

            # Today's call stats
            call_stats = db.get_todays_call_stats(user_id=CURRENT_USER_ID)

            # Live activity feed (compact, for Briefing + Command Center)
            live_feed = db.get_live_activity_feed(hours=8, limit=20)

            # Morning Pulse metrics (business health strip)
            pulse_metrics = db.get_morning_pulse_metrics(user_id=CURRENT_USER_ID)
            pulse_metrics['contacts_ready'] = len(contacts)

            # Activity summary (aggregate overnight stats)
            activity_summary = db.get_activity_summary(hours=24)

            # Morning summary sentence
            morning_summary = generate_morning_summary(contacts, pipeline, activity_summary)

            # Reassigned leads (alerts)
            reassigned_leads = db.get_recently_reassigned_leads(
                from_user_id=CURRENT_USER_ID, days=7
            )

            # New leads with source grouping (for Overnight Intelligence)
            new_leads_detail = db.get_recent_contacts(days=1, user_id=CURRENT_USER_ID)

            # Pre-serialize contacts for Power Hour JS
            contacts_json = json.dumps(contacts, default=str)

            return render_template('home_v3.html',
                                 contacts=contacts,
                                 contacts_json=contacts_json,
                                 contact_groups=contact_groups,
                                 narrative_items=narrative_items,
                                 pipeline=pipeline,
                                 call_stats=call_stats,
                                 live_feed=live_feed,
                                 pulse_metrics=pulse_metrics,
                                 activity_summary=activity_summary,
                                 morning_summary=morning_summary,
                                 reassigned_leads=reassigned_leads,
                                 new_leads_detail=new_leads_detail,
                                 current_user_id=CURRENT_USER_ID,
                                 refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))
        except Exception as e:
            logger.error(f"Mission Control v3 failed, falling back to v2: {e}", exc_info=True)
            # Fall through to v2

    # Get view filter from query params (default to 'my_leads')
    current_view = request.args.get('view', 'my_leads')
    if current_view not in CONTACT_VIEWS:
        current_view = 'my_leads'

    # ===== PRIORITY ACTIONS =====
    # Today's calls, follow-ups, and buyers needing property updates
    todays_actions = db.get_todays_actions(user_id=CURRENT_USER_ID, limit=10)

    # ===== TODOIST TASKS =====
    # Fetch tasks from Todoist grouped by project
    todoist_tasks = {'projects': [], 'total_count': 0, 'overdue_count': 0}
    active_deals = []
    if TASK_SYNC_AVAILABLE:
        try:
            todoist_tasks = get_tasks_by_project(limit=20)
        except Exception as e:
            logger.warning(f"Failed to fetch Todoist tasks: {e}")
        try:
            active_deals = get_active_deals()
        except Exception as e:
            logger.warning(f"Failed to fetch active deals: {e}")

    # ===== PIPELINE SNAPSHOT =====
    # Dual-input funnel: Leads + Properties -> Pursuits -> Contracts
    pipeline = db.get_pipeline_snapshot(user_id=CURRENT_USER_ID)

    # ===== HOTTEST LEADS =====
    hottest_leads = db.get_hottest_leads(limit=8, user_id=CURRENT_USER_ID)

    # ===== OVERNIGHT CHANGES =====
    # New leads, price drops, status changes, going cold
    overnight = db.get_overnight_changes(hours=24)

    # ===== ACTIVE PURSUITS =====
    # Buyer + property portfolio combinations
    active_pursuits = db.get_active_pursuits(limit=5)

    # ===== BUYERS NEEDING PROPERTY WORK =====
    # Buyers in CURATE phase with requirements but no recent packages
    buyers_needing_work = db.get_buyers_needing_property_work(user_id=CURRENT_USER_ID, limit=5)

    # ===== CALL LIST DATA (for v2 embedded call list) =====
    call_list_data = {}
    call_list_counts = {}
    for list_type in ('priority', 'new_leads', 'hot', 'follow_up', 'going_cold'):
        call_list_counts[list_type] = db.count_call_list_contacts(list_type, user_id=CURRENT_USER_ID)
        call_list_data[list_type] = db.get_call_list_contacts(list_type, user_id=CURRENT_USER_ID, limit=25)

    # ===== V2 DASHBOARD =====
    if True:
        return render_template('home_v2.html',
                             todays_actions=todays_actions,
                             todoist_tasks=todoist_tasks,
                             active_deals=active_deals,
                             pipeline=pipeline,
                             hottest_leads=hottest_leads,
                             overnight=overnight,
                             active_pursuits=active_pursuits,
                             buyers_needing_work=buyers_needing_work,
                             call_list_data=call_list_data,
                             call_list_counts=call_list_counts,
                             refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))

    # ===== LEGACY DATA (for v1 backward compatibility) =====
    # Get property stats
    all_properties = fetch_properties()
    property_metrics = calculate_metrics(all_properties)

    property_stats = {
        'total': len(all_properties),
        'status_counts': calculate_status_counts(all_properties),
        'avg_price': "${:,.0f}".format(property_metrics.get('avg_price', 0)) if property_metrics.get('avg_price') else '--'
    }

    # Get contact stats (filtered by view)
    contact_stats = db.get_contact_stats(user_id=CURRENT_USER_ID, view=current_view)

    # Get top priority contacts (filtered by view)
    top_contacts = db.get_contacts_by_priority(
        min_priority=0,
        limit=10,
        user_id=CURRENT_USER_ID,
        view=current_view
    )

    # Count actions due
    actions_due = len(todays_actions.get('calls', [])) + len(todays_actions.get('follow_ups', []))

    # Get today's property changes
    todays_changes = db.get_todays_changes()
    change_summary = db.get_change_summary(hours=24)

    return render_template('home.html',
                         # New dashboard data
                         todays_actions=todays_actions,
                         todoist_tasks=todoist_tasks,
                         active_deals=active_deals,
                         pipeline=pipeline,
                         hottest_leads=hottest_leads,
                         overnight=overnight,
                         active_pursuits=active_pursuits,
                         buyers_needing_work=buyers_needing_work,
                         # Legacy data
                         property_stats=property_stats,
                         contact_stats=contact_stats,
                         top_contacts=top_contacts,
                         actions_due=actions_due,
                         todays_changes=todays_changes,
                         change_summary=change_summary,
                         current_view=current_view,
                         refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


# ═══════════════════════════════════════════════════════════════
# END OF DAY REPORT
# ═══════════════════════════════════════════════════════════════

@app.route('/eod')
@requires_auth
def end_of_day():
    """End of Day Report — daily accountability and review."""
    db = get_db()
    eod_data = db.get_end_of_day_report(user_id=CURRENT_USER_ID)
    eod_narrative = generate_eod_narrative(eod_data) if INTELLIGENCE_AVAILABLE else {}
    return render_template('eod_report.html',
                         eod=eod_data, narrative=eod_narrative,
                         active_nav='eod',
                         refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


REPORTS_DIR = PROJECT_ROOT / 'reports'

# Import report generator (for on-demand generation)
try:
    sys.path.insert(0, str(REPORTS_DIR))
    from generate_calls_report import generate_date_range_report, sync_calls_from_fub
    REPORT_GENERATOR_AVAILABLE = True
except ImportError:
    REPORT_GENERATOR_AVAILABLE = False
    logger.warning("generate_calls_report not available; report generation disabled")


def _format_file_size(size_bytes):
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


@app.route('/reports/')
@requires_auth
def reports_index():
    """Reports hub with generator UI and saved reports list."""
    reports = []
    if REPORTS_DIR.is_dir():
        for f in sorted(REPORTS_DIR.glob('*.html'), reverse=True):
            stat = f.stat()
            reports.append({
                'name': f.name,
                'size': _format_file_size(stat.st_size),
                'modified': datetime.fromtimestamp(stat.st_mtime, tz=ET).strftime('%b %d, %Y %I:%M %p'),
            })

    return render_template('reports.html',
                         reports=reports,
                         active_nav='reports',
                         refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


@app.route('/api/reports/generate-calls', methods=['POST'])
@requires_auth
def api_generate_calls_report():
    """Generate a call activity report for a date range."""
    if not REPORT_GENERATOR_AVAILABLE:
        return jsonify({'success': False, 'error': 'Report generator not available'}), 500

    data = request.get_json() or {}
    start_str = data.get('start_date', '').strip()
    end_str = data.get('end_date', '').strip()

    if not start_str:
        return jsonify({'success': False, 'error': 'start_date is required'}), 400

    try:
        from datetime import date as date_type
        start_date = date_type.fromisoformat(start_str)
        end_date = date_type.fromisoformat(end_str) if end_str else start_date
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format (expected YYYY-MM-DD)'}), 400

    # If the date range includes today, sync fresh calls from FUB first
    if end_date >= date_type.today():
        try:
            count = sync_calls_from_fub(DB_PATH, start_date.isoformat())
            if count >= 0:
                logger.info(f"Live FUB sync: {count} new calls synced before report generation")
        except Exception as e:
            logger.warning(f"FUB call sync failed, generating report with existing data: {e}")

    try:
        output_file = generate_date_range_report(
            db_path=DB_PATH,
            start_date=start_date,
            end_date=end_date,
            output_dir=str(REPORTS_DIR)
        )
        filename = Path(output_file).name
        return jsonify({
            'success': True,
            'filename': filename,
            'url': f'/reports/{filename}'
        })
    except (ValueError, FileNotFoundError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/reports/<path:filename>')
@requires_auth
def serve_report(filename):
    """Serve a static HTML report file."""
    safe_name = Path(filename).name  # prevent directory traversal
    return send_from_directory(str(REPORTS_DIR), safe_name)


# ═══════════════════════════════════════════════════════════════
# MISSION CONTROL: Power Hour & Live Activity API Endpoints
# ═══════════════════════════════════════════════════════════════

@app.route('/api/power-hour/start', methods=['POST'])
@requires_auth
def api_power_hour_start():
    """Start a new Power Hour session."""
    db = get_db()
    data = request.get_json() or {}
    user_id = data.get('user_id', CURRENT_USER_ID)
    session_id = db.create_power_hour_session(user_id)
    return jsonify({'session_id': session_id, 'status': 'active'})


@app.route('/api/power-hour/disposition', methods=['POST'])
@requires_auth
def api_power_hour_disposition():
    """Record a call disposition within a Power Hour session."""
    db = get_db()
    data = request.get_json() or {}
    session_id = data.get('session_id')
    contact_id = data.get('contact_id')
    disposition = data.get('disposition')

    if not all([session_id, contact_id, disposition]):
        return jsonify({'error': 'Missing required fields'}), 400

    valid_dispositions = ('called', 'left_vm', 'texted', 'no_answer', 'skip', 'appointment')
    if disposition not in valid_dispositions:
        return jsonify({'error': 'Invalid disposition'}), 400

    dispo_id = db.record_power_hour_disposition(
        session_id=session_id,
        contact_id=contact_id,
        disposition=disposition,
        notes=data.get('notes')
    )
    return jsonify({'id': dispo_id, 'status': 'recorded'})


@app.route('/api/power-hour/end', methods=['POST'])
@requires_auth
def api_power_hour_end():
    """End a Power Hour session and return summary stats."""
    db = get_db()
    data = request.get_json() or {}
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400

    summary = db.end_power_hour_session(session_id)
    return jsonify(summary)


def _fub_briefing_text(contact, list_key):
    """Generate one-liner briefing context for a FUB contact."""
    days = contact.get('lastCommDays')
    days_text = f"Last contact {days} days ago." if days is not None else "No contact history."
    briefings = {
        'new_leads': f"New lead. {days_text}",
        'priority': f"Hot Prospect. {days_text}",
        'hot': f"0-3 month timeframe. {days_text}",
        'warm': f"3-6 month timeframe. {days_text}",
        'cool': f"6+ month timeframe. {days_text}",
        'unresponsive': f"Unresponsive lead. {days_text}",
        'timeframe_empty': "Nurture — no timeframe set yet.",
    }
    return briefings.get(list_key, days_text)


def _batch_fub_activity_stats(db, fub_ids: list) -> dict:
    """Batch-fetch activity stats for FUB contacts from DREAMS database.
    Returns dict keyed by fub_id string with views, favorites, cities, comms."""
    if not fub_ids:
        return {}
    try:
        conn = db._get_connection()
        cutoff_24h = (datetime.now() - timedelta(hours=24)).isoformat()
        cutoff_7d = (datetime.now() - timedelta(days=7)).isoformat()
        placeholders = ','.join('?' * len(fub_ids))

        # Property views 24h and 7d
        views = {}
        rows = conn.execute(f'''
            SELECT contact_id,
                   SUM(CASE WHEN occurred_at >= ? THEN 1 ELSE 0 END) AS views_24h,
                   COUNT(*) AS views_7d
            FROM contact_events
            WHERE contact_id IN ({placeholders})
            AND event_type = 'property_view'
            AND occurred_at >= ?
            GROUP BY contact_id
        ''', [cutoff_24h] + fub_ids + [cutoff_7d]).fetchall()
        for r in rows:
            views[r['contact_id']] = {'views_24h': r['views_24h'], 'views_7d': r['views_7d']}

        # Favorites 7d
        fav_rows = conn.execute(f'''
            SELECT contact_id, COUNT(*) AS cnt
            FROM contact_events
            WHERE contact_id IN ({placeholders})
            AND event_type = 'property_favorite'
            AND occurred_at >= ?
            GROUP BY contact_id
        ''', fub_ids + [cutoff_7d]).fetchall()

        # Recent cities from property views
        city_rows = conn.execute(f'''
            SELECT ce.contact_id, COALESCE(ic.city, 'Unknown') AS city, COUNT(*) AS cnt
            FROM contact_events ce
            LEFT JOIN idx_property_cache ic ON ce.property_mls = ic.mls_number
            WHERE ce.contact_id IN ({placeholders})
            AND ce.event_type = 'property_view'
            AND ce.occurred_at >= ?
            AND ic.city IS NOT NULL
            GROUP BY ce.contact_id, ic.city
            ORDER BY cnt DESC
        ''', fub_ids + [cutoff_7d]).fetchall()

        # Days since last communication (need lead IDs)
        lead_rows = conn.execute(f'''
            SELECT fub_id, id FROM leads WHERE CAST(fub_id AS TEXT) IN ({placeholders})
        ''', fub_ids).fetchall()
        lead_map = {str(r['fub_id']): r['id'] for r in lead_rows}

        comm_stats = {}
        if lead_map:
            lead_ids = list(lead_map.values())
            lp = ','.join('?' * len(lead_ids))
            comm_rows = conn.execute(f'''
                SELECT contact_id,
                       CAST(julianday('now') - julianday(MAX(occurred_at)) AS INTEGER) AS days_since
                FROM contact_communications
                WHERE contact_id IN ({lp})
                GROUP BY contact_id
            ''', lead_ids).fetchall()
            # Map lead_id back to fub_id
            lead_to_fub = {v: k for k, v in lead_map.items()}
            for r in comm_rows:
                fub_key = lead_to_fub.get(r['contact_id'])
                if fub_key:
                    comm_stats[fub_key] = r['days_since']

        # Distinct property view counts (for intel tab badge)
        pv_counts = {}
        pv_rows = conn.execute(f'''
            SELECT contact_id, COUNT(DISTINCT COALESCE(property_mls, property_address)) AS cnt
            FROM contact_events
            WHERE contact_id IN ({placeholders})
            AND event_type IN ('property_view', 'property_favorite', 'property_share')
            GROUP BY contact_id
        ''', fub_ids).fetchall()
        for r in pv_rows:
            pv_counts[r['contact_id']] = r['cnt']

        # Intake form counts (for intel tab badge)
        intake_counts = {}
        if lead_map:
            lead_ids = list(lead_map.values())
            lp2 = ','.join('?' * len(lead_ids))
            fp2 = ','.join('?' * len(fub_ids))
            intake_rows = conn.execute(f'''
                SELECT lead_id, COUNT(*) AS cnt FROM intake_forms
                WHERE lead_id IN ({lp2}) OR lead_id IN ({fp2})
                GROUP BY lead_id
            ''', lead_ids + fub_ids).fetchall()
            # Map back to fub_id
            lead_to_fub2 = {v: k for k, v in lead_map.items()}
            for r in intake_rows:
                fub_key = lead_to_fub2.get(r['lead_id']) or r['lead_id']
                intake_counts[fub_key] = intake_counts.get(fub_key, 0) + r['cnt']

        # Build result dict
        result = {}
        city_map = {}
        for r in city_rows:
            cid = r['contact_id']
            if cid not in city_map:
                city_map[cid] = []
            if len(city_map[cid]) < 3:
                city_map[cid].append(r['city'])

        for fid in fub_ids:
            v = views.get(fid, {})
            result[fid] = {
                'views_24h': v.get('views_24h', 0),
                'views_7d': v.get('views_7d', 0),
                'favorites_7d': 0,
                'recent_cities': city_map.get(fid, []),
                'days_since_last_comm': comm_stats.get(fid),
                'property_view_count': pv_counts.get(fid, 0),
                'intake_count': intake_counts.get(fid, 0),
            }

        for r in fav_rows:
            if r['contact_id'] in result:
                result[r['contact_id']]['favorites_7d'] = r['cnt']

        return result
    except Exception as e:
        logger.warning(f"Batch FUB activity stats failed: {e}")
        return {}


@app.route('/api/power-hour/fub-queue/<dreams_key>')
@requires_auth
def api_power_hour_fub_queue(dreams_key):
    """Fetch FUB smart list contacts formatted for Power Hour."""
    valid_keys = [v['dreams_key'] for v in SMART_LIST_MAP.values()]
    if dreams_key not in valid_keys:
        return jsonify({'success': False, 'error': 'Invalid list'}), 400

    client = _get_fub_client()
    if not client:
        return jsonify({'success': False, 'error': 'FUB API not configured'}), 500

    people = []
    for stage in ('Lead', 'Nurture', 'Hot Prospect'):
        batch = client.fetch_collection(
            "/people", "people",
            {"assignedUserId": CURRENT_USER_ID, "stage": stage, "fields": "allFields"},
            use_cache=False)
        people.extend(batch)

    buckets = _bucket_fub_contacts(people)
    contacts = buckets.get(dreams_key, [])

    # Cross-reference FUB contacts with DREAMS database for enrichment
    db = get_db()

    # Batch-fetch activity stats for all FUB contacts that exist in DREAMS
    fub_ids_str = [str(c['id']) for c in contacts]
    activity_stats = _batch_fub_activity_stats(db, fub_ids_str)

    ph_contacts = []
    for c in contacts:
        parts = c['name'].split(' ', 1) if c.get('name') else ['', '']
        fub_id = c['id']

        # Look up DREAMS enrichment data by FUB ID
        dreams_contact = db.get_contact_by_fub_id(str(fub_id))

        ph = {
            'id': f"fub_{fub_id}",
            'fub_id': fub_id,
            'first_name': parts[0],
            'last_name': parts[1] if len(parts) > 1 else '',
            'phone': c.get('phone', ''),
            'stage': c.get('stage', ''),
            'heat_score': None,
            'value_score': None,
            'priority_score': None,
            'score_trend': None,
            'heat_delta': None,
            'price_range_label': None,
            'recent_cities': [],
            'email': None,
            'source': 'fub',
            'fub_list': dreams_key,
            'lastCommDays': c.get('lastCommDays'),
            'timeframeStatus': c.get('timeframeStatus'),
            'financing_status': None,
            'pre_approval_amount': None,
            'intent_signal_count': None,
            'intent_repeat_views': None,
            'intent_sharing': None,
            'days_since_activity': None,
            'created_at': None,
            'property_views_24h': 0,
            'property_views_7d': 0,
            'favorites_7d': 0,
        }

        # Merge DREAMS data if contact exists in our database
        if dreams_contact:
            dc = dreams_contact
            ph['id'] = dc.get('id', ph['id'])
            ph['email'] = dc.get('email') or None
            ph['heat_score'] = dc.get('heat_score')
            ph['value_score'] = dc.get('value_score')
            ph['priority_score'] = dc.get('priority_score')
            ph['score_trend'] = dc.get('score_trend')
            ph['days_since_activity'] = dc.get('days_since_activity')
            ph['created_at'] = dc.get('created_at')
            ph['intent_signal_count'] = dc.get('intent_signal_count')
            ph['intent_repeat_views'] = dc.get('intent_repeat_views')
            ph['intent_sharing'] = dc.get('intent_sharing')
            # Price range
            min_p = dc.get('min_price')
            max_p = dc.get('max_price')
            if min_p and max_p:
                ph['price_range_label'] = f"${min_p // 1000}K-${max_p // 1000}K"
            elif max_p:
                ph['price_range_label'] = f"up to ${max_p // 1000}K"
            elif min_p:
                ph['price_range_label'] = f"${min_p // 1000}K+"
            # Cities from preferred_cities field
            if dc.get('preferred_cities'):
                try:
                    cities = json.loads(dc['preferred_cities']) if isinstance(dc['preferred_cities'], str) else dc['preferred_cities']
                    ph['recent_cities'] = cities if isinstance(cities, list) else []
                except (json.JSONDecodeError, TypeError):
                    ph['recent_cities'] = []

        # Merge batch activity stats (property views, cities, comms)
        fub_key = str(fub_id)
        stats = activity_stats.get(fub_key, {})
        if stats:
            ph['property_views_24h'] = stats.get('views_24h', 0)
            ph['property_views_7d'] = stats.get('views_7d', 0)
            ph['favorites_7d'] = stats.get('favorites_7d', 0)
            ph['days_since_last_comm'] = stats.get('days_since_last_comm')
            ph['property_view_count'] = stats.get('property_view_count', 0)
            ph['intake_count'] = stats.get('intake_count', 0)
            # Override cities with event-based cities if available
            if stats.get('recent_cities'):
                ph['recent_cities'] = stats['recent_cities']

        # Generate intelligence briefing (same engine as DREAMS Priority)
        if INTELLIGENCE_AVAILABLE and dreams_contact:
            try:
                from intelligence import generate_briefing
                ph['briefing'] = generate_briefing(ph)
            except Exception:
                ph['briefing'] = {'text': _fub_briefing_text(c, dreams_key)}
        else:
            ph['briefing'] = {'text': _fub_briefing_text(c, dreams_key)}

        ph_contacts.append(ph)

    return jsonify({'success': True, 'contacts': ph_contacts, 'count': len(ph_contacts)})


@app.route('/api/live-activity')
@requires_auth
def api_live_activity():
    """Live activity feed for Command Center (polled every 60s)."""
    db = get_db()
    events = db.get_live_activity_feed(hours=8, limit=20)
    return jsonify({'events': events})


@app.route('/call-list')
@requires_auth
def call_list():
    """Call List view - contacts ready to call with quick actions."""
    db = get_db()

    # Get list type from query params
    current_list = request.args.get('list', 'priority')

    # Get counts for all lists
    counts = {
        'priority': db.count_call_list_contacts('priority', user_id=CURRENT_USER_ID),
        'new_leads': db.count_call_list_contacts('new_leads', user_id=CURRENT_USER_ID),
        'hot': db.count_call_list_contacts('hot', user_id=CURRENT_USER_ID),
        'follow_up': db.count_call_list_contacts('follow_up', user_id=CURRENT_USER_ID),
        'going_cold': db.count_call_list_contacts('going_cold', user_id=CURRENT_USER_ID),
    }

    # Get contacts for current list
    contacts = db.get_call_list_contacts(current_list, user_id=CURRENT_USER_ID, limit=50)

    return render_template('call_list.html',
                         contacts=contacts,
                         current_list=current_list,
                         counts=counts)


@app.route('/fub-list')
@requires_auth
def fub_list():
    """FUB-style call list grouped by category."""
    return render_template('fub_list.html')


@app.route('/api/fub-list')
@requires_auth
def api_fub_list():
    """API endpoint returning FUB list data as JSON for live refresh."""
    db = get_db()
    lists = db.get_fub_style_lists(user_id=CURRENT_USER_ID, limit=50)

    # Convert to serializable format and add totals
    result = {}
    total = 0
    for key, contacts in lists.items():
        result[key] = []
        for c in contacts:
            result[key].append({
                'id': c['id'],
                'first_name': c['first_name'],
                'last_name': c['last_name'],
                'phone': c.get('phone'),
                'stage': c.get('stage'),
                'heat_score': c.get('heat_score'),
                'priority_score': c.get('priority_score'),
                'relationship_score': c.get('relationship_score'),
                'fub_id': c.get('fub_id'),
            })
        total += len(contacts)

    return jsonify({
        'success': True,
        'lists': result,
        'total': total,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


@app.route('/pursuits')
@requires_auth
def pursuits_list():
    """Pursuits list view - Buyer + Property portfolios"""
    db = get_db()

    # Get all pursuits with details
    pursuits = db.get_all_pursuits()

    # Get buyers who could become pursuits (qualified but no pursuit yet)
    potential_buyers = db.get_potential_pursuit_buyers()

    return render_template('pursuits.html',
                         pursuits=pursuits,
                         potential_buyers=potential_buyers,
                         refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


@app.route('/pursuits/create', methods=['POST'])
@requires_auth
def create_pursuit():
    """Create a new pursuit from a buyer"""
    db = get_db()

    buyer_id = request.form.get('buyer_id')
    name = request.form.get('name')
    criteria_summary = request.form.get('criteria_summary')

    if not buyer_id:
        return jsonify({'error': 'buyer_id required'}), 400

    pursuit_id = db.create_pursuit(
        buyer_id=buyer_id,
        name=name,
        criteria_summary=criteria_summary
    )

    return redirect(url_for('pursuits_list'))


@app.route('/properties')
@requires_auth
def properties_list():
    """Property list view (requires authentication)"""
    # Get filter parameters
    added_for = request.args.get('client', '')
    status = request.args.get('status', '')
    city = request.args.get('city', '')  # comma-separated for multi-select
    county = request.args.get('county', '')  # comma-separated for multi-select
    show_all = request.args.get('show_all', '')
    q = request.args.get('q', '').strip()
    view_mode = request.args.get('view', 'cards')

    # Parse numeric filter params safely
    try:
        min_price = int(request.args.get('min_price', '')) if request.args.get('min_price') else None
    except ValueError:
        min_price = None
    try:
        max_price = int(request.args.get('max_price', '')) if request.args.get('max_price') else None
    except ValueError:
        max_price = None
    try:
        min_beds = int(request.args.get('min_beds', '')) if request.args.get('min_beds') else None
    except ValueError:
        min_beds = None

    # Pagination: 48 for cards, 100 for table
    page = max(1, int(request.args.get('page', 1)))
    per_page = 48 if view_mode == 'cards' else 100

    # Sort parameters (server-side sorting for performance)
    sort_by = request.args.get('sort', 'price')
    sort_order = request.args.get('order', 'desc')

    # Default to Active status for nimble loading (unless show_all or other filter set)
    if not status and not show_all and not added_for and not q:
        status = 'Active'

    # Get dropdown options efficiently (uses indexed DISTINCT queries)
    filter_options = get_filter_options()
    clients = filter_options['clients']
    cities = filter_options['cities']
    counties = filter_options['counties']
    statuses = filter_options['statuses']
    county_cities = filter_options['county_cities']

    # Common filter kwargs
    filter_kwargs = dict(
        added_for=added_for if added_for else None,
        status=status if status else None,
        city=city if city else None,
        county=county if county else None,
        q=q if q else None,
        min_price=min_price,
        max_price=max_price,
        min_beds=min_beds,
    )

    # Get total count for pagination
    total_count = count_properties(**filter_kwargs)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    # Fetch filtered, sorted, paginated properties
    properties = fetch_properties(
        **filter_kwargs,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=per_page,
        offset=offset
    )

    # Enrich with IDX photos for properties without Notion photos
    properties = enrich_properties_with_idx_photos(properties)

    # Calculate metrics on current page
    metrics = calculate_metrics(properties)
    metrics['status_counts'] = {}

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
                         show_all=show_all,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         page=page,
                         total_pages=total_pages,
                         total_count=total_count,
                         per_page=per_page,
                         search_query=q,
                         selected_min_price=min_price,
                         selected_max_price=max_price,
                         selected_min_beds=min_beds,
                         view_mode=view_mode,
                         county_cities=county_cities,
                         refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


@app.route('/properties/map')
@requires_auth
def properties_map():
    """Interactive map view of properties with spatial data."""
    # Get filter parameters
    status = request.args.get('status', '')
    county = request.args.get('county', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')

    # Get dropdown options
    filter_options = get_filter_options()
    counties = filter_options['counties']
    statuses = filter_options['statuses']

    # Fetch properties with coordinates
    with db._get_connection() as conn:
        query = '''
            SELECT id, address, city, county, state, zip, list_price as price,
                   beds, baths, sqft, acreage,
                   status, latitude, longitude, photos, primary_photo
            FROM listings
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        '''
        params = []

        if status:
            query += ' AND LOWER(status) = LOWER(?)'
            params.append(status)

        if county:
            query += ' AND county LIKE ?'
            params.append(f'%{county}%')

        if min_price:
            query += ' AND list_price >= ?'
            params.append(int(min_price))

        if max_price:
            query += ' AND list_price <= ?'
            params.append(int(max_price))

        query += ' ORDER BY list_price DESC LIMIT 500'

        rows = conn.execute(query, params).fetchall()

        properties = []
        for row in rows:
            prop = dict(row)

            # Use primary_photo, or parse first from photos JSON
            if not prop.get('primary_photo') and prop.get('photos'):
                try:
                    photo_list = json.loads(prop['photos'])
                    prop['primary_photo'] = photo_list[0] if photo_list else None
                except (json.JSONDecodeError, IndexError):
                    prop['primary_photo'] = None

            # Clean county name
            if prop.get('county'):
                prop['county'] = re.sub(r'\s+County$', '', prop['county'], flags=re.IGNORECASE).strip()

            properties.append(prop)

    return render_template('properties_map.html',
                         properties=properties,
                         counties=counties,
                         statuses=statuses,
                         selected_status=status,
                         selected_county=county,
                         min_price=min_price,
                         max_price=max_price)


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
                         refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


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


@app.route('/properties/<property_id>')
@requires_auth
def property_detail(property_id):
    """Property detail page with full MLS field coverage."""
    with db._get_connection() as conn:
        prop = conn.execute('''
            SELECT * FROM listings WHERE id = ?
        ''', [property_id]).fetchone()

        if not prop:
            return "Property not found", 404

        prop_dict = dict(prop)

        # Normalize list_price to price for template
        prop_dict['price'] = prop_dict.get('list_price')

        # Parse all JSON array fields
        json_fields = [
            'photos', 'interior_features', 'exterior_features', 'appliances',
            'fireplace_features', 'flooring', 'parking_features',
            'construction_materials', 'water_source', 'sewer',
            'heating', 'cooling', 'documents_available', 'views',
            'style', 'amenities', 'roof', 'foundation'
        ]
        for field in json_fields:
            raw = prop_dict.get(field)
            if raw and isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                    prop_dict[field] = parsed if isinstance(parsed, list) else [parsed]
                except json.JSONDecodeError:
                    prop_dict[field] = [s.strip() for s in raw.split(',') if s.strip()]
            elif not raw:
                prop_dict[field] = []

        # Query agents table for enriched listing agent info
        agent_info = {
            'name': prop_dict.get('listing_agent_name', ''),
            'phone': prop_dict.get('listing_agent_phone', ''),
            'email': prop_dict.get('listing_agent_email', ''),
            'office': prop_dict.get('listing_office_name', ''),
            'photo_url': None,
            'website': None,
        }
        if prop_dict.get('listing_agent_id'):
            agent_row = conn.execute(
                'SELECT * FROM agents WHERE mls_agent_id = ?',
                [prop_dict['listing_agent_id']]
            ).fetchone()
            if agent_row:
                agent_dict = dict(agent_row)
                if not agent_info['name']:
                    agent_info['name'] = agent_dict.get('full_name') or agent_dict.get('name', '')
                if not agent_info['phone']:
                    agent_info['phone'] = agent_dict.get('phone') or agent_dict.get('mobile_phone', '')
                if not agent_info['email']:
                    agent_info['email'] = agent_dict.get('email', '')
                if not agent_info['office']:
                    agent_info['office'] = agent_dict.get('office_name', '')
                agent_info['photo_url'] = agent_dict.get('photo_url')
                agent_info['website'] = agent_dict.get('website')

        # Build buyer agent info if sold
        buyer_agent_info = None
        if prop_dict.get('buyer_agent_name'):
            buyer_agent_info = {
                'name': prop_dict.get('buyer_agent_name', ''),
                'office': prop_dict.get('buyer_office_name', ''),
            }

        # Build GIS URL from county + parcel number
        gis_url = None
        county = prop_dict.get('county', '')
        parcel = prop_dict.get('parcel_number', '')
        if county and parcel:
            template = COUNTY_GIS_URLS.get(county)
            if template:
                gis_url = template.replace('{parcel}', urllib.parse.quote(parcel))

        # Build Google Maps directions URL
        directions_url = None
        addr_parts = [
            prop_dict.get('address', ''),
            prop_dict.get('city', ''),
            prop_dict.get('state', ''),
            prop_dict.get('zip', '')
        ]
        full_address = ', '.join(p for p in addr_parts if p)
        if full_address:
            directions_url = f"https://www.google.com/maps/dir/?api=1&destination={urllib.parse.quote(full_address)}"

        # Compute price per sqft
        price_per_sqft = None
        if prop_dict.get('price') and prop_dict.get('sqft') and prop_dict['sqft'] > 0:
            price_per_sqft = round(prop_dict['price'] / prop_dict['sqft'])

        # Google Maps API key
        google_maps_key = os.environ.get('GOOGLE_MAPS_KEY', '')

        # Price history and changes are not yet tracked for listings
        # (will be rebuilt by Navica sync change detection)
        price_history = []
        changes = []
        interested = []

        return render_template('property_detail.html',
                             property=prop_dict,
                             agent_info=agent_info,
                             buyer_agent_info=buyer_agent_info,
                             gis_url=gis_url,
                             directions_url=directions_url,
                             price_per_sqft=price_per_sqft,
                             google_maps_key=google_maps_key,
                             price_history=price_history,
                             changes=changes,
                             interested_contacts=interested)


@app.route('/api/properties/<property_id>/price-history')
@requires_auth
def api_property_price_history(property_id):
    """API endpoint for property price history (for charts)."""
    history = db.get_property_price_history(property_id)
    return jsonify({'history': history})


# =========================================================================
# CONTACTS ROUTES
# =========================================================================

def get_suggested_action(contact):
    """Get suggested action for a contact based on scores and activity."""
    priority = contact.get('priority_score') or 0
    heat = contact.get('heat_score') or 0
    value = contact.get('value_score') or 0
    days = contact.get('days_since_activity') or 999
    intent_count = sum([
        1 if contact.get('intent_repeat_views') else 0,
        1 if contact.get('intent_high_favorites') else 0,
        1 if contact.get('intent_activity_burst') else 0,
        1 if contact.get('intent_sharing') else 0
    ])

    if priority >= 90:
        return {'icon': '🔥', 'text': 'Immediate Contact', 'class': 'urgent'}
    elif intent_count >= 3:
        return {'icon': '🎯', 'text': 'Schedule Showing', 'class': 'high'}
    elif value >= 80 and heat >= 70:
        return {'icon': '💎', 'text': 'Present Listing', 'class': 'high'}
    elif days > 30 and value >= 60:
        return {'icon': '📧', 'text': 'Re-engagement Email', 'class': 'medium'}
    elif heat >= 70 and value < 50:
        return {'icon': '📊', 'text': 'Send Market Analysis', 'class': 'medium'}
    elif priority >= 75:
        return {'icon': '📱', 'text': 'Follow Up Call', 'class': 'medium'}
    else:
        return {'icon': '🌱', 'text': 'Nurture', 'class': 'low'}


def compute_action_queue(contacts):
    """Compute action queue grouped by priority tier."""
    queue = {
        1: [],  # Immediate Contact: priority >= 80, days <= 7
        2: [],  # High Value Warm: value >= 70, heat >= 50
        3: [],  # Nurture Opportunities: relationship >= 60, priority 50-75
        4: []   # Re-engagement: days > 30, value >= 50
    }
    seen = set()

    for c in contacts:
        cid = c.get('id')
        priority = c.get('priority_score') or 0
        heat = c.get('heat_score') or 0
        value = c.get('value_score') or 0
        relationship = c.get('relationship_score') or 0
        days = c.get('days_since_activity') or 999

        # Priority 1: Hot leads needing immediate contact
        if priority >= 80 and days <= 7 and cid not in seen:
            queue[1].append(c)
            seen.add(cid)
        # Priority 2: High value warm leads
        elif value >= 70 and heat >= 50 and cid not in seen:
            queue[2].append(c)
            seen.add(cid)
        # Priority 3: Nurturing opportunities
        elif relationship >= 60 and 50 <= priority < 75 and cid not in seen:
            queue[3].append(c)
            seen.add(cid)
        # Priority 4: Re-engagement needed
        elif days > 30 and value >= 50 and cid not in seen:
            queue[4].append(c)
            seen.add(cid)

    return queue


def compute_score_analysis(contacts):
    """Compute score distribution and insights."""
    analysis = {
        'distribution': {
            'priority': {'excellent': 0, 'good': 0, 'medium': 0, 'low': 0},
            'heat': {'excellent': 0, 'good': 0, 'medium': 0, 'low': 0},
            'value': {'excellent': 0, 'good': 0, 'medium': 0, 'low': 0},
            'relationship': {'excellent': 0, 'good': 0, 'medium': 0, 'low': 0}
        },
        'insights': []
    }

    for c in contacts:
        for score_type in ['priority', 'heat', 'value', 'relationship']:
            score = c.get(f'{score_type}_score') or 0
            if score >= 90:
                analysis['distribution'][score_type]['excellent'] += 1
            elif score >= 70:
                analysis['distribution'][score_type]['good'] += 1
            elif score >= 50:
                analysis['distribution'][score_type]['medium'] += 1
            else:
                analysis['distribution'][score_type]['low'] += 1

    # Compute insights
    high_heat_low_value = len([c for c in contacts
                               if (c.get('heat_score') or 0) >= 70 and (c.get('value_score') or 0) < 40])
    high_value_low_heat = len([c for c in contacts
                               if (c.get('value_score') or 0) >= 70 and (c.get('heat_score') or 0) < 40])
    perfect_prospects = len([c for c in contacts
                             if (c.get('heat_score') or 0) >= 70
                             and (c.get('value_score') or 0) >= 70
                             and (c.get('relationship_score') or 0) >= 70])
    high_intent_quiet = len([c for c in contacts
                             if (c.get('intent_signal_count') or 0) >= 3
                             and (c.get('days_since_activity') or 0) > 14])

    analysis['insights'] = [
        {'category': 'High Heat, Low Value', 'count': high_heat_low_value,
         'description': 'Engaged but potentially price shopping or early stage'},
        {'category': 'High Value, Low Heat', 'count': high_value_low_heat,
         'description': 'Hidden gems - quality prospects needing nurturing'},
        {'category': 'Perfect Prospects', 'count': perfect_prospects,
         'description': 'All scores high - ready to close'},
        {'category': 'High Intent, Quiet', 'count': high_intent_quiet,
         'description': 'Strong intent signals despite lower recent activity'}
    ]

    return analysis


def compute_strategic_insights(contacts):
    """Compute strategic insights with actionable recommendations."""
    insights = []

    # High value cold leads
    high_value_cold = [c for c in contacts
                       if (c.get('value_score') or 0) >= 70 and (c.get('heat_score') or 0) < 40]
    if high_value_cold:
        insights.append({
            'type': 'opportunity',
            'title': f'{len(high_value_cold)} High-Value Cold Leads',
            'description': 'Quality prospects who have gone quiet. A strategic re-engagement campaign could unlock significant opportunities.',
            'action': 'Create a personalized re-engagement email sequence focusing on their specific interests.',
            'contacts': high_value_cold[:5]
        })

    # Leads stuck in pipeline
    stuck_leads = [c for c in contacts
                   if (c.get('heat_score') or 0) >= 70 and (c.get('relationship_score') or 0) < 40]
    if stuck_leads:
        insights.append({
            'type': 'warning',
            'title': f'{len(stuck_leads)} Leads Stuck in Pipeline',
            'description': 'Highly engaged but relationship scores are low, suggesting they may need more trust-building.',
            'action': 'Schedule personal calls or video meetings to strengthen the relationship.',
            'contacts': stuck_leads[:5]
        })

    # High intent quiet leads
    high_intent_quiet = [c for c in contacts
                         if (c.get('intent_signal_count') or 0) >= 3
                         and (c.get('days_since_activity') or 0) > 14]
    if high_intent_quiet:
        insights.append({
            'type': 'opportunity',
            'title': f'{len(high_intent_quiet)} High-Intent Quiet Leads',
            'description': "Leads showing strong buying signals but haven't been contacted recently.",
            'action': "Prioritize these for contact today - they're showing buying signals.",
            'contacts': high_intent_quiet[:5]
        })

    # Stale valuable leads
    stale_valuable = [c for c in contacts
                      if (c.get('days_since_activity') or 0) > 30 and (c.get('value_score') or 0) >= 60]
    if len(stale_valuable) > 3:
        insights.append({
            'type': 'warning',
            'title': f'{len(stale_valuable)} Valuable Leads Going Stale',
            'description': "High-value prospects haven't been contacted in over 30 days.",
            'action': 'Implement an automated re-engagement sequence or assign for immediate follow-up.',
            'contacts': stale_valuable[:5]
        })

    # Perfect prospects
    perfect = [c for c in contacts
               if (c.get('heat_score') or 0) >= 70
               and (c.get('value_score') or 0) >= 70
               and (c.get('relationship_score') or 0) >= 70]
    if perfect:
        insights.append({
            'type': 'success',
            'title': f'{len(perfect)} Perfect Prospects Ready to Close',
            'description': "All scores high - they're hot, valuable, and have strong relationships.",
            'action': 'Focus on closing these first - schedule property showings or listing appointments.',
            'contacts': perfect[:5]
        })

    return insights


def compute_trends(contacts):
    """Compute activity pattern trends."""
    active = len([c for c in contacts if (c.get('days_since_activity') or 999) <= 7])
    warm = len([c for c in contacts if 7 < (c.get('days_since_activity') or 999) <= 30])
    cold = len([c for c in contacts if 30 < (c.get('days_since_activity') or 999) <= 90])
    stale = len([c for c in contacts if (c.get('days_since_activity') or 999) > 90])

    return {
        'activity_pattern': {
            'Active (< 7d)': active,
            'Warm (7-30d)': warm,
            'Cold (30-90d)': cold,
            'Stale (> 90d)': stale
        },
        'total': len(contacts)
    }


@app.route('/contacts')
@requires_auth
def contacts_list():
    """Contacts list view with tabs (requires authentication)"""
    db = get_db()

    # Get view filter from query params (default to 'my_leads')
    current_view = request.args.get('view', 'my_leads')
    if current_view not in CONTACT_VIEWS:
        current_view = 'my_leads'

    # Get filter parameters
    min_heat = request.args.get('min_heat', 0, type=float)
    min_value = request.args.get('min_value', 0, type=float)
    stage = request.args.get('stage', '')
    sort_by = request.args.get('sort', 'priority')  # priority, heat, value, name
    filter_type = request.args.get('filter', '')  # hot_leads, high_value, active_week
    active_tab = request.args.get('tab', 'contacts')  # contacts, queue, analysis, insights, trends

    # Get all contacts (filtered by view)
    all_contacts = db.get_contacts_by_priority(
        min_priority=0,
        limit=2000,
        user_id=CURRENT_USER_ID,
        view=current_view
    )

    # Add suggested action to each contact
    for contact in all_contacts:
        contact['suggested_action'] = get_suggested_action(contact)

    # Compute data for all tabs (using full unfiltered list)
    action_queue = compute_action_queue(all_contacts)
    score_analysis = compute_score_analysis(all_contacts)
    strategic_insights = compute_strategic_insights(all_contacts)
    trends = compute_trends(all_contacts)

    # Apply filters for the contacts tab
    contacts = all_contacts.copy()

    # Apply quick filter from metric card clicks
    if filter_type == 'hot_leads':
        contacts = [c for c in contacts if (c.get('heat_score') or 0) >= 75]
    elif filter_type == 'high_value':
        contacts = [c for c in contacts if (c.get('value_score') or 0) >= 60]
    elif filter_type == 'active_week':
        contacts = [c for c in contacts if (c.get('days_since_activity') or 999) <= 7]
    elif filter_type == 'pipeline':
        pipeline_stages = {'Under Contract', 'Pending', 'Active Under Contract'}
        contacts = [c for c in contacts if c.get('stage') in pipeline_stages]
    elif filter_type == 'active_buyers':
        buyer_stages = {'Active Client', 'Active Buyer', 'Hot Prospect', 'Prospect'}
        contacts = [c for c in contacts if c.get('stage') in buyer_stages]
    elif filter_type == 'new_leads_3d':
        cutoff = (datetime.now() - timedelta(days=3)).isoformat()
        contacts = [c for c in contacts if (c.get('created_at') or '') >= cutoff]
    elif filter_type == 'reassigned':
        reassigned = db.get_recently_reassigned_leads(from_user_id=CURRENT_USER_ID, days=7)
        reassigned_ids = {str(rl.get('id', '')) for rl in reassigned}
        contacts = [c for c in contacts if str(c.get('id', '')) in reassigned_ids]

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

    # Get unique stages for filter dropdown
    stages = sorted(set(c.get('stage') for c in all_contacts if c.get('stage')))

    # Get aggregate stats (filtered by view)
    stats = db.get_contact_stats(user_id=CURRENT_USER_ID, view=current_view)

    # Smart list counts for pill bar
    smart_lists = db.get_fub_style_lists(user_id=CURRENT_USER_ID)

    return render_template('contacts.html',
                         contacts=contacts,
                         all_contacts=all_contacts,
                         stats=stats,
                         current_view=current_view,
                         stages=stages,
                         selected_stage=stage,
                         selected_min_heat=min_heat,
                         selected_sort=sort_by,
                         selected_filter=filter_type,
                         active_tab=active_tab,
                         action_queue=action_queue,
                         score_analysis=score_analysis,
                         strategic_insights=strategic_insights,
                         trends=trends,
                         smart_lists=smart_lists,
                         refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


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

    # Contact-property links will be rebuilt with Navica data
    properties = []

    # Get property view summary (aggregated from contact_events)
    property_summary = db.get_contact_property_summary(contact_id)

    # Get activity timeline (communications + events from last 30 days)
    timeline = db.get_activity_timeline(contact_id, days=30, limit=50)

    # Get trend summary (scoring history, 7d avg, trend direction)
    trend_summary = db.get_contact_trend_summary(contact_id)

    # Get contact actions (pending and recent completed)
    actions = db.get_contact_actions(contact_id, include_completed=True, limit=20)

    # Today's date for due date comparisons
    today = datetime.now().strftime('%Y-%m-%d')

    return render_template('contact_detail.html',
                         contact=contact,
                         properties=properties,
                         property_summary=property_summary,
                         timeline=timeline,
                         trend_summary=trend_summary,
                         actions=actions,
                         today=today,
                         refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


# =========================================================================
# ACTIONS PAGE
# =========================================================================

@app.route('/actions')
@requires_auth
def actions_list():
    """Actions list view - shows all pending actions across contacts."""
    db = get_db()

    # Get all pending actions
    all_actions = db.get_pending_actions(limit=200)

    # Get today's date for categorization
    today = datetime.now().strftime('%Y-%m-%d')

    # Categorize actions
    overdue_actions = []
    today_actions = []
    upcoming_actions = []
    no_date_actions = []

    for action in all_actions:
        due_date = action.get('due_date')
        if not due_date:
            no_date_actions.append(action)
        elif due_date < today:
            overdue_actions.append(action)
        elif due_date == today:
            today_actions.append(action)
        else:
            upcoming_actions.append(action)

    # Sort each category by priority then due date
    def sort_key(a):
        return (a.get('priority', 5), a.get('due_date') or '9999-99-99')

    overdue_actions.sort(key=sort_key)
    today_actions.sort(key=sort_key)
    upcoming_actions.sort(key=sort_key)
    no_date_actions.sort(key=lambda a: a.get('priority', 5))

    return render_template('actions.html',
                         overdue_actions=overdue_actions,
                         today_actions=today_actions,
                         upcoming_actions=upcoming_actions,
                         no_date_actions=no_date_actions,
                         today=today)


# =========================================================================
# SCORING RUNS PAGE
# =========================================================================

@app.route('/system/scoring-runs')
@requires_auth
def scoring_runs_list():
    """Scoring runs history view - shows audit trail of FUB sync runs."""
    db = get_db()

    # Get recent scoring runs
    runs = db.get_recent_scoring_runs(limit=50)

    # Calculate summary stats
    total_contacts_processed = sum(r.get('contacts_processed', 0) or 0 for r in runs)
    successful_runs = sum(1 for r in runs if r.get('status') == 'success')
    success_rate = int((successful_runs / len(runs) * 100)) if runs else 0

    return render_template('scoring_runs.html',
                         runs=runs,
                         total_contacts_processed=total_contacts_processed,
                         success_rate=success_rate)


# =========================================================================
# MY LEADS PAGE
# =========================================================================

@app.route('/my-leads')
@requires_auth
def my_leads():
    """My Leads view - shows leads assigned to the current user with assignment history."""
    db = get_db()

    # Get user ID from environment (set in .env)
    user_id = int(os.getenv('FUB_MY_USER_ID', 8))

    # Get user name from cached users
    user = db.get_fub_user(user_id)
    user_name = user.get('name') if user else f"User {user_id}"

    # Get filter parameter
    filter_type = request.args.get('filter', 'current')

    # Get assignment stats
    stats = db.get_user_assignment_stats(user_id)

    # Get leads based on filter
    if filter_type == 'current':
        leads = db.get_contacts_assigned_to_user(user_id, include_history=True)
    elif filter_type == 'past':
        leads = db.get_contacts_with_assignment_to_user(
            user_id, include_current=False, include_past=True
        )
    else:  # all
        leads = db.get_contacts_with_assignment_to_user(
            user_id, include_current=True, include_past=True
        )

    # Get counts for filter tabs
    current_leads = db.get_contacts_assigned_to_user(user_id, include_history=False)
    all_leads = db.get_contacts_with_assignment_to_user(
        user_id, include_current=True, include_past=True
    )
    past_leads = db.get_contacts_with_assignment_to_user(
        user_id, include_current=False, include_past=True
    )

    return render_template('my_leads.html',
                         leads=leads,
                         user_id=user_id,
                         user_name=user_name,
                         stats=stats,
                         filter=filter_type,
                         current_count=len(current_leads),
                         all_count=len(all_leads),
                         past_count=len(past_leads))


# =========================================================================
# CONTACT ACTIONS API
# =========================================================================

@app.route('/api/contacts/<contact_id>/actions', methods=['GET'])
@requires_auth
def get_contact_actions_api(contact_id):
    """Get actions for a contact."""
    db = get_db()
    include_completed = request.args.get('include_completed', 'false').lower() == 'true'
    actions = db.get_contact_actions(contact_id, include_completed=include_completed)
    return jsonify({'success': True, 'actions': actions})


@app.route('/api/contacts/<contact_id>/actions', methods=['POST'])
@requires_auth
def add_contact_action_api(contact_id):
    """Add a new action for a contact."""
    db = get_db()
    data = request.get_json()

    if not data or not data.get('action_type'):
        return jsonify({'success': False, 'error': 'action_type is required'}), 400

    action_id = db.add_contact_action(
        contact_id=contact_id,
        action_type=data.get('action_type'),
        description=data.get('description'),
        due_date=data.get('due_date'),
        priority=data.get('priority', 3),
        created_by='user'
    )

    return jsonify({'success': True, 'action_id': action_id})


@app.route('/api/contacts/<contact_id>/actions/<int:action_id>/complete', methods=['POST'])
@requires_auth
def complete_contact_action_api(contact_id, action_id):
    """Mark an action as completed."""
    db = get_db()
    success = db.complete_contact_action(action_id, completed_by='user')

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Action not found or already completed'}), 404


@app.route('/api/actions/pending', methods=['GET'])
@requires_auth
def get_pending_actions_api():
    """Get all pending actions across all contacts."""
    db = get_db()
    due_before = request.args.get('due_before')
    limit = request.args.get('limit', 100, type=int)
    actions = db.get_pending_actions(due_before=due_before, limit=limit)
    return jsonify({'success': True, 'actions': actions})


@app.route('/api/scoring-runs', methods=['GET'])
@requires_auth
def get_scoring_runs_api():
    """Get recent scoring runs."""
    db = get_db()
    limit = request.args.get('limit', 10, type=int)
    runs = db.get_recent_scoring_runs(limit=limit)
    return jsonify({'success': True, 'runs': runs})


@app.route('/api/contacts/<contact_id>/matches', methods=['GET'])
@requires_auth
def get_contact_matches_api(contact_id):
    """
    Get property matches for a contact based on stated and behavioral preferences.

    Data sources:
    1. Intake forms (explicit stated requirements)
    2. Behavioral analysis (property viewing patterns)
    3. Lead table data (basic preferences)

    Returns matched properties with score breakdowns.
    """
    db = get_db()
    min_score = request.args.get('min_score', 40.0, type=float)
    limit = request.args.get('limit', 15, type=int)

    # Get behavioral preferences (from activity analysis)
    behavioral = db.get_behavioral_preferences(contact_id)

    # Get stated requirements (from intake forms)
    stated = db.get_stated_requirements(contact_id)

    # Get matching properties
    matches = db.find_matching_properties(contact_id, min_score=min_score, limit=limit)

    return jsonify({
        'success': True,
        'behavioral_preferences': behavioral,
        'stated_requirements': stated,
        'matches': matches,
        'count': len(matches)
    })


def _resolve_contact_id(db, contact_id: str) -> Optional[str]:
    """Resolve various contact ID formats to a DREAMS lead ID (UUID).

    Handles:
    - "fub_123" composite → strips prefix, looks up by fub_id
    - UUID format → returns directly
    - Numeric string → looks up by fub_id
    Returns the UUID lead ID, or the original contact_id if no match found.
    """
    if contact_id.startswith('fub_'):
        fub_id = contact_id[4:]
        lead = db.get_contact_by_fub_id(fub_id)
        return lead['id'] if lead else fub_id
    elif contact_id.isdigit():
        lead = db.get_contact_by_fub_id(contact_id)
        return lead['id'] if lead else contact_id
    return contact_id


@app.route('/api/contacts/<contact_id>/intel')
@requires_auth
def api_contact_intel(contact_id):
    """Get contact intelligence data for Power Hour expandable sections.
    Returns intake forms, behavioral preferences, and property view summary."""
    db = get_db()
    resolved_id = _resolve_contact_id(db, contact_id)

    intake_forms = db.get_intake_forms_for_lead(resolved_id)
    behavioral = db.get_behavioral_preferences(resolved_id)
    property_views = db.get_contact_property_summary(resolved_id)

    # Limit property views to top 10, sorted by last_viewed
    property_views = sorted(
        property_views,
        key=lambda x: x.get('last_viewed') or '',
        reverse=True
    )[:10]

    return jsonify({
        'success': True,
        'intake_forms': intake_forms,
        'behavioral': behavioral,
        'property_views': property_views
    })


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


# =========================================================================
# CONTACT WORKSPACE ROUTES (Phase 1: Unified Contact Hub)
# =========================================================================

# Buyer workflow constants (migrated from buyer-workflow app)
NEED_TYPES = [
    ('primary_home', 'Primary Home'),
    ('second_home', 'Second Home'),
    ('child_home', 'Home for Child/Family'),
    ('str', 'Short-Term Rental (STR)'),
    ('ltr', 'Long-Term Rental (LTR)'),
    ('investment', 'Investment Property'),
    ('land', 'Land/Lot'),
    ('relocation', 'Relocation'),
]

URGENCY_OPTIONS = [
    ('asap', 'ASAP - Ready to buy now'),
    ('1-3_months', '1-3 months'),
    ('3-6_months', '3-6 months'),
    ('6-12_months', '6-12 months'),
    ('flexible', 'Flexible / Just browsing'),
]

FINANCING_OPTIONS = [
    ('pre_approved', 'Pre-approved'),
    ('cash', 'Cash buyer'),
    ('needs_pre_approval', 'Needs pre-approval'),
    ('unknown', 'Unknown'),
]

WNC_COUNTIES = [
    'Macon', 'Jackson', 'Swain', 'Cherokee', 'Clay', 'Graham',
    'Haywood', 'Transylvania', 'Henderson', 'Buncombe', 'Madison',
    'Yancey', 'Mitchell', 'Avery', 'Watauga', 'Ashe', 'Alleghany',
]

PROPERTY_TYPES = [
    'Single Family Residential', 'Condo/Co-op', 'Townhouse',
    'Multi-Family (2-4 Unit)', 'Vacant Land', 'Mobile/Manufactured Home',
    'Ranch', 'Other',
]

VIEW_OPTIONS = [
    'Mountain', 'Long Range', 'Lake', 'River', 'Valley', 'Wooded', 'Pastoral',
]

WATER_OPTIONS = [
    'Creek', 'River', 'Pond', 'Lake Access', 'Lake Front', 'River Front', 'Springs',
]

# Redfin imports database path
PROPERTIES_DB_PATH = os.getenv('PROPERTIES_DB_PATH', str(PROJECT_ROOT / 'data' / 'redfin_imports.db'))


def get_properties_db():
    """Get database connection for property searches (redfin_imports)."""
    import sqlite3
    conn = sqlite3.connect(PROPERTIES_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.template_filter('from_json')
def from_json_filter(value):
    """Parse JSON string to Python object."""
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


@app.route('/contacts/<contact_id>/workspace')
@requires_auth
def contact_workspace(contact_id):
    """
    Unified Contact Workspace - central hub for managing a buyer relationship.

    Tabs:
    - Info: Basic contact info, stage, scores, quick actions
    - Requirements: Intake forms with inline editing + behavioral inference
    - Activity: Timeline of communications and events
    - Packages: Property packages created for this contact
    - Showings: Scheduled and past showings
    - Matches: AI-suggested properties based on requirements
    """
    db = get_db()

    # Get contact
    contact = db.get_lead(contact_id)
    if not contact:
        return "Contact not found", 404

    # Auto-populate IDX cache for this contact's uncached MLS numbers
    populate_idx_cache_for_contact(db, contact_id, limit=20)

    # Get active tab from query param
    active_tab = request.args.get('tab', 'info')

    # Get intake forms for this contact
    intake_forms = db.get_intake_forms_for_lead(contact_id)

    # Get stated requirements (consolidated from intake forms)
    stated_requirements = db.get_stated_requirements(contact_id)

    # Get behavioral preferences (inferred from activity)
    behavioral_prefs = db.get_behavioral_preferences(contact_id)

    # Get consolidated requirements (Phase 5)
    consolidated_reqs = db.get_consolidated_requirements(contact_id)
    if not consolidated_reqs and (stated_requirements.get('confidence', 0) > 0 or behavioral_prefs.get('confidence', 0) > 0):
        # Auto-consolidate if we have source data
        try:
            consolidated_reqs = db.consolidate_requirements(contact_id)
        except Exception as e:
            logger.warning(f"Error consolidating requirements: {e}")
            consolidated_reqs = None

    # Get requirements by source for comparison view
    requirements_sources = None
    if active_tab == 'requirements':
        try:
            requirements_sources = db.get_requirements_by_source(contact_id)
        except Exception as e:
            logger.warning(f"Error getting requirements sources: {e}")

    # Get activity timeline
    timeline = db.get_activity_timeline(contact_id, days=30, limit=50)

    # Get trend summary
    trend_summary = db.get_contact_trend_summary(contact_id)

    # Get contact actions
    actions = db.get_contact_actions(contact_id, include_completed=True, limit=20)

    # Get property view summary
    property_summary = db.get_contact_property_summary(contact_id)

    # Get packages for this contact (package_properties table dropped, count will be 0)
    packages = []
    try:
        with db._get_connection() as conn:
            packages = conn.execute('''
                SELECT p.*, 0 as property_count
                FROM property_packages p
                WHERE p.lead_id = ?
                ORDER BY p.created_at DESC
            ''', (contact_id,)).fetchall()
            packages = [dict(row) for row in packages]
    except Exception as e:
        logger.warning(f"Error fetching packages: {e}")

    # Showings table dropped during Navica migration; will rebuild later
    showings = []

    # Today's date for due date comparisons
    today = datetime.now().strftime('%Y-%m-%d')

    return render_template('contact_workspace.html',
        contact=contact,
        active_tab=active_tab,
        intake_forms=intake_forms,
        stated_requirements=stated_requirements,
        behavioral_prefs=behavioral_prefs,
        consolidated_reqs=consolidated_reqs,
        requirements_sources=requirements_sources,
        timeline=timeline,
        trend_summary=trend_summary,
        actions=actions,
        property_summary=property_summary,
        packages=packages,
        showings=showings,
        today=today,
        # Intake form options
        need_types=NEED_TYPES,
        urgency_options=URGENCY_OPTIONS,
        financing_options=FINANCING_OPTIONS,
        counties=WNC_COUNTIES,
        property_types=PROPERTY_TYPES,
        view_options=VIEW_OPTIONS,
        water_options=WATER_OPTIONS,
        refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


@app.route('/contacts/<contact_id>/intake/save', methods=['POST'])
@requires_auth
def contact_intake_save(contact_id):
    """Save intake form for a contact (inline workspace editing)."""
    import uuid
    db = get_db()

    form_id = request.form.get('form_id')
    is_new = not form_id

    if is_new:
        form_id = str(uuid.uuid4())

    # Build JSON arrays from multi-select fields
    def get_json_array(field):
        values = request.form.getlist(field)
        return json.dumps(values) if values else None

    # Handle cities as comma-separated input
    cities_input = request.form.get('cities', '')
    cities_list = [c.strip() for c in cities_input.split(',') if c.strip()]

    data = {
        'id': form_id,
        'lead_id': contact_id,
        'form_name': request.form.get('form_name'),
        'need_type': request.form.get('need_type'),
        'status': request.form.get('status', 'active'),
        'priority': request.form.get('priority', 1),
        'source': request.form.get('source'),
        'source_date': request.form.get('source_date'),
        'source_notes': request.form.get('source_notes'),

        # Location
        'counties': get_json_array('counties'),
        'cities': json.dumps(cities_list) if cities_list else None,
        'zip_codes': get_json_array('zip_codes'),

        # Property criteria
        'property_types': get_json_array('property_types'),
        'min_price': request.form.get('min_price') or None,
        'max_price': request.form.get('max_price') or None,
        'min_beds': request.form.get('min_beds') or None,
        'max_beds': request.form.get('max_beds') or None,
        'min_baths': request.form.get('min_baths') or None,
        'max_baths': request.form.get('max_baths') or None,
        'min_sqft': request.form.get('min_sqft') or None,
        'max_sqft': request.form.get('max_sqft') or None,
        'min_acreage': request.form.get('min_acreage') or None,
        'max_acreage': request.form.get('max_acreage') or None,
        'min_year_built': request.form.get('min_year_built') or None,
        'max_year_built': request.form.get('max_year_built') or None,

        # Features
        'views_required': get_json_array('views_required'),
        'water_features': get_json_array('water_features'),
        'style_preferences': get_json_array('style_preferences'),
        'must_have_features': request.form.get('must_have_features'),
        'nice_to_have_features': request.form.get('nice_to_have_features'),
        'deal_breakers': request.form.get('deal_breakers'),

        # Investment
        'target_cap_rate': request.form.get('target_cap_rate') or None,
        'target_rental_income': request.form.get('target_rental_income') or None,
        'accepts_fixer_upper': 1 if request.form.get('accepts_fixer_upper') else 0,

        # Timeline
        'urgency': request.form.get('urgency'),
        'move_in_date': request.form.get('move_in_date') or None,
        'financing_status': request.form.get('financing_status'),
        'pre_approval_amount': request.form.get('pre_approval_amount') or None,

        # Notes
        'agent_notes': request.form.get('agent_notes'),
        'confidence_score': request.form.get('confidence_score') or None,
        'updated_at': datetime.now().isoformat(),
    }

    try:
        with db._get_connection() as conn:
            if is_new:
                data['created_at'] = datetime.now().isoformat()
                placeholders = ', '.join(['?' for _ in data])
                columns = ', '.join(data.keys())
                conn.execute(f'INSERT INTO intake_forms ({columns}) VALUES ({placeholders})', list(data.values()))
            else:
                set_clause = ', '.join([f'{k} = ?' for k in data.keys() if k != 'id'])
                values = [v for k, v in data.items() if k != 'id'] + [form_id]
                conn.execute(f'UPDATE intake_forms SET {set_clause} WHERE id = ?', values)
            conn.commit()
    except Exception as e:
        logger.error(f"Error saving intake form: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    # Redirect back to workspace requirements tab
    return redirect(url_for('contact_workspace', contact_id=contact_id, tab='requirements'))


@app.route('/contacts/<contact_id>/intake/<form_id>/delete', methods=['POST'])
@requires_auth
def contact_intake_delete(contact_id, form_id):
    """Delete an intake form."""
    db = get_db()

    try:
        success = db.delete_intake_form(form_id)
        if success:
            logger.info(f"Deleted intake form {form_id} for contact {contact_id}")
        else:
            logger.warning(f"Intake form {form_id} not found")
    except Exception as e:
        logger.error(f"Error deleting intake form: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    # Redirect back to workspace requirements tab
    return redirect(url_for('contact_workspace', contact_id=contact_id, tab='requirements'))


@app.route('/api/contacts/<contact_id>/intake/<form_id>', methods=['DELETE'])
@requires_auth
def api_intake_delete(contact_id, form_id):
    """API endpoint to delete an intake form."""
    db = get_db()

    try:
        success = db.delete_intake_form(form_id)
        if success:
            logger.info(f"Deleted intake form {form_id} for contact {contact_id}")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Form not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting intake form: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/contacts/<contact_id>/search')
@requires_auth
def contact_property_search(contact_id):
    """
    Search properties based on contact's intake requirements.
    Queries the redfin_imports database.
    """
    db = get_db()

    # Get contact
    contact = db.get_lead(contact_id)
    if not contact:
        return "Contact not found", 404

    # Get stated requirements
    requirements = db.get_stated_requirements(contact_id)

    # Get behavioral preferences for additional context
    behavioral = db.get_behavioral_preferences(contact_id)

    # Get form_id if specified (for specific intake form search)
    form_id = request.args.get('form_id')
    intake_form = None

    if form_id:
        forms = db.get_intake_forms_for_lead(contact_id)
        for f in forms:
            if f.get('id') == form_id:
                intake_form = f
                break

    # Build search criteria from requirements or form
    search_criteria = {}

    if intake_form:
        # Use specific intake form criteria
        search_criteria = {
            'min_price': intake_form.get('min_price'),
            'max_price': intake_form.get('max_price'),
            'min_beds': intake_form.get('min_beds'),
            'min_baths': intake_form.get('min_baths'),
            'min_sqft': intake_form.get('min_sqft'),
            'min_acreage': intake_form.get('min_acreage'),
            'counties': intake_form.get('counties'),
            'property_types': intake_form.get('property_types'),
        }
    elif requirements and requirements.get('confidence', 0) > 0:
        # Use consolidated stated requirements
        search_criteria = {
            'min_price': requirements.get('min_price'),
            'max_price': requirements.get('max_price'),
            'min_beds': requirements.get('min_beds'),
            'min_baths': requirements.get('min_baths'),
            'min_sqft': requirements.get('min_sqft'),
            'min_acreage': requirements.get('min_acreage'),
            'counties': json.dumps(requirements.get('counties', [])) if requirements.get('counties') else None,
        }
    elif behavioral and behavioral.get('confidence', 0) > 0:
        # Fall back to behavioral inference
        search_criteria = {
            'min_price': int(behavioral.get('price_range', [0, 0])[0] * 0.9) if behavioral.get('price_range') else None,
            'max_price': int(behavioral.get('price_range', [0, 0])[1] * 1.1) if behavioral.get('price_range') else None,
            'counties': json.dumps(behavioral.get('counties', [])) if behavioral.get('counties') else None,
        }

    # Allow URL parameter overrides
    if request.args.get('min_price'):
        search_criteria['min_price'] = request.args.get('min_price')
    if request.args.get('max_price'):
        search_criteria['max_price'] = request.args.get('max_price')
    if request.args.get('min_beds'):
        search_criteria['min_beds'] = request.args.get('min_beds')
    if request.args.get('county'):
        search_criteria['counties'] = json.dumps([request.args.get('county')])

    # Query listings table (canonical property source)
    properties = []
    try:
        with db._get_connection() as conn:
            query = 'SELECT * FROM listings WHERE LOWER(status) = \'active\''
            params = []

            # Apply search criteria
            if search_criteria.get('min_price'):
                query += ' AND list_price >= ?'
                params.append(int(search_criteria['min_price']))
            if search_criteria.get('max_price'):
                query += ' AND list_price <= ?'
                params.append(int(search_criteria['max_price']))
            if search_criteria.get('min_beds'):
                query += ' AND beds >= ?'
                params.append(int(search_criteria['min_beds']))
            if search_criteria.get('min_baths'):
                query += ' AND baths >= ?'
                params.append(float(search_criteria['min_baths']))
            if search_criteria.get('min_sqft'):
                query += ' AND sqft >= ?'
                params.append(int(search_criteria['min_sqft']))
            if search_criteria.get('min_acreage'):
                query += ' AND acreage >= ?'
                params.append(float(search_criteria['min_acreage']))

            # Counties filter
            if search_criteria.get('counties'):
                try:
                    counties = json.loads(search_criteria['counties'])
                    if counties:
                        placeholders = ','.join(['?' for _ in counties])
                        query += f' AND county IN ({placeholders})'
                        params.extend(counties)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Property types filter
            if search_criteria.get('property_types'):
                try:
                    types = json.loads(search_criteria['property_types'])
                    if types:
                        placeholders = ','.join(['?' for _ in types])
                        query += f' AND property_type IN ({placeholders})'
                        params.extend(types)
                except (json.JSONDecodeError, TypeError):
                    pass

            query += ' ORDER BY days_on_market ASC, list_price ASC LIMIT 100'

            logger.info(f"Property search query: {query}")
            logger.info(f"Property search params: {params}")

            rows = conn.execute(query, params).fetchall()
            properties = [dict(row) for row in rows]
            # Normalize list_price to price for templates
            for prop in properties:
                prop['price'] = prop.get('list_price')

    except Exception as e:
        logger.error(f"Property search error: {e}")

    # Get existing packages for "Add to Package" dropdown
    packages = []
    try:
        with db._get_connection() as conn:
            packages = conn.execute('''
                SELECT id, name, status FROM property_packages
                WHERE lead_id = ? AND status IN ('draft', 'ready')
                ORDER BY created_at DESC
            ''', (contact_id,)).fetchall()
            packages = [dict(row) for row in packages]
    except Exception as e:
        logger.warning(f"Error fetching packages: {e}")

    return render_template('property_search_results.html',
        contact=contact,
        properties=properties,
        search_criteria=search_criteria,
        requirements=requirements,
        behavioral=behavioral,
        intake_form=intake_form,
        packages=packages,
        counties=WNC_COUNTIES,
        property_types=PROPERTY_TYPES)


@app.route('/contacts/<contact_id>/packages/create', methods=['POST'])
@requires_auth
def contact_create_package(contact_id):
    """Create a new package from selected properties."""
    import uuid
    import secrets
    db = get_db()

    # Get contact
    contact = db.get_lead(contact_id)
    if not contact:
        return jsonify({'success': False, 'error': 'Contact not found'}), 404

    # Get selected property IDs
    property_ids = request.form.getlist('property_ids')
    if not property_ids:
        return jsonify({'success': False, 'error': 'No properties selected'}), 400

    # Create package
    package_id = str(uuid.uuid4())
    share_token = secrets.token_urlsafe(16)

    # Generate package name from contact name and date
    contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
    package_name = f"{contact_name} - {datetime.now().strftime('%b %d, %Y')}"

    # Get intake form ID if provided
    intake_form_id = request.form.get('intake_form_id')

    try:
        with db._get_connection() as conn:
            # Create package
            conn.execute('''
                INSERT INTO property_packages (id, lead_id, intake_form_id, name, status, share_token, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'draft', ?, ?, ?)
            ''', (package_id, contact_id, intake_form_id, package_name, share_token,
                  datetime.now().isoformat(), datetime.now().isoformat()))

            # TODO: Rebuild package_properties table with listings-compatible schema
            # Package-property linking disabled during Navica migration
            pass

            conn.commit()
    except Exception as e:
        logger.error(f"Error creating package: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    # Redirect to package detail or back to workspace
    return redirect(url_for('contact_package_detail', contact_id=contact_id, package_id=package_id))


@app.route('/contacts/<contact_id>/packages/<package_id>')
@requires_auth
def contact_package_detail(contact_id, package_id):
    """View package detail within contact workspace context."""
    db = get_db()

    # Get contact
    contact = db.get_lead(contact_id)
    if not contact:
        return "Contact not found", 404

    # Get package
    package = None
    properties = []

    try:
        with db._get_connection() as conn:
            package = conn.execute('''
                SELECT * FROM property_packages WHERE id = ? AND lead_id = ?
            ''', (package_id, contact_id)).fetchone()

            if not package:
                return "Package not found", 404

            package = dict(package)

            # Package properties table was dropped during Navica migration.
            # Property packages will be rebuilt with listings-compatible schema.
            pass

    except Exception as e:
        logger.error(f"Error fetching package: {e}")
        return "Error loading package", 500

    # Generate shareable client URL
    client_url = None
    if package.get('share_token'):
        base_url = request.host_url.rstrip('/')
        client_url = f"{base_url}/view/{package['share_token']}"

    return render_template('package_detail.html',
        contact=contact,
        package=package,
        properties=properties,
        client_url=client_url)


@app.route('/contacts/<contact_id>/packages/<package_id>/add', methods=['POST'])
@requires_auth
def contact_package_add_properties(contact_id, package_id):
    """Add properties to an existing package."""
    import uuid
    db = get_db()

    property_ids = request.form.getlist('property_ids')
    if not property_ids:
        return jsonify({'success': False, 'error': 'No properties selected'}), 400

    # TODO: Rebuild package_properties table with listings-compatible schema
    return jsonify({'success': False, 'error': 'Package property linking not yet available (Navica migration in progress)'}), 501


@app.route('/contacts/<contact_id>/packages/<package_id>/remove/<property_id>', methods=['POST'])
@requires_auth
def contact_package_remove_property(contact_id, package_id, property_id):
    """Remove a property from a package."""
    db = get_db()

    # TODO: Rebuild package_properties table with listings-compatible schema
    return jsonify({'success': False, 'error': 'Package property linking not yet available (Navica migration in progress)'}), 501


@app.route('/contacts/<contact_id>/packages/<package_id>/pdf')
@requires_auth
def contact_package_pdf(contact_id, package_id):
    """Generate and download PDF for a property package."""
    try:
        from apps.automation.pdf_generator import generate_pdf_bytes, get_package_pdf_filename

        # Generate PDF bytes
        pdf_bytes = generate_pdf_bytes(package_id)

        if not pdf_bytes:
            return "Failed to generate PDF. Make sure WeasyPrint is installed.", 500

        # Get filename
        filename = get_package_pdf_filename(package_id)

        # Return PDF as download
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'application/pdf'
            }
        )

    except ImportError:
        return "PDF generation requires WeasyPrint. Install with: pip install weasyprint", 500
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        return f"Error generating PDF: {str(e)}", 500


# =========================================================================
# WORKFLOW PIPELINE ROUTES (Phase 4: Kanban Pipeline)
# =========================================================================

@app.route('/pipeline')
@requires_auth
def workflow_pipeline():
    """
    Kanban-style pipeline view showing contacts by workflow stage.
    """
    db = get_db()

    # Get pipeline data (contacts grouped by stage)
    pipeline = db.get_workflow_pipeline()

    # Get stage counts
    stage_counts = db.get_workflow_stage_counts()

    # Stage definitions for display
    stages = db.WORKFLOW_STAGES

    return render_template('workflow_pipeline.html',
        pipeline=pipeline,
        stage_counts=stage_counts,
        stages=stages,
        total_contacts=sum(stage_counts.values()))


@app.route('/api/workflow/pipeline')
@requires_auth
def api_workflow_pipeline():
    """API endpoint for pipeline data."""
    db = get_db()

    pipeline = db.get_workflow_pipeline()
    stage_counts = db.get_workflow_stage_counts()

    return jsonify({
        'success': True,
        'pipeline': pipeline,
        'stage_counts': stage_counts,
        'stages': [{'id': s[0], 'name': s[1], 'description': s[2]} for s in db.WORKFLOW_STAGES]
    })


@app.route('/api/contacts/<contact_id>/workflow')
@requires_auth
def api_get_contact_workflow(contact_id):
    """Get workflow state for a contact."""
    db = get_db()

    workflow = db.get_contact_workflow(contact_id)
    if not workflow:
        # Return default state if not initialized
        workflow = {
            'contact_id': contact_id,
            'current_stage': 'new_lead',
            'stage_history': [],
            'workflow_status': 'active'
        }

    # Add inferred stage for comparison
    inferred_stage = db.infer_workflow_stage(contact_id)

    return jsonify({
        'success': True,
        'workflow': workflow,
        'inferred_stage': inferred_stage
    })


@app.route('/api/contacts/<contact_id>/workflow/stage', methods=['POST'])
@requires_auth
def api_update_contact_workflow_stage(contact_id):
    """Update workflow stage for a contact."""
    db = get_db()

    data = request.get_json() or {}
    new_stage = data.get('stage')
    notes = data.get('notes')

    if not new_stage:
        return jsonify({'success': False, 'error': 'Stage is required'}), 400

    # Validate stage
    valid_stages = [s[0] for s in db.WORKFLOW_STAGES]
    if new_stage not in valid_stages:
        return jsonify({'success': False, 'error': f'Invalid stage: {new_stage}'}), 400

    try:
        workflow = db.update_contact_workflow_stage(contact_id, new_stage, notes)
        return jsonify({
            'success': True,
            'workflow': workflow
        })
    except Exception as e:
        logger.error(f"Error updating workflow stage: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/workflow/initialize', methods=['POST'])
@requires_auth
def api_initialize_workflows():
    """Initialize workflow records for all contacts."""
    db = get_db()

    try:
        count = db.bulk_initialize_workflows()
        return jsonify({
            'success': True,
            'initialized': count
        })
    except Exception as e:
        logger.error(f"Error initializing workflows: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/<contact_id>/workflow/auto-stage', methods=['POST'])
@requires_auth
def api_auto_stage_contact(contact_id):
    """Automatically set workflow stage based on contact activity."""
    db = get_db()

    try:
        inferred_stage = db.infer_workflow_stage(contact_id)
        workflow = db.update_contact_workflow_stage(contact_id, inferred_stage, 'Auto-staged based on activity')

        return jsonify({
            'success': True,
            'workflow': workflow,
            'inferred_stage': inferred_stage
        })
    except Exception as e:
        logger.error(f"Error auto-staging contact: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================================================================
# REQUIREMENTS CONSOLIDATION API (Phase 5)
# =========================================================================

@app.route('/api/contacts/<contact_id>/requirements')
@requires_auth
def api_get_requirements(contact_id):
    """Get consolidated requirements for a contact."""
    db = get_db()

    try:
        # Get or create consolidated requirements
        requirements = db.get_consolidated_requirements(contact_id)
        if not requirements:
            requirements = db.consolidate_requirements(contact_id)

        return jsonify({
            'success': True,
            'requirements': requirements
        })
    except Exception as e:
        logger.error(f"Error getting requirements: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/<contact_id>/requirements/sources')
@requires_auth
def api_get_requirements_by_source(contact_id):
    """Get requirements broken down by source for comparison."""
    db = get_db()

    try:
        sources = db.get_requirements_by_source(contact_id)
        return jsonify({
            'success': True,
            'sources': sources
        })
    except Exception as e:
        logger.error(f"Error getting requirements by source: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/<contact_id>/requirements/consolidate', methods=['POST'])
@requires_auth
def api_consolidate_requirements(contact_id):
    """Force re-consolidation of requirements from all sources."""
    db = get_db()

    try:
        requirements = db.consolidate_requirements(contact_id)
        return jsonify({
            'success': True,
            'requirements': requirements
        })
    except Exception as e:
        logger.error(f"Error consolidating requirements: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/<contact_id>/requirements/override', methods=['POST'])
@requires_auth
def api_override_requirement(contact_id):
    """Override a specific requirement field."""
    db = get_db()

    data = request.get_json() or {}
    field_name = data.get('field')
    value = data.get('value')

    if not field_name:
        return jsonify({'success': False, 'error': 'Field name required'}), 400

    try:
        requirements = db.override_requirement(contact_id, field_name, value, 'agent')
        return jsonify({
            'success': True,
            'requirements': requirements
        })
    except Exception as e:
        logger.error(f"Error overriding requirement: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/<contact_id>/requirements/changes')
@requires_auth
def api_get_requirements_changes(contact_id):
    """Get audit trail of requirement changes."""
    db = get_db()

    try:
        changes = db.get_requirements_changes(contact_id)
        return jsonify({
            'success': True,
            'changes': changes
        })
    except Exception as e:
        logger.error(f"Error getting requirement changes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/<contact_id>/requirements/refresh', methods=['POST'])
@requires_auth
def api_refresh_requirements(contact_id):
    """Re-consolidate requirements from all sources."""
    db = get_db()

    try:
        requirements = db.consolidate_requirements(contact_id)
        return jsonify({
            'success': True,
            'requirements': requirements
        })
    except Exception as e:
        logger.error(f"Error refreshing requirements: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# Property Changes Routes
# ==========================================

@app.route('/properties/changes')
@requires_auth
def property_changes():
    """View recent property changes (price drops, status changes, new listings)."""
    from datetime import timedelta

    # Get filter parameters
    change_type = request.args.get('type', '')
    county = request.args.get('county', '')
    days = int(request.args.get('days', 7))

    db = get_db()

    # Calculate cutoff date
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    with db._get_connection() as conn:
        # Property changes table was dropped during Navica migration.
        # Change tracking will be rebuilt by Navica sync_engine's change detection.
        changes = []
        summary = {}
        counties = []

    # Separate changes by type for easier rendering
    # Handle both old format (price, status) and new format (price_change, status_change)
    # DOM changes are no longer tracked (DOM is calculated from list_date)
    all_price_changes = [c for c in changes if c['change_type'] in ('price_change', 'price')]
    new_listings = [c for c in changes if c['change_type'] == 'new_listing']

    # Filter status changes - exclude case-only changes (e.g., "contingent" -> "Contingent")
    status_changes = [
        c for c in changes
        if c['change_type'] in ('status_change', 'status')
        and (c.get('old_value') or '').lower() != (c.get('new_value') or '').lower()
    ]

    # Filter out DOM changes and case-only status changes from the all changes list
    filtered_changes = [
        c for c in changes
        if c['change_type'] not in ('dom_update', 'dom')
        and not (
            c['change_type'] in ('status_change', 'status')
            and (c.get('old_value') or '').lower() == (c.get('new_value') or '').lower()
        )
    ]

    # Deduplicate price changes by address (keep only the most recent per address)
    seen_addresses = set()
    price_changes = []
    for c in all_price_changes:
        addr = c.get('property_address', '')
        if addr not in seen_addresses:
            seen_addresses.add(addr)
            price_changes.append(c)

    # Normalize summary (DOM no longer tracked, use filtered counts)
    normalized_summary = {
        'price_changes': len(price_changes),
        'new_listings': len(new_listings),
        'status_changes': len(status_changes),  # Use filtered count
    }

    return render_template('property_changes.html',
                           changes=filtered_changes,
                           price_changes=price_changes,
                           new_listings=new_listings,
                           status_changes=status_changes,
                           summary=normalized_summary,
                           counties=counties,
                           selected_type=change_type,
                           selected_county=county,
                           selected_days=days,
                           cutoff_date=cutoff,
                           refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


# ==========================================
# Settings Registry & Helpers
# ==========================================

# Category definitions: slug -> (icon, label, description)
SETTINGS_CATEGORIES = [
    ('fub', '👥', 'Follow Up Boss', 'CRM connection and API settings'),
    ('email', '📨', 'Email & Notifications', 'SMTP, alerts, and report settings'),
    ('scoring', '🎯', 'Scoring & Priority', 'Heat, recency, priority, and call list weights'),
    ('integrations', '🔗', 'Integrations', 'Notion, Google Sheets, Apify, and other services'),
    ('scraping', '🕷', 'Web Scraping & Proxy', 'ScraperAPI, Browserless, and proxy configuration'),
    ('idx', '🏠', 'IDX Site', 'IDX website credentials'),
    ('task_sync', '☑', 'Task Sync', 'Todoist and FUB polling configuration'),
    ('linear', '🔧', 'Linear Sync', 'Linear project management integration'),
    ('performance', '⚡', 'Performance', 'Request throttling, caching, and parallelism'),
    ('exclusions', '🚫', 'Exclusions', 'Contacts and emails excluded from scoring'),
    ('agent_info', '👤', 'Agent Info', 'Agent and brokerage details'),
    ('system', '🔒', 'System & Security', 'Environment, auth, database, and CORS'),
    ('automation', None, 'Automation Rules', None),  # Special: link-only
]

# Registry of all .env settings to display
# Each entry: key, label, description, category slug, value_type, is_secret, default
ENV_SETTINGS_REGISTRY = [
    # --- Follow Up Boss ---
    {'key': 'FUB_API_KEY', 'label': 'API Key', 'description': 'Follow Up Boss API key for data sync',
     'category': 'fub', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'FUB_BASE_URL', 'label': 'API Base URL', 'description': 'FUB REST API endpoint',
     'category': 'fub', 'value_type': 'string', 'is_secret': False, 'default': 'https://api.followupboss.com/v1'},
    {'key': 'FUB_APP_URL', 'label': 'App URL', 'description': 'FUB web app URL for deep links',
     'category': 'fub', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'FUB_MY_USER_ID', 'label': 'My User ID', 'description': 'Your FUB user ID for "My Leads" filtering',
     'category': 'fub', 'value_type': 'string', 'is_secret': False, 'default': ''},

    # --- Email & Notifications ---
    {'key': 'SMTP_ENABLED', 'label': 'SMTP Enabled', 'description': 'Enable outbound email notifications',
     'category': 'email', 'value_type': 'string', 'is_secret': False, 'default': 'false'},
    {'key': 'SMTP_SERVER', 'label': 'SMTP Server', 'description': 'Mail server hostname',
     'category': 'email', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'SMTP_PORT', 'label': 'SMTP Port', 'description': 'Mail server port (587 for TLS)',
     'category': 'email', 'value_type': 'string', 'is_secret': False, 'default': '587'},
    {'key': 'SMTP_USERNAME', 'label': 'SMTP Username', 'description': 'Email account username',
     'category': 'email', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'SMTP_PASSWORD', 'label': 'SMTP Password', 'description': 'Email account password or app password',
     'category': 'email', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'EMAIL_TO', 'label': 'Recipient Email', 'description': 'Default email recipient for reports and alerts',
     'category': 'email', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'EMAIL_SUBJECT_PREFIX', 'label': 'Subject Prefix', 'description': 'Prefix for all outbound email subjects',
     'category': 'email', 'value_type': 'string', 'is_secret': False, 'default': ''},

    # --- Scoring & Priority ---
    {'key': 'HEAT_WEIGHT_WEBSITE_VISIT', 'label': 'Website Visit Weight', 'description': 'Points per website visit event',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '1.5'},
    {'key': 'HEAT_WEIGHT_PROPERTY_VIEWED', 'label': 'Property Viewed Weight', 'description': 'Points per property view',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '3.0'},
    {'key': 'HEAT_WEIGHT_PROPERTY_FAVORITED', 'label': 'Property Favorited Weight', 'description': 'Points per property favorited',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '5.0'},
    {'key': 'HEAT_WEIGHT_PROPERTY_SHARED', 'label': 'Property Shared Weight', 'description': 'Points per property shared',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '1.5'},
    {'key': 'HEAT_WEIGHT_CALL_INBOUND', 'label': 'Inbound Call Weight', 'description': 'Points per inbound call',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '5.0'},
    {'key': 'HEAT_WEIGHT_TEXT_INBOUND', 'label': 'Inbound Text Weight', 'description': 'Points per inbound text',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '3.0'},
    {'key': 'RECENCY_BONUS_0_3_DAYS', 'label': 'Recency 0-3 Days', 'description': 'Bonus points for activity in last 3 days',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '25'},
    {'key': 'RECENCY_BONUS_4_7_DAYS', 'label': 'Recency 4-7 Days', 'description': 'Bonus points for activity 4-7 days ago',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '15'},
    {'key': 'RECENCY_BONUS_8_14_DAYS', 'label': 'Recency 8-14 Days', 'description': 'Bonus points for activity 8-14 days ago',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '10'},
    {'key': 'RECENCY_BONUS_15_30_DAYS', 'label': 'Recency 15-30 Days', 'description': 'Bonus points for activity 15-30 days ago',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '5'},
    {'key': 'PRIORITY_WEIGHT_HEAT', 'label': 'Heat Weight in Priority', 'description': 'Weight of heat score in priority calculation (0-1)',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '0.50'},
    {'key': 'CALL_LIST_MIN_PRIORITY', 'label': 'Call List Min Priority', 'description': 'Minimum priority score to appear on call list',
     'category': 'scoring', 'value_type': 'string', 'is_secret': False, 'default': '30'},

    # --- Integrations ---
    {'key': 'NOTION_API_KEY', 'label': 'Notion API Key', 'description': 'Notion integration token',
     'category': 'integrations', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'NOTION_PROPERTIES_DB_ID', 'label': 'Notion Properties DB', 'description': 'Notion database ID for properties',
     'category': 'integrations', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'GOOGLE_SERVICE_ACCOUNT_FILE', 'label': 'Google Service Account', 'description': 'Path to Google service account JSON file',
     'category': 'integrations', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'GOOGLE_SHEET_ID', 'label': 'Google Sheet ID', 'description': 'Target Google Sheets spreadsheet ID',
     'category': 'integrations', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'APIFY_TOKEN', 'label': 'Apify Token', 'description': 'Apify platform API token',
     'category': 'integrations', 'value_type': 'string', 'is_secret': True, 'default': ''},

    # --- Web Scraping & Proxy ---
    {'key': 'SCRAPERAPI_KEY', 'label': 'ScraperAPI Key', 'description': 'ScraperAPI access key for web scraping',
     'category': 'scraping', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'BROWSERLESS_TOKEN', 'label': 'Browserless Token', 'description': 'Browserless.io API token for headless Chrome',
     'category': 'scraping', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'PROXY_HOST', 'label': 'Proxy Host', 'description': 'Residential proxy hostname',
     'category': 'scraping', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'PROXY_PORT', 'label': 'Proxy Port', 'description': 'Residential proxy port',
     'category': 'scraping', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'PROXY_USER', 'label': 'Proxy Username', 'description': 'Residential proxy auth username',
     'category': 'scraping', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'PROXY_PASS', 'label': 'Proxy Password', 'description': 'Residential proxy auth password',
     'category': 'scraping', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'FORCE_LOCAL_BROWSER', 'label': 'Force Local Browser', 'description': 'Skip Browserless and use local Chrome',
     'category': 'scraping', 'value_type': 'string', 'is_secret': False, 'default': 'false'},
    {'key': 'SKIP_PROXY', 'label': 'Skip Proxy', 'description': 'Bypass proxy (use direct connection)',
     'category': 'scraping', 'value_type': 'string', 'is_secret': False, 'default': 'false'},

    # --- IDX Site ---
    {'key': 'IDX_EMAIL', 'label': 'IDX Email', 'description': 'IDX site login email',
     'category': 'idx', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'IDX_PHONE', 'label': 'IDX Phone', 'description': 'IDX site phone number',
     'category': 'idx', 'value_type': 'string', 'is_secret': False, 'default': ''},

    # --- Task Sync ---
    {'key': 'TODOIST_API_TOKEN', 'label': 'Todoist API Token', 'description': 'Todoist personal API token',
     'category': 'task_sync', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'TASK_SYNC_ENV', 'label': 'Task Sync Environment', 'description': 'Task sync environment (dev/prd)',
     'category': 'task_sync', 'value_type': 'string', 'is_secret': False, 'default': 'dev'},
    {'key': 'FUB_POLL_INTERVAL', 'label': 'FUB Poll Interval', 'description': 'Seconds between FUB polling cycles',
     'category': 'task_sync', 'value_type': 'string', 'is_secret': False, 'default': '30'},
    {'key': 'TODOIST_POLL_INTERVAL', 'label': 'Todoist Poll Interval', 'description': 'Seconds between Todoist polling cycles',
     'category': 'task_sync', 'value_type': 'string', 'is_secret': False, 'default': '30'},
    {'key': 'DEAL_CACHE_REFRESH', 'label': 'Deal Cache Refresh', 'description': 'Seconds between deal cache refreshes',
     'category': 'task_sync', 'value_type': 'string', 'is_secret': False, 'default': '300'},

    # --- Linear Sync ---
    {'key': 'LINEAR_API_KEY', 'label': 'Linear API Key', 'description': 'Linear personal API key',
     'category': 'linear', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'LINEAR_SYNC_ENV', 'label': 'Linear Sync Environment', 'description': 'Linear sync environment (dev/prd)',
     'category': 'linear', 'value_type': 'string', 'is_secret': False, 'default': 'dev'},
    {'key': 'LINEAR_POLL_INTERVAL', 'label': 'Linear Poll Interval', 'description': 'Seconds between Linear polling cycles',
     'category': 'linear', 'value_type': 'string', 'is_secret': False, 'default': '30'},
    {'key': 'LINEAR_DEVELOP_TEAM_ID', 'label': 'Develop Team ID', 'description': 'Linear team ID for development tasks',
     'category': 'linear', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'LINEAR_TRANSACT_TEAM_ID', 'label': 'Transact Team ID', 'description': 'Linear team ID for transaction tasks',
     'category': 'linear', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'LINEAR_GENERAL_TEAM_ID', 'label': 'General Team ID', 'description': 'Linear team ID for general tasks',
     'category': 'linear', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'LINEAR_FUB_SYNCED_LABEL_ID', 'label': 'FUB Synced Label', 'description': 'Linear label ID for FUB-synced issues',
     'category': 'linear', 'value_type': 'string', 'is_secret': False, 'default': ''},

    # --- Performance ---
    {'key': 'REQUEST_SLEEP_SECONDS', 'label': 'Request Sleep', 'description': 'Seconds to sleep between API requests',
     'category': 'performance', 'value_type': 'string', 'is_secret': False, 'default': '0.2'},
    {'key': 'DEFAULT_FETCH_LIMIT', 'label': 'Default Fetch Limit', 'description': 'Default number of records per API fetch',
     'category': 'performance', 'value_type': 'string', 'is_secret': False, 'default': '100'},
    {'key': 'MAX_PARALLEL_WORKERS', 'label': 'Max Parallel Workers', 'description': 'Max concurrent worker threads',
     'category': 'performance', 'value_type': 'string', 'is_secret': False, 'default': '5'},
    {'key': 'ENABLE_STAGE_SYNC', 'label': 'Enable Stage Sync', 'description': 'Sync lead stages from FUB',
     'category': 'performance', 'value_type': 'string', 'is_secret': False, 'default': 'false'},
    {'key': 'ENABLE_CACHE', 'label': 'Enable Cache', 'description': 'Enable in-memory caching',
     'category': 'performance', 'value_type': 'string', 'is_secret': False, 'default': 'true'},
    {'key': 'CACHE_MAX_AGE_MINUTES', 'label': 'Cache Max Age', 'description': 'Minutes before cached data expires',
     'category': 'performance', 'value_type': 'string', 'is_secret': False, 'default': '30'},

    # --- Exclusions ---
    {'key': 'EXCLUDE_LEAD_IDS', 'label': 'Excluded Lead IDs', 'description': 'Comma-separated FUB contact IDs to exclude from scoring',
     'category': 'exclusions', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'EXCLUDE_EMAILS', 'label': 'Excluded Emails', 'description': 'Comma-separated email addresses to exclude',
     'category': 'exclusions', 'value_type': 'string', 'is_secret': False, 'default': ''},

    # --- Agent Info ---
    {'key': 'AGENT_NAME', 'label': 'Agent Name', 'description': 'Agent display name',
     'category': 'agent_info', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'AGENT_EMAIL', 'label': 'Agent Email', 'description': 'Agent email address',
     'category': 'agent_info', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'AGENT_PHONE', 'label': 'Agent Phone', 'description': 'Agent phone number',
     'category': 'agent_info', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'BROKERAGE_NAME', 'label': 'Brokerage Name', 'description': 'Brokerage/team name',
     'category': 'agent_info', 'value_type': 'string', 'is_secret': False, 'default': ''},

    # --- System & Security ---
    {'key': 'DREAMS_ENV', 'label': 'Environment', 'description': 'Runtime environment (dev/prd)',
     'category': 'system', 'value_type': 'string', 'is_secret': False, 'default': 'dev'},
    {'key': 'FLASK_DEBUG', 'label': 'Flask Debug Mode', 'description': 'Enable Flask debug mode (dev only)',
     'category': 'system', 'value_type': 'string', 'is_secret': False, 'default': 'false'},
    {'key': 'DREAMS_DB_PATH', 'label': 'Database Path', 'description': 'Path to SQLite database file',
     'category': 'system', 'value_type': 'string', 'is_secret': False, 'default': 'data/dreams.db'},
    {'key': 'DASHBOARD_USERNAME', 'label': 'Dashboard Username', 'description': 'Basic auth username for dashboard',
     'category': 'system', 'value_type': 'string', 'is_secret': False, 'default': ''},
    {'key': 'DASHBOARD_PASSWORD', 'label': 'Dashboard Password', 'description': 'Basic auth password for dashboard',
     'category': 'system', 'value_type': 'string', 'is_secret': True, 'default': ''},
    {'key': 'DREAMS_API_KEY', 'label': 'API Key', 'description': 'API authentication key for property-api',
     'category': 'system', 'value_type': 'string', 'is_secret': True, 'default': ''},
]


def mask_secret(value):
    """Mask a secret value, showing only last 4 chars."""
    if not value:
        return None
    if len(value) <= 4:
        return '••••'
    return '••••••••' + value[-4:]


# Map DB categories to page categories
DB_CATEGORY_MAP = {
    'alerts': 'email',
    'reports': 'email',
    'integrations': 'fub',
    'general': 'system',
    # 'automation' is excluded — it has its own dedicated page
}


def build_settings_page_data(db):
    """
    Build merged settings data from .env registry and DB settings.

    Returns:
        (categories, settings_by_category)
        categories: ordered list of (slug, icon, label, description)
        settings_by_category: dict of slug -> list of setting dicts
    """
    settings_by_category = {}

    # 1. Populate env settings from registry
    for entry in ENV_SETTINGS_REGISTRY:
        cat = entry['category']
        if cat not in settings_by_category:
            settings_by_category[cat] = []

        raw_value = os.getenv(entry['key'], '') or ''
        display_value = mask_secret(raw_value) if entry['is_secret'] and raw_value else raw_value
        is_set = bool(raw_value)

        settings_by_category[cat].append({
            'key': entry['key'],
            'label': entry['label'],
            'description': entry['description'],
            'source': 'env',
            'value_type': entry['value_type'],
            'is_secret': entry['is_secret'],
            'raw_value': raw_value,
            'display_value': display_value,
            'is_set': is_set,
            'default': entry['default'],
        })

    # 2. Add DB settings, mapped to page categories
    all_db_settings = db.get_all_settings()
    for setting in all_db_settings:
        db_cat = setting['category']
        # Skip automation — has its own page
        if db_cat == 'automation':
            continue
        page_cat = DB_CATEGORY_MAP.get(db_cat, db_cat)
        if page_cat not in settings_by_category:
            settings_by_category[page_cat] = []

        # Build a friendly label from key
        label = setting['key'].replace('_', ' ').title()
        # Special labels for well-known keys
        FRIENDLY_LABELS = {
            'alerts_global_enabled': 'Master Alert Switch',
            'new_listing_alerts_enabled': 'New Listing Alerts',
            'new_listing_match_threshold': 'New Listing Match Threshold',
            'alert_lookback_hours': 'Alert Lookback Period',
            'max_properties_per_alert': 'Max Properties Per Alert Email',
            'price_drop_alerts_enabled': 'Price Drop Alerts',
            'price_drop_match_threshold': 'Price Drop Match Threshold',
            'min_price_drop_pct': 'Min Price Drop Percentage',
            'weekly_summary_enabled': 'Weekly Market Summary',
            'monthly_report_enabled': 'Monthly Lead Report',
            'fub_note_push_enabled': 'Push Matches to FUB Notes',
        }
        label = FRIENDLY_LABELS.get(setting['key'], label)

        settings_by_category[page_cat].append({
            'key': setting['key'],
            'label': label,
            'description': setting['description'],
            'source': 'db',
            'value_type': setting['value_type'],
            'value': setting['value'],
            'converted_value': setting['converted_value'],
            'updated_at': setting.get('updated_at'),
            'updated_by': setting.get('updated_by'),
            'is_master': setting['key'] == 'alerts_global_enabled',
        })

    # 3. Return categories in defined order (skip empty ones and automation)
    categories = []
    for slug, icon, label, description in SETTINGS_CATEGORIES:
        if slug == 'automation':
            categories.append((slug, icon, label, description))
        elif slug in settings_by_category:
            categories.append((slug, icon, label, description))

    return categories, settings_by_category


# ==========================================
# Admin Settings Routes
# ==========================================

@app.route('/admin/settings')
@requires_auth
def admin_settings():
    """Admin settings page — merged .env + DB settings, organized by category."""
    db = get_db()
    categories, settings_by_category = build_settings_page_data(db)

    return render_template('admin_settings.html',
                           categories=categories,
                           settings_by_category=settings_by_category,
                           env_name=DREAMS_ENV)


@app.route('/admin/settings', methods=['POST'])
@requires_auth
def admin_settings_save():
    """Save admin settings."""
    db = get_db()

    try:
        # Get all current settings to know what keys to update
        all_settings = db.get_all_settings()

        for setting in all_settings:
            key = setting['key']
            value_type = setting['value_type']

            # Handle boolean settings (checkboxes)
            if value_type == 'boolean':
                # Checkbox: present = true, absent = false
                new_value = key in request.form
            else:
                # Get the value from form
                new_value = request.form.get(key)
                if new_value is None:
                    continue

                # Convert to appropriate type
                if value_type == 'integer':
                    new_value = int(new_value)
                elif value_type == 'float':
                    new_value = float(new_value)

            # Update the setting
            db.set_setting(key, new_value, updated_by='admin')

        return redirect(url_for('admin_settings') + '?saved=1')

    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return redirect(url_for('admin_settings') + '?error=' + str(e))


@app.route('/api/admin/settings', methods=['GET'])
@requires_auth
def api_get_settings():
    """API endpoint to get all settings."""
    db = get_db()

    try:
        settings = db.get_all_settings()
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/settings/<key>', methods=['PUT'])
@requires_auth
def api_update_setting(key):
    """API endpoint to update a single setting."""
    db = get_db()

    try:
        data = request.get_json()
        value = data.get('value')

        if value is None:
            return jsonify({'success': False, 'error': 'Value is required'}), 400

        db.set_setting(key, value, updated_by='admin')

        return jsonify({
            'success': True,
            'key': key,
            'value': value
        })
    except Exception as e:
        logger.error(f"Error updating setting: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# PDF Generator Routes
# ==========================================

@app.route('/pdf-generator')
@requires_auth
def pdf_generator():
    """PDF generator page for creating lead profile PDFs."""
    return render_template('pdf_generator.html')


@app.route('/api/leads/search')
@requires_auth
def api_leads_search():
    """API endpoint to search leads for PDF generator dropdown."""
    db = get_db()
    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 50)), 100)

    try:
        with db._get_connection() as conn:
            if query and len(query) >= 2:
                # Search by name, email, or phone
                sql = '''
                    SELECT id, fub_id, first_name, last_name, email, phone,
                           stage, heat_score, priority_score, days_since_activity
                    FROM leads
                    WHERE first_name LIKE ? OR last_name LIKE ?
                       OR email LIKE ? OR phone LIKE ?
                    ORDER BY
                        CASE WHEN days_since_activity IS NULL THEN 1 ELSE 0 END,
                        days_since_activity ASC,
                        heat_score DESC
                    LIMIT ?
                '''
                search_term = f'%{query}%'
                rows = conn.execute(sql, (search_term, search_term, search_term, search_term, limit)).fetchall()
            else:
                # Return leads sorted by most recent activity
                sql = '''
                    SELECT id, fub_id, first_name, last_name, email, phone,
                           stage, heat_score, priority_score, days_since_activity
                    FROM leads
                    WHERE stage NOT IN ('Trash', 'Agents/Vendors/Lendors')
                    ORDER BY
                        CASE WHEN days_since_activity IS NULL THEN 1 ELSE 0 END,
                        days_since_activity ASC,
                        heat_score DESC
                    LIMIT ?
                '''
                rows = conn.execute(sql, (limit,)).fetchall()

            leads = []
            for row in rows:
                leads.append({
                    'id': row[0],
                    'fub_id': row[1],
                    'first_name': row[2],
                    'last_name': row[3],
                    'email': row[4],
                    'phone': row[5],
                    'stage': row[6],
                    'heat_score': row[7] or 0,
                    'priority_score': row[8] or 0,
                    'days_since_activity': row[9]
                })

            return jsonify({
                'success': True,
                'leads': leads,
                'count': len(leads)
            })

    except Exception as e:
        logger.error(f"Error searching leads: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pdf/generate/<lead_id>', methods=['POST'])
@requires_auth
def api_generate_pdf(lead_id):
    """API endpoint to generate a lead profile PDF."""
    try:
        # Run the PDF generator script
        script_path = PROJECT_ROOT / 'scripts' / 'generate_lead_pdf.py'
        venv_python = PROJECT_ROOT / '.venv' / 'bin' / 'python3'

        # Use venv python if available, otherwise system python
        python_cmd = str(venv_python) if venv_python.exists() else 'python3'

        result = subprocess.run(
            [python_cmd, str(script_path), '--id', str(lead_id)],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=30
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or 'Unknown error generating PDF'
            logger.error(f"PDF generation failed: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500

        # Parse output to get filename
        output_lines = result.stdout.strip().split('\n')
        pdf_path = None
        for line in output_lines:
            if 'PDF created:' in line:
                pdf_path = line.split('PDF created:')[1].strip()
                break

        if not pdf_path:
            return jsonify({'success': False, 'error': 'Could not determine PDF path'}), 500

        # Get just the filename
        filename = os.path.basename(pdf_path)

        return jsonify({
            'success': True,
            'filename': filename,
            'download_url': f'/pdf/download/{filename}'
        })

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'PDF generation timed out'}), 500
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/pdf/download/<filename>')
@requires_auth
def download_pdf(filename):
    """Serve generated PDF files for download."""
    from flask import send_file

    # Security: ensure filename is safe
    if '..' in filename or '/' in filename:
        return jsonify({'error': 'Invalid filename'}), 400

    pdf_path = PROJECT_ROOT / 'output' / filename

    if not pdf_path.exists():
        return jsonify({'error': 'PDF not found'}), 404

    return send_file(
        pdf_path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# ==========================================
# Listings Gallery (New Schema)
# ==========================================

@app.route('/listings')
@requires_auth
def listings_gallery():
    """Listings gallery view - showcases properties with photos from new schema."""
    import json as json_lib

    # Get filter parameters
    county = request.args.get('county', '')
    city = request.args.get('city', '')
    status = request.args.get('status', 'ACTIVE')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    photos_only = request.args.get('photos_only', '1')  # Default to photos only

    # Pagination
    page = max(1, int(request.args.get('page', 1)))
    per_page = 24  # Good for grid layout

    with db._get_connection() as conn:
        # Get filter options from listings (denormalized address data)
        counties = [r[0] for r in conn.execute(
            "SELECT DISTINCT county FROM listings WHERE county IS NOT NULL AND county != '' ORDER BY county"
        ).fetchall()]

        cities = [r[0] for r in conn.execute(
            "SELECT DISTINCT city FROM listings WHERE city IS NOT NULL AND city != '' ORDER BY city"
        ).fetchall()]

        statuses = [r[0] for r in conn.execute(
            "SELECT DISTINCT status FROM listings WHERE status IS NOT NULL ORDER BY status"
        ).fetchall()]

        # Build query for listings with denormalized address data
        # (faster than JOIN - address fields now on listings table)
        query = '''
            SELECT
                l.id as listing_id,
                l.mls_source,
                l.mls_number,
                l.status,
                l.list_price,
                l.beds,
                l.baths,
                l.sqft,
                l.year_built,
                l.property_type,
                l.primary_photo,
                l.photos,
                l.redfin_url,
                l.listing_agent_name,
                l.listing_agent_phone,
                l.parcel_id,
                l.address,
                l.city,
                l.county,
                l.state,
                l.zip,
                l.latitude,
                l.longitude,
                l.acreage,
                l.photo_confidence,
                l.photo_review_status
            FROM listings l
            WHERE 1=1
        '''
        params = []

        if photos_only == '1':
            query += ' AND l.primary_photo IS NOT NULL'

        if status:
            query += ' AND l.status = ?'
            params.append(status)

        if county:
            query += ' AND l.county = ?'
            params.append(county)

        if city:
            query += ' AND l.city = ?'
            params.append(city)

        if min_price:
            query += ' AND l.list_price >= ?'
            params.append(int(min_price))

        if max_price:
            query += ' AND l.list_price <= ?'
            params.append(int(max_price))

        # Count total
        count_query = query.replace('SELECT\n                l.id as listing_id', 'SELECT COUNT(*)')
        count_query = count_query.split('FROM listings')[0] + 'COUNT(*) FROM listings' + count_query.split('FROM listings')[1]
        # Simpler approach
        count_result = conn.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()
        total_count = count_result[0] if count_result else 0

        total_pages = max(1, (total_count + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        # Add sorting and pagination
        query += ' ORDER BY l.list_price DESC LIMIT ? OFFSET ?'
        params.extend([per_page, offset])

        rows = conn.execute(query, params).fetchall()

        # Convert to list of dicts
        listings = []
        for row in rows:
            listing = dict(row)
            # Parse photos JSON if present
            if listing.get('photos'):
                try:
                    listing['photos_list'] = json_lib.loads(listing['photos'])
                except:
                    listing['photos_list'] = []
            else:
                listing['photos_list'] = []
            listings.append(listing)

    return render_template('listings_gallery.html',
                         listings=listings,
                         counties=counties,
                         cities=cities,
                         statuses=statuses,
                         selected_county=county,
                         selected_city=city,
                         selected_status=status,
                         min_price=min_price,
                         max_price=max_price,
                         photos_only=photos_only,
                         page=page,
                         total_pages=total_pages,
                         total_count=total_count,
                         per_page=per_page)


@app.route('/photos')
@requires_auth
def photos_dashboard():
    """Photo enrichment dashboard - shows photo stats and review queue."""
    view = request.args.get('view', 'verified')  # verified, pending, all
    page = max(1, int(request.args.get('page', 1)))
    per_page = 24

    with db._get_connection() as conn:
        # Get photo enrichment stats
        stats = {}
        stats['total_active'] = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE status = 'ACTIVE'"
        ).fetchone()[0]
        stats['with_photos'] = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE primary_photo IS NOT NULL"
        ).fetchone()[0]
        stats['verified'] = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE photo_review_status = 'verified'"
        ).fetchone()[0]
        stats['pending_review'] = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE photo_review_status = 'pending_review'"
        ).fetchone()[0]
        stats['rejected'] = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE photo_review_status = 'rejected'"
        ).fetchone()[0]
        stats['no_photos'] = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE status = 'ACTIVE' AND (primary_photo IS NULL OR primary_photo = '')"
        ).fetchone()[0]

        # Confidence breakdown
        confidence_stats = conn.execute('''
            SELECT
                CASE
                    WHEN photo_confidence >= 90 THEN '90-100%'
                    WHEN photo_confidence >= 70 THEN '70-89%'
                    WHEN photo_confidence >= 50 THEN '50-69%'
                    ELSE 'Below 50%'
                END as confidence_range,
                COUNT(*) as count
            FROM listings
            WHERE photo_confidence IS NOT NULL
            GROUP BY confidence_range
            ORDER BY confidence_range DESC
        ''').fetchall()
        stats['confidence_breakdown'] = {r[0]: r[1] for r in confidence_stats}

        # Source breakdown
        source_stats = conn.execute('''
            SELECT photo_source, COUNT(*) as count
            FROM listings
            WHERE photo_source IS NOT NULL
            GROUP BY photo_source
            ORDER BY count DESC
        ''').fetchall()
        stats['source_breakdown'] = {r[0]: r[1] for r in source_stats}

        # Build query based on view
        if view == 'pending':
            where_clause = "WHERE photo_review_status = 'pending_review'"
        elif view == 'all':
            where_clause = "WHERE primary_photo IS NOT NULL"
        else:  # verified (default)
            where_clause = "WHERE photo_review_status = 'verified'"

        # Get total count for pagination
        total_count = conn.execute(f"SELECT COUNT(*) FROM listings {where_clause}").fetchone()[0]
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        offset = (page - 1) * per_page

        # Get filter options
        counties = [r[0] for r in conn.execute(
            "SELECT DISTINCT l.county FROM listings l WHERE l.primary_photo IS NOT NULL AND l.county IS NOT NULL ORDER BY l.county"
        ).fetchall()]

        # Apply additional filters
        county_filter = request.args.get('county', '')
        min_price = request.args.get('min_price', '')
        max_price = request.args.get('max_price', '')
        sort_by = request.args.get('sort', 'newest')

        extra_where = ""
        params = []
        if county_filter:
            extra_where += " AND l.county = ?"
            params.append(county_filter)
        if min_price:
            extra_where += " AND l.list_price >= ?"
            params.append(int(min_price))
        if max_price:
            extra_where += " AND l.list_price <= ?"
            params.append(int(max_price))

        # Sort options
        sort_map = {
            'newest': 'l.captured_at DESC',
            'price_high': 'l.list_price DESC',
            'price_low': 'l.list_price ASC',
            'beds': 'l.beds DESC',
            'acreage': 'l.acreage DESC',
            'elevation': 'p.elevation_feet DESC',
        }
        order_by = sort_map.get(sort_by, 'l.captured_at DESC')

        # Get listings with parcel geospatial data
        base_where = where_clause.replace('WHERE', 'WHERE l.')
        listings = conn.execute(f'''
            SELECT
                l.id, l.address, l.city, l.county, l.zip, l.state,
                l.list_price, l.beds, l.baths, l.sqft, l.acreage,
                l.year_built, l.property_type, l.style, l.days_on_market,
                l.hoa_fee,
                l.primary_photo, l.photo_source, l.photo_confidence, l.photo_review_status,
                l.redfin_url, l.idx_url, l.mls_number, l.mls_source,
                l.listing_agent_name, l.listing_agent_phone, l.listing_office_name,
                l.latitude, l.longitude
            FROM listings l
            {base_where} {extra_where}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        ''', params + [per_page, offset]).fetchall()
        listings = [dict(row) for row in listings]

    return render_template('photos_dashboard.html',
                         listings=listings,
                         stats=stats,
                         view=view,
                         page=page,
                         total_pages=total_pages,
                         total_count=total_count,
                         counties=counties,
                         selected_county=county_filter,
                         min_price=min_price,
                         max_price=max_price,
                         sort_by=sort_by)


@app.route('/api/photos/<listing_id>/approve', methods=['POST'])
@requires_auth
def approve_photo(listing_id):
    """Approve a pending photo."""
    with db._get_connection() as conn:
        conn.execute('''
            UPDATE listings
            SET photo_review_status = 'verified',
                photo_verified_by = 'manual',
                photo_verified_at = datetime('now')
            WHERE id = ?
        ''', [listing_id])
        conn.commit()
    return jsonify({'success': True})


@app.route('/api/photos/<listing_id>/reject', methods=['POST'])
@requires_auth
def reject_photo(listing_id):
    """Reject a photo (clears the photo)."""
    with db._get_connection() as conn:
        conn.execute('''
            UPDATE listings
            SET photo_review_status = 'rejected',
                primary_photo = NULL,
                photo_verified_by = 'manual',
                photo_verified_at = datetime('now')
            WHERE id = ?
        ''', [listing_id])
        conn.commit()
    return jsonify({'success': True})


@app.route('/api/listings/<listing_id>')
@requires_auth
def api_listing_detail(listing_id):
    """API endpoint for listing details."""
    import json as json_lib

    with db._get_connection() as conn:
        row = conn.execute('''
            SELECT l.*
            FROM listings l
            WHERE l.id = ?
        ''', [listing_id]).fetchone()

        if not row:
            return jsonify({'error': 'Listing not found'}), 404

        listing = dict(row)
        if listing.get('photos'):
            try:
                listing['photos'] = json_lib.loads(listing['photos'])
            except:
                listing['photos'] = []

        return jsonify(listing)


@app.route('/photos/<path:filename>')
@requires_auth
def serve_photo(filename):
    """Serve MLS photos from data/photos directory."""
    photos_dir = PROJECT_ROOT / 'data' / 'photos'
    return send_from_directory(photos_dir, filename)


@app.route('/data-quality')
@requires_auth
def data_quality():
    """Data quality monitoring dashboard."""
    db_conn = get_db()

    # Listings stats
    listings_stats = db_conn.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN mls_number IS NOT NULL AND mls_number != '' THEN 1 END) as has_mls,
            COUNT(CASE WHEN photos IS NOT NULL AND photos != '[]' AND photos != '' THEN 1 END) as has_photos_json,
            COUNT(CASE WHEN primary_photo IS NOT NULL AND primary_photo != '' THEN 1 END) as has_primary_photo,
            COUNT(CASE WHEN latitude IS NOT NULL AND latitude != 0 THEN 1 END) as has_coords,
            COUNT(CASE WHEN listing_agent_name IS NOT NULL AND listing_agent_name != '' THEN 1 END) as has_agent,
            COUNT(CASE WHEN parcel_id IS NOT NULL THEN 1 END) as has_parcel,
            COUNT(CASE WHEN status = 'ACTIVE' THEN 1 END) as active,
            COUNT(CASE WHEN status = 'PENDING' THEN 1 END) as pending,
            COUNT(CASE WHEN status = 'SOLD' THEN 1 END) as sold
        FROM listings
    """).fetchone()

    # Listings by source
    source_stats = db_conn.execute("""
        SELECT
            mls_source,
            COUNT(*) as count,
            COUNT(CASE WHEN mls_number IS NOT NULL AND mls_number != '' THEN 1 END) as has_mls,
            COUNT(CASE WHEN photos IS NOT NULL AND photos != '[]' AND photos != '' THEN 1 END) as has_photos,
            COUNT(CASE WHEN listing_agent_name IS NOT NULL AND listing_agent_name != '' THEN 1 END) as has_agent,
            MAX(updated_at) as last_updated
        FROM listings
        GROUP BY mls_source
        ORDER BY count DESC
    """).fetchall()

    # Parcels stats (parcels table retired in Navica migration; spatial data now on listings)
    parcels_stats = {'total': 0, 'has_coords': 0, 'has_flood': 0, 'has_elevation': 0, 'spatially_enriched': 0, 'last_spatial_enrichment': None}

    # Photo coverage by source
    photo_stats = db_conn.execute("""
        SELECT
            COALESCE(photo_source, 'none') as source,
            COUNT(*) as count,
            ROUND(AVG(photo_confidence), 1) as avg_confidence
        FROM listings
        GROUP BY photo_source
        ORDER BY count DESC
    """).fetchall()

    # Photo review status
    review_stats = db_conn.execute("""
        SELECT
            COALESCE(photo_review_status, 'not_reviewed') as status,
            COUNT(*) as count
        FROM listings
        GROUP BY photo_review_status
        ORDER BY count DESC
    """).fetchall()

    # Coverage by city (top 10)
    city_coverage = db_conn.execute("""
        SELECT
            city,
            COUNT(*) as total,
            COUNT(CASE WHEN mls_number IS NOT NULL AND mls_number != '' THEN 1 END) as has_mls,
            COUNT(CASE WHEN primary_photo IS NOT NULL AND primary_photo != '' THEN 1 END) as has_photo
        FROM listings
        WHERE status = 'ACTIVE'
        GROUP BY city
        ORDER BY total DESC
        LIMIT 10
    """).fetchall()

    # Import history (last 10 imports based on created_at clusters)
    recent_imports = db_conn.execute("""
        SELECT
            DATE(created_at) as import_date,
            mls_source,
            COUNT(*) as records
        FROM listings
        WHERE created_at > datetime('now', '-30 days')
        GROUP BY DATE(created_at), mls_source
        ORDER BY import_date DESC
        LIMIT 10
    """).fetchall()

    # MLS Grid sync state
    mlsgrid_state = {}
    state_file = PROJECT_ROOT / 'data' / 'mlsgrid_sync_state.json'
    if state_file.exists():
        import json as json_lib
        with open(state_file) as f:
            mlsgrid_state = json_lib.load(f)

    return render_template('data_quality.html',
                          listings_stats=dict(listings_stats),
                          source_stats=[dict(s) for s in source_stats],
                          parcels_stats=dict(parcels_stats),
                          photo_stats=[dict(s) for s in photo_stats],
                          review_stats=[dict(s) for s in review_stats],
                          city_coverage=[dict(c) for c in city_coverage],
                          recent_imports=[dict(i) for i in recent_imports],
                          mlsgrid_state=mlsgrid_state,
                          refresh_time=datetime.now(tz=ET).strftime('%B %d, %Y %I:%M %p'))


@app.route('/api/data-quality')
@requires_auth
def api_data_quality():
    """Data quality API endpoint for programmatic access."""
    db_conn = get_db()

    stats = db_conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM listings) as total_listings,
            (SELECT COUNT(*) FROM listings WHERE mls_number IS NOT NULL AND mls_number != '') as listings_with_mls,
            (SELECT COUNT(*) FROM listings WHERE primary_photo IS NOT NULL AND primary_photo != '') as listings_with_photos,
            (SELECT COUNT(*) FROM listings WHERE latitude IS NOT NULL AND latitude != 0) as listings_with_coords
    """).fetchone()

    return jsonify({
        'listings': {
            'total': stats['total_listings'],
            'with_mls_number': stats['listings_with_mls'],
            'with_photos': stats['listings_with_photos'],
            'with_coords': stats['listings_with_coords'],
            'mls_coverage_pct': round(stats['listings_with_mls'] / stats['total_listings'] * 100, 1) if stats['total_listings'] else 0,
            'photo_coverage_pct': round(stats['listings_with_photos'] / stats['total_listings'] * 100, 1) if stats['total_listings'] else 0,
        },
        'timestamp': datetime.now().isoformat(),
    })


# ==========================================
# Automation Rules Admin Routes
# ==========================================

@app.route('/admin/automation')
@requires_auth
def admin_automation():
    """Automation rules configuration and log viewer."""
    db = get_db()

    # Build settings dict for template
    all_settings = db.get_all_settings()
    settings = {}
    for s in all_settings:
        settings[s['key']] = s['converted_value']

    # Get automation stats and log
    stats = db.get_automation_stats()
    log_entries = db.get_automation_log(limit=50)

    return render_template('admin_automation.html',
                           settings=settings,
                           stats=stats,
                           log_entries=log_entries)


@app.route('/admin/automation', methods=['POST'])
@requires_auth
def admin_automation_save():
    """Save automation rule settings."""
    db = get_db()

    # All automation setting keys and their types
    automation_settings = {
        # Booleans (checkboxes)
        'rules_engine_enabled': 'boolean',
        'rule_activity_burst_enabled': 'boolean',
        'rule_going_cold_enabled': 'boolean',
        'rule_hot_lead_enabled': 'boolean',
        'rule_warming_lead_enabled': 'boolean',
        'rule_new_lead_enabled': 'boolean',
        # Integers
        'rule_activity_burst_threshold': 'integer',
        'rule_activity_burst_cooldown_hours': 'integer',
        'rule_going_cold_days': 'integer',
        'rule_going_cold_min_heat': 'integer',
        'rule_going_cold_cooldown_hours': 'integer',
        'rule_hot_lead_threshold': 'integer',
        'rule_hot_lead_cooldown_hours': 'integer',
        'rule_warming_lead_min_delta': 'integer',
        'rule_warming_lead_cooldown_hours': 'integer',
        'rule_new_lead_hours': 'integer',
        # Strings
        'rules_agent_email': 'string',
    }

    try:
        for key, value_type in automation_settings.items():
            if value_type == 'boolean':
                new_value = key in request.form
            elif value_type == 'integer':
                raw = request.form.get(key)
                if raw is None:
                    continue
                new_value = int(raw)
            else:
                new_value = request.form.get(key, '')

            db.set_setting(key, new_value, updated_by='admin')

        return redirect(url_for('admin_automation') + '?saved=1')
    except Exception as e:
        logger.error(f"Error saving automation settings: {e}")
        return redirect(url_for('admin_automation') + '?error=' + str(e))


# ---------------------------------------------------------------------------
# SOP Documents
# ---------------------------------------------------------------------------

@app.route('/sop/lead-gen-calling')
@requires_auth
def sop_lead_gen_calling():
    """Serve the Lead Generation Calling SOP as a dashboard page with sidebar."""
    return render_template('sop_wrapper.html', active_nav='sop-calling',
                           sop_title='Lead Generation Calling SOP')


# ---------------------------------------------------------------------------
# FUB Smart Lists — live comparison view
# ---------------------------------------------------------------------------

# FUB client (lazy init)
_fub_client = None

def _get_fub_client():
    global _fub_client
    if _fub_client is None:
        api_key = os.getenv('FUB_API_KEY')
        if not api_key:
            return None
        from fub_core import FUBClient
        _fub_client = FUBClient(api_key=api_key, logger=logger)
    return _fub_client

# Canonical list definitions: cadence labels + DREAMS mapping
SMART_LIST_MAP = {
    'New Leads':        {'dreams_key': 'new_leads',        'cadence': 'Daily'},
    'Priority':         {'dreams_key': 'priority',         'cadence': 'Semiweekly'},
    'Hot':              {'dreams_key': 'hot',              'cadence': 'Weekly'},
    'Warm':             {'dreams_key': 'warm',             'cadence': 'Monthly'},
    'Cool':             {'dreams_key': 'cool',             'cadence': 'Quarterly'},
    'Unresponsive':     {'dreams_key': 'unresponsive',     'cadence': 'Biweekly'},
    'Timeframe Empty':  {'dreams_key': 'timeframe_empty',  'cadence': 'As needed'},
}

SMART_LIST_ORDER = ['New Leads', 'Priority', 'Hot', 'Warm', 'Cool', 'Unresponsive', 'Timeframe Empty']


def _bucket_fub_contacts(people):
    """
    Bucket FUB contacts into cadence categories matching FUB's actual filters.

    These rules come directly from FUB's saved smart-list filter configs:
      New Leads:       Stage=Lead, created < 14 days, lastComm > 12 hours ago
      Priority:        Stage=Hot Prospect, lastComm > 3 days ago
      Hot:             Stage=Nurture, timeframe=0-3 Months (id=1), lastComm > 7 days ago
      Warm:            Stage=Nurture, timeframe=3-6 Months (id=2), lastComm > 30 days ago
      Cool:            Stage=Nurture, timeframe in (6-12, 12+, No Plans) (id=3,4,5), lastComm > 90 days ago
      Unresponsive:    Stage=Lead, created > 14 days, lastComm > 14 days ago
      Timeframe Empty: Stage=Nurture, timeframe is empty (no timeframeId)
    """
    from datetime import timedelta, timezone
    now = datetime.now(timezone.utc)

    buckets = {k: [] for k in ['new_leads', 'priority', 'hot', 'warm', 'cool', 'unresponsive', 'timeframe_empty']}

    def _parse_contact(p):
        phones = p.get('phones', [])
        phone = phones[0].get('value', '') if phones else ''
        lc = p.get('lastCommunication')
        lc_date = None
        lc_hours = 999999
        if lc and isinstance(lc, dict) and lc.get('date'):
            try:
                lc_date = datetime.fromisoformat(lc['date'].replace('Z', '+00:00'))
                lc_hours = (now - lc_date).total_seconds() / 3600
            except (ValueError, TypeError):
                pass
        created_dt = None
        created_str = p.get('created', '')
        if created_str:
            try:
                created_dt = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pass
        # Use fractional days to match FUB's datetime-level comparison
        lc_days_f = lc_hours / 24 if lc_hours < 999999 else 9999
        emails = p.get('emails', [])
        email = emails[0].get('value', '') if emails else ''
        return {
            'id': p.get('id'),
            'first_name': p.get('firstName', ''),
            'last_name': p.get('lastName', ''),
            'name': f"{p.get('firstName', '')} {p.get('lastName', '')}".strip(),
            'email': email,
            'phone': phone,
            'stage': p.get('stage', ''),
            'contacted': p.get('contacted', 0),
            'lastActivity': p.get('lastActivity', ''),
            'lastComm': lc_date.isoformat() if lc_date else None,
            'lastCommDays': int(lc_days_f),
            'lastCommHours': lc_hours,
            'timeframeId': p.get('timeframeId'),
            'timeframeStatus': p.get('timeframeStatus'),
            'created': created_str,
            '_created_dt': created_dt,
            '_lc_days_f': lc_days_f,
        }

    parsed = [_parse_contact(p) for p in people]

    for c in parsed:
        stage = c['stage']
        tf_id = c['timeframeId']
        lc_hours = c['lastCommHours']
        lc_days = c.pop('_lc_days_f')  # fractional days for accurate threshold comparison
        created_dt = c.pop('_created_dt', None)  # internal, remove from output

        # --- New Leads: Stage=Lead, created < 14 days, lastComm > 12 hours ago ---
        if stage == 'Lead' and created_dt:
            age_days = (now - created_dt).total_seconds() / 86400
            if age_days < 14 and lc_hours > 12:
                buckets['new_leads'].append(c)
                continue

        # --- Priority: Stage=Hot Prospect, lastComm > 3 days ago ---
        if stage == 'Hot Prospect' and lc_days > 3:
            buckets['priority'].append(c)
            continue

        # --- Stage=Nurture buckets (Hot, Warm, Cool, Timeframe Empty) ---
        if stage == 'Nurture':
            # Timeframe Empty: no timeframeId set
            if tf_id is None:
                buckets['timeframe_empty'].append(c)
                continue
            # Hot: timeframe=0-3 Months (id=1), lastComm > 7 days
            if tf_id == 1 and lc_days > 7:
                buckets['hot'].append(c)
                continue
            # Warm: timeframe=3-6 Months (id=2), lastComm > 30 days
            if tf_id == 2 and lc_days > 30:
                buckets['warm'].append(c)
                continue
            # Cool: timeframe in 6-12 (3), 12+ (4), No Plans (5), lastComm > 90 days
            if tf_id in (3, 4, 5) and lc_days > 90:
                buckets['cool'].append(c)
                continue

        # --- Unresponsive: Stage=Lead, created > 14 days, lastComm > 14 days ago ---
        if stage == 'Lead' and created_dt:
            age_days = (now - created_dt).total_seconds() / 86400
            if age_days > 14 and lc_days > 14:
                buckets['unresponsive'].append(c)
                continue

    # Sort: new_leads by created DESC, priority by lastComm ASC, others by lastCommDays ASC
    buckets['new_leads'].sort(key=lambda c: c.get('created', ''), reverse=True)
    for key in ['priority', 'hot', 'warm', 'cool', 'unresponsive', 'timeframe_empty']:
        buckets[key].sort(key=lambda c: c.get('lastCommDays', 9999))

    return buckets


def _explain_fub_only(contact, dreams_key, dreams_db):
    """Explain why a FUB contact is NOT on the matching DREAMS list."""
    fub_id = contact.get('id')
    if not fub_id:
        return "No FUB ID"

    with dreams_db._get_connection() as conn:
        row = conn.execute(
            "SELECT heat_score, priority_score, relationship_score, stage, created_at, contact_group "
            "FROM leads WHERE fub_id = ?", [fub_id]
        ).fetchone()

    if not row:
        return "Not synced to DREAMS"

    lead = dict(row)
    heat = lead.get('heat_score') or 0
    rel = lead.get('relationship_score') or 0
    stage = lead.get('stage', '')
    group = lead.get('contact_group', '')
    created = lead.get('created_at', '')

    if group != 'scored':
        return f"Contact group is '{group}', not 'scored'"

    if stage in ('Trash', 'Closed', 'Past Client', 'DNC', 'Agents/Vendors/Lendors'):
        return f"DREAMS excludes stage '{stage}'"

    if dreams_key == 'new_leads':
        if stage != 'Lead':
            return f"Stage is '{stage}', not 'Lead'"
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        if created and created < cutoff:
            days_ago = (datetime.now() - datetime.fromisoformat(created.replace('Z', ''))).days
            return f"Created {days_ago} days ago (DREAMS uses 7-day window)"
    elif dreams_key == 'hot':
        return f"Heat score is {heat} (threshold: 70). FUB uses Stage=Nurture + timeframe=0-3mo + lastComm >7d"
    elif dreams_key == 'warm':
        if heat >= 70:
            return f"Heat {heat} → Hot in DREAMS. FUB uses Stage=Nurture + timeframe=3-6mo + lastComm >30d"
        return f"Heat score {heat} (range: 40-69). FUB uses Stage=Nurture + timeframe=3-6mo"
    elif dreams_key == 'cool':
        if heat >= 40:
            return f"Heat {heat} → higher tier in DREAMS. FUB uses Stage=Nurture + timeframe=6-12/12+/No Plans + lastComm >90d"
        return f"Heat score {heat} (range: 10-39). FUB uses Stage=Nurture + long timeframe"
    elif dreams_key == 'unresponsive':
        if rel >= 15:
            return f"Relationship score {rel} (threshold: <15). FUB uses Stage=Lead + created >14d + lastComm >14d"
        if heat <= 5:
            return f"Heat {heat} (needs >5). FUB uses Stage=Lead + created >14d + lastComm >14d"
    elif dreams_key == 'timeframe_empty':
        tf = lead.get('fub_timeframe')
        if tf:
            tf_names = {1: '0-3 Months', 2: '3-6 Months', 3: '6-12 Months', 4: '12+ Months', 5: 'No Plans'}
            return f"Has FUB timeframe set ({tf_names.get(tf, tf)}). Both FUB and DREAMS require empty timeframe"
        return f"Timeframe is empty but may not meet other FUB criteria (Stage=Nurture required)"
    elif dreams_key == 'priority':
        return f"Priority score {lead.get('priority_score', 0)} — not in top tier. FUB uses Stage=Hot Prospect + lastComm >3d"

    return "Criteria mismatch"


# FUB timeframe ID → label mapping
FUB_TIMEFRAME_NAMES = {1: '0-3 Months', 2: '3-6 Months', 3: '6-12 Months', 4: '12+ Months', 5: 'No Plans'}


def _explain_dreams_only(contact, dreams_key):
    """Explain why a DREAMS contact is NOT on the matching FUB list."""
    heat = contact.get('heat_score') or 0
    rel = contact.get('relationship_score') or 0
    stage = contact.get('stage', '')

    if dreams_key == 'new_leads':
        return f"DREAMS uses 7-day window + heat/priority scoring; FUB uses 14-day + lastComm >12hrs"
    elif dreams_key == 'hot':
        return f"DREAMS heat={heat} (IDX activity). FUB requires Stage=Nurture + timeframe=0-3mo + lastComm >7d"
    elif dreams_key == 'warm':
        return f"DREAMS heat={heat}. FUB requires Stage=Nurture + timeframe=3-6mo + lastComm >30d"
    elif dreams_key == 'cool':
        return f"DREAMS heat={heat}. FUB requires Stage=Nurture + timeframe 6-12/12+/No Plans + lastComm >90d"
    elif dreams_key == 'unresponsive':
        return f"Low relationship ({rel}) in DREAMS. FUB requires Stage=Lead + created >14d + lastComm >14d"
    elif dreams_key == 'timeframe_empty':
        return f"FUB timeframe not set in DREAMS. FUB also requires Stage=Nurture"
    elif dreams_key == 'priority':
        return f"High priority in DREAMS. FUB requires Stage=Hot Prospect + lastComm >3d"

    return "Different methodology"


@app.route('/smart-lists')
@requires_auth
def smart_lists_page():
    """Smart Lists comparison: FUB live vs DREAMS local."""
    db = get_db()
    dreams_lists = db.get_fub_style_lists(user_id=CURRENT_USER_ID, limit=100)
    return render_template('smart_lists.html',
                           active_nav='smart-lists',
                           dreams_lists=dreams_lists,
                           smart_list_map=SMART_LIST_MAP,
                           smart_list_order=SMART_LIST_ORDER)


@app.route('/api/smart-lists/fub')
@requires_auth
def api_smart_lists_fub():
    """Fetch FUB contacts, bucket them into cadence categories, return counts + contacts."""
    client = _get_fub_client()
    if not client:
        return jsonify({'success': False, 'error': 'FUB_API_KEY not configured'}), 500

    try:
        # Fetch contacts from all relevant stages (Lead, Nurture, Hot Prospect)
        # with allFields for lastCommunication and timeframeId
        people = []
        for stage in ('Lead', 'Nurture', 'Hot Prospect'):
            batch = client.fetch_collection(
                "/people", "people",
                {"assignedUserId": CURRENT_USER_ID, "stage": stage, "fields": "allFields"},
                use_cache=False
            )
            people.extend(batch)
            logger.info(f"FUB smart lists: fetched {len(batch)} {stage} contacts")
    except Exception as e:
        logger.error(f"Failed to fetch FUB contacts: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch from FUB API'}), 502

    buckets = _bucket_fub_contacts(people)

    # Build response matching SMART_LIST_ORDER
    result = []
    for fub_name in SMART_LIST_ORDER:
        info = SMART_LIST_MAP[fub_name]
        dk = info['dreams_key']
        contacts = buckets.get(dk, [])
        result.append({
            'name': fub_name,
            'dreams_key': dk,
            'cadence': info['cadence'],
            'count': len(contacts),
            'contacts': contacts,
        })

    return jsonify({
        'success': True,
        'lists': result,
        'total_fetched': len(people),
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


@app.route('/api/smart-lists/compare/<dreams_key>')
@requires_auth
def api_smart_list_compare(dreams_key):
    """Compare a FUB bucket with the matching DREAMS list by fub_id overlap."""
    valid_keys = {v['dreams_key'] for v in SMART_LIST_MAP.values()}
    if dreams_key not in valid_keys:
        return jsonify({'success': False, 'error': 'Invalid list key'}), 400

    db = get_db()
    client = _get_fub_client()
    if not client:
        return jsonify({'success': False, 'error': 'FUB_API_KEY not configured'}), 500

    # Get DREAMS contacts for this list
    dreams_lists = db.get_fub_style_lists(user_id=CURRENT_USER_ID, limit=200)
    dreams_contacts = dreams_lists.get(dreams_key, [])

    # Get FUB contacts (re-fetch and bucket — all relevant stages)
    try:
        people = []
        for stage in ('Lead', 'Nurture', 'Hot Prospect'):
            batch = client.fetch_collection(
                "/people", "people",
                {"assignedUserId": CURRENT_USER_ID, "stage": stage, "fields": "allFields"},
                use_cache=False
            )
            people.extend(batch)
    except Exception as e:
        logger.error(f"Failed to fetch FUB people for compare: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch FUB contacts'}), 502

    buckets = _bucket_fub_contacts(people)
    fub_contacts = buckets.get(dreams_key, [])

    # Build ID sets
    dreams_by_fub_id = {}
    for c in dreams_contacts:
        fid = c.get('fub_id')
        if fid:
            dreams_by_fub_id[int(fid)] = c

    fub_by_id = {c['id']: c for c in fub_contacts if c.get('id')}

    dreams_ids = set(dreams_by_fub_id.keys())
    fub_ids = set(fub_by_id.keys())

    both_ids = dreams_ids & fub_ids
    fub_only_ids = fub_ids - dreams_ids
    dreams_only_ids = dreams_ids - fub_ids

    # Build FUB-only with reasons (look up raw contact from people list)
    fub_raw_by_id = {p.get('id'): p for p in people}
    fub_only = []
    for fid in fub_only_ids:
        c = fub_by_id[fid]
        raw = fub_raw_by_id.get(fid, {})
        reason = _explain_fub_only(raw, dreams_key, db)
        fub_only.append({
            'fub_id': fid,
            'name': c.get('name', ''),
            'phone': c.get('phone', ''),
            'stage': c.get('stage', ''),
            'reason': reason,
        })

    # Build DREAMS-only with reasons
    dreams_only = []
    for did in dreams_only_ids:
        c = dreams_by_fub_id[did]
        reason = _explain_dreams_only(c, dreams_key)
        dreams_only.append({
            'fub_id': did,
            'name': f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
            'phone': c.get('phone', ''),
            'stage': c.get('stage', ''),
            'heat_score': c.get('heat_score'),
            'priority_score': c.get('priority_score'),
            'reason': reason,
        })

    return jsonify({
        'success': True,
        'dreams_key': dreams_key,
        'counts': {
            'fub': len(fub_ids),
            'dreams': len(dreams_ids),
            'both': len(both_ids),
            'fub_only': len(fub_only_ids),
            'dreams_only': len(dreams_only_ids),
        },
        'fub_only': fub_only,
        'dreams_only': dreams_only,
    })


# ── Smart List Export: CSV + Google Sheets ─────────────────────────────

# dreams_key -> display name for filenames/tab names
_SMART_LIST_NAMES = {v['dreams_key']: k for k, v in SMART_LIST_MAP.items()}


@app.route('/api/smart-lists/<dreams_key>/csv')
@requires_auth
def api_smart_list_csv(dreams_key):
    """Download DREAMS contacts for a smart list as CSV."""
    valid_keys = {v['dreams_key'] for v in SMART_LIST_MAP.values()}
    if dreams_key not in valid_keys:
        return jsonify({'success': False, 'error': 'Invalid list key'}), 400

    db = get_db()
    dreams_lists = db.get_fub_style_lists(user_id=CURRENT_USER_ID, limit=500)
    contacts = dreams_lists.get(dreams_key, [])

    import io, csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['First Name', 'Last Name', 'ID', 'Email', 'Phone'])
    for c in contacts:
        writer.writerow([
            c.get('first_name', ''),
            c.get('last_name', ''),
            c.get('fub_id', c.get('id', '')),
            c.get('email', ''),
            c.get('phone', ''),
        ])

    list_name = _SMART_LIST_NAMES.get(dreams_key, dreams_key).replace(' ', '')
    date_prefix = datetime.now().strftime('%y%m%d')
    filename = f"{date_prefix}.DREAMS.{list_name}.csv"

    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@app.route('/api/smart-lists/<dreams_key>/sheets', methods=['POST'])
@requires_auth
def api_smart_list_sheets(dreams_key):
    """Push a smart list to a Google Sheets tab. Handles both FUB and DREAMS sources."""
    valid_keys = {v['dreams_key'] for v in SMART_LIST_MAP.values()}
    if dreams_key not in valid_keys:
        return jsonify({'success': False, 'error': 'Invalid list key'}), 400

    data = request.get_json(silent=True) or {}
    source = data.get('source', 'dreams')
    if source not in ('fub', 'dreams'):
        return jsonify({'success': False, 'error': 'source must be fub or dreams'}), 400

    # Build rows
    rows = []
    if source == 'dreams':
        db = get_db()
        dreams_lists = db.get_fub_style_lists(user_id=CURRENT_USER_ID, limit=500)
        contacts = dreams_lists.get(dreams_key, [])
        for c in contacts:
            rows.append([
                c.get('first_name', ''),
                c.get('last_name', ''),
                str(c.get('fub_id', c.get('id', ''))),
                c.get('email', ''),
                c.get('phone', ''),
            ])
    else:
        # FUB source: contacts sent from the client
        contacts = data.get('contacts', [])
        for c in contacts:
            rows.append([
                c.get('first_name', ''),
                c.get('last_name', ''),
                str(c.get('id', '')),
                c.get('email', ''),
                c.get('phone', ''),
            ])

    list_name = _SMART_LIST_NAMES.get(dreams_key, dreams_key)
    tab_name = f"{source.upper()}: {list_name}"

    # Google Sheets auth (reuse service account from fub-to-sheets)
    sheet_id = os.getenv('GOOGLE_SHEET_ID')
    sa_path = PROJECT_ROOT / 'service_account.json'
    if not sheet_id or not sa_path.exists():
        return jsonify({'success': False, 'error': 'Google Sheets not configured'}), 500

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds = Credentials.from_service_account_file(
            str(sa_path),
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive',
            ]
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)

        # Get or create worksheet
        try:
            ws = sh.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=tab_name, rows=max(len(rows) + 10, 100), cols=10)

        # Clear and write
        ws.clear()
        header = ['First Name', 'Last Name', 'ID', 'Email', 'Phone']
        all_data = [header] + rows
        if all_data:
            ws.update(all_data, value_input_option='USER_ENTERED')

        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        return jsonify({
            'success': True,
            'tab_name': tab_name,
            'row_count': len(rows),
            'sheet_url': sheet_url,
        })

    except Exception as e:
        logger.error(f"Sheets export failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to write to Google Sheets'}), 500


if __name__ == '__main__':
    is_debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=5001, debug=is_debug)
