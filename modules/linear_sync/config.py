"""Configuration for Linear Sync module."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')


class Config:
    """Configuration settings for Linear sync."""

    def __init__(self):
        # Environment
        self.ENV = os.getenv('LINEAR_SYNC_ENV', 'dev')

        # Linear API
        self.LINEAR_API_KEY = os.getenv('LINEAR_API_KEY', '')
        self.LINEAR_API_URL = 'https://api.linear.app/graphql'

        # FUB API (reuse from task_sync)
        self.FUB_API_KEY = os.getenv('FUB_API_KEY', '')
        self.FUB_BASE_URL = os.getenv('FUB_BASE_URL', 'https://api.followupboss.com/v1')
        self.FUB_SYSTEM_NAME = os.getenv('FUB_SYSTEM_NAME', 'myDREAMS')
        self.FUB_SYSTEM_KEY = os.getenv('FUB_SYSTEM_KEY', '')

        # Poll intervals (seconds)
        self.LINEAR_POLL_INTERVAL = int(os.getenv('LINEAR_POLL_INTERVAL', '30'))
        self.FUB_POLL_INTERVAL = int(os.getenv('FUB_POLL_INTERVAL', '30'))
        self.DEAL_CACHE_REFRESH = int(os.getenv('DEAL_CACHE_REFRESH', '300'))

        # Database
        self.DB_PATH = PROJECT_ROOT / 'data' / 'linear_sync.db'

        # API server (for webhooks, optional)
        self.API_HOST = os.getenv('LINEAR_SYNC_API_HOST', '127.0.0.1')
        self.API_PORT = int(os.getenv('LINEAR_SYNC_API_PORT', '8200'))

        # Logging
        self.LOG_LEVEL = os.getenv('LINEAR_SYNC_LOG_LEVEL', 'INFO')

        # Team IDs (set after setup)
        self.DEVELOP_TEAM_ID = os.getenv('LINEAR_DEVELOP_TEAM_ID', '')
        self.TRANSACT_TEAM_ID = os.getenv('LINEAR_TRANSACT_TEAM_ID', '')
        self.GENERAL_TEAM_ID = os.getenv('LINEAR_GENERAL_TEAM_ID', '')

        # Label IDs (set after setup)
        self.FUB_SYNCED_LABEL_ID = os.getenv('LINEAR_FUB_SYNCED_LABEL_ID', '')

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []

        if not self.LINEAR_API_KEY:
            errors.append('LINEAR_API_KEY not set')

        if not self.FUB_API_KEY:
            errors.append('FUB_API_KEY not set')

        return errors

    def is_configured(self) -> bool:
        """Check if basic configuration is present."""
        return bool(self.LINEAR_API_KEY and self.FUB_API_KEY)

    def teams_configured(self) -> bool:
        """Check if Linear teams are configured."""
        return bool(self.DEVELOP_TEAM_ID and self.TRANSACT_TEAM_ID and self.GENERAL_TEAM_ID)


# Module-level singleton
config = Config()
