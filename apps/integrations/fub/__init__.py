"""
Follow Up Boss adapter.

Wraps apps/fub-core/src/fub_core/FUBClient in a clean, testable, swappable
interface. See README.md in this directory for the full contract.

Usage:
    from apps.integrations.fub import FUBAdapter

    fub = FUBAdapter.from_env()  # reads FUB_API_KEY from environment
    if fub.is_configured():
        result = fub.create_event(
            event_type="General Inquiry",
            person={"firstName": "Jane", "emails": [{"value": "jane@example.com"}]},
            message="I'm interested in your listings in Franklin NC",
            source="wncmountain.homes",
        )
        if not result.ok:
            logger.warning("FUB push failed: %s", result.error)
"""

from .adapter import FUBAdapter

__all__ = ["FUBAdapter"]
