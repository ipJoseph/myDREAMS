# Report Formatting Guide

Standard branding and layout rules for all printable reports and forms in myDREAMS.

All printed reports must look like professionally branded documents from Jon Tharp Homes, not raw browser output.

## Branding Assets

| Asset | Path | Format |
|-------|------|--------|
| Logo | `assets/branding/jth-icon.jpg` | Base64-encoded inline for print |
| Colors | See below | CSS values |
| Agent Info | Environment variables | Pipe-separated in footer |

## Color Palette

| Name | Hex | Usage |
|------|-----|-------|
| Navy | `#082d40` | Headings, table headers, borders |
| Gold | `#ddab4a` | Subtitle text, dividers, accents, row numbers |
| Gray | `#4e4e4e` | Body text, secondary info |
| Light gray | `#fafbfc` | Alternating table rows |
| White | `#ffffff` | Background |

## Page Setup

```css
@page {
    size: letter;
    margin: 0.4in 0.5in 0.6in 0.5in;
}
```

- Always set `@page` margins in print CSS to control the printable area
- Use `letter` size (8.5 x 11 in) as default

## Header Layout

Every printed report must have a centered branded header:

1. **Logo** (44px height, centered)
2. **Title** (28px, 800 weight, navy, uppercase, 3px letter-spacing)
3. **Subtitle** (14px, 600 weight, gold, uppercase, 2px letter-spacing)
4. **Context line** (15px, 700 weight, navy; e.g., property address, report title)
5. **Date line** (12px, gray)
6. **Gold divider** (3px solid `#ddab4a`, full width, below header)

```html
<div class="print-header">
    <img src="{{ logo_b64 }}" class="print-logo">
    <h2>REPORT TITLE</h2>
    <div class="print-subtitle">Jon Tharp Homes</div>
    <div class="context">Context-specific info</div>
    <div class="date">Date</div>
</div>
```

## Footer Layout

Fixed to bottom of every printed page:

- Gold top border (2px solid `#ddab4a`)
- Agent info centered, pipe-separated, 10px font, gray
- Format: `Name | Phone | Email | Website`

```css
.print-footer {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    text-align: center;
    padding-top: 10px;
    border-top: 2px solid #ddab4a;
    font-size: 10px;
    color: #4e4e4e;
}
```

## Agent Info (Environment Variables)

| Variable | Default |
|----------|---------|
| `AGENT_NAME` | Joseph Williams |
| `AGENT_PHONE` | (828) 347-9363 |
| `AGENT_EMAIL` | Joseph@JonTharpHomes.com |
| `AGENT_WEBSITE` | www.JonTharpHomes.com |

Load in route and pass to template:

```python
import base64
logo_path = PROJECT_ROOT / 'assets' / 'branding' / 'jth-icon.jpg'
logo_b64 = ''
if logo_path.exists():
    logo_data = logo_path.read_bytes()
    logo_b64 = f"data:image/jpeg;base64,{base64.b64encode(logo_data).decode()}"

agent_info = {
    'name': os.environ.get('AGENT_NAME', 'Joseph Williams'),
    'phone': os.environ.get('AGENT_PHONE', '(828) 347-9363'),
    'email': os.environ.get('AGENT_EMAIL', 'Joseph@JonTharpHomes.com'),
    'website': os.environ.get('AGENT_WEBSITE', 'www.JonTharpHomes.com'),
}
```

## Table Styling

| Element | Style |
|---------|-------|
| Header row | Navy background (`#082d40`), white text, uppercase, 1px letter-spacing |
| Body rows | Alternating white / `#fafbfc` |
| Row numbers | Gold text (`#ddab4a`), small font |
| Cell borders | `1px solid #e5e5e5` |
| Cell padding | 8-10px |

Must use `-webkit-print-color-adjust: exact` and `print-color-adjust: exact` for backgrounds to render in print.

## Print CSS Rules

Every report template must include these print overrides:

```css
@media print {
    /* Page margins */
    @page { margin: 0.4in 0.5in 0.6in 0.5in; }

    /* Clean background */
    body { background: white !important; }

    /* Hide dashboard UI */
    .sidebar, .sidebar-toggle, .sidebar-overlay { display: none !important; }
    .main-content { margin-left: 0 !important; }

    /* Hide interactive elements */
    .no-print, button, .header-actions { display: none !important; }

    /* Show branded header/footer */
    .print-header { display: block !important; }
    .print-footer { display: block !important; }

    /* Force print colors */
    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
```

## Hide On-Screen Header in Print

The on-screen header (with edit fields, buttons) should be hidden in print. The branded `print-header` replaces it:

```css
@media print {
    .expense-header { display: none !important; }
    .save-banner { display: none !important; }
}
```

## Existing Reports Using This Standard

| Report | Route | Template |
|--------|-------|----------|
| Open House Sign-In | `/reports/open-house-signin` | `apps/automation/open_house_signin.py` (WeasyPrint PDF) |
| Expense Report | `/expenses/<id>` | `templates/expense_form.html` (HTML print) |

## Checklist for New Reports

- [ ] Logo loaded as base64, passed to template
- [ ] Agent info from env vars, passed to template
- [ ] Centered print header with logo, title, subtitle, gold divider
- [ ] Fixed footer with gold top border and agent info
- [ ] `@page` margins set
- [ ] Dashboard sidebar and buttons hidden in print
- [ ] Table headers use navy background
- [ ] Alternating row backgrounds
- [ ] `-webkit-print-color-adjust: exact` on colored elements
- [ ] Tested in browser print preview (Ctrl+P)
