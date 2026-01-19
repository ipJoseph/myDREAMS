# DREAMS Data Dictionary

Database schema documentation for myDREAMS SQLite database.

**Last Updated:** 2026-01-19
**Database:** `dreams.db`
**Environments:** DEV (local) and PRD (178.156.221.10) - schemas synchronized

---

## Environment Comparison

| Table | DEV Rows | PRD Rows | Status |
|-------|----------|----------|--------|
| leads | 430 | 430 | ✓ Synced |
| contact_events | 5,446 | 5,446 | ✓ Synced |
| contact_communications | 274 | 274 | ✓ Synced |
| contact_properties | 0 | 0 | ✓ Synced |
| contact_scoring_history | 1,285 | 1,285 | ✓ Synced |
| lead_activities | 0 | 0 | ✓ Synced |
| properties | 164 | 164 | ✓ Synced |
| property_changes | 0 | 0 | ✓ Synced |
| idx_property_cache | 865* | 830 | ⚠ DEV ahead (cache populating) |
| matches | 0 | 0 | ✓ Synced |
| packages | 0 | 0 | ✓ Synced |
| sync_log | 0 | 0 | ✓ Synced |

*DEV cache continues to populate via background process

---

## Core Tables

### leads
Primary contact/lead table synced from Follow Up Boss (FUB).

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Internal UUID or FUB person ID |
| external_id | TEXT | External system ID |
| external_source | TEXT | Source system (e.g., 'fub') |
| first_name | TEXT | Contact first name |
| last_name | TEXT | Contact last name |
| email | TEXT | Primary email address |
| phone | TEXT | Primary phone number |
| stage | TEXT | Lead stage (default: 'lead') |
| type | TEXT | Lead type (default: 'buyer') |
| source | TEXT | Lead source |
| fub_id | TEXT | Follow Up Boss person ID |
| lead_type_tags | TEXT | JSON array of type tags |
| **Scoring Fields** | | |
| heat_score | INTEGER | Engagement/activity score (0-100) |
| value_score | INTEGER | Potential deal value score |
| relationship_score | INTEGER | Relationship strength score |
| priority_score | INTEGER | Combined priority ranking |
| score_trend | TEXT | 'warming', 'cooling', 'stable' |
| heat_score_7d_avg | REAL | 7-day rolling average heat score |
| last_score_recorded_at | TEXT | Last scoring snapshot timestamp |
| **Activity Metrics** | | |
| website_visits | INTEGER | Total website visits |
| properties_viewed | INTEGER | Total property views |
| properties_favorited | INTEGER | Total favorites |
| properties_shared | INTEGER | Total shares |
| calls_inbound | INTEGER | Inbound call count |
| calls_outbound | INTEGER | Outbound call count |
| texts_total | INTEGER | Total text messages |
| emails_received | INTEGER | Emails received |
| emails_sent | INTEGER | Emails sent |
| total_communications | INTEGER | Total comms count |
| total_events | INTEGER | Total events count |
| avg_price_viewed | REAL | Average price of viewed properties |
| days_since_activity | INTEGER | Days since last activity |
| last_activity_at | TEXT | Timestamp of last activity |
| **Intent Signals** | | |
| intent_repeat_views | INTEGER | Repeated property views |
| intent_high_favorites | INTEGER | High favorite activity |
| intent_activity_burst | INTEGER | Recent activity burst |
| intent_sharing | INTEGER | Sharing behavior |
| intent_signal_count | INTEGER | Total intent signals |
| **Preferences** | | |
| min_price | INTEGER | Minimum price preference |
| max_price | INTEGER | Maximum price preference |
| min_beds | INTEGER | Minimum bedrooms |
| min_baths | REAL | Minimum bathrooms |
| min_sqft | INTEGER | Minimum square footage |
| min_acreage | REAL | Minimum acreage |
| preferred_cities | TEXT | JSON array of preferred cities |
| preferred_features | TEXT | JSON array of preferred features |
| deal_breakers | TEXT | JSON array of deal breakers |
| requirements_confidence | REAL | Confidence in stated requirements |
| requirements_updated_at | TEXT | Last preference update |
| **Workflow** | | |
| assigned_agent | TEXT | Assigned agent name |
| tags | TEXT | JSON array of tags |
| notes | TEXT | Free-form notes |
| next_action | TEXT | Next action to take |
| next_action_date | TEXT | Due date for next action |
| **Timestamps** | | |
| created_at | TEXT | Record creation timestamp |
| updated_at | TEXT | Last update timestamp |
| last_synced_at | TEXT | Last FUB sync timestamp |

**Indexes:** `stage`, `priority_score DESC`, `fub_id`, `heat_score DESC`

---

### contact_events
Website activity events from FUB (property views, favorites, shares).

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Unique event ID |
| contact_id | TEXT FK | References leads.fub_id |
| event_type | TEXT | 'website_visit', 'property_view', 'property_favorite', 'property_share' |
| occurred_at | TEXT | Event timestamp |
| property_address | TEXT | Denormalized property address |
| property_price | INTEGER | Property price at time of event |
| property_mls | TEXT | MLS number |
| fub_event_id | TEXT | FUB event ID for deduplication |
| imported_at | TEXT | Import timestamp |

**Indexes:** `contact_id + occurred_at DESC`, `event_type`

---

### contact_communications
Call, text, and email records from FUB.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Unique communication ID |
| contact_id | TEXT FK | References leads.id |
| comm_type | TEXT | 'call', 'text', 'email' |
| direction | TEXT | 'inbound', 'outbound' |
| occurred_at | TEXT | Communication timestamp |
| duration_seconds | INTEGER | Call duration (calls only) |
| fub_id | TEXT | FUB record ID |
| fub_user_name | TEXT | Agent who handled it |
| status | TEXT | 'completed', 'missed', 'voicemail' |
| imported_at | TEXT | Import timestamp |

**Indexes:** `contact_id + occurred_at DESC`, `comm_type`

---

### contact_scoring_history
Daily snapshots of contact scores for trend analysis.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| contact_id | TEXT FK | References leads.id |
| recorded_at | TEXT | Snapshot timestamp |
| sync_id | INTEGER | Associated sync batch ID |
| heat_score | REAL | Heat score at snapshot |
| value_score | REAL | Value score at snapshot |
| relationship_score | REAL | Relationship score at snapshot |
| priority_score | REAL | Priority score at snapshot |
| website_visits | INTEGER | Cumulative visits |
| properties_viewed | INTEGER | Cumulative views |
| calls_inbound | INTEGER | Cumulative inbound calls |
| calls_outbound | INTEGER | Cumulative outbound calls |
| texts_total | INTEGER | Cumulative texts |
| intent_signal_count | INTEGER | Cumulative intent signals |
| heat_delta | REAL | Change from previous snapshot |
| trend_direction | TEXT | 'warming', 'cooling', 'stable' |

**Indexes:** `contact_id + recorded_at DESC`

---

### contact_properties
Junction table linking contacts to properties (saved, viewed, matched).

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Unique ID |
| contact_id | TEXT FK | References leads.id |
| property_id | TEXT FK | References properties.id |
| relationship | TEXT | 'saved', 'viewed', 'shared', 'matched', 'favorited' |
| match_score | REAL | Computed match score |
| view_count | INTEGER | Number of views |
| first_viewed_at | TEXT | First view timestamp |
| last_viewed_at | TEXT | Last view timestamp |
| saved_at | TEXT | Save timestamp |
| shared_at | TEXT | Share timestamp |
| shared_with | TEXT | JSON array of recipients |
| notes | TEXT | Notes |
| created_at | TEXT | Creation timestamp |
| updated_at | TEXT | Update timestamp |

**Indexes:** `contact_id`, `property_id`, `relationship`
**Constraints:** UNIQUE(contact_id, property_id)

---

## Property Tables

### properties
Property listings from various sources (Notion, Zillow, Redfin, IDX).

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Internal property ID |
| mls_number | TEXT | MLS listing number |
| parcel_id | TEXT | County parcel ID |
| zillow_id | TEXT | Zillow property ID |
| redfin_id | TEXT | Redfin property ID |
| realtor_id | TEXT | Realtor.com ID |
| address | TEXT | Full street address |
| city | TEXT | City |
| state | TEXT | State |
| zip | TEXT | ZIP code |
| county | TEXT | County |
| **Listing Details** | | |
| price | INTEGER | Current list price |
| beds | INTEGER | Bedrooms |
| baths | REAL | Bathrooms |
| sqft | INTEGER | Square footage |
| acreage | REAL | Lot size in acres |
| year_built | INTEGER | Year built |
| property_type | TEXT | Property type |
| style | TEXT | Architectural style |
| status | TEXT | 'active', 'pending', 'sold' |
| days_on_market | INTEGER | DOM |
| list_date | TEXT | Original list date |
| initial_price | INTEGER | Initial list price |
| price_history | TEXT | JSON price history |
| status_history | TEXT | JSON status history |
| **Features** | | |
| views | TEXT | View features |
| water_features | TEXT | Water features |
| amenities | TEXT | Amenities list |
| heating | TEXT | Heating type |
| cooling | TEXT | Cooling type |
| garage | TEXT | Garage details |
| sewer | TEXT | Sewer type |
| roof | TEXT | Roof type |
| stories | INTEGER | Number of stories |
| subdivision | TEXT | Subdivision name |
| **Location** | | |
| latitude | REAL | GPS latitude |
| longitude | REAL | GPS longitude |
| school_elementary_rating | INTEGER | Elementary school rating |
| school_middle_rating | INTEGER | Middle school rating |
| school_high_rating | INTEGER | High school rating |
| **Financial** | | |
| hoa_fee | INTEGER | Monthly HOA fee |
| tax_assessed_value | INTEGER | Tax assessed value |
| tax_annual_amount | INTEGER | Annual property tax |
| zestimate | INTEGER | Zillow estimate |
| rent_zestimate | INTEGER | Zillow rent estimate |
| **Engagement** | | |
| page_views | INTEGER | Listing page views |
| favorites_count | INTEGER | Favorites count |
| **Agent/Listing Info** | | |
| listing_agent_name | TEXT | Listing agent |
| listing_agent_phone | TEXT | Agent phone |
| listing_agent_email | TEXT | Agent email |
| listing_brokerage | TEXT | Listing brokerage |
| **URLs** | | |
| zillow_url | TEXT | Zillow listing URL |
| realtor_url | TEXT | Realtor.com URL |
| redfin_url | TEXT | Redfin URL |
| mls_url | TEXT | MLS URL |
| idx_url | TEXT | IDX URL |
| photo_urls | TEXT | JSON array of photo URLs |
| primary_photo | TEXT | Primary photo URL |
| virtual_tour_url | TEXT | Virtual tour URL |
| **IDX Validation** | | |
| idx_mls_number | TEXT | Validated IDX MLS# |
| original_mls_number | TEXT | Original MLS# before validation |
| idx_validation_status | TEXT | 'pending', 'validated', 'not_found' |
| idx_validated_at | TEXT | Validation timestamp |
| idx_mls_source | TEXT | IDX source |
| mls_source | TEXT | MLS data source |
| **Notion Sync** | | |
| notion_page_id | TEXT | Notion page ID |
| notion_synced_at | TEXT | Last Notion sync |
| sync_status | TEXT | 'pending', 'synced', 'error' |
| sync_error | TEXT | Sync error message |
| **Workflow** | | |
| added_for | TEXT | Client name |
| added_by | TEXT | Agent who added |
| source | TEXT | Data source |
| notes | TEXT | Notes |
| captured_by | TEXT | Capture source |
| **Timestamps** | | |
| created_at | TEXT | Creation timestamp |
| updated_at | TEXT | Update timestamp |
| last_monitored_at | TEXT | Last monitoring check |

**Indexes:** `status`, `city`, `price`, `zillow_id`, `mls_number`, `sync_status`, `redfin_id`, `idx_validation_status`

---

### property_changes
Tracks price and status changes for monitoring/alerts.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Change record ID |
| property_id | TEXT | Property ID or Notion page ID |
| property_address | TEXT | Property address |
| change_type | TEXT | 'price', 'status', 'dom', 'views', 'saves' |
| old_value | TEXT | Previous value |
| new_value | TEXT | New value |
| change_amount | INTEGER | Delta for price changes |
| detected_at | TEXT | Detection timestamp |
| notified | INTEGER | 0 = not notified, 1 = notified |
| source | TEXT | 'redfin', 'zillow', 'realtor' |
| notion_url | TEXT | Link to Notion page |

**Indexes:** `detected_at DESC`, `change_type`, `notified`

---

### idx_property_cache
Cache of MLS# to address mappings from IDX site scraping.

| Column | Type | Description |
|--------|------|-------------|
| mls_number | TEXT PK | MLS listing number |
| address | TEXT | Full address (or "[Not found on IDX]") |
| city | TEXT | City |
| price | INTEGER | Listed price |
| status | TEXT | 'Active', 'Pending', 'Sold' |
| photo_url | TEXT | Primary property photo URL |
| last_updated | TEXT | Last cache update |

**Purpose:** Populates address info for contact events that only have MLS#. Photo URLs provide fallback for properties without Notion photos.

---

## Supporting Tables

### lead_activities
Generic activity log for leads (not currently populated).

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Activity ID |
| lead_id | TEXT FK | References leads.id |
| activity_type | TEXT | Activity type |
| activity_source | TEXT | Source system |
| activity_data | TEXT | JSON activity data |
| property_id | TEXT | Associated property |
| occurred_at | TEXT | Activity timestamp |
| imported_at | TEXT | Import timestamp |

**Indexes:** `lead_id`, `activity_type`

---

### matches
Property match suggestions for leads (future use).

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Match ID |
| lead_id | TEXT FK | References leads.id |
| property_id | TEXT FK | References properties.id |
| total_score | REAL | Overall match score |
| stated_score | REAL | Based on stated preferences |
| behavioral_score | REAL | Based on viewing behavior |
| score_breakdown | TEXT | JSON score details |
| match_status | TEXT | 'suggested', 'sent', 'accepted', 'rejected' |
| suggested_at | TEXT | Suggestion timestamp |
| sent_at | TEXT | Sent to client timestamp |
| response_at | TEXT | Client response timestamp |
| shown_at | TEXT | Shown to client timestamp |
| lead_feedback | TEXT | Client feedback |
| agent_notes | TEXT | Agent notes |

**Indexes:** `lead_id`, `total_score DESC`
**Constraints:** UNIQUE(lead_id, property_id)

---

### packages
Property tour packages (future use).

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | Package ID |
| lead_id | TEXT FK | References leads.id |
| title | TEXT | Package title |
| property_ids | TEXT | JSON array of property IDs |
| showing_date | TEXT | Scheduled showing date |
| pdf_path | TEXT | Generated PDF path |
| html_content | TEXT | Package HTML content |
| status | TEXT | 'draft', 'sent', 'scheduled' |
| created_at | TEXT | Creation timestamp |
| sent_at | TEXT | Sent timestamp |
| opened_at | TEXT | Client opened timestamp |

---

### sync_log
Audit log for data synchronization operations.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| sync_type | TEXT | Type of sync operation |
| source | TEXT | Source system |
| direction | TEXT | 'import', 'export' |
| records_processed | INTEGER | Total records processed |
| records_created | INTEGER | New records created |
| records_updated | INTEGER | Records updated |
| records_failed | INTEGER | Failed records |
| started_at | TEXT | Sync start time |
| completed_at | TEXT | Sync completion time |
| error_message | TEXT | Error details |
| details | TEXT | JSON additional details |

---

## Data Flow

```
Follow Up Boss (FUB)
        │
        ▼
    fub-to-sheets sync (cron 11:00 daily)
        │
        ├──► leads table
        ├──► contact_events table
        ├──► contact_communications table
        └──► contact_scoring_history table

IDX Site (smokymountainhomes4sale.com)
        │
        ▼
    populate_idx_cache.py (cron 6:30 AM/PM)
        │
        └──► idx_property_cache table

Notion Properties Database
        │
        ▼
    property-dashboard app
        │
        └──► properties table (via API)
```

---

## Cron Jobs

| Schedule | Job | Environment |
|----------|-----|-------------|
| 11:00 daily | FUB Sync | PRD |
| 06:30, 18:30 | IDX Cache | DEV + PRD |

---

## Notes

1. **ID Formats:**
   - `leads.id`: UUID for older imports, FUB numeric ID for newer
   - `leads.fub_id`: Always FUB numeric person ID
   - Events use `fub_id` as `contact_id`, requiring lookup in some queries

2. **Empty Tables:** `lead_activities`, `matches`, `packages`, `contact_properties`, `property_changes`, `sync_log` are schema-ready but not yet populated.

3. **Sync Strategy:** DEV→PRD via `scp` of `dreams.db` file. IDX cache continues building independently on both.
