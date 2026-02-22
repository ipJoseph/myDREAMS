#!/usr/bin/env python3
"""
DREAMS Buyer Workflow App

Agent-centric workflow for managing buyer relationships:
1. Buyer intake forms (capture requirements)
2. Property search (from aggregated sources)
3. Package creation (group properties for presentation)
4. Client presentation (shareable links)
5. Showing management (itinerary, routing)

Port: 5003
"""

import json
import logging
import os
import secrets
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, g

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))


# Custom Jinja filters
@app.template_filter('from_json')
def from_json_filter(value):
    """Parse JSON string to Python object."""
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


@app.context_processor
def utility_processor():
    """Add utility functions to templates."""
    return {
        'now': datetime.utcnow
    }

# Database path (single database for all data)
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

# Need types for intake forms
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


def get_db():
    """Get database connection for workflow data (leads, forms, packages)."""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def get_properties_db():
    """Get database connection for property searches (same as dreams.db)."""
    return get_db()


@app.teardown_appcontext
def close_db(error):
    """Close database connections."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize database tables from schema.sql."""
    schema_path = Path(__file__).parent / 'schema.sql'
    if not schema_path.exists():
        return

    db = sqlite3.connect(DB_PATH)
    try:
        # Strip SQL comments, then execute each statement individually
        schema = schema_path.read_text()
        # Remove full-line comments
        lines = [line for line in schema.splitlines() if not line.strip().startswith('--')]
        clean_sql = '\n'.join(lines)
        for statement in clean_sql.split(';'):
            statement = statement.strip()
            if not statement:
                continue
            try:
                db.execute(statement)
            except sqlite3.OperationalError:
                pass  # Table/index already exists or column mismatch
        db.commit()
        logger.info("Database schema initialized from schema.sql")
    except Exception as e:
        logger.error(f"Error initializing schema: {e}")
    finally:
        db.close()


# Initialize tables at startup
init_db()


def row_to_dict(row):
    """Convert sqlite3.Row to dict."""
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    """Convert list of sqlite3.Row to list of dicts."""
    return [dict(row) for row in rows]


# =============================================================================
# DASHBOARD
# =============================================================================

@app.route('/')
def dashboard():
    """Main dashboard showing overview."""
    db = get_db()

    # Get counts
    leads_count = db.execute('SELECT COUNT(*) FROM leads WHERE stage != "closed"').fetchone()[0]
    active_forms = db.execute('SELECT COUNT(*) FROM intake_forms WHERE status = "active"').fetchone()[0]
    active_packages = db.execute('SELECT COUNT(*) FROM property_packages WHERE status IN ("draft", "ready", "sent")').fetchone()[0]
    upcoming_showings = db.execute('SELECT COUNT(*) FROM showings WHERE status = "scheduled" AND scheduled_date >= date("now")').fetchone()[0]

    # Recent leads
    recent_leads = db.execute('''
        SELECT id, first_name, last_name, email, phone, stage, heat_score
        FROM leads
        ORDER BY updated_at DESC
        LIMIT 10
    ''').fetchall()

    # Active intake forms
    active_intake = db.execute('''
        SELECT i.*, l.first_name, l.last_name
        FROM intake_forms i
        JOIN leads l ON i.lead_id = l.id
        WHERE i.status = 'active'
        ORDER BY i.updated_at DESC
        LIMIT 10
    ''').fetchall()

    return render_template('dashboard.html',
        leads_count=leads_count,
        active_forms=active_forms,
        active_packages=active_packages,
        upcoming_showings=upcoming_showings,
        recent_leads=rows_to_list(recent_leads),
        active_intake=rows_to_list(active_intake),
    )


# =============================================================================
# LEADS / BUYERS
# =============================================================================

@app.route('/leads')
def leads_list():
    """List all leads/buyers."""
    db = get_db()

    # Get filter params
    stage = request.args.get('stage', '')
    lead_type = request.args.get('type', '')
    search = request.args.get('search', '')

    query = 'SELECT * FROM leads WHERE 1=1'
    params = []

    if stage:
        query += ' AND stage = ?'
        params.append(stage)
    if lead_type:
        query += ' AND type = ?'
        params.append(lead_type)
    if search:
        query += ' AND (first_name LIKE ? OR last_name LIKE ? OR email LIKE ?)'
        params.extend([f'%{search}%'] * 3)

    query += ' ORDER BY heat_score DESC, updated_at DESC LIMIT 100'

    leads = db.execute(query, params).fetchall()

    return render_template('leads.html',
        leads=rows_to_list(leads),
        stage=stage,
        lead_type=lead_type,
        search=search,
    )


@app.route('/leads/<lead_id>')
def lead_detail(lead_id):
    """Lead detail page with intake forms and packages."""
    db = get_db()

    lead = db.execute('SELECT * FROM leads WHERE id = ?', (lead_id,)).fetchone()
    if not lead:
        flash('Lead not found', 'error')
        return redirect(url_for('leads_list'))

    # Get intake forms for this lead
    intake_forms = db.execute('''
        SELECT * FROM intake_forms
        WHERE lead_id = ?
        ORDER BY created_at DESC
    ''', (lead_id,)).fetchall()

    # Get packages for this lead
    packages = db.execute('''
        SELECT p.*, COUNT(pp.id) as property_count
        FROM property_packages p
        LEFT JOIN package_properties pp ON p.id = pp.package_id
        WHERE p.lead_id = ?
        GROUP BY p.id
        ORDER BY p.created_at DESC
    ''', (lead_id,)).fetchall()

    # Get showings
    showings = db.execute('''
        SELECT * FROM showings
        WHERE lead_id = ?
        ORDER BY scheduled_date DESC
    ''', (lead_id,)).fetchall()

    return render_template('lead_detail.html',
        lead=row_to_dict(lead),
        intake_forms=rows_to_list(intake_forms),
        packages=rows_to_list(packages),
        showings=rows_to_list(showings),
        need_types=NEED_TYPES,
    )


# =============================================================================
# INTAKE FORMS
# =============================================================================

@app.route('/intake/new/<lead_id>')
def intake_new(lead_id):
    """New intake form for a lead."""
    db = get_db()

    lead = db.execute('SELECT * FROM leads WHERE id = ?', (lead_id,)).fetchone()
    if not lead:
        flash('Lead not found', 'error')
        return redirect(url_for('leads_list'))

    return render_template('intake_form.html',
        lead=row_to_dict(lead),
        form=None,
        need_types=NEED_TYPES,
        urgency_options=URGENCY_OPTIONS,
        financing_options=FINANCING_OPTIONS,
        counties=WNC_COUNTIES,
        property_types=PROPERTY_TYPES,
        view_options=VIEW_OPTIONS,
        water_options=WATER_OPTIONS,
    )


@app.route('/intake/<form_id>')
def intake_edit(form_id):
    """Edit existing intake form."""
    db = get_db()

    form = db.execute('SELECT * FROM intake_forms WHERE id = ?', (form_id,)).fetchone()
    if not form:
        flash('Intake form not found', 'error')
        return redirect(url_for('leads_list'))

    lead = db.execute('SELECT * FROM leads WHERE id = ?', (form['lead_id'],)).fetchone()

    return render_template('intake_form.html',
        lead=row_to_dict(lead),
        form=row_to_dict(form),
        need_types=NEED_TYPES,
        urgency_options=URGENCY_OPTIONS,
        financing_options=FINANCING_OPTIONS,
        counties=WNC_COUNTIES,
        property_types=PROPERTY_TYPES,
        view_options=VIEW_OPTIONS,
        water_options=WATER_OPTIONS,
    )


@app.route('/intake/save', methods=['POST'])
def intake_save():
    """Save intake form."""
    db = get_db()

    form_id = request.form.get('form_id')
    lead_id = request.form.get('lead_id')
    is_new = not form_id

    if is_new:
        form_id = str(uuid.uuid4())

    # Build JSON arrays from multi-select fields
    def get_json_array(field):
        values = request.form.getlist(field)
        return json.dumps(values) if values else None

    data = {
        'id': form_id,
        'lead_id': lead_id,
        'form_name': request.form.get('form_name'),
        'need_type': request.form.get('need_type'),
        'status': request.form.get('status', 'active'),
        'priority': request.form.get('priority', 1),
        'source': request.form.get('source'),
        'source_date': request.form.get('source_date'),
        'source_notes': request.form.get('source_notes'),

        # Location
        'counties': get_json_array('counties'),
        'cities': get_json_array('cities'),
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
        'updated_at': datetime.utcnow().isoformat(),
    }

    if is_new:
        data['created_at'] = datetime.utcnow().isoformat()
        placeholders = ', '.join(['?' for _ in data])
        columns = ', '.join(data.keys())
        db.execute(f'INSERT INTO intake_forms ({columns}) VALUES ({placeholders})', list(data.values()))
    else:
        set_clause = ', '.join([f'{k} = ?' for k in data.keys() if k != 'id'])
        values = [v for k, v in data.items() if k != 'id'] + [form_id]
        db.execute(f'UPDATE intake_forms SET {set_clause} WHERE id = ?', values)

    db.commit()

    flash('Intake form saved successfully', 'success')
    return redirect(url_for('lead_detail', lead_id=lead_id))


@app.route('/intake/<form_id>/search')
def intake_search(form_id):
    """Search properties based on intake form criteria."""
    db = get_db()
    props_db = get_properties_db()

    form = db.execute('SELECT * FROM intake_forms WHERE id = ?', (form_id,)).fetchone()
    if not form:
        flash('Intake form not found', 'error')
        return redirect(url_for('leads_list'))

    lead = db.execute('SELECT * FROM leads WHERE id = ?', (form['lead_id'],)).fetchone()

    # Build property query from intake criteria
    query = 'SELECT * FROM listings WHERE 1=1'
    params = []

    form = row_to_dict(form)

    # Price range
    if form.get('min_price'):
        query += ' AND list_price >= ?'
        params.append(int(form['min_price']))
    if form.get('max_price'):
        query += ' AND list_price <= ?'
        params.append(int(form['max_price']))

    # Beds/Baths
    if form.get('min_beds'):
        query += ' AND beds >= ?'
        params.append(int(form['min_beds']))
    if form.get('min_baths'):
        query += ' AND baths >= ?'
        params.append(float(form['min_baths']))

    # Size
    if form.get('min_sqft'):
        query += ' AND sqft >= ?'
        params.append(int(form['min_sqft']))
    if form.get('min_acreage'):
        query += ' AND acreage >= ?'
        params.append(float(form['min_acreage']))

    # Counties
    if form.get('counties'):
        counties = json.loads(form['counties'])
        if counties:
            placeholders = ','.join(['?' for _ in counties])
            query += f' AND county IN ({placeholders})'
            params.extend(counties)

    # Property types
    if form.get('property_types'):
        types = json.loads(form['property_types'])
        if types:
            placeholders = ','.join(['?' for _ in types])
            query += f' AND property_type IN ({placeholders})'
            params.extend(types)

    query += ' AND status = "ACTIVE" ORDER BY days_on_market ASC, list_price ASC LIMIT 100'

    # Debug logging
    logger.info(f"Search query: {query}")
    logger.info(f"Search params: {params}")

    properties = props_db.execute(query, params).fetchall()
    logger.info(f"Found {len(properties)} properties")

    return render_template('intake_search_results.html',
        form=form,
        lead=row_to_dict(lead),
        properties=rows_to_list(properties),
    )


# =============================================================================
# PROPERTY PACKAGES
# =============================================================================

@app.route('/packages')
def packages_list():
    """List all packages."""
    db = get_db()

    packages = db.execute('''
        SELECT p.*, l.first_name, l.last_name, COUNT(pp.id) as property_count
        FROM property_packages p
        JOIN leads l ON p.lead_id = l.id
        LEFT JOIN package_properties pp ON p.id = pp.package_id
        GROUP BY p.id
        ORDER BY p.updated_at DESC
    ''').fetchall()

    return render_template('packages.html', packages=rows_to_list(packages))


@app.route('/packages/new/<lead_id>')
def package_new(lead_id):
    """Create new package for a lead."""
    db = get_db()

    lead = db.execute('SELECT * FROM leads WHERE id = ?', (lead_id,)).fetchone()
    if not lead:
        flash('Lead not found', 'error')
        return redirect(url_for('leads_list'))

    # Get intake forms to optionally link
    intake_forms = db.execute('''
        SELECT id, form_name, need_type FROM intake_forms
        WHERE lead_id = ? AND status = 'active'
    ''', (lead_id,)).fetchall()

    return render_template('package_form.html',
        lead=row_to_dict(lead),
        package=None,
        intake_forms=rows_to_list(intake_forms),
    )


@app.route('/packages/<package_id>')
def package_detail(package_id):
    """Package detail with properties."""
    db = get_db()
    props_db = get_properties_db()

    package = db.execute('''
        SELECT p.*, l.first_name, l.last_name, l.email, l.phone
        FROM property_packages p
        JOIN leads l ON p.lead_id = l.id
        WHERE p.id = ?
    ''', (package_id,)).fetchone()

    if not package:
        flash('Package not found', 'error')
        return redirect(url_for('packages_list'))

    # Get package_properties metadata
    pkg_props = db.execute('''
        SELECT property_id, display_order, agent_notes as package_notes,
               client_favorited, client_rating, showing_requested
        FROM package_properties
        WHERE package_id = ?
        ORDER BY display_order
    ''', (package_id,)).fetchall()

    # Fetch property details from listings
    properties = []
    if pkg_props:
        prop_ids = [p['property_id'] for p in pkg_props]
        placeholders = ','.join(['?' for _ in prop_ids])
        props_data = props_db.execute(f'SELECT * FROM listings WHERE id IN ({placeholders})', prop_ids).fetchall()
        props_dict = {p['id']: dict(p) for p in props_data}

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

    # Get intake form if linked
    intake_form = None
    if package['intake_form_id']:
        intake_form = db.execute(
            'SELECT * FROM intake_forms WHERE id = ?',
            (package['intake_form_id'],)
        ).fetchone()

    return render_template('package_detail.html',
        package=row_to_dict(package),
        properties=properties,  # Already list of dicts
        intake_form=row_to_dict(intake_form) if intake_form else None,
    )


@app.route('/packages/save', methods=['POST'])
def package_save():
    """Save package."""
    db = get_db()

    package_id = request.form.get('package_id')
    lead_id = request.form.get('lead_id')
    is_new = not package_id

    if is_new:
        package_id = str(uuid.uuid4())
        share_token = secrets.token_urlsafe(16)
    else:
        existing = db.execute('SELECT share_token FROM property_packages WHERE id = ?', (package_id,)).fetchone()
        share_token = existing['share_token'] if existing else secrets.token_urlsafe(16)

    data = {
        'id': package_id,
        'lead_id': lead_id,
        'intake_form_id': request.form.get('intake_form_id') or None,
        'name': request.form.get('name'),
        'description': request.form.get('description'),
        'status': request.form.get('status', 'draft'),
        'share_token': share_token,
        'notes': request.form.get('notes'),
        'updated_at': datetime.utcnow().isoformat(),
    }

    if is_new:
        data['created_at'] = datetime.utcnow().isoformat()
        placeholders = ', '.join(['?' for _ in data])
        columns = ', '.join(data.keys())
        db.execute(f'INSERT INTO property_packages ({columns}) VALUES ({placeholders})', list(data.values()))
    else:
        set_clause = ', '.join([f'{k} = ?' for k in data.keys() if k != 'id'])
        values = [v for k, v in data.items() if k != 'id'] + [package_id]
        db.execute(f'UPDATE property_packages SET {set_clause} WHERE id = ?', values)

    # Add selected properties to the package (from search results)
    property_ids = request.form.getlist('property_ids')
    if property_ids:
        for i, prop_id in enumerate(property_ids):
            # Check if already in package
            existing = db.execute(
                'SELECT id FROM package_properties WHERE package_id = ? AND property_id = ?',
                (package_id, prop_id)
            ).fetchone()

            if not existing:
                db.execute('''
                    INSERT INTO package_properties (id, package_id, property_id, display_order, added_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (str(uuid.uuid4()), package_id, prop_id, i + 1, datetime.utcnow().isoformat()))

    db.commit()

    if property_ids:
        flash(f'Package created with {len(property_ids)} properties', 'success')
    else:
        flash('Package saved successfully', 'success')
    return redirect(url_for('package_detail', package_id=package_id))


@app.route('/packages/<package_id>/add-properties', methods=['GET', 'POST'])
def package_add_properties(package_id):
    """Add properties to package."""
    db = get_db()
    props_db = get_properties_db()

    package = db.execute('SELECT * FROM property_packages WHERE id = ?', (package_id,)).fetchone()
    if not package:
        flash('Package not found', 'error')
        return redirect(url_for('packages_list'))

    if request.method == 'POST':
        property_ids = request.form.getlist('property_ids')

        # Get current max order
        max_order = db.execute(
            'SELECT MAX(display_order) FROM package_properties WHERE package_id = ?',
            (package_id,)
        ).fetchone()[0] or 0

        for i, prop_id in enumerate(property_ids):
            # Check if already in package
            existing = db.execute(
                'SELECT id FROM package_properties WHERE package_id = ? AND property_id = ?',
                (package_id, prop_id)
            ).fetchone()

            if not existing:
                db.execute('''
                    INSERT INTO package_properties (id, package_id, property_id, display_order, added_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (str(uuid.uuid4()), package_id, prop_id, max_order + i + 1, datetime.utcnow().isoformat()))

        db.commit()
        flash(f'Added {len(property_ids)} properties to package', 'success')
        return redirect(url_for('package_detail', package_id=package_id))

    # GET - show property selection
    # Get properties not already in this package
    existing_ids = db.execute(
        'SELECT property_id FROM package_properties WHERE package_id = ?',
        (package_id,)
    ).fetchall()
    existing_ids = [r['property_id'] for r in existing_ids]

    # Get filter criteria
    county = request.args.get('county', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    search = request.args.get('search', '')

    query = 'SELECT * FROM listings WHERE status = "ACTIVE"'
    params = []

    if existing_ids:
        placeholders = ','.join(['?' for _ in existing_ids])
        query += f' AND id NOT IN ({placeholders})'
        params.extend(existing_ids)

    if county:
        query += ' AND county = ?'
        params.append(county)
    if min_price:
        query += ' AND list_price >= ?'
        params.append(int(min_price))
    if max_price:
        query += ' AND list_price <= ?'
        params.append(int(max_price))
    if search:
        query += ' AND (address LIKE ? OR city LIKE ? OR mls_number LIKE ?)'
        params.extend([f'%{search}%'] * 3)

    query += ' ORDER BY days_on_market ASC LIMIT 100'

    properties = props_db.execute(query, params).fetchall()

    return render_template('package_add_properties.html',
        package=row_to_dict(package),
        properties=rows_to_list(properties),
        counties=WNC_COUNTIES,
        county=county,
        min_price=min_price,
        max_price=max_price,
        search=search,
    )


@app.route('/packages/<package_id>/remove/<property_id>', methods=['POST'])
def package_remove_property(package_id, property_id):
    """Remove property from package."""
    db = get_db()
    db.execute(
        'DELETE FROM package_properties WHERE package_id = ? AND property_id = ?',
        (package_id, property_id)
    )
    db.commit()
    return jsonify({'success': True})


# =============================================================================
# CLIENT PRESENTATION VIEW (Public)
# =============================================================================

@app.route('/view/<share_token>')
def client_view(share_token):
    """Public client view of a package."""
    db = get_db()
    props_db = get_properties_db()

    package = db.execute('''
        SELECT p.*, l.first_name, l.last_name
        FROM property_packages p
        JOIN leads l ON p.lead_id = l.id
        WHERE p.share_token = ?
    ''', (share_token,)).fetchone()

    if not package:
        return render_template('client_not_found.html'), 404

    # Check expiration
    if package['expires_at']:
        if datetime.fromisoformat(package['expires_at']) < datetime.utcnow():
            return render_template('client_expired.html'), 410

    # Update view tracking
    db.execute('''
        UPDATE property_packages
        SET view_count = view_count + 1,
            viewed_at = COALESCE(viewed_at, ?)
        WHERE id = ?
    ''', (datetime.utcnow().isoformat(), package['id']))
    db.commit()

    # Get package_properties metadata
    pkg_props = db.execute('''
        SELECT property_id, display_order, client_notes, highlight_features,
               client_favorited, client_rating
        FROM package_properties
        WHERE package_id = ?
        ORDER BY display_order
    ''', (package['id'],)).fetchall()

    # Fetch property details from listings
    properties = []
    if pkg_props:
        prop_ids = [p['property_id'] for p in pkg_props]
        placeholders = ','.join(['?' for _ in prop_ids])
        props_data = props_db.execute(f'SELECT * FROM listings WHERE id IN ({placeholders})', prop_ids).fetchall()
        props_dict = {p['id']: dict(p) for p in props_data}

        for pp in pkg_props:
            prop = props_dict.get(pp['property_id'])
            if prop:
                prop.update({
                    'display_order': pp['display_order'],
                    'client_notes': pp['client_notes'],
                    'highlight_features': pp['highlight_features'],
                    'client_favorited': pp['client_favorited'],
                    'client_rating': pp['client_rating'],
                })
                properties.append(prop)

    return render_template('client_view.html',
        package=row_to_dict(package),
        properties=properties,  # Already list of dicts
    )


@app.route('/view/<share_token>/favorite/<property_id>', methods=['POST'])
def client_favorite(share_token, property_id):
    """Toggle client favorite."""
    db = get_db()

    package = db.execute(
        'SELECT id FROM property_packages WHERE share_token = ?',
        (share_token,)
    ).fetchone()

    if not package:
        return jsonify({'error': 'Not found'}), 404

    # Toggle favorite
    current = db.execute('''
        SELECT client_favorited FROM package_properties
        WHERE package_id = ? AND property_id = ?
    ''', (package['id'], property_id)).fetchone()

    new_value = 0 if current and current['client_favorited'] else 1

    db.execute('''
        UPDATE package_properties
        SET client_favorited = ?, client_viewed_at = ?
        WHERE package_id = ? AND property_id = ?
    ''', (new_value, datetime.utcnow().isoformat(), package['id'], property_id))
    db.commit()

    return jsonify({'favorited': new_value})


@app.route('/view/<share_token>/request-showing/<property_id>', methods=['POST'])
def client_request_showing(share_token, property_id):
    """Client requests showing for a property."""
    db = get_db()

    package = db.execute(
        'SELECT id FROM property_packages WHERE share_token = ?',
        (share_token,)
    ).fetchone()

    if not package:
        return jsonify({'error': 'Not found'}), 404

    db.execute('''
        UPDATE package_properties
        SET showing_requested = 1
        WHERE package_id = ? AND property_id = ?
    ''', (package['id'], property_id))
    db.commit()

    return jsonify({'success': True})


# =============================================================================
# SHOWINGS
# =============================================================================

@app.route('/showings')
def showings_list():
    """List all showings."""
    db = get_db()

    showings = db.execute('''
        SELECT s.*, l.first_name, l.last_name,
               COUNT(sp.id) as property_count
        FROM showings s
        JOIN leads l ON s.lead_id = l.id
        LEFT JOIN showing_properties sp ON s.id = sp.showing_id
        GROUP BY s.id
        ORDER BY s.scheduled_date DESC, s.scheduled_time
    ''').fetchall()

    return render_template('showings.html', showings=rows_to_list(showings))


@app.route('/showings/new/<lead_id>')
def showing_new(lead_id):
    """Create new showing."""
    db = get_db()
    props_db = get_properties_db()

    lead = db.execute('SELECT * FROM leads WHERE id = ?', (lead_id,)).fetchone()
    if not lead:
        flash('Lead not found', 'error')
        return redirect(url_for('leads_list'))

    # Get packages for this lead
    packages = db.execute('''
        SELECT p.*, COUNT(pp.id) as property_count
        FROM property_packages p
        LEFT JOIN package_properties pp ON p.id = pp.package_id
        WHERE p.lead_id = ?
        GROUP BY p.id
    ''', (lead_id,)).fetchall()

    # Get properties with showing requested - first get IDs from dreams.db
    req_props = db.execute('''
        SELECT pp.property_id, pp.package_id
        FROM package_properties pp
        JOIN property_packages pkg ON pp.package_id = pkg.id
        WHERE pkg.lead_id = ? AND pp.showing_requested = 1
    ''', (lead_id,)).fetchall()

    # Then fetch property details from listings
    requested = []
    if req_props:
        prop_ids = [p['property_id'] for p in req_props]
        placeholders = ','.join(['?' for _ in prop_ids])
        props_data = props_db.execute(f'SELECT * FROM listings WHERE id IN ({placeholders})', prop_ids).fetchall()
        props_dict = {p['id']: dict(p) for p in props_data}

        for rp in req_props:
            prop = props_dict.get(rp['property_id'])
            if prop:
                prop['package_id'] = rp['package_id']
                requested.append(prop)

    return render_template('showing_form.html',
        lead=row_to_dict(lead),
        showing=None,
        packages=rows_to_list(packages),
        requested_properties=requested,  # Already list of dicts
    )


@app.route('/showings/<showing_id>')
def showing_detail(showing_id):
    """Showing detail with itinerary."""
    db = get_db()
    props_db = get_properties_db()

    showing = db.execute('''
        SELECT s.*, l.first_name, l.last_name, l.phone, l.email
        FROM showings s
        JOIN leads l ON s.lead_id = l.id
        WHERE s.id = ?
    ''', (showing_id,)).fetchone()

    if not showing:
        flash('Showing not found', 'error')
        return redirect(url_for('showings_list'))

    # Get showing_properties metadata
    show_props = db.execute('''
        SELECT property_id, stop_order, scheduled_time, time_at_property,
               showing_type, access_info, special_instructions, status
        FROM showing_properties
        WHERE showing_id = ?
        ORDER BY stop_order
    ''', (showing_id,)).fetchall()

    # Fetch property details from listings
    properties = []
    if show_props:
        prop_ids = [p['property_id'] for p in show_props]
        placeholders = ','.join(['?' for _ in prop_ids])
        props_data = props_db.execute(f'SELECT * FROM listings WHERE id IN ({placeholders})', prop_ids).fetchall()
        props_dict = {p['id']: dict(p) for p in props_data}

        for sp in show_props:
            prop = props_dict.get(sp['property_id'])
            if prop:
                prop.update({
                    'stop_order': sp['stop_order'],
                    'scheduled_time': sp['scheduled_time'],
                    'time_at_property': sp['time_at_property'],
                    'showing_type': sp['showing_type'],
                    'access_info': sp['access_info'],
                    'special_instructions': sp['special_instructions'],
                    'status': sp['status'],
                })
                properties.append(prop)

    return render_template('showing_detail.html',
        showing=row_to_dict(showing),
        properties=properties,  # Already list of dicts
    )


@app.route('/showings/save', methods=['POST'])
def showing_save():
    """Save showing."""
    db = get_db()

    showing_id = request.form.get('showing_id')
    lead_id = request.form.get('lead_id')
    is_new = not showing_id

    if is_new:
        showing_id = str(uuid.uuid4())

    data = {
        'id': showing_id,
        'lead_id': lead_id,
        'package_id': request.form.get('package_id') or None,
        'name': request.form.get('name'),
        'scheduled_date': request.form.get('scheduled_date'),
        'scheduled_time': request.form.get('scheduled_time'),
        'meeting_point': request.form.get('meeting_point'),
        'meeting_address': request.form.get('meeting_address'),
        'agent_notes': request.form.get('agent_notes'),
        'updated_at': datetime.utcnow().isoformat(),
    }

    if is_new:
        data['status'] = 'scheduled'
        data['created_at'] = datetime.utcnow().isoformat()
        placeholders = ', '.join(['?' for _ in data])
        columns = ', '.join(data.keys())
        db.execute(f'INSERT INTO showings ({columns}) VALUES ({placeholders})', list(data.values()))
    else:
        set_clause = ', '.join([f'{k} = ?' for k in data.keys() if k != 'id'])
        values = [v for k, v in data.items() if k != 'id'] + [showing_id]
        db.execute(f'UPDATE showings SET {set_clause} WHERE id = ?', values)

    db.commit()

    flash('Showing saved successfully', 'success')
    return redirect(url_for('showing_detail', showing_id=showing_id))


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/leads/search')
def api_leads_search():
    """Search leads API."""
    db = get_db()
    q = request.args.get('q', '')

    if len(q) < 2:
        return jsonify([])

    leads = db.execute('''
        SELECT id, first_name, last_name, email, phone
        FROM leads
        WHERE first_name LIKE ? OR last_name LIKE ? OR email LIKE ?
        LIMIT 20
    ''', (f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()

    return jsonify(rows_to_list(leads))


@app.route('/showings/<showing_id>/add-properties', methods=['GET', 'POST'])
def showing_add_properties(showing_id):
    """Add properties to a showing."""
    db = get_db()
    props_db = get_properties_db()

    showing = db.execute('SELECT * FROM showings WHERE id = ?', (showing_id,)).fetchone()
    if not showing:
        flash('Showing not found', 'error')
        return redirect(url_for('showings_list'))

    if request.method == 'POST':
        property_ids = request.form.getlist('property_ids')

        # Get current max order
        max_order = db.execute(
            'SELECT MAX(stop_order) FROM showing_properties WHERE showing_id = ?',
            (showing_id,)
        ).fetchone()[0] or 0

        for i, prop_id in enumerate(property_ids):
            existing = db.execute(
                'SELECT id FROM showing_properties WHERE showing_id = ? AND property_id = ?',
                (showing_id, prop_id)
            ).fetchone()

            if not existing:
                db.execute('''
                    INSERT INTO showing_properties (id, showing_id, property_id, stop_order, status)
                    VALUES (?, ?, ?, ?, 'pending')
                ''', (str(uuid.uuid4()), showing_id, prop_id, max_order + i + 1))

        db.commit()
        flash(f'Added {len(property_ids)} properties to showing', 'success')
        return redirect(url_for('showing_detail', showing_id=showing_id))

    # GET - show property selection
    existing_ids = db.execute(
        'SELECT property_id FROM showing_properties WHERE showing_id = ?',
        (showing_id,)
    ).fetchall()
    existing_ids = [r['property_id'] for r in existing_ids]

    # Get properties from linked package if any
    properties = []
    if showing['package_id']:
        # Get property_ids from package (dreams.db), then fetch details from props_db
        package_prop_ids = db.execute(
            'SELECT property_id FROM package_properties WHERE package_id = ?',
            (showing['package_id'],)
        ).fetchall()
        if package_prop_ids:
            prop_ids = [r['property_id'] for r in package_prop_ids]
            placeholders = ','.join(['?' for _ in prop_ids])
            properties = props_db.execute(f'''
                SELECT * FROM listings WHERE id IN ({placeholders})
            ''', prop_ids).fetchall()
    else:
        properties = props_db.execute('''
            SELECT * FROM listings
            WHERE status = 'ACTIVE'
            ORDER BY county, city
            LIMIT 100
        ''').fetchall()

    return render_template('showing_add_properties.html',
        showing=row_to_dict(showing),
        properties=rows_to_list(properties),
        existing_ids=existing_ids,
    )


@app.route('/showings/<showing_id>/optimize-route', methods=['POST'])
def showing_optimize_route(showing_id):
    """Optimize the showing route order using nearest neighbor algorithm."""
    db = get_db()
    props_db = get_properties_db()

    showing = db.execute('SELECT * FROM showings WHERE id = ?', (showing_id,)).fetchone()
    if not showing:
        return jsonify({'error': 'Showing not found'}), 404

    # Get showing_properties from dreams.db
    show_props = db.execute('''
        SELECT id, property_id, stop_order FROM showing_properties
        WHERE showing_id = ?
        ORDER BY stop_order
    ''', (showing_id,)).fetchall()

    if not show_props:
        return jsonify({'error': 'No properties in showing'}), 400

    # Fetch property coordinates from listings
    prop_ids = [p['property_id'] for p in show_props]
    placeholders = ','.join(['?' for _ in prop_ids])
    props_data = props_db.execute(f'''
        SELECT id, address, latitude, longitude FROM listings WHERE id IN ({placeholders})
    ''', prop_ids).fetchall()
    props_dict = {p['id']: dict(p) for p in props_data}

    # Merge showing_properties with property data
    properties = []
    for sp in show_props:
        prop = props_dict.get(sp['property_id'])
        if prop:
            properties.append({
                'id': sp['id'],
                'property_id': sp['property_id'],
                'stop_order': sp['stop_order'],
                'address': prop['address'],
                'latitude': prop['latitude'],
                'longitude': prop['longitude'],
            })

    # Filter to properties with coordinates
    with_coords = [p for p in properties if p['latitude'] and p['longitude']]

    if len(with_coords) < 2:
        return jsonify({'error': 'Need at least 2 properties with coordinates'}), 400

    # Simple nearest neighbor optimization
    # Start with meeting point if available, otherwise first property
    start_lat = showing['meeting_address'] if showing['meeting_address'] else None

    optimized = []
    remaining = with_coords.copy()

    # Start with first property (or could use meeting point)
    current = remaining.pop(0)
    optimized.append(current)

    while remaining:
        # Find nearest unvisited property
        nearest = min(remaining, key=lambda p: _haversine(
            current['latitude'], current['longitude'],
            p['latitude'], p['longitude']
        ))
        remaining.remove(nearest)
        optimized.append(nearest)
        current = nearest

    # Update stop orders
    for i, prop in enumerate(optimized):
        db.execute('''
            UPDATE showing_properties SET stop_order = ? WHERE id = ?
        ''', (i + 1, prop['id']))

    # Calculate total distance
    total_distance = 0
    for i in range(len(optimized) - 1):
        total_distance += _haversine(
            optimized[i]['latitude'], optimized[i]['longitude'],
            optimized[i+1]['latitude'], optimized[i+1]['longitude']
        )

    # Estimate drive time (assume 30mph average in mountains)
    drive_time_hours = total_distance / 30
    drive_time_minutes = int(drive_time_hours * 60)

    # Update showing with route info
    db.execute('''
        UPDATE showings
        SET route_optimized = 1, total_drive_time = ?, total_distance = ?, updated_at = ?
        WHERE id = ?
    ''', (drive_time_minutes, round(total_distance, 1), datetime.utcnow().isoformat(), showing_id))

    db.commit()

    return jsonify({
        'success': True,
        'total_distance': round(total_distance, 1),
        'drive_time_minutes': drive_time_minutes,
        'order': [p['property_id'] for p in optimized]
    })


def _haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in miles."""
    from math import radians, sin, cos, sqrt, atan2

    R = 3959  # Earth's radius in miles

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


@app.route('/showings/<showing_id>/google-maps-url')
def showing_google_maps_url(showing_id):
    """Generate Google Maps directions URL for the showing."""
    db = get_db()
    props_db = get_properties_db()

    showing = db.execute('SELECT * FROM showings WHERE id = ?', (showing_id,)).fetchone()
    if not showing:
        return jsonify({'error': 'Showing not found'}), 404

    # Get showing_properties in order
    show_props = db.execute('''
        SELECT property_id FROM showing_properties
        WHERE showing_id = ?
        ORDER BY stop_order
    ''', (showing_id,)).fetchall()

    if not show_props:
        return jsonify({'error': 'No properties in showing'}), 400

    # Fetch property addresses from listings
    prop_ids = [p['property_id'] for p in show_props]
    placeholders = ','.join(['?' for _ in prop_ids])
    props_data = props_db.execute(f'''
        SELECT id, address, city, state, zip FROM listings WHERE id IN ({placeholders})
    ''', prop_ids).fetchall()
    props_dict = {p['id']: dict(p) for p in props_data}

    # Build ordered list of properties
    properties = []
    for sp in show_props:
        prop = props_dict.get(sp['property_id'])
        if prop:
            properties.append(prop)

    # Build Google Maps URL
    # Format: https://www.google.com/maps/dir/origin/waypoint1/waypoint2/.../destination
    addresses = []

    # Add meeting point as origin if available
    if showing['meeting_address']:
        addresses.append(showing['meeting_address'])

    # Add all properties
    for prop in properties:
        addr = f"{prop['address']}, {prop['city']}, {prop['state']} {prop['zip']}"
        addresses.append(addr)

    # URL encode addresses
    from urllib.parse import quote
    encoded = '/'.join(quote(addr) for addr in addresses)

    maps_url = f"https://www.google.com/maps/dir/{encoded}"

    return jsonify({
        'url': maps_url,
        'addresses': addresses
    })


@app.route('/api/mls/open/<mls_number>')
def api_mls_open(mls_number):
    """Open Canopy MLS listing page for a given MLS number.

    Launches browser with authenticated MLS session.
    Requires prior login: python apps/redfin-importer/mls_opener.py --login
    """
    import subprocess

    cookies_file = PROJECT_ROOT / 'data' / '.canopy_mls_cookies.json'

    if not cookies_file.exists():
        return jsonify({
            'error': 'MLS login required',
            'message': 'Run: python apps/redfin-importer/mls_opener.py --login'
        }), 401

    # Launch MLS opener in background (headed mode so user sees browser)
    mls_script = PROJECT_ROOT / 'apps' / 'redfin-importer' / 'mls_opener.py'

    try:
        # Run async in background - opens browser with MLS listing
        subprocess.Popen(
            [sys.executable, str(mls_script), '--mls', mls_number, '--headed'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return jsonify({
            'success': True,
            'message': f'Opening MLS# {mls_number} in browser'
        })
    except Exception as e:
        logger.error(f"Error launching MLS opener: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/properties/search')
def api_properties_search():
    """Search properties API."""
    props_db = get_properties_db()

    county = request.args.get('county')
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    beds = request.args.get('beds')
    status = request.args.get('status', 'ACTIVE')

    query = 'SELECT * FROM listings WHERE 1=1'
    params = []

    if status:
        query += ' AND (status = ? OR LOWER(status) = LOWER(?))'
        params.extend([status, status])
    if county:
        query += ' AND county = ?'
        params.append(county)
    if min_price:
        query += ' AND list_price >= ?'
        params.append(int(min_price))
    if max_price:
        query += ' AND list_price <= ?'
        params.append(int(max_price))
    if beds:
        query += ' AND beds >= ?'
        params.append(int(beds))

    query += ' ORDER BY days_on_market LIMIT 50'

    properties = props_db.execute(query, params).fetchall()
    return jsonify(rows_to_list(properties))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    is_debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=5003, debug=is_debug)
