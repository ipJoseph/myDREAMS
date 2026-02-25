"""
PDF Property Package Generator

Generates branded PDF packages from property packages table.
Uses WeasyPrint for HTML to PDF conversion.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from apps.automation import config
from apps.automation.email_service import render_template

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

# Try to import WeasyPrint
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logger.warning("WeasyPrint not installed. PDF generation will be unavailable.")
    logger.warning("Install with: pip install weasyprint")

# PDF output directory
PDF_OUTPUT_DIR = config.DATA_DIR / 'pdfs'


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_package_data(package_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch package and associated property data.

    Args:
        package_id: The package ID to fetch

    Returns:
        Dictionary with package and property data, or None if not found
    """
    conn = get_db_connection()

    try:
        # Get package (using property_packages table)
        package = conn.execute('''
            SELECT
                p.id,
                p.lead_id,
                p.name as title,
                p.status,
                p.created_at,
                l.first_name,
                l.last_name,
                l.email
            FROM property_packages p
            JOIN leads l ON l.id = p.lead_id
            WHERE p.id = ?
        ''', [package_id]).fetchone()

        if not package:
            logger.error(f"Package {package_id} not found")
            return None

        package_dict = dict(package)

        # Get properties from package_properties join table
        props = conn.execute('''
            SELECT
                pr.id, pr.mls_number, pr.address, pr.city, pr.state, pr.zip, pr.county,
                pr.list_price as price, pr.beds, pr.baths, pr.sqft, pr.acreage, pr.year_built,
                pr.property_type, pr.style, pr.status, pr.views,
                pr.days_on_market, pr.heating, pr.cooling, pr.garage_spaces as garage,
                pr.photos as photo_urls, pr.primary_photo,
                pr.zillow_url, pr.redfin_url, pr.idx_url, pr.public_remarks as notes,
                pr.elevation_feet, pr.sold_price, pr.sold_date,
                pp.display_order, pp.agent_notes as package_notes
            FROM package_properties pp
            JOIN listings pr ON pr.id = pp.listing_id
            WHERE pp.package_id = ?
            ORDER BY pp.display_order, pp.added_at
        ''', [package_id]).fetchall()

        properties = []
        if props:

            for prop in props:
                prop_dict = dict(prop)

                # Parse photo URLs: prefer primary_photo, then first from photos JSON
                if prop_dict.get('primary_photo'):
                    prop_dict['photo_url'] = prop_dict['primary_photo']
                elif prop_dict.get('photo_urls'):
                    try:
                        photos = json.loads(prop_dict['photo_urls'])
                        prop_dict['photo_url'] = photos[0] if photos else None
                    except json.JSONDecodeError:
                        prop_dict['photo_url'] = None
                else:
                    prop_dict['photo_url'] = None

                # Use package_notes from join, or fall back to contact_properties
                if not prop_dict.get('package_notes'):
                    agent_notes = conn.execute('''
                        SELECT notes FROM contact_properties
                        WHERE contact_id = ? AND property_id = ?
                    ''', [package['lead_id'], prop_dict['id']]).fetchone()
                    prop_dict['agent_notes'] = agent_notes['notes'] if agent_notes else None
                else:
                    prop_dict['agent_notes'] = prop_dict.get('package_notes')

                prop_dict['description'] = None  # Could add later

                properties.append(prop_dict)

        package_dict['properties'] = properties
        package_dict['client_name'] = f"{package['first_name']} {package['last_name']}"

        return package_dict

    finally:
        conn.close()


def get_agent_branding() -> Dict[str, Any]:
    """Get agent branding info for PDFs."""
    return {
        'agent_name': config.AGENT_NAME,
        'agent_email': config.AGENT_EMAIL,
        'agent_phone': config.AGENT_PHONE,
        'agent_headshot': config.AGENT_HEADSHOT_URL,
        'brokerage_name': config.BROKERAGE_NAME,
        'brokerage_logo': config.BROKERAGE_LOGO_URL
    }


def render_package_html(package_id: str, layout: str = 'showcase') -> Optional[str]:
    """
    Render a property package as HTML.

    Args:
        package_id: The package ID to render
        layout: 'showcase' (1 property per page, default) or 'comparison' (side-by-side grid)

    Returns:
        HTML string or None if package not found
    """
    package_data = get_package_data(package_id)

    if not package_data:
        return None

    branding = get_agent_branding()

    # Build template context
    context = {
        **package_data,
        **branding,
        'package_date': datetime.now().strftime('%B %d, %Y'),
        'showing_date': package_data.get('showing_date', '')
    }

    template_name = 'property_package_comparison.html' if layout == 'comparison' else 'property_package.html'
    return render_template(template_name, **context)


def generate_pdf(package_id: str, output_path: Optional[str] = None, layout: str = 'showcase') -> Optional[str]:
    """
    Generate a PDF from a property package.

    Args:
        package_id: The package ID to generate PDF for
        output_path: Optional custom output path. If not provided,
                    saves to PDF_OUTPUT_DIR with auto-generated name.
        layout: 'showcase' (1 property per page) or 'comparison' (side-by-side grid)

    Returns:
        Path to generated PDF or None if failed
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint not available. Cannot generate PDF.")
        return None

    logger.info(f"Generating PDF for package {package_id} (layout={layout})")

    # Render HTML
    html_content = render_package_html(package_id, layout=layout)

    if not html_content:
        return None

    # Determine output path
    if output_path is None:
        PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Get package data for filename
        package_data = get_package_data(package_id)
        client_name = package_data['client_name'].replace(' ', '_')
        timestamp = datetime.now().strftime('%Y%m%d')
        output_path = str(PDF_OUTPUT_DIR / f"property_package_{client_name}_{timestamp}.pdf")

    try:
        # Generate PDF
        html = HTML(string=html_content, base_url=str(config.PROJECT_ROOT))
        html.write_pdf(output_path)

        logger.info(f"PDF generated: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}")
        return None


def generate_pdf_bytes(package_id: str, layout: str = 'showcase') -> Optional[bytes]:
    """
    Generate a PDF and return as bytes (for web serving).

    Args:
        package_id: The package ID to generate PDF for
        layout: 'showcase' (1 property per page) or 'comparison' (side-by-side grid)

    Returns:
        PDF as bytes or None if failed
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint not available. Cannot generate PDF.")
        return None

    # Render HTML
    html_content = render_package_html(package_id, layout=layout)

    if not html_content:
        return None

    try:
        html = HTML(string=html_content, base_url=str(config.PROJECT_ROOT))
        return html.write_pdf()

    except Exception as e:
        logger.error(f"Failed to generate PDF bytes: {e}")
        return None


def get_package_pdf_filename(package_id: str) -> str:
    """Generate a nice filename for the PDF download."""
    package_data = get_package_data(package_id)

    if package_data:
        client_name = package_data['client_name'].replace(' ', '_')
        title = (package_data.get('title') or 'Properties').replace(' ', '_')
        return f"{title}_{client_name}.pdf"

    return f"property_package_{package_id}.pdf"


def list_packages_for_contact(contact_id: str) -> List[Dict[str, Any]]:
    """List all packages for a contact."""
    conn = get_db_connection()

    try:
        packages = conn.execute('''
            SELECT
                p.id,
                p.name as title,
                p.status,
                p.created_at,
                COUNT(pp.listing_id) as property_count
            FROM property_packages p
            LEFT JOIN package_properties pp ON pp.package_id = p.id
            WHERE p.lead_id = ?
            GROUP BY p.id
            ORDER BY p.created_at DESC
        ''', [contact_id]).fetchall()

        results = []
        for pkg in packages:
            pkg_dict = dict(pkg)
            results.append(pkg_dict)

        return results

    finally:
        conn.close()


def main():
    """CLI entry point for testing."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_generator.py <package_id> [output_path] [--comparison]")
        sys.exit(1)

    package_id = sys.argv[1]
    layout = 'comparison' if '--comparison' in sys.argv else 'showcase'

    # Filter out flags to find output_path
    args = [a for a in sys.argv[2:] if not a.startswith('--')]
    output_path = args[0] if args else None

    result = generate_pdf(package_id, output_path, layout=layout)

    if result:
        print(f"PDF generated ({layout} layout): {result}")
        sys.exit(0)
    else:
        print("Failed to generate PDF")
        sys.exit(1)


if __name__ == '__main__':
    main()
