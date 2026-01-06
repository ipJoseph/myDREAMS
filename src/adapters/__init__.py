"""
DREAMS Adapters Package

This package contains adapters for integrating with external systems:
- CRM systems (Follow Up Boss, Salesforce, Sierra, etc.)
- Property data sources (Zillow, MLS, ScraperAPI)
- Presentation layers (Notion, Airtable, Google Sheets)
"""

from src.adapters.base_adapter import (
    CRMAdapter,
    PropertyAdapter,
    PresentationAdapter,
    Lead,
    Activity,
    Property,
    Match,
)

__all__ = [
    "CRMAdapter",
    "PropertyAdapter", 
    "PresentationAdapter",
    "Lead",
    "Activity",
    "Property",
    "Match",
]
