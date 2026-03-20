# Future Features & Enhancements

Ideas and design notes for future releases. Items here are not committed to a timeline; they capture thinking for when we're ready to build.

---

## Configurable Zone System (Public Release)

**Context:** The zone system shipped in v1 as a hardcoded county-to-zone mapping for WNC Mountain Homes. For a public release, zones become a core configuration primitive that any team can use to define their working geographies.

**The idea:** A team (brokerage, agent group, solo agent) configures their own zones during onboarding. Zones define:
- Which listings show by default on their public site
- How their dashboard scopes searches
- How stats, areas, and map views are bounded
- Call list and lead routing territories

**How it could work:**
- Admin UI where a team draws or selects counties/zip codes per zone
- Each zone gets a name, number, and description (e.g., "Core Market", "Secondary", "Extended")
- Default view zone(s) are configurable per team
- Agents within a team can have zone assignments (for lead routing, farm areas)
- Public site visitors see the team's default zones; toggle to expand

**Why this matters for public release:**
- Every real estate team has a service area, but it varies wildly by market
- A Charlotte team's zones look nothing like a WNC team's zones
- Without configurable zones, every team sees irrelevant listings mixed in with their market
- Zone configuration is a natural onboarding step: "Where do you work?"

**Building blocks already in place:**
- `zone` column on listings table (INTEGER, indexed)
- `compute_zone()` in field_mapper (currently reads from hardcoded ZONE_MAP)
- All public API endpoints accept `?zone=` parameter
- Dashboard and public site both have zone controls
- Backfill script pattern (`scripts/backfill_zones.py`) for recomputing zones

**What needs to change for configurability:**
- `zones` config table: team_id, zone_number, zone_name, counties (JSON array)
- `compute_zone()` reads from config table instead of hardcoded dict
- Admin UI for zone CRUD (draw on map or select from county/zip list)
- Team settings: default_zones (which zones show by default)
- Agent-zone assignments for territory management
- Backfill/recompute trigger when zone config changes

---

## House Tour Schedule PDF (Showing Itinerary)

**Context:** When an agent schedules showings for a buyer, they need a clean, branded PDF itinerary to hand to the client. The route planner has all the data; we just need to render it as a polished flyer.

**Reference:** 11x8.5 landscape flyer with property cards stacked vertically. Each card has: photo (left), address + price + showing time + property details (right).

**Data sources:**
1. `showings` table: date, time, name, lead_id, route_data (JSON with full stop order, times, notes)
2. `listings` table: address, city, state, zip, price, beds, baths, sqft, acreage, year_built, primary_photo, mls_number
3. `leads` table: buyer name
4. Agent branding (same assets as buyer report)

**Layout (per page, landscape 11x8.5):**
- Header: "HOUSE TOUR SCHEDULE" in large serif font, date, buyer name
- Jon Tharp Homes logo (top right or top left)
- 4-5 property cards per page, each card:
  - Left: primary photo (thumbnail, ~150px wide)
  - Right: address (bold), city/state/zip
  - Showing time (from route_data stops), e.g., "10:00 AM - 10:30 AM"
  - Price, Beds, Baths, SqFt, Acreage, Year Built in a compact row
  - Agent notes if present
- Footer: agent name, phone, email, website
- Page numbers if multi-page

**Implementation:**
- New file: `apps/automation/tour_schedule.py`
- Function: `generate_tour_schedule(showing_id) -> bytes`
- Uses WeasyPrint (same as buyer_report.py)
- Triggered from: "Print Itinerary" button on route planner, or from showings list
- Also available from package detail page

**Route planner integration:**
- Add "Print Itinerary" button next to "Print Details" in the route planner bottom bar
- Parse route_data JSON to get ordered stops with times
- Cross-reference listing_id to get full property data and photos

**Buyer report integration:**
- The Download PDF on package detail currently generates buyer reports (3 pages per property)
- Add option to prepend the tour schedule as the first page(s) of the combined PDF
- Or offer as a separate download: "Tour Schedule" vs "Full Report"
