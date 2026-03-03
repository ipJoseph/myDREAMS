---
description: Generate lead profile PDF
---

# PDF Lead Profile Generator

Generate a professionally formatted PDF profile for any lead in the database.

## Usage

```
/pdf <lead name>
/pdf Katie Boggs
/pdf Steve Legg
```

## Instructions

1. Parse the lead name from $ARGUMENTS
2. Run the PDF generator script using the project's virtual environment:
   ```bash
   source .venv/bin/activate && python3 scripts/generate_lead_pdf.py "$ARGUMENTS"
   ```
3. Report the output file path to the user
4. Offer to open the PDF with `xdg-open`

## Alternative Search Methods

If the name doesn't match, try:
- By email: `python3 scripts/generate_lead_pdf.py --email "email@example.com"`
- By ID: `python3 scripts/generate_lead_pdf.py --id "lead-id"`

## Output

PDFs are saved to: `output/<lead_name>_profile.pdf`

## Argument

$ARGUMENTS - Required: Lead name (e.g., "Steve Legg", "Katie Boggs")
