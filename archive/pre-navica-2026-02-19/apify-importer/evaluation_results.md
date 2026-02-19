# Apify Scraper Evaluation Results

**Status:** Not yet started
**Test Set:** 50 properties (export with `python evaluate_scrapers.py --export-test-set`)

---

## Evaluation Checklist

- [ ] Create Apify free account at https://apify.com
- [ ] Get API token from https://console.apify.com/account#/integrations
- [ ] Set token: `export APIFY_TOKEN='your_token'`
- [ ] Export test properties
- [ ] Run Redfin scrapers (3 total)
- [ ] Run Zillow scrapers (2 total)
- [ ] Analyze results and pick winner

---

## Redfin Scrapers

### 1. tri_angle/redfin-search

**URL:** https://apify.com/tri_angle/redfin-search
**Pricing:** $1/1,000 results
**Status:** [ ] Not tested

| Metric | Result |
|--------|--------|
| Results returned | - |
| Time (seconds) | - |
| Must-have fields | -/9 |
| Nice-to-have fields | -/10 |
| Match rate | - |
| Data quality issues | - |

**Field Mapping:**
```
address → ?
city → ?
price → ?
status → ?
beds → ?
baths → ?
sqft → ?
photo_url → ?
```

**Notes:**
-

---

### 2. epctex/redfin-scraper

**URL:** https://apify.com/epctex/redfin-scraper
**Pricing:** ~$0.06-0.09 CU/100 properties
**Status:** [ ] Not tested

| Metric | Result |
|--------|--------|
| Results returned | - |
| Time (seconds) | - |
| Must-have fields | -/9 |
| Nice-to-have fields | -/10 |
| Match rate | - |
| Data quality issues | - |

**Notes:**
- Includes schools and walkscore data
-

---

### 3. mantisus/redfin-fast-scraper

**URL:** https://apify.com/mantisus/redfin-fast-scraper
**Pricing:** Pay-per-result
**Status:** [ ] Not tested

| Metric | Result |
|--------|--------|
| Results returned | - |
| Time (seconds) | - |
| Must-have fields | -/9 |
| Nice-to-have fields | -/10 |
| Match rate | - |
| Data quality issues | - |

**Notes:**
- Claims built-in deduplication
- Claims "very fast"

---

## Zillow Scrapers

### 1. maxcopell/zillow-scraper

**URL:** https://apify.com/maxcopell/zillow-scraper
**Pricing:** $2/1,000 results (2K free)
**Status:** [ ] Not tested

| Metric | Result |
|--------|--------|
| Results returned | - |
| Time (seconds) | - |
| Must-have fields | -/9 |
| Nice-to-have fields | -/10 |
| Match rate | - |
| Data quality issues | - |

**Field Mapping:**
```
address → ?
zpid → ?
price → ?
zestimate → ?
status → ?
beds → ?
baths → ?
sqft → ?
```

**Notes:**
- Most popular Zillow scraper
- Requires residential proxies (included in Apify)

---

### 2. maxcopell/zillow-detail-scraper

**URL:** https://apify.com/maxcopell/zillow-detail-scraper
**Pricing:** Pay-per-result
**Status:** [ ] Not tested

| Metric | Result |
|--------|--------|
| Results returned | - |
| Time (seconds) | - |
| Must-have fields | -/9 |
| Nice-to-have fields | -/10 |
| Match rate | - |
| Data quality issues | - |

**Notes:**
- Requires zpids (need to get from search scraper first)
- Use for full property details if search scraper lacks fields

---

## Required Fields Checklist

### Must Have

| Field | Redfin tri_angle | Redfin epctex | Redfin mantisus | Zillow maxcopell |
|-------|------------------|---------------|-----------------|------------------|
| address | | | | |
| city | | | | |
| state | | | | |
| zip | | | | |
| price | | | | |
| status | | | | |
| beds | | | | |
| baths | | | | |
| sqft | | | | |
| photo_url | | | | |

### Nice to Have

| Field | Redfin tri_angle | Redfin epctex | Redfin mantisus | Zillow maxcopell |
|-------|------------------|---------------|-----------------|------------------|
| days_on_market | | | | |
| views/favorites | | | | |
| listing_agent_name | | | | |
| listing_agent_phone | | | | |
| price_history | | | | |
| all_photos | | | | |
| mls_number | | | | |
| acreage | | | | |
| year_built | | | | |

---

## Cost Analysis

### Evaluation Phase

| Scraper | Properties | Est. Cost |
|---------|-----------|-----------|
| redfin_triangle (50) | 50 | $0.05 |
| redfin_epctex (50) | 50 | $0.05 |
| redfin_mantisus (50) | 50 | $0.05 |
| zillow_maxcopell (50) | 50 | $0.10 |
| **Total evaluation** | 200 | **~$0.25** |

Free tier ($5) easily covers all evaluation runs.

### Full Update (After Evaluation)

| Scenario | Properties | Est. Cost |
|----------|-----------|-----------|
| Redfin full WNC | 9,000 | ~$9 |
| Zillow full WNC | 9,000 | ~$18 |
| **Total one-time** | - | **~$27** |

---

## Data Quality Spot Checks

After running evaluations, manually verify 10 properties:

| Property Address | Field | Scraper Value | Website Value | Match? |
|-----------------|-------|---------------|---------------|--------|
| | price | | | |
| | status | | | |
| | beds | | | |
| | baths | | | |
| | sqft | | | |

---

## Decision Matrix

| Criteria | Weight | Redfin Winner | Zillow Winner |
|----------|--------|---------------|---------------|
| Field completeness | 40% | | |
| Data accuracy | 30% | | |
| Speed | 15% | | |
| Cost efficiency | 15% | | |
| **Overall Winner** | | **?** | **?** |

---

## Final Recommendation

**Redfin Scraper:**
- Reason:

**Zillow Scraper:**
- Reason:

**Estimated Monthly Cost:** $
