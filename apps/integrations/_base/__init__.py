"""
Shared primitives for vendor adapters.

Every adapter under apps/integrations/<vendor>/ should inherit from the
Adapter base class defined here so it gets the audit-log-then-forward
pattern, healthcheck contract, and configuration check for free.
"""

from .adapter import Adapter, AdapterResult

__all__ = ["Adapter", "AdapterResult"]
