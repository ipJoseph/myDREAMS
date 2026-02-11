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
    from intelligence import generate_briefings, group_by_urgency, generate_overnight_narrative
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


def get_filter_options() -> Dict[str, List[str]]:
    """Get distinct values for filter dropdowns - efficient single query approach"""
    with db._get_connection() as conn:
        options = {}
        # Use properties_v2 view (backed by normalized parcels + listings tables)
        # Falls back to properties table if view doesn't exist
        table = 'properties_v2'
        try:
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        except:
            table = 'properties'

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
        return options


def count_properties(added_for: Optional[str] = None, status: Optional[str] = None,
                     city: Optional[str] = None, county: Optional[str] = None) -> int:
    """Count properties matching filters (for pagination)"""
    with db._get_connection() as conn:
        # Use properties_v2 view (backed by normalized schema)
        table = 'properties_v2'
        try:
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        except:
            table = 'properties'

        query = f'SELECT COUNT(*) FROM {table} WHERE 1=1'
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

        return conn.execute(query, params).fetchone()[0]


def fetch_properties(added_for: Optional[str] = None, status: Optional[str] = None,
                      city: Optional[str] = None, county: Optional[str] = None,
                      sort_by: str = 'price', sort_order: str = 'desc',
                      limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
    """Fetch properties from SQLite with optional filters, sorting, and pagination"""
    # Whitelist of allowed sort columns (prevents SQL injection)
    ALLOWED_SORTS = {
        'price': 'price', 'address': 'address', 'city': 'city', 'county': 'county',
        'beds': 'beds', 'baths': 'baths', 'sqft': 'sqft', 'acreage': 'acreage',
        'status': 'status', 'dom': 'days_on_market', 'year_built': 'year_built',
        'created_at': 'created_at', 'mls_number': 'mls_number'
    }
    sort_column = ALLOWED_SORTS.get(sort_by, 'price')
    sort_dir = 'ASC' if sort_order == 'asc' else 'DESC'

    with db._get_connection() as conn:
        # Use properties_v2 view (backed by normalized schema)
        table = 'properties_v2'
        try:
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        except:
            table = 'properties'

        query = f'SELECT * FROM {table} WHERE 1=1'
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

            # Live activity feed (for Command Center)
            live_feed = db.get_live_activity_feed(hours=8, limit=20)

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
                                 current_user_id=CURRENT_USER_ID,
                                 refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))
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
                             refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))

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
                         refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


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
                         refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


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
    city = request.args.get('city', '')
    county = request.args.get('county', '')
    show_all = request.args.get('show_all', '')

    # Pagination (100 per page for fast rendering)
    page = max(1, int(request.args.get('page', 1)))
    per_page = 100

    # Sort parameters (server-side sorting for performance)
    sort_by = request.args.get('sort', 'price')
    sort_order = request.args.get('order', 'desc')

    # Default to Active status for nimble loading (unless show_all or other filter set)
    if not status and not show_all and not added_for:
        status = 'Active'

    # Get dropdown options efficiently (uses indexed DISTINCT queries)
    filter_options = get_filter_options()
    clients = filter_options['clients']
    cities = filter_options['cities']
    counties = filter_options['counties']
    statuses = filter_options['statuses']

    # Get total count for pagination
    total_count = count_properties(
        added_for=added_for if added_for else None,
        status=status if status else None,
        city=city if city else None,
        county=county if county else None
    )
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    # Fetch filtered, sorted, paginated properties
    properties = fetch_properties(
        added_for=added_for if added_for else None,
        status=status if status else None,
        city=city if city else None,
        county=county if county else None,
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
                         refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


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
        # Use properties_v2 view (backed by normalized schema)
        table = 'properties_v2'
        try:
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        except:
            table = 'properties'

        query = f'''
            SELECT id, address, city, county, state, zip, price, beds, baths, sqft, acreage,
                   status, latitude, longitude, photo_urls,
                   flood_zone, flood_factor, elevation_feet, view_potential,
                   wildfire_risk, wildfire_score, slope_percent, aspect
            FROM {table}
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
            query += ' AND price >= ?'
            params.append(int(min_price))

        if max_price:
            query += ' AND price <= ?'
            params.append(int(max_price))

        query += ' ORDER BY price DESC LIMIT 500'

        rows = conn.execute(query, params).fetchall()

        properties = []
        for row in rows:
            prop = dict(row)

            # Parse first photo URL
            if prop.get('photo_urls'):
                try:
                    photos = json.loads(prop['photo_urls'])
                    prop['primary_photo'] = photos[0] if photos else None
                except (json.JSONDecodeError, IndexError):
                    prop['primary_photo'] = None
            else:
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


@app.route('/properties/<property_id>')
@requires_auth
def property_detail(property_id):
    """Property detail page with price history chart."""
    with db._get_connection() as conn:
        # Try properties_v2 view first (covers listings table with lst_* IDs),
        # then fall back to legacy properties table (UUID IDs)
        prop = None
        try:
            prop = conn.execute('''
                SELECT p.*,
                       (SELECT COUNT(*) FROM property_changes WHERE property_id = p.id) as change_count
                FROM properties_v2 p
                WHERE p.id = ?
            ''', [property_id]).fetchone()
        except Exception:
            pass

        if not prop:
            prop = conn.execute('''
                SELECT p.*,
                       (SELECT COUNT(*) FROM property_changes WHERE property_id = p.id) as change_count
                FROM properties p
                WHERE p.id = ?
            ''', [property_id]).fetchone()

        if not prop:
            return "Property not found", 404

        prop_dict = dict(prop)

        # Parse photo URLs
        if prop_dict.get('photo_urls'):
            try:
                prop_dict['photos'] = json.loads(prop_dict['photo_urls'])
            except json.JSONDecodeError:
                prop_dict['photos'] = []
        else:
            prop_dict['photos'] = []

        # Get price history
        price_history = db.get_property_price_history(property_id)

        # Get recent changes
        changes = conn.execute('''
            SELECT change_type, old_value, new_value, change_amount, detected_at
            FROM property_changes
            WHERE property_id = ?
            ORDER BY detected_at DESC
            LIMIT 10
        ''', [property_id]).fetchall()

        # Get contacts interested in this property
        interested = conn.execute('''
            SELECT l.id, l.first_name, l.last_name, l.email,
                   cp.relationship, cp.notes, cp.created_at
            FROM contact_properties cp
            JOIN leads l ON l.id = cp.contact_id
            WHERE cp.property_id = ?
            ORDER BY cp.created_at DESC
        ''', [property_id]).fetchall()

        return render_template('property_detail.html',
                             property=prop_dict,
                             price_history=price_history,
                             changes=[dict(c) for c in changes],
                             interested_contacts=[dict(i) for i in interested])


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
                         refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


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

    # Get packages for this contact
    packages = []
    try:
        with db._get_connection() as conn:
            packages = conn.execute('''
                SELECT p.*, COUNT(pp.id) as property_count
                FROM property_packages p
                LEFT JOIN package_properties pp ON p.id = pp.package_id
                WHERE p.lead_id = ?
                GROUP BY p.id
                ORDER BY p.created_at DESC
            ''', (contact_id,)).fetchall()
            packages = [dict(row) for row in packages]
    except Exception as e:
        logger.warning(f"Error fetching packages: {e}")

    # Get showings for this contact
    showings = []
    try:
        with db._get_connection() as conn:
            showings = conn.execute('''
                SELECT s.*, COUNT(sp.id) as property_count
                FROM showings s
                LEFT JOIN showing_properties sp ON s.id = sp.showing_id
                WHERE s.lead_id = ?
                GROUP BY s.id
                ORDER BY s.scheduled_date DESC
            ''', (contact_id,)).fetchall()
            showings = [dict(row) for row in showings]
    except Exception as e:
        logger.warning(f"Error fetching showings: {e}")

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
        refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


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

    # Query redfin_imports database
    properties = []
    try:
        props_db = get_properties_db()

        query = 'SELECT * FROM properties WHERE (status = "active" OR status = "Active")'
        params = []

        # Apply search criteria
        if search_criteria.get('min_price'):
            query += ' AND price >= ?'
            params.append(int(search_criteria['min_price']))
        if search_criteria.get('max_price'):
            query += ' AND price <= ?'
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

        query += ' ORDER BY days_on_market ASC, price ASC LIMIT 100'

        logger.info(f"Property search query: {query}")
        logger.info(f"Property search params: {params}")

        rows = props_db.execute(query, params).fetchall()
        properties = [dict(row) for row in rows]
        props_db.close()

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

            # Add properties to package
            for i, prop_id in enumerate(property_ids):
                pp_id = str(uuid.uuid4())
                conn.execute('''
                    INSERT INTO package_properties (id, package_id, property_id, display_order, added_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (pp_id, package_id, prop_id, i + 1, datetime.now().isoformat()))

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

            # Get package properties metadata
            pkg_props = conn.execute('''
                SELECT property_id, display_order, agent_notes as package_notes,
                       client_favorited, client_rating, showing_requested
                FROM package_properties
                WHERE package_id = ?
                ORDER BY display_order
            ''', (package_id,)).fetchall()

        # Fetch property details from redfin_imports
        if pkg_props:
            props_db = get_properties_db()
            prop_ids = [p['property_id'] for p in pkg_props]
            placeholders = ','.join(['?' for _ in prop_ids])
            props_data = props_db.execute(f'SELECT * FROM properties WHERE id IN ({placeholders})', prop_ids).fetchall()
            props_dict = {p['id']: dict(p) for p in props_data}
            props_db.close()

            # Merge property data with package metadata
            for pp in pkg_props:
                prop = props_dict.get(pp['property_id'])
                if prop:
                    prop.update({
                        'display_order': pp['display_order'],
                        'package_notes': pp['package_notes'],
                        'client_favorited': pp['client_favorited'],
                        'client_rating': pp['client_rating'],
                        'showing_requested': pp['showing_requested'],
                    })
                    properties.append(prop)

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

    try:
        with db._get_connection() as conn:
            # Get current max order
            max_order = conn.execute(
                'SELECT MAX(display_order) FROM package_properties WHERE package_id = ?',
                (package_id,)
            ).fetchone()[0] or 0

            for i, prop_id in enumerate(property_ids):
                # Check if already in package
                existing = conn.execute(
                    'SELECT id FROM package_properties WHERE package_id = ? AND property_id = ?',
                    (package_id, prop_id)
                ).fetchone()

                if not existing:
                    pp_id = str(uuid.uuid4())
                    conn.execute('''
                        INSERT INTO package_properties (id, package_id, property_id, display_order, added_at)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (pp_id, package_id, prop_id, max_order + i + 1, datetime.now().isoformat()))

            # Update package timestamp
            conn.execute('UPDATE property_packages SET updated_at = ? WHERE id = ?',
                        (datetime.now().isoformat(), package_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Error adding properties to package: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    return redirect(url_for('contact_package_detail', contact_id=contact_id, package_id=package_id))


@app.route('/contacts/<contact_id>/packages/<package_id>/remove/<property_id>', methods=['POST'])
@requires_auth
def contact_package_remove_property(contact_id, package_id, property_id):
    """Remove a property from a package."""
    db = get_db()

    try:
        with db._get_connection() as conn:
            conn.execute(
                'DELETE FROM package_properties WHERE package_id = ? AND property_id = ?',
                (package_id, property_id)
            )
            conn.execute('UPDATE property_packages SET updated_at = ? WHERE id = ?',
                        (datetime.now().isoformat(), package_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Error removing property from package: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': True})


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
        # Build query
        query = '''
            SELECT
                pc.id,
                pc.property_id,
                pc.property_address,
                pc.change_type,
                pc.old_value,
                pc.new_value,
                pc.change_amount,
                pc.detected_at,
                pc.source,
                pc.notified,
                p.city,
                p.county,
                p.beds,
                p.baths,
                p.sqft,
                p.price as current_price,
                p.status as current_status,
                p.redfin_url
            FROM property_changes pc
            LEFT JOIN properties p ON pc.property_id = p.id
            WHERE pc.detected_at >= ?
        '''
        params = [cutoff]

        if change_type:
            query += ' AND pc.change_type = ?'
            params.append(change_type)

        if county:
            query += ' AND p.county = ?'
            params.append(county)

        query += ' ORDER BY pc.detected_at DESC LIMIT 200'

        changes = [dict(row) for row in conn.execute(query, params).fetchall()]

        # Process changes for display
        for change in changes:
            # Calculate percentage for price changes
            if change['change_type'] == 'price_change' and change['old_value'] and change['new_value']:
                try:
                    old_price = int(change['old_value'])
                    new_price = int(change['new_value'])
                    if old_price > 0:
                        change['change_pct'] = round((new_price - old_price) / old_price * 100, 1)
                    else:
                        change['change_pct'] = 0
                except (ValueError, TypeError):
                    change['change_pct'] = 0
            else:
                change['change_pct'] = 0

        # Get summary counts
        summary_query = '''
            SELECT change_type, COUNT(*) as count
            FROM property_changes
            WHERE detected_at >= ?
            GROUP BY change_type
        '''
        summary = {row['change_type']: row['count'] for row in conn.execute(summary_query, [cutoff]).fetchall()}

        # Get counties for filter dropdown
        counties = [row['county'] for row in conn.execute('''
            SELECT DISTINCT p.county
            FROM property_changes pc
            JOIN properties p ON pc.property_id = p.id
            WHERE pc.detected_at >= ?
            AND p.county IS NOT NULL
            ORDER BY p.county
        ''', [cutoff]).fetchall()]

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
                           refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


# ==========================================
# Admin Settings Routes
# ==========================================

@app.route('/admin/settings')
@requires_auth
def admin_settings():
    """Admin settings page for configuring alert thresholds and automation."""
    db = get_db()

    # Get all settings grouped by category
    all_settings = db.get_all_settings()

    # Group settings by category
    settings_by_category = {}
    for setting in all_settings:
        category = setting['category']
        if category not in settings_by_category:
            settings_by_category[category] = []
        settings_by_category[category].append(setting)

    return render_template('admin_settings.html',
                           settings_by_category=settings_by_category,
                           all_settings=all_settings)


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
                p.elevation_feet, p.slope_percent, p.aspect, p.flood_zone,
                p.flood_factor, p.view_potential, p.wildfire_risk, p.wildfire_score,
                p.latitude, p.longitude, p.assessed_value
            FROM listings l
            LEFT JOIN parcels p ON l.parcel_id = p.id
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
            SELECT
                l.*,
                p.address, p.city, p.county, p.state, p.zip,
                p.latitude, p.longitude, p.acreage, p.apn,
                p.owner_name, p.owner_phone, p.assessed_value
            FROM listings l
            JOIN parcels p ON l.parcel_id = p.id
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

    # Parcels stats
    parcels_stats = db_conn.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN latitude IS NOT NULL AND latitude != 0 THEN 1 END) as has_coords,
            COUNT(CASE WHEN flood_zone IS NOT NULL AND flood_zone != '' THEN 1 END) as has_flood,
            COUNT(CASE WHEN elevation_feet IS NOT NULL THEN 1 END) as has_elevation,
            COUNT(CASE WHEN spatial_enriched_at IS NOT NULL THEN 1 END) as spatially_enriched,
            MAX(spatial_enriched_at) as last_spatial_enrichment
        FROM parcels
    """).fetchone()

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
                          refresh_time=datetime.now().strftime('%B %d, %Y %I:%M %p'))


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
            (SELECT COUNT(*) FROM listings WHERE latitude IS NOT NULL AND latitude != 0) as listings_with_coords,
            (SELECT COUNT(*) FROM parcels) as total_parcels,
            (SELECT COUNT(*) FROM parcels WHERE spatial_enriched_at IS NOT NULL) as parcels_enriched
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
        'parcels': {
            'total': stats['total_parcels'],
            'spatially_enriched': stats['parcels_enriched'],
            'enrichment_pct': round(stats['parcels_enriched'] / stats['total_parcels'] * 100, 1) if stats['total_parcels'] else 0,
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

# Canonical FUB smart list names → DREAMS list keys + cadence labels
SMART_LIST_MAP = {
    'New Leads':        {'dreams_key': 'new_leads',        'cadence': 'Daily'},
    'Priority':         {'dreams_key': 'priority',         'cadence': 'Semiweekly'},
    'Hot':              {'dreams_key': 'hot',              'cadence': 'Weekly'},
    'Warm':             {'dreams_key': 'warm',             'cadence': 'Monthly'},
    'Cool':             {'dreams_key': 'cool',             'cadence': 'Quarterly'},
    'Unresponsive':     {'dreams_key': 'unresponsive',     'cadence': 'Biweekly'},
    'Timeframe Empty':  {'dreams_key': 'timeframe_empty',  'cadence': 'As needed'},
}

# Ordered list for display
SMART_LIST_ORDER = ['New Leads', 'Priority', 'Hot', 'Warm', 'Cool', 'Unresponsive', 'Timeframe Empty']


def _explain_fub_only(contact, dreams_key, dreams_db):
    """Explain why a FUB contact is NOT on the matching DREAMS list."""
    fub_id = contact.get('id')
    if not fub_id:
        return "No FUB ID"

    # Look up in DREAMS DB
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
            return f"Created {days_ago} days ago (threshold: 7 days)"
    elif dreams_key == 'hot':
        return f"Heat score is {heat} (threshold: 70)"
    elif dreams_key == 'warm':
        if heat >= 70:
            return f"Heat score {heat} puts them in Hot instead"
        return f"Heat score is {heat} (range: 40-69)"
    elif dreams_key == 'cool':
        if heat >= 40:
            return f"Heat score {heat} puts them in a higher tier"
        return f"Heat score is {heat} (range: 10-39)"
    elif dreams_key == 'unresponsive':
        if rel >= 15:
            return f"Relationship score is {rel} (threshold: <15)"
        if heat <= 5:
            return f"Heat score is {heat} (needs >5)"
    elif dreams_key == 'timeframe_empty':
        return f"May have intake form or heat {heat} < 30"
    elif dreams_key == 'priority':
        return f"Priority score {lead.get('priority_score', 0)} — not in top tier"

    return "Criteria mismatch"


def _explain_dreams_only(contact, dreams_key):
    """Explain why a DREAMS contact is NOT on the matching FUB smart list."""
    heat = contact.get('heat_score') or 0
    rel = contact.get('relationship_score') or 0
    stage = contact.get('stage', '')

    if dreams_key == 'new_leads':
        return f"In DREAMS as new lead — may have aged out of FUB's window or FUB stage differs"
    elif dreams_key == 'hot':
        return f"DREAMS heat={heat} qualifies as Hot — FUB uses different activity rules"
    elif dreams_key == 'warm':
        return f"DREAMS heat={heat} qualifies as Warm — FUB criteria differ"
    elif dreams_key == 'cool':
        return f"DREAMS heat={heat} qualifies as Cool — FUB criteria differ"
    elif dreams_key == 'unresponsive':
        return f"Low relationship ({rel}) in DREAMS — FUB may use last-comm date instead"
    elif dreams_key == 'timeframe_empty':
        return f"No intake form in DREAMS — FUB may not track this"
    elif dreams_key == 'priority':
        return f"High priority in DREAMS — FUB's Priority list uses different rules"

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
    """Fetch FUB smart lists (names + counts) on demand."""
    client = _get_fub_client()
    if not client:
        return jsonify({'success': False, 'error': 'FUB_API_KEY not configured'}), 500

    try:
        raw_lists = client.fetch_smart_lists()
    except Exception as e:
        logger.error(f"Failed to fetch FUB smart lists: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch from FUB API'}), 502

    # Filter to only the lists we care about and normalize
    result = []
    for sl in raw_lists:
        name = sl.get('name', '')
        if name in SMART_LIST_MAP:
            result.append({
                'id': sl.get('id'),
                'name': name,
                'count': sl.get('count', 0),
                'cadence': SMART_LIST_MAP[name]['cadence'],
                'dreams_key': SMART_LIST_MAP[name]['dreams_key'],
            })

    # Sort by our canonical order
    order_idx = {n: i for i, n in enumerate(SMART_LIST_ORDER)}
    result.sort(key=lambda x: order_idx.get(x['name'], 99))

    return jsonify({
        'success': True,
        'lists': result,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


@app.route('/api/smart-lists/fub/<int:list_id>/people')
@requires_auth
def api_smart_list_people(list_id):
    """Fetch contacts for a specific FUB smart list."""
    client = _get_fub_client()
    if not client:
        return jsonify({'success': False, 'error': 'FUB_API_KEY not configured'}), 500

    try:
        people = client.fetch_smart_list_people(list_id)
    except Exception as e:
        logger.error(f"Failed to fetch FUB smart list people for {list_id}: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch from FUB API'}), 502

    contacts = []
    for p in people:
        phones = p.get('phones', [])
        phone = phones[0].get('value', '') if phones else ''
        emails = p.get('emails', [])
        email = emails[0].get('value', '') if emails else ''
        contacts.append({
            'id': p.get('id'),
            'first_name': p.get('firstName', ''),
            'last_name': p.get('lastName', ''),
            'name': f"{p.get('firstName', '')} {p.get('lastName', '')}".strip(),
            'phone': phone,
            'email': email,
            'stage': p.get('stage', ''),
            'lastActivity': p.get('lastActivity', ''),
        })

    return jsonify({
        'success': True,
        'contacts': contacts,
        'count': len(contacts),
    })


@app.route('/api/smart-lists/compare/<dreams_key>')
@requires_auth
def api_smart_list_compare(dreams_key):
    """Compare a FUB smart list with the matching DREAMS list."""
    # Validate dreams_key
    valid_keys = {v['dreams_key'] for v in SMART_LIST_MAP.values()}
    if dreams_key not in valid_keys:
        return jsonify({'success': False, 'error': 'Invalid list key'}), 400

    fub_list_id = request.args.get('fub_list_id', type=int)
    if not fub_list_id:
        return jsonify({'success': False, 'error': 'fub_list_id required'}), 400

    db = get_db()
    client = _get_fub_client()
    if not client:
        return jsonify({'success': False, 'error': 'FUB_API_KEY not configured'}), 500

    # Get DREAMS contacts for this list
    dreams_lists = db.get_fub_style_lists(user_id=CURRENT_USER_ID, limit=200)
    dreams_contacts = dreams_lists.get(dreams_key, [])

    # Get FUB contacts for this list
    try:
        fub_people = client.fetch_smart_list_people(fub_list_id)
    except Exception as e:
        logger.error(f"Failed to fetch FUB people for compare: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch FUB contacts'}), 502

    # Build FUB ID sets
    dreams_by_fub_id = {}
    for c in dreams_contacts:
        fid = c.get('fub_id')
        if fid:
            dreams_by_fub_id[int(fid)] = c

    fub_by_id = {}
    for p in fub_people:
        pid = p.get('id')
        if pid:
            fub_by_id[int(pid)] = p

    dreams_ids = set(dreams_by_fub_id.keys())
    fub_ids = set(fub_by_id.keys())

    both_ids = dreams_ids & fub_ids
    fub_only_ids = fub_ids - dreams_ids
    dreams_only_ids = dreams_ids - fub_ids

    # Build FUB-only with reasons
    fub_only = []
    for fid in fub_only_ids:
        p = fub_by_id[fid]
        phones = p.get('phones', [])
        phone = phones[0].get('value', '') if phones else ''
        reason = _explain_fub_only(p, dreams_key, db)
        fub_only.append({
            'fub_id': fid,
            'name': f"{p.get('firstName', '')} {p.get('lastName', '')}".strip(),
            'phone': phone,
            'stage': p.get('stage', ''),
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


if __name__ == '__main__':
    is_debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=5001, debug=is_debug)
