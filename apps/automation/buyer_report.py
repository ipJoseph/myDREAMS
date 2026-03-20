"""
Buyer Report PDF Generator

Generates single-property PDF reports modeled after the RPR Buyer Report format.
Uses WeasyPrint for HTML-to-PDF conversion. Three pages per property:
  Page 1: Cover (photo, address, agent card)
  Page 2: Property Details (facts, remarks)
  Page 3: Maps (satellite + road)
"""

import base64
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

HEADSHOT_PATH = ASSETS_DIR / "agent-headshot.jpg"
LOGO_PATH = ASSETS_DIR / "jth-icon.jpg"

# Load .env if present (for GOOGLE_MAPS_API_KEY and other settings)
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"\''))

# Google Maps API key from environment
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# ---------------------------------------------------------------------------
# Agent info (hardcoded for now)
# ---------------------------------------------------------------------------
AGENT = {
    "name": "Joseph Williams",
    "license": "North Carolina Real Estate License #360474",
    "mobile": "(828) 347-9363",
    "email": "Joseph@NCPropertyInvestments.com",
    "website": "www.JonTharpHomes.com",
    "office": "Jon Tharp Homes, A Keller Williams Team",
}

# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------
NAVY = "#082d40"
GOLD = "#ddab4a"
GRAY = "#4e4e4e"


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
    """
    Find a local photo file for the listing.
    Priority: photo_local_path column, then mlsgrid/{mls}.jpg, then navica/{mls}_01.jpg.
    """
    mls = listing.get("mls_number", "")

    # 1. Use photo_local_path if present
    local_path = listing.get("photo_local_path")
    if local_path:
        full = PROJECT_ROOT / local_path
        if full.exists():
            return full

    # 2. mlsgrid convention
    mlsgrid = PHOTOS_DIR / "mlsgrid" / f"{mls}.jpg"
    if mlsgrid.exists():
        return mlsgrid

    # 3. navica convention (primary = _01)
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
        return "N/A"
    try:
        return f"${int(float(val)):,}"
    except (ValueError, TypeError):
        return "N/A"


def _fmt_number(val) -> str:
    """Format a numeric value with commas."""
    if val is None:
        return "N/A"
    try:
        return f"{int(float(val)):,}"
    except (ValueError, TypeError):
        return str(val)


def _sanitize_for_filename(text: str) -> str:
    """Turn an address into a filename-safe string."""
    text = re.sub(r"[^\w\s-]", "", text or "")
    text = re.sub(r"\s+", "-", text.strip())
    return text


def _price_per_sqft(listing: dict) -> str:
    price = listing.get("list_price")
    sqft = listing.get("sqft")
    if price and sqft:
        try:
            ppsf = float(price) / float(sqft)
            return f"${ppsf:,.0f}"
        except (ValueError, TypeError, ZeroDivisionError):
            pass
    return "N/A"


def _status_label(status: str) -> str:
    """Return a human-readable status label."""
    mapping = {
        "Active": "Active / For Sale",
        "Pending": "Pending",
        "Closed": "Sold / Closed",
        "ActiveUnderContract": "Active Under Contract",
    }
    return mapping.get(status or "", status or "N/A")


def _google_map_url(lat, lng, zoom: int, maptype: str) -> str:
    """Build a Google Static Maps URL."""
    if not lat or not lng or not GOOGLE_MAPS_API_KEY:
        return ""
    return (
        f"https://maps.googleapis.com/maps/api/staticmap"
        f"?center={lat},{lng}"
        f"&zoom={zoom}"
        f"&size=800x400"
        f"&maptype={maptype}"
        f"&markers=color:red%7C{lat},{lng}"
        f"&key={GOOGLE_MAPS_API_KEY}"
    )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def _get_listing(listing_id: str) -> Optional[dict]:
    """Fetch a single listing by id or mls_number."""
    conn = sqlite3.connect(str(DATABASE_PATH))
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

def _build_html(listing: dict, index: int = 0) -> str:
    """Build the 3-page HTML for a single listing buyer report."""

    # Load assets as base64
    logo_b64 = _load_base64(LOGO_PATH)
    headshot_b64 = _load_base64(HEADSHOT_PATH)

    # Property photo
    photo_path = _find_local_photo(listing)
    photo_b64 = _load_base64(photo_path) if photo_path else ""

    # Computed fields
    address = listing.get("address") or "Address Not Available"
    city = listing.get("city") or ""
    state = listing.get("state") or "NC"
    zipcode = listing.get("zip") or ""
    city_state_zip = f"{city}, {state} {zipcode}".strip().strip(",").strip()
    full_address = f"{address}, {city_state_zip}" if city_state_zip else address

    price = _fmt_price(listing.get("list_price"))
    beds = _fmt_number(listing.get("beds"))
    baths = _fmt_number(listing.get("baths"))
    sqft = _fmt_number(listing.get("sqft"))
    acreage = listing.get("acreage") or "N/A"
    if acreage != "N/A":
        try:
            acreage = f"{float(acreage):.2f}"
        except (ValueError, TypeError):
            pass
    year_built = listing.get("year_built") or "N/A"
    dom = listing.get("days_on_market") or "N/A"
    ppsf = _price_per_sqft(listing)
    mls_num = listing.get("mls_number") or "N/A"
    status = listing.get("status") or "N/A"
    status_label = _status_label(status)
    list_date = listing.get("list_date") or ""
    prop_type = listing.get("property_type") or "N/A"
    prop_subtype = listing.get("property_subtype") or ""
    land_use = prop_subtype if prop_subtype else prop_type
    county = listing.get("county") or "N/A"
    parcel = listing.get("parcel_number") or "N/A"
    remarks = listing.get("public_remarks") or "No description available."

    lat = listing.get("latitude")
    lng = listing.get("longitude")
    sat_url = _google_map_url(lat, lng, 17, "satellite")
    road_url = _google_map_url(lat, lng, 15, "roadmap")

    today = datetime.now().strftime("%B %d, %Y")

    # Photo HTML
    if photo_b64:
        cover_photo_html = f'<img src="{photo_b64}" class="cover-photo" alt="Property photo" />'
        detail_photo_html = f'<img src="{photo_b64}" class="detail-photo" alt="Property photo" />'
    else:
        cover_photo_html = '<div class="photo-placeholder">Photo Not Available</div>'
        detail_photo_html = '<div class="photo-placeholder-detail">Photo Not Available</div>'

    # Map HTML
    # Fetch map images and embed as base64 (WeasyPrint can't reliably fetch remote URLs)
    sat_html = '<div class="map-placeholder">Aerial map unavailable (no coordinates or API key)</div>'
    road_html = '<div class="map-placeholder">Road map unavailable (no coordinates or API key)</div>'

    if sat_url:
        try:
            import requests
            resp = requests.get(sat_url, timeout=10)
            if resp.status_code == 200 and 'image' in resp.headers.get('Content-Type', ''):
                sat_b64 = base64.b64encode(resp.content).decode()
                sat_html = f'<img src="data:image/png;base64,{sat_b64}" class="map-img" alt="Aerial view" />'
        except Exception:
            pass

    if road_url:
        try:
            import requests
            resp = requests.get(road_url, timeout=10)
            if resp.status_code == 200 and 'image' in resp.headers.get('Content-Type', ''):
                road_b64 = base64.b64encode(resp.content).decode()
                road_html = f'<img src="data:image/png;base64,{road_b64}" class="map-img" alt="Road map" />'
            else:
                logger.warning(f"Road map request failed: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Road map fetch error: {e}")

    # Status badge color
    status_bg = GOLD if status == "Active" else "#6c757d"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<style>
/* ------------------------------------------------------------------ */
/* Global / Page Setup                                                 */
/* ------------------------------------------------------------------ */
@page {{
    size: 8.5in 11in;
    margin: 0.5in 0.6in 0.7in 0.6in;
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: "Open Sans", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt;
    color: {GRAY};
    line-height: 1.45;
}}

h1, h2, h3, h4 {{
    font-family: Georgia, "Times New Roman", serif;
    color: {NAVY};
    font-weight: normal;
}}

.page {{
    position: relative;
    min-height: 9.0in;
}}
.page-break {{
    page-break-before: always;
}}

/* ------------------------------------------------------------------ */
/* Header (pages 2 & 3)                                                */
/* ------------------------------------------------------------------ */
.header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding-bottom: 8px;
    border-bottom: 2px solid {NAVY};
    margin-bottom: 16px;
}}
.header-left {{
    font-family: Georgia, "Times New Roman", serif;
    color: {NAVY};
    font-size: 14pt;
    font-weight: bold;
}}
.header-address {{
    font-size: 9pt;
    color: {GRAY};
    margin-top: 2px;
}}
.header-logo {{
    width: 60px;
    height: auto;
}}

/* ------------------------------------------------------------------ */
/* Footer                                                              */
/* ------------------------------------------------------------------ */
.footer {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    font-size: 7pt;
    color: #999;
    border-top: 1px solid #ddd;
    padding-top: 6px;
    display: flex;
    justify-content: space-between;
}}

/* ================================================================== */
/* PAGE 1: COVER                                                       */
/* ================================================================== */
.cover-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}}
.cover-logo {{
    width: 70px;
    height: auto;
}}
.cover-label {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 16pt;
    color: {NAVY};
    font-weight: bold;
}}
.cover-address {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 26pt;
    color: {NAVY};
    line-height: 1.2;
    margin-bottom: 4px;
}}
.cover-city {{
    font-size: 14pt;
    color: {GRAY};
    margin-bottom: 10px;
}}
.cover-hr {{
    border: none;
    border-top: 3px solid {GOLD};
    margin-bottom: 14px;
}}
.cover-photo {{
    width: 100%;
    max-height: 4.4in;
    object-fit: cover;
    border-radius: 4px;
}}
.photo-placeholder {{
    width: 100%;
    height: 4.4in;
    background: #f0f0f0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #999;
    font-size: 14pt;
    border-radius: 4px;
    border: 1px solid #ddd;
}}

/* Agent card */
.agent-card {{
    display: flex;
    align-items: center;
    margin-top: 18px;
    padding: 14px 18px;
    background: {NAVY};
    border-radius: 6px;
    color: #fff;
}}
.agent-headshot {{
    width: 72px;
    height: 72px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid {GOLD};
    margin-right: 16px;
    flex-shrink: 0;
}}
.agent-info {{
    line-height: 1.5;
}}
.agent-name {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 13pt;
    color: {GOLD};
    font-weight: bold;
}}
.agent-detail {{
    font-size: 8.5pt;
    color: #ccc;
}}

/* ================================================================== */
/* PAGE 2: PROPERTY DETAILS                                            */
/* ================================================================== */
.detail-photo {{
    width: 100%;
    max-height: 2.6in;
    object-fit: cover;
    border-radius: 4px;
    margin-bottom: 12px;
}}
.photo-placeholder-detail {{
    width: 100%;
    height: 2.6in;
    background: #f0f0f0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #999;
    font-size: 12pt;
    border-radius: 4px;
    border: 1px solid #ddd;
    margin-bottom: 12px;
}}

.status-badge {{
    display: inline-block;
    padding: 3px 12px;
    border-radius: 3px;
    color: #fff;
    font-size: 9pt;
    font-weight: bold;
    margin-bottom: 10px;
}}

.price-row {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 14px;
}}
.price-box {{
    background: #f7f7f7;
    padding: 10px 16px;
    border-radius: 4px;
    border-left: 4px solid {GOLD};
    min-width: 200px;
}}
.price-big {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 22pt;
    color: {NAVY};
    font-weight: bold;
}}
.price-meta {{
    font-size: 8.5pt;
    color: {GRAY};
    margin-top: 2px;
}}

.highlights {{
    display: flex;
    gap: 20px;
    align-items: flex-start;
}}
.highlight-item {{
    text-align: center;
    min-width: 70px;
}}
.highlight-value {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 16pt;
    color: {NAVY};
    font-weight: bold;
}}
.highlight-label {{
    font-size: 8pt;
    color: {GRAY};
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* Basic Facts grid */
.section-title {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 12pt;
    color: {NAVY};
    border-bottom: 2px solid {GOLD};
    padding-bottom: 4px;
    margin-top: 14px;
    margin-bottom: 8px;
}}
.facts-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 0;
}}
.fact-item {{
    width: 50%;
    padding: 5px 0;
    border-bottom: 1px solid #eee;
    display: flex;
}}
.fact-label {{
    font-weight: bold;
    color: {NAVY};
    width: 130px;
    flex-shrink: 0;
    font-size: 9pt;
}}
.fact-value {{
    font-size: 9pt;
}}

.remarks {{
    font-size: 9pt;
    line-height: 1.55;
    color: {GRAY};
    margin-top: 4px;
    max-height: 180px;
    overflow: hidden;
}}

/* ================================================================== */
/* PAGE 3: MAPS                                                        */
/* ================================================================== */
.map-section-title {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 11pt;
    color: {NAVY};
    margin-top: 12px;
    margin-bottom: 6px;
}}
.map-img {{
    width: 100%;
    max-height: 280px;
    object-fit: cover;
    border-radius: 4px;
    border: 1px solid #ddd;
}}
.map-placeholder {{
    width: 100%;
    height: 200px;
    background: #f0f0f0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #999;
    border-radius: 4px;
    border: 1px solid #ddd;
    font-size: 10pt;
}}
</style>
</head>
<body>

<!-- ================================================================ -->
<!-- PAGE 1: COVER                                                     -->
<!-- ================================================================ -->
<div class="page" id="page-cover-{index}">

    <div class="cover-top">
        <img src="{logo_b64}" class="cover-logo" alt="Logo" />
        <span class="cover-label">Buyer Report</span>
    </div>

    <div class="cover-address">{address}</div>
    <div class="cover-city">{city_state_zip}</div>
    <hr class="cover-hr" />

    {cover_photo_html}

    <div class="agent-card">
        <img src="{headshot_b64}" class="agent-headshot" alt="Agent headshot" />
        <div class="agent-info">
            <div class="agent-name">{AGENT['name']}</div>
            <div class="agent-detail">{AGENT['license']}</div>
            <div class="agent-detail">{AGENT['mobile']} &nbsp;|&nbsp; {AGENT['email']}</div>
            <div class="agent-detail">{AGENT['website']}</div>
            <div class="agent-detail">{AGENT['office']}</div>
        </div>
    </div>

    <div class="footer">
        <span>Generated {today}</span>
        <span>Information deemed reliable but not guaranteed.</span>
        <span>Page 1</span>
    </div>
</div>

<!-- ================================================================ -->
<!-- PAGE 2: PROPERTY DETAILS                                          -->
<!-- ================================================================ -->
<div class="page page-break" id="page-details-{index}">

    <div class="header">
        <div>
            <div class="header-left">Buyer Report</div>
            <div class="header-address">{full_address}</div>
        </div>
        <img src="{logo_b64}" class="header-logo" alt="Logo" />
    </div>

    {detail_photo_html}

    <div class="status-badge" style="background: {status_bg};">{status_label}</div>

    <div class="price-row">
        <div class="price-box">
            <div class="price-big">{price}</div>
            <div class="price-meta">List Price &nbsp;|&nbsp; Active: {list_date}</div>
            <div class="price-meta">MLS# {mls_num}</div>
        </div>
        <div class="highlights">
            <div class="highlight-item">
                <div class="highlight-value">{beds}</div>
                <div class="highlight-label">Beds</div>
            </div>
            <div class="highlight-item">
                <div class="highlight-value">{baths}</div>
                <div class="highlight-label">Baths</div>
            </div>
            <div class="highlight-item">
                <div class="highlight-value">{sqft}</div>
                <div class="highlight-label">Sq Ft</div>
            </div>
            <div class="highlight-item">
                <div class="highlight-value">{acreage}</div>
                <div class="highlight-label">Acres</div>
            </div>
        </div>
    </div>

    <div class="section-title">Basic Facts</div>
    <div class="facts-grid">
        <div class="fact-item">
            <span class="fact-label">Type</span>
            <span class="fact-value">{prop_type}</span>
        </div>
        <div class="fact-item">
            <span class="fact-label">Days on Market</span>
            <span class="fact-value">{dom}</span>
        </div>
        <div class="fact-item">
            <span class="fact-label">Year Built</span>
            <span class="fact-value">{year_built}</span>
        </div>
        <div class="fact-item">
            <span class="fact-label">Price / Sq Ft</span>
            <span class="fact-value">{ppsf}</span>
        </div>
        <div class="fact-item">
            <span class="fact-label">Land Use</span>
            <span class="fact-value">{land_use}</span>
        </div>
        <div class="fact-item">
            <span class="fact-label">APN / Tax ID</span>
            <span class="fact-value">{parcel}</span>
        </div>
        <div class="fact-item">
            <span class="fact-label">County</span>
            <span class="fact-value">{county}</span>
        </div>
        <div class="fact-item">
            <span class="fact-label">MLS#</span>
            <span class="fact-value">{mls_num}</span>
        </div>
    </div>

    <div class="section-title">Description</div>
    <div class="remarks">{remarks}</div>

    <div class="footer">
        <span>Generated {today}</span>
        <span>Information deemed reliable but not guaranteed.</span>
        <span>Page 2</span>
    </div>
</div>

<!-- ================================================================ -->
<!-- PAGE 3: MAPS                                                      -->
<!-- ================================================================ -->
<div class="page page-break" id="page-maps-{index}">

    <div class="header">
        <div>
            <div class="header-left">Buyer Report</div>
            <div class="header-address">{full_address}</div>
        </div>
        <img src="{logo_b64}" class="header-logo" alt="Logo" />
    </div>

    <div class="section-title">Maps</div>

    <div class="map-section-title">Aerial</div>
    {sat_html}

    <div class="map-section-title" style="margin-top: 18px;">Road</div>
    {road_html}

    <div class="footer">
        <span>Generated {today}</span>
        <span>Information deemed reliable but not guaranteed.</span>
        <span>Page 3</span>
    </div>
</div>

</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_buyer_report(listing_id: str) -> Optional[bytes]:
    """
    Generate a Buyer Report PDF for a single listing.

    Args:
        listing_id: The listing id or mls_number.

    Returns:
        PDF file contents as bytes, or None on failure.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint is not installed.")
        return None

    listing = _get_listing(listing_id)
    if not listing:
        logger.error("Listing not found: %s", listing_id)
        return None

    html_str = _build_html(listing)
    try:
        pdf_bytes = HTML(string=html_str).write_pdf()
        return pdf_bytes
    except Exception as exc:
        logger.error("Failed to render PDF for listing %s: %s", listing_id, exc)
        return None


def generate_buyer_report_html(listing_id: str) -> Optional[str]:
    """
    Return the raw HTML for a buyer report (useful for combining multiple
    listings into a single PDF render).

    Args:
        listing_id: The listing id or mls_number.

    Returns:
        HTML string, or None if listing not found.
    """
    listing = _get_listing(listing_id)
    if not listing:
        logger.error("Listing not found: %s", listing_id)
        return None
    return _build_html(listing)


def generate_combined_report(listing_ids: list) -> Optional[bytes]:
    """
    Generate a single PDF containing buyer reports for multiple listings.
    Each listing gets its own 3-page report. Pages are concatenated into
    one HTML document and rendered in a single WeasyPrint pass.

    Args:
        listing_ids: List of listing ids or mls_numbers.

    Returns:
        PDF bytes, or None on failure.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint is not installed.")
        return None

    if not listing_ids:
        logger.error("No listing IDs provided.")
        return None

    # Build individual HTML documents, then extract the body content and
    # combine under one set of styles. The first listing provides the full
    # HTML shell; subsequent listings contribute only their page divs.
    all_pages = []
    style_block = ""

    for idx, lid in enumerate(listing_ids):
        listing = _get_listing(lid)
        if not listing:
            logger.warning("Listing not found, skipping: %s", lid)
            continue

        html_str = _build_html(listing, index=idx)

        if idx == 0:
            # Extract everything before the first <div class="page"
            # and after the last </div>\n</body>
            style_end = html_str.find("</style>") + len("</style>")
            head_end = html_str.find("</head>")
            style_block = html_str[:head_end]

        # Extract body content (all page divs)
        body_start = html_str.find("<body>") + len("<body>")
        body_end = html_str.find("</body>")
        body_content = html_str[body_start:body_end].strip()

        # For listings after the first, make sure page 1 also has a page break
        if idx > 0:
            body_content = body_content.replace(
                'class="page" id="page-cover-{index}"',
                'class="page page-break" id="page-cover-{index}"',
                1,
            )

        all_pages.append(body_content)

    if not all_pages:
        logger.error("No valid listings found for combined report.")
        return None

    combined_html = (
        style_block
        + "\n</head>\n<body>\n"
        + "\n\n".join(all_pages)
        + "\n</body>\n</html>"
    )

    try:
        pdf_bytes = HTML(string=combined_html).write_pdf()
        return pdf_bytes
    except Exception as exc:
        logger.error("Failed to render combined PDF: %s", exc)
        return None


def get_report_filename(listing: dict) -> str:
    """
    Generate a clean filename for a buyer report.

    Args:
        listing: Dictionary with at least 'address'.

    Returns:
        Filename like '540-Toot-Hollow-Rd-Buyer-Report.pdf'
    """
    address = listing.get("address") or "Property"
    safe = _sanitize_for_filename(address)
    return f"{safe}-Buyer-Report.pdf"


def get_package_report_filename(package_name: str) -> str:
    """
    Generate a filename for a combined package report.

    Args:
        package_name: Name of the package.

    Returns:
        Filename like 'Mountain-Homes-Buyer-Report.pdf'
    """
    safe = _sanitize_for_filename(package_name or "Package")
    return f"{safe}-Buyer-Report.pdf"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Load .env for GOOGLE_MAPS_API_KEY
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"\''))
        GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    if len(sys.argv) < 2:
        print("Usage: python -m apps.automation.buyer_report <listing_id> [output_file]", file=sys.stderr)
        sys.exit(1)

    listing_id = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    pdf = generate_buyer_report(listing_id)
    if pdf is None:
        print("Failed to generate report.", file=sys.stderr)
        sys.exit(1)

    if output_file:
        Path(output_file).write_bytes(pdf)
        print(f"Written to {output_file} ({len(pdf):,} bytes)")
    else:
        sys.stdout.buffer.write(pdf)
