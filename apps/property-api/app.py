"""
Property API Server

Flask server that receives property data from the Chrome extension
and stores it in SQLite (canonical store), then syncs to Notion.
"""

import os
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from routes.properties import properties_bp
from routes.health import health_bp
from services.notion_sync_service import NotionSyncService

# Load environment variables
load_dotenv(PROJECT_ROOT / '.env')

app = Flask(__name__)

# Enable CORS for Chrome extension
# Allow all origins since we're running locally - Chrome extension IDs vary
CORS(app, resources={r"/*": {"origins": "*"}})

# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(properties_bp, url_prefix='/api/v1')

# Initialize services
notion_sync_service = None

def init_services():
    """Initialize background services."""
    global notion_sync_service

    notion_api_key = os.getenv('NOTION_API_KEY')
    notion_db_id = os.getenv('NOTION_PROPERTIES_DB_ID')
    db_path = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

    if notion_api_key and notion_db_id:
        from src.core.database import DREAMSDatabase
        db = DREAMSDatabase(db_path)
        notion_sync_service = NotionSyncService(
            notion_api_key=notion_api_key,
            database_id=notion_db_id,
            db=db
        )
        notion_sync_service.start_background_sync(interval_seconds=60)
        print(f"Notion sync service started (every 60s)")
    else:
        print("Warning: Notion credentials not configured, sync disabled")


@app.route('/')
def index():
    return jsonify({
        'name': 'DREAMS Property API',
        'version': '1.0.0',
        'status': 'running'
    })


if __name__ == '__main__':
    init_services()
    # Disable reloader to prevent duplicate background sync threads
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
