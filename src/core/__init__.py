"""
DREAMS Core Package

Business logic for the DREAMS platform:
- Database operations
- Lead scoring
- Activity monitoring
- Preference inference
- Buyer-property matching
- Package generation
"""

from src.core.database import DREAMSDatabase
from src.core.matching_engine import MatchingEngine
from src.core.listing_service import ListingService, ListingFilters

__all__ = [
    "DREAMSDatabase",
    "MatchingEngine",
    "ListingService",
    "ListingFilters",
]
