
Concretely:
1, SQLite now, Postgres later
2. Canonical models for vendors, leads, deals
3. External IDs tie everything back to FUB
4. Sync flows are explicit and directional

Your existing FUB-to-Sheets code already understands:
1. FUB auth
2. pagination
3. rate limits
4. data quirks

We will reuse that, not fight it. The correct next step, one thing only

Before we touch deals or leads, we need to extract the shared FUB logic so we are not duplicating or entangling code.

Next step: create a shared FUB core library

Goal:
1. One place that knows how to talk to FUB
2. Used by vendor sync later
3. Used by deals workbench
4. Used by leads workbench
5. Potentially used by Sheets exporters
