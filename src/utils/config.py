"""
Configuration Management

Load and validate configuration from YAML and environment variables.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml
from dotenv import load_dotenv


def load_config(
    config_path: Optional[Union[str, Path]] = None,
    env_path: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    Load configuration from YAML file and environment variables.
    
    Environment variables override YAML values.
    
    Args:
        config_path: Path to YAML config file (default: config/config.yaml)
        env_path: Path to .env file (default: config/.env)
        
    Returns:
        Configuration dictionary
    """
    # Determine paths
    base_dir = Path(__file__).parent.parent.parent.parent
    
    if env_path is None:
        env_path = base_dir / "config" / ".env"
    else:
        env_path = Path(env_path)
        
    if config_path is None:
        config_path = base_dir / "config" / "config.yaml"
    else:
        config_path = Path(config_path)
    
    # Load environment variables
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # Try loading from repo root .env (backward compatibility)
        root_env = base_dir / ".env"
        if root_env.exists():
            load_dotenv(root_env)
    
    # Load YAML config
    config = {}
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
    
    # Expand environment variable references in config
    config = _expand_env_vars(config)
    
    # Override with direct environment variables
    config = _apply_env_overrides(config)
    
    # Ensure defaults
    config.setdefault('database', {})
    config['database'].setdefault('path', './data/dreams.db')
    
    return config


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand ${VAR} references in config values."""
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
        var_name = obj[2:-1]
        return os.environ.get(var_name, obj)
    return obj


def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply direct environment variable overrides."""
    
    # Database
    if os.environ.get('DREAMS_DB_PATH'):
        config.setdefault('database', {})['path'] = os.environ['DREAMS_DB_PATH']
    
    # Logging
    if os.environ.get('DREAMS_LOG_LEVEL'):
        config.setdefault('logging', {})['level'] = os.environ['DREAMS_LOG_LEVEL']
    
    return config


def get_db_path(config: Dict[str, Any]) -> str:
    """Get database path from config."""
    return config.get('database', {}).get('path', './data/dreams.db')


def get_api_key(service: str) -> Optional[str]:
    """Get API key for a service from environment."""
    key_map = {
        'fub': 'FUB_API_KEY',
        'followupboss': 'FUB_API_KEY',
        'notion': 'NOTION_API_KEY',
        'scraper': 'SCRAPER_API_KEY',
        'scraperapi': 'SCRAPER_API_KEY',
    }
    env_var = key_map.get(service.lower())
    return os.environ.get(env_var) if env_var else None
