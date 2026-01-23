"""
Automation Configuration

Centralized settings for all automation features.
Settings can be configured via:
1. Database (system_settings table) - preferred for runtime changes
2. Environment variables - fallback
3. Defaults - hardcoded fallback
"""

import os
import sqlite3
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
TEMPLATES_DIR = Path(__file__).parent / 'templates'

# Database
DATABASE_PATH = os.getenv('DREAMS_DB_PATH', str(DATA_DIR / 'dreams.db'))


def get_db_setting(key: str, default: Any = None) -> Any:
    """
    Get a setting from the database with fallback to environment variable and default.

    Priority order:
    1. Database system_settings table
    2. Environment variable (uppercase key with underscores)
    3. Provided default value

    Args:
        key: Setting key (e.g., 'new_listing_match_threshold')
        default: Default value if not found anywhere

    Returns:
        Setting value converted to appropriate type
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT value, value_type FROM system_settings WHERE key = ?',
            (key,)
        ).fetchone()
        conn.close()

        if row:
            value = row['value']
            value_type = row['value_type']

            # Convert based on type
            if value_type == 'integer':
                return int(value)
            elif value_type == 'float':
                return float(value)
            elif value_type == 'boolean':
                return value.lower() in ('true', '1', 'yes')
            elif value_type == 'json':
                import json
                return json.loads(value)
            else:
                return value
    except Exception:
        pass  # Fall through to env var / default

    # Try environment variable
    env_key = key.upper()
    env_value = os.getenv(env_key)
    if env_value is not None:
        # Try to convert based on default type
        if isinstance(default, bool):
            return env_value.lower() in ('true', '1', 'yes')
        elif isinstance(default, int):
            return int(env_value)
        elif isinstance(default, float):
            return float(env_value)
        return env_value

    return default

# SMTP Configuration
SMTP_ENABLED = os.getenv('SMTP_ENABLED', 'true').lower() == 'true'
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
EMAIL_FROM_NAME = os.getenv('EMAIL_FROM_NAME', 'DREAMS Automation')

# Agent branding for PDFs
AGENT_NAME = os.getenv('AGENT_NAME', 'Joseph "Eugy" Williams')
AGENT_EMAIL = os.getenv('AGENT_EMAIL', 'eugy@jontharp.com')
AGENT_PHONE = os.getenv('AGENT_PHONE', '828-808-5373')
BROKERAGE_NAME = os.getenv('BROKERAGE_NAME', 'Keller Williams - Jon Tharp Homes')
AGENT_HEADSHOT_URL = os.getenv('AGENT_HEADSHOT_URL', '')
BROKERAGE_LOGO_URL = os.getenv('BROKERAGE_LOGO_URL', '')

# Feature-specific settings
WEEKLY_SUMMARY_RECIPIENT = os.getenv('WEEKLY_SUMMARY_RECIPIENT', SMTP_USERNAME)
MONTHLY_REPORT_RECIPIENT = os.getenv('MONTHLY_REPORT_RECIPIENT', SMTP_USERNAME)

# Matching thresholds
NEW_LISTING_MATCH_THRESHOLD = int(os.getenv('NEW_LISTING_MATCH_THRESHOLD', '60'))
ALERT_LOOKBACK_HOURS = int(os.getenv('ALERT_LOOKBACK_HOURS', '24'))

# Counties to track (WNC focus)
# Can be overridden via TRACKED_COUNTIES env var (comma-separated)
_default_counties = [
    # Original WNC counties
    'Buncombe',
    'Henderson',
    'Madison',
    'McDowell',
    'Haywood',
    'Transylvania',
    'Polk',
    'Rutherford',
    'Yancey',
    'Mitchell',
    # Additional counties from property data
    'Macon',
    'Macon County',
    'Jackson',
    'Jackson County',
    'Cherokee',
    'Cherokee County',
    'Swain',
    'Swain County',
    'Clay',
    'Clay County',
    'Graham',
    'Graham County',
    'Towns',
    'Towns County',
    'Haywood County',
]
_env_counties = os.getenv('TRACKED_COUNTIES', '')
TRACKED_COUNTIES = [c.strip() for c in _env_counties.split(',') if c.strip()] if _env_counties else _default_counties

# Logging
LOG_LEVEL = os.getenv('AUTOMATION_LOG_LEVEL', 'INFO')
