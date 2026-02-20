"""
Property API Server

Flask server that receives property data from the Chrome extension
and stores it in SQLite (canonical store), then syncs to Notion.
"""

import os
import sys
from functools import wraps
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

from routes.properties import properties_bp
from routes.health import health_bp
from routes.contacts import contacts_bp
from routes.public import public_bp
from services.notion_sync_service import NotionSyncService
from services.idx_validation_service import IDXValidationService

# Load environment variables
load_dotenv(PROJECT_ROOT / '.env')

app = Flask(__name__)

# Enable CORS for Chrome extension and dashboard
ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', 'https://app.wncmountain.homes,http://localhost:5001').split(',')
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

# API Key Authentication
API_KEY = os.getenv('DREAMS_API_KEY')
DREAMS_ENV = os.getenv('DREAMS_ENV', 'dev').lower()

if not API_KEY:
    import logging as _logging
    _auth_logger = _logging.getLogger('dreams.auth')
    if DREAMS_ENV == 'prd':
        _auth_logger.critical("DREAMS_API_KEY is not set! API is running WITHOUT authentication in PRODUCTION.")
    else:
        _auth_logger.warning("DREAMS_API_KEY is not set. API authentication is disabled (dev mode).")


def require_api_key(f):
    """Decorator to require API key authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip auth if no API key is configured (local development)
        if not API_KEY:
            return f(*args, **kwargs)

        # Check X-API-Key header
        provided_key = request.headers.get('X-API-Key')
        if not provided_key or provided_key != API_KEY:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'UNAUTHORIZED',
                    'message': 'Invalid or missing API key'
                }
            }), 401

        return f(*args, **kwargs)
    return decorated_function


@app.before_request
def check_api_key():
    """Check API key for all /api/* routes (except public endpoints)."""
    # Skip auth for non-API routes (health, index)
    if not request.path.startswith('/api/'):
        return None

    # Public endpoints require no authentication
    if request.path.startswith('/api/public/'):
        return None

    # Skip auth if no API key is configured (local development)
    if not API_KEY:
        return None

    # Check X-API-Key header
    provided_key = request.headers.get('X-API-Key')
    if not provided_key or provided_key != API_KEY:
        return jsonify({
            'success': False,
            'error': {
                'code': 'UNAUTHORIZED',
                'message': 'Invalid or missing API key'
            }
        }), 401

    return None

# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(properties_bp, url_prefix='/api/v1')
app.register_blueprint(contacts_bp, url_prefix='/api/v1')
app.register_blueprint(public_bp, url_prefix='/api/public')

# Initialize services
notion_sync_service = None
idx_validation_service = None

def init_services():
    """Initialize background services."""
    global notion_sync_service
    global idx_validation_service

    notion_api_key = os.getenv('NOTION_API_KEY')
    notion_db_id = os.getenv('NOTION_PROPERTIES_DB_ID')
    db_path = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

    from src.core.database import DREAMSDatabase
    db = DREAMSDatabase(db_path)

    if notion_api_key and notion_db_id:
        notion_sync_service = NotionSyncService(
            notion_api_key=notion_api_key,
            database_id=notion_db_id,
            db=db
        )
        notion_sync_service.start_background_sync(interval_seconds=60)
        print(f"Notion sync service started (every 60s)")
    else:
        print("Warning: Notion credentials not configured, sync disabled")

    # Initialize IDX validation service
    idx_validation_service = IDXValidationService(db=db)
    idx_validation_service.start_background_validation(interval_seconds=300)  # Every 5 minutes
    print(f"IDX validation service started (every 5 min)")


@app.route('/')
def index():
    return jsonify({
        'name': 'DREAMS Property API',
        'version': '1.0.0',
        'status': 'running'
    })


# Start background services when running under gunicorn in production.
# gunicorn with preload_app=True imports this module but skips __main__,
# so we need a module-level trigger for the daemon threads.
if DREAMS_ENV == 'prd' and __name__ != '__main__':
    init_services()


if __name__ == '__main__':
    init_services()
    # Disable reloader to prevent duplicate background sync threads
    is_debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=is_debug, use_reloader=False)
