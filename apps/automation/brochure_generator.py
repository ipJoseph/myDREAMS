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


def _generate_cover_pdf(collection: dict, properties: list[dict]) -> bytes | None:
    """
    Generate cover page + table of contents + optional map page as PDF bytes.
    """
    if not WEASYPRINT_AVAILABLE:
        return None

    branding = _get_agent_branding()

    prices = [p['list_price'] for p in properties if p.get('list_price') and p['list_price'] > 0]
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None

    # Build Google Static Maps URL if properties have coordinates
    map_url = None
    google_key = config.get_db_setting('google_maps_api_key', '')
    geo_props = [p for p in properties if p.get('latitude') and p.get('longitude')]
    if geo_props and google_key:
        markers = '|'.join(
            f'label:{i+1}|{p["latitude"]},{p["longitude"]}'
            for i, p in enumerate(geo_props[:15])  # max 15 markers
        )
        map_url = (
            f'https://maps.googleapis.com/maps/api/staticmap?'
            f'size=700x500&maptype=roadmap'
            f'&markers=color:0xC5A55A|{markers}'
            f'&key={google_key}'
        )

    # Get buyer name if available
    buyer_name = None
    if collection.get('lead_id'):
        conn = _get_db()
        lead = conn.execute(
            'SELECT first_name, last_name FROM leads WHERE id = ?',
            [collection['lead_id']]
        ).fetchone()
        conn.close()
        if lead:
            buyer_name = f"{lead['first_name'] or ''} {lead['last_name'] or ''}".strip()

    context = {
        **branding,
        'collection_name': collection.get('name') or 'Property Collection',
        'description': collection.get('description') or '',
        'cover_image': collection.get('cover_image') or '',
        'property_count': len(properties),
        'min_price': min_price,
        'max_price': max_price,
        'prepared_date': datetime.now().strftime('%B %d, %Y'),
        'buyer_name': buyer_name,
        'properties': properties,
        'map_url': map_url,
    }

    html_content = render_template('collection_cover.html', **context)
    try:
        html = HTML(string=html_content, base_url=str(config.PROJECT_ROOT))
        return html.write_pdf()
    except Exception as e:
        logger.error(f"Failed to generate cover PDF: {e}")
        return None


def _generate_comparison_pdf(collection: dict, properties: list[dict]) -> bytes | None:
    """
    Generate side-by-side comparison table as PDF bytes.
    Fits up to 6 properties per page (landscape).
    """
    if not WEASYPRINT_AVAILABLE:
        return None

    branding = _get_agent_branding()

    # Split into pages of 6
    max_per_page = 6
    property_pages = []
    for i in range(0, len(properties), max_per_page):
        page = properties[i:i + max_per_page]
        # Add 1-based index for display
        for j, prop in enumerate(page):
            prop['_index'] = i + j + 1
        property_pages.append(page)

    context = {
        **branding,
        'collection_name': collection.get('name') or 'Property Collection',
        'prepared_date': datetime.now().strftime('%B %d, %Y'),
        'property_pages': property_pages,
    }

    html_content = render_template('collection_comparison.html', **context)
    try:
        html = HTML(string=html_content, base_url=str(config.PROJECT_ROOT))
        return html.write_pdf()
    except Exception as e:
        logger.error(f"Failed to generate comparison PDF: {e}")
        return None


def generate_collection_pdf(share_token: str) -> tuple[bytes | None, str]:
    """
    Generate combined PDF for all properties in a collection.

    Structure:
    1. Cover page with collection name, stats, agent branding
    2. Table of contents
    3. Map overview page (if properties have coordinates)
    4. Individual property brochures
    5. Comparison table (landscape)

    Returns (pdf_bytes, collection_name) or (None, '') on failure.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint not available.")
        return None, ''

    conn = _get_db()
    try:
        # Get collection
        collection = conn.execute(
            'SELECT * FROM property_packages WHERE share_token = ?',
            [share_token]
        ).fetchone()

        if not collection:
            return None, ''

        collection_dict = dict(collection)
        collection_name = collection['name'] or 'Collection'

        # Get full listing data in order
        rows = conn.execute(
            '''SELECT l.*, pkp.display_order, pkp.agent_notes as pkg_agent_notes
               FROM package_properties pkp
               JOIN listings l ON l.id = pkp.listing_id
               WHERE pkp.package_id = ? AND l.idx_opt_in = 1
               ORDER BY pkp.display_order, pkp.added_at''',
            [collection['id']]
        ).fetchall()

        if not rows:
            return None, collection_name

        properties = []
        for r in rows:
            p = dict(r)
            # Use package agent_notes if set
            if p.get('pkg_agent_notes'):
                p['agent_notes'] = p['pkg_agent_notes']
            properties.append(p)

    finally:
        conn.close()

    listing_ids = [p['id'] for p in properties]

    import io
    try:
        import pypdf
    except ImportError:
        logger.warning("pypdf not installed. Generating without cover/comparison pages.")
        # Fallback: just concatenate brochures
        all_pdfs = []
        for lid in listing_ids:
            pdf_bytes = generate_brochure_bytes(lid)
            if pdf_bytes:
                all_pdfs.append(pdf_bytes)
        if not all_pdfs:
            return None, collection_name
        return all_pdfs[0] if len(all_pdfs) == 1 else all_pdfs[0], collection_name

    merger = pypdf.PdfWriter()

    # 1. Cover page + TOC + map
    cover_pdf = _generate_cover_pdf(collection_dict, properties)
    if cover_pdf:
        reader = pypdf.PdfReader(io.BytesIO(cover_pdf))
        for page in reader.pages:
            merger.add_page(page)

    # 2. Individual property brochures
    for lid in listing_ids:
        pdf_bytes = generate_brochure_bytes(lid)
        if pdf_bytes:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                merger.add_page(page)

    # 3. Comparison table at the end
    if len(properties) >= 2:
        comparison_pdf = _generate_comparison_pdf(collection_dict, properties)
        if comparison_pdf:
            reader = pypdf.PdfReader(io.BytesIO(comparison_pdf))
            for page in reader.pages:
                merger.add_page(page)

    if len(merger.pages) == 0:
        return None, collection_name

    output = io.BytesIO()
    merger.write(output)
    return output.getvalue(), collection_name


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
