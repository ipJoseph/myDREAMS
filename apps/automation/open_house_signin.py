"""
Open House Sign-In Sheet Generator

Generates a branded PDF sign-in sheet with columns for Name, Email, and Phone.
Uses the same DREAMS branding (navy/gold) as the tour schedule PDFs.

Uses WeasyPrint for HTML-to-PDF conversion.
"""

import base64
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logger.warning("WeasyPrint not installed. PDF generation unavailable.")

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets" / "branding"
LOGO_PATH = ASSETS_DIR / "jth-icon.jpg"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Load .env
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"\''))

# Branding
NAVY = "#082d40"
GOLD = "#ddab4a"
GRAY = "#4e4e4e"

AGENT = {
    "name": os.environ.get("AGENT_NAME", "Joseph Williams"),
    "phone": os.environ.get("AGENT_PHONE", "(828) 347-9363"),
    "email": os.environ.get("AGENT_EMAIL", "Joseph@JonTharpHomes.com"),
    "website": os.environ.get("AGENT_WEBSITE", "www.JonTharpHomes.com"),
}

NUM_ROWS = 20  # sign-in rows per page


def _load_base64(path: Path) -> str:
    if path.exists():
        data = path.read_bytes()
        ext = path.suffix.lower().replace('.', '')
        if ext == 'jpg':
            ext = 'jpeg'
        return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
    return ""


def generate_signin_sheet(address: str = "", date: str = "", output_path: str = None) -> Optional[bytes]:
    """Generate an open house sign-in sheet PDF.

    Args:
        address: Property address (shown in header)
        date: Open house date (shown in header)
        output_path: If provided, write PDF to this path and return the path.
                     Otherwise return PDF bytes.
    """
    if not WEASYPRINT_AVAILABLE:
        logger.error("WeasyPrint not installed")
        return None

    logo_b64 = _load_base64(LOGO_PATH)
    logo_img = f'<img src="{logo_b64}" class="logo">' if logo_b64 else ''

    # Build sign-in rows
    rows_html = ""
    for i in range(1, NUM_ROWS + 1):
        rows_html += f"""
        <tr>
            <td class="row-num">{i}</td>
            <td class="input-cell"></td>
            <td class="input-cell"></td>
            <td class="input-cell"></td>
        </tr>"""

    address_display = address or "Property Address"
    date_display = date or ""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: letter;
    margin: 0.4in 0.5in 0.6in 0.5in;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    color: {GRAY};
    font-size: 12px;
    line-height: 1.4;
}}

/* Header */
.header {{
    text-align: center;
    padding-bottom: 12px;
    margin-bottom: 8px;
    border-bottom: 3px solid {GOLD};
}}
.header h1 {{
    font-size: 28px;
    font-weight: 800;
    color: {NAVY};
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 4px;
}}
.header .subtitle {{
    font-size: 14px;
    font-weight: 600;
    color: {GOLD};
    letter-spacing: 2px;
    text-transform: uppercase;
}}
.header .address {{
    font-size: 16px;
    font-weight: 700;
    color: {NAVY};
    margin-top: 10px;
}}
.header .date {{
    font-size: 13px;
    color: {GRAY};
    margin-top: 2px;
}}
.logo {{
    height: 40px;
    width: auto;
    margin-bottom: 6px;
}}

/* Welcome text */
.welcome {{
    text-align: center;
    font-size: 12px;
    color: {GRAY};
    margin: 10px 0 14px 0;
    font-style: italic;
}}

/* Sign-in table */
.signin-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 4px;
}}
.signin-table thead th {{
    background: {NAVY};
    color: white;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 10px 12px;
    text-align: left;
    border: 1px solid {NAVY};
}}
.signin-table thead th:first-child {{
    width: 36px;
    text-align: center;
    padding: 10px 6px;
}}
.signin-table thead th.name-col {{
    width: 40%;
}}
.signin-table thead th.email-col {{
    width: 35%;
}}
.signin-table thead th.phone-col {{
    width: 25%;
}}
.signin-table td {{
    border: 1px solid #ccc;
    padding: 0;
    height: 32px;
    vertical-align: middle;
}}
.signin-table .row-num {{
    text-align: center;
    font-size: 11px;
    font-weight: 600;
    color: {GOLD};
    background: #fafafa;
    width: 36px;
}}
.signin-table .input-cell {{
    padding: 4px 8px;
}}
.signin-table tr:nth-child(even) td {{
    background: #fafbfc;
}}
.signin-table tr:nth-child(even) .row-num {{
    background: #f5f5f5;
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
    border-top: 2px solid {GOLD};
    font-size: 10px;
    color: {GRAY};
}}
.footer-info {{
    display: flex;
    gap: 6px;
    align-items: center;
}}
</style>
</head>
<body>

<div class="header">
    {logo_img}
    <h1>Open House</h1>
    <div class="subtitle">Sign-In Sheet</div>
    <div class="address">{_escape(address_display)}</div>
    {"<div class='date'>" + _escape(date_display) + "</div>" if date_display else ""}
</div>

<div class="welcome">
    Welcome! Please sign in below. We look forward to helping you find your perfect mountain home.
</div>

<table class="signin-table">
    <thead>
        <tr>
            <th>#</th>
            <th class="name-col">Name</th>
            <th class="email-col">Email Address</th>
            <th class="phone-col">Phone</th>
        </tr>
    </thead>
    <tbody>
        {rows_html}
    </tbody>
</table>

<div class="footer">
    <div class="footer-info">
        {AGENT['name']} | {AGENT['phone']} | {AGENT['email']} | {AGENT['website']}
    </div>
</div>

</body>
</html>"""

    pdf_bytes = HTML(string=html).write_pdf()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(pdf_bytes)
        logger.info(f"Sign-in sheet saved: {output_path}")
        return output_path

    return pdf_bytes


def _escape(text: str) -> str:
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


if __name__ == "__main__":
    import sys
    address = sys.argv[1] if len(sys.argv) > 1 else ""
    date = sys.argv[2] if len(sys.argv) > 2 else ""
    out = str(REPORTS_DIR / "open-house-signin.pdf")
    generate_signin_sheet(address=address, date=date, output_path=out)
    print(f"Generated: {out}")
