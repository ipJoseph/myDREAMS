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

            # Seed default system settings
            self._seed_default_settings(conn)
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
            ("properties_shared", "INTEGER DEFAULT 0"),  # Properties shared count
            ("emails_received", "INTEGER DEFAULT 0"),   # Emails received
            ("emails_sent", "INTEGER DEFAULT 0"),       # Emails sent
            # Assignment tracking columns
            ("assigned_user_id", "INTEGER"),            # FUB user ID
            ("assigned_user_name", "TEXT"),             # Cached user name for display
            ("assigned_at", "TEXT"),                    # When assigned to current user
            # Reassignment tracking
            ("reassigned_at", "TEXT"),                  # When lead was reassigned away from user
            ("reassigned_from_user_id", "INTEGER"),     # Previous user ID before reassignment
            ("reassigned_reason", "TEXT"),              # 'round_robin', 'transfer', 'deleted', 'unknown'
        ]

        for col_name, col_type in new_lead_columns:
            if col_name not in existing_cols:
                try:
                    conn.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column {col_name} to leads table")
                except sqlite3.OperationalError:
                    pass  # Column already exists

        # Apply migrations for properties table (spatial enrichment columns)
        cursor = conn.execute("PRAGMA table_info(properties)")
        existing_prop_cols = {row[1] for row in cursor.fetchall()}

        new_property_columns = [
            ("school_district", "TEXT"),
            ("flood_zone", "TEXT"),
            ("flood_zone_subtype", "TEXT"),
            ("flood_factor", "INTEGER"),
            ("flood_sfha", "INTEGER DEFAULT 0"),
            ("elevation_feet", "INTEGER"),
            ("slope_percent", "REAL"),
            ("aspect", "TEXT"),
            ("view_potential", "INTEGER"),
            ("wildfire_risk", "TEXT"),
            ("wildfire_score", "INTEGER"),
            ("spatial_enriched_at", "TEXT"),
        ]

        for col_name, col_type in new_property_columns:
            if col_name not in existing_prop_cols:
                try:
                    conn.execute(f"ALTER TABLE properties ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column {col_name} to properties table")
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
            school_district TEXT,
            -- Spatial enrichment fields (NC OneMap)
            flood_zone TEXT,                 -- FEMA zone: X, A, AE, VE, etc.
            flood_zone_subtype TEXT,         -- Zone subtype (shaded, floodway)
            flood_factor INTEGER,            -- Risk score 1-10
            flood_sfha INTEGER DEFAULT 0,    -- Special Flood Hazard Area (1=yes)
            elevation_feet INTEGER,          -- Elevation in feet
            slope_percent REAL,              -- Terrain slope percentage
            aspect TEXT,                     -- Facing direction: N, NE, E, etc.
            view_potential INTEGER,          -- Mountain view score 1-10
            wildfire_risk TEXT,              -- Risk category: Low, Moderate, High, Very High
            wildfire_score INTEGER,          -- Risk score 1-10
            spatial_enriched_at TEXT,        -- When spatial data was last updated
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

        -- Contact daily activity (aggregated stats per contact per day)
        CREATE TABLE IF NOT EXISTS contact_daily_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id TEXT NOT NULL,
            activity_date TEXT NOT NULL,  -- YYYY-MM-DD format
            -- Daily activity counts
            website_visits INTEGER DEFAULT 0,
            properties_viewed INTEGER DEFAULT 0,
            properties_favorited INTEGER DEFAULT 0,
            properties_shared INTEGER DEFAULT 0,
            calls_inbound INTEGER DEFAULT 0,
            calls_outbound INTEGER DEFAULT 0,
            texts_inbound INTEGER DEFAULT 0,
            texts_outbound INTEGER DEFAULT 0,
            emails_received INTEGER DEFAULT 0,
            emails_sent INTEGER DEFAULT 0,
            -- Score snapshot at end of day
            heat_score_snapshot REAL,
            value_score_snapshot REAL,
            relationship_score_snapshot REAL,
            priority_score_snapshot REAL,
            -- Metadata
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(contact_id, activity_date),
            FOREIGN KEY (contact_id) REFERENCES leads(id)
        );

        -- Contact actions (persistent action tracking across syncs)
        CREATE TABLE IF NOT EXISTS contact_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id TEXT NOT NULL,
            action_type TEXT NOT NULL,    -- 'call', 'email', 'text', 'meeting', 'follow_up', 'showing', 'note'
            description TEXT,
            due_date TEXT,                -- YYYY-MM-DD format
            priority INTEGER DEFAULT 3,   -- 1 (highest) to 5 (lowest)
            completed_at TEXT,
            completed_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT DEFAULT 'user',  -- 'user', 'system', 'sync'
            FOREIGN KEY (contact_id) REFERENCES leads(id)
        );

        -- Scoring runs (audit trail for scoring operations)
        CREATE TABLE IF NOT EXISTS scoring_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            contacts_processed INTEGER DEFAULT 0,
            contacts_scored INTEGER DEFAULT 0,
            contacts_new INTEGER DEFAULT 0,
            contacts_updated INTEGER DEFAULT 0,
            run_duration_seconds REAL,
            fub_api_calls INTEGER DEFAULT 0,
            config_snapshot TEXT,         -- JSON of scoring weights used
            source TEXT DEFAULT 'scheduled',  -- 'scheduled', 'manual', 'api'
            status TEXT DEFAULT 'running',    -- 'running', 'success', 'partial', 'failed'
            error_message TEXT,
            notes TEXT
        );

        -- Contact workflow tracking (Phase 4: Pipeline)
        CREATE TABLE IF NOT EXISTS contact_workflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id TEXT NOT NULL UNIQUE,
            current_stage TEXT NOT NULL DEFAULT 'new_lead',
            stage_entered_at TEXT DEFAULT CURRENT_TIMESTAMP,
            stage_history TEXT,              -- JSON array of {stage, entered_at, exited_at, duration_days}
            workflow_status TEXT DEFAULT 'active',  -- 'active', 'paused', 'completed', 'lost'
            requirements_confidence REAL DEFAULT 0,
            days_in_current_stage INTEGER DEFAULT 0,
            last_stage_change_at TEXT,
            auto_stage_enabled INTEGER DEFAULT 1,  -- Allow automatic stage transitions
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES leads(id)
        );

        -- Consolidated contact requirements (Phase 5: Requirements Consolidation)
        -- Each field tracks its source and confidence level
        CREATE TABLE IF NOT EXISTS contact_requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id TEXT NOT NULL UNIQUE,

            -- Price requirements
            price_min INTEGER,
            price_min_source TEXT,           -- 'intake', 'behavioral', 'notes', 'override'
            price_min_confidence REAL DEFAULT 0,
            price_max INTEGER,
            price_max_source TEXT,
            price_max_confidence REAL DEFAULT 0,

            -- Size requirements
            beds_min INTEGER,
            beds_min_source TEXT,
            beds_min_confidence REAL DEFAULT 0,
            baths_min REAL,
            baths_min_source TEXT,
            baths_min_confidence REAL DEFAULT 0,
            sqft_min INTEGER,
            sqft_min_source TEXT,
            sqft_min_confidence REAL DEFAULT 0,
            acreage_min REAL,
            acreage_min_source TEXT,
            acreage_min_confidence REAL DEFAULT 0,

            -- Location requirements (JSON arrays)
            counties TEXT,                   -- JSON array of county names
            counties_source TEXT,
            counties_confidence REAL DEFAULT 0,
            cities TEXT,                     -- JSON array of city names
            cities_source TEXT,
            cities_confidence REAL DEFAULT 0,

            -- Property type requirements
            property_types TEXT,             -- JSON array
            property_types_source TEXT,
            property_types_confidence REAL DEFAULT 0,

            -- Feature requirements (JSON arrays)
            must_have_features TEXT,         -- JSON array of required features
            must_have_source TEXT,
            must_have_confidence REAL DEFAULT 0,
            nice_to_have_features TEXT,      -- JSON array of preferred features
            deal_breakers TEXT,              -- JSON array of deal breakers
            deal_breakers_source TEXT,
            deal_breakers_confidence REAL DEFAULT 0,

            -- Views and water (JSON arrays)
            views_required TEXT,
            views_source TEXT,
            views_confidence REAL DEFAULT 0,
            water_features TEXT,
            water_source TEXT,
            water_confidence REAL DEFAULT 0,

            -- Timeline
            urgency TEXT,
            urgency_source TEXT,
            urgency_confidence REAL DEFAULT 0,
            move_in_date TEXT,

            -- Financing
            financing_status TEXT,
            financing_source TEXT,
            financing_confidence REAL DEFAULT 0,
            pre_approval_amount INTEGER,

            -- Agent overrides (JSON object of field -> value)
            agent_overrides TEXT,

            -- Metadata
            overall_confidence REAL DEFAULT 0,   -- Weighted average of all field confidences
            data_completeness REAL DEFAULT 0,    -- Percentage of fields populated
            last_consolidated_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES leads(id)
        );

        -- Requirements change audit trail
        CREATE TABLE IF NOT EXISTS requirements_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            old_source TEXT,
            new_source TEXT,
            old_confidence REAL,
            new_confidence REAL,
            change_reason TEXT,              -- 'consolidation', 'override', 'intake_update', 'behavioral_update'
            changed_by TEXT,                 -- 'system' or agent name
            changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES leads(id)
        );

        -- Alert log (track sent alerts to prevent duplicates)
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,        -- 'new_listing', 'price_drop', 'weekly_summary', 'monthly_report'
            contact_id TEXT,
            property_id TEXT,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            email_to TEXT,
            status TEXT DEFAULT 'sent',      -- 'sent', 'failed', 'bounced'
            error_message TEXT,
            metadata TEXT,                   -- JSON for additional context
            UNIQUE(alert_type, contact_id, property_id)
        );

        -- Market snapshots (weekly market state for trend comparison)
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,     -- YYYY-MM-DD format
            county TEXT,                     -- NULL = all counties combined
            total_active INTEGER DEFAULT 0,
            new_listings INTEGER DEFAULT 0,
            avg_price INTEGER,
            median_price INTEGER,
            avg_dom REAL,                    -- Average days on market
            pending_count INTEGER DEFAULT 0,
            sold_count INTEGER DEFAULT 0,
            price_reduced_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(snapshot_date, county)
        );

        -- System settings (configurable thresholds and automation behavior)
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            value_type TEXT DEFAULT 'string',  -- 'string', 'integer', 'float', 'boolean', 'json'
            description TEXT,
            category TEXT DEFAULT 'general',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        );

        -- FUB Users (cache of team members for assignment display)
        CREATE TABLE IF NOT EXISTS fub_users (
            id INTEGER PRIMARY KEY,           -- FUB user ID
            name TEXT NOT NULL,
            email TEXT,
            role TEXT,
            phone TEXT,
            picture_url TEXT,
            is_active INTEGER DEFAULT 1,
            last_synced_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Assignment History (track lead assignment changes)
        CREATE TABLE IF NOT EXISTS assignment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id TEXT NOT NULL,
            assigned_from_user_id INTEGER,    -- NULL if new assignment
            assigned_from_user_name TEXT,
            assigned_to_user_id INTEGER NOT NULL,
            assigned_to_user_name TEXT NOT NULL,
            assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'sync',       -- 'sync', 'manual', 'round_robin', 'transfer'
            notes TEXT,
            FOREIGN KEY (contact_id) REFERENCES leads(id)
        );

        -- Pursuits: Buyer + Property Portfolio (maps to FUB Deals)
        CREATE TABLE IF NOT EXISTS pursuits (
            id TEXT PRIMARY KEY,
            buyer_id TEXT NOT NULL,               -- FK to leads
            intake_form_id TEXT,                  -- FK to intake_forms (future)
            fub_deal_id INTEGER,                  -- FUB deal ID if synced
            name TEXT,                            -- "John Smith — Primary Residence"
            status TEXT DEFAULT 'active',         -- active, paused, converted, abandoned
            criteria_summary TEXT,                -- "3BR, $300-400K, Franklin"
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES leads(id)
        );

        -- Properties within a Pursuit
        CREATE TABLE IF NOT EXISTS pursuit_properties (
            id TEXT PRIMARY KEY,
            pursuit_id TEXT NOT NULL,             -- FK to pursuits
            property_id TEXT NOT NULL,            -- FK to properties
            status TEXT DEFAULT 'suggested',      -- suggested, sent, viewed, favorited, rejected
            source TEXT DEFAULT 'agent_added',    -- idx_saved, agent_added, auto_match
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            sent_at TEXT,
            viewed_at TEXT,
            notes TEXT,
            FOREIGN KEY (pursuit_id) REFERENCES pursuits(id),
            FOREIGN KEY (property_id) REFERENCES properties(id),
            UNIQUE(pursuit_id, property_id)
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
        -- Spatial enrichment indexes
        CREATE INDEX IF NOT EXISTS idx_properties_flood_zone ON properties(flood_zone);
        CREATE INDEX IF NOT EXISTS idx_properties_flood_factor ON properties(flood_factor);
        CREATE INDEX IF NOT EXISTS idx_properties_elevation ON properties(elevation_feet);
        CREATE INDEX IF NOT EXISTS idx_properties_view_potential ON properties(view_potential);
        CREATE INDEX IF NOT EXISTS idx_properties_wildfire ON properties(wildfire_risk);
        CREATE INDEX IF NOT EXISTS idx_properties_spatial_enriched ON properties(spatial_enriched_at);
        CREATE INDEX IF NOT EXISTS idx_properties_lat_lng ON properties(latitude, longitude);
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
        -- Contact daily activity indexes
        CREATE INDEX IF NOT EXISTS idx_daily_activity_contact ON contact_daily_activity(contact_id, activity_date DESC);
        CREATE INDEX IF NOT EXISTS idx_daily_activity_date ON contact_daily_activity(activity_date DESC);
        -- Contact actions indexes
        CREATE INDEX IF NOT EXISTS idx_actions_contact ON contact_actions(contact_id);
        CREATE INDEX IF NOT EXISTS idx_actions_due ON contact_actions(due_date) WHERE completed_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_actions_pending ON contact_actions(completed_at) WHERE completed_at IS NULL;
        -- Scoring runs indexes
        CREATE INDEX IF NOT EXISTS idx_scoring_runs_date ON scoring_runs(run_at DESC);
        CREATE INDEX IF NOT EXISTS idx_scoring_runs_status ON scoring_runs(status);
        -- Contact workflow indexes
        CREATE INDEX IF NOT EXISTS idx_workflow_contact ON contact_workflow(contact_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_stage ON contact_workflow(current_stage);
        CREATE INDEX IF NOT EXISTS idx_workflow_status ON contact_workflow(workflow_status);
        -- Contact requirements indexes
        CREATE INDEX IF NOT EXISTS idx_requirements_contact ON contact_requirements(contact_id);
        CREATE INDEX IF NOT EXISTS idx_requirements_changes_contact ON requirements_changes(contact_id);
        CREATE INDEX IF NOT EXISTS idx_requirements_changes_field ON requirements_changes(field_name);
        -- Alert log indexes
        CREATE INDEX IF NOT EXISTS idx_alert_log_type ON alert_log(alert_type);
        CREATE INDEX IF NOT EXISTS idx_alert_log_contact ON alert_log(contact_id);
        CREATE INDEX IF NOT EXISTS idx_alert_log_property ON alert_log(property_id);
        CREATE INDEX IF NOT EXISTS idx_alert_log_sent ON alert_log(sent_at DESC);
        -- Market snapshots indexes
        CREATE INDEX IF NOT EXISTS idx_market_snapshots_date ON market_snapshots(snapshot_date DESC);
        CREATE INDEX IF NOT EXISTS idx_market_snapshots_county ON market_snapshots(county);
        -- System settings indexes
        CREATE INDEX IF NOT EXISTS idx_system_settings_category ON system_settings(category);
        -- Assignment tracking indexes
        CREATE INDEX IF NOT EXISTS idx_leads_assigned_user ON leads(assigned_user_id);
        CREATE INDEX IF NOT EXISTS idx_leads_assigned_at ON leads(assigned_at DESC);
        CREATE INDEX IF NOT EXISTS idx_assignment_history_contact ON assignment_history(contact_id, assigned_at DESC);
        CREATE INDEX IF NOT EXISTS idx_assignment_history_to_user ON assignment_history(assigned_to_user_id, assigned_at DESC);
        CREATE INDEX IF NOT EXISTS idx_assignment_history_from_user ON assignment_history(assigned_from_user_id);
        -- Pursuit indexes
        CREATE INDEX IF NOT EXISTS idx_pursuits_buyer ON pursuits(buyer_id);
        CREATE INDEX IF NOT EXISTS idx_pursuits_status ON pursuits(status);
        CREATE INDEX IF NOT EXISTS idx_pursuits_fub_deal ON pursuits(fub_deal_id);
        CREATE INDEX IF NOT EXISTS idx_pursuit_properties_pursuit ON pursuit_properties(pursuit_id);
        CREATE INDEX IF NOT EXISTS idx_pursuit_properties_property ON pursuit_properties(property_id);
        CREATE INDEX IF NOT EXISTS idx_pursuit_properties_status ON pursuit_properties(status);
        '''

    def _seed_default_settings(self, conn) -> None:
        """Insert default system settings if they don't exist."""
        default_settings = [
            # Alert settings
            ('new_listing_match_threshold', '60', 'integer', 'alerts',
             'Minimum match score (0-100) to trigger new listing alerts'),
            ('alert_lookback_hours', '24', 'integer', 'alerts',
             'Hours to look back for new listings'),
            ('max_properties_per_alert', '10', 'integer', 'alerts',
             'Maximum properties in a single alert email'),
            ('new_listing_alerts_enabled', 'true', 'boolean', 'alerts',
             'Enable/disable new listing alerts'),
            ('price_drop_alerts_enabled', 'true', 'boolean', 'alerts',
             'Enable/disable price drop alerts'),
            ('price_drop_match_threshold', '50', 'integer', 'alerts',
             'Minimum match score (0-100) to trigger price drop alerts'),
            ('min_price_drop_pct', '5.0', 'float', 'alerts',
             'Minimum price drop percentage to trigger alert'),
            ('alerts_global_enabled', 'true', 'boolean', 'alerts',
             'Master switch for all alerts'),
            # Report settings
            ('weekly_summary_enabled', 'true', 'boolean', 'reports',
             'Enable/disable weekly market summary'),
            ('monthly_report_enabled', 'true', 'boolean', 'reports',
             'Enable/disable monthly lead report'),
            # Integration settings
            ('fub_note_push_enabled', 'true', 'boolean', 'integrations',
             'Push matched properties as notes to FUB contacts'),
        ]

        for key, value, value_type, category, description in default_settings:
            conn.execute('''
                INSERT OR IGNORE INTO system_settings (key, value, value_type, category, description)
                VALUES (?, ?, ?, ?, ?)
            ''', [key, value, value_type, category, description])

    # ==========================================
    # SYSTEM SETTINGS OPERATIONS
    # ==========================================

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a system setting value with automatic type conversion.

        Args:
            key: Setting key
            default: Default value if setting doesn't exist

        Returns:
            Setting value converted to appropriate type
        """
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT value, value_type FROM system_settings WHERE key = ?',
                (key,)
            ).fetchone()

            if not row:
                return default

            value = row['value']
            value_type = row['value_type']

            # Convert based on type
            if value_type == 'integer':
                return int(value)
            elif value_type == 'float':
                return float(value)
            elif value_type == 'boolean':
                return value.lower() in ('true', '1', 'yes')
            elif value_type == 'json':
                return json.loads(value)
            else:
                return value

    def set_setting(self, key: str, value: Any, updated_by: str = None) -> bool:
        """
        Update a system setting value.

        Args:
            key: Setting key
            value: New value (will be converted to string for storage)
            updated_by: Who made the change

        Returns:
            True if successful
        """
        with self._get_connection() as conn:
            # Convert value to string for storage
            if isinstance(value, bool):
                str_value = 'true' if value else 'false'
            elif isinstance(value, (dict, list)):
                str_value = json.dumps(value)
            else:
                str_value = str(value)

            conn.execute('''
                UPDATE system_settings
                SET value = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                WHERE key = ?
            ''', [str_value, updated_by, key])
            conn.commit()
            return True

    def get_all_settings(self, category: str = None) -> List[Dict[str, Any]]:
        """
        Get all system settings, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of setting dictionaries with converted values
        """
        with self._get_connection() as conn:
            if category:
                rows = conn.execute(
                    'SELECT * FROM system_settings WHERE category = ? ORDER BY key',
                    (category,)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM system_settings ORDER BY category, key'
                ).fetchall()

            settings = []
            for row in rows:
                setting = dict(row)
                # Convert value based on type
                value_type = setting['value_type']
                raw_value = setting['value']

                if value_type == 'integer':
                    setting['converted_value'] = int(raw_value)
                elif value_type == 'float':
                    setting['converted_value'] = float(raw_value)
                elif value_type == 'boolean':
                    setting['converted_value'] = raw_value.lower() in ('true', '1', 'yes')
                elif value_type == 'json':
                    setting['converted_value'] = json.loads(raw_value)
                else:
                    setting['converted_value'] = raw_value

                settings.append(setting)

            return settings

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
        limit: int = 100,
        user_id: Optional[int] = None,
        view: str = 'all'
    ) -> List[Dict[str, Any]]:
        """
        Get contacts sorted by priority score with optional filtering.

        Args:
            min_priority: Minimum priority score
            limit: Maximum contacts to return
            user_id: Filter by assigned user ID (required for 'my_leads' view)
            view: Filter view - 'all', 'my_leads', 'ponds', 'agents', 'unassigned'
        """
        with self._get_connection() as conn:
            query = 'SELECT * FROM leads WHERE priority_score >= ?'
            params = [min_priority]

            # Apply view filter
            if view == 'my_leads' and user_id:
                query += ' AND assigned_user_id = ?'
                params.append(user_id)
            elif view == 'ponds':
                # Ponds = contacts assigned to Ava Cares (user 12) or other pond managers
                query += ' AND assigned_user_id = 12'
            elif view == 'agents':
                # Agents/Vendors/Lenders stage
                query += " AND stage = 'Agents/Vendors/Lendors'"
            elif view == 'unassigned':
                query += ' AND (assigned_user_id IS NULL OR assigned_user_id = 0)'
            elif view == 'team':
                # All team contacts except ponds and unassigned
                query += ' AND assigned_user_id IS NOT NULL AND assigned_user_id != 12'
            # 'all' = no additional filter

            query += ' ORDER BY priority_score DESC LIMIT ?'
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_contact_stats(
        self,
        user_id: Optional[int] = None,
        view: str = 'all'
    ) -> Dict[str, Any]:
        """
        Get aggregate statistics for contacts with optional filtering.

        Args:
            user_id: Filter by assigned user ID (required for 'my_leads' view)
            view: Filter view - 'all', 'my_leads', 'ponds', 'agents', 'unassigned', 'team'
        """
        with self._get_connection() as conn:
            # Build WHERE clause based on view
            where_clause = '1=1'
            params = []

            if view == 'my_leads' and user_id:
                where_clause = 'assigned_user_id = ?'
                params = [user_id]
            elif view == 'ponds':
                where_clause = 'assigned_user_id = 12'
            elif view == 'agents':
                where_clause = "stage = 'Agents/Vendors/Lendors'"
            elif view == 'unassigned':
                where_clause = '(assigned_user_id IS NULL OR assigned_user_id = 0)'
            elif view == 'team':
                where_clause = 'assigned_user_id IS NOT NULL AND assigned_user_id != 12'

            total = conn.execute(
                f'SELECT COUNT(*) FROM leads WHERE {where_clause}', params
            ).fetchone()[0]
            hot = conn.execute(
                f'SELECT COUNT(*) FROM leads WHERE {where_clause} AND heat_score >= 75', params
            ).fetchone()[0]
            high_value = conn.execute(
                f'SELECT COUNT(*) FROM leads WHERE {where_clause} AND value_score >= 60', params
            ).fetchone()[0]
            active_week = conn.execute(
                f'SELECT COUNT(*) FROM leads WHERE {where_clause} AND days_since_activity <= 7', params
            ).fetchone()[0]
            avg_priority = conn.execute(
                f'SELECT AVG(priority_score) FROM leads WHERE {where_clause} AND priority_score > 0', params
            ).fetchone()[0] or 0
            high_intent = conn.execute(
                f'SELECT COUNT(*) FROM leads WHERE {where_clause} AND intent_signal_count >= 4', params
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
    # INTAKE FORM OPERATIONS
    # ==========================================

    def get_intake_forms_for_lead(self, lead_id: str) -> List[Dict[str, Any]]:
        """Get all intake forms for a lead."""
        with self._get_connection() as conn:
            # Try both lead_id formats (UUID and fub_id)
            rows = conn.execute('''
                SELECT * FROM intake_forms
                WHERE lead_id = ? OR lead_id = (
                    SELECT fub_id FROM leads WHERE id = ?
                )
                ORDER BY priority ASC, updated_at DESC
            ''', (lead_id, lead_id)).fetchall()
            return [dict(row) for row in rows]

    def delete_intake_form(self, form_id: str) -> bool:
        """
        Delete an intake form by ID.

        Args:
            form_id: The intake form ID to delete

        Returns:
            True if deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                'DELETE FROM intake_forms WHERE id = ?',
                (form_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_stated_requirements(self, lead_id: str) -> Dict[str, Any]:
        """
        Get consolidated stated requirements from intake forms.
        Merges multiple intake forms into a single requirements dict.
        Primary home needs take priority over investment needs.
        """
        forms = self.get_intake_forms_for_lead(lead_id)

        if not forms:
            return {
                'has_intake_form': False,
                'min_price': None,
                'max_price': None,
                'min_beds': None,
                'max_beds': None,
                'min_baths': None,
                'max_baths': None,
                'min_sqft': None,
                'max_sqft': None,
                'min_acreage': None,
                'max_acreage': None,
                'counties': [],
                'cities': [],
                'property_types': [],
                'must_have_features': [],
                'deal_breakers': [],
                'confidence': 0.0
            }

        # Prioritize primary_home over investment
        primary = next((f for f in forms if f.get('need_type') == 'primary_home'), None)
        form = primary or forms[0]

        import json

        def parse_json_list(val):
            if not val:
                return []
            if isinstance(val, list):
                return val
            try:
                result = json.loads(val)
                return result if isinstance(result, list) else []
            except:
                return []

        return {
            'has_intake_form': True,
            'need_type': form.get('need_type'),
            'min_price': form.get('min_price'),
            'max_price': form.get('max_price'),
            'min_beds': form.get('min_beds'),
            'max_beds': form.get('max_beds'),
            'min_baths': form.get('min_baths'),
            'max_baths': form.get('max_baths'),
            'min_sqft': form.get('min_sqft'),
            'max_sqft': form.get('max_sqft'),
            'min_acreage': form.get('min_acreage'),
            'max_acreage': form.get('max_acreage'),
            'counties': parse_json_list(form.get('counties')),
            'cities': parse_json_list(form.get('cities')),
            'property_types': parse_json_list(form.get('property_types')),
            'must_have_features': parse_json_list(form.get('must_have_features')),
            'nice_to_have': parse_json_list(form.get('nice_to_have_features')),
            'deal_breakers': parse_json_list(form.get('deal_breakers')),
            'views_required': parse_json_list(form.get('views_required')),
            'water_features': parse_json_list(form.get('water_features')),
            'urgency': form.get('urgency'),
            'financing_status': form.get('financing_status'),
            'pre_approval_amount': form.get('pre_approval_amount'),
            'confidence': (form.get('confidence_score') or 50) / 100.0
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

    def find_matching_properties(
        self,
        lead_id: str,
        min_score: float = 40.0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Find properties that match a buyer's stated and behavioral preferences.

        Data sources (in priority order):
        1. Intake forms (highest priority - explicit stated requirements)
        2. Leads table (mid priority - may have some requirements)
        3. Behavioral analysis (always used - weighted 60%)

        Uses weighted multi-factor scoring:
        - Price fit (30%): Property price within buyer's range
        - Location (25%): City/county matches preferred locations
        - Size (25%): Meets bedroom/bathroom requirements
        - Recency (20%): Newer listings score higher

        Returns list of matches with score breakdown.
        """
        lead = self.get_lead(lead_id)
        if not lead:
            return []

        # Get behavioral preferences
        behavioral = self.get_behavioral_preferences(lead_id)

        # Get stated requirements from intake forms (highest priority)
        intake = self.get_stated_requirements(lead_id)

        # Determine stated price range (intake form > leads table)
        stated_min = intake.get('min_price') or lead.get('min_price')
        stated_max = intake.get('max_price') or lead.get('max_price')
        behav_min, behav_max = behavioral.get('price_range') or (None, None)

        # Weighted blend: behavioral 60%, stated 40%
        min_price = None
        max_price = None

        if behav_min and stated_min:
            min_price = int(stated_min * 0.4 + behav_min * 0.6)
        elif behav_min:
            min_price = behav_min
        elif stated_min:
            min_price = stated_min

        if behav_max and stated_max:
            max_price = int(stated_max * 0.4 + behav_max * 0.6)
        elif behav_max:
            max_price = behav_max
        elif stated_max:
            max_price = stated_max

        # If we have a price range, expand it slightly for flexibility
        if min_price:
            min_price = int(min_price * 0.8)  # 20% below
        if max_price:
            max_price = int(max_price * 1.15)  # 15% above

        # Get stated locations (intake forms have counties and cities)
        stated_cities = intake.get('cities', [])
        stated_counties = intake.get('counties', [])
        if not stated_cities and lead.get('preferred_cities'):
            try:
                import json
                stated_cities = json.loads(lead['preferred_cities'])
            except (json.JSONDecodeError, TypeError):
                pass
        behavioral_cities = behavioral.get('cities', [])

        # Stated requirements (intake form > leads table)
        min_beds = intake.get('min_beds') or lead.get('min_beds')
        min_baths = intake.get('min_baths') or lead.get('min_baths')
        min_sqft = intake.get('min_sqft')
        min_acreage = intake.get('min_acreage')

        # Query properties
        with self._get_connection() as conn:
            query = '''
                SELECT * FROM properties
                WHERE status = 'active'
            '''
            params = []

            # Apply loose price filter if available
            if min_price:
                query += ' AND (price IS NULL OR price >= ?)'
                params.append(min_price)
            if max_price:
                query += ' AND (price IS NULL OR price <= ?)'
                params.append(max_price)

            query += ' ORDER BY created_at DESC LIMIT 200'

            properties = conn.execute(query, params).fetchall()

        # Score each property
        matches = []
        for prop_row in properties:
            prop = dict(prop_row)
            score_breakdown = {}

            # Price scoring (30%)
            price_score = self._score_price_match(
                prop.get('price'),
                stated_min, stated_max,
                behav_min, behav_max
            )
            score_breakdown['price'] = round(price_score * 30, 1)

            # Location scoring (25%)
            location_score = self._score_location_match(
                prop.get('city'),
                stated_cities,
                behavioral_cities
            )
            score_breakdown['location'] = round(location_score * 25, 1)

            # Size scoring (25%)
            size_score = self._score_size_match(
                prop.get('beds'),
                prop.get('baths'),
                min_beds,
                min_baths
            )
            score_breakdown['size'] = round(size_score * 25, 1)

            # Recency scoring (20%)
            recency_score = self._score_recency_match(prop.get('days_on_market'))
            score_breakdown['recency'] = round(recency_score * 20, 1)

            total_score = sum(score_breakdown.values())

            if total_score >= min_score:
                matches.append({
                    'property': prop,
                    'total_score': round(total_score, 1),
                    'score_breakdown': score_breakdown,
                    'stated_contribution': round(score_breakdown['size'] + score_breakdown['price'] * 0.4, 1),
                    'behavioral_contribution': round(
                        score_breakdown['location'] + score_breakdown['price'] * 0.6 + score_breakdown['recency'],
                        1
                    )
                })

        # Sort by score and return top matches
        matches.sort(key=lambda m: m['total_score'], reverse=True)
        return matches[:limit]

    def _score_price_match(
        self,
        price: int,
        stated_min: int,
        stated_max: int,
        behav_min: int,
        behav_max: int
    ) -> float:
        """Score price fit. Returns 0.0-1.0"""
        if not price:
            return 0.5  # Neutral if no price

        # Blend ranges
        min_p = stated_min or behav_min or 0
        max_p = stated_max or behav_max or float('inf')

        if behav_min and stated_min:
            min_p = stated_min * 0.4 + behav_min * 0.6
        if behav_max and stated_max:
            max_p = stated_max * 0.4 + behav_max * 0.6

        if min_p <= price <= max_p:
            return 1.0
        elif price < min_p:
            return 0.7  # Under budget is okay
        else:
            over_pct = (price - max_p) / max_p if max_p else 0
            return max(0, 1.0 - over_pct * 2)

    def _score_location_match(
        self,
        city: str,
        stated_cities: List[str],
        behavioral_cities: List[str]
    ) -> float:
        """Score location match. Returns 0.0-1.0"""
        if not city:
            return 0.5

        city_lower = city.lower()

        # Behavioral match (stronger signal)
        for bc in behavioral_cities:
            if bc.lower() == city_lower:
                return 1.0

        # Stated preference match
        for sc in stated_cities:
            if sc.lower() == city_lower:
                return 0.9

        # Not in any preferred list
        return 0.3

    def _score_size_match(
        self,
        beds: int,
        baths: float,
        min_beds: int,
        min_baths: float
    ) -> float:
        """Score size requirements. Returns 0.0-1.0"""
        score = 1.0

        if min_beds and beds and beds < min_beds:
            score *= 0.5
        if min_baths and baths and baths < min_baths:
            score *= 0.8

        return score

    def _score_recency_match(self, days_on_market: int) -> float:
        """Score freshness. Returns 0.0-1.0"""
        if days_on_market is None:
            return 0.5

        if days_on_market <= 7:
            return 1.0
        elif days_on_market <= 30:
            return 0.8
        elif days_on_market <= 90:
            return 0.6
        else:
            return 0.4

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

    def get_behavioral_preferences(self, lead_id: str) -> Dict[str, Any]:
        """
        Analyze contact_events to infer buyer preferences from behavior.

        Examines viewed/favorited/shared properties to extract patterns in:
        - Price range (10th-90th percentile, weighted by engagement)
        - Locations (cities, weighted by engagement)
        - Size requirements (beds, baths, sqft patterns)
        - Land requirements (acreage patterns)

        Returns comprehensive preference dict for matching algorithm.
        """
        from collections import Counter

        with self._get_connection() as conn:
            # Get fub_id for the lead (events use fub_id as contact_id)
            fub_row = conn.execute(
                'SELECT fub_id FROM leads WHERE id = ?', (lead_id,)
            ).fetchone()
            contact_id = fub_row[0] if fub_row and fub_row[0] else lead_id

            # Get property events with price data
            events = conn.execute('''
                SELECT event_type, property_price, property_mls, property_address
                FROM contact_events
                WHERE contact_id = ? AND event_type IN ('property_view', 'property_favorite', 'property_share')
                ORDER BY occurred_at DESC
                LIMIT 200
            ''', (contact_id,)).fetchall()

            if not events:
                return {
                    'price_range': None,
                    'avg_price': None,
                    'cities': [],
                    'counties': [],
                    'beds_range': None,
                    'baths_range': None,
                    'sqft_range': None,
                    'acreage_range': None,
                    'avg_beds': None,
                    'avg_baths': None,
                    'view_count': 0,
                    'favorite_count': 0,
                    'confidence': 0.0
                }

            # Weight by event type (favorites/shares are stronger signals)
            weights = {'property_view': 1.0, 'property_favorite': 3.0, 'property_share': 2.5}

            weighted_prices = []
            weighted_beds = []
            weighted_baths = []
            weighted_sqft = []
            weighted_acreage = []
            cities = []
            counties = []
            view_count = 0
            favorite_count = 0

            # Collect MLS numbers for batch property lookup
            mls_numbers = set()
            for event in events:
                mls = event[2]
                if mls:
                    mls_numbers.add(mls)

            # Batch fetch property details
            property_cache = {}
            if mls_numbers:
                placeholders = ','.join(['?' for _ in mls_numbers])
                props = conn.execute(f'''
                    SELECT mls_number, idx_mls_number, city, county, beds, baths, sqft, acreage
                    FROM properties
                    WHERE mls_number IN ({placeholders}) OR idx_mls_number IN ({placeholders})
                ''', list(mls_numbers) + list(mls_numbers)).fetchall()
                for prop in props:
                    # Cache by both mls_number and idx_mls_number
                    if prop[0]:
                        property_cache[prop[0]] = prop
                    if prop[1]:
                        property_cache[prop[1]] = prop

            for event in events:
                event_type = event[0]
                price = event[1]
                mls = event[2]

                weight = weights.get(event_type, 1.0)
                weight_int = int(weight)

                if event_type == 'property_view':
                    view_count += 1
                elif event_type == 'property_favorite':
                    favorite_count += 1

                # Add price data (weighted)
                if price:
                    for _ in range(weight_int):
                        weighted_prices.append(price)

                # Look up property details for beds/baths/sqft/acreage/location
                if mls and mls in property_cache:
                    prop = property_cache[mls]
                    city = prop[2]
                    county = prop[3]
                    beds = prop[4]
                    baths = prop[5]
                    sqft = prop[6]
                    acreage = prop[7]

                    if city:
                        for _ in range(weight_int):
                            cities.append(city)
                    if county:
                        for _ in range(weight_int):
                            counties.append(county)
                    if beds:
                        for _ in range(weight_int):
                            weighted_beds.append(beds)
                    if baths:
                        for _ in range(weight_int):
                            weighted_baths.append(baths)
                    if sqft:
                        for _ in range(weight_int):
                            weighted_sqft.append(sqft)
                    if acreage and acreage > 0:
                        for _ in range(weight_int):
                            weighted_acreage.append(acreage)

            def calc_range(values):
                """Calculate 10th-90th percentile range."""
                if not values:
                    return None
                values.sort()
                n = len(values)
                min_val = values[int(n * 0.1)] if n > 1 else values[0]
                max_val = values[int(n * 0.9)] if n > 1 else values[0]
                return (min_val, max_val)

            def calc_avg(values):
                """Calculate average, return None if empty."""
                if not values:
                    return None
                return sum(values) / len(values)

            # Calculate ranges and averages
            price_range = calc_range(weighted_prices)
            avg_price = int(calc_avg(weighted_prices)) if weighted_prices else None
            beds_range = calc_range(weighted_beds)
            avg_beds = round(calc_avg(weighted_beds), 1) if weighted_beds else None
            baths_range = calc_range(weighted_baths)
            avg_baths = round(calc_avg(weighted_baths), 1) if weighted_baths else None
            sqft_range = calc_range(weighted_sqft)
            acreage_range = calc_range(weighted_acreage)

            # Get most common locations
            city_counts = Counter(cities)
            county_counts = Counter(counties)
            top_cities = [city for city, _ in city_counts.most_common(5)]
            top_counties = [county for county, _ in county_counts.most_common(3)]

            # Confidence based on data volume
            confidence = min(1.0, len(events) / 30)

            return {
                'price_range': price_range,
                'avg_price': avg_price,
                'cities': top_cities,
                'counties': top_counties,
                'beds_range': beds_range,
                'avg_beds': avg_beds,
                'baths_range': baths_range,
                'avg_baths': avg_baths,
                'sqft_range': sqft_range,
                'acreage_range': acreage_range,
                'view_count': view_count,
                'favorite_count': favorite_count,
                'confidence': round(confidence, 2)
            }

    # ==========================================
    # NOTE PARSING FOR REQUIREMENTS EXTRACTION
    # ==========================================

    def parse_requirements_from_notes(self, notes_text: str) -> Dict[str, Any]:
        """
        Extract buyer requirements from free-text notes using pattern matching.

        Looks for patterns like:
        - Price: "budget $300k", "under 400000", "$250k-$350k"
        - Bedrooms: "3 bed", "3+ bedrooms", "at least 2 bed"
        - Bathrooms: "2 bath", "2+ baths", "needs 2 full baths"
        - Size: "1500 sqft", "2000+ square feet", "min 1800 sf"
        - Acreage: "1 acre", "2+ acres", "at least 5 acres"
        - Location: "near downtown", "in Bryson City", "Macon County"

        Returns dict with extracted requirements.
        """
        import re

        if not notes_text:
            return {'has_requirements': False}

        text = notes_text.lower()
        result = {'has_requirements': False}

        def parse_price(s):
            """Parse price string like '350k', '350,000', '350000' to int."""
            s = s.replace(',', '').replace('$', '').strip()
            if s.endswith('k'):
                return int(float(s[:-1]) * 1000)
            else:
                val = int(float(s))
                # If it looks like shorthand (e.g., 350 meaning 350k)
                if val < 1000:
                    return val * 1000
                return val

        # Price range patterns (most specific first)
        range_match = re.search(r'\$?(\d+(?:,\d{3})?k?)\s*[-–to]+\s*\$?(\d+(?:,\d{3})?k?)', text)
        if range_match:
            result['has_requirements'] = True
            result['min_price'] = parse_price(range_match.group(1))
            result['max_price'] = parse_price(range_match.group(2))
        else:
            # Single price patterns
            budget_match = re.search(r'budget[:\s]+\$?(\d+(?:,\d{3})?k?)', text)
            under_match = re.search(r'(?:under|less than|max(?:imum)?)[:\s]+\$?(\d+(?:,\d{3})?k?)', text)
            around_match = re.search(r'(?:around|about|approximately)[:\s]+\$?(\d+(?:,\d{3})?k?)', text)
            looking_match = re.search(r'(?:looking for|want(?:s)?)[:\s]+\$?(\d+(?:,\d{3})?k?)', text)
            dollar_match = re.search(r'\$(\d+(?:,\d{3})?k?)', text)

            if under_match:
                result['has_requirements'] = True
                result['max_price'] = parse_price(under_match.group(1))
            elif budget_match:
                result['has_requirements'] = True
                price = parse_price(budget_match.group(1))
                result['min_price'] = int(price * 0.85)
                result['max_price'] = int(price * 1.15)
            elif around_match:
                result['has_requirements'] = True
                price = parse_price(around_match.group(1))
                result['min_price'] = int(price * 0.9)
                result['max_price'] = int(price * 1.1)
            elif looking_match:
                result['has_requirements'] = True
                result['max_price'] = parse_price(looking_match.group(1))
            elif dollar_match and 'bed' not in text[:text.find('$')+10]:
                # Only use dollar match if it's not near "bed" (avoid matching $3k for 3 bed)
                result['has_requirements'] = True
                result['budget'] = parse_price(dollar_match.group(1))

        # Bedroom patterns
        bed_patterns = [
            r'(\d+)\+?\s*(?:bed(?:room)?s?|br|bd)',  # 3 bed, 3+ bedrooms, 3 br
            r'at\s+least\s+(\d+)\s*(?:bed(?:room)?s?|br|bd)',  # at least 3 bed
            r'min(?:imum)?\s+(\d+)\s*(?:bed(?:room)?s?|br|bd)',  # min 3 bed
        ]

        for pattern in bed_patterns:
            match = re.search(pattern, text)
            if match:
                result['has_requirements'] = True
                result['min_beds'] = int(match.group(1))
                break

        # Bathroom patterns
        bath_patterns = [
            r'(\d+(?:\.\d)?)\+?\s*(?:bath(?:room)?s?|ba)',  # 2 bath, 2+ baths
            r'at\s+least\s+(\d+(?:\.\d)?)\s*(?:bath(?:room)?s?|ba)',  # at least 2 bath
            r'min(?:imum)?\s+(\d+(?:\.\d)?)\s*(?:bath(?:room)?s?|ba)',  # min 2 bath
        ]

        for pattern in bath_patterns:
            match = re.search(pattern, text)
            if match:
                result['has_requirements'] = True
                result['min_baths'] = float(match.group(1))
                break

        # Square footage patterns
        sqft_patterns = [
            r'(\d{1,2}),?(\d{3})\+?\s*(?:sq\.?\s*f(?:oo)?t|sqft|sf)',  # 1500 sqft
            r'min(?:imum)?\s+(\d{1,2}),?(\d{3})\s*(?:sq\.?\s*f(?:oo)?t|sqft|sf)',  # min 1500 sqft
            r'at\s+least\s+(\d{1,2}),?(\d{3})\s*(?:sq\.?\s*f(?:oo)?t|sqft|sf)',  # at least 1500 sqft
        ]

        for pattern in sqft_patterns:
            match = re.search(pattern, text)
            if match:
                result['has_requirements'] = True
                sqft = int(match.group(1) + match.group(2))
                result['min_sqft'] = sqft
                break

        # Acreage patterns
        acre_patterns = [
            r'(\d+(?:\.\d+)?)\+?\s*acres?',  # 5 acres, 2.5+ acres
            r'at\s+least\s+(\d+(?:\.\d+)?)\s*acres?',  # at least 5 acres
            r'min(?:imum)?\s+(\d+(?:\.\d+)?)\s*acres?',  # min 5 acres
        ]

        for pattern in acre_patterns:
            match = re.search(pattern, text)
            if match:
                result['has_requirements'] = True
                result['min_acreage'] = float(match.group(1))
                break

        # Location patterns (WNC-specific cities and counties)
        wnc_cities = [
            'bryson city', 'sylva', 'waynesville', 'asheville', 'franklin',
            'highlands', 'cashiers', 'murphy', 'cherokee', 'maggie valley',
            'canton', 'clyde', 'dillsboro', 'cullowhee', 'webster',
            'robbinsville', 'andrews', 'hayesville', 'young harris'
        ]
        wnc_counties = [
            'macon', 'jackson', 'swain', 'haywood', 'buncombe', 'henderson',
            'transylvania', 'clay', 'cherokee', 'graham', 'madison'
        ]

        found_cities = []
        found_counties = []

        for city in wnc_cities:
            if city in text:
                result['has_requirements'] = True
                found_cities.append(city.title())

        for county in wnc_counties:
            if county + ' county' in text or f'in {county}' in text:
                result['has_requirements'] = True
                found_counties.append(county.title())

        if found_cities:
            result['preferred_cities'] = found_cities
        if found_counties:
            result['preferred_counties'] = found_counties

        # Feature keywords
        features = []
        feature_keywords = {
            'mountain view': 'Mountain Views',
            'long range view': 'Long Range Views',
            'creek': 'Creek/Water',
            'river': 'River/Water',
            'waterfront': 'Waterfront',
            'garage': 'Garage',
            'basement': 'Basement',
            'workshop': 'Workshop',
            'barn': 'Barn',
            'flat land': 'Flat/Usable Land',
            'usable land': 'Flat/Usable Land',
            'fenced': 'Fenced',
            'privacy': 'Privacy',
            'no hoa': 'No HOA',
            'paved road': 'Paved Road Access',
        }

        for keyword, feature_name in feature_keywords.items():
            if keyword in text:
                result['has_requirements'] = True
                features.append(feature_name)

        if features:
            result['desired_features'] = features

        return result

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
            # Get fub_id for this contact (events/communications use fub_id)
            fub_id_row = conn.execute(
                'SELECT fub_id FROM leads WHERE id = ?',
                (contact_id,)
            ).fetchone()
            event_contact_id = fub_id_row[0] if fub_id_row and fub_id_row[0] else contact_id

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
            ''', (event_contact_id, cutoff, event_contact_id, cutoff, limit)).fetchall()

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
        status: Optional[str] = None,
        photo_url: Optional[str] = None
    ):
        """Insert or update IDX property cache entry."""
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO idx_property_cache (mls_number, address, city, price, status, photo_url, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(mls_number) DO UPDATE SET
                    address = excluded.address,
                    city = excluded.city,
                    price = COALESCE(excluded.price, price),
                    status = COALESCE(excluded.status, status),
                    photo_url = COALESCE(excluded.photo_url, photo_url),
                    last_updated = CURRENT_TIMESTAMP
            ''', (mls_number, address, city, price, status, photo_url))
            conn.commit()

    def get_uncached_mls_numbers(self, limit: int = 100, contact_id: Optional[str] = None) -> List[str]:
        """Get MLS numbers from contact_events that aren't in the cache.

        Args:
            limit: Max number of MLS numbers to return
            contact_id: Optional - only get uncached MLS for this contact
        """
        with self._get_connection() as conn:
            if contact_id:
                rows = conn.execute('''
                    SELECT DISTINCT e.property_mls
                    FROM contact_events e
                    LEFT JOIN idx_property_cache c ON e.property_mls = c.mls_number
                    WHERE e.property_mls IS NOT NULL
                        AND e.contact_id = ?
                        AND c.mls_number IS NULL
                    LIMIT ?
                ''', (contact_id, limit)).fetchall()
            else:
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
            # First, get the fub_id for this contact (events use fub_id, not lead id)
            # This handles cases where lead.id is a UUID but fub_id is the numeric FUB ID
            fub_id_row = conn.execute(
                'SELECT fub_id FROM leads WHERE id = ?',
                (contact_id,)
            ).fetchone()

            # Use fub_id if available, otherwise fall back to contact_id
            event_contact_id = fub_id_row[0] if fub_id_row and fub_id_row[0] else contact_id

            # Get all property events for this contact, aggregated by property
            # LEFT JOIN with both properties table and idx_property_cache
            rows = conn.execute('''
                SELECT
                    COALESCE(e.property_address, p.address, c.address) as property_address,
                    COALESCE(MAX(e.property_price), p.price, c.price) as property_price,
                    e.property_mls,
                    COUNT(CASE WHEN e.event_type IN ('property_view', 'property_favorite', 'property_share') THEN 1 END) as view_count,
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
            ''', (event_contact_id,)).fetchall()

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
        # Get fub_id for event/communications lookups
        with self._get_connection() as conn:
            fub_id_row = conn.execute(
                'SELECT fub_id FROM leads WHERE id = ?',
                (contact_id,)
            ).fetchone()
        event_contact_id = fub_id_row[0] if fub_id_row and fub_id_row[0] else contact_id

        # Get latest scoring (uses fub_id internally)
        latest = self.get_latest_scoring(event_contact_id)

        # Get 7-day average
        avg_7d = self.calculate_heat_score_7d_avg(event_contact_id)

        # Get scoring history for trend
        history = self.get_scoring_history(event_contact_id, days=7)

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
            ''', (event_contact_id, week_ago)).fetchone()[0]

            events_week = conn.execute('''
                SELECT COUNT(*) FROM contact_events
                WHERE contact_id = ? AND occurred_at >= ?
            ''', (event_contact_id, week_ago)).fetchone()[0]

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

    def get_property_price_history(self, property_id: str) -> List[Dict[str, Any]]:
        """
        Get price history for a specific property.

        Combines:
        - Initial list price (list_date)
        - All price changes from property_changes table
        - Current price

        Args:
            property_id: The property ID

        Returns:
            List of price points sorted by date, each with:
            - date: ISO date string
            - price: Price at that point
            - event: Description of the change
        """
        history = []

        with self._get_connection() as conn:
            # Get the property details
            prop = conn.execute('''
                SELECT id, address, price, initial_price, list_date, created_at
                FROM properties WHERE id = ?
            ''', [property_id]).fetchone()

            if not prop:
                return []

            prop_dict = dict(prop)

            # Add initial list price if available
            if prop_dict.get('initial_price'):
                list_date = prop_dict.get('list_date') or prop_dict.get('created_at', '')[:10]
                history.append({
                    'date': list_date,
                    'price': prop_dict['initial_price'],
                    'event': 'Listed'
                })

            # Get all price changes for this property
            changes = conn.execute('''
                SELECT old_value, new_value, change_amount, detected_at
                FROM property_changes
                WHERE property_id = ? AND change_type = 'price'
                ORDER BY detected_at ASC
            ''', [property_id]).fetchall()

            for change in changes:
                c = dict(change)
                try:
                    # Parse the price from old_value/new_value (might be formatted)
                    new_price = int(c['new_value'].replace('$', '').replace(',', ''))
                    change_amt = c.get('change_amount', 0)

                    if change_amt and change_amt < 0:
                        event = f'Price Reduced (${abs(change_amt):,})'
                    elif change_amt and change_amt > 0:
                        event = f'Price Increased (${change_amt:,})'
                    else:
                        event = 'Price Change'

                    history.append({
                        'date': c['detected_at'][:10],
                        'price': new_price,
                        'event': event
                    })
                except (ValueError, TypeError, AttributeError):
                    continue

            # Add current price if different from last history point
            current_price = prop_dict.get('price')
            if current_price:
                if not history or history[-1]['price'] != current_price:
                    history.append({
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'price': current_price,
                        'event': 'Current'
                    })

            # Sort by date
            history.sort(key=lambda x: x['date'])

            return history

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
                # Exclude case-only changes (e.g., "contingent" -> "Contingent")
                old_val = (change.get('old_value') or '').lower()
                new_val = (change.get('new_value') or '').lower()
                if old_val != new_val:
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

    # ==========================================
    # DASHBOARD (HOME PAGE) OPERATIONS
    # ==========================================

    def get_pipeline_snapshot(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get pipeline counts for the dashboard snapshot.

        Returns counts for: leads, buyers, properties, pursuits, contracts
        Plus 7-day deltas for trend indicators.
        """
        with self._get_connection() as conn:
            today = datetime.now()
            week_ago = (today - timedelta(days=7)).isoformat()

            # Base user filter
            user_filter = ""
            user_params = []
            if user_id:
                user_filter = "AND assigned_user_id = ?"
                user_params = [user_id]

            # LEADS: stage = 'Lead' or similar early stages
            leads_count = conn.execute(f'''
                SELECT COUNT(*) FROM leads
                WHERE stage IN ('Lead', 'lead', 'New Lead')
                {user_filter}
            ''', user_params).fetchone()[0]

            leads_week_ago = conn.execute(f'''
                SELECT COUNT(*) FROM leads
                WHERE stage IN ('Lead', 'lead', 'New Lead')
                AND created_at <= ?
                {user_filter}
            ''', [week_ago] + user_params).fetchone()[0]

            # BUYERS: Qualified leads (Prospect, Active Client, etc.)
            buyers_count = conn.execute(f'''
                SELECT COUNT(*) FROM leads
                WHERE stage IN ('Prospect', 'Active Client', 'Active Buyer', 'Qualified')
                {user_filter}
            ''', user_params).fetchone()[0]

            # Buyers needing intake (no requirements captured)
            buyers_need_intake = conn.execute(f'''
                SELECT COUNT(*) FROM leads
                WHERE stage IN ('Prospect', 'Active Client', 'Active Buyer', 'Qualified')
                AND (min_price IS NULL OR max_price IS NULL OR preferred_cities IS NULL)
                {user_filter}
            ''', user_params).fetchone()[0]

            # PROPERTIES: Active listings
            properties_active = conn.execute('''
                SELECT COUNT(*) FROM properties WHERE status = 'active'
            ''').fetchone()[0]

            # New properties today
            today_start = today.replace(hour=0, minute=0, second=0).isoformat()
            properties_new = conn.execute('''
                SELECT COUNT(*) FROM properties
                WHERE status = 'active' AND created_at >= ?
            ''', [today_start]).fetchone()[0]

            # Price drops in last 24 hours
            yesterday = (today - timedelta(hours=24)).isoformat()
            price_drops = conn.execute('''
                SELECT COUNT(*) FROM property_changes
                WHERE change_type = 'price' AND change_amount < 0 AND detected_at >= ?
            ''', [yesterday]).fetchone()[0]

            # PURSUITS: Active pursuits
            pursuits_count = conn.execute('''
                SELECT COUNT(*) FROM pursuits WHERE status = 'active'
            ''').fetchone()[0]

            # Total properties in active pursuits
            pursuit_properties_count = conn.execute('''
                SELECT COUNT(*) FROM pursuit_properties pp
                JOIN pursuits p ON pp.pursuit_id = p.id
                WHERE p.status = 'active'
            ''').fetchone()[0]

            # CONTRACTS: Under contract (stage-based for now)
            contracts_count = conn.execute(f'''
                SELECT COUNT(*) FROM leads
                WHERE stage IN ('Under Contract', 'Pending', 'Active Under Contract')
                {user_filter}
            ''', user_params).fetchone()[0]

            # Pipeline value (sum of max_price for contracts)
            pipeline_value = conn.execute(f'''
                SELECT COALESCE(SUM(max_price), 0) FROM leads
                WHERE stage IN ('Under Contract', 'Pending', 'Active Under Contract')
                {user_filter}
            ''', user_params).fetchone()[0]

            return {
                'leads': {
                    'count': leads_count,
                    'delta': leads_count - leads_week_ago,
                    'label': 'Leads'
                },
                'buyers': {
                    'count': buyers_count,
                    'need_intake': buyers_need_intake,
                    'label': 'Buyers'
                },
                'properties': {
                    'active': properties_active,
                    'new_today': properties_new,
                    'price_drops': price_drops,
                    'label': 'Properties'
                },
                'pursuits': {
                    'count': pursuits_count,
                    'properties_count': pursuit_properties_count,
                    'label': 'Pursuits'
                },
                'contracts': {
                    'count': contracts_count,
                    'value': pipeline_value,
                    'label': 'Contracts'
                }
            }

    def get_todays_actions(self, user_id: Optional[int] = None, limit: int = 10) -> Dict[str, List[Dict]]:
        """
        Get today's priority actions for the dashboard.

        Returns grouped actions: calls, follow_ups, send_properties
        """
        with self._get_connection() as conn:
            today = datetime.now().strftime('%Y-%m-%d')

            user_filter = ""
            user_params = []
            if user_id:
                user_filter = "AND l.assigned_user_id = ?"
                user_params = [user_id]

            # Calls due today (from contact_actions table)
            calls = conn.execute(f'''
                SELECT
                    ca.id as action_id,
                    ca.contact_id,
                    l.first_name || ' ' || COALESCE(l.last_name, '') as name,
                    l.phone,
                    l.email,
                    l.stage,
                    l.priority_score,
                    l.heat_score,
                    ca.description,
                    ca.due_date,
                    l.fub_id
                FROM contact_actions ca
                JOIN leads l ON ca.contact_id = l.id
                WHERE ca.action_type = 'call'
                AND ca.completed_at IS NULL
                AND ca.due_date <= ?
                {user_filter}
                ORDER BY ca.due_date ASC, l.priority_score DESC
                LIMIT ?
            ''', [today] + user_params + [limit]).fetchall()

            # Follow-ups due today
            follow_ups = conn.execute(f'''
                SELECT
                    ca.id as action_id,
                    ca.contact_id,
                    l.first_name || ' ' || COALESCE(l.last_name, '') as name,
                    l.phone,
                    l.email,
                    l.stage,
                    l.priority_score,
                    ca.description,
                    ca.due_date,
                    l.fub_id
                FROM contact_actions ca
                JOIN leads l ON ca.contact_id = l.id
                WHERE ca.action_type = 'follow_up'
                AND ca.completed_at IS NULL
                AND ca.due_date <= ?
                {user_filter}
                ORDER BY ca.due_date ASC, l.priority_score DESC
                LIMIT ?
            ''', [today] + user_params + [limit]).fetchall()

            # Buyers with new matches (hot leads with requirements who have new matching properties)
            # For now, return high-priority buyers that may need property updates
            send_properties = conn.execute(f'''
                SELECT
                    l.id as contact_id,
                    l.first_name || ' ' || COALESCE(l.last_name, '') as name,
                    l.phone,
                    l.email,
                    l.stage,
                    l.priority_score,
                    l.heat_score,
                    l.min_price,
                    l.max_price,
                    l.preferred_cities,
                    l.fub_id
                FROM leads l
                WHERE l.stage IN ('Prospect', 'Active Client', 'Active Buyer', 'Qualified')
                AND l.heat_score >= 50
                AND l.min_price IS NOT NULL
                {user_filter}
                ORDER BY l.priority_score DESC
                LIMIT ?
            ''', user_params + [limit]).fetchall()

            return {
                'calls': [dict(row) for row in calls],
                'follow_ups': [dict(row) for row in follow_ups],
                'send_properties': [dict(row) for row in send_properties]
            }

    def get_overnight_changes(self, hours: int = 24) -> Dict[str, List[Dict]]:
        """
        Get overnight/recent changes for the dashboard.

        Returns: new_leads, price_drops, new_matches, going_cold, status_changes
        """
        with self._get_connection() as conn:
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

            # New leads in the time period
            new_leads = conn.execute('''
                SELECT
                    id, first_name, last_name, email, phone, source, stage,
                    heat_score, priority_score, created_at
                FROM leads
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT 10
            ''', [cutoff]).fetchall()

            # Price drops on active properties
            price_drops = conn.execute('''
                SELECT
                    pc.property_id,
                    pc.property_address,
                    pc.old_value,
                    pc.new_value,
                    pc.change_amount,
                    pc.detected_at,
                    p.city,
                    p.beds,
                    p.baths
                FROM property_changes pc
                LEFT JOIN properties p ON pc.property_id = p.id
                WHERE pc.change_type = 'price'
                AND pc.change_amount < 0
                AND pc.detected_at >= ?
                ORDER BY pc.change_amount ASC
                LIMIT 10
            ''', [cutoff]).fetchall()

            # Status changes (pending, sold, etc.)
            # Exclude case-only changes (e.g., "contingent" -> "Contingent")
            status_changes = conn.execute('''
                SELECT
                    pc.property_id,
                    pc.property_address,
                    pc.old_value,
                    pc.new_value,
                    pc.detected_at,
                    p.city,
                    p.price
                FROM property_changes pc
                LEFT JOIN properties p ON pc.property_id = p.id
                WHERE pc.change_type = 'status'
                AND pc.detected_at >= ?
                AND LOWER(pc.old_value) != LOWER(pc.new_value)
                ORDER BY pc.detected_at DESC
                LIMIT 10
            ''', [cutoff]).fetchall()

            # Leads going cold (no activity in 7+ days, was active before)
            cold_cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            going_cold = conn.execute('''
                SELECT
                    id, first_name, last_name, email, phone, stage,
                    heat_score, priority_score, last_activity_at, days_since_activity
                FROM leads
                WHERE stage IN ('Lead', 'Prospect', 'Active Client', 'Active Buyer')
                AND heat_score >= 30
                AND (days_since_activity >= 7 OR last_activity_at IS NULL OR last_activity_at <= ?)
                ORDER BY priority_score DESC
                LIMIT 10
            ''', [cold_cutoff]).fetchall()

            return {
                'new_leads': [dict(row) for row in new_leads],
                'price_drops': [dict(row) for row in price_drops],
                'status_changes': [dict(row) for row in status_changes],
                'going_cold': [dict(row) for row in going_cold]
            }

    def get_hottest_leads(self, limit: int = 5, user_id: Optional[int] = None) -> List[Dict]:
        """
        Get the hottest leads by heat score.
        """
        with self._get_connection() as conn:
            user_filter = ""
            user_params = []
            if user_id:
                user_filter = "AND assigned_user_id = ?"
                user_params = [user_id]

            results = conn.execute(f'''
                SELECT
                    id, first_name, last_name, email, phone, stage, source,
                    heat_score, value_score, relationship_score, priority_score,
                    website_visits, properties_viewed, properties_favorited,
                    last_activity_at, days_since_activity,
                    min_price, max_price, preferred_cities,
                    fub_id
                FROM leads
                WHERE heat_score > 0
                AND stage NOT IN ('Past Client', 'Trash', 'Agents/Vendors/Lendors')
                {user_filter}
                ORDER BY heat_score DESC
                LIMIT ?
            ''', user_params + [limit]).fetchall()

            return [dict(row) for row in results]

    def get_active_pursuits(self, limit: int = 5) -> List[Dict]:
        """
        Get active pursuits with property counts.
        """
        with self._get_connection() as conn:
            pursuits = conn.execute('''
                SELECT
                    p.id,
                    p.name,
                    p.status,
                    p.criteria_summary,
                    p.created_at,
                    p.updated_at,
                    l.id as buyer_id,
                    l.first_name || ' ' || COALESCE(l.last_name, '') as buyer_name,
                    l.email as buyer_email,
                    l.phone as buyer_phone,
                    l.fub_id as buyer_fub_id,
                    COUNT(pp.id) as property_count,
                    SUM(CASE WHEN pp.status = 'favorited' THEN 1 ELSE 0 END) as favorited_count,
                    SUM(CASE WHEN pp.added_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as new_count
                FROM pursuits p
                JOIN leads l ON p.buyer_id = l.id
                LEFT JOIN pursuit_properties pp ON p.id = pp.pursuit_id
                WHERE p.status = 'active'
                GROUP BY p.id
                ORDER BY p.updated_at DESC
                LIMIT ?
            ''', [limit]).fetchall()

            return [dict(row) for row in pursuits]

    def create_pursuit(
        self,
        buyer_id: str,
        name: str,
        criteria_summary: Optional[str] = None,
        intake_form_id: Optional[str] = None,
        fub_deal_id: Optional[int] = None
    ) -> str:
        """
        Create a new pursuit for a buyer.

        Returns the pursuit ID.
        """
        import uuid
        pursuit_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO pursuits (id, buyer_id, name, criteria_summary, intake_form_id, fub_deal_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', [pursuit_id, buyer_id, name, criteria_summary, intake_form_id, fub_deal_id])
            conn.commit()

        return pursuit_id

    def add_property_to_pursuit(
        self,
        pursuit_id: str,
        property_id: str,
        source: str = 'agent_added',
        status: str = 'suggested',
        notes: Optional[str] = None
    ) -> str:
        """
        Add a property to a pursuit.

        Returns the pursuit_property ID.
        """
        import uuid
        pp_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            conn.execute('''
                INSERT OR IGNORE INTO pursuit_properties
                (id, pursuit_id, property_id, source, status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', [pp_id, pursuit_id, property_id, source, status, notes])
            conn.commit()

        return pp_id

    # ==========================================
    # CONTACT DAILY ACTIVITY OPERATIONS
    # ==========================================

    def record_daily_activity(
        self,
        contact_id: str,
        activity_date: str,
        website_visits: int = 0,
        properties_viewed: int = 0,
        properties_favorited: int = 0,
        properties_shared: int = 0,
        calls_inbound: int = 0,
        calls_outbound: int = 0,
        texts_inbound: int = 0,
        texts_outbound: int = 0,
        emails_received: int = 0,
        emails_sent: int = 0,
        heat_score: float = None,
        value_score: float = None,
        relationship_score: float = None,
        priority_score: float = None
    ) -> bool:
        """
        Record or update daily activity for a contact.
        Uses upsert to handle both new and existing records.

        Args:
            contact_id: The contact's ID
            activity_date: Date in YYYY-MM-DD format
            *_counts: Activity counts for the day
            *_score: Score snapshots (optional)

        Returns:
            True if successful
        """
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO contact_daily_activity
                (contact_id, activity_date, website_visits, properties_viewed,
                 properties_favorited, properties_shared, calls_inbound, calls_outbound,
                 texts_inbound, texts_outbound, emails_received, emails_sent,
                 heat_score_snapshot, value_score_snapshot, relationship_score_snapshot,
                 priority_score_snapshot, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contact_id, activity_date) DO UPDATE SET
                    website_visits = excluded.website_visits,
                    properties_viewed = excluded.properties_viewed,
                    properties_favorited = excluded.properties_favorited,
                    properties_shared = excluded.properties_shared,
                    calls_inbound = excluded.calls_inbound,
                    calls_outbound = excluded.calls_outbound,
                    texts_inbound = excluded.texts_inbound,
                    texts_outbound = excluded.texts_outbound,
                    emails_received = excluded.emails_received,
                    emails_sent = excluded.emails_sent,
                    heat_score_snapshot = COALESCE(excluded.heat_score_snapshot, heat_score_snapshot),
                    value_score_snapshot = COALESCE(excluded.value_score_snapshot, value_score_snapshot),
                    relationship_score_snapshot = COALESCE(excluded.relationship_score_snapshot, relationship_score_snapshot),
                    priority_score_snapshot = COALESCE(excluded.priority_score_snapshot, priority_score_snapshot),
                    updated_at = excluded.updated_at
            ''', (
                contact_id, activity_date, website_visits, properties_viewed,
                properties_favorited, properties_shared, calls_inbound, calls_outbound,
                texts_inbound, texts_outbound, emails_received, emails_sent,
                heat_score, value_score, relationship_score, priority_score,
                datetime.now().isoformat()
            ))
            conn.commit()
            return True

    def get_contact_daily_activity(
        self,
        contact_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get daily activity records for a contact.

        Args:
            contact_id: The contact's ID
            days: Number of days to look back

        Returns:
            List of daily activity records, most recent first
        """
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM contact_daily_activity
                WHERE contact_id = ? AND activity_date >= ?
                ORDER BY activity_date DESC
            ''', (contact_id, cutoff)).fetchall()
            return [dict(row) for row in rows]

    def aggregate_daily_activity_from_events(
        self,
        contact_id: str,
        activity_date: str
    ) -> Dict[str, int]:
        """
        Aggregate activity counts from contact_events and contact_communications
        for a specific contact and date.

        Args:
            contact_id: The contact's ID
            activity_date: Date in YYYY-MM-DD format

        Returns:
            Dict with aggregated counts
        """
        date_start = f"{activity_date}T00:00:00"
        date_end = f"{activity_date}T23:59:59"

        with self._get_connection() as conn:
            # Aggregate events
            events = conn.execute('''
                SELECT event_type, COUNT(*) as count
                FROM contact_events
                WHERE contact_id = ? AND occurred_at >= ? AND occurred_at <= ?
                GROUP BY event_type
            ''', (contact_id, date_start, date_end)).fetchall()

            event_counts = {row['event_type']: row['count'] for row in events}

            # Aggregate communications
            comms = conn.execute('''
                SELECT comm_type, direction, COUNT(*) as count
                FROM contact_communications
                WHERE contact_id = ? AND occurred_at >= ? AND occurred_at <= ?
                GROUP BY comm_type, direction
            ''', (contact_id, date_start, date_end)).fetchall()

            comm_counts = {}
            for row in comms:
                key = f"{row['comm_type']}_{row['direction']}"
                comm_counts[key] = row['count']

        return {
            'website_visits': event_counts.get('website_visit', 0),
            'properties_viewed': event_counts.get('property_view', 0),
            'properties_favorited': event_counts.get('property_favorite', 0),
            'properties_shared': event_counts.get('property_share', 0),
            'calls_inbound': comm_counts.get('call_inbound', 0),
            'calls_outbound': comm_counts.get('call_outbound', 0),
            'texts_inbound': comm_counts.get('text_inbound', 0),
            'texts_outbound': comm_counts.get('text_outbound', 0),
            'emails_received': comm_counts.get('email_inbound', 0),
            'emails_sent': comm_counts.get('email_outbound', 0)
        }

    def get_activity_summary_by_date(
        self,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated activity across all contacts grouped by date.
        Useful for daily reports and trend analysis.

        Args:
            days: Number of days to look back

        Returns:
            List of daily summaries
        """
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT
                    activity_date,
                    COUNT(DISTINCT contact_id) as active_contacts,
                    SUM(website_visits) as total_website_visits,
                    SUM(properties_viewed) as total_properties_viewed,
                    SUM(properties_favorited) as total_favorited,
                    SUM(calls_inbound + calls_outbound) as total_calls,
                    SUM(texts_inbound + texts_outbound) as total_texts,
                    SUM(emails_received + emails_sent) as total_emails
                FROM contact_daily_activity
                WHERE activity_date >= ?
                GROUP BY activity_date
                ORDER BY activity_date DESC
            ''', (cutoff,)).fetchall()
            return [dict(row) for row in rows]

    # ==========================================
    # CONTACT ACTIONS OPERATIONS
    # ==========================================

    def add_contact_action(
        self,
        contact_id: str,
        action_type: str,
        description: str = None,
        due_date: str = None,
        priority: int = 3,
        created_by: str = 'user'
    ) -> int:
        """
        Add a new action for a contact.

        Args:
            contact_id: The contact's ID
            action_type: Type of action (call, email, text, meeting, follow_up, showing, note)
            description: Optional description
            due_date: Optional due date in YYYY-MM-DD format
            priority: Priority 1-5 (1 highest)
            created_by: Who created the action (user, system, sync)

        Returns:
            The ID of the created action
        """
        with self._get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO contact_actions
                (contact_id, action_type, description, due_date, priority, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (contact_id, action_type, description, due_date, priority, created_by))
            conn.commit()
            return cursor.lastrowid

    def get_contact_actions(
        self,
        contact_id: str,
        include_completed: bool = False,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get actions for a contact.

        Args:
            contact_id: The contact's ID
            include_completed: Whether to include completed actions
            limit: Maximum number of records

        Returns:
            List of action records
        """
        query = 'SELECT * FROM contact_actions WHERE contact_id = ?'
        params = [contact_id]

        if not include_completed:
            query += ' AND completed_at IS NULL'

        query += ' ORDER BY COALESCE(due_date, "9999-12-31"), priority, created_at LIMIT ?'
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def complete_contact_action(
        self,
        action_id: int,
        completed_by: str = 'user'
    ) -> bool:
        """
        Mark an action as completed.

        Args:
            action_id: The action's ID
            completed_by: Who completed the action

        Returns:
            True if action was updated
        """
        with self._get_connection() as conn:
            cursor = conn.execute('''
                UPDATE contact_actions
                SET completed_at = ?, completed_by = ?
                WHERE id = ? AND completed_at IS NULL
            ''', (datetime.now().isoformat(), completed_by, action_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_pending_actions(
        self,
        due_before: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all pending (uncompleted) actions, optionally filtered by due date.

        Args:
            due_before: Optional date filter (YYYY-MM-DD) - get actions due on or before
            limit: Maximum number of records

        Returns:
            List of pending actions with contact info
        """
        query = '''
            SELECT
                a.*,
                l.first_name,
                l.last_name,
                l.email,
                l.phone,
                l.fub_id,
                l.priority_score
            FROM contact_actions a
            JOIN leads l ON a.contact_id = l.id
            WHERE a.completed_at IS NULL
        '''
        params = []

        if due_before:
            query += ' AND (a.due_date IS NULL OR a.due_date <= ?)'
            params.append(due_before)

        query += ' ORDER BY COALESCE(a.due_date, "9999-12-31"), a.priority, l.priority_score DESC LIMIT ?'
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_action_counts_by_contact(self) -> Dict[str, int]:
        """
        Get count of pending actions per contact.

        Returns:
            Dict mapping contact_id to pending action count
        """
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT contact_id, COUNT(*) as count
                FROM contact_actions
                WHERE completed_at IS NULL
                GROUP BY contact_id
            ''').fetchall()
            return {row['contact_id']: row['count'] for row in rows}

    # ==========================================
    # SCORING RUNS OPERATIONS
    # ==========================================

    def start_scoring_run(
        self,
        source: str = 'scheduled',
        config_snapshot: dict = None
    ) -> int:
        """
        Start a new scoring run and return its ID.

        Args:
            source: What triggered the run (scheduled, manual, api)
            config_snapshot: Dict of scoring configuration/weights used

        Returns:
            The ID of the new scoring run
        """
        config_json = json.dumps(config_snapshot) if config_snapshot else None

        with self._get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO scoring_runs (source, config_snapshot, status)
                VALUES (?, ?, 'running')
            ''', (source, config_json))
            conn.commit()
            return cursor.lastrowid

    def complete_scoring_run(
        self,
        run_id: int,
        contacts_processed: int = 0,
        contacts_scored: int = 0,
        contacts_new: int = 0,
        contacts_updated: int = 0,
        fub_api_calls: int = 0,
        status: str = 'success',
        error_message: str = None,
        notes: str = None
    ) -> bool:
        """
        Complete a scoring run with final stats.

        Args:
            run_id: The scoring run ID
            contacts_*: Various counts
            fub_api_calls: Number of FUB API calls made
            status: Final status (success, partial, failed)
            error_message: Error message if failed
            notes: Any additional notes

        Returns:
            True if updated
        """
        with self._get_connection() as conn:
            # Get start time to calculate duration
            row = conn.execute(
                'SELECT run_at FROM scoring_runs WHERE id = ?',
                (run_id,)
            ).fetchone()

            duration = None
            if row:
                start_time = datetime.fromisoformat(row['run_at'])
                duration = (datetime.now() - start_time).total_seconds()

            cursor = conn.execute('''
                UPDATE scoring_runs SET
                    completed_at = ?,
                    contacts_processed = ?,
                    contacts_scored = ?,
                    contacts_new = ?,
                    contacts_updated = ?,
                    run_duration_seconds = ?,
                    fub_api_calls = ?,
                    status = ?,
                    error_message = ?,
                    notes = ?
                WHERE id = ?
            ''', (
                datetime.now().isoformat(),
                contacts_processed, contacts_scored, contacts_new, contacts_updated,
                duration, fub_api_calls, status, error_message, notes, run_id
            ))
            conn.commit()
            return cursor.rowcount > 0

    def get_recent_scoring_runs(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent scoring runs.

        Args:
            limit: Maximum number of runs to return

        Returns:
            List of scoring run records
        """
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM scoring_runs
                ORDER BY run_at DESC
                LIMIT ?
            ''', (limit,)).fetchall()
            return [dict(row) for row in rows]

    def get_scoring_run_stats(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get aggregate stats about scoring runs.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with stats about scoring runs
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            stats = conn.execute('''
                SELECT
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_runs,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                    AVG(run_duration_seconds) as avg_duration_seconds,
                    SUM(contacts_processed) as total_contacts_processed,
                    SUM(fub_api_calls) as total_api_calls
                FROM scoring_runs
                WHERE run_at >= ?
            ''', (cutoff,)).fetchone()

            return dict(stats) if stats else {}

    def get_last_successful_run(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent successful scoring run.

        Returns:
            The scoring run record or None
        """
        with self._get_connection() as conn:
            row = conn.execute('''
                SELECT * FROM scoring_runs
                WHERE status = 'success'
                ORDER BY run_at DESC
                LIMIT 1
            ''').fetchone()
            return dict(row) if row else None

    def get_recent_contacts(self, days: int = 3) -> List[Dict[str, Any]]:
        """
        Get contacts created in the last N days, deduplicated by email.

        When duplicates exist (same email), keeps the most complete record
        (prefers the one with phone number).

        Args:
            days: Number of days to look back (default 3)

        Returns:
            List of contacts with name, created_at, and days_ago
        """
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        with self._get_connection() as conn:
            # Use GROUP BY with CASE to prefer records with phone numbers
            rows = conn.execute('''
                SELECT
                    MAX(CASE WHEN phone IS NOT NULL AND phone != '' THEN id ELSE id END) as id,
                    first_name,
                    last_name,
                    email,
                    MAX(phone) as phone,
                    stage,
                    source,
                    MIN(created_at) as created_at,
                    DATE(MIN(created_at)) as created_date,
                    CAST(julianday('now') - julianday(DATE(MIN(created_at))) AS INTEGER) as days_ago
                FROM leads
                WHERE DATE(created_at) >= ?
                GROUP BY LOWER(COALESCE(email, first_name || ' ' || last_name))
                ORDER BY MIN(created_at) DESC
            ''', (cutoff,)).fetchall()
            return [dict(row) for row in rows]

    # ==========================================
    # WORKFLOW OPERATIONS (Phase 4: Pipeline)
    # ==========================================

    # Workflow stage definitions
    WORKFLOW_STAGES = [
        ('new_lead', 'New Lead', 'Lead just created, no engagement yet'),
        ('requirements_discovery', 'Requirements Discovery', 'Gathering buyer requirements'),
        ('active_search', 'Active Search', 'Actively searching for properties'),
        ('reviewing_options', 'Reviewing Options', 'Reviewing property packages'),
        ('showing_scheduled', 'Showing Scheduled', 'Has upcoming showings'),
        ('post_showing', 'Post-Showing', 'Completed showings, awaiting feedback'),
        ('offer_pending', 'Offer Pending', 'Offer submitted'),
        ('under_contract', 'Under Contract', 'Contract accepted'),
        ('closed', 'Closed', 'Transaction completed'),
        ('nurture', 'Nurture', 'Long-term follow-up'),
    ]

    def get_contact_workflow(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """
        Get workflow state for a contact.

        Args:
            contact_id: Contact ID

        Returns:
            Workflow record or None if not found
        """
        with self._get_connection() as conn:
            row = conn.execute('''
                SELECT * FROM contact_workflow WHERE contact_id = ?
            ''', (contact_id,)).fetchone()

            if row:
                result = dict(row)
                # Parse JSON stage history
                if result.get('stage_history'):
                    try:
                        result['stage_history'] = json.loads(result['stage_history'])
                    except (json.JSONDecodeError, TypeError):
                        result['stage_history'] = []
                return result
            return None

    def ensure_contact_workflow(self, contact_id: str) -> Dict[str, Any]:
        """
        Get or create workflow record for a contact.

        Args:
            contact_id: Contact ID

        Returns:
            Workflow record (existing or newly created)
        """
        existing = self.get_contact_workflow(contact_id)
        if existing:
            return existing

        # Create new workflow record
        with self._get_connection() as conn:
            now = datetime.now().isoformat()
            conn.execute('''
                INSERT INTO contact_workflow (contact_id, current_stage, stage_entered_at, created_at, updated_at)
                VALUES (?, 'new_lead', ?, ?, ?)
            ''', (contact_id, now, now, now))
            conn.commit()

        return self.get_contact_workflow(contact_id)

    def update_contact_workflow_stage(
        self,
        contact_id: str,
        new_stage: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transition a contact to a new workflow stage.

        Args:
            contact_id: Contact ID
            new_stage: New stage name
            notes: Optional notes about the transition

        Returns:
            Updated workflow record
        """
        # Ensure workflow exists
        workflow = self.ensure_contact_workflow(contact_id)
        old_stage = workflow.get('current_stage', 'new_lead')

        if old_stage == new_stage:
            return workflow  # No change needed

        now = datetime.now().isoformat()
        stage_entered = workflow.get('stage_entered_at', now)

        # Calculate days in old stage
        try:
            entered_dt = datetime.fromisoformat(stage_entered)
            days_in_stage = (datetime.now() - entered_dt).days
        except (ValueError, TypeError):
            days_in_stage = 0

        # Build stage history
        history = workflow.get('stage_history', []) or []
        history.append({
            'stage': old_stage,
            'entered_at': stage_entered,
            'exited_at': now,
            'duration_days': days_in_stage
        })

        with self._get_connection() as conn:
            conn.execute('''
                UPDATE contact_workflow
                SET current_stage = ?,
                    stage_entered_at = ?,
                    stage_history = ?,
                    days_in_current_stage = 0,
                    last_stage_change_at = ?,
                    updated_at = ?,
                    notes = COALESCE(?, notes)
                WHERE contact_id = ?
            ''', (new_stage, now, json.dumps(history), now, now, notes, contact_id))
            conn.commit()

        return self.get_contact_workflow(contact_id)

    def get_workflow_pipeline(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all contacts grouped by workflow stage for pipeline view.

        Returns:
            Dict mapping stage names to lists of contacts
        """
        # Initialize all stages with empty lists
        pipeline = {stage[0]: [] for stage in self.WORKFLOW_STAGES}

        with self._get_connection() as conn:
            # Get all contacts with their workflow state
            rows = conn.execute('''
                SELECT
                    l.id, l.first_name, l.last_name, l.email, l.phone,
                    l.stage, l.heat_score, l.priority_score, l.value_score,
                    l.properties_viewed, l.properties_favorited,
                    l.days_since_activity, l.last_activity_at,
                    COALESCE(w.current_stage, 'new_lead') as workflow_stage,
                    w.stage_entered_at, w.days_in_current_stage,
                    w.workflow_status
                FROM leads l
                LEFT JOIN contact_workflow w ON l.id = w.contact_id
                WHERE l.stage NOT IN ('Closed', 'closed', 'Trash', 'trash')
                ORDER BY l.priority_score DESC
            ''').fetchall()

            for row in rows:
                contact = dict(row)
                stage = contact.get('workflow_stage', 'new_lead')
                if stage in pipeline:
                    pipeline[stage].append(contact)
                else:
                    # Unknown stage, put in new_lead
                    pipeline['new_lead'].append(contact)

        return pipeline

    def get_workflow_stage_counts(self) -> Dict[str, int]:
        """
        Get count of contacts in each workflow stage.

        Returns:
            Dict mapping stage names to counts
        """
        counts = {stage[0]: 0 for stage in self.WORKFLOW_STAGES}

        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT
                    COALESCE(w.current_stage, 'new_lead') as stage,
                    COUNT(*) as count
                FROM leads l
                LEFT JOIN contact_workflow w ON l.id = w.contact_id
                WHERE l.stage NOT IN ('Closed', 'closed', 'Trash', 'trash')
                GROUP BY COALESCE(w.current_stage, 'new_lead')
            ''').fetchall()

            for row in rows:
                stage = row['stage']
                if stage in counts:
                    counts[stage] = row['count']

        return counts

    def bulk_initialize_workflows(self) -> int:
        """
        Create workflow records for all contacts that don't have one.
        Useful for initial setup or migration.

        Returns:
            Number of workflow records created
        """
        with self._get_connection() as conn:
            now = datetime.now().isoformat()

            # Get contacts without workflow records
            result = conn.execute('''
                INSERT INTO contact_workflow (contact_id, current_stage, stage_entered_at, created_at, updated_at)
                SELECT l.id, 'new_lead', ?, ?, ?
                FROM leads l
                LEFT JOIN contact_workflow w ON l.id = w.contact_id
                WHERE w.contact_id IS NULL
            ''', (now, now, now))
            conn.commit()

            return result.rowcount

    def infer_workflow_stage(self, contact_id: str) -> str:
        """
        Infer the appropriate workflow stage based on contact activity.
        Used for automatic stage transitions.

        Args:
            contact_id: Contact ID

        Returns:
            Inferred stage name
        """
        with self._get_connection() as conn:
            # Get contact data
            contact = conn.execute('''
                SELECT * FROM leads WHERE id = ?
            ''', (contact_id,)).fetchone()

            if not contact:
                return 'new_lead'

            contact = dict(contact)

            # Check for intake forms
            intake = conn.execute('''
                SELECT COUNT(*) as count FROM intake_forms
                WHERE lead_id = ? AND status = 'active'
            ''', (contact_id,)).fetchone()
            has_intake = intake and intake['count'] > 0

            # Check for packages
            packages = conn.execute('''
                SELECT COUNT(*) as count, MAX(status) as max_status
                FROM property_packages WHERE lead_id = ?
            ''', (contact_id,)).fetchone()
            has_packages = packages and packages['count'] > 0
            package_sent = packages and packages['max_status'] in ('sent', 'ready')

            # Check for showings
            showings = conn.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN status = 'scheduled' AND scheduled_date >= date('now') THEN 1 ELSE 0 END) as upcoming,
                       SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
                FROM showings WHERE lead_id = ?
            ''', (contact_id,)).fetchone()
            has_upcoming_showing = showings and showings['upcoming'] > 0
            has_completed_showing = showings and showings['completed'] > 0

            # Inference logic based on plan
            if has_upcoming_showing:
                return 'showing_scheduled'
            elif has_completed_showing:
                return 'post_showing'
            elif package_sent:
                return 'reviewing_options'
            elif has_packages or (contact.get('properties_viewed', 0) >= 5):
                return 'active_search'
            elif has_intake or (contact.get('properties_viewed', 0) >= 2):
                return 'requirements_discovery'
            elif contact.get('days_since_activity', 999) > 30:
                return 'nurture'
            else:
                return 'new_lead'

    # ==========================================
    # REQUIREMENTS CONSOLIDATION (Phase 5)
    # ==========================================

    # Source confidence levels
    REQUIREMENT_SOURCES = {
        'intake': 0.9,      # Explicit from intake forms
        'behavioral': 0.7,  # Inferred from property views/favorites
        'notes': 0.6,       # Parsed from agent notes
        'override': 1.0,    # Manual agent override
    }

    def get_consolidated_requirements(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the consolidated requirements for a contact.

        Args:
            contact_id: Contact ID

        Returns:
            Consolidated requirements dict or None
        """
        with self._get_connection() as conn:
            row = conn.execute('''
                SELECT * FROM contact_requirements WHERE contact_id = ?
            ''', (contact_id,)).fetchone()

            if row:
                result = dict(row)
                # Parse JSON fields
                json_fields = ['counties', 'cities', 'property_types', 'must_have_features',
                              'nice_to_have_features', 'deal_breakers', 'views_required',
                              'water_features', 'agent_overrides']
                for field in json_fields:
                    if result.get(field):
                        try:
                            result[field] = json.loads(result[field])
                        except (json.JSONDecodeError, TypeError):
                            result[field] = []
                return result
            return None

    def consolidate_requirements(self, contact_id: str) -> Dict[str, Any]:
        """
        Consolidate requirements from all sources for a contact.
        Creates or updates the contact_requirements record.

        Sources (in priority order):
        1. Agent overrides (confidence 1.0)
        2. Intake forms (confidence 0.9)
        3. Behavioral analysis (confidence 0.7)
        4. Note parsing (confidence 0.6)

        Args:
            contact_id: Contact ID

        Returns:
            Consolidated requirements dict
        """
        # Gather data from all sources
        intake_reqs = self.get_stated_requirements(contact_id)
        behavioral_reqs = self.get_behavioral_preferences(contact_id)
        note_reqs = self.parse_requirements_from_notes(contact_id)

        # Get existing requirements for overrides
        existing = self.get_consolidated_requirements(contact_id)
        overrides = existing.get('agent_overrides', {}) if existing else {}

        # Build consolidated requirements
        consolidated = {
            'contact_id': contact_id,
        }

        # Helper to select best value based on confidence
        def select_best(field_name, sources):
            """Select the value with highest confidence."""
            best_value = None
            best_source = None
            best_confidence = 0

            # Check override first
            if field_name in overrides:
                return overrides[field_name], 'override', 1.0

            for source_name, source_data, base_confidence in sources:
                if source_data and field_name in source_data:
                    value = source_data[field_name]
                    if value is not None and value != '' and value != []:
                        # Adjust confidence based on data quality
                        confidence = base_confidence
                        if source_name == 'behavioral':
                            # Scale by behavioral confidence
                            confidence *= source_data.get('confidence', 0.5)
                        if confidence > best_confidence:
                            best_value = value
                            best_source = source_name
                            best_confidence = confidence

            return best_value, best_source, best_confidence

        # Sources list: (name, data, base_confidence)
        sources = [
            ('intake', intake_reqs, 0.9),
            ('behavioral', behavioral_reqs, 0.7),
            ('notes', note_reqs, 0.6),
        ]

        # Consolidate price
        price_min, price_min_src, price_min_conf = select_best('min_price', sources)
        price_max, price_max_src, price_max_conf = select_best('max_price', sources)

        # For behavioral, use price_range tuple
        if not price_min and behavioral_reqs and behavioral_reqs.get('price_range'):
            price_min = int(behavioral_reqs['price_range'][0] * 0.9)  # 10% buffer
            price_min_src = 'behavioral'
            price_min_conf = 0.7 * behavioral_reqs.get('confidence', 0.5)
        if not price_max and behavioral_reqs and behavioral_reqs.get('price_range'):
            price_max = int(behavioral_reqs['price_range'][1] * 1.1)  # 10% buffer
            price_max_src = 'behavioral'
            price_max_conf = 0.7 * behavioral_reqs.get('confidence', 0.5)

        consolidated['price_min'] = price_min
        consolidated['price_min_source'] = price_min_src
        consolidated['price_min_confidence'] = price_min_conf or 0
        consolidated['price_max'] = price_max
        consolidated['price_max_source'] = price_max_src
        consolidated['price_max_confidence'] = price_max_conf or 0

        # Consolidate size requirements
        beds_min, beds_src, beds_conf = select_best('min_beds', sources)
        consolidated['beds_min'] = beds_min
        consolidated['beds_min_source'] = beds_src
        consolidated['beds_min_confidence'] = beds_conf or 0

        baths_min, baths_src, baths_conf = select_best('min_baths', sources)
        consolidated['baths_min'] = baths_min
        consolidated['baths_min_source'] = baths_src
        consolidated['baths_min_confidence'] = baths_conf or 0

        sqft_min, sqft_src, sqft_conf = select_best('min_sqft', sources)
        consolidated['sqft_min'] = sqft_min
        consolidated['sqft_min_source'] = sqft_src
        consolidated['sqft_min_confidence'] = sqft_conf or 0

        acreage_min, acreage_src, acreage_conf = select_best('min_acreage', sources)
        consolidated['acreage_min'] = acreage_min
        consolidated['acreage_min_source'] = acreage_src
        consolidated['acreage_min_confidence'] = acreage_conf or 0

        # Consolidate location
        counties, counties_src, counties_conf = select_best('counties', sources)
        consolidated['counties'] = json.dumps(counties) if counties else None
        consolidated['counties_source'] = counties_src
        consolidated['counties_confidence'] = counties_conf or 0

        cities, cities_src, cities_conf = select_best('cities', sources)
        # For behavioral, cities come directly
        if not cities and behavioral_reqs and behavioral_reqs.get('cities'):
            cities = behavioral_reqs['cities']
            cities_src = 'behavioral'
            cities_conf = 0.7 * behavioral_reqs.get('confidence', 0.5)
        consolidated['cities'] = json.dumps(cities) if cities else None
        consolidated['cities_source'] = cities_src
        consolidated['cities_confidence'] = cities_conf or 0

        # Property types
        prop_types, prop_src, prop_conf = select_best('property_types', sources)
        consolidated['property_types'] = json.dumps(prop_types) if prop_types else None
        consolidated['property_types_source'] = prop_src
        consolidated['property_types_confidence'] = prop_conf or 0

        # Features
        must_have, must_src, must_conf = select_best('must_have_features', sources)
        consolidated['must_have_features'] = json.dumps(must_have) if must_have else None
        consolidated['must_have_source'] = must_src
        consolidated['must_have_confidence'] = must_conf or 0

        deal_breakers, db_src, db_conf = select_best('deal_breakers', sources)
        consolidated['deal_breakers'] = json.dumps(deal_breakers) if deal_breakers else None
        consolidated['deal_breakers_source'] = db_src
        consolidated['deal_breakers_confidence'] = db_conf or 0

        # Views and water
        views, views_src, views_conf = select_best('views_required', sources)
        consolidated['views_required'] = json.dumps(views) if views else None
        consolidated['views_source'] = views_src
        consolidated['views_confidence'] = views_conf or 0

        water, water_src, water_conf = select_best('water_features', sources)
        consolidated['water_features'] = json.dumps(water) if water else None
        consolidated['water_source'] = water_src
        consolidated['water_confidence'] = water_conf or 0

        # Timeline
        urgency, urgency_src, urgency_conf = select_best('urgency', sources)
        consolidated['urgency'] = urgency
        consolidated['urgency_source'] = urgency_src
        consolidated['urgency_confidence'] = urgency_conf or 0

        move_in, _, _ = select_best('move_in_date', sources)
        consolidated['move_in_date'] = move_in

        # Financing
        financing, fin_src, fin_conf = select_best('financing_status', sources)
        consolidated['financing_status'] = financing
        consolidated['financing_source'] = fin_src
        consolidated['financing_confidence'] = fin_conf or 0

        pre_approval, _, _ = select_best('pre_approval_amount', sources)
        consolidated['pre_approval_amount'] = pre_approval

        # Store overrides
        consolidated['agent_overrides'] = json.dumps(overrides) if overrides else None

        # Calculate overall confidence and completeness
        confidence_fields = [
            'price_min_confidence', 'price_max_confidence', 'beds_min_confidence',
            'counties_confidence', 'cities_confidence'
        ]
        confidences = [consolidated.get(f, 0) or 0 for f in confidence_fields]
        non_zero = [c for c in confidences if c > 0]
        consolidated['overall_confidence'] = sum(non_zero) / len(non_zero) if non_zero else 0

        # Data completeness
        key_fields = ['price_min', 'price_max', 'beds_min', 'counties', 'cities']
        populated = sum(1 for f in key_fields if consolidated.get(f))
        consolidated['data_completeness'] = populated / len(key_fields)

        consolidated['last_consolidated_at'] = datetime.now().isoformat()
        consolidated['updated_at'] = datetime.now().isoformat()

        # Upsert the record
        self._upsert_requirements(consolidated)

        return self.get_consolidated_requirements(contact_id)

    def _upsert_requirements(self, data: Dict[str, Any]) -> None:
        """Insert or update contact requirements."""
        with self._get_connection() as conn:
            # Check if exists
            existing = conn.execute(
                'SELECT id FROM contact_requirements WHERE contact_id = ?',
                (data['contact_id'],)
            ).fetchone()

            if existing:
                # Update
                set_parts = []
                values = []
                for key, value in data.items():
                    if key != 'contact_id':
                        set_parts.append(f'{key} = ?')
                        values.append(value)
                values.append(data['contact_id'])

                conn.execute(
                    f"UPDATE contact_requirements SET {', '.join(set_parts)} WHERE contact_id = ?",
                    values
                )
            else:
                # Insert
                data['created_at'] = datetime.now().isoformat()
                columns = ', '.join(data.keys())
                placeholders = ', '.join(['?' for _ in data])
                conn.execute(
                    f"INSERT INTO contact_requirements ({columns}) VALUES ({placeholders})",
                    list(data.values())
                )

            conn.commit()

    def override_requirement(
        self,
        contact_id: str,
        field_name: str,
        value: Any,
        changed_by: str = 'agent'
    ) -> Dict[str, Any]:
        """
        Override a specific requirement field.

        Args:
            contact_id: Contact ID
            field_name: Field to override (e.g., 'price_min', 'beds_min')
            value: New value
            changed_by: Who made the change

        Returns:
            Updated consolidated requirements
        """
        # Get current requirements
        current = self.get_consolidated_requirements(contact_id)
        if not current:
            # Consolidate first
            current = self.consolidate_requirements(contact_id)

        # Get current overrides
        overrides = current.get('agent_overrides', {}) or {}

        # Record old value for audit
        old_value = current.get(field_name)
        old_source = current.get(f'{field_name}_source')
        old_confidence = current.get(f'{field_name}_confidence')

        # Add override
        overrides[field_name] = value

        # Update the record
        with self._get_connection() as conn:
            conn.execute('''
                UPDATE contact_requirements
                SET agent_overrides = ?,
                    updated_at = ?
                WHERE contact_id = ?
            ''', (json.dumps(overrides), datetime.now().isoformat(), contact_id))

            # Record change in audit trail
            conn.execute('''
                INSERT INTO requirements_changes
                (contact_id, field_name, old_value, new_value, old_source, new_source,
                 old_confidence, new_confidence, change_reason, changed_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (contact_id, field_name, str(old_value), str(value),
                  old_source, 'override', old_confidence, 1.0, 'override', changed_by))

            conn.commit()

        # Re-consolidate to apply override
        return self.consolidate_requirements(contact_id)

    def parse_requirements_from_notes(self, contact_id: str) -> Dict[str, Any]:
        """
        Parse buyer requirements from FUB notes and agent notes.

        Uses regex patterns to extract:
        - Price ranges ($XXX-$XXX, under $XXX, up to $XXX)
        - Bedrooms (X bed, X BR, X bedroom)
        - Bathrooms (X bath, X BA)
        - Acreage (X acres, X+ acres)
        - Location mentions (county names, city names)

        Args:
            contact_id: Contact ID

        Returns:
            Dict of parsed requirements with confidence
        """
        import re

        parsed = {
            'confidence': 0.6,  # Base confidence for note parsing
        }

        # Get contact notes
        with self._get_connection() as conn:
            # Get from leads table
            contact = conn.execute(
                'SELECT notes FROM leads WHERE id = ?',
                (contact_id,)
            ).fetchone()

            # Get from intake forms (agent_notes field)
            intake_notes = conn.execute('''
                SELECT agent_notes, source_notes FROM intake_forms
                WHERE lead_id = ? AND (agent_notes IS NOT NULL OR source_notes IS NOT NULL)
            ''', (contact_id,)).fetchall()

        # Combine all notes
        all_notes = []
        if contact and contact['notes']:
            all_notes.append(contact['notes'])
        for note in intake_notes:
            if note['agent_notes']:
                all_notes.append(note['agent_notes'])
            if note['source_notes']:
                all_notes.append(note['source_notes'])

        if not all_notes:
            return parsed

        text = ' '.join(all_notes).lower()

        # Price patterns
        # "$300k-$500k", "$300,000 to $500,000", "under $400k", "up to 500k"
        price_patterns = [
            r'\$?([\d,]+)k?\s*[-–to]+\s*\$?([\d,]+)k?',  # Range
            r'under\s*\$?([\d,]+)k?',                      # Under X
            r'up\s*to\s*\$?([\d,]+)k?',                    # Up to X
            r'max(?:imum)?\s*\$?([\d,]+)k?',               # Max X
            r'budget[:\s]*\$?([\d,]+)k?',                  # Budget X
        ]

        for pattern in price_patterns[:1]:  # Range pattern
            match = re.search(pattern, text)
            if match:
                try:
                    min_val = int(match.group(1).replace(',', ''))
                    max_val = int(match.group(2).replace(',', ''))
                    # Handle "k" suffix
                    if min_val < 10000:
                        min_val *= 1000
                    if max_val < 10000:
                        max_val *= 1000
                    parsed['min_price'] = min_val
                    parsed['max_price'] = max_val
                    break
                except (ValueError, IndexError):
                    pass

        for pattern in price_patterns[1:]:  # Single value patterns
            if 'max_price' not in parsed:
                match = re.search(pattern, text)
                if match:
                    try:
                        val = int(match.group(1).replace(',', ''))
                        if val < 10000:
                            val *= 1000
                        parsed['max_price'] = val
                    except (ValueError, IndexError):
                        pass

        # Bedroom patterns
        bed_patterns = [
            r'(\d+)\+?\s*(?:bed|br|bedroom)',
            r'(\d+)\s*(?:bed|br|bedroom)',
        ]
        for pattern in bed_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    parsed['min_beds'] = int(match.group(1))
                    break
                except (ValueError, IndexError):
                    pass

        # Bathroom patterns
        bath_patterns = [
            r'(\d+(?:\.\d+)?)\+?\s*(?:bath|ba|bathroom)',
        ]
        for pattern in bath_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    parsed['min_baths'] = float(match.group(1))
                    break
                except (ValueError, IndexError):
                    pass

        # Acreage patterns
        acre_patterns = [
            r'(\d+(?:\.\d+)?)\+?\s*(?:acre|ac)',
            r'at\s*least\s*(\d+(?:\.\d+)?)\s*acre',
        ]
        for pattern in acre_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    parsed['min_acreage'] = float(match.group(1))
                    break
                except (ValueError, IndexError):
                    pass

        # County mentions (WNC counties)
        wnc_counties = ['macon', 'jackson', 'swain', 'cherokee', 'clay', 'graham',
                        'haywood', 'transylvania', 'henderson', 'buncombe', 'madison',
                        'yancey', 'mitchell', 'avery', 'watauga', 'ashe', 'alleghany']
        found_counties = []
        for county in wnc_counties:
            if county in text:
                found_counties.append(county.title())
        if found_counties:
            parsed['counties'] = found_counties

        # Common city mentions
        wnc_cities = ['franklin', 'highlands', 'cashiers', 'sylva', 'waynesville',
                      'asheville', 'brevard', 'hendersonville', 'murphy', 'robbinsville',
                      'bryson city', 'cherokee', 'maggie valley', 'canton', 'black mountain']
        found_cities = []
        for city in wnc_cities:
            if city in text:
                found_cities.append(city.title())
        if found_cities:
            parsed['cities'] = found_cities

        # Feature keywords
        must_have_keywords = ['must have', 'need', 'require', 'essential', 'important']
        deal_breaker_keywords = ['no ', "can't", 'cannot', 'won\'t', 'deal breaker', 'avoid']

        # Extract must-haves (simple approach)
        must_have_features = []
        common_features = ['garage', 'basement', 'view', 'mountain view', 'creek', 'river',
                          'main level', 'one level', 'single story', 'workshop', 'barn']
        for feature in common_features:
            if feature in text:
                # Check if it's a must-have context
                for keyword in must_have_keywords:
                    if keyword in text and feature in text[max(0, text.find(keyword)-50):text.find(keyword)+100]:
                        must_have_features.append(feature.title())
                        break

        if must_have_features:
            parsed['must_have_features'] = must_have_features

        # Calculate confidence based on how much was found
        found_count = len([k for k in parsed if k != 'confidence'])
        if found_count >= 3:
            parsed['confidence'] = 0.7
        elif found_count >= 1:
            parsed['confidence'] = 0.6
        else:
            parsed['confidence'] = 0

        return parsed

    def get_requirements_by_source(self, contact_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Get requirements broken down by source for comparison.

        Args:
            contact_id: Contact ID

        Returns:
            Dict with 'intake', 'behavioral', 'notes', 'consolidated' keys
        """
        return {
            'intake': self.get_stated_requirements(contact_id),
            'behavioral': self.get_behavioral_preferences(contact_id),
            'notes': self.parse_requirements_from_notes(contact_id),
            'consolidated': self.get_consolidated_requirements(contact_id),
        }

    def get_requirements_changes(
        self,
        contact_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get audit trail of requirement changes for a contact.

        Args:
            contact_id: Contact ID
            limit: Max records to return

        Returns:
            List of change records
        """
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM requirements_changes
                WHERE contact_id = ?
                ORDER BY changed_at DESC
                LIMIT ?
            ''', (contact_id, limit)).fetchall()
            return [dict(row) for row in rows]

    # ==========================================
    # FUB USERS OPERATIONS
    # ==========================================

    def sync_fub_users(self, users: List[Dict[str, Any]]) -> int:
        """
        Sync FUB users to local cache.

        Args:
            users: List of user dicts from FUB API

        Returns:
            Number of users synced
        """
        with self._get_connection() as conn:
            now = datetime.now().isoformat()
            count = 0

            for user in users:
                conn.execute('''
                    INSERT INTO fub_users (id, name, email, role, phone, picture_url, is_active, last_synced_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        email = excluded.email,
                        role = excluded.role,
                        phone = excluded.phone,
                        picture_url = excluded.picture_url,
                        is_active = 1,
                        last_synced_at = excluded.last_synced_at
                ''', (
                    user.get('id'),
                    user.get('name'),
                    user.get('email'),
                    user.get('role'),
                    user.get('phone'),
                    user.get('picture', {}).get('60x60') if isinstance(user.get('picture'), dict) else None,
                    now
                ))
                count += 1

            conn.commit()
            return count

    def get_fub_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a FUB user by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM fub_users WHERE id = ?',
                (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_fub_users(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all FUB users."""
        with self._get_connection() as conn:
            if active_only:
                rows = conn.execute(
                    'SELECT * FROM fub_users WHERE is_active = 1 ORDER BY name'
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM fub_users ORDER BY name'
                ).fetchall()
            return [dict(row) for row in rows]

    # ==========================================
    # ASSIGNMENT TRACKING OPERATIONS
    # ==========================================

    def update_contact_assignment(
        self,
        contact_id: str,
        new_user_id: int,
        new_user_name: str,
        source: str = 'sync'
    ) -> bool:
        """
        Update contact assignment and record in history if changed.

        Args:
            contact_id: Contact ID
            new_user_id: New FUB user ID
            new_user_name: New user's name
            source: Source of change ('sync', 'manual', 'round_robin', 'transfer')

        Returns:
            True if assignment changed, False if unchanged
        """
        with self._get_connection() as conn:
            now = datetime.now().isoformat()

            # Get current assignment
            row = conn.execute(
                'SELECT assigned_user_id, assigned_user_name FROM leads WHERE id = ?',
                (contact_id,)
            ).fetchone()

            if not row:
                return False

            old_user_id = row['assigned_user_id']
            old_user_name = row['assigned_user_name']

            # Check if assignment changed
            if old_user_id == new_user_id:
                return False

            # Update leads table
            conn.execute('''
                UPDATE leads SET
                    assigned_user_id = ?,
                    assigned_user_name = ?,
                    assigned_at = ?,
                    updated_at = ?
                WHERE id = ?
            ''', (new_user_id, new_user_name, now, now, contact_id))

            # Record in assignment history
            conn.execute('''
                INSERT INTO assignment_history
                (contact_id, assigned_from_user_id, assigned_from_user_name,
                 assigned_to_user_id, assigned_to_user_name, assigned_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                contact_id, old_user_id, old_user_name,
                new_user_id, new_user_name, now, source
            ))

            conn.commit()
            return True

    def get_contacts_assigned_to_user(
        self,
        user_id: int,
        include_history: bool = True,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Get all contacts currently assigned to a user.

        Args:
            user_id: FUB user ID
            include_history: Include assignment history for each contact
            limit: Maximum contacts to return

        Returns:
            List of contacts with optional assignment history
        """
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT l.*,
                       (SELECT COUNT(*) FROM assignment_history ah
                        WHERE ah.contact_id = l.id) as assignment_count
                FROM leads l
                WHERE l.assigned_user_id = ?
                ORDER BY l.assigned_at DESC NULLS LAST, l.priority_score DESC
                LIMIT ?
            ''', (user_id, limit)).fetchall()

            contacts = [dict(row) for row in rows]

            if include_history:
                for contact in contacts:
                    contact['assignment_history'] = self.get_assignment_history(
                        contact['id'], limit=10
                    )

            return contacts

    def get_assignment_history(
        self,
        contact_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get assignment history for a contact.

        Args:
            contact_id: Contact ID
            limit: Max records to return

        Returns:
            List of assignment changes, newest first
        """
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM assignment_history
                WHERE contact_id = ?
                ORDER BY assigned_at DESC
                LIMIT ?
            ''', (contact_id, limit)).fetchall()
            return [dict(row) for row in rows]

    def get_user_assignment_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Get assignment statistics for a user.

        Args:
            user_id: FUB user ID

        Returns:
            Stats dict with counts, dates, etc.
        """
        with self._get_connection() as conn:
            # Current assignments
            current = conn.execute('''
                SELECT COUNT(*) as count
                FROM leads
                WHERE assigned_user_id = ?
            ''', (user_id,)).fetchone()

            # Assignments received in last 30 days
            cutoff_30d = (datetime.now() - timedelta(days=30)).isoformat()
            received_30d = conn.execute('''
                SELECT COUNT(*) as count
                FROM assignment_history
                WHERE assigned_to_user_id = ? AND assigned_at >= ?
            ''', (user_id, cutoff_30d)).fetchone()

            # Assignments transferred out in last 30 days
            transferred_30d = conn.execute('''
                SELECT COUNT(*) as count
                FROM assignment_history
                WHERE assigned_from_user_id = ? AND assigned_at >= ?
            ''', (user_id, cutoff_30d)).fetchone()

            # Most recent assignment
            recent = conn.execute('''
                SELECT assigned_at, contact_id
                FROM assignment_history
                WHERE assigned_to_user_id = ?
                ORDER BY assigned_at DESC
                LIMIT 1
            ''', (user_id,)).fetchone()

            return {
                'current_count': current['count'] if current else 0,
                'received_30d': received_30d['count'] if received_30d else 0,
                'transferred_30d': transferred_30d['count'] if transferred_30d else 0,
                'most_recent_at': recent['assigned_at'] if recent else None,
                'most_recent_contact_id': recent['contact_id'] if recent else None,
            }

    def get_contacts_with_assignment_to_user(
        self,
        user_id: int,
        include_current: bool = True,
        include_past: bool = True,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Get contacts that have ever been assigned to a user, with assignment history.
        Shows most recent assignment date for sorting.

        Args:
            user_id: FUB user ID
            include_current: Include currently assigned contacts
            include_past: Include previously assigned contacts
            limit: Maximum contacts to return

        Returns:
            List of contacts with assignment info, ordered by most recent assignment
        """
        with self._get_connection() as conn:
            # Build conditions
            conditions = []
            params = []

            if include_current and include_past:
                # Get all contacts that have ever been assigned to this user
                conditions.append('''
                    l.id IN (
                        SELECT DISTINCT contact_id FROM assignment_history
                        WHERE assigned_to_user_id = ?
                    )
                ''')
                params.append(user_id)

                # Also include currently assigned (might not have history yet)
                conditions.append('l.assigned_user_id = ?')
                params.append(user_id)

                where_clause = '(' + ' OR '.join(conditions) + ')'
            elif include_current:
                where_clause = 'l.assigned_user_id = ?'
                params.append(user_id)
            elif include_past:
                where_clause = '''
                    l.id IN (
                        SELECT DISTINCT contact_id FROM assignment_history
                        WHERE assigned_to_user_id = ?
                    ) AND l.assigned_user_id != ?
                '''
                params.extend([user_id, user_id])
            else:
                return []

            # Get most recent assignment date to this user for each contact
            rows = conn.execute(f'''
                SELECT l.*,
                       l.assigned_user_id = ? as is_currently_assigned,
                       (SELECT MAX(assigned_at) FROM assignment_history ah
                        WHERE ah.contact_id = l.id AND ah.assigned_to_user_id = ?) as last_assigned_to_me,
                       (SELECT COUNT(*) FROM assignment_history ah
                        WHERE ah.contact_id = l.id AND ah.assigned_to_user_id = ?) as times_assigned_to_me
                FROM leads l
                WHERE {where_clause}
                ORDER BY
                    CASE WHEN l.assigned_user_id = ? THEN 0 ELSE 1 END,
                    (SELECT MAX(assigned_at) FROM assignment_history ah
                     WHERE ah.contact_id = l.id AND ah.assigned_to_user_id = ?) DESC NULLS LAST
                LIMIT ?
            ''', [user_id, user_id, user_id] + params + [user_id, user_id, limit]).fetchall()

            contacts = []
            for row in rows:
                contact = dict(row)
                contact['assignment_history'] = self.get_assignment_history(
                    contact['id'], limit=10
                )
                contacts.append(contact)

            return contacts

    # ==========================================
    # REASSIGNMENT DETECTION OPERATIONS
    # ==========================================

    def detect_reassigned_leads(
        self,
        user_id: int,
        current_fub_ids: set
    ) -> List[Dict[str, Any]]:
        """
        Detect leads that were previously assigned to a user but are no longer in FUB.

        This identifies leads that have been:
        - Reassigned via round-robin (speed to lead timeout)
        - Manually transferred to another agent
        - Deleted from FUB

        Args:
            user_id: The FUB user ID to check
            current_fub_ids: Set of FUB IDs currently assigned to this user (from FUB API)

        Returns:
            List of leads that are no longer assigned to this user
        """
        with self._get_connection() as conn:
            # Get all leads currently marked as assigned to this user in local DB
            # that don't have a reassigned_at timestamp yet
            rows = conn.execute('''
                SELECT id, fub_id, first_name, last_name, email, phone,
                       assigned_user_id, assigned_user_name, assigned_at,
                       stage, source, heat_score, priority_score
                FROM leads
                WHERE assigned_user_id = ?
                  AND reassigned_at IS NULL
            ''', (user_id,)).fetchall()

            reassigned = []
            for row in rows:
                lead = dict(row)
                fub_id = lead.get('fub_id') or lead.get('id')

                # If this lead's FUB ID is not in the current FUB response for this user,
                # it has been reassigned
                if str(fub_id) not in current_fub_ids:
                    reassigned.append(lead)

            return reassigned

    def mark_leads_as_reassigned(
        self,
        lead_ids: List[str],
        from_user_id: int,
        reason: str = 'unknown'
    ) -> int:
        """
        Mark leads as reassigned away from a user.

        Args:
            lead_ids: List of lead IDs (primary keys) to mark
            from_user_id: The user ID they were reassigned from
            reason: The reason for reassignment ('round_robin', 'transfer', 'deleted', 'unknown')

        Returns:
            Number of leads marked
        """
        if not lead_ids:
            return 0

        with self._get_connection() as conn:
            now = datetime.now().isoformat()
            count = 0

            for lead_id in lead_ids:
                conn.execute('''
                    UPDATE leads SET
                        reassigned_at = ?,
                        reassigned_from_user_id = ?,
                        reassigned_reason = ?,
                        updated_at = ?
                    WHERE id = ?
                ''', (now, from_user_id, reason, now, lead_id))
                count += 1

            conn.commit()
            return count

    def get_recently_reassigned_leads(
        self,
        from_user_id: int,
        days: int = 7,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get leads that were recently reassigned away from a user.

        Args:
            from_user_id: The user ID they were reassigned from
            days: Number of days to look back
            limit: Maximum leads to return

        Returns:
            List of reassigned leads with details
        """
        with self._get_connection() as conn:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            rows = conn.execute('''
                SELECT id, fub_id, first_name, last_name, email, phone,
                       reassigned_at, reassigned_from_user_id, reassigned_reason,
                       assigned_user_id, assigned_user_name,
                       stage, source, heat_score, priority_score
                FROM leads
                WHERE reassigned_from_user_id = ?
                  AND reassigned_at >= ?
                ORDER BY reassigned_at DESC
                LIMIT ?
            ''', (from_user_id, cutoff, limit)).fetchall()

            return [dict(row) for row in rows]

    def get_reassignment_stats(
        self,
        user_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get reassignment statistics for a user.

        Args:
            user_id: The FUB user ID
            days: Number of days to analyze

        Returns:
            Dict with reassignment stats
        """
        with self._get_connection() as conn:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            # Total reassigned in period
            total = conn.execute('''
                SELECT COUNT(*) as count
                FROM leads
                WHERE reassigned_from_user_id = ?
                  AND reassigned_at >= ?
            ''', (user_id, cutoff)).fetchone()

            # By reason
            by_reason = conn.execute('''
                SELECT reassigned_reason, COUNT(*) as count
                FROM leads
                WHERE reassigned_from_user_id = ?
                  AND reassigned_at >= ?
                GROUP BY reassigned_reason
            ''', (user_id, cutoff)).fetchall()

            return {
                'total_reassigned': total['count'] if total else 0,
                'by_reason': {row['reassigned_reason']: row['count'] for row in by_reason}
            }
