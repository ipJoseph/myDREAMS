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
from routes.public_writes import public_writes_bp
from routes.user import user_bp
from routes.admin import admin_bp

# Flask-Limiter is optional: if it's not installed, we log a warning and
# the public write endpoints run without per-IP rate limiting. The endpoint
# still has validation, Turnstile (if configured), and logging — this just
# removes one defense layer. We prefer degraded-but-running over hard-fail.
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _LIMITER_AVAILABLE = True
except ImportError:
    _LIMITER_AVAILABLE = False
    import logging as _logging
    _logging.getLogger('dreams.limiter').warning(
        "flask-limiter not installed; /api/public write endpoints will run without rate limiting. "
        "Install with: pip install flask-limiter"
    )
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

    # User endpoints handle their own auth (JWT-based)
    if request.path.startswith('/api/user/'):
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
app.register_blueprint(public_writes_bp, url_prefix='/api/public')
app.register_blueprint(user_bp, url_prefix='/api/user')
app.register_blueprint(admin_bp, url_prefix='/api/v1/admin')

# Rate limiting for the public write endpoints (unauthenticated).
# Only the contact form endpoint is limited — other /api/public/* reads
# are not rate-limited by this limiter.
#
# NOTE: Flask-Limiter's `limiter.limit(...)(func)` returns a wrapped function
# but does NOT mutate app.view_functions — we have to do that explicitly so
# Flask's router actually calls the limited version.
if _LIMITER_AVAILABLE:
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[],  # No global default — opt in per-route
        storage_uri="memory://",  # Good enough for single-process; swap to redis:// if we scale out
        headers_enabled=True,  # Send X-RateLimit-* headers on responses
    )
    _contact_endpoint = 'public_writes.create_public_contact'
    _original_view = app.view_functions[_contact_endpoint]
    _limited_view = limiter.limit("10 per hour")(_original_view)
    app.view_functions[_contact_endpoint] = _limited_view

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

    if notion_api_key and notion_db_id and not os.getenv('DISABLE_NOTION_SYNC'):
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
