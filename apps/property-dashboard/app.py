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
from dotenv import load_dotenv

# Module logger
logger = logging.getLogger(__name__)

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
load_dotenv(PROJECT_ROOT / '.env')

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


@app.route('/properties/<property_id>')
@requires_auth
def property_detail(property_id):
    """Property detail page with price history chart."""
    with db._get_connection() as conn:
        # Get property details
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
                   cp.status, cp.notes, cp.is_favorited, cp.created_at
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

    # Get filter parameters
    min_heat = request.args.get('min_heat', 0, type=float)
    min_value = request.args.get('min_value', 0, type=float)
    stage = request.args.get('stage', '')
    sort_by = request.args.get('sort', 'priority')  # priority, heat, value, name
    filter_type = request.args.get('filter', '')  # hot_leads, high_value, active_week
    active_tab = request.args.get('tab', 'contacts')  # contacts, queue, analysis, insights, trends

    # Get all contacts (no artificial limit - let the database handle it)
    all_contacts = db.get_contacts_by_priority(min_priority=0, limit=2000)

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

    # Get aggregate stats
    stats = db.get_contact_stats()

    return render_template('contacts.html',
                         contacts=contacts,
                         all_contacts=all_contacts,
                         stats=stats,
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
