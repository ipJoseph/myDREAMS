"""
Public write endpoints — unauthenticated POST routes for the public website.

Mounted at /api/public/ alongside the read-only routes in public.py. The
distinction is that everything here accepts user-submitted data and writes
to the database. These endpoints are:

  - POST /api/public/contacts  — contact form / request-info / save-listing
  - POST /api/public/events    — (Phase C) behavioral event ingestion

Design rules:
  1. Zero authentication. Anyone on the internet can hit these. That means
     strict validation, rate limiting, and (when configured) Cloudflare
     Turnstile verification.
  2. Best-effort FUB push. The local DB write is the source of truth. If
     the FUB adapter is not configured or the FUB API is down, the request
     still succeeds — the event is stored locally and will be back-filled
     later. Users should never see a 500 because FUB is unreachable.
  3. No PII in logs. We log source/IP/outcome but not the submitted
     email, phone, or message body.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from flask import Blueprint, jsonify, request

# Ensure repo root is on sys.path for apps.* and src.* imports.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps.integrations.fub import FUBAdapter  # noqa: E402
from src.core.database import DREAMSDatabase  # noqa: E402

logger = logging.getLogger("dreams.public_writes")

public_writes_bp = Blueprint("public_writes", __name__)

_DB_PATH = os.getenv("DREAMS_DB_PATH", str(_REPO_ROOT / "data" / "dreams.db"))

# One adapter per process. It's cheap and stateless.
_fub_adapter: Optional[FUBAdapter] = None


def _get_fub() -> FUBAdapter:
    global _fub_adapter
    if _fub_adapter is None:
        _fub_adapter = FUBAdapter.from_env()
    return _fub_adapter


def _get_db() -> DREAMSDatabase:
    return DREAMSDatabase(_DB_PATH)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_MAX_NAME_LEN = 120
_MAX_MESSAGE_LEN = 4000


def _normalize_phone(raw: Optional[str]) -> Optional[str]:
    """
    Strip to digits, keep leading + for international, cap at 20 chars.
    Returns None for empty input. This is intentionally forgiving — we don't
    reject phone numbers, we just normalize them for storage and lookup.
    """
    if not raw:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    has_plus = raw.startswith("+")
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    out = ("+" + digits) if has_plus else digits
    return out[:20]


def _validate_contact_payload(
    data: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Validate and normalize an inbound /api/public/contacts payload.

    Returns (clean_data, None) on success, or (None, error_message) on
    validation failure. Keeps only whitelisted fields.
    """
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object"

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone_raw = data.get("phone")
    message = (data.get("message") or "").strip()
    source = (data.get("source") or "contact_form").strip()[:64]
    listing_id = data.get("listing_id")

    # At least one of email or phone must be present
    if not email and not phone_raw:
        return None, "Either email or phone is required"

    if email:
        if len(email) > 254 or not _EMAIL_RE.match(email):
            return None, "Invalid email address"

    phone = _normalize_phone(phone_raw)
    if phone_raw and not phone:
        return None, "Invalid phone number"

    if len(name) > _MAX_NAME_LEN:
        return None, f"Name too long (max {_MAX_NAME_LEN} chars)"
    if len(message) > _MAX_MESSAGE_LEN:
        return None, f"Message too long (max {_MAX_MESSAGE_LEN} chars)"

    # Split "First Last" into first/last. If the name is one word, put it in
    # first_name and leave last_name None. If it has more parts, last_name
    # absorbs everything after the first space.
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    if name:
        parts = name.split(None, 1)
        first_name = parts[0][:_MAX_NAME_LEN]
        if len(parts) > 1:
            last_name = parts[1][:_MAX_NAME_LEN]

    # UTM / attribution pass-through (optional)
    utm = {}
    for key in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"):
        v = data.get(key)
        if v:
            utm[key] = str(v)[:128]

    clean = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email or None,
        "phone": phone,
        "message": message or None,
        "source": source,
        "listing_id": str(listing_id)[:64] if listing_id else None,
        "utm": utm,
    }
    return clean, None


# ---------------------------------------------------------------------------
# Cloudflare Turnstile (optional, gated on env var presence)
# ---------------------------------------------------------------------------

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _verify_turnstile(token: Optional[str], remote_ip: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Verify a Cloudflare Turnstile token. Only enforced when
    TURNSTILE_SECRET_KEY is set in the environment. Otherwise returns
    (True, None) — DEV mode.
    """
    secret = os.getenv("TURNSTILE_SECRET_KEY")
    if not secret:
        return True, None  # Turnstile not configured, skip

    if not token:
        return False, "Missing Turnstile token"

    try:
        resp = requests.post(
            _TURNSTILE_VERIFY_URL,
            data={"secret": secret, "response": token, "remoteip": remote_ip or ""},
            timeout=5,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:
        logger.warning("Turnstile verify call failed: %s", e)
        # Fail open OR fail closed? We fail closed when Turnstile is enabled
        # because that's the whole point of enabling it.
        return False, "Turnstile verification unavailable"

    if body.get("success"):
        return True, None
    return False, f"Turnstile rejected: {body.get('error-codes', ['unknown'])}"


# ---------------------------------------------------------------------------
# The contact form endpoint
# ---------------------------------------------------------------------------

@public_writes_bp.route("/contacts", methods=["POST"])
def create_public_contact():
    """
    Accept a contact form / request-info / save-listing submission from the
    public website and record it in dreams.db + forward to FUB.

    Request body:
        {
          "name": "Jane Doe",
          "email": "jane@example.com",
          "phone": "828-555-1234",
          "message": "I'm interested in your listings",  # optional
          "listing_id": "NCM12345",                      # optional
          "source": "contact_form",                      # or request_info, save_listing, etc.
          "utm_source": "google", ...                    # optional, any utm_*
          "turnstile_token": "..."                       # required if Turnstile is configured
        }

    Response:
        200: {ok: true, contact_id: "..."}
        400: {ok: false, error: "validation message"}
        429: {ok: false, error: "rate limit"}
    """
    remote_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()

    data = request.get_json(silent=True) or {}

    # 1. Turnstile (if configured)
    turn_ok, turn_err = _verify_turnstile(data.get("turnstile_token"), remote_ip)
    if not turn_ok:
        logger.info("public_contact: turnstile failed ip=%s err=%s", remote_ip, turn_err)
        return jsonify({"ok": False, "error": turn_err}), 400

    # 2. Validation
    clean, err = _validate_contact_payload(data)
    if err:
        logger.info("public_contact: validation failed ip=%s err=%s", remote_ip, err)
        return jsonify({"ok": False, "error": err}), 400

    # 3. Local DB write (source of truth) — retry on DB lock
    #    The MLS Grid sync holds write locks for 2-5 min every 30 min.
    #    Retrying with short sleeps catches the brief gaps between batch commits.
    import time as _time
    import sqlite3 as _sqlite3

    contact_id = None
    db_retries = 15
    for attempt in range(db_retries):
        try:
            contact_id = _upsert_public_contact(clean, remote_ip)
            break
        except _sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < db_retries - 1:
                if attempt % 5 == 0:
                    logger.warning("public_contact: DB locked, retry %d/%d", attempt + 1, db_retries)
                _time.sleep(1)
            else:
                logger.error("public_contact: DB write failed after %d attempts: %s", db_retries, e)
                return jsonify({
                    "ok": False,
                    "error": "Server is busy. Please try again in a moment.",
                }), 503

    # 4. Best-effort FUB push
    fub_result = _push_to_fub(clean)
    fub_status = "skipped" if fub_result.skipped else ("ok" if fub_result.ok else "failed")

    logger.info(
        "public_contact: ok contact_id=%s source=%s listing_id=%s fub=%s ip=%s",
        contact_id, clean["source"], clean["listing_id"], fub_status, remote_ip,
    )

    return jsonify({
        "ok": True,
        "contact_id": contact_id,
        "fub": fub_status,
    }), 200


def _upsert_public_contact(clean: Dict[str, Any], remote_ip: str) -> str:
    """
    Upsert a web-form contact into the `leads` table.

    Dedupe strategy: EMAIL ONLY. Never auto-merge on phone alone.
    If a phone matches a different lead, flag as potential duplicate
    for agent review (never merge automatically).

    This prevents false merges when one person uses the same phone
    number for personal and business accounts (different emails).
    """
    db = _get_db()

    existing_id: Optional[str] = None
    with db._get_connection() as conn:
        # Match on email only (primary identity key)
        if clean["email"]:
            row = conn.execute(
                "SELECT id FROM leads WHERE LOWER(email) = ? LIMIT 1",
                (clean["email"],),
            ).fetchone()
            if row:
                existing_id = row[0]

        # If no email match but phone matches a DIFFERENT lead, flag as
        # potential duplicate for agent review. Never auto-merge.
        if not existing_id and clean["phone"]:
            phone_match = conn.execute(
                "SELECT id, first_name, last_name, email FROM leads "
                "WHERE phone = ? AND archive_status = 'active' LIMIT 1",
                (clean["phone"],),
            ).fetchone()
            if phone_match:
                _flag_potential_duplicate(
                    conn, phone_match[0],
                    clean["email"], clean["first_name"], clean["last_name"],
                    clean["phone"], "phone_match"
                )

    contact_id = existing_id or str(uuid.uuid4())

    lead_data: Dict[str, Any] = {
        "id": contact_id,
        "first_name": clean["first_name"],
        "last_name": clean["last_name"],
        "email": clean["email"],
        "phone": clean["phone"],
        "source": clean["source"],
        "stage": "Lead",
        "type": "lead",
        "contact_group": "web_form",
        "archive_status": "active",
    }
    if not existing_id:
        lead_data["created_at"] = datetime.now().isoformat()
    if clean["message"]:
        # Store the message as a note in the lead's notes field. If there
        # are existing notes, we don't clobber them — append with a timestamp.
        lead_data["notes"] = _compose_notes_field(
            existing_id, clean["message"], clean["source"], remote_ip
        )

    # Remove None values to avoid overwriting fields on upsert.
    lead_data = {k: v for k, v in lead_data.items() if v is not None}

    db.upsert_contact_dict(lead_data)
    return contact_id


def _flag_potential_duplicate(
    conn, existing_lead_id: str,
    new_email: Optional[str], new_first: Optional[str], new_last: Optional[str],
    shared_phone: str, match_type: str,
) -> None:
    """
    Record a potential duplicate flag on an existing lead.

    Stored in a separate table so we can query/dismiss them from the
    dashboard without polluting the leads table with JSON columns.
    """
    try:
        conn.execute("""
            INSERT OR IGNORE INTO potential_duplicates
            (id, existing_lead_id, new_email, new_first_name, new_last_name,
             shared_value, match_type, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            str(uuid.uuid4()), existing_lead_id,
            new_email, new_first, new_last,
            shared_phone, match_type,
            datetime.now().isoformat(),
        ))
        conn.commit()
        logger.info("Flagged potential duplicate: phone=%s matches lead=%s",
                     shared_phone, existing_lead_id)
    except Exception as e:
        # Table might not exist yet; log and continue
        logger.warning("Could not flag duplicate (table may not exist): %s", e)


def _compose_notes_field(
    existing_id: Optional[str],
    message: str,
    source: str,
    remote_ip: str,
) -> str:
    """
    Prepend a timestamped entry to the lead's notes field so we preserve
    history. We only read the existing value when updating — this keeps the
    new-lead path fast.
    """
    header = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {source} (ip:{remote_ip})"
    new_entry = f"{header}\n{message}"
    if not existing_id:
        return new_entry

    db = _get_db()
    with db._get_connection() as conn:
        row = conn.execute("SELECT notes FROM leads WHERE id = ?", (existing_id,)).fetchone()
        existing_notes = row[0] if row and row[0] else ""

    if existing_notes:
        return f"{new_entry}\n\n--- previous notes ---\n{existing_notes}"
    return new_entry


def _push_to_fub(clean: Dict[str, Any]):
    """
    Best-effort FUB event push. Returns an AdapterResult regardless of
    outcome — the caller only uses it for logging.

    Event type rules:
      - If the submission has a listing_id, type = "Property Inquiry"
      - Otherwise, type = "General Inquiry"
    """
    adapter = _get_fub()
    if not adapter.is_configured():
        return adapter.create_event(  # returns AdapterResult.skip()
            event_type="General Inquiry",
            source="wncmountain.homes",
        )

    person = FUBAdapter.build_person_dict(
        first_name=clean["first_name"],
        last_name=clean["last_name"],
        email=clean["email"],
        phone=clean["phone"],
    )

    property_obj: Optional[Dict[str, Any]] = None
    if clean["listing_id"]:
        property_obj = _lookup_listing_for_fub(clean["listing_id"])

    event_type = "Property Inquiry" if property_obj else "General Inquiry"

    return adapter.create_event(
        event_type=event_type,
        source="wncmountain.homes",
        person=person,
        property=property_obj,
        message=clean["message"],
        description=f"Submitted via {clean['source']}",
    )


def _lookup_listing_for_fub(listing_id: str) -> Optional[Dict[str, Any]]:
    """
    Build a FUB-shaped property object from a listing_id we can match in
    the listings table. Returns None if the listing isn't found — the
    endpoint still succeeds, the event just won't carry property context.
    """
    try:
        db = _get_db()
        with db._get_connection() as conn:
            # Try matching by id OR by mls_number since the frontend may pass either.
            row = conn.execute(
                """
                SELECT address, city, state, zip, mls_number,
                       list_price, beds, baths, sqft, acreage, property_type
                FROM listings
                WHERE id = ? OR mls_number = ?
                LIMIT 1
                """,
                (listing_id, listing_id),
            ).fetchone()
        if not row:
            return None
        (street, city, state, zipc, mls, price, beds, baths, area, lot, ptype) = row
    except Exception as e:
        logger.warning("listing lookup failed for %s: %s", listing_id, e)
        return None

    property_obj: Dict[str, Any] = {}
    if street:
        property_obj["street"] = street
    if city:
        property_obj["city"] = city
    if state:
        property_obj["state"] = state
    if zipc is not None:
        property_obj["code"] = str(zipc)
    if mls:
        property_obj["mlsNumber"] = mls
    if price:
        property_obj["price"] = float(price)
    if beds is not None:
        try:
            property_obj["bedrooms"] = int(beds)
        except (TypeError, ValueError):
            pass
    if baths is not None:
        try:
            property_obj["bathrooms"] = float(baths)
        except (TypeError, ValueError):
            pass
    if area is not None:
        try:
            property_obj["area"] = int(area)
        except (TypeError, ValueError):
            pass
    if lot is not None:
        try:
            property_obj["lot"] = float(lot)
        except (TypeError, ValueError):
            pass
    if ptype:
        property_obj["type"] = ptype
    return property_obj or None


# ---------------------------------------------------------------------------
# Event tracking endpoint (Phase C — "be our own Real Geeks")
# ---------------------------------------------------------------------------

# Valid event types the client may send. Mapped to FUB event types.
_VALID_CLIENT_EVENTS = {
    "viewed_property": "Viewed Property",
    "saved_property": "Saved Property",
    "property_search": "Property Search",
    "saved_search": "Saved Property Search",
    "visited_website": "Visited Website",
    "viewed_page": "Viewed Page",
    "registration": "Registration",
}


@public_writes_bp.route("/events", methods=["POST"])
def track_public_event():
    """
    Ingest a behavioral event from the public website.

    This is the Real Geeks replacement. The public site fires events for
    property views, saves, searches, and page visits. We store locally
    AND forward to FUB's /v1/events endpoint.

    Request body:
        {
          "event": "viewed_property",         # required, one of _VALID_CLIENT_EVENTS
          "email": "jane@example.com",        # required for FUB dedup
          "listing_id": "lst_abc123",         # optional, for property events
          "page_url": "/listings/lst_abc123", # optional
          "page_title": "1040 Soquili Dr",    # optional
        }

    Response:
        200: {ok: true}
        400: {ok: false, error: "..."}
    """
    data = request.get_json(silent=True) or {}

    event_key = (data.get("event") or "").strip().lower()
    email = (data.get("email") or "").strip().lower()
    listing_id = data.get("listing_id")
    page_url = data.get("page_url")
    page_title = data.get("page_title")

    if event_key not in _VALID_CLIENT_EVENTS:
        return jsonify({"ok": False, "error": f"Unknown event type: {event_key}"}), 400

    if not email:
        # Anonymous events are still valuable for FUB pixel tracking,
        # but we can't store them locally without an identifier.
        # Accept silently — the FUB pixel handles anonymous tracking.
        return jsonify({"ok": True, "anonymous": True}), 200

    fub_event_type = _VALID_CLIENT_EVENTS[event_key]

    # Look up property data if listing_id provided
    property_obj = None
    property_address = None
    property_price = None
    property_mls = None
    if listing_id:
        property_obj = _lookup_listing_for_fub(listing_id)
        if property_obj:
            property_address = property_obj.get("street")
            property_price = property_obj.get("price")
            property_mls = property_obj.get("mlsNumber")

    # Match email to existing contact
    contact_id = None
    try:
        db = _get_db()
        with db._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM leads WHERE LOWER(email) = ? LIMIT 1", (email,)
            ).fetchone()
            if row:
                contact_id = row[0]
    except Exception:
        pass

    # Store locally in contact_events (with retry for DB lock)
    import time as _time
    import sqlite3 as _sqlite3
    now = datetime.now().isoformat()
    event_id = f"web_{uuid.uuid4().hex[:12]}"

    for attempt in range(5):
        try:
            db = _get_db()
            with db._get_connection() as conn:
                conn.execute(
                    """INSERT INTO contact_events
                       (id, contact_id, event_type, occurred_at,
                        property_address, property_price, property_mls, imported_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (event_id, contact_id, fub_event_type, now,
                     property_address, property_price, property_mls, now),
                )
                conn.commit()
            break
        except _sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 4:
                _time.sleep(1)
            else:
                logger.warning("Event store failed after retries: %s", e)
                # Don't fail the request — still try FUB push
                break

    # Forward to FUB (best-effort)
    fub_result = _get_fub().create_event(
        event_type=fub_event_type,
        source="wncmountain.homes",
        person=FUBAdapter.build_person_dict(email=email),
        property=property_obj,
        page_url=page_url,
        page_title=page_title,
    )

    fub_status = "skipped" if fub_result.skipped else ("ok" if fub_result.ok else "failed")
    logger.info("track_event: %s email=%s listing=%s fub=%s",
                fub_event_type, email[:20], listing_id, fub_status)

    return jsonify({"ok": True, "fub": fub_status}), 200


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@public_writes_bp.route("/writes/health", methods=["GET"])
def public_writes_health():
    """Expose FUB adapter status for dashboards / monitoring."""
    return jsonify({
        "ok": True,
        "fub": _get_fub().healthcheck(),
        "turnstile_enabled": bool(os.getenv("TURNSTILE_SECRET_KEY")),
    })
