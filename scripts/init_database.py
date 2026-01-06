#!/usr/bin/env python3
"""
Initialize DREAMS Database

Creates the SQLite database with all required tables.
Run this once before using the system.

Usage:
    python scripts/init_database.py
    
Run from your myDREAMS repository root.
"""

import sys
import os
from pathlib import Path

# Determine repo root (parent of scripts/)
REPO_ROOT = Path(__file__).parent.parent.absolute()

# Add src to path
sys.path.insert(0, str(REPO_ROOT))

# Change to repo root for relative paths to work
os.chdir(REPO_ROOT)

from src.utils.config import load_config, get_db_path
from src.utils.logging import setup_logging
from src.core.database import DREAMSDatabase


def main():
    """Initialize the database."""
    print(f"DREAMS Platform - Database Initialization")
    print(f"Repository root: {REPO_ROOT}")
    print()
    
    # Load configuration
    config = load_config(
        config_path=REPO_ROOT / "config" / "config.yaml",
        env_path=REPO_ROOT / "config" / ".env"
    )
    
    # Setup logging
    log_config = config.get('logging', {})
    logger = setup_logging(
        level=log_config.get('level', 'INFO'),
        log_file=log_config.get('file')
    )
    
    # Get database path - default to data/dreams.db
    db_path = get_db_path(config)
    if not db_path or db_path == './data/dreams.db':
        db_path = REPO_ROOT / "data" / "dreams.db"
    
    logger.info(f"Initializing database at: {db_path}")
    
    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Create database (tables are created in __init__)
    db = DREAMSDatabase(str(db_path))
    
    logger.info("Database initialized successfully!")
    logger.info(f"Database file: {Path(db_path).absolute()}")
    
    print()
    print(f"✓ Database created: {db_path}")
    print()
    print("Next: Run data migration scripts or start using the platform.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
