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
