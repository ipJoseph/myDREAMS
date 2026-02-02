"""
Configuration management for Task Sync module.

Loads environment variables and provides typed config access.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Find project root and load .env
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')


class Config:
    """Task sync configuration."""

    # Environment
    TASK_SYNC_ENV: str = os.getenv('TASK_SYNC_ENV', 'dev')

    # Todoist
    TODOIST_API_TOKEN: str = os.getenv('TODOIST_API_TOKEN', '')
    TODOIST_USE_WEBHOOKS: bool = os.getenv('TODOIST_USE_WEBHOOKS', 'false').lower() == 'true'
    TODOIST_WEBHOOK_SECRET: str = os.getenv('TODOIST_WEBHOOK_SECRET', '')

    # Follow Up Boss
    FUB_API_KEY: str = os.getenv('FUB_API_KEY', '')
    FUB_BASE_URL: str = os.getenv('FUB_BASE_URL', 'https://api.followupboss.com/v1')
    FUB_SYSTEM_NAME: str = os.getenv('FUB_SYSTEM_NAME', 'myDREAMS')
    FUB_SYSTEM_KEY: str = os.getenv('FUB_SYSTEM_KEY', '')

    # Sync intervals (seconds)
    FUB_POLL_INTERVAL: int = int(os.getenv('FUB_POLL_INTERVAL', '30'))
    TODOIST_POLL_INTERVAL: int = int(os.getenv('TODOIST_POLL_INTERVAL', '30'))
    DEAL_CACHE_REFRESH: int = int(os.getenv('DEAL_CACHE_REFRESH', '300'))

    # Database
    DB_PATH: Path = PROJECT_ROOT / 'data' / 'task_sync.db'

    # API Server
    API_HOST: str = os.getenv('TASK_SYNC_API_HOST', '127.0.0.1')
    API_PORT: int = int(os.getenv('TASK_SYNC_API_PORT', '8100'))

    # Logging (set TASK_SYNC_LOG_LEVEL=DEBUG for verbose output)
    LOG_LEVEL: str = os.getenv('TASK_SYNC_LOG_LEVEL', 'INFO')

    @classmethod
    def is_dev(cls) -> bool:
        return cls.TASK_SYNC_ENV == 'dev'

    @classmethod
    def is_prod(cls) -> bool:
        return cls.TASK_SYNC_ENV == 'prod'

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration. Returns list of errors."""
        errors = []

        if not cls.FUB_API_KEY:
            errors.append("FUB_API_KEY is required")

        if not cls.TODOIST_API_TOKEN:
            errors.append("TODOIST_API_TOKEN is required")

        if cls.TODOIST_USE_WEBHOOKS and not cls.TODOIST_WEBHOOK_SECRET:
            errors.append("TODOIST_WEBHOOK_SECRET required when using webhooks")

        return errors


# Singleton instance
config = Config()
