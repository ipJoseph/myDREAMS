"""
House Tour Schedule PDF Generator

Generates a branded landscape PDF (11x8.5) showing a client-facing showing itinerary.
Each property gets a horizontal card with photo, address, showing time, price, and details.
Break stops (lunch, coffee) get a distinct card style.

Uses WeasyPrint for HTML-to-PDF conversion.
"""

import base64
import json
import os
import re
import sqlite3
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logger.warning("WeasyPrint not installed. PDF generation unavailable.")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "dreams.db"
PHOTOS_DIR = PROJECT_ROOT / "data" / "photos"
ASSETS_DIR = PROJECT_ROOT / "assets" / "branding"

LOGO_PATH = ASSETS_DIR / "jth-icon.jpg"

# Load .env if present
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"\''))

# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------
NAVY = "#082d40"
GOLD = "#ddab4a"
GRAY = "#4e4e4e"

AGENT = {
    "name": os.environ.get("AGENT_NAME", "Joseph Williams"),
    "phone": os.environ.get("AGENT_PHONE", "(828) 347-9363"),
    "email": os.environ.get("AGENT_EMAIL", "Joseph@JonTharpHomes.com"),
    "website": os.environ.get("AGENT_WEBSITE", "www.JonTharpHomes.com"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_base64(filepath: Path, fallback: str = "") -> str:
    """Load a file as a base64 data URI. Return fallback on failure."""
    if not filepath or not filepath.exists():
        return fallback
    try:
        data = filepath.read_bytes()
        ext = filepath.suffix.lower().lstrip(".")
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except Exception as exc:
        logger.warning("Could not load %s: %s", filepath, exc)
        return fallback


def _find_local_photo(listing: dict) -> Optional[Path]:
    """Find a local photo file for the listing."""
    mls = listing.get("mls_number", "")

    # 1. photo_local_path column
    local_path = listing.get("photo_local_path")
    if local_path:
        full = PROJECT_ROOT / local_path
        if full.exists():
            return full

    # 2. mlsgrid convention
    mlsgrid = PHOTOS_DIR / "mlsgrid" / f"{mls}.jpg"
    if mlsgrid.exists():
        return mlsgrid

    # 3. navica convention
    navica = PHOTOS_DIR / "navica" / f"{mls}_01.jpg"
    if navica.exists():
        return navica
    navica_plain = PHOTOS_DIR / "navica" / f"{mls}.jpg"
    if navica_plain.exists():
        return navica_plain

    return None


def _fmt_price(val) -> str:
    """Format a price value as $X,XXX,XXX."""
    if val is None:
        return ""
    try:
        return f"${int(float(val)):,}"
    except (ValueError, TypeError):
        return ""


def _fmt_number(val) -> str:
    """Format a numeric value with commas."""
    if val is None:
        return ""
    try:
        return f"{int(float(val)):,}"
    except (ValueError, TypeError):
        return str(val) if val else ""


def _sanitize_for_filename(text: str) -> str:
    """Turn text into a filename-safe string."""
    text = re.sub(r"[^\w\s-]", "", text or "")
    text = re.sub(r"\s+", "-", text.strip())
    return text


def _escape(text) -> str:
    """HTML-escape a string."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def _get_showing(showing_id: str, db_path: str = None) -> Optional[dict]:
    """Fetch a showing record by ID."""
    path = db_path or str(DATABASE_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM showings WHERE id = ?", [showing_id]
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_lead(lead_id: str, db_path: str = None) -> Optional[dict]:
    """Fetch a lead record by ID."""
    if not lead_id:
        return None
    path = db_path or str(DATABASE_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM leads WHERE id = ?", [lead_id]
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_listing(listing_id: str, db_path: str = None) -> Optional[dict]:
    """Fetch a listing by id."""
    if not listing_id:
        return None
    path = db_path or str(DATABASE_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM listings WHERE id = ? OR mls_number = ? LIMIT 1",
            [listing_id, listing_id],
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

def _build_html(showing_data: dict, db_path: str = None, version: str = "agent") -> str:
    """
    Build the full HTML for the tour schedule PDF.

    showing_data can be either a dict from the showings table
    or a manually constructed dict with the same fields.
    version: 'agent' (includes door codes, private remarks) or
             'buyer' (no door codes, adds elevation, views, DOM, HOA, taxes)
    """
    # Parse route data
    route_data_raw = showing_data.get("route_data", "{}")
    if isinstance(route_data_raw, str):
        try:
            route_data = json.loads(route_data_raw)
        except (json.JSONDecodeError, TypeError):
            route_data = {}
    else:
        route_data = route_data_raw or {}

    stops = route_data.get("stops", [])
    depart_time = route_data.get("departTime", "")
    return_time = route_data.get("returnTime", "")
    total_miles = route_data.get("totalMiles", "")

    # Buyer name
    buyer_name = showing_data.get("buyer_name", "")
    if not buyer_name:
        lead = _get_lead(showing_data.get("lead_id"), db_path)
        if lead:
            first = (lead.get("first_name") or "").strip()
            last = (lead.get("last_name") or "").strip()
            buyer_name = f"{first} {last}".strip()

    # Date
    sched_date = showing_data.get("scheduled_date", "")
    if sched_date:
        try:
            dt = datetime.strptime(sched_date, "%Y-%m-%d")
            date_display = dt.strftime("%A, %B %-d, %Y")
        except ValueError:
            date_display = sched_date
    else:
        date_display = ""

    # Load logo
    logo_b64 = _load_base64(LOGO_PATH)

    # Build property cards with travel dividers between stops
    cards_html = []
    stop_num = 0

    for i, stop in enumerate(stops):
        is_break = stop.get("isBreak", False)

        # Build travel divider (before this stop, not before the first)
        divider_html = ''
        if i > 0:
            prev_stop = stops[i - 1]
            drive_min = prev_stop.get("driveMinutes")
            drive_mi = prev_stop.get("driveMiles")
            if drive_min is not None and drive_mi is not None:
                label = f"{drive_min} min | {drive_mi} mi"
                divider_html = (
                    f'<div class="travel-divider">'
                    f'<div class="line"></div>'
                    f'<span class="label">{_escape(label)}</span>'
                    f'<div class="line"></div>'
                    f'</div>'
                )

        if is_break:
            card_html = _build_break_card(stop)
        else:
            stop_num += 1
            property_id = stop.get("propertyId")
            listing = _get_listing(property_id, db_path) if property_id else None
            card_html = _build_property_card(stop, listing, stop_num, version)

        # Wrap divider + card in a group to prevent page breaks splitting them
        cards_html.append(
            f'<div class="stop-group">{divider_html}{card_html}</div>'
        )

    cards_joined = "\n".join(cards_html)

    # Timing info line
    timing_parts = []
    if depart_time:
        timing_parts.append(f"Depart {_escape(str(depart_time))}")
    if return_time:
        timing_parts.append(f"Return {_escape(str(return_time))}")
    timing_display = " | ".join(timing_parts)
    schedule_label = "AGENT&#39;S SCHEDULE" if version == "agent" else "SCHEDULE"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: 8.5in 11in;
    margin: 0.5in;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    color: {GRAY};
    font-size: 11px;
    line-height: 1.4;
    padding-bottom: 40px;  /* reserve space for fixed footer */
}}

/* Header */
.header {{
    text-align: center;
    margin-bottom: 10px;
}}
.header h1 {{
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 32px;
    color: {NAVY};
    font-weight: 700;
    letter-spacing: 2px;
    margin-bottom: 0;
    line-height: 1.1;
}}
.header .subtitle {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 13px;
    color: {GOLD};
    text-transform: uppercase;
    letter-spacing: 4px;
    font-weight: 600;
    margin-top: 2px;
}}
.gold-line {{
    height: 1px;
    background: {GOLD};
    margin: 8px 0;
}}
.header-meta {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: {GRAY};
    padding: 4px 0 8px 0;
}}
.header-meta .date {{ font-weight: 600; }}
.header-meta .buyer {{ font-weight: 600; color: {NAVY}; font-size: 14px; }}
.header-meta .timing {{ color: {GRAY}; }}

/* Stop group: keeps divider + card together across page breaks */
.stop-group {{
    page-break-inside: avoid;
}}

/* Property cards */
.card {{
    border-top: 2px solid {GOLD};
    padding: 10px 0 8px 0;
    display: flex;
    gap: 14px;
    align-items: flex-start;
}}
.card-photo {{
    width: 150px;
    min-width: 150px;
    height: 100px;
    border-radius: 4px;
    overflow: hidden;
    background: #f0f0f0;
    flex-shrink: 0;
}}
.card-photo img {{
    width: 150px;
    height: 100px;
    object-fit: cover;
    display: block;
}}
.card-photo-placeholder {{
    width: 150px;
    height: 100px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #e8e8e8;
    color: #aaa;
    font-size: 10px;
}}
.card-info {{
    flex: 1;
    min-width: 0;
}}
.card-address {{
    font-size: 14px;
    font-weight: 700;
    color: {NAVY};
    margin-bottom: 3px;
}}
.card-address .city {{
    font-weight: 400;
    color: {GRAY};
    font-size: 12px;
}}
.card-time-price {{
    font-size: 12px;
    color: {GRAY};
    margin-bottom: 3px;
}}
.card-time-price .time {{
    font-weight: 700;
    color: {NAVY};
}}
.card-time-price .price {{
    font-weight: 700;
    color: {GOLD};
}}
.card-stats {{
    font-size: 11px;
    color: {GRAY};
    margin-bottom: 3px;
}}
.card-notes {{
    font-size: 11px;
    color: #888;
    font-style: italic;
}}
.card-stop-num {{
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 18px;
    font-weight: 700;
    color: {GOLD};
    width: 28px;
    text-align: center;
    flex-shrink: 0;
    padding-top: 2px;
}}

/* Break card */
.break-card {{
    border-top: 2px solid {GOLD};
    padding: 10px 14px;
    display: flex;
    gap: 12px;
    align-items: center;
    background: #fdf8ee;
    page-break-inside: avoid;
    border-radius: 0 0 4px 4px;
}}
.break-icon {{
    font-size: 22px;
    flex-shrink: 0;
    width: 28px;
    text-align: center;
}}
.break-info {{
    flex: 1;
}}
.break-label {{
    font-size: 13px;
    font-weight: 700;
    color: {NAVY};
}}
.break-detail {{
    font-size: 11px;
    color: {GRAY};
}}

/* Travel divider between stops: single line with label overlaid */
.travel-divider {{
    display: flex;
    align-items: center;
    padding: 2px 0;
    page-break-inside: avoid;
}}
.travel-divider .line {{
    flex: 1;
    height: 0;
    border-top: 2px solid {GOLD};
}}
.travel-divider .label {{
    padding: 2px 14px;
    font-size: 12px;
    font-weight: 600;
    color: {GOLD};
    border-radius: 12px;
    white-space: nowrap;
    background: #fff;
    flex-shrink: 0;
}}
.stop-group .travel-divider + .card,
.stop-group .travel-divider + .break-card {{
    border-top: none;
}}

/* Footer */
.footer {{
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-top: 1px solid {GOLD};
    font-size: 10px;
    color: {GRAY};
}}
.footer-info {{
    display: flex;
    gap: 6px;
    align-items: center;
}}
.footer-logo {{
    height: 30px;
    width: auto;
}}
</style>
</head>
<body>

<div class="header">
    <h1>HOUSE TOUR</h1>
    <div class="subtitle">{schedule_label}</div>
    <div class="gold-line"></div>
    <div class="header-meta">
        <span class="date">{_escape(date_display)}</span>
        <span class="buyer">{_escape(buyer_name)}</span>
        <span class="timing">{timing_display}</span>
    </div>
</div>

{cards_joined}

<div class="footer">
    <div class="footer-info">
        {_escape(AGENT['name'])} | {_escape(AGENT['phone'])} | {_escape(AGENT['email'])} | {_escape(AGENT['website'])}
    </div>
    {f'<img class="footer-logo" src="{logo_b64}">' if logo_b64 else ''}
</div>

</body>
</html>"""

    return html


def _build_property_card(stop: dict, listing: Optional[dict], stop_num: int, version: str = "agent") -> str:
    """Build HTML for a single property card. version='agent' or 'buyer'."""
    address = _escape(stop.get("address") or stop.get("label") or "")
    city = _escape(stop.get("city", ""))

    # Time display
    st_start = stop.get("stStart", "")
    st_end = stop.get("stEnd", "")
    if st_start and st_end:
        time_display = f"{_escape(st_start)} - {_escape(st_end)}"
    elif st_start:
        time_display = _escape(st_start)
    else:
        time_display = "TBD"

    # Price and stats from listing
    price = ""
    stats_parts = []
    photo_html = '<div class="card-photo-placeholder">No Photo</div>'

    if listing:
        price = _fmt_price(listing.get("list_price"))

        beds = listing.get("bedrooms") or listing.get("beds")
        baths = listing.get("bathrooms") or listing.get("baths")
        sqft = listing.get("sqft") or listing.get("living_area")
        acres = listing.get("lot_size_area") or listing.get("acreage")
        year_built = listing.get("year_built")

        if beds:
            stats_parts.append(f"{_fmt_number(beds)} Beds")
        if baths:
            stats_parts.append(f"{_fmt_number(baths)} Baths")
        if sqft:
            stats_parts.append(f"{_fmt_number(sqft)} SqFt")
        if acres:
            try:
                acres_val = float(acres)
                if acres_val > 0:
                    stats_parts.append(f"{acres_val:.2f} Acres")
            except (ValueError, TypeError):
                pass
        if year_built:
            stats_parts.append(f"Built {_escape(str(int(float(year_built))))}")

        # Photo
        photo_path = _find_local_photo(listing)
        if photo_path:
            photo_b64 = _load_base64(photo_path)
            if photo_b64:
                photo_html = f'<img src="{photo_b64}" alt="Property photo">'

        # Fill in city from listing if not in stop
        if not city:
            city = _escape(listing.get("city", ""))
            state = _escape(listing.get("state", ""))
            zipcode = _escape(listing.get("postal_code") or listing.get("zip_code", ""))
            if state:
                city = f"{city}, {state}"
            if zipcode:
                city = f"{city} {zipcode}"

    # Buyer version: add extra stats
    extra_lines = []
    if listing and version == "buyer":
        elevation = listing.get("elevation_feet")
        if elevation:
            stats_parts.append(f"{_fmt_number(elevation)} ft Elev")

        views_raw = listing.get("views")
        if views_raw:
            try:
                vlist = json.loads(views_raw) if isinstance(views_raw, str) else views_raw
                if isinstance(vlist, list) and vlist:
                    extra_lines.append(f"Views: {', '.join(str(v) for v in vlist)}")
            except (json.JSONDecodeError, TypeError):
                if isinstance(views_raw, str) and views_raw:
                    extra_lines.append(f"Views: {_escape(views_raw)}")

        dom = listing.get("days_on_market")
        if dom is not None:
            extra_lines.append(f"Days on Market: {dom}")

        hoa_fee = listing.get("hoa_fee")
        hoa_freq = listing.get("hoa_frequency") or listing.get("hoa_freq")
        if hoa_fee:
            hoa_str = f"HOA: {_fmt_price(hoa_fee)}"
            if hoa_freq:
                hoa_str += f" ({_escape(str(hoa_freq))})"
            extra_lines.append(hoa_str)

        tax = listing.get("tax_annual_amount")
        county = listing.get("county")
        if tax:
            tax_str = f"County Tax: {_fmt_price(tax)}/yr"
            if county:
                tax_str += f" ({_escape(county)})"
            extra_lines.append(tax_str)

    # Agent version: add extra details
    if listing and version == "agent":
        private = listing.get("private_remarks")
        if private:
            extra_lines.append(f"Agent Notes: {_escape(private)}")

    # Directions (both versions)
    if listing:
        directions = listing.get("directions")
        if directions:
            extra_lines.append(f"Directions: {_escape(directions)}")

    stats_display = " | ".join(stats_parts) if stats_parts else ""

    # Notes (agent version only; buyer version hides door codes etc.)
    notes = stop.get("notes", "")
    notes_html = ""
    if notes and version == "agent":
        notes_html = f'<div class="card-notes">{_escape(notes)}</div>'

    # City/state line
    city_html = f' <span class="city">{city}</span>' if city else ""

    # Price separator
    price_sep = ""
    if price:
        price_sep = f' | <span class="price">{_escape(price)}</span>'

    extra_html = ""
    for line in extra_lines:
        extra_html += f'<div class="card-notes">{line}</div>'

    return f"""<div class="card">
    <div class="card-stop-num">{stop_num}</div>
    <div class="card-photo">{photo_html}</div>
    <div class="card-info">
        <div class="card-address">{address}{city_html}</div>
        <div class="card-time-price">
            <span class="time">{time_display}</span>{price_sep}
        </div>
        {"<div class='card-stats'>" + _escape(stats_display) + "</div>" if stats_display else ""}
        {notes_html}
        {extra_html}
    </div>
</div>"""


def _build_break_card(stop: dict) -> str:
    """Build HTML for a break stop card."""
    label = _escape(stop.get("label") or stop.get("name") or "Break")
    address = _escape(stop.get("address", ""))
    duration = stop.get("duration", "")

    st_start = stop.get("stStart", "")
    st_end = stop.get("stEnd", "")

    detail_parts = []
    if address:
        detail_parts.append(address)
    if st_start and st_end:
        detail_parts.append(f"{_escape(st_start)} - {_escape(st_end)}")
    elif st_start:
        detail_parts.append(_escape(st_start))
    if duration:
        detail_parts.append(f"{duration} min")

    detail = " | ".join(detail_parts)

    return f"""<div class="break-card">
    <div class="break-icon">&#9749;</div>
    <div class="break-info">
        <div class="break-label">{label}</div>
        <div class="break-detail">{detail}</div>
    </div>
</div>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_tour_schedule(showing_id: str, db_path: str = None, version: str = "agent") -> Optional[bytes]:
    """
    Generate a House Tour Schedule PDF for the given showing ID.

    version: 'agent' (private remarks, door codes) or 'buyer' (public details, no codes)
    Returns PDF bytes on success, or None on failure.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint is not installed. Cannot generate PDF.")
        return None

    path = db_path or str(DATABASE_PATH)
    showing = _get_showing(showing_id, path)
    if not showing:
        logger.error("Showing %s not found", showing_id)
        return None

    html = _build_html(showing, path, version)
    try:
        pdf_bytes = HTML(string=html).write_pdf()
        logger.info("Generated tour schedule PDF for showing %s (%d bytes)", showing_id, len(pdf_bytes))
        return pdf_bytes
    except Exception as exc:
        logger.error("Failed to generate PDF for showing %s: %s", showing_id, exc)
        return None


def generate_tour_schedule_from_data(data: dict, db_path: str = None, version: str = "agent") -> Optional[bytes]:
    """
    Generate a House Tour Schedule PDF from a dict of showing-like data.

    version: 'agent' or 'buyer'
    Returns PDF bytes on success, or None on failure.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint is not installed. Cannot generate PDF.")
        return None

    html = _build_html(data, db_path or str(DATABASE_PATH), version)
    try:
        pdf_bytes = HTML(string=html).write_pdf()
        logger.info("Generated tour schedule PDF from data (%d bytes)", len(pdf_bytes))
        return pdf_bytes
    except Exception as exc:
        logger.error("Failed to generate PDF from data: %s", exc)
        return None


def get_schedule_filename(showing: dict) -> str:
    """Generate a clean filename for the tour schedule PDF."""
    name = showing.get("name", "")
    sched_date = showing.get("scheduled_date", "")

    parts = []
    parts.append("House-Tour")
    if sched_date:
        parts.append(sched_date)
    if name:
        parts.append(_sanitize_for_filename(name))

    return "-".join(parts) + ".pdf"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a House Tour Schedule PDF")
    parser.add_argument("showing_id", help="ID of the showing record")
    parser.add_argument("-o", "--output", help="Output file path (default: auto-generated)")
    parser.add_argument("--db", help="Database path (default: data/dreams.db)")
    args = parser.parse_args()

    db = args.db or str(DATABASE_PATH)

    showing = _get_showing(args.showing_id, db)
    if not showing:
        print(f"Error: Showing '{args.showing_id}' not found.")
        sys.exit(1)

    pdf = generate_tour_schedule(args.showing_id, db)
    if not pdf:
        print("Error: Failed to generate PDF.")
        sys.exit(1)

    output_path = args.output or get_schedule_filename(showing)
    with open(output_path, "wb") as f:
        f.write(pdf)
    print(f"Saved tour schedule to: {output_path}")
