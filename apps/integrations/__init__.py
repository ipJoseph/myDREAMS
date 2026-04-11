"""
myDREAMS Integrations

Vendor adapters for external services. Every integration with a third party
(FUB, JustCall, Twilio, etc.) lives here as a focused adapter package.

The conductor (property-api, property-dashboard, scoring/reporting code)
talks to adapters via their public interfaces — never directly to vendor APIs.
This is what makes it possible to swap, upgrade, or remove a vendor without
touching the rest of the system.

See the top-level README.md in this directory for the adapter pattern.
"""
