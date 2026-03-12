# myDREAMS Data Dictionary

*Generated 2026-03-12*

## Overview

- **Database**: SQLite at `data/dreams.db`
- **Total tables**: 44
- **Total listings**: 54,486 (53,899 IDX-eligible, 587 BBO-only)

---

## IDX vs BBO Audit Summary

**Current state**: All data lives in a single `listings` table. IDX and BBO data are **not** in separate tables. The `idx_opt_in` flag (0 or 1) distinguishes them.

**Public API compliance**: The public API (`/api/public/*`) correctly filters with `WHERE idx_opt_in = 1` on every query. BBO-only fields (`private_remarks`, `showing_instructions`, `buyer_agent_*`) are excluded from the `PUBLIC_LISTING_FIELDS` whitelist. **No BBO data is currently leaking to the public site.**

See: [IDX/BBO Separation Plan](#idxbbo-separation-plan) at end of document.

---

## Table Groups

### 1. Property Data (MLS)

#### `listings` (54,486 rows)
The single canonical property table. All MLS sources write here.

| Field | Type | Sample | Notes |
|-------|------|--------|-------|
| id | TEXT PK | `lst_bf51c559eac6` | Generated hash ID |
| parcel_id | TEXT | | FK to parcels (unused) |
| mls_source | TEXT | `NavicaMLS` | Source MLS system |
| mls_number | TEXT | `26040941` | MLS listing number |
| status | TEXT | `ACTIVE` | ACTIVE, PENDING, SOLD, EXPIRED, WITHDRAWN, HOLD |
| list_price | INTEGER | `449000` | Current list price |
| original_list_price | INTEGER | `465000` | Original list price |
| list_date | TEXT | `2026-01-15` | Date listed |
| sold_price | INTEGER | `440000` | Sale price (sold only) |
| sold_date | TEXT | `2026-02-28` | Date sold |
| days_on_market | INTEGER | `45` | DOM from MLS |
| beds | INTEGER | `3` | Bedrooms |
| baths | REAL | `2.0` | Bathrooms |
| sqft | INTEGER | `1850` | Heated square footage |
| year_built | INTEGER | `2005` | Year constructed |
| property_type | TEXT | `Residential` | Residential, Land, Commercial |
| property_subtype | TEXT | `Single Family` | |
| style | TEXT | `Ranch` | Architectural style |
| acreage | REAL | `2.5` | Lot acreage |
| lot_sqft | INTEGER | `108900` | Lot size in sqft |
| stories | INTEGER | `2` | Number of stories |
| garage_spaces | INTEGER | `2` | |
| address | TEXT | `123 Mountain View Dr` | Street address |
| city | TEXT | `Franklin` | City |
| state | TEXT | `NC` | State (default NC) |
| zip | TEXT | `28734` | ZIP code |
| county | TEXT | `Macon` | County |
| latitude | REAL | `35.1822` | GPS latitude |
| longitude | REAL | `-83.3818` | GPS longitude |
| subdivision | TEXT | `Mountain Estates` | Subdivision name |
| views | TEXT | `Mountain View,Long Range` | View types |
| amenities | TEXT | | Community amenities |
| heating | TEXT | `Heat Pump` | Heating type |
| cooling | TEXT | `Central Air` | Cooling type |
| appliances | TEXT | | Appliances included |
| interior_features | TEXT | | Interior features |
| exterior_features | TEXT | | Exterior features |
| water_source | TEXT | `Well` | Water source |
| sewer | TEXT | `Septic` | Sewer type |
| construction_materials | TEXT | | Construction materials |
| foundation | TEXT | | Foundation type |
| flooring | TEXT | | Flooring types |
| fireplace_features | TEXT | | Fireplace info |
| parking_features | TEXT | | Parking details |
| roof | TEXT | `Metal` | Roof type |
| hoa_fee | INTEGER | `275` | HOA fee amount |
| hoa_frequency | TEXT | `Annually` | HOA payment frequency |
| tax_annual_amount | INTEGER | `1850` | Annual property tax |
| tax_assessed_value | INTEGER | `185000` | Tax assessed value |
| tax_year | INTEGER | `2025` | Tax year |
| photos | TEXT | `["https://..."]` | JSON array of photo URLs |
| primary_photo | TEXT | `https://dvvjkgh...` | Main photo URL |
| photo_count | INTEGER | `15` | Number of photos |
| photo_local_path | TEXT | `data/photos/navica/26040941.jpg` | Local cached photo |
| photo_source | TEXT | `navica` | Photo origin |
| photo_confidence | REAL | | Photo match confidence |
| photo_verified_at | TEXT | | When photo was verified |
| photo_review_status | TEXT | `verified` | Photo verification status |
| virtual_tour_url | TEXT | | Virtual tour link |
| listing_agent_id | TEXT | `2598_12` | Agent ID |
| listing_agent_name | TEXT | `John Smith` | Agent name |
| listing_agent_phone | TEXT | `828-555-1234` | Agent phone |
| listing_agent_email | TEXT | `john@example.com` | Agent email |
| listing_office_id | TEXT | `2598` | Office ID |
| listing_office_name | TEXT | `Mountain Realty` | Office name |
| buyer_agent_id | TEXT | | **BBO only**: buyer's agent ID |
| buyer_agent_name | TEXT | | **BBO only**: buyer's agent name |
| buyer_office_id | TEXT | | **BBO only**: buyer's office ID |
| buyer_office_name | TEXT | | **BBO only**: buyer's office name |
| public_remarks | TEXT | `Welcome to this...` | Public description (IDX safe) |
| private_remarks | TEXT | | **BBO only**: agent-to-agent notes |
| showing_instructions | TEXT | | **BBO only**: showing access info |
| directions | TEXT | | Directions to property |
| mls_url | TEXT | | MLS listing URL |
| idx_url | TEXT | | IDX listing URL |
| idx_opt_in | INTEGER | `1` | **1=IDX eligible, 0=BBO only** |
| idx_address_display | INTEGER | `1` | 1=show address, 0=suppress |
| vow_opt_in | INTEGER | | Virtual Office Website opt-in |
| listing_key | TEXT | `edd5b2b5f54c...` | MLS unique key |
| parcel_number | TEXT | `7539816761` | Tax parcel number |
| expiration_date | TEXT | `2026-08-22` | Listing expiration |
| modification_timestamp | TEXT | | Last MLS modification |
| documents_count | INTEGER | `6` | Attached document count |
| documents_available | TEXT | `["Survey/Plat"]` | JSON array of doc types |
| documents_change_timestamp | TEXT | | |
| elevation_feet | INTEGER | `3200` | **Enriched**: elevation |
| flood_zone | TEXT | `X` | **Enriched**: FEMA flood zone |
| flood_factor | INTEGER | `1` | **Enriched**: flood risk 1-10 |
| view_potential | INTEGER | `4` | **Enriched**: view score 1-5 |
| is_residential | INTEGER | `1` | Residential flag |
| source | TEXT | `navica` | Data source system |
| captured_at | TEXT | `2026-02-19T23:26:58` | First import timestamp |
| updated_at | TEXT | `2026-03-12T02:00:14` | Last update timestamp |
| added_for | TEXT | | Client this was added for |
| added_by | TEXT | | Who added it |
| notes | TEXT | | Agent notes |

#### `agents` (645 rows)
MLS agent/office records synced from Navica.

| Field | Type | Sample | Notes |
|-------|------|--------|-------|
| id | TEXT PK | `2598_12` | Agent ID |
| mls_source | TEXT | `NavicaMLS` | Source MLS |
| mls_agent_id | TEXT | | MLS-specific agent ID |
| mls_office_id | TEXT | | MLS office ID |
| name | TEXT | `Wanda Jones` | Display name |
| full_name | TEXT | `Wanda J. Jones` | Full name (Navica) |
| first_name | TEXT | `Wanda` | |
| last_name | TEXT | `Jones` | |
| phone | TEXT | `828-507-1159` | |
| mobile_phone | TEXT | | |
| email | TEXT | | |
| website | TEXT | | |
| photo_url | TEXT | | |
| agent_type | TEXT | | |
| member_type | TEXT | | Navica member type |
| member_status | TEXT | | Active/Inactive |
| office_name | TEXT | `WC Properties` | |
| member_key | TEXT | | Navica member key |
| member_mls_id | TEXT | | |
| office_key | TEXT | | |
| address/city/state/zip | TEXT | | Office address |
| modification_timestamp | TEXT | | |
| created_at / updated_at | TEXT | | |

#### `open_houses`
Open house events linked to listings.

| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | Auto-increment |
| open_house_key | TEXT UNIQUE | MLS unique key |
| listing_key | TEXT | Links to listings.listing_key |
| listing_id | TEXT | Links to listings.mls_number |
| date | TEXT | Event date |
| start_time / end_time | TEXT | Time window |
| type | TEXT | Open house type |
| remarks | TEXT | |
| status | TEXT | |

#### `property_changes`
Tracks price drops, status changes, etc.

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| property_id | TEXT | Links to listings |
| property_address | TEXT | Denormalized |
| change_type | TEXT | 'price', 'status', etc. |
| old_value / new_value | TEXT | |
| change_amount | REAL | Dollar/numeric change |
| change_percent | REAL | Percentage change |
| detected_at | TEXT | When change was detected |
| notification_sent | INTEGER | Alert sent flag |
| notified_leads | TEXT | Which leads were notified |

#### `property_monitors`
Per-property monitoring configuration.

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| property_id | TEXT UNIQUE | Links to listings |
| monitor_price/status/dom/photos/views | INTEGER | What to watch (booleans) |
| last_price/status/dom/photo_count/views | varies | Last known values |
| check_frequency | TEXT | 'hourly', 'daily', 'weekly' |
| alert_on_price_drop | INTEGER | |
| price_drop_threshold | REAL | e.g., 0.05 = 5% |

#### `idx_property_cache`
Cache for IDX website property lookups.

| Field | Type | Notes |
|-------|------|-------|
| mls_number | TEXT PK | |
| address / city | TEXT | |
| price | REAL | |
| status | TEXT | |
| photo_url | TEXT | |
| last_updated | TEXT | |

---

### 2. Contact/Lead Data (CRM)

#### `leads` (main contacts table)
All buyer/seller contacts with scoring.

| Field | Type | Sample | Notes |
|-------|------|--------|-------|
| id | TEXT PK | `con_abc123` | |
| external_id | TEXT | `12345` | FUB person ID |
| external_source | TEXT | `fub` | Source CRM |
| fub_id | TEXT | | Follow Up Boss ID |
| first_name / last_name | TEXT | `John` / `Smith` | |
| email / phone | TEXT | | |
| stage | TEXT | `lead` | CRM stage |
| type | TEXT | `buyer` | buyer/seller |
| source | TEXT | `IDX Website` | Lead source |
| heat_score | INTEGER | `72` | IDX activity score |
| value_score | INTEGER | `85` | Revenue opportunity |
| relationship_score | INTEGER | `45` | Communication frequency |
| priority_score | INTEGER | `67` | Blended priority |
| score_trend | TEXT | `warming` | |
| heat_score_7d_avg | REAL | | 7-day average |
| min_price / max_price | INTEGER | | Price range |
| min_beds / min_baths / min_sqft / min_acreage | varies | | Minimum requirements |
| preferred_cities | TEXT | | JSON array |
| preferred_features | TEXT | | JSON array |
| deal_breakers | TEXT | | JSON array |
| requirements_confidence | REAL | | How confident in requirements |
| website_visits | INTEGER | `12` | IDX site visits |
| properties_viewed | INTEGER | `45` | Properties viewed |
| properties_favorited | INTEGER | `3` | Properties saved |
| calls_inbound / calls_outbound | INTEGER | | Call counts |
| texts_total | INTEGER | | Text count |
| emails_received / emails_sent | INTEGER | | Email counts |
| properties_shared | INTEGER | | Shares count |
| total_communications / total_events | INTEGER | | Totals |
| intent_repeat_views / intent_high_favorites / intent_activity_burst / intent_sharing / intent_signal_count | INTEGER | | Intent signals |
| assigned_agent | TEXT | | Assigned agent name |
| assigned_user_id / assigned_user_name | varies | | FUB user assignment |
| assigned_at / reassigned_at | TEXT | | |
| contact_group | TEXT | `scored` | Grouping |
| next_action / next_action_date | TEXT | | Recommended next step |
| tags / notes / lead_type_tags | TEXT | | |
| last_activity_at | TEXT | | |
| days_since_activity | INTEGER | | |
| created_at / updated_at / last_synced_at | TEXT | | |

#### `contact_events`
IDX website behavioral events (views, favorites, shares).

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| contact_id | TEXT FK | Links to leads |
| event_type | TEXT | 'website_visit', 'property_view', 'property_favorite', 'property_share' |
| occurred_at | TEXT | |
| property_address | TEXT | Denormalized |
| property_price | INTEGER | |
| property_mls | TEXT | |
| fub_event_id | TEXT | Dedup key |

#### `contact_communications`
Calls, texts, emails between agent and contact.

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| contact_id | TEXT FK | Links to leads |
| comm_type | TEXT | 'call', 'text', 'email' |
| direction | TEXT | 'inbound', 'outbound' |
| occurred_at | TEXT | |
| duration_seconds | INTEGER | Calls only |
| fub_user_name | TEXT | Agent who handled |
| status | TEXT | 'completed', 'missed', 'voicemail' |

#### `contact_daily_activity`
Aggregated daily activity per contact.

| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| contact_id | TEXT FK | |
| activity_date | TEXT | YYYY-MM-DD |
| website_visits / properties_viewed / properties_favorited / properties_shared | INTEGER | Daily counts |
| calls_inbound / calls_outbound / texts_inbound / texts_outbound | INTEGER | |
| emails_received / emails_sent | INTEGER | |
| heat/value/relationship/priority_score_snapshot | REAL | End-of-day scores |

#### `contact_scoring_history`
Score snapshots over time for trend analysis.

| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| contact_id | TEXT FK | |
| recorded_at | TEXT | |
| sync_id | INTEGER | |
| heat/value/relationship/priority_score | REAL | Scores at snapshot |
| website_visits / properties_viewed / calls_* / texts_total | INTEGER | Activity at snapshot |
| heat_delta | REAL | Change since last |
| trend_direction | TEXT | 'warming', 'cooling', 'stable' |

#### `lead_activities`
Raw activity events for leads.

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| lead_id | TEXT FK | |
| activity_type | TEXT | |
| activity_source | TEXT | |
| activity_data | TEXT | JSON |
| property_id | TEXT | |
| occurred_at | TEXT | |

#### `contact_actions`
Agent to-do items per contact.

| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK | |
| contact_id | TEXT FK | |
| action_type | TEXT | 'call', 'email', 'text', 'meeting', 'follow_up', 'showing', 'note' |
| description | TEXT | |
| due_date | TEXT | |
| priority | INTEGER | 1 (highest) to 5 |
| completed_at / completed_by | TEXT | |

#### `contact_workflow`
Buyer pipeline stage tracking.

| Field | Type | Notes |
|-------|------|-------|
| contact_id | TEXT UNIQUE | |
| current_stage | TEXT | e.g., 'new_lead' |
| stage_history | TEXT | JSON array of transitions |
| workflow_status | TEXT | 'active', 'paused', 'completed', 'lost' |
| requirements_confidence | REAL | |
| auto_stage_enabled | INTEGER | Allow auto transitions |

#### `contact_requirements`
Consolidated buyer requirements with confidence tracking per field.

| Field | Type | Notes |
|-------|------|-------|
| contact_id | TEXT UNIQUE | |
| price_min / price_max | INTEGER | With `_source` and `_confidence` for each |
| beds_min / baths_min / sqft_min / acreage_min | varies | With source and confidence |
| counties / cities | TEXT | JSON arrays, with source and confidence |
| property_types | TEXT | JSON array |
| must_have_features / nice_to_have_features / deal_breakers | TEXT | JSON arrays |
| views_required / water_features | TEXT | JSON arrays |
| urgency | TEXT | 'asap', '1-3_months', etc. |
| financing_status | TEXT | 'pre_approved', 'cash', etc. |
| overall_confidence / data_completeness | REAL | |

#### `requirements_changes`
Audit trail for requirement changes.

| Field | Type | Notes |
|-------|------|-------|
| contact_id | TEXT FK | |
| field_name | TEXT | Which field changed |
| old_value / new_value | TEXT | |
| old_source / new_source | TEXT | |
| change_reason | TEXT | 'consolidation', 'override', etc. |
| changed_by | TEXT | 'system' or agent name |

#### `assignment_history`
Lead reassignment audit trail.

| Field | Type | Notes |
|-------|------|-------|
| contact_id | TEXT FK | |
| assigned_from/to_user_id | INTEGER | |
| assigned_from/to_user_name | TEXT | |
| source | TEXT | 'sync', 'manual', 'round_robin', 'transfer' |

---

### 3. Buyer Workflow

#### `intake_forms`
Buyer requirement intake forms (one buyer can have multiple searches).

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| lead_id | TEXT FK | Links to leads |
| form_name | TEXT | e.g., "John's Primary Home Search" |
| need_type | TEXT | 'primary_home', 'str', 'ltr', 'investment', 'land', etc. |
| status | TEXT | 'active', 'paused', 'completed', 'cancelled' |
| source | TEXT | 'idx_activity', 'phone_call', 'email', etc. |
| counties / cities / zip_codes / subdivisions | TEXT | JSON arrays |
| property_types | TEXT | JSON array |
| min/max_price, beds, baths, sqft, acreage, year_built | varies | Criteria ranges |
| views_required / water_features | TEXT | JSON arrays |
| style_preferences / must_have_features / nice_to_have_features / deal_breakers | TEXT | JSON arrays |
| target_cap_rate / target_rental_income | varies | Investment-specific |
| urgency | TEXT | Timeline |
| financing_status / pre_approval_amount | varies | |
| confidence_score | INTEGER | 1-10 |

#### `pursuits`
Active buyer deal pursuits.

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| buyer_id | TEXT | Links to leads |
| name | TEXT | |
| status | TEXT | 'active' |
| intake_form_id | TEXT | |
| fub_deal_id | TEXT | FUB deal link |

#### `pursuit_properties`
Properties associated with a pursuit.

| Field | Type | Notes |
|-------|------|-------|
| pursuit_id | TEXT FK | |
| property_id | TEXT | Links to listings |
| status | TEXT | 'suggested', etc. |
| source | TEXT | How it was added |

#### `showings`
Showing appointments.

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| lead_id | TEXT FK | |
| property_id | TEXT | |
| showing_date | TEXT | |
| status | TEXT | 'scheduled' |

#### `showing_properties`
Individual stops within a showing tour.

| Field | Type | Notes |
|-------|------|-------|
| showing_id | TEXT FK | |
| property_id | TEXT FK | |
| stop_order | INTEGER | Order in tour |
| scheduled_time | TEXT | |
| time_at_property | INTEGER | Minutes to spend |
| showing_type | TEXT | 'exterior_only', 'interior', etc. |
| access_info | TEXT | Lockbox code, etc. |
| client_interest_level | INTEGER | 1-5 |
| client_feedback | TEXT | |
| status | TEXT | 'pending', 'confirmed', 'shown', etc. |

---

### 4. Property Packages (Client Presentations)

#### `property_packages`
Client property collections/presentations.

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| lead_id | TEXT FK | |
| intake_form_id | TEXT FK | |
| name | TEXT | Package name |
| status | TEXT | 'draft', etc. |
| share_token | TEXT UNIQUE | Public sharing token |
| share_url | TEXT | |
| view_count | INTEGER | |
| collection_type | TEXT | 'agent_package' |
| is_public | INTEGER | |
| slug | TEXT | |
| criteria_json | TEXT | |
| auto_refresh | INTEGER | |

#### `package_properties`
Properties within a package.

| Field | Type | Notes |
|-------|------|-------|
| package_id | TEXT FK | |
| listing_id | TEXT FK | |
| display_order | INTEGER | |
| agent_notes / client_notes | TEXT | |
| highlight_features | TEXT | |
| client_favorited | INTEGER | |
| client_rating | INTEGER | |
| showing_requested | INTEGER | |

---

### 5. Public Website (User Accounts)

#### `users`
Registered website users (buyers browsing the public site).

| Field | Type | Notes |
|-------|------|-------|
| id | TEXT PK | |
| email | TEXT UNIQUE | |
| name | TEXT | |
| password_hash | TEXT | |
| google_id | TEXT UNIQUE | OAuth |
| lead_id | TEXT | Links to leads table |

#### `user_favorites`
Buyer's saved/favorited listings on public site.

| Field | Type | Notes |
|-------|------|-------|
| user_id | TEXT FK | |
| listing_id | TEXT | |
| UNIQUE(user_id, listing_id) | | |

#### `saved_searches`
Buyer's saved search criteria.

| Field | Type | Notes |
|-------|------|-------|
| user_id | TEXT FK | |
| name | TEXT | |
| filters_json | TEXT | Saved filter criteria |
| alert_frequency | TEXT | 'daily' |

#### `auth_accounts` / `auth_sessions`
OAuth accounts and active sessions for website auth.

#### `buyer_activity`
Tracks registered user actions on the public site.

| Field | Type | Notes |
|-------|------|-------|
| user_id | TEXT FK | |
| lead_id | TEXT | |
| activity_type | TEXT | |
| entity_type / entity_id / entity_name | TEXT | What was interacted with |
| agent_notified | INTEGER | |

---

### 6. Market Data & Analytics

#### `tmo_market_data`
TMO (The Market Online) report data.

| Field | Type | Notes |
|-------|------|-------|
| region | TEXT | Market region |
| property_type | TEXT | |
| report_date | TEXT | |
| price_range | TEXT | e.g., "$200K-$300K" |
| price_range_min / max | INTEGER | |
| active_listings / pending_listings | INTEGER | |
| pending_ratio / months_inventory | REAL | |
| avg_original/final_list_price / avg_sale_price | REAL | |
| list_to_sale_ratio | REAL | |
| avg_dom_sold / avg_dom_active | INTEGER | |

#### `market_snapshots`
Daily market statistics by county.

| Field | Type | Notes |
|-------|------|-------|
| snapshot_date | TEXT | YYYY-MM-DD |
| county | TEXT | NULL = all counties |
| total_active / new_listings / pending_count / sold_count / price_reduced_count | INTEGER | |
| avg_price / median_price | INTEGER | |
| avg_dom | REAL | |

---

### 7. System & Sync

#### `scoring_runs`
Log of lead scoring executions.

#### `sync_log`
Audit trail of all sync operations.

| Field | Type | Notes |
|-------|------|-------|
| sync_type | TEXT | |
| source | TEXT | |
| direction | TEXT | |
| records_processed / created / updated / failed | INTEGER | |
| status | TEXT | |

#### `automation_log`
Log of fired automation rules (alerts, tasks).

#### `alert_log`
Log of sent alerts (new listings, price drops, summaries).

#### `fub_users`
Follow Up Boss user/agent records.

#### `fub_write_log`
Audit trail of writes to FUB API.

#### `power_hour_sessions` / `power_hour_dispositions`
Call session tracking for power hour calling blocks.

#### `system_settings`
Key-value configuration store.

| Field | Type | Notes |
|-------|------|-------|
| key | TEXT PK | Setting name |
| value | TEXT | Setting value |
| value_type | TEXT | 'string', 'integer', 'json', etc. |
| category | TEXT | Grouping |

---

## IDX/BBO Separation Plan

### Current State
- **Single `listings` table** contains both IDX and BBO data
- `idx_opt_in` flag distinguishes: 53,899 IDX (99%) vs 587 BBO-only (1%)
- BBO-only fields stored on all rows: `private_remarks`, `showing_instructions`, `buyer_agent_*`
- Even IDX-eligible listings have `private_remarks` (44,403 of 53,899) and `showing_instructions` (53,890)

### Public API Audit Result: PASS
The public API is correctly protected:
1. Every query includes `WHERE idx_opt_in = 1`
2. Field whitelists (`PUBLIC_LISTING_FIELDS`, `PUBLIC_LIST_FIELDS`, `MAP_MARKER_FIELDS`) exclude all BBO-only fields
3. `idx_address_display` is respected (address suppressed when 0, markers omitted from map)
4. No direct database access from the public site (all goes through API)

### Recommendation: Keep Single Table, Enforce at API Layer

Splitting into separate tables introduces significant complexity with minimal benefit:

**Problems with separate tables:**
- Every query that needs both IDX and BBO data (agent dashboard, property packages, showings) requires JOINs or UNION queries
- The sync engine would need to write to two tables, or we'd need a post-sync split process
- Schema changes require updating two tables
- A single listing can switch from IDX to BBO (or vice versa) when the seller changes their opt-in; moving rows between tables on every sync is fragile
- 82% of IDX listings already have `private_remarks` data; these are the same records, just with different display rules

**Current approach is correct because:**
- IDX vs BBO is a **display permission**, not a data source distinction
- The same listing from the same MLS can have both IDX and BBO fields
- The `idx_opt_in` flag + API field whitelists is exactly how MLS data vendors (MLS Grid, Navica) intend this to work
- Adding Mountain Lakes and Canopy data just means more rows in the same table with the same pattern

**What to reinforce as we add MLSs:**
1. Public API: always filter `idx_opt_in = 1` (already done)
2. Public API: always use field whitelists, never `SELECT *` (already done)
3. Agent dashboard: can show all data (BBO fields are for agent eyes only)
4. Property packages shared with clients: use IDX field whitelist (verify this)
5. Add integration tests that assert BBO fields never appear in public API responses
