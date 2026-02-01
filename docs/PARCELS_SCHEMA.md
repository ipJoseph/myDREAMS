# Parcels Table Schema

*Data dictionary for the parcels table in the DREAMS database*

Last updated: January 30, 2026

---

## Overview

The `parcels` table stores immutable land/parcel data. This data changes rarely (only with subdivision or property line changes). Each parcel can have multiple listings over time as the property is bought and sold.

**Primary Key:** `id` (MD5 hash of APN + County)

---

## Fields by Category

| Field | Type | Source |
|-------|------|--------|
| **Identity** | | |
| id | TEXT | Generated (MD5 hash of APN+County) |
| apn | TEXT | PropStream |
| alt_apn | TEXT | PropStream |
| county | TEXT | PropStream |
| state | TEXT | PropStream |
| **Location** | | |
| address | TEXT | PropStream |
| address_raw | TEXT | PropStream |
| city | TEXT | PropStream |
| zip | TEXT | PropStream |
| latitude | REAL | NC OneMap API |
| longitude | REAL | NC OneMap API |
| **Physical** | | |
| acreage | REAL | PropStream |
| legal_description | TEXT | PropStream |
| land_use | TEXT | PropStream |
| **Owner** | | |
| owner_name | TEXT | PropStream |
| owner_name_2 | TEXT | PropStream |
| owner_occupied | TEXT | PropStream |
| owner_phone | TEXT | PropStream |
| owner_email | TEXT | PropStream |
| **Mailing** | | |
| mailing_address | TEXT | PropStream |
| mailing_city | TEXT | PropStream |
| mailing_state | TEXT | PropStream |
| mailing_zip | TEXT | PropStream |
| **Tax/Value** | | |
| assessed_value | INTEGER | PropStream |
| assessed_land_value | INTEGER | PropStream |
| assessed_building_value | INTEGER | PropStream |
| tax_annual | INTEGER | PropStream |
| **Sales History** | | |
| last_sale_date | TEXT | PropStream |
| last_sale_amount | INTEGER | PropStream |
| **Spatial** | | |
| flood_zone | TEXT | NC OneMap (FEMA) |
| flood_zone_subtype | TEXT | NC OneMap (FEMA) |
| flood_factor | INTEGER | Calculated (1-10 risk) |
| flood_sfha | INTEGER | NC OneMap (FEMA) |
| elevation_feet | INTEGER | USGS National Map |
| slope_percent | REAL | USGS National Map |
| aspect | TEXT | USGS National Map |
| view_potential | INTEGER | Calculated (elevation-based) |
| wildfire_risk | TEXT | NC OneMap |
| wildfire_score | INTEGER | Calculated (1-10 risk) |
| spatial_enriched_at | TEXT | System timestamp |
| **Meta** | | |
| created_at | TEXT | System timestamp |
| updated_at | TEXT | System timestamp |

---

## Data Sources

| Source | Fields | Notes |
|--------|--------|-------|
| **PropStream** | Identity, location, physical, owner, mailing, tax/value, sales | Baseline data from 11-county Excel export |
| **NC OneMap API** | latitude, longitude | Parcel centroid coordinates matched by APN |
| **NC OneMap (FEMA)** | flood_zone, flood_zone_subtype, flood_sfha | Federal flood hazard data |
| **USGS National Map** | elevation_feet, slope_percent, aspect | Terrain data |
| **Calculated** | flood_factor, view_potential, wildfire_score | Derived scores (1-10 scale) |

---

## Relationships

```
parcels (1) ──────► (N) listings
   │
   └── One parcel can have many listings over time
       (each sale/listing creates a new listing record)
```

---

## Indexes

- `idx_parcels_apn` - Fast APN lookup
- `idx_parcels_county` - County filtering
- `idx_parcels_city` - City filtering
- `idx_parcels_apn_county` (UNIQUE) - Dedupe by APN+County

---

## Calculated Fields

### View Potential (1-10 scale)

Estimates mountain view quality based on terrain characteristics.

**Base score:** 5 (moderate)

| Factor | Condition | Score Change |
|--------|-----------|--------------|
| **Elevation** | > 4,000 ft | +3 |
| | > 3,000 ft | +2 |
| | > 2,000 ft | +1 |
| | < 1,500 ft | -1 |
| **Aspect** | S, SW, W facing | +2 |
| | SE, NW facing | +1 |
| **Slope** | 10-30% (ideal) | +1 |
| | > 50% (too steep) | -1 |

**Result clamped to 1-10**

*Logic: Higher elevations + southwest-facing slopes (toward the Blue Ridge) = better mountain views in WNC.*

### Flood Factor (1-10 scale)

Risk score derived from FEMA flood zone designation.

| Zone | Description | Score |
|------|-------------|-------|
| X | Minimal risk | 1-2 |
| X500 | 0.2% annual chance | 3-4 |
| A, AE | 1% annual chance (100-yr) | 6-7 |
| AO, AH | Shallow flooding | 7-8 |
| VE, V | Coastal high hazard | 9-10 |

### Wildfire Score (1-10 scale)

Risk score derived from NC wildfire risk assessment.

| Risk Category | Score |
|---------------|-------|
| Low | 1-2 |
| Moderate | 3-4 |
| High | 6-7 |
| Very High | 8-10 |
