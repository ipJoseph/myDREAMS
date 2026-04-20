"""Contact-related read queries extracted from DREAMSDatabase.

This is the first slice of the #16 god-class decomposition. The service
takes a DREAMSDatabase instance and uses its connection helper, so
transactions and the PostgreSQL / sqlite3 auto-detection continue to
work exactly as before.

New code should call `db.contacts.get_by_fub_id(...)` rather than
`db.get_contact_by_fub_id(...)`. The DREAMSDatabase methods are kept
as thin delegators during the migration period.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.database import DREAMSDatabase


class ContactService:
    """Queries against the `leads` table (aka contacts in UI terms)."""

    def __init__(self, db: "DREAMSDatabase"):
        self._db = db

    def get_by_fub_id(self, fub_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a contact by Follow Up Boss ID."""
        with self._db._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM leads WHERE fub_id = ?',
                (fub_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_hot(
        self,
        min_heat: float = 50.0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Scored contacts sorted by heat score."""
        with self._db._get_connection() as conn:
            rows = conn.execute(
                '''
                SELECT * FROM leads
                WHERE contact_group = 'scored'
                AND heat_score >= ?
                ORDER BY heat_score DESC, priority_score DESC
                LIMIT ?
                ''',
                (min_heat, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_by_priority(
        self,
        min_priority: float = 0,
        limit: int = 100,
        user_id: Optional[int] = None,
        view: str = 'all',
    ) -> List[Dict[str, Any]]:
        """Contacts sorted by priority with optional view filter.

        Views:
            'all' — every row passing the priority floor
            'my_leads' — scored contacts assigned to user_id
            'brand_new' / 'hand_raised' / 'warm_pond' / 'agents_vendors' —
                pond views, sorted by last activity rather than priority
        """
        pond_views = {'brand_new', 'hand_raised', 'warm_pond', 'agents_vendors'}
        is_pond_view = view in pond_views

        with self._db._get_connection() as conn:
            query = 'SELECT * FROM leads WHERE 1=1'
            params: List[Any] = []

            if not is_pond_view:
                query += ' AND priority_score >= ?'
                params.append(min_priority)

            if view == 'my_leads' and user_id:
                query += ' AND contact_group = ? AND assigned_user_id = ?'
                params.extend(['scored', user_id])
            elif is_pond_view:
                query += ' AND contact_group = ?'
                params.append(view)

            if is_pond_view:
                query += ' ORDER BY last_activity_at DESC LIMIT ?'
            else:
                query += ' ORDER BY priority_score DESC LIMIT ?'
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_stats(
        self,
        user_id: Optional[int] = None,
        view: str = 'all',
    ) -> Dict[str, Any]:
        """Aggregate counters used by the contacts dashboard header."""
        pond_views = {'brand_new', 'hand_raised', 'warm_pond', 'agents_vendors'}

        with self._db._get_connection() as conn:
            where_clause = '1=1'
            params: List[Any] = []

            if view == 'my_leads' and user_id:
                where_clause = 'contact_group = ? AND assigned_user_id = ?'
                params = ['scored', user_id]
            elif view in pond_views:
                where_clause = 'contact_group = ?'
                params = [view]

            def scalar(sql: str) -> Any:
                return conn.execute(sql, params).fetchone()[0]

            total = scalar(f'SELECT COUNT(*) FROM leads WHERE {where_clause}')
            hot = scalar(
                f'SELECT COUNT(*) FROM leads WHERE {where_clause} AND heat_score >= 75'
            )
            high_value = scalar(
                f'SELECT COUNT(*) FROM leads WHERE {where_clause} AND value_score >= 60'
            )
            active_week = scalar(
                f'SELECT COUNT(*) FROM leads WHERE {where_clause} AND days_since_activity <= 7'
            )
            avg_priority = scalar(
                f'SELECT AVG(priority_score) FROM leads WHERE {where_clause} AND priority_score > 0'
            ) or 0
            high_intent = scalar(
                f'SELECT COUNT(*) FROM leads WHERE {where_clause} AND intent_signal_count >= 4'
            )

            return {
                'total': total,
                'hot': hot,
                'high_value': high_value,
                'active_week': active_week,
                'avg_priority': round(float(avg_priority), 1),
                'high_intent': high_intent,
            }
