#!/usr/bin/env python3
"""
Redfin Property Query Form

Web interface for querying imported Redfin properties.
Comprehensive filters with easy-to-use dropdowns.

Usage:
    python redfin_query_app.py
    # Opens at http://localhost:5002
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response
import csv
import io

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = os.getenv('REDFIN_DB_PATH', str(PROJECT_ROOT / 'data' / 'redfin_imports.db'))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'redfin-query-dev-key')


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_distinct_values(column: str) -> list:
    """Get distinct non-null values for a column."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT DISTINCT {column}
        FROM properties
        WHERE {column} IS NOT NULL AND {column} != ''
        ORDER BY {column}
    """)
    values = [row[0] for row in cursor.fetchall()]
    conn.close()
    return values


def get_filter_options():
    """Get all dropdown options from database."""
    return {
        'counties': get_distinct_values('county'),
        'cities': get_distinct_values('city'),
        'property_types': get_distinct_values('property_type'),
        'statuses': get_distinct_values('status'),
        'mls_sources': get_distinct_values('mls_source'),
        # View types - these would come from property features/description parsing
        'view_types': ['Mountain', 'Water', 'Woods', 'Pasture', 'Long Range', 'Lake', 'River', 'Creek'],
        # Property styles
        'style_types': ['Cabin', 'Craftsman', 'Bungalow', 'Ranch', 'Colonial', 'Contemporary', 'Log', 'A-Frame', 'Farmhouse'],
    }


def build_query(filters: dict) -> tuple:
    """Build SQL query from filters. Returns (query, params)."""
    query = "SELECT * FROM properties WHERE 1=1"
    params = []

    # County filter (multi-select)
    if filters.get('counties'):
        placeholders = ','.join(['?' for _ in filters['counties']])
        query += f" AND county IN ({placeholders})"
        params.extend(filters['counties'])

    # City filter (multi-select)
    if filters.get('cities'):
        placeholders = ','.join(['?' for _ in filters['cities']])
        query += f" AND city IN ({placeholders})"
        params.extend(filters['cities'])

    # Status filter
    if filters.get('status'):
        query += " AND status = ?"
        params.append(filters['status'])

    # Bedrooms
    if filters.get('min_beds'):
        query += " AND beds >= ?"
        params.append(int(filters['min_beds']))
    if filters.get('max_beds'):
        query += " AND beds <= ?"
        params.append(int(filters['max_beds']))

    # Bathrooms
    if filters.get('min_baths'):
        query += " AND baths >= ?"
        params.append(float(filters['min_baths']))
    if filters.get('max_baths'):
        query += " AND baths <= ?"
        params.append(float(filters['max_baths']))

    # Price
    if filters.get('min_price'):
        query += " AND price >= ?"
        params.append(int(filters['min_price']))
    if filters.get('max_price'):
        query += " AND price <= ?"
        params.append(int(filters['max_price']))

    # Lot size (acreage)
    if filters.get('min_lot'):
        query += " AND acreage >= ?"
        params.append(float(filters['min_lot']))
    if filters.get('max_lot'):
        query += " AND acreage <= ?"
        params.append(float(filters['max_lot']))

    # Square footage
    if filters.get('min_sqft'):
        query += " AND sqft >= ?"
        params.append(int(filters['min_sqft']))
    if filters.get('max_sqft'):
        query += " AND sqft <= ?"
        params.append(int(filters['max_sqft']))

    # Property type (multi-select)
    if filters.get('property_types'):
        placeholders = ','.join(['?' for _ in filters['property_types']])
        query += f" AND property_type IN ({placeholders})"
        params.extend(filters['property_types'])

    # Year built
    if filters.get('min_year'):
        query += " AND year_built >= ?"
        params.append(int(filters['min_year']))
    if filters.get('max_year'):
        query += " AND year_built <= ?"
        params.append(int(filters['max_year']))

    # Days on market
    if filters.get('max_dom'):
        query += " AND days_on_market <= ?"
        params.append(int(filters['max_dom']))

    # Order by
    order_by = filters.get('order_by', 'price')
    order_dir = filters.get('order_dir', 'ASC')
    if order_by in ['price', 'beds', 'baths', 'sqft', 'acreage', 'days_on_market', 'created_at']:
        query += f" ORDER BY {order_by} {order_dir}"

    # Limit
    limit = min(int(filters.get('limit', 100)), 500)
    query += f" LIMIT {limit}"

    return query, params


def execute_query(filters: dict) -> list:
    """Execute query and return results."""
    query, params = build_query(filters)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


@app.route('/')
def index():
    """Main query form page."""
    options = get_filter_options()

    # Get some stats
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM properties")
    total_properties = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT county) FROM properties WHERE county IS NOT NULL")
    total_counties = cursor.fetchone()[0]
    conn.close()

    return render_template('query_form.html',
                         options=options,
                         total_properties=total_properties,
                         total_counties=total_counties)


@app.route('/api/cities')
def get_cities_for_county():
    """Get cities for selected county(s) - for cascading dropdown."""
    counties = request.args.getlist('county')
    if not counties:
        return jsonify([])

    conn = get_db()
    cursor = conn.cursor()
    placeholders = ','.join(['?' for _ in counties])
    cursor.execute(f"""
        SELECT DISTINCT city
        FROM properties
        WHERE county IN ({placeholders}) AND city IS NOT NULL AND city != ''
        ORDER BY city
    """, counties)
    cities = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify(cities)


@app.route('/search', methods=['POST'])
def search():
    """Execute search and return results."""
    filters = {
        'counties': request.form.getlist('counties'),
        'cities': request.form.getlist('cities'),
        'status': request.form.get('status'),
        'min_beds': request.form.get('min_beds'),
        'max_beds': request.form.get('max_beds'),
        'min_baths': request.form.get('min_baths'),
        'max_baths': request.form.get('max_baths'),
        'min_price': request.form.get('min_price'),
        'max_price': request.form.get('max_price'),
        'min_lot': request.form.get('min_lot'),
        'max_lot': request.form.get('max_lot'),
        'min_sqft': request.form.get('min_sqft'),
        'max_sqft': request.form.get('max_sqft'),
        'property_types': request.form.getlist('property_types'),
        'min_year': request.form.get('min_year'),
        'max_year': request.form.get('max_year'),
        'max_dom': request.form.get('max_dom'),
        'order_by': request.form.get('order_by', 'price'),
        'order_dir': request.form.get('order_dir', 'ASC'),
        'limit': request.form.get('limit', 100),
    }

    # Clean empty values
    filters = {k: v for k, v in filters.items() if v and v != '' and v != []}

    created_for = request.form.get('created_for', 'Client')
    results = execute_query(filters)
    options = get_filter_options()

    return render_template('query_form.html',
                         options=options,
                         results=results,
                         filters=filters,
                         created_for=created_for,
                         result_count=len(results))


@app.route('/export', methods=['POST'])
def export_csv():
    """Export search results to CSV."""
    filters = {
        'counties': request.form.getlist('counties'),
        'cities': request.form.getlist('cities'),
        'status': request.form.get('status'),
        'min_beds': request.form.get('min_beds'),
        'max_beds': request.form.get('max_beds'),
        'min_baths': request.form.get('min_baths'),
        'max_baths': request.form.get('max_baths'),
        'min_price': request.form.get('min_price'),
        'max_price': request.form.get('max_price'),
        'min_lot': request.form.get('min_lot'),
        'max_lot': request.form.get('max_lot'),
        'min_sqft': request.form.get('min_sqft'),
        'max_sqft': request.form.get('max_sqft'),
        'property_types': request.form.getlist('property_types'),
        'min_year': request.form.get('min_year'),
        'max_year': request.form.get('max_year'),
        'max_dom': request.form.get('max_dom'),
        'order_by': request.form.get('order_by', 'price'),
        'order_dir': request.form.get('order_dir', 'ASC'),
        'limit': 500,  # Higher limit for export
    }

    filters = {k: v for k, v in filters.items() if v and v != '' and v != []}
    results = execute_query(filters)

    created_for = request.form.get('created_for', 'Export')
    timestamp = datetime.now().strftime('%y%m%d_%H%M')
    filename = f"properties_{created_for.replace(' ', '_')}_{timestamp}.csv"

    # Create CSV
    output = io.StringIO()
    if results:
        writer = csv.DictWriter(output, fieldnames=[
            'address', 'city', 'county', 'zip', 'price', 'beds', 'baths',
            'sqft', 'acreage', 'year_built', 'property_type', 'status',
            'days_on_market', 'mls_number', 'mls_source', 'redfin_url'
        ])
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k, '') for k in writer.fieldnames})

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


if __name__ == '__main__':
    print(f"Database: {DB_PATH}")
    print(f"Starting Redfin Query App on http://localhost:5002")
    is_debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=5002, debug=is_debug)
