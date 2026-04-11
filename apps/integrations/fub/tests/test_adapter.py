"""
Smoke tests for apps.integrations.fub.FUBAdapter.

These tests do NOT hit a real FUB instance. They use a mock FUBClient
injected into the adapter. The goal is to exercise the adapter's public
contract — not to re-test fub_core's HTTP handling.

Run from repo root:
    python3 -m pytest apps/integrations/fub/tests/ -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.integrations._base import AdapterResult
from apps.integrations.fub import FUBAdapter


# ---------------------------------------------------------------------------
# is_configured / healthcheck
# ---------------------------------------------------------------------------

def test_not_configured_without_api_key(monkeypatch):
    monkeypatch.delenv("FUB_API_KEY", raising=False)
    adapter = FUBAdapter.from_env()
    assert adapter.is_configured() is False


def test_configured_with_api_key(monkeypatch):
    monkeypatch.setenv("FUB_API_KEY", "test-key")
    adapter = FUBAdapter.from_env()
    assert adapter.is_configured() is True


def test_configured_with_injected_client():
    adapter = FUBAdapter(client=MagicMock())
    assert adapter.is_configured() is True


# ---------------------------------------------------------------------------
# create_event: the main write path
# ---------------------------------------------------------------------------

def test_create_event_skipped_when_not_configured():
    adapter = FUBAdapter(api_key=None)
    result = adapter.create_event(
        event_type="General Inquiry",
        source="wncmountain.homes",
        person=FUBAdapter.build_person_dict(email="jane@example.com"),
        message="hello",
    )
    assert result.ok is True
    assert result.skipped is True
    assert result.error_code == "SKIPPED"


def test_create_event_success_returns_data():
    mock_client = MagicMock()
    mock_client.create_event.return_value = {"id": 42, "type": "General Inquiry"}
    adapter = FUBAdapter(client=mock_client)

    result = adapter.create_event(
        event_type="General Inquiry",
        source="wncmountain.homes",
        person=FUBAdapter.build_person_dict(
            first_name="Jane",
            email="jane@example.com",
        ),
        message="interested in your listings",
    )

    assert result.ok is True
    assert result.skipped is False
    assert result.data == {"id": 42, "type": "General Inquiry"}

    # Verify the adapter passed through the right arguments.
    call_kwargs = mock_client.create_event.call_args.kwargs
    assert call_kwargs["event_type"] == "General Inquiry"
    assert call_kwargs["source"] == "wncmountain.homes"
    assert call_kwargs["system"] == "myDREAMS"
    assert call_kwargs["message"] == "interested in your listings"
    assert call_kwargs["person"]["firstName"] == "Jane"
    assert call_kwargs["person"]["emails"] == [{"value": "jane@example.com"}]


def test_create_event_none_result_is_failure():
    """fub_core returns None on HTTP error; adapter must surface that as failure."""
    mock_client = MagicMock()
    mock_client.create_event.return_value = None
    adapter = FUBAdapter(client=mock_client)

    result = adapter.create_event(
        event_type="General Inquiry",
        source="wncmountain.homes",
        person=FUBAdapter.build_person_dict(email="jane@example.com"),
    )

    assert result.ok is False
    assert result.error_code == "FUB_WRITE_FAILED"


def test_create_event_invalid_type_is_failure():
    mock_client = MagicMock()
    mock_client.create_event.side_effect = ValueError("Invalid event_type 'Bogus'")
    adapter = FUBAdapter(client=mock_client)

    result = adapter.create_event(
        event_type="Bogus",
        source="wncmountain.homes",
    )

    assert result.ok is False
    assert result.error_code == "INVALID_EVENT_TYPE"


def test_create_event_exception_is_failure():
    mock_client = MagicMock()
    mock_client.create_event.side_effect = RuntimeError("network exploded")
    adapter = FUBAdapter(client=mock_client)

    result = adapter.create_event(
        event_type="General Inquiry",
        source="wncmountain.homes",
    )

    assert result.ok is False
    assert result.error_code == "UNEXPECTED"
    assert "network exploded" in result.error


# ---------------------------------------------------------------------------
# build_person_dict helper
# ---------------------------------------------------------------------------

def test_build_person_dict_all_fields():
    person = FUBAdapter.build_person_dict(
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        phone="828-555-1234",
        tags=["EUG", "Web Lead"],
        stage="Lead",
    )
    assert person == {
        "firstName": "Jane",
        "lastName": "Doe",
        "emails": [{"value": "jane@example.com"}],
        "phones": [{"value": "828-555-1234"}],
        "tags": ["EUG", "Web Lead"],
        "stage": "Lead",
    }


def test_build_person_dict_omits_nones():
    person = FUBAdapter.build_person_dict(email="jane@example.com")
    assert person == {"emails": [{"value": "jane@example.com"}]}


# ---------------------------------------------------------------------------
# create_note
# ---------------------------------------------------------------------------

def test_create_note_skipped_when_not_configured():
    adapter = FUBAdapter(api_key=None)
    result = adapter.create_note(person_id=1, body="hello")
    assert result.skipped is True


def test_create_note_success():
    mock_client = MagicMock()
    mock_client.create_note.return_value = {"id": 99}
    adapter = FUBAdapter(client=mock_client)

    result = adapter.create_note(person_id=1, body="test note")

    assert result.ok is True
    assert result.data == {"id": 99}
    mock_client.create_note.assert_called_once_with(
        person_id=1, body="test note", user_id=None,
    )


# ---------------------------------------------------------------------------
# healthcheck
# ---------------------------------------------------------------------------

def test_healthcheck_reports_not_configured():
    adapter = FUBAdapter(api_key=None)
    hc = adapter.healthcheck()
    assert hc["configured"] is False
    assert hc["ok"] is False
    assert "not set" in hc["detail"]


def test_healthcheck_ok_when_me_returns_user():
    mock_client = MagicMock()
    mock_client.fetch_current_user.return_value = {"name": "Eugy Williams", "id": 123}
    adapter = FUBAdapter(client=mock_client)
    hc = adapter.healthcheck()
    assert hc["configured"] is True
    assert hc["ok"] is True
    assert "Eugy Williams" in hc["detail"]


def test_healthcheck_fails_when_me_raises():
    mock_client = MagicMock()
    mock_client.fetch_current_user.side_effect = RuntimeError("401 Unauthorized")
    adapter = FUBAdapter(client=mock_client)
    hc = adapter.healthcheck()
    assert hc["configured"] is True
    assert hc["ok"] is False
    assert "401" in hc["detail"]
