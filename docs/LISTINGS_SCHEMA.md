# Listings Table Schema

*Data dictionary for the listings table in the DREAMS database*

Last updated: January 30, 2026

---

## Overview

The `listings` table stores transactional MLS/listing data. This data changes with each sale or listing event. A single parcel can have multiple listings over time as the property is bought and sold.

**Primary Key:** `id` (Generated hash)

**Foreign Key:** `parcel_id` → `parcels.id`

---

## Fields by Category

| Field | Type | Source |
|-------|------|--------|
| **Identity** | | |
| id | TEXT | Generated (hash of APN+status+price) |
| parcel_id | TEXT | FK to parcels table |
| mls_source | TEXT | PropStream / MLS feed |
| mls_number | TEXT | MLS feed (NULL from PropStream) |
| **Listing Details** | | |
| status | TEXT | PropStream (ACTIVE, PENDING, SOLD, etc.) |
| list_price | INTEGER | PropStream |
| list_date | TEXT | PropStream |
| sold_price | INTEGER | MLS feed |
| sold_date | TEXT | MLS feed |
| days_on_market | INTEGER | Calculated / MLS feed |
| **Property Specs** | | |
| beds | INTEGER | PropStream |
| baths | REAL | PropStream |
| sqft | INTEGER | PropStream |
| year_built | INTEGER | PropStream |
| property_type | TEXT | PropStream |
| style | TEXT | MLS feed |
| **Features** | | |
| views | TEXT | MLS feed (JSON) |
| amenities | TEXT | MLS feed (JSON) |
| heating | TEXT | MLS feed |
| cooling | TEXT | MLS feed |
| garage | TEXT | MLS feed |
| hoa_fee | INTEGER | MLS feed |
| **Photos** | | |
| photos | TEXT | Redfin scraper (JSON array) |
| primary_photo | TEXT | Redfin scraper |
| photo_source | TEXT | System (redfin, zillow, mls) |
| photo_confidence | REAL | Calculated (0-100) |
| photo_verified_at | TEXT | System timestamp |
| photo_verified_by | TEXT | System (auto / agent name) |
| photo_review_status | TEXT | System (verified, pending_review, rejected) |
| photo_count | INTEGER | Calculated |
| virtual_tour_url | TEXT | MLS feed |
| **External Links** | | |
| mls_url | TEXT | MLS feed |
| idx_url | TEXT | IDX site |
| redfin_url | TEXT | Redfin scraper |
| redfin_id | TEXT | Redfin scraper |
| zillow_url | TEXT | Zillow scraper |
| zillow_id | TEXT | Zillow scraper |
| **Listing Agent** | | |
| listing_agent_id | TEXT | MLS feed |
| listing_agent_name | TEXT | PropStream / MLS feed |
| listing_agent_phone | TEXT | PropStream / MLS feed |
| listing_agent_email | TEXT | PropStream / MLS feed |
| listing_office_id | TEXT | MLS feed |
| listing_office_name | TEXT | PropStream / MLS feed |
| **Client Work** | | |
| added_for | TEXT | Manual (client name for portfolio) |
| added_by | TEXT | Manual (agent who added) |
| notes | TEXT | Manual |
| **Denormalized Address** | | |
| address | TEXT | Copied from parcels |
| city | TEXT | Copied from parcels |
| state | TEXT | Copied from parcels |
| zip | TEXT | Copied from parcels |
| county | TEXT | Copied from parcels |
| latitude | REAL | Copied from parcels |
| longitude | REAL | Copied from parcels |
| acreage | REAL | Copied from parcels |
| **Flags** | | |
| is_residential | INTEGER | System (1=residential, 0=commercial/industrial) |
| **Meta** | | |
| source | TEXT | System (propstream_11county, etc.) |
| captured_at | TEXT | System timestamp |
| updated_at | TEXT | System timestamp |

---

## Data Sources

| Source | Fields | Notes |
|--------|--------|-------|
| **PropStream** | status, list_price, list_date, beds, baths, sqft, year_built, property_type, agent info | Baseline from 11-county Excel export |
| **MLS Feed** | mls_number, sold_price, sold_date, style, features, amenities | Direct MLS data (when available) |
| **Redfin Scraper** | photos, primary_photo, redfin_url, redfin_id | Verified photo enrichment |
| **Zillow Scraper** | zillow_url, zillow_id | Backup photo source |
| **Parcels Table** | address, city, state, zip, county, latitude, longitude, acreage | Denormalized for fast queries |
| **Manual** | added_for, added_by, notes | Agent input for client portfolios |

---

## Relationships

```
parcels (1) ──────► (N) listings
                         │
                         ▼
              contact_listings (N:M)
                         │
                         ▼
                    leads (N)
```

---

## Photo Verification

Photos are verified using multi-factor matching before being accepted:

| Factor | Weight | Threshold |
|--------|--------|-----------|
| Address match | 30% | Fuzzy similarity |
| Price match | 25% | Within 5% |
| Beds/Baths match | 25% | Exact match |
| Coordinates | 20% | < 0.1 mile |

**Confidence Thresholds:**
- ≥ 90%: Auto-accept
- 70-89%: Accept with note
- 50-69%: Queue for manual review
- < 50%: Reject

---

## Indexes

- `idx_listings_parcel` - Join to parcels
- `idx_listings_status` - Status filtering
- `idx_listings_mls` - MLS source + number lookup
- `idx_listings_price` - Price range queries
- `idx_listings_mls_unique` (UNIQUE) - Dedupe by MLS source + number
