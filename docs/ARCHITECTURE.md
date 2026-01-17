# DREAMS Platform Architecture

*Technical Reference Document*

---

## Overview

This document defines the technical architecture for the DREAMS (Desktop Real Estate Agent Management System) platform. It is intended for developers extending the system and for architectural decision-making.

---

## Core Principles

### 1. Canonical Data Layer
All data flows through SQLite. External systems (CRMs, property sources, presentation tools) are adapters that read from and write to the canonical store.

### 2. Adapter Pattern
Every external integration implements a standard interface. Swapping one CRM for another requires only a new adapter implementation—zero changes to core logic.

### 3. Offline-First
The system must function without internet connectivity. Syncs happen when connected; core operations work locally.

### 4. Portable by Default
No cloud dependencies in the core. Users own their data file (SQLite) and can move it between machines.

---

## Database Schema

### SQLite Configuration
```sql
-- Enable WAL mode for crash recovery and concurrent reads
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```

### Core Tables

```sql
-- ============================================
-- LEADS TABLE
-- Canonical lead/contact record
-- ============================================
CREATE TABLE leads (
    id TEXT PRIMARY KEY,                    -- Internal DREAMS ID (UUID)
    external_id TEXT,                       -- CRM's ID for this lead
    external_source TEXT,                   -- Which CRM (fub, salesforce, etc.)
    
    -- Basic Info
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    
    -- Classification
    stage TEXT,                             -- lead, prospect, client, past_client
    type TEXT,                              -- buyer, seller, both, investor
    source TEXT,                            -- Where they came from
    
    -- Scoring (multi-dimensional)
    heat_score INTEGER DEFAULT 0,           -- 0-100: Engagement level
    value_score INTEGER DEFAULT 0,          -- 0-100: Transaction potential
    relationship_score INTEGER DEFAULT 0,   -- 0-100: Connection strength
    priority_score INTEGER DEFAULT 0,       -- 0-100: Calculated priority
    
    -- Buyer Requirements (inferred + stated)
    min_price INTEGER,
    max_price INTEGER,
    min_beds INTEGER,
    min_baths REAL,
    min_sqft INTEGER,
    min_acreage REAL,
    preferred_cities TEXT,                  -- JSON array
    preferred_features TEXT,                -- JSON array
    deal_breakers TEXT,                     -- JSON array
    requirements_confidence REAL,           -- 0.0-1.0: How sure are we?
    requirements_updated_at TEXT,
    
    -- Metadata
    assigned_agent TEXT,
    tags TEXT,                              -- JSON array
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TEXT,
    
    UNIQUE(external_id, external_source)
);

CREATE INDEX idx_leads_stage ON leads(stage);
CREATE INDEX idx_leads_type ON leads(type);
CREATE INDEX idx_leads_priority ON leads(priority_score DESC);


-- ============================================
-- LEAD ACTIVITIES TABLE
-- Behavioral signals from CRM
-- ============================================
CREATE TABLE lead_activities (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    
    activity_type TEXT NOT NULL,            -- search, save, favorite, inquiry, view, email_open, etc.
    activity_source TEXT,                   -- fub, real_geeks, zillow, etc.
    activity_data TEXT,                     -- JSON: details of the activity
    
    -- If activity relates to a property
    property_id TEXT,
    
    occurred_at TEXT NOT NULL,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (property_id) REFERENCES properties(id)
);

CREATE INDEX idx_activities_lead ON lead_activities(lead_id);
CREATE INDEX idx_activities_type ON lead_activities(activity_type);
CREATE INDEX idx_activities_date ON lead_activities(occurred_at DESC);


-- ============================================
-- PROPERTIES TABLE
-- All tracked properties
-- ============================================
CREATE TABLE properties (
    id TEXT PRIMARY KEY,                    -- Internal DREAMS ID (UUID)
    
    -- Identifiers
    mls_number TEXT,
    parcel_id TEXT,
    zillow_id TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    county TEXT,
    
    -- Core Attributes
    price INTEGER,
    beds INTEGER,
    baths REAL,
    sqft INTEGER,
    acreage REAL,
    year_built INTEGER,
    
    -- Property Details
    property_type TEXT,                     -- single_family, condo, land, etc.
    style TEXT,                             -- cabin, a-frame, ranch, modern, etc.
    
    -- Features (JSON arrays for flexibility)
    views TEXT,                             -- ["mountain", "valley", "forest"]
    water_features TEXT,                    -- ["creek", "pond", "well"]
    amenities TEXT,                         -- ["garage", "basement", "deck"]
    
    -- Status
    status TEXT DEFAULT 'active',           -- active, pending, sold, withdrawn
    days_on_market INTEGER,
    list_date TEXT,
    
    -- Agent Info
    listing_agent_name TEXT,
    listing_agent_phone TEXT,
    listing_agent_email TEXT,
    listing_brokerage TEXT,
    
    -- Links
    zillow_url TEXT,
    realtor_url TEXT,
    mls_url TEXT,
    idx_url TEXT,
    
    -- Monitoring
    initial_price INTEGER,
    price_history TEXT,                     -- JSON array of {date, price}
    status_history TEXT,                    -- JSON array of {date, status}
    
    -- Media
    photo_urls TEXT,                        -- JSON array
    virtual_tour_url TEXT,
    
    -- Metadata
    source TEXT,                            -- Where we got this property
    notes TEXT,
    captured_by TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_monitored_at TEXT
);

CREATE INDEX idx_properties_status ON properties(status);
CREATE INDEX idx_properties_city ON properties(city);
CREATE INDEX idx_properties_price ON properties(price);
CREATE INDEX idx_properties_mls ON properties(mls_number);


-- ============================================
-- MATCHES TABLE
-- Buyer-Property matching results
-- ============================================
CREATE TABLE matches (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    property_id TEXT NOT NULL,
    
    -- Scoring
    total_score REAL,                       -- 0-100: Overall match quality
    stated_score REAL,                      -- Score based on stated requirements
    behavioral_score REAL,                  -- Score based on activity signals
    
    -- Score Breakdown (JSON for detailed analysis)
    score_breakdown TEXT,                   -- {"price": 25, "location": 20, ...}
    
    -- Status
    match_status TEXT DEFAULT 'suggested',  -- suggested, sent, viewed, interested, rejected, shown
    
    -- Tracking
    suggested_at TEXT DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT,
    response_at TEXT,
    shown_at TEXT,
    
    -- Feedback
    lead_feedback TEXT,                     -- Why they liked/rejected
    agent_notes TEXT,
    
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (property_id) REFERENCES properties(id),
    UNIQUE(lead_id, property_id)
);

CREATE INDEX idx_matches_lead ON matches(lead_id);
CREATE INDEX idx_matches_property ON matches(property_id);
CREATE INDEX idx_matches_score ON matches(total_score DESC);


-- ============================================
-- PACKAGES TABLE
-- Generated showing packages
-- ============================================
CREATE TABLE packages (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    
    -- Package Contents
    title TEXT,
    property_ids TEXT,                      -- JSON array of property IDs
    showing_date TEXT,
    
    -- Output
    pdf_path TEXT,
    html_content TEXT,
    
    -- Status
    status TEXT DEFAULT 'draft',            -- draft, generated, sent, completed
    
    -- Tracking
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT,
    opened_at TEXT,
    
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);


-- ============================================
-- SYNC LOG TABLE
-- Track all sync operations
-- ============================================
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type TEXT NOT NULL,                -- leads, properties, activities
    source TEXT NOT NULL,                   -- fub, zillow, notion, etc.
    direction TEXT NOT NULL,                -- inbound, outbound
    
    records_processed INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    error_message TEXT,
    
    details TEXT                            -- JSON for additional context
);

CREATE INDEX idx_sync_log_type ON sync_log(sync_type, source);
CREATE INDEX idx_sync_log_date ON sync_log(started_at DESC);
```

---

## Adapter Interfaces

### Base CRM Adapter

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Lead:
    """Canonical lead representation"""
    id: str
    external_id: str
    external_source: str
    first_name: str
    last_name: str
    email: Optional[str]
    phone: Optional[str]
    stage: str
    type: str
    source: Optional[str]
    assigned_agent: Optional[str]
    tags: List[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

@dataclass
class Activity:
    """Canonical activity representation"""
    id: str
    lead_id: str
    activity_type: str
    activity_source: str
    activity_data: dict
    property_id: Optional[str]
    occurred_at: datetime

class CRMAdapter(ABC):
    """Abstract interface for CRM integrations"""
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to CRM"""
        pass
    
    @abstractmethod
    def fetch_leads(
        self, 
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Lead]:
        """Fetch leads from CRM"""
        pass
    
    @abstractmethod
    def fetch_lead(self, external_id: str) -> Optional[Lead]:
        """Fetch single lead by CRM ID"""
        pass
    
    @abstractmethod
    def fetch_activities(
        self, 
        lead_id: str,
        since: Optional[datetime] = None
    ) -> List[Activity]:
        """Fetch activities for a lead"""
        pass
    
    @abstractmethod
    def update_lead(self, lead: Lead) -> bool:
        """Push lead updates back to CRM"""
        pass
    
    @abstractmethod
    def create_note(self, lead_id: str, note: str) -> bool:
        """Add note to lead in CRM"""
        pass
```

### Base Property Adapter

```python
@dataclass
class Property:
    """Canonical property representation"""
    id: str
    mls_number: Optional[str]
    parcel_id: Optional[str]
    address: str
    city: str
    state: str
    zip: str
    price: int
    beds: int
    baths: float
    sqft: int
    acreage: Optional[float]
    property_type: str
    style: Optional[str]
    status: str
    days_on_market: Optional[int]
    listing_agent_name: Optional[str]
    listing_agent_phone: Optional[str]
    photo_urls: List[str]
    source: str
    source_url: str

class PropertyAdapter(ABC):
    """Abstract interface for property data sources"""
    
    @abstractmethod
    def search_properties(
        self,
        city: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_beds: Optional[int] = None,
        min_sqft: Optional[int] = None,
        **kwargs
    ) -> List[Property]:
        """Search for properties matching criteria"""
        pass
    
    @abstractmethod
    def fetch_property(self, url: str) -> Optional[Property]:
        """Fetch single property by URL"""
        pass
    
    @abstractmethod
    def monitor_property(self, property_id: str) -> Optional[Property]:
        """Check for updates to tracked property"""
        pass
```

### Base Presentation Adapter

```python
class PresentationAdapter(ABC):
    """Abstract interface for presentation layer (Notion, Airtable, etc.)"""
    
    @abstractmethod
    def sync_leads(self, leads: List[Lead]) -> int:
        """Push leads to presentation layer"""
        pass
    
    @abstractmethod
    def sync_properties(self, properties: List[Property]) -> int:
        """Push properties to presentation layer"""
        pass
    
    @abstractmethod
    def sync_matches(self, matches: List[Match]) -> int:
        """Push matches to presentation layer"""
        pass
    
    @abstractmethod
    def get_user_updates(self) -> List[dict]:
        """Pull any manual edits from presentation layer"""
        pass
```

---

## Matching Algorithm

### Overview

The matching engine scores properties against buyer requirements using a weighted multi-factor approach that prioritizes behavioral signals over stated preferences.

### Weight Distribution

| Factor | Weight | Source |
|--------|--------|--------|
| Price Fit | 25% | Stated + Behavioral |
| Location Match | 20% | Stated + Behavioral |
| Size Match (beds/baths/sqft) | 20% | Stated |
| Feature Match | 15% | Behavioral (saves, views) |
| Style Match | 10% | Behavioral |
| Recency/Freshness | 10% | Property DOM |

### Behavioral Signal Interpretation

```python
def infer_preferences_from_activities(activities: List[Activity]) -> BuyerPreferences:
    """
    Analyze lead activities to infer actual preferences.
    Actions speak louder than words.
    """
    
    # Track properties they've interacted with
    saved_properties = [a for a in activities if a.activity_type == 'save']
    favorited = [a for a in activities if a.activity_type == 'favorite']
    inquiries = [a for a in activities if a.activity_type == 'inquiry']
    views = [a for a in activities if a.activity_type == 'view']
    
    # Weight by signal strength
    weighted_properties = []
    for prop in saved_properties:
        weighted_properties.append((prop.property_id, 3.0))  # Saves are strong
    for prop in favorited:
        weighted_properties.append((prop.property_id, 2.5))  # Favorites are strong
    for prop in inquiries:
        weighted_properties.append((prop.property_id, 4.0))  # Inquiries are strongest
    for prop in views:
        weighted_properties.append((prop.property_id, 1.0))  # Views are weak
    
    # Analyze property attributes
    prices = []
    cities = []
    styles = []
    features = []
    
    for prop_id, weight in weighted_properties:
        prop = get_property(prop_id)
        if prop:
            prices.extend([prop.price] * int(weight))
            cities.extend([prop.city] * int(weight))
            if prop.style:
                styles.extend([prop.style] * int(weight))
            # ... extract other attributes
    
    # Calculate inferred ranges
    return BuyerPreferences(
        inferred_min_price=percentile(prices, 10),
        inferred_max_price=percentile(prices, 90),
        preferred_cities=most_common(cities, n=3),
        preferred_styles=most_common(styles, n=2),
        confidence=calculate_confidence(len(weighted_properties))
    )
```

### Final Score Calculation

```python
def calculate_match_score(lead: Lead, property: Property) -> MatchScore:
    """
    Calculate overall match score between lead and property.
    """
    
    # Get stated requirements
    stated = get_stated_requirements(lead)
    
    # Get inferred preferences from behavior
    activities = get_lead_activities(lead.id)
    behavioral = infer_preferences_from_activities(activities)
    
    scores = {}
    
    # Price scoring (25%)
    scores['price'] = score_price_fit(
        property.price,
        stated.min_price, stated.max_price,
        behavioral.inferred_min_price, behavioral.inferred_max_price
    ) * 25
    
    # Location scoring (20%)
    scores['location'] = score_location_fit(
        property.city,
        stated.preferred_cities,
        behavioral.preferred_cities
    ) * 20
    
    # Size scoring (20%)
    scores['size'] = score_size_fit(
        property.beds, property.baths, property.sqft,
        stated.min_beds, stated.min_baths, stated.min_sqft
    ) * 20
    
    # Feature scoring (15%)
    scores['features'] = score_feature_overlap(
        property.amenities + property.views + property.water_features,
        behavioral.preferred_features
    ) * 15
    
    # Style scoring (10%)
    scores['style'] = score_style_match(
        property.style,
        behavioral.preferred_styles
    ) * 10
    
    # Recency scoring (10%)
    scores['recency'] = score_freshness(property.days_on_market) * 10
    
    return MatchScore(
        total=sum(scores.values()),
        breakdown=scores,
        stated_component=scores['price'] * 0.5 + scores['size'],
        behavioral_component=scores['price'] * 0.5 + scores['location'] + scores['features'] + scores['style']
    )
```

---

## Data Flow Diagrams

### Lead Sync Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│     CRM     │────▶│  CRM Adapter │────▶│   SQLite    │
│ (FUB, etc.) │     │              │     │  leads      │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                                                ▼
                    ┌──────────────┐     ┌─────────────┐
                    │ Presentation │◀────│   Notion    │
                    │   Adapter    │     │  Adapter    │
                    └──────────────┘     └─────────────┘
```

### Property Capture Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Chrome    │────▶│   Zillow     │────▶│   SQLite    │
│  Extension  │     │   Adapter    │     │ properties  │
└─────────────┘     └──────────────┘     └─────────────┘
       │
       │           ┌──────────────┐
       └──────────▶│   ScraperAPI │ (for monitoring)
                   └──────────────┘
```

### Matching Flow

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│   SQLite    │────▶│  Matching   │────▶│   SQLite     │
│   leads     │     │   Engine    │     │   matches    │
└─────────────┘     └──────┬──────┘     └──────────────┘
                          │
┌─────────────┐           │
│   SQLite    │───────────┘
│ properties  │
└─────────────┘
```

---

## Configuration Management

### Environment Variables

```bash
# Core
DREAMS_DB_PATH=/path/to/dreams.db
DREAMS_LOG_LEVEL=INFO

# Follow Up Boss
FUB_API_KEY=your_api_key
FUB_BASE_URL=https://api.followupboss.com/v1

# Notion
NOTION_API_KEY=your_integration_token
NOTION_LEADS_DB=database_id
NOTION_PROPERTIES_DB=database_id

# ScraperAPI
SCRAPER_API_KEY=your_api_key

# Google Sheets (service account)
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service_account.json
GOOGLE_SPREADSHEET_ID=spreadsheet_id
```

### Configuration File

```yaml
# config/config.yaml
database:
  path: ${DREAMS_DB_PATH}
  wal_mode: true
  busy_timeout: 5000

sync:
  leads:
    schedule: "0 6,18 * * *"  # 6 AM and 6 PM
    batch_size: 100
  properties:
    schedule: "0 7 * * *"  # 7 AM daily
    monitoring_enabled: true

matching:
  weights:
    price: 0.25
    location: 0.20
    size: 0.20
    features: 0.15
    style: 0.10
    recency: 0.10
  behavioral_weight: 0.6
  stated_weight: 0.4
  min_score_threshold: 50

adapters:
  crm:
    active: followupboss
    available:
      - followupboss
      - salesforce
      - sierra
  
  presentation:
    active: notion
    available:
      - notion
      - airtable
      - sheets
```

---

## Shared UI Design System

### Color Palette

#### Primary Colors

| Color | Hex | Preview | Usage |
|-------|-----|---------|-------|
| Primary Blue | `#007bff` | ![#007bff](https://via.placeholder.com/20/007bff/007bff.png) | Primary actions, links |
| Success Green | `#28a745` | ![#28a745](https://via.placeholder.com/20/28a745/28a745.png) | Validated status, success states |
| Warning Yellow | `#ffc107` | ![#ffc107](https://via.placeholder.com/20/ffc107/ffc107.png) | Pending status, warnings |
| Danger Red | `#dc3545` | ![#dc3545](https://via.placeholder.com/20/dc3545/dc3545.png) | Errors, validation failures |
| Info Cyan | `#17a2b8` | ![#17a2b8](https://via.placeholder.com/20/17a2b8/17a2b8.png) | Informational messages |

#### Status Colors (IDX Validation)

| Status | Background | Text | Preview |
|--------|------------|------|---------|
| Validated | `#d4edda` | `#155724` | ![#d4edda](https://via.placeholder.com/60x20/d4edda/155724.png?text=+) |
| Pending | `#fff3cd` | `#856404` | ![#fff3cd](https://via.placeholder.com/60x20/fff3cd/856404.png?text=+) |
| Not Found | `#e2e3e5` | `#383d41` | ![#e2e3e5](https://via.placeholder.com/60x20/e2e3e5/383d41.png?text=+) |
| Error | `#f8d7da` | `#721c24` | ![#f8d7da](https://via.placeholder.com/60x20/f8d7da/721c24.png?text=+) |

#### Property Status Colors

| Status | Color | Preview | CSS Class |
|--------|-------|---------|-----------|
| Active | `#28a745` | ![#28a745](https://via.placeholder.com/20/28a745/28a745.png) | `.status-active` |
| Pending | `#ffc107` | ![#ffc107](https://via.placeholder.com/20/ffc107/ffc107.png) | `.status-pending` |
| Sold | `#6c757d` | ![#6c757d](https://via.placeholder.com/20/6c757d/6c757d.png) | `.status-sold` |
| Under Contract | `#fd7e14` | ![#fd7e14](https://via.placeholder.com/20/fd7e14/fd7e14.png) | `.status-contract` |

#### Background & Surface Colors

| Element | Color | Preview |
|---------|-------|---------|
| Page Background | `#f8f9fa` | ![#f8f9fa](https://via.placeholder.com/20/f8f9fa/f8f9fa.png) |
| Card Background | `#ffffff` | ![#ffffff](https://via.placeholder.com/20/ffffff/ffffff.png) |
| Table Header | `#e9ecef` | ![#e9ecef](https://via.placeholder.com/20/e9ecef/e9ecef.png) |
| Border Color | `#dee2e6` | ![#dee2e6](https://via.placeholder.com/20/dee2e6/dee2e6.png) |
| Text Primary | `#212529` | ![#212529](https://via.placeholder.com/20/212529/212529.png) |
| Text Secondary | `#6c757d` | ![#6c757d](https://via.placeholder.com/20/6c757d/6c757d.png) |

### CSS Variables (Proposed)

```css
:root {
  /* Primary palette */
  --color-primary: #007bff;
  --color-success: #28a745;
  --color-warning: #ffc107;
  --color-danger: #dc3545;
  --color-info: #17a2b8;

  /* IDX validation status */
  --idx-validated-bg: #d4edda;
  --idx-validated-text: #155724;
  --idx-pending-bg: #fff3cd;
  --idx-pending-text: #856404;
  --idx-not-found-bg: #e2e3e5;
  --idx-not-found-text: #383d41;
  --idx-error-bg: #f8d7da;
  --idx-error-text: #721c24;

  /* Surfaces */
  --bg-page: #f8f9fa;
  --bg-card: #ffffff;
  --bg-header: #e9ecef;
  --border-color: #dee2e6;

  /* Text */
  --text-primary: #212529;
  --text-secondary: #6c757d;
}
```

### Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Body | System UI / -apple-system | 14px | 400 |
| Headings | System UI / -apple-system | 18-24px | 600 |
| Table Data | Monospace (for numbers) | 13px | 400 |
| Badges | System UI | 12px | 500 |

### Component Patterns

#### Status Badges
```html
<span class="badge badge-success">Validated</span>
<span class="badge badge-warning">Pending</span>
<span class="badge badge-secondary">Not Found</span>
<span class="badge badge-danger">Error</span>
```

#### Action Buttons
```html
<button class="btn btn-primary btn-sm">Primary Action</button>
<button class="btn btn-outline-primary btn-sm">Secondary</button>
<button class="btn btn-link btn-sm">Text Link</button>
```

---

## Error Handling

### Standard Error Response

```python
@dataclass
class DREAMSError:
    code: str
    message: str
    details: Optional[dict] = None
    recoverable: bool = True

# Error codes
ERRORS = {
    'DB_CONNECTION': DREAMSError('DB001', 'Database connection failed'),
    'API_RATE_LIMIT': DREAMSError('API001', 'API rate limit exceeded', recoverable=True),
    'API_AUTH': DREAMSError('API002', 'API authentication failed', recoverable=False),
    'SYNC_PARTIAL': DREAMSError('SYNC001', 'Sync completed with errors'),
    'ADAPTER_MISSING': DREAMSError('ADAPT001', 'Required adapter not configured'),
}
```

### Retry Strategy

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60)
)
def api_call_with_retry(func, *args, **kwargs):
    """Wrap API calls with exponential backoff"""
    return func(*args, **kwargs)
```

---

## Testing Strategy

### Unit Tests
- Test each adapter in isolation with mocked responses
- Test matching algorithm with known inputs/outputs
- Test database operations with in-memory SQLite

### Integration Tests
- Test full sync pipeline with sandbox API accounts
- Test presentation layer sync with test workspaces
- Test package generation end-to-end

### Acceptance Tests
- Dolores workflow tests: Can she complete her daily tasks?
- Performance tests: Does matching run in <5 seconds for 1000 properties?
- Data integrity tests: Does data survive round-trip sync?

---

*Architecture document maintained by Joseph & Claude*
*Last updated: January 17, 2026*
