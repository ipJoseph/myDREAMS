"""
Admin API endpoints for agent-facing operations.

These endpoints require API key authentication (X-API-Key header)
and handle template management, featured collections, and smart collection review.

Endpoints:
    POST   /admin/templates           - Create template
    GET    /admin/templates           - List templates
    GET    /admin/templates/:id       - Get template detail
    PUT    /admin/templates/:id       - Update template
    DELETE /admin/templates/:id       - Delete template
    POST   /admin/templates/:id/clone - Clone template for a buyer
    GET    /admin/featured            - List featured collections
    PUT    /admin/featured/:id        - Update featured status/order
    GET    /admin/smart-collections/queue - Pending smart collections
    POST   /admin/smart-collections/:id/review - Accept/reject smart collection
"""

import json
import logging
import os
import re
import secrets
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

admin_bp = Blueprint('admin', __name__)

DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


# =============================================================================
# TEMPLATE CRUD
# =============================================================================

@admin_bp.route('/templates', methods=['POST'])
def create_template():
    """Create a new template collection."""
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'success': False, 'error': {'code': 'VALIDATION', 'message': 'Name is required'}}), 400

    template_id = str(uuid.uuid4())
    slug = _slugify(data['name'])
    now = datetime.utcnow().isoformat()

    db = get_db()
    try:
        # Ensure slug is unique
        existing = db.execute('SELECT id FROM property_packages WHERE slug = ?', (slug,)).fetchone()
        if existing:
            slug = f"{slug}-{secrets.token_hex(3)}"

        db.execute('''
            INSERT INTO property_packages
            (id, name, description, status, collection_type, slug, cover_image,
             criteria_json, is_public, created_by, created_at, updated_at)
            VALUES (?, ?, ?, 'draft', 'template', ?, ?, ?, ?, ?, ?, ?)
        ''', (
            template_id,
            data['name'],
            data.get('description', ''),
            slug,
            data.get('cover_image'),
            json.dumps(data.get('criteria')) if data.get('criteria') else None,
            1 if data.get('is_public') else 0,
            data.get('created_by', 'agent'),
            now, now
        ))
        db.commit()

        return jsonify({
            'success': True,
            'template': {
                'id': template_id,
                'name': data['name'],
                'slug': slug,
                'collection_type': 'template'
            }
        }), 201

    except Exception as e:
        logger.error(f"Error creating template: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to create template'}}), 500
    finally:
        db.close()


@admin_bp.route('/templates', methods=['GET'])
def list_templates():
    """List all templates and featured collections."""
    collection_type = request.args.get('type', 'template')
    db = get_db()
    try:
        rows = db.execute('''
            SELECT pp.id, pp.name, pp.description, pp.status, pp.collection_type,
                   pp.slug, pp.cover_image, pp.is_public, pp.featured_order,
                   pp.criteria_json, pp.auto_refresh, pp.created_at, pp.updated_at,
                   COUNT(pkp.id) as property_count,
                   MIN(l.list_price) as min_price,
                   MAX(l.list_price) as max_price
            FROM property_packages pp
            LEFT JOIN package_properties pkp ON pkp.package_id = pp.id
            LEFT JOIN listings l ON l.id = pkp.listing_id
            WHERE pp.collection_type IN ('template', 'featured')
            GROUP BY pp.id
            ORDER BY pp.updated_at DESC
        ''').fetchall()

        templates = []
        for row in rows:
            t = dict(row)
            if t.get('criteria_json'):
                try:
                    t['criteria'] = json.loads(t['criteria_json'])
                except (json.JSONDecodeError, TypeError):
                    t['criteria'] = None
            del t['criteria_json']
            templates.append(t)

        return jsonify({'success': True, 'templates': templates})

    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to list templates'}}), 500
    finally:
        db.close()


@admin_bp.route('/templates/<template_id>', methods=['GET'])
def get_template(template_id):
    """Get template detail with properties."""
    db = get_db()
    try:
        template = db.execute('''
            SELECT id, name, description, status, collection_type, slug,
                   cover_image, is_public, featured_order, criteria_json,
                   auto_refresh, created_by, created_at, updated_at
            FROM property_packages
            WHERE id = ? AND collection_type IN ('template', 'featured')
        ''', (template_id,)).fetchone()

        if not template:
            return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Template not found'}}), 404

        t = dict(template)
        if t.get('criteria_json'):
            try:
                t['criteria'] = json.loads(t['criteria_json'])
            except (json.JSONDecodeError, TypeError):
                t['criteria'] = None
        t.pop('criteria_json', None)

        # Get properties
        properties = db.execute('''
            SELECT l.id, l.address, l.city, l.county, l.state, l.zip,
                   l.list_price, l.beds, l.baths, l.sqft, l.acreage,
                   l.status, l.primary_photo, l.mls_number, l.latitude, l.longitude,
                   l.days_on_market, l.property_type,
                   pkp.display_order, pkp.agent_notes, pkp.added_at
            FROM package_properties pkp
            JOIN listings l ON l.id = pkp.listing_id
            WHERE pkp.package_id = ?
            ORDER BY pkp.display_order, pkp.added_at
        ''', (template_id,)).fetchall()

        t['properties'] = [dict(p) for p in properties]

        return jsonify({'success': True, 'template': t})

    except Exception as e:
        logger.error(f"Error getting template: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to get template'}}), 500
    finally:
        db.close()


@admin_bp.route('/templates/<template_id>', methods=['PUT'])
def update_template(template_id):
    """Update template metadata."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': {'code': 'VALIDATION', 'message': 'No data provided'}}), 400

    db = get_db()
    try:
        existing = db.execute(
            'SELECT id, slug FROM property_packages WHERE id = ? AND collection_type IN (?, ?)',
            (template_id, 'template', 'featured')
        ).fetchone()
        if not existing:
            return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Template not found'}}), 404

        # Build update fields
        allowed_fields = {
            'name', 'description', 'status', 'collection_type', 'cover_image',
            'is_public', 'featured_order', 'auto_refresh', 'slug'
        }
        updates = []
        values = []
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = ?")
                values.append(data[field])

        # Handle criteria separately (serialize to JSON)
        if 'criteria' in data:
            updates.append("criteria_json = ?")
            values.append(json.dumps(data['criteria']) if data['criteria'] else None)

        # Auto-generate slug if name changed
        if 'name' in data and 'slug' not in data:
            new_slug = _slugify(data['name'])
            dup = db.execute('SELECT id FROM property_packages WHERE slug = ? AND id != ?', (new_slug, template_id)).fetchone()
            if dup:
                new_slug = f"{new_slug}-{secrets.token_hex(3)}"
            updates.append("slug = ?")
            values.append(new_slug)

        if not updates:
            return jsonify({'success': True, 'message': 'No changes'})

        updates.append("updated_at = ?")
        values.append(datetime.utcnow().isoformat())
        values.append(template_id)

        db.execute(
            f"UPDATE property_packages SET {', '.join(updates)} WHERE id = ?",
            values
        )
        db.commit()

        return jsonify({'success': True, 'message': 'Template updated'})

    except Exception as e:
        logger.error(f"Error updating template: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to update template'}}), 500
    finally:
        db.close()


@admin_bp.route('/templates/<template_id>', methods=['DELETE'])
def delete_template(template_id):
    """Delete a template and its property links."""
    db = get_db()
    try:
        existing = db.execute(
            'SELECT id FROM property_packages WHERE id = ? AND collection_type IN (?, ?)',
            (template_id, 'template', 'featured')
        ).fetchone()
        if not existing:
            return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Template not found'}}), 404

        db.execute('DELETE FROM package_properties WHERE package_id = ?', (template_id,))
        db.execute('DELETE FROM property_packages WHERE id = ?', (template_id,))
        db.commit()

        return jsonify({'success': True, 'message': 'Template deleted'})

    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to delete template'}}), 500
    finally:
        db.close()


@admin_bp.route('/templates/<template_id>/properties', methods=['POST'])
def add_template_property(template_id):
    """Add a property to a template."""
    data = request.get_json()
    if not data or not data.get('listing_id'):
        return jsonify({'success': False, 'error': {'code': 'VALIDATION', 'message': 'listing_id is required'}}), 400

    db = get_db()
    try:
        template = db.execute(
            'SELECT id FROM property_packages WHERE id = ? AND collection_type IN (?, ?)',
            (template_id, 'template', 'featured')
        ).fetchone()
        if not template:
            return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Template not found'}}), 404

        # Check listing exists
        listing = db.execute('SELECT id FROM listings WHERE id = ?', (data['listing_id'],)).fetchone()
        if not listing:
            return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Listing not found'}}), 404

        # Get next display order
        max_order = db.execute(
            'SELECT COALESCE(MAX(display_order), 0) FROM package_properties WHERE package_id = ?',
            (template_id,)
        ).fetchone()[0]

        link_id = str(uuid.uuid4())
        db.execute('''
            INSERT OR IGNORE INTO package_properties
            (id, package_id, listing_id, display_order, agent_notes, added_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            link_id, template_id, data['listing_id'],
            data.get('display_order', max_order + 1),
            data.get('agent_notes'),
            datetime.utcnow().isoformat()
        ))

        db.execute('UPDATE property_packages SET updated_at = ? WHERE id = ?',
                    (datetime.utcnow().isoformat(), template_id))
        db.commit()

        return jsonify({'success': True, 'id': link_id})

    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': {'code': 'DUPLICATE', 'message': 'Property already in template'}}), 409
    except Exception as e:
        logger.error(f"Error adding property to template: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to add property'}}), 500
    finally:
        db.close()


@admin_bp.route('/templates/<template_id>/properties/<listing_id>', methods=['DELETE'])
def remove_template_property(template_id, listing_id):
    """Remove a property from a template."""
    db = get_db()
    try:
        db.execute(
            'DELETE FROM package_properties WHERE package_id = ? AND listing_id = ?',
            (template_id, listing_id)
        )
        db.execute('UPDATE property_packages SET updated_at = ? WHERE id = ?',
                    (datetime.utcnow().isoformat(), template_id))
        db.commit()
        return jsonify({'success': True, 'message': 'Property removed'})
    except Exception as e:
        logger.error(f"Error removing property from template: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to remove property'}}), 500
    finally:
        db.close()


@admin_bp.route('/templates/<template_id>/clone', methods=['POST'])
def clone_template(template_id):
    """Clone a template for a specific buyer.

    Creates a new buyer-facing collection with all properties from the template.
    Accepts lead_id or user_id to identify the buyer.
    """
    data = request.get_json() or {}
    lead_id = data.get('lead_id')
    user_id = data.get('user_id')
    custom_name = data.get('name')

    if not lead_id and not user_id:
        return jsonify({'success': False, 'error': {'code': 'VALIDATION', 'message': 'lead_id or user_id required'}}), 400

    db = get_db()
    try:
        # Get the template
        template = db.execute('''
            SELECT id, name, description, collection_type
            FROM property_packages
            WHERE id = ? AND collection_type IN ('template', 'featured')
        ''', (template_id,)).fetchone()

        if not template:
            return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Template not found'}}), 404

        # Get template properties
        properties = db.execute('''
            SELECT listing_id, display_order, agent_notes
            FROM package_properties
            WHERE package_id = ?
            ORDER BY display_order
        ''', (template_id,)).fetchall()

        # Create new collection
        new_id = str(uuid.uuid4())
        share_token = secrets.token_urlsafe(16)
        now = datetime.utcnow().isoformat()
        name = custom_name or f"{template['name']}"

        db.execute('''
            INSERT INTO property_packages
            (id, name, description, status, lead_id, user_id,
             collection_type, share_token, derived_from_id, derived_from_type,
             created_by, created_at, updated_at)
            VALUES (?, ?, ?, 'ready', ?, ?, 'agent_package', ?, ?, 'template', 'agent', ?, ?)
        ''', (
            new_id, name, template['description'],
            lead_id, user_id, share_token,
            template_id, now, now
        ))

        # Copy all properties
        for prop in properties:
            db.execute('''
                INSERT INTO package_properties
                (id, package_id, listing_id, display_order, agent_notes, added_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                str(uuid.uuid4()), new_id, prop['listing_id'],
                prop['display_order'], prop['agent_notes'], now
            ))

        db.commit()

        return jsonify({
            'success': True,
            'collection': {
                'id': new_id,
                'name': name,
                'share_token': share_token,
                'derived_from_id': template_id,
                'derived_from_type': 'template',
                'property_count': len(properties)
            }
        }), 201

    except Exception as e:
        logger.error(f"Error cloning template: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to clone template'}}), 500
    finally:
        db.close()


# =============================================================================
# SMART COLLECTION REVIEW (Phase 4 endpoints, registered early)
# =============================================================================

@admin_bp.route('/smart-collections/queue', methods=['GET'])
def smart_collection_queue():
    """Get pending smart collections awaiting agent review."""
    db = get_db()
    try:
        rows = db.execute('''
            SELECT pp.id, pp.name, pp.description, pp.status, pp.criteria_json,
                   pp.lead_id, pp.user_id, pp.created_at,
                   l.first_name, l.last_name, l.email,
                   COUNT(pkp.id) as property_count
            FROM property_packages pp
            LEFT JOIN leads l ON l.id = pp.lead_id
            LEFT JOIN package_properties pkp ON pkp.package_id = pp.id
            WHERE pp.collection_type = 'smart' AND pp.status = 'pending_review'
            GROUP BY pp.id
            ORDER BY pp.created_at DESC
        ''').fetchall()

        queue = []
        for row in rows:
            item = dict(row)
            if item.get('criteria_json'):
                try:
                    item['criteria'] = json.loads(item['criteria_json'])
                except (json.JSONDecodeError, TypeError):
                    item['criteria'] = None
            item.pop('criteria_json', None)
            queue.append(item)

        return jsonify({'success': True, 'queue': queue})

    except Exception as e:
        logger.error(f"Error getting smart collection queue: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to get queue'}}), 500
    finally:
        db.close()


@admin_bp.route('/smart-collections/<collection_id>/review', methods=['POST'])
def review_smart_collection(collection_id):
    """Accept or reject a smart collection."""
    data = request.get_json()
    if not data or data.get('action') not in ('accept', 'reject'):
        return jsonify({'success': False, 'error': {'code': 'VALIDATION', 'message': "action must be 'accept' or 'reject'"}}), 400

    db = get_db()
    try:
        collection = db.execute(
            'SELECT id, status FROM property_packages WHERE id = ? AND collection_type = ?',
            (collection_id, 'smart')
        ).fetchone()
        if not collection:
            return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Smart collection not found'}}), 404

        now = datetime.utcnow().isoformat()
        action = data['action']

        if action == 'accept':
            new_status = 'ready'
            # Generate share token so buyer can see it
            share_token = secrets.token_urlsafe(16)
            db.execute('''
                UPDATE property_packages
                SET status = ?, share_token = ?, updated_at = ?
                WHERE id = ?
            ''', (new_status, share_token, now, collection_id))
        else:
            db.execute('''
                UPDATE property_packages
                SET status = 'archived', updated_at = ?
                WHERE id = ?
            ''', (now, collection_id))

        db.commit()
        return jsonify({'success': True, 'action': action, 'new_status': 'ready' if action == 'accept' else 'archived'})

    except Exception as e:
        logger.error(f"Error reviewing smart collection: {e}")
        return jsonify({'success': False, 'error': {'code': 'SERVER_ERROR', 'message': 'Failed to review collection'}}), 500
    finally:
        db.close()
