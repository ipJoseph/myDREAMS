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
            parcel_id TEXT,
            zillow_id TEXT,
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
            zillow_url TEXT,
            realtor_url TEXT,
            mls_url TEXT,
            idx_url TEXT,
            photo_urls TEXT,
            virtual_tour_url TEXT,
            source TEXT,
            notes TEXT,
            captured_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_monitored_at TEXT
        );
        
        CREATE INDEX IF NOT EXISTS idx_properties_status ON properties(status);
        CREATE INDEX IF NOT EXISTS idx_properties_city ON properties(city);
        CREATE INDEX IF NOT EXISTS idx_properties_price ON properties(price);
        
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
