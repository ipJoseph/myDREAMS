"""
DREAMS Database Module

SQLite database operations for the canonical data store.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
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

            # First create tables only (without indexes that depend on new columns)
            tables_schema = self._get_tables_schema()
            conn.executescript(tables_schema)
            conn.commit()

            # Apply migrations to add missing columns to existing tables
            self._apply_migrations(conn)
            conn.commit()

            # Now create indexes (columns will exist)
            indexes_schema = self._get_indexes_schema()
            conn.executescript(indexes_schema)
            conn.commit()

            logger.info(f"Database initialized at {self.db_path}")

    def _apply_migrations(self, conn) -> None:
        """Add missing columns to existing tables (for schema updates)."""
        # Get existing columns in leads table
        cursor = conn.execute("PRAGMA table_info(leads)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        # Define new columns that may be missing
        new_lead_columns = [
            ("fub_id", "TEXT"),
            ("lead_type_tags", "TEXT"),
            ("heat_score", "REAL DEFAULT 0"),
            ("value_score", "REAL DEFAULT 0"),
            ("relationship_score", "REAL DEFAULT 0"),
            ("priority_score", "REAL DEFAULT 0"),
            ("website_visits", "INTEGER DEFAULT 0"),
            ("properties_viewed", "INTEGER DEFAULT 0"),
            ("properties_favorited", "INTEGER DEFAULT 0"),
            ("calls_inbound", "INTEGER DEFAULT 0"),
            ("calls_outbound", "INTEGER DEFAULT 0"),
            ("texts_total", "INTEGER DEFAULT 0"),
            ("avg_price_viewed", "REAL"),
            ("days_since_activity", "INTEGER"),
            ("last_activity_at", "TEXT"),
            ("intent_repeat_views", "INTEGER DEFAULT 0"),
            ("intent_high_favorites", "INTEGER DEFAULT 0"),
            ("intent_activity_burst", "INTEGER DEFAULT 0"),
            ("intent_sharing", "INTEGER DEFAULT 0"),
            ("intent_signal_count", "INTEGER DEFAULT 0"),
            ("next_action", "TEXT"),
            ("next_action_date", "TEXT"),
            # Enhanced FUB data architecture columns
            ("score_trend", "TEXT"),                    # 'warming', 'cooling', 'stable'
            ("heat_score_7d_avg", "REAL"),              # Rolling 7-day average
            ("last_score_recorded_at", "TEXT"),         # Last scoring history timestamp
            ("total_communications", "INTEGER DEFAULT 0"),  # Total comms count
            ("total_events", "INTEGER DEFAULT 0"),      # Total events count
        ]

        for col_name, col_type in new_lead_columns:
            if col_name not in existing_cols:
                try:
                    conn.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column {col_name} to leads table")
                except sqlite3.OperationalError:
                    pass  # Column already exists
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _get_tables_schema(self) -> str:
        """Return the CREATE TABLE statements only."""
        return '''
        -- Leads/Contacts table (unified for FUB contacts and general leads)
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            external_id TEXT,
            external_source TEXT,
            fub_id TEXT,              -- Follow Up Boss contact ID
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            phone TEXT,
            stage TEXT DEFAULT 'lead',
            type TEXT DEFAULT 'buyer',
            source TEXT,
            lead_type_tags TEXT,      -- JSON array of tags
            -- Scoring fields (REAL for decimal precision)
            heat_score REAL DEFAULT 0,
            value_score REAL DEFAULT 0,
            relationship_score REAL DEFAULT 0,
            priority_score REAL DEFAULT 0,
            -- Buyer preferences
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
            -- Activity stats (from FUB)
            website_visits INTEGER DEFAULT 0,
            properties_viewed INTEGER DEFAULT 0,
            properties_favorited INTEGER DEFAULT 0,
            calls_inbound INTEGER DEFAULT 0,
            calls_outbound INTEGER DEFAULT 0,
            texts_total INTEGER DEFAULT 0,
            avg_price_viewed REAL,
            days_since_activity INTEGER,
            last_activity_at TEXT,
            -- Intent signals (computed)
            intent_repeat_views INTEGER DEFAULT 0,
            intent_high_favorites INTEGER DEFAULT 0,
            intent_activity_burst INTEGER DEFAULT 0,
            intent_sharing INTEGER DEFAULT 0,
            intent_signal_count INTEGER DEFAULT 0,
            -- Action tracking
            next_action TEXT,
            next_action_date TEXT,
            -- Admin fields
            assigned_agent TEXT,
            tags TEXT,
            notes TEXT,
            -- Timestamps
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_synced_at TEXT,
            UNIQUE(external_id, external_source)
        );

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

        -- Contact-Property relationships (saved/viewed/shared)
        CREATE TABLE IF NOT EXISTS contact_properties (
            id TEXT PRIMARY KEY,
            contact_id TEXT NOT NULL,
            property_id TEXT NOT NULL,
            relationship TEXT DEFAULT 'saved',  -- 'saved', 'viewed', 'shared', 'matched', 'favorited'
            match_score REAL,
            view_count INTEGER DEFAULT 0,
            first_viewed_at TEXT,
            last_viewed_at TEXT,
            saved_at TEXT,
            shared_at TEXT,
            shared_with TEXT,                   -- JSON array of recipients
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES leads(id),
            FOREIGN KEY (property_id) REFERENCES properties(id),
            UNIQUE(contact_id, property_id)
        );

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

        -- Contact scoring history (track score snapshots for trend analysis)
        CREATE TABLE IF NOT EXISTS contact_scoring_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sync_id INTEGER,
            -- Score snapshots
            heat_score REAL NOT NULL DEFAULT 0,
            value_score REAL NOT NULL DEFAULT 0,
            relationship_score REAL NOT NULL DEFAULT 0,
            priority_score REAL NOT NULL DEFAULT 0,
            -- Activity counts at snapshot time
            website_visits INTEGER DEFAULT 0,
            properties_viewed INTEGER DEFAULT 0,
            calls_inbound INTEGER DEFAULT 0,
            calls_outbound INTEGER DEFAULT 0,
            texts_total INTEGER DEFAULT 0,
            intent_signal_count INTEGER DEFAULT 0,
            -- Computed trends
            heat_delta REAL,
            trend_direction TEXT,  -- 'warming', 'cooling', 'stable'
            FOREIGN KEY (contact_id) REFERENCES leads(id)
        );

        -- Contact communications (individual call/text records - NO content stored for privacy)
        CREATE TABLE IF NOT EXISTS contact_communications (
            id TEXT PRIMARY KEY,
            contact_id TEXT NOT NULL,
            comm_type TEXT NOT NULL,      -- 'call', 'text', 'email'
            direction TEXT NOT NULL,      -- 'inbound', 'outbound'
            occurred_at TEXT NOT NULL,
            duration_seconds INTEGER,     -- Calls only
            fub_id TEXT,
            fub_user_name TEXT,           -- Agent who handled it
            status TEXT,                  -- 'completed', 'missed', 'voicemail'
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES leads(id)
        );

        -- Contact events (website visits, property views, favorites from FUB)
        CREATE TABLE IF NOT EXISTS contact_events (
            id TEXT PRIMARY KEY,
            contact_id TEXT NOT NULL,
            event_type TEXT NOT NULL,     -- 'website_visit', 'property_view', 'property_favorite', 'property_share'
            occurred_at TEXT NOT NULL,
            property_address TEXT,        -- Denormalized for display
            property_price INTEGER,
            property_mls TEXT,
            fub_event_id TEXT,            -- For deduplication
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES leads(id)
        );

        -- IDX Property Cache (MLS to address lookup from IDX site)
        CREATE TABLE IF NOT EXISTS idx_property_cache (
            mls_number TEXT PRIMARY KEY,
            address TEXT,
            city TEXT,
            price INTEGER,
            status TEXT,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Property changes (price/status changes detected by monitor)
        CREATE TABLE IF NOT EXISTS property_changes (
            id TEXT PRIMARY KEY,
            property_id TEXT,             -- Notion page ID or internal property ID
            property_address TEXT NOT NULL,
            change_type TEXT NOT NULL,    -- 'price', 'status', 'dom', 'views', 'saves'
            old_value TEXT,
            new_value TEXT,
            change_amount INTEGER,        -- For price: delta (positive or negative)
            detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notified INTEGER DEFAULT 0,   -- 0 = not notified, 1 = included in report
            source TEXT,                  -- 'redfin', 'zillow', 'realtor'
            notion_url TEXT               -- Link to Notion page for quick access
        );
        '''

    def _get_indexes_schema(self) -> str:
        """Return the CREATE INDEX statements (run after migrations)."""
        return '''
        CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
        CREATE INDEX IF NOT EXISTS idx_leads_priority ON leads(priority_score DESC);
        CREATE INDEX IF NOT EXISTS idx_leads_fub_id ON leads(fub_id);
        CREATE INDEX IF NOT EXISTS idx_leads_heat ON leads(heat_score DESC);
        CREATE INDEX IF NOT EXISTS idx_activities_lead ON lead_activities(lead_id);
        CREATE INDEX IF NOT EXISTS idx_activities_type ON lead_activities(activity_type);
        CREATE INDEX IF NOT EXISTS idx_properties_status ON properties(status);
        CREATE INDEX IF NOT EXISTS idx_properties_city ON properties(city);
        CREATE INDEX IF NOT EXISTS idx_properties_price ON properties(price);
        CREATE INDEX IF NOT EXISTS idx_properties_zillow_id ON properties(zillow_id);
        CREATE INDEX IF NOT EXISTS idx_properties_redfin_id ON properties(redfin_id);
        CREATE INDEX IF NOT EXISTS idx_properties_mls ON properties(mls_number);
        CREATE INDEX IF NOT EXISTS idx_properties_sync_status ON properties(sync_status);
        CREATE INDEX IF NOT EXISTS idx_properties_idx_validation ON properties(idx_validation_status);
        CREATE INDEX IF NOT EXISTS idx_matches_lead ON matches(lead_id);
        CREATE INDEX IF NOT EXISTS idx_matches_score ON matches(total_score DESC);
        CREATE INDEX IF NOT EXISTS idx_contact_props_contact ON contact_properties(contact_id);
        CREATE INDEX IF NOT EXISTS idx_contact_props_property ON contact_properties(property_id);
        CREATE INDEX IF NOT EXISTS idx_contact_props_relationship ON contact_properties(relationship);
        -- Contact scoring history indexes
        CREATE INDEX IF NOT EXISTS idx_scoring_history_contact ON contact_scoring_history(contact_id, recorded_at DESC);
        -- Contact communications indexes
        CREATE INDEX IF NOT EXISTS idx_comms_contact ON contact_communications(contact_id, occurred_at DESC);
        CREATE INDEX IF NOT EXISTS idx_comms_type ON contact_communications(comm_type);
        -- Contact events indexes
        CREATE INDEX IF NOT EXISTS idx_events_contact ON contact_events(contact_id, occurred_at DESC);
        CREATE INDEX IF NOT EXISTS idx_events_type ON contact_events(event_type);
        -- Property changes indexes
        CREATE INDEX IF NOT EXISTS idx_property_changes_detected ON property_changes(detected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_property_changes_type ON property_changes(change_type);
        CREATE INDEX IF NOT EXISTS idx_property_changes_notified ON property_changes(notified);
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

    def upsert_contact_dict(self, data: Dict[str, Any]) -> bool:
        """Insert or update a contact/lead from a dictionary (FUB sync)."""
        with self._get_connection() as conn:
            # Check if record exists by external_id + external_source
            external_id = data.get('external_id')
            external_source = data.get('external_source')

            existing_id = None
            if external_id and external_source:
                row = conn.execute(
                    'SELECT id FROM leads WHERE external_id = ? AND external_source = ?',
                    (external_id, external_source)
                ).fetchone()
                if row:
                    existing_id = row[0]

            # Use existing ID if found, otherwise ensure we have an ID
            if existing_id:
                data['id'] = existing_id
            elif 'id' not in data:
                import uuid
                data['id'] = str(uuid.uuid4())

            data['updated_at'] = datetime.now().isoformat()
            data['last_synced_at'] = datetime.now().isoformat()

            # Filter out None values for cleaner storage
            data = {k: v for k, v in data.items() if v is not None}

            columns = list(data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            update_clause = ', '.join([f'{col} = ?' for col in columns if col != 'id'])

            query = f'''
                INSERT INTO leads ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(id) DO UPDATE SET {update_clause}
            '''

            values = list(data.values())
            update_values = [v for k, v in data.items() if k != 'id']

            conn.execute(query, values + update_values)
            conn.commit()
            return True

    def get_contact_by_fub_id(self, fub_id: str) -> Optional[Dict[str, Any]]:
        """Get contact by Follow Up Boss ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM leads WHERE fub_id = ?',
                (fub_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_hot_contacts(
        self,
        min_heat: float = 50.0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get contacts sorted by heat score."""
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM leads
                WHERE heat_score >= ?
                ORDER BY heat_score DESC, priority_score DESC
                LIMIT ?
            ''', (min_heat, limit)).fetchall()
            return [dict(row) for row in rows]

    def get_contacts_by_priority(
        self,
        min_priority: float = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get contacts sorted by priority score."""
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM leads
                WHERE priority_score >= ?
                ORDER BY priority_score DESC
                LIMIT ?
            ''', (min_priority, limit)).fetchall()
            return [dict(row) for row in rows]

    def get_contact_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics for contacts."""
        with self._get_connection() as conn:
            total = conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
            hot = conn.execute(
                'SELECT COUNT(*) FROM leads WHERE heat_score >= 75'
            ).fetchone()[0]
            high_value = conn.execute(
                'SELECT COUNT(*) FROM leads WHERE value_score >= 60'
            ).fetchone()[0]
            active_week = conn.execute(
                'SELECT COUNT(*) FROM leads WHERE days_since_activity <= 7'
            ).fetchone()[0]
            avg_priority = conn.execute(
                'SELECT AVG(priority_score) FROM leads WHERE priority_score > 0'
            ).fetchone()[0] or 0
            high_intent = conn.execute(
                'SELECT COUNT(*) FROM leads WHERE intent_signal_count >= 4'
            ).fetchone()[0]

            return {
                'total': total,
                'hot': hot,
                'high_value': high_value,
                'active_week': active_week,
                'avg_priority': round(avg_priority, 1),
                'high_intent': high_intent
            }

    # ==========================================
    # CONTACT-PROPERTY RELATIONSHIP OPERATIONS
    # ==========================================

    def upsert_contact_property(
        self,
        contact_id: str,
        property_id: str,
        relationship: str = 'saved',
        match_score: Optional[float] = None,
        notes: Optional[str] = None
    ) -> bool:
        """Link a contact to a property."""
        import uuid
        with self._get_connection() as conn:
            now = datetime.now().isoformat()

            # Check if relationship exists
            existing = conn.execute('''
                SELECT id FROM contact_properties
                WHERE contact_id = ? AND property_id = ?
            ''', (contact_id, property_id)).fetchone()

            if existing:
                # Update existing relationship
                conn.execute('''
                    UPDATE contact_properties SET
                        relationship = ?,
                        match_score = COALESCE(?, match_score),
                        view_count = view_count + 1,
                        last_viewed_at = ?,
                        notes = COALESCE(?, notes),
                        updated_at = ?
                    WHERE contact_id = ? AND property_id = ?
                ''', (relationship, match_score, now, notes, now, contact_id, property_id))
            else:
                # Create new relationship
                conn.execute('''
                    INSERT INTO contact_properties
                    (id, contact_id, property_id, relationship, match_score,
                     view_count, first_viewed_at, last_viewed_at, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                ''', (str(uuid.uuid4()), contact_id, property_id, relationship,
                      match_score, now, now, notes, now, now))

            conn.commit()
            return True

    def get_contact_properties(
        self,
        contact_id: str,
        relationship: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get properties linked to a contact."""
        with self._get_connection() as conn:
            if relationship:
                rows = conn.execute('''
                    SELECT cp.*, p.address, p.city, p.price, p.beds, p.baths, p.status
                    FROM contact_properties cp
                    JOIN properties p ON cp.property_id = p.id
                    WHERE cp.contact_id = ? AND cp.relationship = ?
                    ORDER BY cp.updated_at DESC
                ''', (contact_id, relationship)).fetchall()
            else:
                rows = conn.execute('''
                    SELECT cp.*, p.address, p.city, p.price, p.beds, p.baths, p.status
                    FROM contact_properties cp
                    JOIN properties p ON cp.property_id = p.id
                    WHERE cp.contact_id = ?
                    ORDER BY cp.updated_at DESC
                ''', (contact_id,)).fetchall()
            return [dict(row) for row in rows]

    def get_property_contacts(
        self,
        property_id: str,
        relationship: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get contacts linked to a property."""
        with self._get_connection() as conn:
            if relationship:
                rows = conn.execute('''
                    SELECT cp.*, l.first_name, l.last_name, l.email, l.phone,
                           l.heat_score, l.priority_score
                    FROM contact_properties cp
                    JOIN leads l ON cp.contact_id = l.id
                    WHERE cp.property_id = ? AND cp.relationship = ?
                    ORDER BY l.priority_score DESC
                ''', (property_id, relationship)).fetchall()
            else:
                rows = conn.execute('''
                    SELECT cp.*, l.first_name, l.last_name, l.email, l.phone,
                           l.heat_score, l.priority_score
                    FROM contact_properties cp
                    JOIN leads l ON cp.contact_id = l.id
                    WHERE cp.property_id = ?
                    ORDER BY l.priority_score DESC
                ''', (property_id,)).fetchall()
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

    # ==========================================
    # CONTACT SCORING HISTORY OPERATIONS
    # ==========================================

    def should_record_daily_score(self, contact_id: str) -> bool:
        """Check if we should record a score today (only once per day)."""
        with self._get_connection() as conn:
            today = datetime.now().date().isoformat()
            row = conn.execute('''
                SELECT COUNT(*) FROM contact_scoring_history
                WHERE contact_id = ? AND DATE(recorded_at) = ?
            ''', (contact_id, today)).fetchone()
            return row[0] == 0

    def insert_scoring_history(
        self,
        contact_id: str,
        heat_score: float,
        value_score: float,
        relationship_score: float,
        priority_score: float,
        website_visits: int = 0,
        properties_viewed: int = 0,
        calls_inbound: int = 0,
        calls_outbound: int = 0,
        texts_total: int = 0,
        intent_signal_count: int = 0,
        sync_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Insert a scoring history record with trend calculation.
        Returns the record ID or None if skipped (already recorded today).
        """
        # Only record once per day
        if not self.should_record_daily_score(contact_id):
            return None

        # Get previous score to calculate delta
        prev = self.get_latest_scoring(contact_id)
        heat_delta = None
        trend_direction = 'stable'

        if prev:
            heat_delta = heat_score - (prev.get('heat_score') or 0)
            if heat_delta > 5:
                trend_direction = 'warming'
            elif heat_delta < -5:
                trend_direction = 'cooling'
            else:
                trend_direction = 'stable'

        with self._get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO contact_scoring_history
                (contact_id, heat_score, value_score, relationship_score, priority_score,
                 website_visits, properties_viewed, calls_inbound, calls_outbound,
                 texts_total, intent_signal_count, heat_delta, trend_direction, sync_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                contact_id, heat_score, value_score, relationship_score, priority_score,
                website_visits, properties_viewed, calls_inbound, calls_outbound,
                texts_total, intent_signal_count, heat_delta, trend_direction, sync_id
            ))
            conn.commit()

            # Update lead with trend and last recorded timestamp
            conn.execute('''
                UPDATE leads SET
                    score_trend = ?,
                    last_score_recorded_at = ?
                WHERE id = ?
            ''', (trend_direction, datetime.now().isoformat(), contact_id))
            conn.commit()

            return cursor.lastrowid

    def get_latest_scoring(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent scoring snapshot for a contact."""
        with self._get_connection() as conn:
            row = conn.execute('''
                SELECT * FROM contact_scoring_history
                WHERE contact_id = ?
                ORDER BY recorded_at DESC LIMIT 1
            ''', (contact_id,)).fetchone()
            return dict(row) if row else None

    def get_scoring_history(
        self,
        contact_id: str,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get scoring history for a contact over the specified days."""
        with self._get_connection() as conn:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            rows = conn.execute('''
                SELECT * FROM contact_scoring_history
                WHERE contact_id = ? AND recorded_at >= ?
                ORDER BY recorded_at DESC
                LIMIT ?
            ''', (contact_id, cutoff, limit)).fetchall()
            return [dict(row) for row in rows]

    def calculate_heat_score_7d_avg(self, contact_id: str) -> Optional[float]:
        """Calculate the 7-day average heat score for a contact."""
        history = self.get_scoring_history(contact_id, days=7)
        if not history:
            return None
        scores = [h.get('heat_score', 0) for h in history]
        return round(sum(scores) / len(scores), 1) if scores else None

    # ==========================================
    # CONTACT COMMUNICATIONS OPERATIONS
    # ==========================================

    def communication_exists(self, comm_id: str) -> bool:
        """Check if a communication record already exists."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT COUNT(*) FROM contact_communications WHERE id = ?',
                (comm_id,)
            ).fetchone()
            return row[0] > 0

    def insert_communication(
        self,
        comm_id: str,
        contact_id: str,
        comm_type: str,
        direction: str,
        occurred_at: str,
        duration_seconds: Optional[int] = None,
        fub_id: Optional[str] = None,
        fub_user_name: Optional[str] = None,
        status: Optional[str] = None
    ) -> bool:
        """Insert a communication record if it doesn't already exist."""
        if self.communication_exists(comm_id):
            return False

        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO contact_communications
                (id, contact_id, comm_type, direction, occurred_at,
                 duration_seconds, fub_id, fub_user_name, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                comm_id, contact_id, comm_type, direction, occurred_at,
                duration_seconds, fub_id, fub_user_name, status
            ))

            # Update total_communications count on lead
            conn.execute('''
                UPDATE leads SET total_communications = (
                    SELECT COUNT(*) FROM contact_communications WHERE contact_id = ?
                ) WHERE id = ?
            ''', (contact_id, contact_id))

            conn.commit()
            return True

    def get_communications(
        self,
        contact_id: str,
        comm_type: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get communications for a contact."""
        query = 'SELECT * FROM contact_communications WHERE contact_id = ?'
        params = [contact_id]

        if comm_type:
            query += ' AND comm_type = ?'
            params.append(comm_type)

        if days:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            query += ' AND occurred_at >= ?'
            params.append(cutoff)

        query += ' ORDER BY occurred_at DESC LIMIT ?'
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    # ==========================================
    # CONTACT EVENTS OPERATIONS
    # ==========================================

    def event_exists(self, event_id: str) -> bool:
        """Check if an event record already exists."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT COUNT(*) FROM contact_events WHERE id = ?',
                (event_id,)
            ).fetchone()
            return row[0] > 0

    def insert_event(
        self,
        event_id: str,
        contact_id: str,
        event_type: str,
        occurred_at: str,
        property_address: Optional[str] = None,
        property_price: Optional[int] = None,
        property_mls: Optional[str] = None,
        fub_event_id: Optional[str] = None
    ) -> bool:
        """Insert an event record if it doesn't already exist."""
        if self.event_exists(event_id):
            return False

        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO contact_events
                (id, contact_id, event_type, occurred_at,
                 property_address, property_price, property_mls, fub_event_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event_id, contact_id, event_type, occurred_at,
                property_address, property_price, property_mls, fub_event_id
            ))

            # Update total_events count on lead
            conn.execute('''
                UPDATE leads SET total_events = (
                    SELECT COUNT(*) FROM contact_events WHERE contact_id = ?
                ) WHERE id = ?
            ''', (contact_id, contact_id))

            conn.commit()
            return True

    def get_events(
        self,
        contact_id: str,
        event_type: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get events for a contact."""
        query = 'SELECT * FROM contact_events WHERE contact_id = ?'
        params = [contact_id]

        if event_type:
            query += ' AND event_type = ?'
            params.append(event_type)

        if days:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            query += ' AND occurred_at >= ?'
            params.append(cutoff)

        query += ' ORDER BY occurred_at DESC LIMIT ?'
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    # ==========================================
    # ACTIVITY TIMELINE OPERATIONS
    # ==========================================

    def get_activity_timeline(
        self,
        contact_id: str,
        days: int = 30,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get combined activity timeline (communications + events) for a contact.
        Returns items sorted by date descending.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT
                    'communication' as activity_category,
                    id,
                    contact_id,
                    comm_type as activity_type,
                    direction,
                    occurred_at,
                    duration_seconds,
                    fub_user_name,
                    status,
                    NULL as property_address,
                    NULL as property_price,
                    NULL as property_mls
                FROM contact_communications
                WHERE contact_id = ? AND occurred_at >= ?

                UNION ALL

                SELECT
                    'event' as activity_category,
                    id,
                    contact_id,
                    event_type as activity_type,
                    NULL as direction,
                    occurred_at,
                    NULL as duration_seconds,
                    NULL as fub_user_name,
                    NULL as status,
                    property_address,
                    property_price,
                    property_mls
                FROM contact_events
                WHERE contact_id = ? AND occurred_at >= ?

                ORDER BY occurred_at DESC
                LIMIT ?
            ''', (contact_id, cutoff, contact_id, cutoff, limit)).fetchall()

            return [dict(row) for row in rows]

    # ==========================================
    # IDX PROPERTY CACHE OPERATIONS
    # ==========================================

    IDX_BASE_URL = "https://www.smokymountainhomes4sale.com/property"

    def get_idx_property_url(self, mls_number: str) -> str:
        """Generate IDX property URL from MLS number."""
        return f"{self.IDX_BASE_URL}/{mls_number}"

    def get_idx_cache(self, mls_number: str) -> Optional[Dict[str, Any]]:
        """Get cached IDX property data by MLS number."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM idx_property_cache WHERE mls_number = ?',
                (mls_number,)
            ).fetchone()
            return dict(row) if row else None

    def upsert_idx_cache(
        self,
        mls_number: str,
        address: str,
        city: Optional[str] = None,
        price: Optional[int] = None,
        status: Optional[str] = None
    ):
        """Insert or update IDX property cache entry."""
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO idx_property_cache (mls_number, address, city, price, status, last_updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(mls_number) DO UPDATE SET
                    address = excluded.address,
                    city = excluded.city,
                    price = COALESCE(excluded.price, price),
                    status = COALESCE(excluded.status, status),
                    last_updated = CURRENT_TIMESTAMP
            ''', (mls_number, address, city, price, status))
            conn.commit()

    def get_uncached_mls_numbers(self, limit: int = 100) -> List[str]:
        """Get MLS numbers from contact_events that aren't in the cache."""
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT DISTINCT e.property_mls
                FROM contact_events e
                LEFT JOIN idx_property_cache c ON e.property_mls = c.mls_number
                WHERE e.property_mls IS NOT NULL
                    AND c.mls_number IS NULL
                LIMIT ?
            ''', (limit,)).fetchall()
            return [row[0] for row in rows]

    # ==========================================
    # PROPERTIES VIEWED OPERATIONS
    # ==========================================

    def get_contact_property_summary(self, contact_id: str) -> List[Dict[str, Any]]:
        """
        Get aggregated property view history for a contact.
        Returns properties this contact has viewed with view counts,
        favorite/share status, and who else is viewing each property.
        Joins with properties table AND idx_property_cache to get addresses.
        """
        with self._get_connection() as conn:
            # Get all property events for this contact, aggregated by property
            # LEFT JOIN with both properties table and idx_property_cache
            rows = conn.execute('''
                SELECT
                    COALESCE(e.property_address, p.address, c.address) as property_address,
                    COALESCE(MAX(e.property_price), p.price, c.price) as property_price,
                    e.property_mls,
                    COUNT(CASE WHEN e.event_type = 'property_view' THEN 1 END) as view_count,
                    MAX(CASE WHEN e.event_type = 'property_favorite' THEN 1 ELSE 0 END) as is_favorited,
                    MAX(CASE WHEN e.event_type = 'property_share' THEN 1 ELSE 0 END) as is_shared,
                    MIN(e.occurred_at) as first_viewed,
                    MAX(e.occurred_at) as last_viewed
                FROM contact_events e
                LEFT JOIN properties p ON e.property_mls = p.mls_number
                LEFT JOIN idx_property_cache c ON e.property_mls = c.mls_number
                WHERE e.contact_id = ?
                    AND (e.property_mls IS NOT NULL OR e.property_address IS NOT NULL)
                GROUP BY COALESCE(e.property_mls, e.property_address)
                ORDER BY MAX(e.occurred_at) DESC
            ''', (contact_id,)).fetchall()

            results = []
            for row in rows:
                prop_data = dict(row)

                # Find other contacts viewing this property (use MLS if no address)
                property_identifier = prop_data['property_address'] or prop_data['property_mls']
                other_contacts = self.get_property_interested_contacts(
                    property_identifier,
                    exclude_contact_id=contact_id
                ) if property_identifier else []
                prop_data['other_contacts'] = other_contacts
                prop_data['other_count'] = len(other_contacts)

                results.append(prop_data)

            return results

    def get_property_interested_contacts(
        self,
        property_identifier: str,
        exclude_contact_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get all contacts who have viewed/favorited/shared a property.
        Used for "who else is viewing" feature.

        Args:
            property_identifier: Property address or MLS number
            exclude_contact_id: Contact ID to exclude (the current contact)
            limit: Max number of contacts to return
        """
        with self._get_connection() as conn:
            query = '''
                SELECT DISTINCT
                    l.id as contact_id,
                    l.first_name,
                    l.last_name,
                    l.heat_score,
                    l.priority_score,
                    COUNT(e.id) as interaction_count,
                    MAX(CASE WHEN e.event_type = 'property_favorite' THEN 1 ELSE 0 END) as has_favorited,
                    MAX(e.occurred_at) as last_interaction
                FROM contact_events e
                JOIN leads l ON e.contact_id = l.id
                WHERE (e.property_address = ? OR e.property_mls = ?)
            '''
            params = [property_identifier, property_identifier]

            if exclude_contact_id:
                query += ' AND e.contact_id != ?'
                params.append(exclude_contact_id)

            query += '''
                GROUP BY l.id, l.first_name, l.last_name, l.heat_score, l.priority_score
                ORDER BY MAX(e.occurred_at) DESC
                LIMIT ?
            '''
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_contact_trend_summary(self, contact_id: str) -> Dict[str, Any]:
        """
        Get a summary of contact's trend data for dashboard display.
        """
        # Get latest scoring
        latest = self.get_latest_scoring(contact_id)

        # Get 7-day average
        avg_7d = self.calculate_heat_score_7d_avg(contact_id)

        # Get scoring history for trend
        history = self.get_scoring_history(contact_id, days=7)

        # Calculate trend direction from history
        trend = 'stable'
        if len(history) >= 2:
            recent = history[0].get('heat_score', 0)
            older = history[-1].get('heat_score', 0)
            delta = recent - older
            if delta > 5:
                trend = 'warming'
            elif delta < -5:
                trend = 'cooling'

        # Get recent activity counts
        with self._get_connection() as conn:
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()

            comms_week = conn.execute('''
                SELECT COUNT(*) FROM contact_communications
                WHERE contact_id = ? AND occurred_at >= ?
            ''', (contact_id, week_ago)).fetchone()[0]

            events_week = conn.execute('''
                SELECT COUNT(*) FROM contact_events
                WHERE contact_id = ? AND occurred_at >= ?
            ''', (contact_id, week_ago)).fetchone()[0]

        return {
            'trend_direction': trend,
            'heat_score_7d_avg': avg_7d,
            'heat_delta': latest.get('heat_delta') if latest else None,
            'communications_this_week': comms_week,
            'events_this_week': events_week,
            'scoring_history': history[:7]  # Last 7 records for mini-chart
        }

    # ==========================================
    # PROPERTY CHANGES OPERATIONS
    # ==========================================

    def insert_property_change(
        self,
        property_address: str,
        change_type: str,
        old_value: str,
        new_value: str,
        property_id: Optional[str] = None,
        change_amount: Optional[int] = None,
        source: Optional[str] = None,
        notion_url: Optional[str] = None
    ) -> str:
        """
        Insert a property change record.

        Args:
            property_address: Address of the property
            change_type: Type of change ('price', 'status', 'dom', 'views', 'saves')
            old_value: Previous value as string
            new_value: New value as string
            property_id: Optional Notion page ID or internal property ID
            change_amount: Optional numeric change amount (for prices)
            source: Source of the data (redfin, zillow, etc.)
            notion_url: Optional link to Notion page

        Returns:
            The ID of the inserted record
        """
        import uuid
        change_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO property_changes
                (id, property_id, property_address, change_type, old_value, new_value,
                 change_amount, detected_at, notified, source, notion_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            ''', (
                change_id, property_id, property_address, change_type,
                old_value, new_value, change_amount,
                datetime.now().isoformat(), source, notion_url
            ))
            conn.commit()

        return change_id

    def get_property_changes(
        self,
        hours: int = 24,
        change_type: Optional[str] = None,
        notified_only: bool = False,
        unnotified_only: bool = False,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get property changes within the specified time window.

        Args:
            hours: Number of hours to look back (default 24)
            change_type: Optional filter by change type
            notified_only: Only return changes that have been notified
            unnotified_only: Only return changes that haven't been notified
            limit: Maximum number of records to return
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        query = 'SELECT * FROM property_changes WHERE detected_at >= ?'
        params = [cutoff]

        if change_type:
            query += ' AND change_type = ?'
            params.append(change_type)

        if notified_only:
            query += ' AND notified = 1'
        elif unnotified_only:
            query += ' AND notified = 0'

        query += ' ORDER BY detected_at DESC LIMIT ?'
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_todays_changes(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get today's property changes organized by type.

        Returns:
            Dict with keys 'price', 'status', 'other' containing lists of changes
        """
        # Get start of today (midnight)
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = today_start.isoformat()

        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM property_changes
                WHERE detected_at >= ?
                ORDER BY detected_at DESC
            ''', (cutoff,)).fetchall()

            changes = {
                'price': [],
                'status': [],
                'other': []
            }

            for row in rows:
                change = dict(row)
                change_type = change.get('change_type', '')

                if change_type == 'price':
                    changes['price'].append(change)
                elif change_type == 'status':
                    changes['status'].append(change)
                else:
                    changes['other'].append(change)

            return changes

    def mark_changes_notified(self, change_ids: List[str]) -> int:
        """
        Mark changes as notified (included in a report).

        Args:
            change_ids: List of change IDs to mark

        Returns:
            Number of records updated
        """
        if not change_ids:
            return 0

        with self._get_connection() as conn:
            placeholders = ', '.join(['?' for _ in change_ids])
            cursor = conn.execute(f'''
                UPDATE property_changes
                SET notified = 1
                WHERE id IN ({placeholders})
            ''', change_ids)
            conn.commit()
            return cursor.rowcount

    def get_change_summary(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get a summary of property changes for reporting.

        Returns:
            Summary dict with counts and notable changes
        """
        changes = self.get_property_changes(hours=hours)

        price_increases = []
        price_decreases = []
        status_changes = []

        for change in changes:
            if change['change_type'] == 'price':
                amount = change.get('change_amount') or 0
                if amount > 0:
                    price_increases.append(change)
                else:
                    price_decreases.append(change)
            elif change['change_type'] == 'status':
                status_changes.append(change)

        return {
            'total_changes': len(changes),
            'price_increases': price_increases,
            'price_decreases': price_decreases,
            'status_changes': status_changes,
            'price_increase_count': len(price_increases),
            'price_decrease_count': len(price_decreases),
            'status_change_count': len(status_changes)
        }
