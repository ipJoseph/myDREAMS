# myDREAMS Integrations

Vendor adapters for third-party services. Every integration with an external
system lives here as a focused, independently testable, individually
swap-able package.

## Why this exists

Before the 2026-04-10 pivot, FUB-touching code was scattered across nine
modules and 31 files in the repo. Adding a new vendor (or removing an old one)
meant grepping the entire codebase. The pivot established a single rule:

**The conductor talks to adapters. Adapters talk to vendors. Nothing else.**

`apps/property-api`, `apps/property-dashboard`, the new `apps/scoring`,
`apps/sync`, and `apps/reporting` modules all import from `apps/integrations/<name>`
and never call vendor APIs directly. If you find code outside `apps/integrations/`
making a `requests.post("https://api.someservice.com/...")` call, that's a bug
worth fixing.

## Layout

```
apps/integrations/
├── README.md           ← you are here
├── __init__.py
├── _base/              ← shared adapter primitives (audit, retry, base class)
│   ├── __init__.py
│   └── adapter.py      ← abstract Adapter base class every adapter implements
├── fub/                ← Follow Up Boss adapter
│   ├── README.md
│   ├── __init__.py
│   ├── adapter.py      ← public FUBAdapter class
│   └── tests/
└── justcall/           ← (Phase F) JustCall calls + SMS adapter
    └── ...
```

## Rules for adding a new adapter

When you add a new vendor integration, you MUST:

1. **Put it in its own subdirectory** under `apps/integrations/`
2. **Write a `README.md`** that explains:
   - What this adapter does and what it doesn't
   - What env vars / credentials it needs
   - How to test it without hitting the real vendor (mocks/fixtures)
   - How to swap it out (what would replace it)
3. **Inherit from `_base.Adapter`** so you get the audit-log-then-forward
   pattern for free
4. **Add an `is_configured()` method** that returns True only when the
   adapter has everything it needs to actually call the vendor. The conductor
   checks this before invoking writes — if False, the call is silently skipped
   (the local DB write still succeeds). This is what lets the system survive
   a credential outage.
5. **Add at least one smoke test** in `tests/` that exercises the adapter
   against a fake/mocked client.
6. **Add an entry to this README** under "Active adapters" below.

## Active adapters

| Adapter | Vendor | Status | Phase introduced |
|---|---|---|---|
| `fub` | Follow Up Boss | Active | B1 (2026-04-10) |
| `justcall` | JustCall | Planned | F (pending) |

## The adapter contract

Every adapter exposes (at minimum):

```python
class Adapter:
    def is_configured(self) -> bool:
        """True if this adapter has credentials and can make real calls."""

    def healthcheck(self) -> dict:
        """Return {ok: bool, detail: str} — used by /health endpoints."""
```

Specific adapters add their own write/read methods on top, named after the
vendor's domain language (FUBAdapter has `create_event`, `create_note`;
JustCallAdapter will have `place_call`, `send_sms`).

## The audit-then-forward pattern

Every outbound write to a vendor is logged to a local table BEFORE the
network call. If the vendor is down, the call fails, but the audit row
remains and a retry job can drain it later. This is how we never lose
events even when external services break.

See `_base/adapter.py` for the implementation.
