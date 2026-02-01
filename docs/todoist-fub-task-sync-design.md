# myDREAMS: Todoist ↔ Follow Up Boss Task Sync

## Design Document v1.0

**Author:** Joseph Williams / Claude (Opus 4.5)
**Date:** 2025-02-01
**Status:** Design Complete — Ready for Implementation
**Module Location:** `myDreams/modules/task_sync/` (proposed)

---

## 1. Problem Statement

Follow Up Boss (FUB) has a limited task/todo system. Tasks in FUB can only be associated with a **Person** (contact), not with a **Deal** (Contact + Property). Google Tasks is similarly limited. Joseph needs a robust task management layer that:

- Provides rich task management (priorities, labels, projects, natural language dates, filters)
- Associates tasks with FUB Deals (Contact + Property), not just contacts
- Flows tasks bidirectionally between Todoist and FUB
- Supports multiple deals per contact (e.g., primary residence, child's property, STR investment)
- Integrates into the existing myDREAMS platform and infrastructure

**Solution:** Todoist Pro as the task management engine, with a custom sync service bridging Todoist and FUB. A local SQLite bridge database maintains the Deal-aware mapping that neither system provides natively.

---

## 2. Architecture Overview

### 2.1 System Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    myDREAMS VPS (Prod)                    │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │          Task Sync Service (FastAPI)                │  │
│  │                                                      │  │
│  │  POST /webhook/todoist  ← Todoist pushes here       │  │
│  │  GET  /health           ← Health check              │  │
│  │                                                      │  │
│  │  FUB Poller (async loop, every 30s)                 │  │
│  │    └─ GET /v1/tasks?updatedAfter=<cursor>           │  │
│  │                                                      │  │
│  │  Deal Cache Refresher (async loop, every 5-10 min)  │  │
│  │    └─ GET /v1/deals                                 │  │
│  │                                                      │  │
│  │  Sync Engine                                         │  │
│  │    ├─ Direction detection (origin tracking)          │  │
│  │    ├─ Conflict resolution (last-write-wins)          │  │
│  │    ├─ ID mapping (bridge table)                      │  │
│  │    ├─ Deal enrichment (FUB /deals + /people lookup)  │  │
│  │    └─ Todoist project/section management             │  │
│  │                                                      │  │
│  │  Todoist Client (REST API v2 + Sync API v1)         │  │
│  │  FUB Client (REST API v1)                            │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │             SQLite: task_sync.db                    │  │
│  │                                                      │  │
│  │  task_map          (bridge / ID mapping table)      │  │
│  │  deal_cache        (FUB deal snapshots)             │  │
│  │  todoist_projects  (project/section ID cache)       │  │
│  │  sync_state        (cursors, tokens, timestamps)    │  │
│  │  sync_log          (audit trail)                    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │       Existing myDREAMS infrastructure              │  │
│  │       (property DB, FUB scripts, cron jobs, etc.)   │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Caddy (reverse proxy, HTTPS termination)               │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Environment Strategy

| Aspect | Dev (Local Machine) | Prod (VPS) |
|---|---|---|
| FUB sync | Poll every 30s | Poll every 30s |
| Todoist sync | Poll via Sync API (30s) | **Webhooks** (real-time) |
| Todoist webhook testing | `ngrok` tunnel OR poll fallback | Native via Caddy |
| Database | SQLite (local copy) | SQLite (VPS) |
| Runner | `python -m task_sync` (manual) | systemd service |
| Config | `.env.dev` | `.env.prod` |
| Log level | DEBUG | INFO |

Controlled by environment variable `TASK_SYNC_ENV=dev|prod` and config flag `TODOIST_USE_WEBHOOKS=true|false`.

### 2.3 Data Flow Summary

```
FUB Task Created/Updated
  → FUB Poller detects change (≤30s latency)
  → Sync Engine checks bridge table
  → If new: create in Todoist, map IDs, enrich with Deal context
  → If existing: update Todoist task, record sync

Todoist Task Created/Updated
  → Webhook (prod) or Sync API poll (dev) detects change
  → Sync Engine checks bridge table
  → If new + CRM-tagged: create FUB task, link to person
  → If existing: update FUB task, record sync
  → If not CRM-tagged: ignore (personal tasks stay in Todoist only)

FUB Deal Stage Changed
  → Deal Cache Refresher detects change
  → Sync Engine moves Todoist section to new pipeline project
```

---

## 3. External API Reference

### 3.1 Todoist API

**Base URLs:**
- REST API v2: `https://api.todoist.com/rest/v2/`
- Sync API v1: `https://api.todoist.com/api/v1/sync`
- Webhooks: Registered via App Management Console at `https://developer.todoist.com/appconsole.html`

**Authentication:** Bearer token in Authorization header
```
Authorization: Bearer <TODOIST_API_TOKEN>
```

Personal API token available at: Todoist Settings → Integrations → API token

**Python SDK:** `todoist-api-python` (PyPI, Python 3.9+)
```bash
pip install todoist-api-python
```

**Key REST API v2 Endpoints:**

| Endpoint | Method | Purpose |
|---|---|---|
| `/projects` | GET, POST | List/create projects |
| `/projects/{id}` | GET, POST, DELETE | Get/update/delete project |
| `/sections` | GET, POST | List/create sections |
| `/sections/{id}` | GET, POST, DELETE | Get/update/delete section |
| `/tasks` | GET, POST | List/create tasks |
| `/tasks/{id}` | GET, POST, DELETE | Get/update/delete task |
| `/tasks/{id}/close` | POST | Complete a task |
| `/tasks/{id}/reopen` | POST | Reopen a task |
| `/comments` | GET, POST | List/create comments |
| `/labels` | GET, POST | List/create labels |

**Sync API — Incremental Sync (for polling in dev):**
```
POST https://api.todoist.com/api/v1/sync
  sync_token=<token>          # Use "*" for full sync, then stored token for incremental
  resource_types=["items"]    # "items" = tasks in Sync API terminology
```
Returns only changes since last sync_token. Store the returned `sync_token` for next call.

**Todoist Webhooks (for prod):**

Watched events relevant to this integration:
- `item:added` — task created
- `item:updated` — task modified
- `item:completed` — task completed
- `item:uncompleted` — task reopened
- `item:deleted` — task deleted

Webhook payload includes `event_name`, `event_data` (full task object), and `user_id`.
Verify via `X-Todoist-Hmac-SHA256` header using your app's client secret.

**Rate Limits:**
- REST API: 1000 requests per 15 minutes per user
- Sync API: 1000 partial syncs per 15 minutes, 100 full syncs per 15 minutes
- Batch up to 100 commands per Sync request

**Todoist Pro Plan Required:**
- 300 active projects (free = 5)
- 150 filters (free = 3)
- Unlimited labels
- Reminders
- Task duration
- $5/month billed annually

### 3.2 Follow Up Boss API

**Base URL:** `https://api.followupboss.com/v1/`

**Authentication:** HTTP Basic Auth — API key as username, password blank
```
Authorization: Basic base64(<FUB_API_KEY>:)
```

API key generated at: FUB → Admin → API

**System Registration (required for integrations):**
Every request must include:
```
X-System: myDREAMS
X-System-Key: <registered_system_key>
```
Register at: https://www.followupboss.com/developer-registration

**Key Endpoints:**

| Endpoint | Method | Purpose |
|---|---|---|
| `/tasks` | GET | List tasks (supports filters) |
| `/tasks` | POST | Create task |
| `/tasks/{id}` | GET | Get specific task |
| `/tasks/{id}` | PUT | Update task |
| `/tasks/{id}` | DELETE | Delete task |
| `/deals` | GET | List deals |
| `/deals/{id}` | GET | Get specific deal |
| `/people/{id}` | GET | Get person details |
| `/identity` | GET | Verify auth / get account info |

**FUB Task Object (key fields):**
```json
{
  "id": 12345,
  "personId": 5001,
  "assignedTo": 1,
  "subject": "Call about listing",
  "dueDate": "2025-02-15",
  "dateDue": "2025-02-15T10:00:00-05:00",
  "isCompleted": false,
  "completedAt": null,
  "created": "2025-02-01T08:00:00-05:00",
  "updated": "2025-02-01T08:00:00-05:00"
}
```

**FUB Deal Object (key fields):**
```json
{
  "id": 5501,
  "personId": 5001,
  "pipelineId": 1,
  "stageId": 3,
  "name": "John Smith - 123 Main St",
  "dealValue": 350000,
  "propertyAddress": "123 Main St",
  "propertyCity": "Franklin",
  "propertyState": "NC",
  "propertyZip": "28734",
  "created": "2025-01-15T10:00:00-05:00",
  "updated": "2025-02-01T08:00:00-05:00"
}
```

**FUB Polling Strategy:**
- Use `GET /v1/tasks?sort=updated&updatedAfter=<ISO_timestamp>` to fetch only recently changed tasks
- Store the last poll timestamp in `sync_state` table
- Poll every 30 seconds
- Respect `X-RateLimit-Remaining` header; back off if < 10

**Rate Limits:** Sliding 10-second window. Monitor via response headers:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Window`
- `X-RateLimit-Context`

---

## 4. Data Model (SQLite)

### 4.1 Database File

`task_sync.db` — stored alongside existing myDREAMS SQLite databases.

### 4.2 Schema

```sql
-- Bridge table: maps task IDs between systems and associates with deals
CREATE TABLE IF NOT EXISTS task_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    todoist_task_id TEXT UNIQUE,          -- Todoist task ID (string in their API)
    fub_task_id INTEGER UNIQUE,           -- FUB task ID (integer)
    fub_person_id INTEGER,                -- FUB contact ID
    fub_deal_id INTEGER,                  -- FUB deal ID (the key innovation)
    todoist_project_id TEXT,              -- Todoist project this task lives in
    todoist_section_id TEXT,              -- Todoist section (Deal grouping)
    origin TEXT NOT NULL,                 -- 'todoist' or 'fub' (where task was created)
    sync_status TEXT DEFAULT 'synced',    -- 'synced', 'pending_to_todoist', 'pending_to_fub', 'conflict', 'error'
    last_synced_at TEXT,                  -- ISO timestamp of last successful sync
    todoist_updated_at TEXT,              -- Last known Todoist modification time
    fub_updated_at TEXT,                  -- Last known FUB modification time
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_task_map_todoist ON task_map(todoist_task_id);
CREATE INDEX idx_task_map_fub ON task_map(fub_task_id);
CREATE INDEX idx_task_map_deal ON task_map(fub_deal_id);
CREATE INDEX idx_task_map_person ON task_map(fub_person_id);
CREATE INDEX idx_task_map_status ON task_map(sync_status);

-- Deal cache: local snapshot of FUB deals to avoid excessive API calls
CREATE TABLE IF NOT EXISTS deal_cache (
    id INTEGER PRIMARY KEY,               -- FUB deal ID
    person_id INTEGER NOT NULL,
    pipeline_id INTEGER,
    stage_id INTEGER,
    stage_name TEXT,
    deal_name TEXT,
    deal_value REAL,
    property_address TEXT,
    property_city TEXT,
    property_state TEXT,
    property_zip TEXT,
    person_name TEXT,                      -- Denormalized for convenience
    person_email TEXT,
    person_phone TEXT,
    todoist_project_id TEXT,              -- Mapped Todoist project for this pipeline stage
    todoist_section_id TEXT,              -- Mapped Todoist section for this deal
    fetched_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT                        -- FUB's updated timestamp
);

CREATE INDEX idx_deal_cache_person ON deal_cache(person_id);
CREATE INDEX idx_deal_cache_stage ON deal_cache(stage_id);

-- Todoist project/section mapping: maps pipeline stages to Todoist projects
CREATE TABLE IF NOT EXISTS todoist_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    todoist_project_id TEXT UNIQUE NOT NULL,
    project_name TEXT NOT NULL,
    fub_pipeline_id INTEGER,
    fub_stage_id INTEGER,
    project_type TEXT NOT NULL,           -- 'pipeline_stage', 'general', 'personal'
    created_at TEXT DEFAULT (datetime('now'))
);

-- Sync state: tracks cursors, tokens, timestamps for incremental sync
CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,                  -- e.g., 'fub_last_poll', 'todoist_sync_token'
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Sync log: audit trail for debugging and monitoring
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    direction TEXT NOT NULL,               -- 'fub_to_todoist', 'todoist_to_fub', 'internal'
    action TEXT NOT NULL,                  -- 'create', 'update', 'complete', 'delete', 'move', 'error'
    todoist_task_id TEXT,
    fub_task_id INTEGER,
    fub_deal_id INTEGER,
    details TEXT,                           -- JSON blob with change details
    status TEXT DEFAULT 'success'          -- 'success', 'error', 'skipped'
);

CREATE INDEX idx_sync_log_timestamp ON sync_log(timestamp);
CREATE INDEX idx_sync_log_status ON sync_log(status);
```

---

## 5. Todoist Project Structure

### 5.1 Organization Strategy

**Projects = FUB Pipeline Stages** (finite, stable set)
**Sections = Deals** (Contact + Property grouping)
**Tasks = Individual action items**
**Labels = Cross-cutting metadata** (county, task type, urgency)

### 5.2 Example Structure

```
Project: "🔍 Prospecting"               ← Pipeline stage
  Section: "Tom Baker — Highlands area"  ← Deal (contact + property context)
    Task: "Initial consultation call"
    Task: "Send market overview packet"

Project: "🏠 Active Buyer"              ← Pipeline stage
  Section: "John Smith — Primary Res — 123 Main St, Franklin"
    Task: "Pull comps"                   ← Labels: @franklin, @comps
    Task: "Schedule showing"
  Section: "John Smith — STR Investment — Bryson City area"
    Task: "Run STR revenue analysis"     ← Labels: @bryson-city, @investment
    Task: "Check zoning for STR"
  Section: "Jane Doe — Downsizing — 88 Elm, Highlands"
    Task: "CMA for listing appointment"

Project: "📋 Under Contract"            ← Pipeline stage
  Section: "Bob Jones — 222 River Rd, Franklin"
    Task: "Follow up on inspection results"
    Task: "Coordinate with lender on appraisal"

Project: "✅ Closed — Follow Up"        ← Post-close nurture
  Section: "Alice Green — 55 Maple Dr, Sylva"
    Task: "30-day check-in call"
    Task: "Request review/referral"

Project: "📌 General CRM Tasks"         ← Non-deal FUB tasks
  (Tasks linked to contacts but no specific deal)

Project: "🧑 Personal / Non-CRM"        ← Not synced to FUB
  (Joseph's personal tasks — excluded from sync)
```

### 5.3 Section Naming Convention

Format: `{Contact Name} — {Deal Description} — {Property Address or Area}`

Examples:
- `John Smith — Primary Res — 123 Main St, Franklin`
- `John Smith — STR Investment — Bryson City area`
- `Jane Doe — Downsizing — Highlands`

This gives immediate context when viewing tasks in Todoist without needing to drill into details.

### 5.4 Label Taxonomy (Suggested Starting Point)

**County labels:** `@macon`, `@jackson`, `@swain`, `@haywood`, `@transylvania`, `@henderson`, `@buncombe`, `@clay`, `@cherokee`, `@graham`, `@polk`

**Task type labels:** `@call`, `@email`, `@showing`, `@paperwork`, `@research`, `@follow-up`

**Deal type labels:** `@buyer`, `@seller`, `@investor`, `@str`

**Sync labels:** `@crm` (marks task for FUB sync — tasks without this in non-pipeline projects are ignored)

### 5.5 Pipeline Stage → Project Mapping

This mapping is stored in `todoist_projects` table and configured at setup time. Example mapping:

| FUB Pipeline Stage | Todoist Project |
|---|---|
| New Lead | 🔍 Prospecting |
| Active Buyer | 🏠 Active Buyer |
| Active Seller | 🏡 Active Seller |
| Under Contract | 📋 Under Contract |
| Closed | ✅ Closed — Follow Up |
| (No deal) | 📌 General CRM Tasks |

This will need to be customized based on Joseph's actual FUB pipeline configuration. The setup script (see Section 8) should fetch pipelines/stages from FUB and prompt for mapping.

---

## 6. Module Structure

### 6.1 File Layout

```
myDreams/
├── modules/
│   └── task_sync/
│       ├── __init__.py
│       ├── __main__.py              # Entry point: python -m modules.task_sync
│       ├── config.py                # Environment-aware configuration
│       ├── db.py                    # SQLite connection, schema init, helpers
│       ├── models.py                # Pydantic models for task, deal, sync objects
│       ├── fub_client.py            # FUB API wrapper (tasks, deals, people)
│       ├── todoist_client.py        # Todoist API wrapper (REST + Sync)
│       ├── bridge.py                # Bridge table CRUD, ID mapping lookups
│       ├── sync_engine.py           # Core sync logic, conflict resolution
│       ├── deal_enrichment.py       # Deal cache management, deal-to-section mapping
│       ├── poller.py                # Async polling loops (FUB + Todoist fallback)
│       ├── api.py                   # FastAPI app (webhook endpoint, health check)
│       ├── setup_wizard.py          # Interactive setup: create projects, map pipelines
│       └── utils.py                 # Shared utilities (logging, timestamp helpers)
├── config/
│   ├── .env.dev                     # Dev environment variables
│   └── .env.prod                    # Prod environment variables
├── docs/
│   └── todoist-fub-task-sync-design.md   # This document
└── ...
```

### 6.2 Module Responsibilities

#### `config.py`
- Load environment variables from `.env.dev` or `.env.prod`
- Expose typed config object with all settings
- Key settings:

```python
# Environment
TASK_SYNC_ENV: str              # "dev" or "prod"

# Todoist
TODOIST_API_TOKEN: str
TODOIST_USE_WEBHOOKS: bool      # True in prod, False in dev
TODOIST_WEBHOOK_SECRET: str     # For HMAC verification (prod only)

# Follow Up Boss
FUB_API_KEY: str
FUB_SYSTEM_NAME: str            # "myDREAMS"
FUB_SYSTEM_KEY: str             # Registered system key

# Sync
FUB_POLL_INTERVAL_SECONDS: int  # Default 30
TODOIST_POLL_INTERVAL_SECONDS: int  # Default 30 (dev only)
DEAL_CACHE_REFRESH_SECONDS: int # Default 300 (5 min)

# Database
DB_PATH: str                    # Path to task_sync.db

# API Server (prod)
API_HOST: str                   # Default "127.0.0.1"
API_PORT: int                   # Default 8100 (behind Caddy)

# Logging
LOG_LEVEL: str                  # "DEBUG" in dev, "INFO" in prod
```

#### `db.py`
- Create/open SQLite connection with WAL mode enabled
- Run schema migrations on startup (create tables if not exist)
- Provide helper functions for common queries
- Connection context manager for safe transactions

#### `models.py`
- Pydantic models for internal task representation, bridging the differences between Todoist and FUB task formats:

```python
class UnifiedTask:
    """Internal task representation that both systems map to/from."""
    title: str
    description: Optional[str]
    due_date: Optional[datetime]
    is_completed: bool
    priority: int                # 1-4 (mapped from both systems)
    fub_person_id: Optional[int]
    fub_deal_id: Optional[int]
    labels: list[str]
    origin: str                  # 'todoist' or 'fub'
```

#### `fub_client.py`
- Wrapper around FUB REST API v1
- Methods:
  - `get_tasks(updated_after: datetime) -> list[FUBTask]`
  - `get_task(task_id: int) -> FUBTask`
  - `create_task(task: FUBTask) -> FUBTask`
  - `update_task(task_id: int, updates: dict) -> FUBTask`
  - `delete_task(task_id: int) -> bool`
  - `get_deals(person_id: Optional[int]) -> list[FUBDeal]`
  - `get_deal(deal_id: int) -> FUBDeal`
  - `get_person(person_id: int) -> FUBPerson`
  - `get_pipelines() -> list[FUBPipeline]`
  - `get_stages() -> list[FUBStage]`
- Handle rate limiting: check `X-RateLimit-Remaining`, sleep if < 10
- Handle HTTP Basic Auth with API key
- Include `X-System` and `X-System-Key` headers on every request
- Use `httpx` (async) for non-blocking calls

#### `todoist_client.py`
- Wrapper around both Todoist REST API v2 and Sync API v1
- REST methods (for writes):
  - `create_task(content, project_id, section_id, labels, due_string, priority) -> TodoistTask`
  - `update_task(task_id, updates) -> TodoistTask`
  - `close_task(task_id) -> bool`
  - `reopen_task(task_id) -> bool`
  - `delete_task(task_id) -> bool`
  - `create_project(name) -> TodoistProject`
  - `create_section(name, project_id) -> TodoistSection`
  - `move_task(task_id, section_id, project_id) -> bool`
- Sync methods (for polling reads):
  - `incremental_sync(sync_token, resource_types) -> SyncResponse`
  - `get_sync_token() -> str` (from sync_state table)
  - `save_sync_token(token)` (to sync_state table)
- Use `todoist-api-python` SDK where convenient, raw `httpx` where needed
- Bearer token auth

#### `bridge.py`
- CRUD operations on `task_map` table
- Key methods:
  - `get_by_todoist_id(todoist_task_id) -> TaskMapping | None`
  - `get_by_fub_id(fub_task_id) -> TaskMapping | None`
  - `get_by_deal(fub_deal_id) -> list[TaskMapping]`
  - `create_mapping(todoist_task_id, fub_task_id, fub_person_id, fub_deal_id, origin) -> TaskMapping`
  - `update_mapping(mapping_id, **kwargs)`
  - `get_pending(direction) -> list[TaskMapping]`
  - `mark_synced(mapping_id, todoist_updated, fub_updated)`
  - `mark_error(mapping_id, error_details)`

#### `sync_engine.py`
- Core orchestration logic
- Key methods:
  - `process_fub_changes(changed_tasks: list[FUBTask])` — handles FUB → Todoist
  - `process_todoist_changes(changed_items: list[TodoistItem])` — handles Todoist → FUB
  - `resolve_conflict(mapping, fub_task, todoist_task)` — last-write-wins
  - `handle_deal_stage_change(deal_id, old_stage, new_stage)` — move Todoist section
- Anti-loop protection: when the sync engine writes to System A, it records the resulting `updated_at` timestamp. When it next polls System A and sees that change, it recognizes its own write and skips it.
- Sync cycle pseudocode:

```
async def run_sync_cycle():
    # 1. Poll FUB for changed tasks
    fub_changes = await fub_client.get_tasks(updated_after=last_fub_poll)
    await process_fub_changes(fub_changes)
    update_sync_state('fub_last_poll', now())

    # 2. Poll/receive Todoist changes
    if using_webhooks:
        # Changes arrive via webhook handler, processed there
        pass
    else:
        sync_response = await todoist_client.incremental_sync(token)
        await process_todoist_changes(sync_response.items)
        save_sync_token(sync_response.sync_token)

    # 3. Refresh deal cache periodically
    if time_since_last_deal_refresh > DEAL_CACHE_REFRESH_SECONDS:
        await refresh_deal_cache()

    # 4. Process any pending/retry items
    await retry_errors()
```

#### `deal_enrichment.py`
- Manages the `deal_cache` table
- Methods:
  - `refresh_deal_cache()` — fetch all active deals from FUB, update cache
  - `get_deals_for_person(person_id) -> list[CachedDeal]`
  - `get_deal(deal_id) -> CachedDeal | None`
  - `resolve_deal_for_task(fub_task) -> CachedDeal | None` — given a FUB task (which only has person_id), determine which deal it belongs to
  - `get_or_create_todoist_section(deal) -> (project_id, section_id)` — ensure the Todoist project/section exists for a deal, create if needed
- Deal resolution strategy when a FUB task comes in with only a person_id:
  1. Look up all active deals for that person
  2. If exactly 1 deal → auto-associate
  3. If multiple deals → create task in "📌 General CRM Tasks" with a comment noting the available deals. Flag for manual association (label `@needs-deal-link`)
  4. If 0 deals → place in "📌 General CRM Tasks"

#### `poller.py`
- Async polling loops using `asyncio`
- FUB poller: runs every `FUB_POLL_INTERVAL_SECONDS`
- Todoist poller (dev only): runs every `TODOIST_POLL_INTERVAL_SECONDS`
- Deal cache refresher: runs every `DEAL_CACHE_REFRESH_SECONDS`
- Graceful shutdown on SIGTERM/SIGINT

#### `api.py`
- FastAPI application
- Endpoints:
  - `POST /webhook/todoist` — receive Todoist webhook events, verify HMAC, dispatch to sync engine
  - `GET /health` — return service status, last sync times, pending count
  - `GET /stats` — return sync statistics (total synced, errors, last 24h activity)
- HMAC verification for Todoist webhooks:

```python
import hmac, hashlib

def verify_todoist_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

#### `setup_wizard.py`
- Interactive CLI tool run once during initial setup
- Steps:
  1. Verify Todoist API token and FUB API key connectivity
  2. Fetch FUB pipelines and stages
  3. Create Todoist projects for each pipeline stage (or map to existing)
  4. Store pipeline-to-project mappings in `todoist_projects` table
  5. Create standard labels in Todoist
  6. Initialize `sync_state` with starting cursors
  7. Optionally do an initial full sync of existing FUB tasks

#### `__main__.py`
- Entry point: `python -m modules.task_sync`
- CLI arguments:
  - `run` — start the sync service (poller + optional API server)
  - `setup` — run the setup wizard
  - `sync-once` — run a single sync cycle (useful for testing)
  - `status` — show current sync state and stats

---

## 7. Sync Logic Details

### 7.1 FUB → Todoist (New Task)

```
1. FUB task detected with no matching todoist_task_id in bridge
2. Look up person_id → get person name from FUB
3. Look up deals for person_id from deal_cache
4. If 1 deal:
   a. Get or create Todoist section for that deal
   b. Create Todoist task in appropriate project/section
   c. Add labels based on deal metadata (county, deal type)
5. If multiple deals:
   a. Create task in "General CRM Tasks" project
   b. Add label @needs-deal-link
   c. Add Todoist comment: "Multiple deals found: [list]. Assign manually."
6. If 0 deals:
   a. Create task in "General CRM Tasks" project
7. Insert bridge record with origin='fub'
8. Log sync action
```

### 7.2 Todoist → FUB (New Task)

```
1. Todoist task detected with no matching fub_task_id in bridge
2. Check if task is in a CRM-synced project (pipeline stage or General CRM)
   - If not (e.g., personal project): skip entirely
3. Look up section → find deal from deal_cache via todoist_section_id
4. If deal found → get person_id from deal
5. Create FUB task:
   - subject = Todoist task content
   - personId = person_id from deal
   - dueDate = Todoist due date
6. Insert bridge record with origin='todoist'
7. Log sync action
```

### 7.3 Updates (Either Direction)

```
1. Change detected in System A
2. Look up bridge record
3. Compare A's updated_at with stored value
   - If matches last known: this is our own echo, skip
4. Compare both systems' updated_at for conflict detection:
   - If only one changed since last sync: apply change to the other
   - If both changed: last-write-wins (most recent updated_at takes precedence)
5. Apply update to System B
6. Update bridge record timestamps
7. Log sync action
```

### 7.4 Task Completion

```
FUB task completed:
  → Update bridge record
  → Close Todoist task via POST /tasks/{id}/close

Todoist task completed:
  → Update bridge record
  → PUT /v1/tasks/{id} with isCompleted=true in FUB
```

### 7.5 Deal Stage Change (Section Move)

```
1. Deal cache refresh detects deal.stage_id changed
2. Look up old stage → old Todoist project
3. Look up new stage → new Todoist project
4. Get all task_map records for this deal
5. For each task:
   a. Move Todoist task to new project (same section name, new project)
   b. Update todoist_project_id in bridge
   c. Update todoist_section_id if section was recreated
6. Log move action
```

### 7.6 Anti-Loop Protection

Every write to an external system records the expected `updated_at`:

```python
# After creating/updating in Todoist
bridge.update_mapping(
    mapping_id,
    todoist_updated_at=response.updated_at,  # What we expect to see next poll
    sync_status='synced'
)

# When polling detects a change
if task.updated_at == mapping.todoist_updated_at:
    # This is our own write echoing back, skip it
    continue
```

---

## 8. Deployment

### 8.1 Caddy Configuration (add to existing Caddyfile)

```
# Add to existing Caddy config on VPS
tasksync.yourdomain.com {
    reverse_proxy localhost:8100
}

# OR if using a path on existing domain:
yourdomain.com {
    handle /tasksync/* {
        reverse_proxy localhost:8100
    }
    # ... existing routes ...
}
```

Caddy handles HTTPS certificate automatically via Let's Encrypt.

### 8.2 systemd Service

```ini
# /etc/systemd/system/mydreams-tasksync.service
[Unit]
Description=myDREAMS Todoist-FUB Task Sync Service
After=network.target

[Service]
Type=simple
User=bigeug
WorkingDirectory=/home/bigeug/myDreams
ExecStart=/home/bigeug/myDreams/.venv/bin/python -m modules.task_sync run
EnvironmentFile=/home/bigeug/myDreams/config/.env.prod
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable mydreams-tasksync
sudo systemctl start mydreams-tasksync
sudo journalctl -u mydreams-tasksync -f  # Watch logs
```

### 8.3 Todoist Webhook Registration (One-Time Setup)

1. Go to https://developer.todoist.com/appconsole.html
2. Create a new app (name: "myDREAMS Task Sync")
3. Set the OAuth redirect URL (required even for personal use)
4. In the Webhooks section:
   - Callback URL: `https://tasksync.yourdomain.com/webhook/todoist`
   - Enable events: `item:added`, `item:updated`, `item:completed`, `item:uncompleted`, `item:deleted`
5. Activate the webhook
6. Copy `client_id` and `client_secret` to `.env.prod`
7. Complete the OAuth flow once for your own account to activate webhooks

### 8.4 FUB System Registration (One-Time Setup)

1. Go to https://www.followupboss.com/developer-registration
2. Register system name: "myDREAMS"
3. Receive `X-System-Key`
4. Add to `.env.prod` as `FUB_SYSTEM_KEY`

---

## 9. Dependencies

```
# Python packages (add to requirements.txt or pyproject.toml)
fastapi>=0.100.0
uvicorn>=0.23.0
httpx>=0.24.0
todoist-api-python>=2.1.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

All are pure Python or have well-maintained wheels. No compiled dependencies that would cause issues on the VPS.

---

## 10. Implementation Order

Recommended build sequence — each step is independently testable:

### Phase 1: Foundation
1. `config.py` — environment config loading
2. `db.py` — schema creation, connection management
3. `models.py` — Pydantic data models

### Phase 2: API Clients
4. `fub_client.py` — FUB REST wrapper (can reuse/extend existing myDREAMS FUB code)
5. `todoist_client.py` — Todoist REST + Sync wrapper
6. Test both clients independently: list tasks, create a test task, delete it

### Phase 3: Bridge Layer
7. `bridge.py` — task_map CRUD operations
8. `deal_enrichment.py` — deal cache management

### Phase 4: Sync Engine
9. `sync_engine.py` — core sync logic
10. `poller.py` — async polling loops
11. Test with `sync-once` command: verify one-shot FUB→Todoist and Todoist→FUB

### Phase 5: Setup & Deployment
12. `setup_wizard.py` — interactive pipeline mapping
13. `api.py` — FastAPI webhook endpoint
14. `__main__.py` — CLI entry point
15. systemd service + Caddy config on VPS

### Phase 6: Polish
16. Error retry logic
17. Monitoring/alerting (email notifications on persistent errors)
18. Integration with existing myDREAMS notification system

---

## 11. Open Questions / Future Considerations

1. **Task descriptions/notes:** FUB tasks have limited description support. Todoist has rich descriptions and comments. Decide what to do with Todoist description content — sync as FUB note? Truncate?

2. **Recurring tasks:** Todoist supports recurring due dates natively. FUB does not. Strategy for recurring tasks needs to be defined.

3. **Assignee mapping:** If Joseph eventually has team members, Todoist collaborators would need to map to FUB users. For now, single-user is fine.

4. **Existing FUB tasks:** Initial migration strategy — do a one-time import of all existing FUB tasks into Todoist during setup? Or start fresh?

5. **Property data enrichment:** Since myDREAMS already has rich property data from Redfin/PropStream, task descriptions in Todoist could be auto-enriched with property details (price, sqft, etc.).

6. **Notification integration:** Hook into existing myDREAMS email notification system for sync errors or tasks needing manual deal association.

7. **Todoist template projects:** Create template task lists for common deal workflows (e.g., "Buyer Under Contract Checklist") that get stamped into a new section when a deal is created.

---

## 12. Reference Links

- **Todoist REST API v2 Docs:** https://developer.todoist.com/rest/v2/
- **Todoist Sync API v1 Docs:** https://developer.todoist.com/api/v1/
- **Todoist App Console:** https://developer.todoist.com/appconsole.html
- **Todoist Python SDK:** https://github.com/Doist/todoist-api-python
- **FUB API Docs:** https://docs.followupboss.com/reference/getting-started
- **FUB Developer Registration:** https://www.followupboss.com/developer-registration
- **FUB Task Endpoints:** https://docs.followupboss.com/reference/tasks-get
- **FUB Deal Endpoints:** https://docs.followupboss.com/reference/deals-get
- **myDREAMS Repo:** https://github.com/ipJoseph/myDREAMS.git
