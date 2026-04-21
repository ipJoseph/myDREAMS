# HubSpot API — Deep Dive

Research note for myDREAMS. Captures the shape of the HubSpot public API so we can evaluate it for contact sync, pipeline automation, or a future marketplace listing. Sourced from HubSpot's developer docs (pulled 2026-04-20).

---

## 1. Authentication — two doors

| | **Private App token** | **OAuth 2.0** |
|---|---|---|
| **Use when** | Internal integration for a single HubSpot account | Shipping an app others install |
| **Setup** | Create in HubSpot settings, get bearer token | Register app, run Authorization Code flow |
| **Token** | Static bearer | Access token (rotates) + refresh token (1 yr) |
| **Scopes** | Checkbox list at creation | Requested at install, user-granted |

**Endpoints (OAuth):**
- Authorize: `https://app.hubspot.com/oauth/authorize`
- Token: `https://api.hubapi.com/oauth/v1/token`

**Header on every call:**
```
Authorization: Bearer <token>
```

For myDREAMS integrating with our own HubSpot account: Private App token is the right choice.

---

## 2. The CRM object model

Everything hangs off `/crm/v3/objects/{objectType}`. The model has three axes: objects, properties, associations.

### Standard objects
- `contacts` — people
- `companies` — orgs
- `deals` — pipeline opportunities
- `tickets` — service
- `appointments`, `courses`, `carts`, `commerce_payments`, `commerce_subscriptions`
- Engagement activities: `notes`, `emails`, `calls`, `meetings`, `tasks`

### Custom objects
- Define our own types (e.g., `property`, `showing`, `offer`)
- Prefixed with `p_` in GraphQL queries (e.g., `p_property`)
- Same CRUD surface as standard objects

### Associations (the graph edges)
Each association has:
- `associationCategory` — `HUBSPOT_DEFINED` | `INTEGRATOR_DEFINED` | `USER_DEFINED` | `WORK`
- `associationTypeId` — integer identifying the kind of link (e.g., "primary contact on deal")

### Properties (the key-value bag on each object)
- Standard + custom properties
- Types: string, number, date, enumeration, datetime, bool
- Sensitivity tiers: normal, sensitive, highly-sensitive — each tier requires a distinct scope (`*.sensitive.read.v2`, `*.highly_sensitive.read.v2`)

---

## 3. Core endpoint shapes

```
GET    /crm/v3/objects/{type}                # list
GET    /crm/v3/objects/{type}/{id}           # read
POST   /crm/v3/objects/{type}                # create
PATCH  /crm/v3/objects/{type}/{id}           # update
DELETE /crm/v3/objects/{type}/{id}           # archive
POST   /crm/v3/objects/{type}/search         # filtered search
POST   /crm/v3/objects/{type}/batch/create   # batch, up to 100
POST   /crm/v3/objects/{type}/batch/read
POST   /crm/v3/objects/{type}/batch/update
POST   /crm/v3/objects/{type}/batch/archive
```

Batch endpoints are the workhorse for sync jobs: 100 records per call, results array with per-record errors.

### Create example

```http
POST /crm/v3/objects/contacts
Authorization: Bearer <token>
Content-Type: application/json

{
  "properties": {
    "email": "buyer@example.com",
    "firstname": "Jane",
    "lastname": "Buyer"
  },
  "associations": [
    {
      "to": { "id": "12345" },
      "types": [
        { "associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 1 }
      ]
    }
  ]
}
```

### Response envelope (shared across create/read/update)
```json
{
  "id": "12345",
  "properties": { "...": "..." },
  "createdAt": "2026-04-20T12:00:00Z",
  "updatedAt": "2026-04-20T12:00:00Z",
  "archived": false
}
```

---

## 4. Search API — how we actually query

`POST /crm/v3/objects/{type}/search`

```json
{
  "filterGroups": [{
    "filters": [
      { "propertyName": "lifecyclestage", "operator": "EQ", "value": "lead" }
    ]
  }],
  "sorts": [{ "propertyName": "createdate", "direction": "DESCENDING" }],
  "properties": ["email", "firstname", "lastname", "phone"],
  "limit": 100,
  "after": "cursor"
}
```

**Gotchas:**
- Cursor pagination (not offset); use `paging.next.after` from the response
- Separate rate bucket from CRUD (~5 req/sec)
- Hard ceiling at 10,000 results per query — page past it by splitting on a monotonically increasing field (e.g., `hs_object_id > last_seen`)
- Filter operators: `EQ`, `NEQ`, `LT`, `LTE`, `GT`, `GTE`, `BETWEEN`, `IN`, `NOT_IN`, `HAS_PROPERTY`, `NOT_HAS_PROPERTY`, `CONTAINS_TOKEN`, `NOT_CONTAINS_TOKEN`

---

## 5. Webhooks & events

- Subscribe to object events (create, update on specific properties, delete) from an app's webhook config
- Payload is batched, ordered within an objectId, signed
- Signature header: `X-HubSpot-Signature-v3` (HMAC-SHA256 of method + URL + body + timestamp)
- Retry: ~10 attempts with exponential backoff on 5xx or timeout
- Events we'd likely care about: `contact.creation`, `contact.propertyChange`, `deal.creation`, `deal.propertyChange`

---

## 6. Rate limits

| Scope | Limit |
|---|---|
| Private apps | 100 req / 10 sec / account |
| OAuth apps | 100 req / 10 sec / account-app combo |
| Search API | ~5 req/sec (separate bucket) |
| Daily cap | Tier-dependent; API add-on raises significantly |

On 429: honor `Retry-After` header. Burst tolerance is small, so a token-bucket limiter on our side is mandatory for any batch work.

---

## 7. Neighboring APIs

- **Marketing** — emails, forms, lists, campaigns
- **Automation** — workflows (programmatic enroll, list membership)
- **CMS / HubDB** — content blocks, tables (only if we use HubSpot-hosted pages)
- **Conversations** — inbox, threads, channel integrations
- **Files** — upload/attach binary assets
- **GraphQL (CRM data)** — read-side query language for HubSpot CMS serverless functions; not a general REST replacement

---

## 8. myDREAMS-specific questions to answer before committing

- **Custom objects for `property` / `showing`:** modeling real estate in HubSpot, associations to contacts, naming collisions between "property" (the object type) and "property" (the key-value attribute concept).
- **Contact sync pattern:** bidirectional sync between our `contacts` table and HubSpot contacts, with webhooks + `hs_object_id` mapping stored on our side.
- **Pipeline/deal mapping:** our LEADS → BUYERS → REQUIREMENTS → PROPERTIES flow onto HubSpot deal stages + automation.
- **Rate limits, batching, retries:** token bucket, backoff, idempotency via `hs_unique_creation_key` or an external dedupe key.
- **Webhook reliability:** signature verification, replay tolerance, ordering, dedupe strategy.
- **Search pagination past 10k:** split strategy when backfilling.
- **Private App vs public app:** only matters if we ever want myDREAMS in the HubSpot marketplace.

---

## References

- HubSpot Developer Docs: https://developers.hubspot.com/docs
- API v3 CRM Objects: https://developers.hubspot.com/docs/api-reference/latest/crm/objects
- OAuth 2.0: https://developers.hubspot.com/docs/api/oauth-quickstart-guide
- Webhooks: https://developers.hubspot.com/docs/api/webhooks
- Public API OpenAPI specs: https://github.com/hubspot/hubspot-public-api-spec-collection
