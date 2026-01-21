-- DREAMS Buyer Workflow Schema Extension
-- Adds intake forms, property packages, and showing management

-- =============================================================================
-- INTAKE FORMS - Captures buyer requirements per property need
-- =============================================================================
-- One buyer can have multiple intake forms (primary home, rental, investment, etc.)

CREATE TABLE IF NOT EXISTS intake_forms (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,                    -- Link to leads table (buyer)

    -- Form metadata
    form_name TEXT,                           -- "John's Primary Home Search"
    need_type TEXT NOT NULL,                  -- 'primary_home', 'child_home', 'str', 'ltr', 'investment', 'land', 'second_home'
    status TEXT DEFAULT 'active',             -- 'active', 'paused', 'completed', 'cancelled'
    priority INTEGER DEFAULT 1,               -- 1=highest priority

    -- Source of requirements
    source TEXT,                              -- 'idx_activity', 'phone_call', 'email', 'in_person', 'text'
    source_date TEXT,                         -- When requirements were captured
    source_notes TEXT,                        -- Notes about the conversation

    -- Location criteria
    counties TEXT,                            -- JSON array: ["Macon", "Jackson"]
    cities TEXT,                              -- JSON array: ["Franklin", "Highlands"]
    zip_codes TEXT,                           -- JSON array: ["28734", "28741"]
    subdivisions TEXT,                        -- JSON array

    -- Property criteria
    property_types TEXT,                      -- JSON array: ["Single Family", "Condo", "Land"]
    min_price INTEGER,
    max_price INTEGER,
    min_beds INTEGER,
    max_beds INTEGER,
    min_baths REAL,
    max_baths REAL,
    min_sqft INTEGER,
    max_sqft INTEGER,
    min_acreage REAL,
    max_acreage REAL,
    min_year_built INTEGER,
    max_year_built INTEGER,

    -- Features/amenities
    views_required TEXT,                      -- JSON array: ["Mountain", "Lake", "Long Range"]
    water_features TEXT,                      -- JSON array: ["Creek", "Pond", "River Access"]
    style_preferences TEXT,                   -- JSON array: ["Ranch", "Cabin", "Contemporary"]
    must_have_features TEXT,                  -- JSON array: ["Garage", "Basement", "Main Level Primary"]
    nice_to_have_features TEXT,               -- JSON array
    deal_breakers TEXT,                       -- JSON array: ["HOA", "Steep Driveway", "No Cell Service"]

    -- Investment specific (for STR/LTR/Investment)
    target_cap_rate REAL,                     -- Target cap rate %
    target_rental_income INTEGER,             -- Monthly rental target
    accepts_fixer_upper INTEGER DEFAULT 0,    -- Boolean

    -- Timeline
    urgency TEXT,                             -- 'asap', '1-3_months', '3-6_months', '6-12_months', 'flexible'
    move_in_date TEXT,                        -- Target date
    financing_status TEXT,                    -- 'pre_approved', 'cash', 'needs_pre_approval', 'unknown'
    pre_approval_amount INTEGER,

    -- Agent notes
    agent_notes TEXT,
    confidence_score INTEGER,                 -- 1-10 how confident we are in requirements
    last_reviewed_at TEXT,

    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

CREATE INDEX IF NOT EXISTS idx_intake_lead ON intake_forms(lead_id);
CREATE INDEX IF NOT EXISTS idx_intake_status ON intake_forms(status);
CREATE INDEX IF NOT EXISTS idx_intake_need_type ON intake_forms(need_type);

-- =============================================================================
-- PROPERTY PACKAGES - Groups of properties for buyer presentation
-- =============================================================================

CREATE TABLE IF NOT EXISTS property_packages (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,                    -- Which buyer this package is for
    intake_form_id TEXT,                      -- Which intake form drove this search (optional)

    -- Package info
    name TEXT NOT NULL,                       -- "Highlands Mountain Views - Jan 2025"
    description TEXT,
    status TEXT DEFAULT 'draft',              -- 'draft', 'ready', 'sent', 'viewed', 'archived'

    -- Presentation tracking
    sent_at TEXT,                             -- When package was sent to client
    viewed_at TEXT,                           -- When client first viewed
    view_count INTEGER DEFAULT 0,

    -- Client link
    share_token TEXT UNIQUE,                  -- Unique token for client access URL
    share_url TEXT,                           -- Full shareable URL
    expires_at TEXT,                          -- Optional expiration

    -- Agent info
    created_by TEXT,                          -- Agent who created
    notes TEXT,

    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (intake_form_id) REFERENCES intake_forms(id)
);

CREATE INDEX IF NOT EXISTS idx_package_lead ON property_packages(lead_id);
CREATE INDEX IF NOT EXISTS idx_package_status ON property_packages(status);
CREATE INDEX IF NOT EXISTS idx_package_token ON property_packages(share_token);

-- =============================================================================
-- PACKAGE PROPERTIES - Junction table linking properties to packages
-- =============================================================================

CREATE TABLE IF NOT EXISTS package_properties (
    id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL,
    property_id TEXT NOT NULL,

    -- Ordering and notes
    display_order INTEGER DEFAULT 0,          -- Order in presentation
    agent_notes TEXT,                         -- Private notes for agent
    client_notes TEXT,                        -- Notes visible to client
    highlight_features TEXT,                  -- JSON array of features to highlight

    -- Client interaction tracking
    client_favorited INTEGER DEFAULT 0,       -- Client marked as favorite
    client_rating INTEGER,                    -- 1-5 stars from client
    client_comments TEXT,                     -- Client feedback
    client_viewed_at TEXT,                    -- When client viewed this property

    -- Status
    showing_requested INTEGER DEFAULT 0,      -- Client wants to see it
    showing_scheduled_at TEXT,
    showing_completed_at TEXT,

    -- Timestamps
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (package_id) REFERENCES property_packages(id) ON DELETE CASCADE,
    FOREIGN KEY (property_id) REFERENCES properties(id),
    UNIQUE(package_id, property_id)
);

CREATE INDEX IF NOT EXISTS idx_pkg_prop_package ON package_properties(package_id);
CREATE INDEX IF NOT EXISTS idx_pkg_prop_property ON package_properties(property_id);
CREATE INDEX IF NOT EXISTS idx_pkg_prop_favorited ON package_properties(client_favorited);

-- =============================================================================
-- SHOWINGS - Schedule and track property showings
-- =============================================================================

CREATE TABLE IF NOT EXISTS showings (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    package_id TEXT,                          -- Optional link to package

    -- Showing info
    name TEXT,                                -- "Tour with John Smith"
    status TEXT DEFAULT 'scheduled',          -- 'scheduled', 'confirmed', 'completed', 'cancelled', 'rescheduled'
    scheduled_date TEXT NOT NULL,             -- Date of showing
    scheduled_time TEXT,                      -- Start time
    estimated_duration INTEGER,               -- Minutes

    -- Route info
    meeting_point TEXT,                       -- Where to meet
    meeting_address TEXT,
    route_optimized INTEGER DEFAULT 0,        -- Has route been optimized?
    route_data TEXT,                          -- JSON with route/directions
    total_drive_time INTEGER,                 -- Estimated total drive time (minutes)
    total_distance REAL,                      -- Total distance (miles)

    -- Notes
    agent_notes TEXT,
    client_notes TEXT,
    showing_instructions TEXT,                -- Compiled showing instructions

    -- Follow up
    feedback_requested_at TEXT,
    feedback_received_at TEXT,
    overall_feedback TEXT,

    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,

    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (package_id) REFERENCES property_packages(id)
);

CREATE INDEX IF NOT EXISTS idx_showings_lead ON showings(lead_id);
CREATE INDEX IF NOT EXISTS idx_showings_date ON showings(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_showings_status ON showings(status);

-- =============================================================================
-- SHOWING PROPERTIES - Properties in a showing tour
-- =============================================================================

CREATE TABLE IF NOT EXISTS showing_properties (
    id TEXT PRIMARY KEY,
    showing_id TEXT NOT NULL,
    property_id TEXT NOT NULL,

    -- Order and timing
    stop_order INTEGER NOT NULL,              -- Order in the tour
    scheduled_time TEXT,                      -- Planned arrival time
    time_at_property INTEGER DEFAULT 30,      -- Minutes to spend

    -- Showing details
    showing_type TEXT,                        -- 'exterior_only', 'interior', 'open_house', 'virtual'
    access_info TEXT,                         -- Lockbox code, contact info
    special_instructions TEXT,

    -- Results
    actual_arrival_time TEXT,
    actual_departure_time TEXT,
    client_interest_level INTEGER,            -- 1-5
    client_feedback TEXT,
    photos_taken TEXT,                        -- JSON array of photo URLs

    -- Status
    status TEXT DEFAULT 'pending',            -- 'pending', 'confirmed', 'shown', 'skipped', 'cancelled'
    skip_reason TEXT,

    FOREIGN KEY (showing_id) REFERENCES showings(id) ON DELETE CASCADE,
    FOREIGN KEY (property_id) REFERENCES properties(id),
    UNIQUE(showing_id, property_id)
);

CREATE INDEX IF NOT EXISTS idx_show_prop_showing ON showing_properties(showing_id);
CREATE INDEX IF NOT EXISTS idx_show_prop_order ON showing_properties(showing_id, stop_order);

-- =============================================================================
-- PROPERTY MONITORING - Track what properties need updates
-- =============================================================================

CREATE TABLE IF NOT EXISTS property_monitors (
    id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL UNIQUE,

    -- What to monitor
    monitor_price INTEGER DEFAULT 1,
    monitor_status INTEGER DEFAULT 1,
    monitor_dom INTEGER DEFAULT 1,
    monitor_photos INTEGER DEFAULT 1,
    monitor_views INTEGER DEFAULT 1,

    -- Last known values (for change detection)
    last_price INTEGER,
    last_status TEXT,
    last_dom INTEGER,
    last_photo_count INTEGER,
    last_views INTEGER,
    last_favorites INTEGER,

    -- Monitoring status
    last_checked_at TEXT,
    last_changed_at TEXT,
    check_frequency TEXT DEFAULT 'daily',     -- 'hourly', 'daily', 'weekly'
    is_active INTEGER DEFAULT 1,

    -- Alert settings
    alert_on_price_drop INTEGER DEFAULT 1,
    alert_on_status_change INTEGER DEFAULT 1,
    price_drop_threshold REAL DEFAULT 0.05,   -- 5% drop triggers alert

    FOREIGN KEY (property_id) REFERENCES properties(id)
);

CREATE INDEX IF NOT EXISTS idx_monitors_active ON property_monitors(is_active);
CREATE INDEX IF NOT EXISTS idx_monitors_last_check ON property_monitors(last_checked_at);

-- =============================================================================
-- PROPERTY CHANGES - Log of detected changes
-- =============================================================================

CREATE TABLE IF NOT EXISTS property_changes (
    id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL,

    -- Change details
    change_type TEXT NOT NULL,                -- 'price', 'status', 'dom', 'photos', 'views'
    old_value TEXT,
    new_value TEXT,
    change_percent REAL,                      -- For numeric changes

    -- Context
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source TEXT,                              -- 'redfin', 'mls', 'zillow', 'manual'

    -- Notification
    notification_sent INTEGER DEFAULT 0,
    notified_leads TEXT,                      -- JSON array of lead IDs notified

    FOREIGN KEY (property_id) REFERENCES properties(id)
);

CREATE INDEX IF NOT EXISTS idx_changes_property ON property_changes(property_id);
CREATE INDEX IF NOT EXISTS idx_changes_type ON property_changes(change_type);
CREATE INDEX IF NOT EXISTS idx_changes_date ON property_changes(detected_at);
