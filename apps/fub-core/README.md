One shared local operational store + multiple FUB adapters

Concretely:

SQLite now, Postgres later

Canonical models for vendors, leads, deals

External IDs tie everything back to FUB

Sync flows are explicit and directional

Your existing FUB-to-Sheets code already understands:

FUB auth

pagination

rate limits

data quirks

We will reuse that, not fight it.

The correct next step, one thing only

Before we touch deals or leads, we need to extract the shared FUB logic so we are not duplicating or entangling code.

Next step: create a shared FUB core library

Goal:

One place that knows how to talk to FUB

Used by vendor sync later

Used by deals workbench

Used by leads workbench

Potentially used by Sheets exporters
