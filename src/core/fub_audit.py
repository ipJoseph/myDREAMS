"""
FUB Write Audit Log

Central logging for every write operation to Follow Up Boss.
All modules that write to FUB should call log_fub_write() after each operation.

Usage:
    from src.core.fub_audit import log_fub_write

    log_fub_write(
        module='new_listing_alerts',
        operation='create_note',
        endpoint='notes',
        http_method='POST',
        fub_person_id=25057,
        payload_summary='DREAMS Alert: 5 new listings matched',
        success=True,
    )
"""

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve DB path once at import time
_DB_PATH = os.getenv(
    'DREAMS_DB_PATH',
    str(Path(__file__).parent.parent.parent / 'data' / 'dreams.db')
)


def log_fub_write(
    module: str,
    operation: str,
    endpoint: str,
    http_method: str,
    fub_person_id: int = None,
    fub_entity_id: int = None,
    contact_id: str = None,
    payload_summary: str = None,
    success: bool = True,
    error_message: str = None,
    response_status: int = None,
) -> None:
    """
    Log a FUB write operation to the fub_write_log table.

    This function never raises. If the log insert fails, it logs
    a warning and moves on so it never disrupts the calling code.

    Args:
        module: Source module name (e.g. 'fub_core', 'new_listing_alerts', 'mcp_server')
        operation: What was done (e.g. 'create_note', 'create_task', 'update_stage')
        endpoint: FUB API endpoint (e.g. 'notes', 'tasks', 'people/25057')
        http_method: HTTP method used (POST, PUT, DELETE)
        fub_person_id: FUB person ID affected
        fub_entity_id: ID of the created/updated entity (note ID, task ID, etc.)
        contact_id: Our internal DREAMS lead/contact ID if known
        payload_summary: Brief description of the payload (truncated to 500 chars)
        success: Whether the operation succeeded
        error_message: Error details if it failed
        response_status: HTTP response status code
    """
    try:
        if payload_summary and len(payload_summary) > 500:
            payload_summary = payload_summary[:497] + '...'

        conn = sqlite3.connect(_DB_PATH)
        conn.execute("PRAGMA busy_timeout = 3000")
        conn.execute(
            '''INSERT INTO fub_write_log
               (occurred_at, module, operation, endpoint, http_method,
                fub_person_id, fub_entity_id, contact_id,
                payload_summary, success, error_message, response_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            [
                datetime.now().isoformat(),
                module, operation, endpoint, http_method,
                fub_person_id, fub_entity_id, contact_id,
                payload_summary,
                1 if success else 0,
                error_message,
                response_status,
            ]
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to log FUB write to audit table: {e}")
