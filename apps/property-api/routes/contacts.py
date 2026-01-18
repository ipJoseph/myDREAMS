"""
Contacts API endpoints for the Property API.

Provides REST API for contact/lead management, synced from FUB.
"""

import os
import sys
from pathlib import Path
from flask import Blueprint, jsonify, request

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.database import DREAMSDatabase

contacts_bp = Blueprint('contacts', __name__)

# Database path
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))


def get_db():
    """Get database instance."""
    return DREAMSDatabase(DB_PATH)


@contacts_bp.route('/contacts', methods=['GET'])
def get_contacts():
    """
    Get contacts with optional filters.

    Query params:
        min_priority: Minimum priority score (default: 0)
        min_heat: Minimum heat score (default: 0)
        stage: Filter by stage
        limit: Max results (default: 100)
    """
    db = get_db()

    min_priority = request.args.get('min_priority', 0, type=float)
    min_heat = request.args.get('min_heat', 0, type=float)
    stage = request.args.get('stage')
    limit = request.args.get('limit', 100, type=int)

    contacts = db.get_contacts_by_priority(min_priority=min_priority, limit=limit)

    # Apply additional filters
    if min_heat > 0:
        contacts = [c for c in contacts if (c.get('heat_score') or 0) >= min_heat]
    if stage:
        contacts = [c for c in contacts if c.get('stage') == stage]

    return jsonify({
        'success': True,
        'count': len(contacts),
        'contacts': contacts
    })


@contacts_bp.route('/contacts/hot', methods=['GET'])
def get_hot_contacts():
    """
    Get hot contacts (high heat scores).

    Query params:
        min_heat: Minimum heat score (default: 50)
        limit: Max results (default: 50)
    """
    db = get_db()

    min_heat = request.args.get('min_heat', 50.0, type=float)
    limit = request.args.get('limit', 50, type=int)

    contacts = db.get_hot_contacts(min_heat=min_heat, limit=limit)

    return jsonify({
        'success': True,
        'count': len(contacts),
        'contacts': contacts
    })


@contacts_bp.route('/contacts/stats', methods=['GET'])
def get_contact_stats():
    """Get aggregate contact statistics."""
    db = get_db()
    stats = db.get_contact_stats()

    return jsonify({
        'success': True,
        'stats': stats
    })


@contacts_bp.route('/contacts/<contact_id>', methods=['GET'])
def get_contact(contact_id):
    """Get a single contact by ID."""
    db = get_db()
    contact = db.get_lead(contact_id)

    if not contact:
        return jsonify({
            'success': False,
            'error': {'code': 'NOT_FOUND', 'message': 'Contact not found'}
        }), 404

    return jsonify({
        'success': True,
        'contact': contact
    })


@contacts_bp.route('/contacts/fub/<fub_id>', methods=['GET'])
def get_contact_by_fub(fub_id):
    """Get a contact by Follow Up Boss ID."""
    db = get_db()
    contact = db.get_contact_by_fub_id(fub_id)

    if not contact:
        return jsonify({
            'success': False,
            'error': {'code': 'NOT_FOUND', 'message': 'Contact not found'}
        }), 404

    return jsonify({
        'success': True,
        'contact': contact
    })


@contacts_bp.route('/contacts', methods=['POST'])
def upsert_contact():
    """
    Create or update a contact.

    Body: Contact data dict
    """
    db = get_db()
    data = request.get_json()

    if not data:
        return jsonify({
            'success': False,
            'error': {'code': 'BAD_REQUEST', 'message': 'No data provided'}
        }), 400

    try:
        db.upsert_contact_dict(data)
        return jsonify({
            'success': True,
            'message': 'Contact saved'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': str(e)}
        }), 500


@contacts_bp.route('/contacts/bulk', methods=['POST'])
def bulk_upsert_contacts():
    """
    Bulk create/update contacts (for FUB sync).

    Body: { "contacts": [...] }
    """
    db = get_db()
    data = request.get_json()

    if not data or 'contacts' not in data:
        return jsonify({
            'success': False,
            'error': {'code': 'BAD_REQUEST', 'message': 'No contacts provided'}
        }), 400

    contacts = data['contacts']
    success_count = 0
    error_count = 0

    for contact in contacts:
        try:
            db.upsert_contact_dict(contact)
            success_count += 1
        except Exception as e:
            error_count += 1
            print(f"Error upserting contact: {e}")

    return jsonify({
        'success': True,
        'message': f'Processed {len(contacts)} contacts',
        'success_count': success_count,
        'error_count': error_count
    })


@contacts_bp.route('/contacts/<contact_id>/properties', methods=['GET'])
def get_contact_properties(contact_id):
    """
    Get properties linked to a contact.

    Query params:
        relationship: Filter by relationship type (saved, viewed, shared, matched)
    """
    db = get_db()
    relationship = request.args.get('relationship')

    properties = db.get_contact_properties(contact_id, relationship=relationship)

    return jsonify({
        'success': True,
        'count': len(properties),
        'properties': properties
    })


@contacts_bp.route('/contacts/<contact_id>/properties/<property_id>', methods=['POST'])
def link_contact_property(contact_id, property_id):
    """
    Link a contact to a property.

    Body: { "relationship": "saved", "match_score": 85.5, "notes": "..." }
    """
    db = get_db()
    data = request.get_json() or {}

    relationship = data.get('relationship', 'saved')
    match_score = data.get('match_score')
    notes = data.get('notes')

    try:
        db.upsert_contact_property(
            contact_id=contact_id,
            property_id=property_id,
            relationship=relationship,
            match_score=match_score,
            notes=notes
        )
        return jsonify({
            'success': True,
            'message': 'Property linked to contact'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': str(e)}
        }), 500


@contacts_bp.route('/properties/<property_id>/contacts', methods=['GET'])
def get_property_contacts(property_id):
    """
    Get contacts linked to a property.

    Query params:
        relationship: Filter by relationship type
    """
    db = get_db()
    relationship = request.args.get('relationship')

    contacts = db.get_property_contacts(property_id, relationship=relationship)

    return jsonify({
        'success': True,
        'count': len(contacts),
        'contacts': contacts
    })
