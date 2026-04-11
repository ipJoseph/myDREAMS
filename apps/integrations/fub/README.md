# FUB Adapter

Wraps `apps/fub-core/src/fub_core/FUBClient` in the adapter pattern defined
in `apps/integrations/_base/`. This is the ONLY path through which myDREAMS
code should talk to Follow Up Boss.

## What this adapter does

- **Creates events** (`create_event`) — posts to FUB's `/v1/events` endpoint.
  This is the single entry point for pushing any website activity, inquiry,
  or behavioral signal into FUB. Auto-creates the person via FUB's built-in
  dedup (email or phone).
- **Creates notes** (`create_note`) — posts to `/v1/notes`. Used for adding
  free-text context to an existing person.
- **Healthcheck** (`healthcheck`) — checks FUB reachability via the `/me`
  endpoint.

## What this adapter does NOT do

- **Does not read data from FUB.** Reads still go through the legacy
  `apps/fub-to-sheets` path (until Phase G0 rewrites it into `apps/sync/fub_pull.py`).
  That's intentional — the adapter is for the new inverted architecture where
  myDREAMS pushes data TO FUB. Reads are a separate concern.
- **Does not maintain local cache.** Every call hits the network. If you
  want caching, wrap the adapter.
- **Does not own scoring.** Scoring happens in `apps/scoring/` against
  dreams.db. This adapter only pushes the events that scoring reads from.

## Configuration

Requires these environment variables:

| Variable | Required | Default | What it does |
|---|---|---|---|
| `FUB_API_KEY` | Yes for real calls | unset | Your FUB API key. Basic-auth username, blank password. |
| `FUB_BASE_URL` | No | `https://api.followupboss.com/v1` | Override for testing against a sandbox. |
| `FUB_SYSTEM_NAME` | No | `myDREAMS` | Sent as the `system` field on every event for attribution in FUB. |

When `FUB_API_KEY` is not set, `is_configured()` returns `False` and all
write methods return `AdapterResult.skip()`. The caller sees a successful
result but no network call happens. This is how the system survives a
credential outage: local DB writes still succeed, FUB pushes queue for retry.

## Usage from the conductor

```python
from apps.integrations.fub import FUBAdapter

fub = FUBAdapter.from_env()

# Phase B1: contact form submission
result = fub.create_event(
    event_type="General Inquiry",
    person={
        "firstName": "Jane",
        "lastName": "Doe",
        "emails": [{"value": "jane@example.com"}],
        "phones": [{"value": "828-555-1234"}],
    },
    message="I'm interested in your Franklin listings",
    source="wncmountain.homes",
)
if not result.ok and not result.skipped:
    logger.warning("FUB push failed: %s", result.error)
    # Local DB write still succeeded — the lead is captured, just not in FUB yet.

# Phase C: property view event
result = fub.create_event(
    event_type="Viewed Property",
    person={"emails": [{"value": "jane@example.com"}]},
    property={
        "street": "123 Mountain Rd",
        "city": "Franklin",
        "state": "NC",
        "code": "28734",
        "mlsNumber": "NCM12345",
        "price": 450000,
        "bedrooms": 3,
        "bathrooms": 2,
    },
    source="wncmountain.homes",
)
```

## Testing

```bash
# From repo root
python3 -m pytest apps/integrations/fub/tests/ -v
```

The smoke tests use a `MockFUBClient` — no real FUB credentials needed.

## How to swap this out

If FUB is ever replaced (with, say, HubSpot or a custom CRM), the steps are:

1. Create `apps/integrations/<new_vendor>/` with the same public contract:
   `is_configured()`, `healthcheck()`, `create_event()`, `create_note()`.
2. Change imports in the conductor:
   - `apps/property-api/routes/public_writes.py`
   - `apps/property-api/routes/...` (event endpoint in Phase C)
   - `apps/scoring/fub_push.py` (once Phase G0 lands)
3. Delete this directory and `apps/fub-core/`.

If we're disciplined about the adapter contract, the conductor code shouldn't
need substantive changes — just the import statements.
