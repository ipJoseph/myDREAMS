# Photo Pipeline Specification

Status: **Draft v1**, 2026-04-21. Supersedes ad-hoc decisions made across 16 commits over the prior 5 weeks. Written after `docs/incidents/20260324-navica-feed-stopped.md` and the connection-leak detour as the first deliverable of a spec-first approach to the photo subsystem.

## Purpose

Photos are the foundation of the public-site experience. Five weeks of patching convinced us that the problem wasn't a missing fix, it was a missing **spec**. This document states what must be true at all times so we can tell, at a glance, whether a listing is in a valid state and where responsibility lies when it isn't. Every future change to the photo system must cite which section of this spec it satisfies.

## States of a listing photo lifecycle

Single column is the source of truth: `listings.gallery_status`.

| State | Meaning | Transitions out |
|---|---|---|
| `pending` | MLS has reported photos for this listing. Local files may or may not be fully on disk yet. Never safe for public list endpoints. | `ready` once verified. `skipped` after N failed download attempts. |
| `ready` | Every URL in `photos` is a local path `/api/public/photos/{source}/{file}` AND every file exists on disk. Safe for public list endpoints. | `pending` if the MLS reports new photos (PhotosChangeTimestamp). `archived` when listing leaves ACTIVE/PENDING. |
| `skipped` | MLS reported zero photos, OR all download attempts failed permanently. Listing may still appear in public list but the detail page shows address-only. | `pending` on manual retry. |
| `archived` | Listing is SOLD / EXPIRED / WITHDRAWN / CANCELLED. Photos may be purged from disk. | Terminal for now. Reserved for future cleanup pipeline. |

## Column ownership and contracts

Five columns currently overlap in meaning. This spec asserts a single writer and a clear contract for each.

| Column | Kind | Single Writer | Readers | Contract |
|---|---|---|---|---|
| `photos` | JSON array of strings | **Gallery worker** only | Public API | If `gallery_status = 'ready'`, every element is a local path `/api/public/photos/...` and the file at that path exists on disk. Never CDN URLs when `ready`. |
| `photos_source_urls` (new; repurpose `photos_local`) | JSON array of strings | **Sync engines** only | Gallery worker | Ephemeral CDN URLs from the MLS API. May be expired at any time. Never served publicly. |
| `primary_photo` | Single URL string | Sync engines | Public API | Best-effort single photo that should be safe to serve immediately. Either a long-lived CDN URL or a local path. Always present if the listing has any photos. |
| `photo_count` | Integer | Sync engines | UI display | Count reported by MLS. Authoritative for "how many photos exist upstream." |
| `photos_count` | Integer | DEPRECATE (duplicate of `photo_count`) | — | Drop in a future migration. |
| `photo_local_path` | String | DEPRECATE (pre-gallery-era single local path) | — | Drop in a future migration. |
| `photo_ready` | Boolean | Gallery worker (legacy) | Public API (legacy) | To be replaced by `gallery_status = 'ready'` checks. Kept in place for one migration cycle. |
| `gallery_status` | Enum text | Gallery worker | Public API, UI, cron | Source of truth for "is this listing presentable?" |
| `gallery_priority` (new) | Integer, default 0 | API (on user detail view) | Gallery worker | User-viewed listings jump the backfill queue by setting priority > 0. Worker orders FIFO by `gallery_priority DESC, photos_change_timestamp ASC`. |
| `photos_change_timestamp` | Timestamp | Sync engines | Gallery worker | Bumped when MLS reports new photo URLs. |
| `photo_verified_at` | Timestamp | Gallery worker | Health dashboard | Last successful verify-on-disk pass. Null means never verified. |

## Invariants

The system is "healthy" only when all of these hold. Any violation is a bug.

1. `gallery_status = 'ready'` ⇒ every element of `photos` starts with `/api/public/photos/` AND the referenced file exists on disk.
2. `gallery_status = 'ready'` ⇒ `photo_verified_at` is not null and is the timestamp of the last successful verify.
3. Sync engines never write to `photos` or `gallery_status = 'ready'`. They only write to `photos_source_urls`, `primary_photo`, `photo_count`, `photos_change_timestamp`, and flip `gallery_status` to `pending` if photos changed.
4. Public list endpoints (`/api/public/listings`, home-page "New on the Market", etc.) return only listings with `gallery_status = 'ready'` AND `idx_opt_in = 1` AND `status IN ('ACTIVE', 'PENDING')`.
5. Public detail endpoint (`/api/public/listings/{id}`) returns 200 whenever `idx_opt_in = 1` AND `status IN ('ACTIVE', 'PENDING')`, regardless of `gallery_status`. The response always includes `gallery_status` so the client can render the correct UX (full gallery when ready, primary-only + "loading more photos" when pending).
6. No request-path code may block on an external HTTP call to `media.mlsgrid.com` or any Navica CDN. Doing so turns pool saturation into an availability incident (2026-04-21 confirmed this at scale). Download work is the gallery worker's job, always asynchronous.
7. Each sync-engine write is its own transaction (or a SAVEPOINT inside a batch transaction). One row's failure must not poison sibling rows. See `docs/incidents/20260324-navica-feed-stopped.md` for the 946-row cascade that motivated this rule.

## Public contracts

What the Next.js site may assume, given that invariants hold.

**List endpoint response** (`GET /api/public/listings`):
- Every listing returned has `gallery_status = 'ready'`
- Every `photos[]` URL is a local path that will return 200 from the photo endpoint
- `primary_photo` is present and safe to render immediately

**Detail endpoint response** (`GET /api/public/listings/{id}`):
- Always has `primary_photo` (local path preferred)
- Always has `gallery_status` in the payload
- If `gallery_status = 'ready'`: `photos` is the full local-path array
- If `gallery_status != 'ready'`: `photos` is either absent or contains only `primary_photo`; client shows primary only and polls the gallery endpoint

**Gallery endpoint** (`GET /api/public/listings/{id}/gallery`):
- Cheap, always fast, does NO external I/O
- Returns `{status: 'ready' | 'pending' | 'skipped', photos: [...] | null}`
- When status is ready, photos is the full local-path array

## Workflow principles

- **Fire-and-forget priority trigger:** when a user views a detail page for a `pending` listing, the API sets `gallery_priority = 10` as a non-blocking side effect. The gallery worker picks it up on the next poll cycle. User sees primary instantly; gallery hydrates within seconds.
- **Client polling, not server push:** the Next.js detail page polls the gallery endpoint every 2 seconds for up to 30 seconds after initial load. No SSE/websocket infra required.
- **No CDN fallback in the request path:** if a listing is `pending` at request time, the response admits it. The client handles it. The server never tries to synchronously fetch from a CDN "just in case."

## Out of spec (deliberate omissions)

These are acknowledged gaps for follow-up, not forgotten:

- **MountainLakesMLS photo pipeline:** as of 2026-04-21 DB state, 0 of 1,417 active/pending MountainLakesMLS listings are `photo_ready`. Separate investigation; not addressed by this spec.
- **Sold/archived photo cleanup on disk:** once `gallery_status = 'archived'` is populated, we can purge disk space. Implementation deferred to Phase 3.
- **Navica-specific CDN expiry behavior:** MLS Grid CDN URLs expire within ~1 hour. Navica behavior is less documented. Both pipelines should follow the same download-to-disk rule; this spec enforces the outcome regardless of which API is upstream.
- **Per-row transaction hardening:** invariant #7 is asserted but not yet enforced in code. Task A8 tracks the fix.

## Relationship to other documents

- `docs/incidents/20260324-navica-feed-stopped.md` — the feed incident this spec was born from.
- `docs/runbooks/postgres-connection-hygiene.md` — connection-layer guarantees that enable invariant #6.
- `docs/ARCHITECTURE.md` — higher-level system view; this spec details the photo subsystem.
- `docs/DECISIONS.md` — any deviation from this spec must record the exception here.
