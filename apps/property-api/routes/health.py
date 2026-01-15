"""
Health check endpoints for the Property API.
"""

from flask import Blueprint, jsonify
import os

health_bp = Blueprint('health', __name__)


@health_bp.route('/health')
def health_check():
    """Basic health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'property-api'
    })


@health_bp.route('/health/notion')
def notion_health():
    """Check Notion connection status."""
    notion_key = os.getenv('NOTION_API_KEY')
    notion_db = os.getenv('NOTION_PROPERTIES_DB_ID')

    if not notion_key or not notion_db:
        return jsonify({
            'status': 'unconfigured',
            'message': 'Notion credentials not set'
        }), 503

    # Could add actual Notion API ping here
    return jsonify({
        'status': 'configured',
        'database_id': notion_db[:8] + '...'
    })
