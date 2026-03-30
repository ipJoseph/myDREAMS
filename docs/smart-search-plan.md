# Smart Search Bar: Implementation Plan

Status: PLANNED (not started)
Created: 2026-03-30
Priority: Next major public site feature

## The Concept

One search bar, Google-style. Inspired by Cloud Agent Suite's Cloud MLX.
A buyer types `3 bed cabin under 400k in Sylva` and gets exactly what they want.
No dropdowns, no checkboxes, no friction.

Current state: basic filter dropdowns on /listings page with a text search box
that does raw LIKE matching. Typing "3 bed under 400k Sylva" returns garbage
because "under" and "400k" are matched literally against address/remarks fields.

---

## Key Decision: Deterministic Parser, Not LLM

Using regex/pattern matching, not Claude API. Three reasons:

1. **Speed.** Parser runs in <1ms. LLM call adds 500-2000ms. Search bars must feel instant.
2. **Cost.** Every public visitor searching = API calls. At scale that's real money for a bounded problem.
3. **Predictability.** The vocabulary is finite: ~120 cities, ~20 counties, 5 property types, and predictable price/bed/bath/acreage patterns. This isn't open-ended NLP.

If the deterministic parser proves insufficient, add an LLM fallback in Phase 3
as an opt-in "Try AI search?" button (user-initiated, not automatic).

---

## How It Works

```
User types: "3 bed cabin under 400k in Sylva"
                    |
                    v
        +-------------------------+
        |  Query Parser           |
        |  (Python, <1ms)         |
        |                         |
        |  Extracts:              |
        |  min_beds = 3           |
        |  max_price = 400000     |
        |  city = Sylva           |
        |  type = Residential     |
        +-------------------------+
                    |
                    v
        Redirects to /listings?min_beds=3&max_price=400000&city=Sylva&property_type=Residential
                    |
                    v
        Existing ListingFilters + search_listings handles everything
        (zero backend search changes needed)
```

The parser translates natural language into the filter vocabulary that already
exists in ListingFilters. The entire backend search pipeline stays untouched.

---

## Parser Extraction Rules (priority order)

| # | Pattern | Example Input | Extracts |
|---|---------|--------------|----------|
| 1 | MLS number | `4358298` or `CAR4358298` | Direct redirect to listing detail |
| 2 | Address | `117 Jackson Street` | Pass as `q` for LIKE matching |
| 3 | Price range | `under 400k`, `$200k-$500k`, `above 300000` | `min_price` / `max_price` |
| 4 | Bedrooms | `3 bed`, `4 bedroom`, `3br` | `min_beds` |
| 5 | Bathrooms | `2 bath`, `3ba` | `min_baths` |
| 6 | Acreage | `5+ acres`, `over 2 acres` | `min_acreage` |
| 7 | Property type | `cabin`, `land`, `farm`, `duplex` | `property_type` |
| 8 | County | `Haywood County`, `Buncombe` | `county` |
| 9 | City | `Sylva`, `Franklin`, `Asheville` | `city` |
| 10 | Features | `mountain views`, `waterfront`, `garage` | Remainder as `q` for remarks LIKE |

### Price parsing

- `under|below|less than|up to|max` + price -> max_price
- `over|above|more than|min|at least` + price -> min_price
- `$XXXk` or `$X.Xm` or `$XXX,XXX` or `XXXk` or `Xm` -> parse to integer
- `$200k-$400k` or `200k to 400k` -> min_price + max_price

### Property type keyword mapping

- `home|house|residential|cabin|cottage|bungalow` -> Residential
- `land|lot|lots|parcel` -> Land
- `farm|ranch|farmhouse|farmland` -> Farm
- `commercial|office|retail|warehouse` -> Commercial
- `multi-family|duplex|triplex|fourplex|apartment` -> Multi-Family

### Ambiguity resolution ("Franklin" = city or county?)

- "Franklin County" -> county filter
- Plain "Franklin" -> city filter (the common intent in WNC)
- Autocomplete (Phase 2) shows both options to disambiguate interactively

### Parser return structure

```python
@dataclass
class ParsedQuery:
    filters: Dict[str, Any]    # Maps to ListingFilters fields
    remainder: str             # Unmatched text -> passed as q
    interpretations: List[str] # Human-readable: ["3+ bedrooms", "Under $400,000", "Sylva"]
    is_mls_lookup: bool        # True if detected as MLS number
    is_address_lookup: bool    # True if detected as street address
```

---

## Autocomplete Strategy

Hybrid approach:

- **Cities/counties** (~150 items): Preload on component mount, filter client-side. Instant.
- **Addresses** (30k+ active): Server-side search, debounced at 200ms, after 3+ chars.
- **MLS numbers**: Server-side lookup when input looks numeric (5+ digits).

### Autocomplete API response

```json
{
  "suggestions": [
    {"type": "city", "value": "Sylva", "label": "Sylva, Jackson County", "count": 245},
    {"type": "address", "value": "117 Sylvan Way", "label": "117 Sylvan Way, Franklin", "listing_id": "abc123"}
  ]
}
```

---

## Three Phases

### Phase 1: Parser + Search Bar (MVP)

New files:
- `src/core/query_parser.py` - Deterministic NL parser with all extraction rules
- `src/core/test_query_parser.py` - Comprehensive unit tests
- `apps/public-site/src/components/SmartSearchBar.tsx` - React component (hero + compact variants)
- `apps/public-site/src/lib/search.ts` - Client API functions

API changes:
- `GET /api/public/search/parse?q=...` - Returns structured filters from natural language

Frontend changes:
- Homepage: replace hero form with `<SmartSearchBar variant="hero" />`
- Listings page: replace text input with `<SmartSearchBar variant="compact" />`

Flow: parse-then-redirect (SmartSearchBar calls parse API, builds URL params,
redirects to /listings?city=Sylva&max_price=400000&min_beds=3). Zero backend
search pipeline changes.

### Phase 2: Autocomplete

- `GET /api/public/autocomplete?q=...&limit=8` endpoint
- Dropdown with sections: Locations, Addresses, Query Interpretations
- Keyboard navigation (arrows, Enter, Escape)
- "Searching for: [3+ beds] [Under $400k] [Sylva]" chip preview while typing

### Phase 3: Enhancements

- LLM fallback for zero-result queries ("Try AI search?" button)
- Search history (localStorage) and popular/trending searches
- "Did you mean?" fuzzy suggestions for typos
- Voice search (Web Speech API, mobile)

---

## File Map

### New files to create

| File | Purpose |
|------|---------|
| `src/core/query_parser.py` | Deterministic NL parser |
| `src/core/test_query_parser.py` | Parser unit tests (critical) |
| `apps/public-site/src/components/SmartSearchBar.tsx` | React search bar component |
| `apps/public-site/src/lib/search.ts` | Client API for parse + autocomplete |

### Existing files to modify

| File | Change |
|------|--------|
| `apps/property-api/routes/public.py` | Add `/search/parse` and `/autocomplete` endpoints |
| `apps/public-site/src/app/page.tsx` | Replace hero `<form>` with SmartSearchBar |
| `apps/public-site/src/components/SearchFilters.tsx` | Replace text input with SmartSearchBar compact |
| `apps/public-site/src/lib/api.ts` | Add `parseSearch()` and `getAutocomplete()` |
| `apps/public-site/src/lib/types.ts` | Add ParsedQuery, AutocompleteSuggestion types |

### Files that DON'T change (important)

| File | Why unchanged |
|------|---------------|
| `src/core/listing_service.py` | Parser outputs ListingFilters params; existing pipeline handles search |
| `apps/public-site/src/app/listings/page.tsx` | Already reads all filter params from searchParams URL |

---

## Performance Notes

- Parser: pure regex on short string, sub-millisecond
- Autocomplete target: <100ms
- City/county prefix match on ~150 rows: instant
- Address LIKE on 30k active: may need index `CREATE INDEX IF NOT EXISTS idx_listings_active_address ON listings(status, address)`
- Client debounce at 200ms prevents excessive API calls
- No FTS5 needed for MVP (zone + status filtering keeps scan set manageable)
- City/county lists cached client-side (fetched once on mount)
- Parse results cached 30 seconds to avoid re-parsing identical queries

---

## Inspiration

Cloud Agent Suite's Cloud MLX: "What if I could search the MLS like Google?"
- 95% of MLS searches use only 12 core fields
- Single search bar with smart autocomplete
- Learns user behavior over time
- Replaces traditional dropdown/checkbox interfaces

Sources:
- https://cloudagentsuite.com/tools/mlx
- https://cloudagentsuite.com/mls
- https://blog.crmls.org/tips/cloud-ecosystem-part-3-cloud-mlx/
