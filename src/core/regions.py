"""
Regional scope for myDREAMS.

myDREAMS serves Western North Carolina mountain real estate. This module
defines the canonical county scope. Listings outside these counties are
out of business scope and must not be synced, displayed, or stored.

This is the single source of truth. Sync engines, photo manager, dashboard
filters, and audit checks should all import from here rather than
hard-coding county lists.
"""

from typing import Optional


# Primary service area: counties we cover as a first-class market.
WNC_PRIMARY_COUNTIES = frozenset({
    'Cherokee',
    'Graham',
    'Clay',
    'Swain',
    'Macon',
    'Jackson',
    'Haywood',
    'Transylvania',
    'Madison',
    'Buncombe',
    'Henderson',
})

# Extended service area: counties we cover but are not the primary focus.
WNC_EXTENDED_COUNTIES = frozenset({
    'Polk',
    'Rutherford',
    'McDowell',
    'Yancey',
    'Mitchell',
    'Burke',
    'Caldwell',
    'Avery',
})

# Union: all counties we serve. Use this for in-scope checks.
WNC_COUNTIES = WNC_PRIMARY_COUNTIES | WNC_EXTENDED_COUNTIES


def is_in_scope(county: Optional[str]) -> bool:
    """True if the listing's county is part of our service area.

    Returns False for None, empty string, or any county not in WNC_COUNTIES.
    Whitespace is stripped before comparison.
    """
    if not county:
        return False
    return county.strip() in WNC_COUNTIES


def is_primary(county: Optional[str]) -> bool:
    """True if the county is in the primary service area."""
    if not county:
        return False
    return county.strip() in WNC_PRIMARY_COUNTIES


def is_extended(county: Optional[str]) -> bool:
    """True if the county is in the extended (non-primary) service area."""
    if not county:
        return False
    return county.strip() in WNC_EXTENDED_COUNTIES
