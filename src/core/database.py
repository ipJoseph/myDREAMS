"""
DREAMS Database Module

SQLite database operations for the canonical data store.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from contextlib import contextmanager
import logging

from src.adapters.base_adapter import Lead, Activity, Property, Match

logger = logging.getLogger(__name__)


class DREAMSDatabase:
    """
    SQLite database manager for DREAMS platform.
    
    This is the canonical data store. All external systems sync through this.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self) -> None:
        """Create tables if they don't exist."""
        with self._get_connection() as conn:
            # Enable WAL mode for better concurrency and crash recovery
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            
            # Read and execute schema
            schema = self._get_schema()
            conn.executescript(schema)
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _get_schema(self) -> str:
        """Return the database schema SQL."""
        return '''
        -- Leads table
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            external_id TEXT,
            external_source TEXT,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            phone TEXT,
            stage TEXT DEFAULT 'lead',
            type TEXT DEFAULT 'buyer',
            source TEXT,
            heat_score INTEGER DEFAULT 0,
            value_score INTEGER DEFAULT 0,
            relationship_score INTEGER DEFAULT 0,
            priority_score INTEGER DEFAULT 0,
            min_price INTEGER,
            max_price INTEGER,
            min_beds INTEGER,
            min_baths REAL,
            min_sqft INTEGER,
            min_acreage REAL,
            preferred_cities TEXT,
            preferred_features TEXT,
            deal_breakers TEXT,
            requirements_confidence REAL,
            requirements_updated_at TEXT,
            assigned_agent TEXT,
            tags TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_synced_at TEXT,
            UNIQUE(external_id, external_source)
        );
        
        CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
        CREATE INDEX IF NOT EXISTS idx_leads_priority ON leads(priority_score DESC);
        
        -- Activities table
        CREATE TABLE IF NOT EXISTS lead_activities (
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            activity_source TEXT,
            activity_data TEXT,
            property_id TEXT,
            occurred_at TEXT NOT NULL,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_activities_lead ON lead_activities(lead_id);
        CREATE INDEX IF NOT EXISTS idx_activities_type ON lead_activities(activity_type);
        
        -- Properties table
        CREATE TABLE IF NOT EXISTS properties (
            id TEXT PRIMARY KEY,
            mls_number TEXT,
            mls_source TEXT,
            parcel_id TEXT,
            zillow_id TEXT,
            realtor_id TEXT,
            redfin_id TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            zip TEXT,
            county TEXT,
            price INTEGER,
            beds INTEGER,
            baths REAL,
            sqft INTEGER,
            acreage REAL,
            year_built INTEGER,
            property_type TEXT,
            style TEXT,
            views TEXT,
            water_features TEXT,
            amenities TEXT,
            status TEXT DEFAULT 'active',
            days_on_market INTEGER,
            list_date TEXT,
            initial_price INTEGER,
            price_history TEXT,
            status_history TEXT,
            listing_agent_name TEXT,
            listing_agent_phone TEXT,
            listing_agent_email TEXT,
            listing_brokerage TEXT,
            -- New financial fields
            hoa_fee INTEGER,
            tax_assessed_value INTEGER,
            tax_annual_amount INTEGER,
            zestimate INTEGER,
            rent_zestimate INTEGER,
            -- New metrics fields
            page_views INTEGER,
            favorites_count INTEGER,
            -- New detail fields
            heating TEXT,
            cooling TEXT,
            garage TEXT,
            sewer TEXT,
            roof TEXT,
            stories INTEGER,
            subdivision TEXT,
            -- Location fields
            latitude REAL,
            longitude REAL,
            school_elementary_rating INTEGER,
            school_middle_rating INTEGER,
            school_high_rating INTEGER,
            -- URLs
            zillow_url TEXT,
            realtor_url TEXT,
            redfin_url TEXT,
            mls_url TEXT,
            idx_url TEXT,
            photo_urls TEXT,
            virtual_tour_url TEXT,
            source TEXT,
            notes TEXT,
            captured_by TEXT,
            added_for TEXT,
            added_by TEXT,
            -- Notion sync tracking
            notion_page_id TEXT,
            notion_synced_at TEXT,
            sync_status TEXT DEFAULT 'pending',
            sync_error TEXT,
            -- IDX validation fields
            idx_mls_number TEXT,
            original_mls_number TEXT,
            idx_validation_status TEXT DEFAULT 'pending',
            idx_validated_at TEXT,
            idx_mls_source TEXT,
            -- Timestamps
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_monitored_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_properties_status ON properties(status);
        CREATE INDEX IF NOT EXISTS idx_properties_city ON properties(city);
        CREATE INDEX IF NOT EXISTS idx_properties_price ON properties(price);
        CREATE INDEX IF NOT EXISTS idx_properties_zillow_id ON properties(zillow_id);
        CREATE INDEX IF NOT EXISTS idx_properties_redfin_id ON properties(redfin_id);
        CREATE INDEX IF NOT EXISTS idx_properties_mls ON properties(mls_number);
        CREATE INDEX IF NOT EXISTS idx_properties_sync_status ON properties(sync_status);
        CREATE INDEX IF NOT EXISTS idx_properties_idx_validation ON properties(idx_validation_status);
        
        -- Matches table
        CREATE TABLE IF NOT EXISTS matches (
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            property_id TEXT NOT NULL,
            total_score REAL,
            stated_score REAL,
            behavioral_score REAL,
            score_breakdown TEXT,
            match_status TEXT DEFAULT 'suggested',
            suggested_at TEXT DEFAULT CURRENT_TIMESTAMP,
            sent_at TEXT,
            response_at TEXT,
            shown_at TEXT,
            lead_feedback TEXT,
            agent_notes TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads(id),
            FOREIGN KEY (property_id) REFERENCES properties(id),
            UNIQUE(lead_id, property_id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_matches_lead ON matches(lead_id);
        CREATE INDEX IF NOT EXISTS idx_matches_score ON matches(total_score DESC);
        
        -- Packages table
        CREATE TABLE IF NOT EXISTS packages (
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            title TEXT,
            property_ids TEXT,
            showing_date TEXT,
            pdf_path TEXT,
            html_content TEXT,
            status TEXT DEFAULT 'draft',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            sent_at TEXT,
            opened_at TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );
        
        -- Sync log table
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_type TEXT NOT NULL,
            source TEXT NOT NULL,
            direction TEXT NOT NULL,
            records_processed INTEGER DEFAULT 0,
            records_created INTEGER DEFAULT 0,
            records_updated INTEGER DEFAULT 0,
            records_failed INTEGER DEFAULT 0,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            error_message TEXT,
            details TEXT
        );
        '''
    
    # ==========================================
    # LEAD OPERATIONS
    # ==========================================
    
    def upsert_lead(self, lead: Lead) -> bool:
        """Insert or update a lead."""
        with self._get_connection() as conn:
            data = lead.to_dict()
            data['updated_at'] = datetime.now().isoformat()
            data['last_synced_at'] = datetime.now().isoformat()
            
            placeholders = ', '.join([f'{k} = ?' for k in data.keys()])
            columns = ', '.join(data.keys())
            values = list(data.values())
            
            conn.execute(f'''
                INSERT INTO leads ({columns})
                VALUES ({', '.join(['?' for _ in values])})
                ON CONFLICT(id) DO UPDATE SET {placeholders}
            ''', values + values)
            conn.commit()
            return True
    
    def get_lead(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """Get lead by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM leads WHERE id = ?',
                (lead_id,)
            ).fetchone()
            return dict(row) if row else None
    
    def get_leads(
        self,
        stage: Optional[str] = None,
        type: Optional[str] = None,
        min_priority: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get leads with optional filters."""
        query = 'SELECT * FROM leads WHERE priority_score >= ?'
        params = [min_priority]
        
        if stage:
            query += ' AND stage = ?'
            params.append(stage)
        if type:
            query += ' AND type = ?'
            params.append(type)
        
        query += ' ORDER BY priority_score DESC LIMIT ?'
        params.append(limit)
        
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    # ==========================================
    # PROPERTY OPERATIONS
    # ==========================================
    
    def upsert_property(self, property: Property) -> bool:
        """Insert or update a property."""
        with self._get_connection() as conn:
            data = property.to_dict()
            data['updated_at'] = datetime.now().isoformat()
            
            placeholders = ', '.join([f'{k} = ?' for k in data.keys()])
            columns = ', '.join(data.keys())
            values = list(data.values())
            
            conn.execute(f'''
                INSERT INTO properties ({columns})
                VALUES ({', '.join(['?' for _ in values])})
                ON CONFLICT(id) DO UPDATE SET {placeholders}
            ''', values + values)
            conn.commit()
            return True
    
    def get_property(self, property_id: str) -> Optional[Dict[str, Any]]:
        """Get property by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM properties WHERE id = ?',
                (property_id,)
            ).fetchone()
            return dict(row) if row else None
    
    def get_properties(
        self,
        status: str = 'active',
        city: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get properties with optional filters."""
        query = 'SELECT * FROM properties WHERE status = ?'
        params = [status]

        if city:
            query += ' AND city = ?'
            params.append(city)
        if min_price:
            query += ' AND price >= ?'
            params.append(min_price)
        if max_price:
            query += ' AND price <= ?'
            params.append(max_price)

        query += ' ORDER BY updated_at DESC LIMIT ?'
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_property_by_zillow_id(self, zillow_id: str) -> Optional[Dict[str, Any]]:
        """Get property by Zillow ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM properties WHERE zillow_id = ?',
                (zillow_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_property_by_realtor_id(self, realtor_id: str) -> Optional[Dict[str, Any]]:
        """Get property by Realtor.com ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM properties WHERE realtor_id = ?',
                (realtor_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_property_by_mls(self, mls_number: str) -> Optional[Dict[str, Any]]:
        """Get property by MLS number."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM properties WHERE mls_number = ?',
                (mls_number,)
            ).fetchone()
            return dict(row) if row else None

    def get_property_by_redfin_id(self, redfin_id: str) -> Optional[Dict[str, Any]]:
        """Get property by Redfin ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM properties WHERE redfin_id = ?',
                (redfin_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_property_by_address(self, address: str, city: str = None) -> Optional[Dict[str, Any]]:
        """Get property by address (and optionally city for more precise matching)."""
        with self._get_connection() as conn:
            # Normalize address for comparison (case-insensitive)
            if city:
                row = conn.execute(
                    'SELECT * FROM properties WHERE LOWER(address) = LOWER(?) AND LOWER(city) = LOWER(?)',
                    (address, city)
                ).fetchone()
            else:
                row = conn.execute(
                    'SELECT * FROM properties WHERE LOWER(address) = LOWER(?)',
                    (address,)
                ).fetchone()
            return dict(row) if row else None

    def upsert_property_dict(self, data: Dict[str, Any]) -> bool:
        """Insert or update a property from a dictionary."""
        with self._get_connection() as conn:
            # Filter out None values and ensure we have an id
            data = {k: v for k, v in data.items() if v is not None}

            if 'id' not in data:
                return False

            # Build upsert query
            columns = list(data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            update_clause = ', '.join([f'{col} = ?' for col in columns if col != 'id'])

            query = f'''
                INSERT INTO properties ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(id) DO UPDATE SET {update_clause}
            '''

            # Values for insert + values for update (excluding id)
            values = list(data.values())
            update_values = [v for k, v in data.items() if k != 'id']

            conn.execute(query, values + update_values)
            conn.commit()
            return True

    def get_properties_by_sync_status(self, status: str) -> List[Dict[str, Any]]:
        """Get properties by sync status (pending, synced, failed)."""
        with self._get_connection() as conn:
            rows = conn.execute(
                'SELECT * FROM properties WHERE sync_status = ? ORDER BY updated_at DESC',
                (status,)
            ).fetchall()
            return [dict(row) for row in rows]

    def update_property_sync_status(
        self,
        property_id: str,
        status: str,
        notion_page_id: Optional[str] = None,
        error: Optional[str] = None
    ) -> bool:
        """Update the sync status of a property."""
        with self._get_connection() as conn:
            if status == 'synced':
                conn.execute('''
                    UPDATE properties SET
                        sync_status = ?,
                        notion_page_id = ?,
                        notion_synced_at = ?,
                        sync_error = NULL
                    WHERE id = ?
                ''', (status, notion_page_id, datetime.now().isoformat(), property_id))
            else:
                conn.execute('''
                    UPDATE properties SET
                        sync_status = ?,
                        sync_error = ?
                    WHERE id = ?
                ''', (status, error, property_id))
            conn.commit()
            return True

    def get_properties_by_idx_validation_status(
        self,
        status: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get properties by IDX validation status (pending, validated, not_found, error)."""
        with self._get_connection() as conn:
            rows = conn.execute(
                '''SELECT * FROM properties
                   WHERE idx_validation_status = ?
                   ORDER BY updated_at DESC
                   LIMIT ?''',
                (status, limit)
            ).fetchall()
            return [dict(row) for row in rows]

    def update_idx_validation(
        self,
        property_id: str,
        status: str,
        idx_mls_number: Optional[str] = None,
        idx_mls_source: Optional[str] = None,
        original_mls_number: Optional[str] = None
    ) -> bool:
        """Update the IDX validation status and MLS information for a property."""
        with self._get_connection() as conn:
            now = datetime.now().isoformat()

            if status == 'validated':
                conn.execute('''
                    UPDATE properties SET
                        idx_validation_status = ?,
                        idx_mls_number = ?,
                        idx_mls_source = ?,
                        original_mls_number = COALESCE(?, original_mls_number, mls_number),
                        idx_validated_at = ?,
                        sync_status = 'pending',
                        updated_at = ?
                    WHERE id = ?
                ''', (status, idx_mls_number, idx_mls_source, original_mls_number, now, now, property_id))
            else:
                conn.execute('''
                    UPDATE properties SET
                        idx_validation_status = ?,
                        original_mls_number = COALESCE(original_mls_number, mls_number),
                        idx_validated_at = ?,
                        sync_status = 'pending',
                        updated_at = ?
                    WHERE id = ?
                ''', (status, now, now, property_id))

            conn.commit()
            return True

    # ==========================================
    # MATCH OPERATIONS
    # ==========================================

    def upsert_match(self, match: Match) -> bool:
        """Insert or update a match."""
        with self._get_connection() as conn:
            data = match.to_dict()
            
            placeholders = ', '.join([f'{k} = ?' for k in data.keys()])
            columns = ', '.join(data.keys())
            values = list(data.values())
            
            conn.execute(f'''
                INSERT INTO matches ({columns})
                VALUES ({', '.join(['?' for _ in values])})
                ON CONFLICT(lead_id, property_id) DO UPDATE SET {placeholders}
            ''', values + values)
            conn.commit()
            return True
    
    def get_matches_for_lead(
        self,
        lead_id: str,
        min_score: float = 0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get matches for a lead, ordered by score."""
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT m.*, p.address, p.city, p.price, p.beds, p.baths
                FROM matches m
                JOIN properties p ON m.property_id = p.id
                WHERE m.lead_id = ? AND m.total_score >= ?
                ORDER BY m.total_score DESC
                LIMIT ?
            ''', (lead_id, min_score, limit)).fetchall()
            return [dict(row) for row in rows]
    
    # ==========================================
    # ACTIVITY OPERATIONS
    # ==========================================
    
    def insert_activity(self, activity: Activity) -> bool:
        """Insert an activity record."""
        with self._get_connection() as conn:
            data = activity.to_dict()
            columns = ', '.join(data.keys())
            values = list(data.values())
            
            conn.execute(f'''
                INSERT OR IGNORE INTO lead_activities ({columns})
                VALUES ({', '.join(['?' for _ in values])})
            ''', values)
            conn.commit()
            return True
    
    def get_activities_for_lead(
        self,
        lead_id: str,
        activity_types: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get activities for a lead."""
        query = 'SELECT * FROM lead_activities WHERE lead_id = ?'
        params = [lead_id]
        
        if activity_types:
            placeholders = ', '.join(['?' for _ in activity_types])
            query += f' AND activity_type IN ({placeholders})'
            params.extend(activity_types)
        
        query += ' ORDER BY occurred_at DESC LIMIT ?'
        params.append(limit)
        
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    # ==========================================
    # SYNC LOG OPERATIONS
    # ==========================================
    
    def log_sync_start(
        self,
        sync_type: str,
        source: str,
        direction: str
    ) -> int:
        """Log start of a sync operation. Returns log ID."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO sync_log (sync_type, source, direction)
                VALUES (?, ?, ?)
            ''', (sync_type, source, direction))
            conn.commit()
            return cursor.lastrowid
    
    def log_sync_complete(
        self,
        log_id: int,
        records_processed: int,
        records_created: int,
        records_updated: int,
        records_failed: int = 0,
        error_message: Optional[str] = None
    ) -> None:
        """Log completion of a sync operation."""
        with self._get_connection() as conn:
            conn.execute('''
                UPDATE sync_log SET
                    records_processed = ?,
                    records_created = ?,
                    records_updated = ?,
                    records_failed = ?,
                    completed_at = ?,
                    error_message = ?
                WHERE id = ?
            ''', (
                records_processed, records_created, records_updated,
                records_failed, datetime.now().isoformat(), error_message, log_id
            ))
            conn.commit()
