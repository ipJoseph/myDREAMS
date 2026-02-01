# Property Database Quality Tracking

## Goal
Make the property database a reliable **single source of truth** with automated data feeds wherever possible.

---

## Baseline Audit (2026-01-31)

### Listings Summary

| Metric | Count | Percentage | Notes |
|--------|-------|------------|-------|
| **Total Listings** | 10,881 | 100% | All records |
| **Has MLS Number** | 3,574 | 32.8% | Critical identifier |
| **Has Photos (JSON)** | 81 | 0.7% | Full photo arrays |
| **Has Primary Photo** | 1,222 | 11.2% | At least one photo URL |
| **Has Coordinates** | 8,924 | 82.0% | Lat/lng populated |
| **Has Agent Info** | 10,684 | 98.2% | Listing agent name |
| **Has Parcel Link** | 9,400 | 86.4% | Foreign key to parcels |

### Listings by Status

| Status | Count | Notes |
|--------|-------|-------|
| ACTIVE | 10,122 | Current listings |
| PENDING | 529 | Under contract |
| SOLD | 0 | Historical data gap |

### Listings by Source

| Source | Total | Has MLS# | Has Photos | Has Agent |
|--------|-------|----------|------------|-----------|
| **PropStream** | 9,319 | 2,012 (21.6%) | 81 (0.9%) | 9,128 (98.0%) |
| **CSMLS** | 1,562 | 1,562 (100%) | 0 (0%) | 1,556 (99.6%) |

**Key Finding**: PropStream provides bulk data but incomplete MLS numbers. CSMLS has 100% MLS coverage but no photos in current import.

### Photo Coverage

| Photo Source | Count | Notes |
|--------------|-------|-------|
| MLS (verified) | 1,062 | From MLS export ZIP files |
| Redfin (scraped) | 106 | Via photo enrichment script |
| **No source** | 9,713 | 89% missing photos |

| Review Status | Count |
|---------------|-------|
| Not reviewed | 10,278 |
| Verified | 601 |
| Pending review | 2 |

### Parcels Summary

| Metric | Count | Percentage | Notes |
|--------|-------|------------|-------|
| **Total Parcels** | 9,717 | 100% | |
| **Has Coordinates** | 9,296 | 95.7% | NC OneMap integration |
| **Has Flood Zone** | 9,296 | 95.7% | FEMA data |
| **Has Elevation** | 9,288 | 95.6% | USGS data |
| **Has APN** | 9,717 | 100% | All records |
| **Has Owner** | 9,717 | 100% | PropStream baseline |
| **Spatially Enriched** | 9,296 | 95.7% | Full enrichment |

**Spatial Enrichment Window**: 2026-01-30 (single day batch)

### Coverage by County (Parcels)

| County | Parcels | % of Total |
|--------|---------|------------|
| Buncombe | 2,591 | 26.7% |
| Jackson | 1,332 | 13.7% |
| Henderson | 1,244 | 12.8% |
| Haywood | 1,038 | 10.7% |
| Macon | 938 | 9.7% |
| Transylvania | 622 | 6.4% |
| Cherokee | 586 | 6.0% |
| Clay | 519 | 5.3% |
| Madison | 404 | 4.2% |
| Swain | 336 | 3.5% |
| Graham | 107 | 1.1% |

### Top Cities - MLS & Photo Coverage (Active Listings)

| City | Listings | Has MLS# | % MLS | Has Photos | % Photos |
|------|----------|----------|-------|------------|----------|
| Asheville | 1,429 | 617 | 43.2% | 17 | 1.2% |
| Hendersonville | 905 | 325 | 35.9% | 4 | 0.4% |
| Franklin | 682 | 326 | 47.8% | 1 | 0.1% |
| Waynesville | 548 | 184 | 33.6% | 4 | 0.7% |
| Hayesville | 415 | 15 | 3.6% | 7 | 1.7% |
| Sylva | 413 | 171 | 41.4% | 0 | 0.0% |
| Murphy | 402 | 17 | 4.2% | 10 | 2.5% |
| Bryson City | 354 | 218 | 61.6% | 0 | 0.0% |
| Brevard | 303 | 117 | 38.6% | 3 | 1.0% |
| Highlands | 247 | 17 | 6.9% | 2 | 0.8% |

---

## Data Source Analysis

### API Availability

| Source | API Available? | Access Method | Automation Potential |
|--------|---------------|---------------|---------------------|
| **Canopy MLS** | YES | MLS Grid (RESO Web API) | HIGH - Contact data@canopyrealtors.com |
| **Carolina Smokies MLS** | UNCLEAR | Need to verify if on MLS Grid | MEDIUM - May need manual exports |
| **PropStream** | NO | Excel export only | NONE - Manual baseline loads only |
| **NC OneMap** | YES | ArcGIS REST API | HIGH - Already integrated |
| **Aggregators** | Scraping only | Rate-limited, blocking risk | LOW - Supplemental photos only |

### Current Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTOMATED (Working)                           │
├─────────────────────────────────────────────────────────────────┤
│  NC OneMap API ────────► Parcels + Spatial                      │
│  (enrich_spatial.py)    - Coordinates, flood, elevation         │
│                         - 95.7% coverage achieved               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    SEMI-AUTOMATED (Working)                      │
├─────────────────────────────────────────────────────────────────┤
│  Carolina Smokies ─────► Listings (CSV export)                  │
│  MLS Export              - 1,562 listings with MLS#             │
│  (import_mls_export.py)  - Agent info, property details         │
│                                                                  │
│  Photo Enrichment ─────► Listings                               │
│  (enrich_photos_verified.py) - Redfin scraping                  │
│                              - 106 photos enriched              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    MANUAL (Baseline)                             │
├─────────────────────────────────────────────────────────────────┤
│  PropStream Export ────► Parcels + Listings baseline            │
│  (import_propstream.py)  - 9,319 listings, 9,717 parcels        │
│                          - 11-county bulk load                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    PLANNED (Not Yet Built)                       │
├─────────────────────────────────────────────────────────────────┤
│  Canopy MLS API ──────► Listings (active, pending, sold)        │
│  (via MLS Grid)         - Full MLS data with photos             │
│                         - Real-time updates                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Gap Analysis

### Critical Gaps

| Gap | Impact | Resolution Path |
|-----|--------|-----------------|
| **MLS# coverage at 32.8%** | Can't dedupe or track listings reliably | MLS Grid API integration |
| **Photo coverage at 11.2%** | Poor client presentation | MLS Grid photos + enhanced scraping |
| **No SOLD history** | Can't do CMAs or market analysis | MLS Grid historical data |
| **CSMLS photos not importing** | MLS photos stored but not linked | Fix import_mls_export.py |

### Data Quality Issues

1. **Duplicate listings** - Same property from PropStream + MLS without MLS# to dedupe
2. **Stale PropStream data** - No automated refresh, unknown age
3. **Photo verification backlog** - 10,278 listings never reviewed
4. **Incomplete coordinates** - 18% of listings missing lat/lng

---

## Experiment Tracking

| # | Date | Source | Action | Records | MLS# | Photos | Coords | Verdict |
|---|------|--------|--------|---------|------|--------|--------|---------|
| 0 | 2026-01-31 | Current | Baseline audit | 10,881 listings | 32.8% | 11.2% | 82.0% | Starting point |

---

## Implementation Plan

### Phase 1: Baseline Metrics (COMPLETE)
- [x] Run data quality audit
- [x] Document current coverage
- [x] Create tracking template

### Phase 2: Investigate MLS Grid Access (This Week)
- [ ] Contact Canopy MLS (data@canopyrealtors.com) about API access
- [ ] Determine licensing requirements and costs
- [ ] Check if Carolina Smokies MLS is also on MLS Grid
- [ ] Get sample API response to understand data structure

### Phase 3: Build MLS Grid Integration (If Approved)
- [ ] Create `import_mlsgrid.py` script
- [ ] Map MLS Grid fields to our schema
- [ ] Implement incremental sync (only changed records)
- [ ] Set up scheduled job (cron or systemd timer)

### Phase 4: Optimize Existing Pipelines
- [ ] Fix CSMLS photo import (photos exist but not linked)
- [ ] Enhance photo enrichment reliability
- [ ] Set up monitoring dashboard for data freshness

### Phase 5: Deprecate Manual Processes
- [ ] Phase out PropStream as primary source
- [ ] Document new workflow

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-31 | Prioritize MLS Grid API | Only viable path to automation for MLS data |
| 2026-01-31 | Keep PropStream for baseline only | No API, can't automate |
| 2026-01-31 | NC OneMap is working well | 95.7% coverage, keep and maintain |

---

## Open Questions

1. **MLS Grid licensing cost** - What does Canopy charge for API access?
2. **Carolina Smokies on MLS Grid?** - Need to verify
3. **Photo source strategy** - MLS feed includes photos, or still need scraping?
4. **Historical data** - Can we get SOLD listings from MLS Grid?

---

## Progress Log

| Date | What We Did | Outcome |
|------|-------------|---------|
| 2026-01-31 | Baseline data quality audit | 32.8% MLS#, 11.2% photos, 82% coords |
| 2026-01-31 | Documented data sources | Confirmed MLS Grid is best path forward |
