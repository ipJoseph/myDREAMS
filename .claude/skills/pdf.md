# PDF Lead Profile Skill

Generate professionally formatted PDF profiles for leads in the myDREAMS database.

## Overview

This skill creates visually appealing PDF reports for individual leads, including:
- Contact information
- Lead scores (heat, priority, relationship, value)
- Buying profile and budget
- Engagement statistics
- AI-generated insights
- Personalized recommendations

## Script Location

`scripts/generate_lead_pdf.py`

## Dependencies

- Python 3.x
- reportlab library (installed in `.venv`)

## Usage

### By Name
```bash
source .venv/bin/activate && python3 scripts/generate_lead_pdf.py "Steve Legg"
```

### By Email
```bash
source .venv/bin/activate && python3 scripts/generate_lead_pdf.py --email "steven.legg1022@gmail.com"
```

### By Lead ID
```bash
source .venv/bin/activate && python3 scripts/generate_lead_pdf.py --id "2e81caf3-59d4-4902-af21-c1ee9ae6f8ee"
```

## Output

PDFs are saved to: `output/<lead_name>_profile.pdf`

Example: `output/steve_legg_profile.pdf`

## PDF Contents

1. **Header** - Lead name and heat score indicator
2. **Contact Information** - Phone, email, stage, source, FUB ID
3. **Lead Scores** - Visual progress bars for heat, priority, relationship, value
4. **Buying Profile** - Budget range, avg price viewed, lead type, dates
5. **Engagement Statistics** - Website visits, properties viewed/favorited, communications
6. **Key Insights** - Auto-generated based on lead data
7. **Recommendation** - Suggested next action based on scores
8. **Footer** - Generation date and branding

## Customization

To modify the PDF format, edit `scripts/generate_lead_pdf.py`:
- Brand colors: Lines 41-44
- Styles: `create_styles()` function
- Insights logic: `generate_insights()` function
- Recommendations: In `build_pdf()` function

## Troubleshooting

If the script fails:
1. Ensure `.venv` exists: `python3 -m venv .venv`
2. Install reportlab: `source .venv/bin/activate && pip install reportlab`
3. Check lead exists in database: Use dreams-db MCP tools to verify
