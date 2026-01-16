#!/usr/bin/env python3
"""
DREAMS Property Dashboard
A web-based summary view of properties from Notion
"""

import os
import sys
import subprocess
import statistics
from datetime import datetime
from flask import Flask, render_template, request, jsonify
import httpx

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

app = Flask(__name__)

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


def extract_property(prop):
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
            # Remove ' County' suffix (case insensitive)
            import re
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
    }


def fetch_properties(added_for=None, status=None, city=None, county=None):
    """Fetch properties from Notion with optional filters"""
    filters = []

    if added_for:
        filters.append({
            'property': 'Added For',
            'rich_text': {'contains': added_for}
        })

    if status:
        filters.append({
            'property': 'Status',
            'select': {'equals': status}
        })

    if city:
        filters.append({
            'property': 'City',
            'select': {'equals': city}
        })

    if county:
        filters.append({
            'property': 'County',
            'rich_text': {'contains': county}
        })

    query_params = {}
    if filters:
        if len(filters) == 1:
            query_params['filter'] = filters[0]
        else:
            query_params['filter'] = {'and': filters}

    # Fetch all pages (handle pagination)
    all_results = []
    has_more = True
    next_cursor = None

    while has_more:
        if next_cursor:
            query_params['start_cursor'] = next_cursor

        url = f'https://api.notion.com/v1/databases/{DATABASE_ID}/query'
        resp = httpx.post(url, headers=NOTION_HEADERS, json=query_params, timeout=30)
        resp.raise_for_status()
        response = resp.json()

        all_results.extend(response['results'])
        has_more = response.get('has_more', False)
        next_cursor = response.get('next_cursor')

    # Extract property data
    properties = []
    for page in all_results:
        if page.get('archived', False) or page.get('in_trash', False):
            continue
        properties.append(extract_property(page))

    return properties


def calculate_metrics(properties):
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


def get_unique_clients(properties):
    """Get unique client names from properties"""
    clients = set()
    for p in properties:
        if p.get('added_for'):
            clients.add(p['added_for'])
    return sorted(list(clients))


def get_unique_cities(properties):
    """Get unique city names from properties"""
    cities = set()
    for p in properties:
        if p.get('city'):
            cities.add(p['city'])
    return sorted(list(cities))


def get_unique_counties(properties):
    """Get unique county names from properties"""
    counties = set()
    for p in properties:
        if p.get('county'):
            counties.add(p['county'])
    return sorted(list(counties))


def get_unique_statuses(properties):
    """Get unique status values from properties"""
    statuses = set()
    for p in properties:
        if p.get('status'):
            statuses.add(p['status'])
    return sorted(list(statuses))


@app.route('/')
def dashboard():
    """Main dashboard view"""
    # Get filter parameters
    added_for = request.args.get('client', '')
    status = request.args.get('status', '')
    city = request.args.get('city', '')
    county = request.args.get('county', '')

    # Fetch all properties first to get dropdown options
    all_properties = fetch_properties()
    clients = get_unique_clients(all_properties)
    cities = get_unique_cities(all_properties)
    counties = get_unique_counties(all_properties)
    statuses = get_unique_statuses(all_properties)

    # Apply filters
    properties = fetch_properties(
        added_for=added_for if added_for else None,
        status=status if status else None,
        city=city if city else None,
        county=county if county else None
    )

    # Calculate metrics
    metrics = calculate_metrics(properties)

    # Count by status
    status_counts = {}
    for p in properties:
        s = p.get('status') or 'Unknown'
        status_counts[s] = status_counts.get(s, 0) + 1
    metrics['status_counts'] = status_counts

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


@app.route('/api/properties')
def api_properties():
    """API endpoint for properties data"""
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


@app.route('/api/idx-portfolio', methods=['POST'])
def create_idx_portfolio():
    """Launch IDX portfolio automation with selected MLS numbers"""
    data = request.get_json()
    mls_numbers = data.get('mls_numbers', [])

    if not mls_numbers:
        return jsonify({'success': False, 'error': 'No MLS numbers provided'}), 400

    # Path to the launch script
    launch_script = os.path.join(os.path.dirname(__file__), 'launch_idx.sh')
    mls_string = ','.join(mls_numbers)

    try:
        # Use shell script to properly detach the process
        result = subprocess.run(
            [launch_script, mls_string],
            capture_output=True,
            text=True,
            timeout=5
        )

        pid = result.stdout.strip()

        return jsonify({
            'success': True,
            'message': f'Opening IDX portfolio with {len(mls_numbers)} properties',
            'mls_count': len(mls_numbers),
            'pid': pid
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
