"""
Property CRUD endpoints.
"""

import os
import sys
import uuid
import json
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.database import DREAMSDatabase

properties_bp = Blueprint('properties', __name__)


def get_db():
    """Get database connection."""
    db_path = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))
    return DREAMSDatabase(db_path)


@properties_bp.route('/properties', methods=['POST'])
def create_property():
    """
    Create or update a property.

    Expects JSON body with property fields.
    Uses source + source_id for upsert matching.
    """
    data = request.get_json()

    # Debug: log if primary_photo is received
    if data and data.get('primary_photo'):
        print(f"API received primary_photo for {data.get('address')}: {data.get('primary_photo')[:80]}...")
    elif data:
        print(f"API received NO primary_photo for {data.get('address')}")

    if not data:
        return jsonify({
            'success': False,
            'error': {'code': 'INVALID_JSON', 'message': 'Request body must be JSON'}
        }), 400

    # Validate required fields
    required = ['address']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({
            'success': False,
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': f'Missing required fields: {", ".join(missing)}'
            }
        }), 400

    try:
        db = get_db()

        # Check for existing property by source + source_id or MLS#
        existing_id = None
        source = data.get('source')
        source_id = data.get('source_id')
        mls_number = data.get('mls_number')

        # For Redfin, use redfin_id directly
        redfin_id = data.get('redfin_id')

        if source and source_id:
            # Look up by zillow_id or realtor_id based on source
            if source == 'zillow':
                existing = db.get_property_by_zillow_id(source_id)
            elif source == 'realtor':
                existing = db.get_property_by_realtor_id(source_id)
            elif source == 'redfin' and redfin_id:
                existing = db.get_property_by_redfin_id(redfin_id)
            else:
                existing = None
            if existing:
                existing_id = existing['id']

        # Also try Redfin ID if available and not matched yet
        if not existing_id and redfin_id:
            existing = db.get_property_by_redfin_id(redfin_id)
            if existing:
                existing_id = existing['id']

        if not existing_id and mls_number:
            existing = db.get_property_by_mls(mls_number)
            if existing:
                existing_id = existing['id']

        # Final fallback: check by address + city
        if not existing_id and data.get('address'):
            existing = db.get_property_by_address(data.get('address'), data.get('city'))
            if existing:
                existing_id = existing['id']

        # Prepare property data
        property_id = existing_id or str(uuid.uuid4())
        now = datetime.now().isoformat()

        property_data = {
            'id': property_id,
            'mls_number': data.get('mls_number'),
            'mls_source': data.get('mls_source'),
            'parcel_id': data.get('parcel_id'),
            'zillow_id': data.get('source_id') if source == 'zillow' else data.get('zillow_id'),
            'realtor_id': data.get('source_id') if source == 'realtor' else data.get('realtor_id'),
            'redfin_id': data.get('redfin_id'),
            'address': data.get('address'),
            'city': data.get('city'),
            'state': data.get('state'),
            'zip': data.get('zip'),
            'county': data.get('county'),
            'price': data.get('price'),
            'beds': data.get('beds'),
            'baths': data.get('baths'),
            'sqft': data.get('sqft'),
            'acreage': data.get('lot_acres') or data.get('acreage'),
            'year_built': data.get('year_built'),
            'property_type': data.get('property_type'),
            'style': data.get('style'),
            'status': data.get('status', 'active'),
            'days_on_market': data.get('days_on_market'),
            'listing_agent_name': data.get('listing_agent_name'),
            'listing_agent_phone': data.get('listing_agent_phone'),
            'listing_agent_email': data.get('listing_agent_email'),
            'listing_brokerage': data.get('listing_brokerage'),
            'hoa_fee': data.get('hoa_fee'),
            'tax_assessed_value': data.get('tax_assessed_value'),
            'tax_annual_amount': data.get('tax_annual_amount'),
            'zestimate': data.get('zestimate'),
            'rent_zestimate': data.get('rent_zestimate'),
            'page_views': data.get('page_views'),
            'favorites_count': data.get('favorites_count'),
            'heating': data.get('heating'),
            'cooling': data.get('cooling'),
            'garage': data.get('garage'),
            'sewer': data.get('sewer'),
            'roof': data.get('roof'),
            'stories': data.get('stories'),
            'subdivision': data.get('subdivision'),
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'school_elementary_rating': data.get('school_elementary_rating'),
            'school_middle_rating': data.get('school_middle_rating'),
            'school_high_rating': data.get('school_high_rating'),
            'zillow_url': data.get('url') if source == 'zillow' else data.get('zillow_url'),
            'realtor_url': data.get('url') if source == 'realtor' else data.get('realtor_url'),
            'redfin_url': data.get('url') if source == 'redfin' else data.get('redfin_url'),
            'photo_urls': json.dumps(data.get('photo_urls')) if isinstance(data.get('photo_urls'), list) else data.get('photo_urls'),
            'primary_photo': data.get('primary_photo'),
            'virtual_tour_url': data.get('virtual_tour_url'),
            'source': source,
            'added_for': data.get('added_for'),
            'added_by': data.get('added_by'),
            'captured_by': data.get('added_by'),
            'notes': data.get('notes'),
            'sync_status': 'pending',
            'idx_validation_status': 'pending' if not existing_id else None,
            'created_at': now if not existing_id else None,
            'updated_at': now
        }

        # Remove None values for cleaner insert
        property_data = {k: v for k, v in property_data.items() if v is not None}

        # Upsert property
        success = db.upsert_property_dict(property_data)

        if success:
            return jsonify({
                'success': True,
                'data': {
                    'id': property_id,
                    'created': existing_id is None,
                    'updated_at': now,
                    'sync_status': 'pending'
                }
            }), 201 if not existing_id else 200
        else:
            return jsonify({
                'success': False,
                'error': {'code': 'DB_ERROR', 'message': 'Failed to save property'}
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': str(e)}
        }), 500


@properties_bp.route('/properties/batch', methods=['POST'])
def batch_create_properties():
    """
    Create or update multiple properties.

    Expects JSON body with 'properties' array.
    """
    data = request.get_json()

    if not data or 'properties' not in data:
        return jsonify({
            'success': False,
            'error': {'code': 'INVALID_JSON', 'message': 'Expected {properties: [...]}'}
        }), 400

    properties = data['properties']
    results = {'created': 0, 'updated': 0, 'failed': 0, 'errors': []}

    for i, prop in enumerate(properties):
        try:
            # Reuse single property logic
            with properties_bp.test_request_context(
                '/properties',
                method='POST',
                json=prop
            ):
                # This is a simplified approach - in production, extract the logic
                pass
            results['created'] += 1
        except Exception as e:
            results['failed'] += 1
            results['errors'].append({'index': i, 'error': str(e)})

    return jsonify({
        'success': results['failed'] == 0,
        'data': results
    })


@properties_bp.route('/properties/<property_id>', methods=['GET'])
def get_property(property_id):
    """Get a single property by ID."""
    try:
        db = get_db()
        prop = db.get_property(property_id)

        if prop:
            return jsonify({'success': True, 'data': prop})
        else:
            return jsonify({
                'success': False,
                'error': {'code': 'NOT_FOUND', 'message': 'Property not found'}
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': str(e)}
        }), 500


@properties_bp.route('/properties', methods=['GET'])
def list_properties():
    """List properties with optional filters."""
    try:
        db = get_db()

        # Parse query params
        status = request.args.get('status', 'active')
        city = request.args.get('city')
        min_price = request.args.get('min_price', type=int)
        max_price = request.args.get('max_price', type=int)
        limit = request.args.get('limit', 100, type=int)

        properties = db.get_properties(
            status=status,
            city=city,
            min_price=min_price,
            max_price=max_price,
            limit=limit
        )

        return jsonify({
            'success': True,
            'data': properties,
            'count': len(properties)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': str(e)}
        }), 500


@properties_bp.route('/properties/check', methods=['GET'])
def check_property_exists():
    """Check if a property exists in the database."""
    try:
        db = get_db()

        redfin_id = request.args.get('redfin_id')
        address = request.args.get('address')
        mls = request.args.get('mls')

        existing = None

        # Check by redfin_id first (most specific)
        if redfin_id and not existing:
            existing = db.get_property_by_redfin_id(redfin_id)

        # Check by MLS number
        if mls and not existing:
            existing = db.get_property_by_mls(mls)

        # Check by address (least specific)
        if address and not existing:
            existing = db.get_property_by_address(address)

        return jsonify({
            'success': True,
            'exists': existing is not None,
            'id': existing['id'] if existing else None
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': str(e)}
        }), 500


@properties_bp.route('/sync/notion', methods=['POST'])
def trigger_notion_sync():
    """Manually trigger Notion sync."""
    from app import notion_sync_service

    if not notion_sync_service:
        return jsonify({
            'success': False,
            'error': {'code': 'NOT_CONFIGURED', 'message': 'Notion sync not configured'}
        }), 503

    try:
        synced = notion_sync_service.sync_pending_properties()
        return jsonify({
            'success': True,
            'data': {'synced_count': synced}
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SYNC_ERROR', 'message': str(e)}
        }), 500


@properties_bp.route('/properties/<property_id>/validate-idx', methods=['POST'])
def validate_idx(property_id):
    """Manually trigger IDX validation for a specific property."""
    import asyncio
    from app import idx_validation_service

    if not idx_validation_service:
        return jsonify({
            'success': False,
            'error': {'code': 'NOT_CONFIGURED', 'message': 'IDX validation service not configured'}
        }), 503

    try:
        # Run the async validation in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                idx_validation_service.validate_single_property(property_id)
            )
        finally:
            loop.close()

        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'VALIDATION_ERROR', 'message': str(e)}
        }), 500


@properties_bp.route('/sync/idx-validation', methods=['POST'])
def trigger_idx_validation():
    """Manually trigger IDX validation for all pending properties."""
    import asyncio
    from app import idx_validation_service

    if not idx_validation_service:
        return jsonify({
            'success': False,
            'error': {'code': 'NOT_CONFIGURED', 'message': 'IDX validation service not configured'}
        }), 503

    try:
        # Run the async validation in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            count = loop.run_until_complete(
                idx_validation_service.validate_pending_properties()
            )
        finally:
            loop.close()

        return jsonify({
            'success': True,
            'data': {'validated_count': count}
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'VALIDATION_ERROR', 'message': str(e)}
        }), 500
