"""
Abstract base class for vendor adapters.

Every adapter (FUB, JustCall, etc.) should inherit from `Adapter` and
implement at minimum `is_configured()` and `healthcheck()`. Adapters then
add vendor-specific methods like `create_event()`, `place_call()`, etc.

The base class provides:
  - A standard `AdapterResult` return type so callers can branch on
    success/failure without catching exceptions.
  - A common shape for `healthcheck()` results.
  - A default `__repr__` that includes the configured-state, useful in
    logs and `/health` endpoints.

Subclasses MUST NOT make network calls in `__init__`. Network calls happen
inside method bodies, never during construction. This keeps adapters cheap
to instantiate (the property-api creates one per request).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AdapterResult:
    """
    Standard return type for adapter write methods.

    Callers branch on `ok`. When `ok=False`, `error` is a short human-readable
    message and `error_code` is a machine-readable enum-like string.

    `data` carries the vendor's response body (or a structured summary of it)
    when present, so callers that need the vendor-assigned ID can read it
    without re-parsing.

    `skipped` is True when the adapter was not configured and the call was
    deliberately bypassed. `ok` is also True in that case so callers don't
    treat it as a failure.
    """

    ok: bool
    skipped: bool = False
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    audit_id: Optional[int] = None

    @classmethod
    def success(cls, data: Optional[Dict[str, Any]] = None,
                audit_id: Optional[int] = None) -> "AdapterResult":
        return cls(ok=True, data=data, audit_id=audit_id)

    @classmethod
    def skip(cls, reason: str) -> "AdapterResult":
        """Return a successful result that did not actually call the vendor."""
        return cls(ok=True, skipped=True, error=reason, error_code="SKIPPED")

    @classmethod
    def failure(cls, error: str, error_code: str = "ERROR",
                audit_id: Optional[int] = None) -> "AdapterResult":
        return cls(ok=False, error=error, error_code=error_code, audit_id=audit_id)


class Adapter:
    """
    Base class for vendor adapters.

    Subclasses must override `is_configured()` and `healthcheck()`. Everything
    else is optional.
    """

    #: Short, lowercase vendor name (e.g. "fub", "justcall"). Subclasses set this.
    name: str = "base"

    def is_configured(self) -> bool:
        """
        Return True iff this adapter has all credentials and configuration
        needed to actually call the vendor API.

        The conductor uses this to decide whether to invoke writes at all.
        When False, write methods should return `AdapterResult.skip()` and
        do nothing else — local DB writes still happen, the system survives.
        """
        raise NotImplementedError

    def healthcheck(self) -> Dict[str, Any]:
        """
        Return a dict suitable for inclusion in a /health JSON response.

        Required keys: `name`, `ok`, `configured`. Optional: `detail`.

        `ok` should reflect whether the adapter can currently reach the
        vendor — implementations may make a cheap test call (e.g., GET /me).
        `configured` is the cheap synchronous answer from `is_configured()`.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} configured={self.is_configured()}>"
