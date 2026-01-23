"""
Automation Configuration

Centralized settings for all automation features.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
TEMPLATES_DIR = Path(__file__).parent / 'templates'

# Database
DATABASE_PATH = os.getenv('DREAMS_DB_PATH', str(DATA_DIR / 'dreams.db'))

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
TRACKED_COUNTIES = [
    'Buncombe',
    'Henderson',
    'Madison',
    'McDowell',
    'Haywood',
    'Transylvania',
    'Polk',
    'Rutherford',
    'Yancey',
    'Mitchell'
]

# Logging
LOG_LEVEL = os.getenv('AUTOMATION_LOG_LEVEL', 'INFO')
