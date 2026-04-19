"""
FUB adapter.

Wraps fub_core.FUBClient in the apps/integrations/_base/Adapter contract:
is_configured(), healthcheck(), and write methods that return AdapterResult
rather than raising exceptions.

Design notes:
- The adapter is cheap to instantiate. No network calls in __init__.
- When FUB_API_KEY is unset, is_configured() returns False and all writes
  return AdapterResult.skip(). Callers do not need to catch exceptions.
- Audit logging of vendor writes lives inside fub_core.FUBClient (its
  _audit_log method writes to the fub_audit table). We don't duplicate it
  here.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make fub_core importable even when running from unusual cwds.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FUB_CORE_SRC = _REPO_ROOT / "apps" / "fub-core" / "src"
if str(_FUB_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_FUB_CORE_SRC))

from fub_core.client import FUBClient  # noqa: E402
from fub_core.exceptions import FUBAPIError  # noqa: E402

from .._base import Adapter, AdapterResult  # noqa: E402

logger = logging.getLogger(__name__)


class FUBAdapter(Adapter):
    """
    Public FUB integration surface.

    Instantiate via `FUBAdapter.from_env()` in normal code. Pass an explicit
    `FUBClient` in tests via `FUBAdapter(client=mock_client)`.
    """

    name = "fub"

    #: Default value for the FUB `system` field — identifies us in FUB's UI.
    DEFAULT_SYSTEM = "myDREAMS"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        system: Optional[str] = None,
        client: Optional[FUBClient] = None,
        is_dev: Optional[bool] = None,
    ):
        """
        Args:
            api_key: FUB API key. If None, is_configured() returns False.
            base_url: Override the FUB base URL (for sandbox testing).
            system: The "system" field sent on events. Defaults to "myDREAMS".
            client: Pre-built FUBClient. Used in tests to inject a mock.
                    If provided, api_key/base_url are ignored.
            is_dev: If True, tags all contacts with DEV_TEST and uses
                    source "localhost" so test data is distinguishable in FUB.
        """
        self.api_key = api_key
        self.base_url = base_url or "https://api.followupboss.com/v1"
        self.system = system or self.DEFAULT_SYSTEM
        self._client_override = client
        self._client: Optional[FUBClient] = None
        self._is_dev = is_dev if is_dev is not None else False

    @classmethod
    def from_env(cls) -> "FUBAdapter":
        """Build an adapter from environment variables."""
        return cls(
            api_key=os.getenv("FUB_API_KEY"),
            base_url=os.getenv("FUB_BASE_URL"),
            system=os.getenv("FUB_SYSTEM_NAME"),
            is_dev=os.getenv("DREAMS_ENV", "dev").lower() != "prd",
        )

    #: When True, all contacts/events are tagged with DEV_TEST and
    #: source is set to "localhost" so they're distinguishable in FUB.
    _is_dev: bool = False

    def is_configured(self) -> bool:
        """True iff we have an API key (or a pre-built client for tests)."""
        if self._client_override is not None:
            return True
        return bool(self.api_key)

    def _get_client(self) -> FUBClient:
        """Lazily build the underlying FUBClient on first use."""
        if self._client_override is not None:
            return self._client_override
        if self._client is None:
            if not self.api_key:
                raise RuntimeError(
                    "FUBAdapter is not configured — FUB_API_KEY is not set. "
                    "Callers should check is_configured() before invoking writes."
                )
            self._client = FUBClient(
                api_key=self.api_key,
                base_url=self.base_url,
                logger=logger,
            )
        return self._client

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def create_event(
        self,
        event_type: str,
        source: str,
        person: Optional[Dict[str, Any]] = None,
        property: Optional[Dict[str, Any]] = None,
        property_search: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        description: Optional[str] = None,
        page_url: Optional[str] = None,
        page_title: Optional[str] = None,
        page_referrer: Optional[str] = None,
        page_duration: Optional[int] = None,
        occurred_at: Optional[str] = None,
        campaign: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
    ) -> AdapterResult:
        """
        Push an event to FUB's /v1/events endpoint.

        This is the single entry point for:
          - Contact form submissions ("General Inquiry" / "Property Inquiry")
          - Property views / saves / searches (Phase C behavioral signals)
          - Incoming calls or texts from JustCall (Phase F)

        The event auto-creates the person in FUB if they don't already exist
        (dedup on email or phone). No separate person-create call is needed.

        Returns AdapterResult:
          - ok=True, skipped=True when FUB_API_KEY is unset (system keeps running)
          - ok=True with .data containing the FUB event dict on success
          - ok=False with .error set on FUB-side failures
        """
        if not self.is_configured():
            logger.info(
                "FUB adapter not configured, skipping event push "
                "(event_type=%s, source=%s)", event_type, source
            )
            return AdapterResult.skip("FUB_API_KEY not set")

        # DEV tagging: override source and inject DEV_TEST tag so test
        # contacts are easily identifiable (and filterable) in FUB.
        if self._is_dev:
            source = "localhost"
            if person is None:
                person = {}
            existing_tags = person.get("tags", [])
            if "DEV_TEST" not in existing_tags:
                person["tags"] = existing_tags + ["DEV_TEST"]
            logger.debug("DEV mode: source='localhost', added DEV_TEST tag")

        try:
            client = self._get_client()
            result = client.create_event(
                event_type=event_type,
                source=source,
                person=person,
                property=property,
                property_search=property_search,
                message=message,
                description=description,
                system=self.system,
                page_url=page_url,
                page_title=page_title,
                page_referrer=page_referrer,
                page_duration=page_duration,
                occurred_at=occurred_at,
                campaign=campaign,
                custom_fields=custom_fields,
            )
        except ValueError as e:
            # Invalid event_type — this is a caller bug, surface it clearly.
            logger.error("Invalid FUB event payload: %s", e)
            return AdapterResult.failure(str(e), error_code="INVALID_EVENT_TYPE")
        except FUBAPIError as e:
            logger.warning("FUB API error during create_event: %s", e)
            return AdapterResult.failure(str(e), error_code="FUB_API_ERROR")
        except Exception as e:
            logger.exception("Unexpected error during FUB create_event")
            return AdapterResult.failure(str(e), error_code="UNEXPECTED")

        if result is None:
            # fub_core returns None on network/HTTP error (it already logged
            # the specifics and wrote to the fub_audit table).
            return AdapterResult.failure(
                "FUB create_event returned None — see fub_audit table for details",
                error_code="FUB_WRITE_FAILED",
            )

        return AdapterResult.success(data=result)

    def create_note(
        self,
        person_id: int,
        body: str,
        user_id: Optional[int] = None,
    ) -> AdapterResult:
        """Create a note on an existing FUB person."""
        if not self.is_configured():
            return AdapterResult.skip("FUB_API_KEY not set")
        try:
            client = self._get_client()
            result = client.create_note(
                person_id=person_id,
                body=body,
                user_id=user_id,
            )
        except Exception as e:
            logger.exception("Unexpected error during FUB create_note")
            return AdapterResult.failure(str(e), error_code="UNEXPECTED")

        if result is None:
            return AdapterResult.failure(
                "FUB create_note returned None — see fub_audit table for details",
                error_code="FUB_WRITE_FAILED",
            )
        return AdapterResult.success(data=result)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def healthcheck(self) -> Dict[str, Any]:
        """
        Try a cheap GET /me to verify the key works and the API is reachable.
        Returns a dict suitable for inclusion in a /health response.
        """
        configured = self.is_configured()
        result = {
            "name": self.name,
            "configured": configured,
            "ok": False,
        }
        if not configured:
            result["detail"] = "FUB_API_KEY not set"
            return result
        try:
            user = self._get_client().fetch_current_user()
            if user:
                result["ok"] = True
                result["detail"] = f"authenticated as {user.get('name', 'unknown')}"
            else:
                result["detail"] = "GET /me returned empty response"
        except Exception as e:
            result["detail"] = f"healthcheck failed: {e}"
        return result

    # ------------------------------------------------------------------
    # Convenience constructors for the contact form use case
    # ------------------------------------------------------------------

    @staticmethod
    def build_person_dict(
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        tags: Optional[List[str]] = None,
        stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build the person sub-object for create_event.

        FUB expects emails and phones as lists of {"value": "..."} dicts.
        This helper spares callers from remembering that shape.
        """
        person: Dict[str, Any] = {}
        if first_name:
            person["firstName"] = first_name
        if last_name:
            person["lastName"] = last_name
        if email:
            person["emails"] = [{"value": email}]
        if phone:
            person["phones"] = [{"value": phone}]
        if tags:
            person["tags"] = tags
        if stage:
            person["stage"] = stage
        return person
