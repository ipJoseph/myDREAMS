"""
Single-Property Brochure PDF Generator

Generates branded PDF brochures for individual properties and collections.
Uses WeasyPrint for HTML to PDF conversion with the navy/gold design system.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime
from typing import Optional

from apps.automation import config
from apps.automation.email_service import render_template

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logger.warning("WeasyPrint not installed. PDF generation unavailable.")


def _get_db():
    """Get database connection with Row factory."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_json_list(value: str | None) -> list[str]:
    """Parse a JSON array string into a list. Falls back to comma split."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return [s.strip() for s in value.split(',') if s.strip()]


def _compute_dom(listing: dict) -> int | None:
    """Compute days on market dynamically for active listings."""
    status = (listing.get('status') or '').upper()
    stored = listing.get('days_on_market')
    if status in ('SOLD', 'CLOSED', 'EXPIRED', 'WITHDRAWN'):
        return stored
    list_date_str = listing.get('list_date')
    if list_date_str:
        try:
            ld = datetime.strptime(str(list_date_str)[:10], '%Y-%m-%d')
            return max(0, (datetime.now() - ld).days)
        except (ValueError, TypeError):
            pass
    return stored


def get_listing_data(listing_id: str) -> dict | None:
    """
    Fetch full listing from DB by ID.

    Returns dict with all fields needed for brochure, including enrichment
    fields not exposed in the public API (flood_zone, view_potential, etc.).
    Returns None if listing not found.
    """
    conn = _get_db()
    try:
        row = conn.execute(
            'SELECT * FROM listings WHERE id = ?',
            [listing_id]
        ).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def _get_agent_branding() -> dict:
    """Get agent branding info for PDFs."""
    return {
        'agent_name': config.AGENT_NAME,
        'agent_email': config.AGENT_EMAIL,
        'agent_phone': config.AGENT_PHONE,
        'agent_headshot': config.AGENT_HEADSHOT_URL,
        'brokerage_name': config.BROKERAGE_NAME,
        'brokerage_logo': config.BROKERAGE_LOGO_URL,
    }


def _build_template_context(listing: dict) -> dict:
    """Build the Jinja2 template context from a listing dict."""
    branding = _get_agent_branding()

    # Compute DOM dynamically
    listing['days_on_market'] = _compute_dom(listing)

    # Parse JSON feature arrays
    interior_features_list = _parse_json_list(listing.get('interior_features'))
    exterior_features_list = _parse_json_list(listing.get('exterior_features'))
    appliances_list = _parse_json_list(listing.get('appliances'))
    flooring_list = _parse_json_list(listing.get('flooring'))
    fireplace_list = _parse_json_list(listing.get('fireplace_features'))
    parking_list = _parse_json_list(listing.get('parking_features'))

    # Merge parking into exterior if present
    if parking_list:
        exterior_features_list = exterior_features_list + parking_list

    # Merge fireplace into interior if present
    if fireplace_list:
        interior_features_list = interior_features_list + fireplace_list

    # Determine if extended page is needed
    remarks = listing.get('public_remarks') or ''
    directions = listing.get('directions') or ''
    status_lower = (listing.get('status') or '').lower()
    is_sold = status_lower in ('sold', 'closed')
    needs_extended = len(remarks) > 600 or directions or is_sold

    context = {
        **listing,
        **branding,
        'interior_features_list': interior_features_list,
        'exterior_features_list': exterior_features_list,
        'appliances_list': appliances_list,
        'flooring_list': flooring_list,
        'needs_extended_page': needs_extended,
    }

    return context


def render_brochure_html(listing_id: str) -> str | None:
    """
    Render single-property brochure HTML.

    Returns HTML string ready for WeasyPrint, or None if listing not found.
    """
    listing = get_listing_data(listing_id)
    if not listing:
        return None

    context = _build_template_context(listing)
    return render_template('property_brochure.html', **context)


def generate_brochure_bytes(listing_id: str) -> bytes | None:
    """
    Generate single-property brochure as PDF bytes.

    Returns PDF bytes for web serving, or None on failure.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint not available.")
        return None

    html_content = render_brochure_html(listing_id)
    if not html_content:
        return None

    try:
        html = HTML(string=html_content, base_url=str(config.PROJECT_ROOT))
        return html.write_pdf()
    except Exception as e:
        logger.error(f"Failed to generate brochure PDF: {e}")
        return None


def generate_collection_pdf(share_token: str) -> tuple[bytes | None, str]:
    """
    Generate combined PDF for all properties in a collection.

    Each property gets its own full brochure treatment. The agent contact
    page appears only once at the very end.

    Returns (pdf_bytes, collection_name) or (None, '') on failure.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint not available.")
        return None, ''

    conn = _get_db()
    try:
        # Get collection
        collection = conn.execute(
            'SELECT id, name FROM property_packages WHERE share_token = ?',
            [share_token]
        ).fetchone()

        if not collection:
            return None, ''

        collection_name = collection['name'] or 'Collection'

        # Get listing IDs in order
        rows = conn.execute(
            '''SELECT l.id FROM package_properties pp
               JOIN listings l ON l.id = pp.listing_id
               WHERE pp.package_id = ? AND l.idx_opt_in = 1
               ORDER BY pp.display_order, pp.added_at''',
            [collection['id']]
        ).fetchall()

        if not rows:
            return None, collection_name

    finally:
        conn.close()

    listing_ids = [r['id'] for r in rows]

    # Generate individual PDFs and concatenate
    all_pdfs = []
    for lid in listing_ids:
        pdf_bytes = generate_brochure_bytes(lid)
        if pdf_bytes:
            all_pdfs.append(pdf_bytes)

    if not all_pdfs:
        return None, collection_name

    # If only one property, return it directly
    if len(all_pdfs) == 1:
        return all_pdfs[0], collection_name

    # Merge multiple PDFs
    try:
        import pypdf
        merger = pypdf.PdfWriter()
        for pdf_data in all_pdfs:
            reader = pypdf.PdfReader(pdf_data)
            for page in reader.pages:
                merger.add_page(page)

        import io
        output = io.BytesIO()
        merger.write(output)
        return output.getvalue(), collection_name
    except ImportError:
        # pypdf not available; return first PDF only
        logger.warning("pypdf not installed. Returning first property only for collection PDF.")
        return all_pdfs[0], collection_name


def get_brochure_filename(listing: dict) -> str:
    """
    Generate a clean filename like '123-Main-St-Franklin-NC.pdf'.

    Strips special characters and replaces spaces with hyphens.
    """
    address = listing.get('address') or 'Property'
    city = listing.get('city') or ''
    state = listing.get('state') or 'NC'

    parts = [address, city, state]
    raw = '-'.join(p for p in parts if p)

    # Replace spaces and special chars with hyphens, collapse multiples
    clean = re.sub(r'[^a-zA-Z0-9\-]', '-', raw)
    clean = re.sub(r'-+', '-', clean).strip('-')

    return f"{clean}.pdf"
