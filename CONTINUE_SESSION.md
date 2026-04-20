# Session Handoff - 2026-03-29

## What Was Done

### MLS Grid API Fix (Critical, Deployed to PRD)
- **`2963bf7`** Fixed MLS Grid API abuse: `_fetch_primary_photo_from_api()` in `src/core/listing_service.py` was making individual API calls per listing view (violating Best Practices rules #3, #4). Disabled on-demand fetch, added photo download during incremental sync in `apps/mlsgrid/sync_engine.py`, created `scripts/backfill_missing_photos.py` for one-time backfill.
- Backfill completed on PRD: 1,759 DB path fixes + 231 photos downloaded. Only 9 listings truly have no photos in MLS.
- Cron jobs were paused then re-enabled on PRD. All 4 Canopy cron entries are active.
- PRD API and dashboard restarted with the fix deployed.

### TMO Pipeline Fix
- **`dd341c3`** Fixed TMO pipeline sending stale report emails after DB sync from PRD. Root cause: `sync-from-prd.sh` overwrites local DB which loses TMO data (parsed only on DEV). Guard now exits immediately if no new PDFs were parsed, preventing re-sends of old dates.
- Re-parsed March 15 + 22 PDFs to restore data in local DB.

### Lead Scoring Overhaul (4 commits)
- **`558038e`** Added source quality bonuses (referral +8, sphere +6, direct +5, open house +4, website +2) and tag bonuses (pre-approved +10, cash buyer +8, relocation +6, investor +5). Fuzzy stage matching for inconsistent team labeling.
- **`6bcd5d6`** Persist FUB email details (from, to, subject, snippet, type) to `contact_communications` table. Added 6 columns via `ensure_schema.py`.
- **`a2c9796`** Fixed FUB email field mapping: `campaignOrigin` for automation detection, `addresses.from[]` for sender. Type classification: auto:FUB/Beacon, auto:FUB Bulk, manual, inbound.
- **`d401471`** Persist FUB text message details (fromNumber, toNumber, deliveryStatus, actionPlanId, groupTextId).
- **`75967f6`** Scoring overhaul: inbound recency bonus (+15/+10/+5 pts), ghost browser detection (heat halved for 30+ views + zero inbound), automated email exclusion from relationship score, zero-inbound penalty.

### Email/Text Backfills Completed
- Email backfill: 4,479 records with full type classification (41% automated, 39% manual, 14% inbound)
- Text backfill: 2,238 records with phone numbers, delivery status, type classification

### Privacy Policy Page (Uncommitted)
- Created `apps/public-site/src/app/privacy/page.tsx` for dotloop API registration
- Added footer link in `apps/public-site/src/app/layout.tsx`
- NOT YET COMMITTED

### Research Completed
- Deep research on GoHighLevel (GHL): complement not competitor. GHL for marketing automation, myDREAMS for property intelligence. Option C recommended (GHL for non-IDX channels only if staying with JTH).
- Reviewed dotloop API docs: feasible integration for transaction management. Registration in progress.
- Reviewed MLS Grid Best Practices Guide and API v2.0 docs.

## Current State
- **Uncommitted changes**: Yes
  - `apps/public-site/src/app/layout.tsx` (privacy link in footer)
  - `apps/public-site/src/app/privacy/page.tsx` (new privacy policy page)
  - `scripts/monitor-photo-downloads.sh` (untracked, monitoring script)
- **DEV ahead of PRD by**: 6 commits (scoring overhaul, TMO fix, email/text persistence)
- **Needs PRD deploy**: Yes, but scoring changes run on DEV cron (fub-to-sheets). TMO fix and ensure_schema changes should be deployed to keep PRD in sync. Public-site privacy page needs `next build` + deploy separately.

## Schema Changes
- `contact_communications` table has 6 new columns: `email_from`, `email_to`, `subject`, `snippet`, `email_type`, `fub_email_id`. Added via `scripts/ensure_schema.py`. PRD DB needs `ensure_schema.py` run after deploy.

## New Environment Variables
- None required. All new scoring weights have sensible defaults and are overridable via env vars.

## In Progress / Next Session Priority

### 1. Scoring Configuration Dashboard (REQUESTED, NOT STARTED)
Eugy requested a visual scoring configuration page in the myDREAMS dashboard:
- Separate page from other config, dedicated to Contact Scoring
- **Priority section** at top: three dials/sliders for Heat/Value/Relationship weighting (currently 50/20/30)
- **Heat section**: weights for each signal (website visits 1.5, property views 3.0, favorites 5.0, shares 1.5, calls 5.0, texts 3.0), recency bonuses, decay multipliers
- **Value section**: price normalization and consistency weights
- **Relationship section**: inbound ratio weight, volume cap, auto-email exclusion toggle, zero-inbound penalty threshold
- **Bonus section**: source quality bonuses, tag bonuses, inbound recency bonuses, ghost browser thresholds
- As graphical as possible: dials, gauges, sliders
- Live preview of how changes would affect top 10 contacts would be ideal
- Config values currently live in `Config` class in `apps/fub-to-sheets/fub_to_sheets_v2.py` (lines ~143-210), all env-var overridable
- Dashboard is Flask app at `apps/property-dashboard/app.py:5001`
- Use `shared/css/dreams.css` design system

### 2. Privacy Policy Page
- Commit the uncommitted public-site changes (privacy page + footer link)
- Build and deploy public site to PRD

### 3. PRD Deploy
- Pull 6 commits to PRD, run ensure_schema.py, restart services
- Public site needs separate `next build` + deploy

### 4. Dotloop Integration
- Eugy is registering for API access. Privacy policy URL: `https://wncmountain.homes/privacy`
- Once client_id and client_secret received, build OAuth flow and initial integration
- Phase 1: read-only transaction dashboard
- Phase 2: Loop-It button from property detail pages
- Phase 3: webhooks for real-time status updates

### 5. FUB Content Access
- FUB API hides email subject, body, and addresses behind a permission tier
- `[CONTENT HIDDEN]` and `* Body is hidden for privacy reasons *` returned
- Worth contacting FUB support to ask about upgrading API access level
- This would unlock AI-powered contextual follow-ups and nudges

## Key Scoring Parameters (Current)
```
Priority Weights: Heat=0.50, Value=0.20, Relationship=0.30
Inbound Recency: 0-2d=+15, 3-7d=+10, 8-14d=+5
Ghost Browser: 30+ views + 3+ outreach + 0 inbound = heat * 0.5
Source Bonuses: referral=+8, sphere=+6, direct=+5, open_house=+4, website=+2
Tag Bonuses: pre-approved=+10, cash_buyer=+8, relocation=+6, investor=+5, buyer/seller=+2
Stage Multipliers: Hot=1.3, Active=1.2, Nurture=1.0, New=0.9, Cold=0.7, Closed/Trash=0.0
Fuzzy Stage Aliases: "hot"->1.3, "warm"->1.2, "prospect"->0.9, "past client"->1.0
Zero-Inbound Penalty: 0 inbound + 3+ personal outreach = relationship * 0.5
Auto Email Exclusion: campaignOrigin or actionPlanId emails excluded from relationship denominator
```
