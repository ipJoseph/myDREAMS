"""
Health check endpoints for the Property API.
"""

import os
import sys
from pathlib import Path

from flask import Blueprint, jsonify

# Allow importing from project root when this blueprint is loaded.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

health_bp = Blueprint('health', __name__)


@health_bp.route('/health')
def health_check():
    """Basic health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'property-api'
    })


@health_bp.route('/health/db')
def db_health():
    """Report which database backend is actually in use + freshness.

    Answers the question that silently went unanswered for days on PRD:
    "Are we actually reading/writing PostgreSQL?"
    """
    from src.core.pg_adapter import active_backend, get_db
    backend = active_backend()
    out = {
        'backend': backend,
        'database_url_set': bool(os.getenv('DATABASE_URL', '').strip()),
    }
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT COUNT(*) AS n, MAX(captured_at) AS max_captured FROM listings"
        ).fetchone()
        d = dict(row) if row else {}
        out['listings_count'] = d.get('n')
        out['max_captured_at'] = str(d.get('max_captured')) if d.get('max_captured') else None
        try:
            conn.close()
        except Exception:
            pass
    except Exception as e:
        out['error'] = type(e).__name__
    return jsonify(out)


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
