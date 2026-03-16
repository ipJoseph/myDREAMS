# GWS Sheets Skill

Read and write Google Sheets data using the `gws` CLI.

## CLI Reference

```bash
# Get spreadsheet metadata (sheet names, properties)
gws sheets spreadsheets get --params '{"spreadsheetId": "SPREADSHEET_ID", "fields": "properties,sheets.properties"}'

# Read a range of cells
gws sheets spreadsheets values get --params '{"spreadsheetId": "SPREADSHEET_ID", "range": "Sheet1!A1:D10"}'

# Read entire sheet
gws sheets spreadsheets values get --params '{"spreadsheetId": "SPREADSHEET_ID", "range": "Sheet1"}'

# Read with formatted values
gws sheets spreadsheets values get --params '{"spreadsheetId": "SPREADSHEET_ID", "range": "Sheet1!A:Z", "valueRenderOption": "FORMATTED_VALUE"}'

# Write to a range
gws sheets spreadsheets values update --params '{"spreadsheetId": "SPREADSHEET_ID", "range": "Sheet1!A1", "valueInputOption": "USER_ENTERED"}' --json '{"values": [["Header1", "Header2"], ["val1", "val2"]]}'

# Append rows to a sheet
gws sheets spreadsheets values append --params '{"spreadsheetId": "SPREADSHEET_ID", "range": "Sheet1!A:Z", "valueInputOption": "USER_ENTERED"}' --json '{"values": [["new1", "new2"], ["new3", "new4"]]}'

# Clear a range
gws sheets spreadsheets values clear --params '{"spreadsheetId": "SPREADSHEET_ID", "range": "Sheet1!A1:D10"}'

# Batch read multiple ranges
gws sheets spreadsheets values batchGet --params '{"spreadsheetId": "SPREADSHEET_ID", "ranges": ["Sheet1!A1:B5", "Sheet2!A1:C3"]}'

# Batch update multiple ranges
gws sheets spreadsheets values batchUpdate --params '{"spreadsheetId": "SPREADSHEET_ID", "valueInputOption": "USER_ENTERED"}' --json '{"data": [{"range": "Sheet1!A1", "values": [["v1"]]}, {"range": "Sheet2!A1", "values": [["v2"]]}]}'

# Create a new spreadsheet
gws sheets spreadsheets create --json '{"properties": {"title": "My New Sheet"}}'
```

## Range Syntax

| Format | Meaning |
|--------|---------|
| Sheet1!A1:D10 | Specific rectangle |
| Sheet1!A:D | Entire columns A through D |
| Sheet1!1:5 | Entire rows 1 through 5 |
| Sheet1 | Entire sheet |
| A1:D10 | First sheet, specific range |

## Value Input Options

- `USER_ENTERED` - Parse values as if typed by a user (formulas executed, dates parsed)
- `RAW` - Store values exactly as provided (no parsing)

## Finding a Spreadsheet ID

The spreadsheet ID is in the URL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`

Or search Drive for spreadsheets:
```bash
gws drive files list --params '{"q": "mimeType = '\''application/vnd.google-apps.spreadsheet'\'' and name contains '\''search term'\''", "fields": "files(id,name,modifiedTime)"}'
```

## Instructions

When the user asks to read or write spreadsheet data:

1. If they provide a URL, extract the spreadsheet ID from it
2. If they give a name, search Drive for the spreadsheet first
3. Get sheet metadata first to know available sheet names
4. Read data and present it in a clean table format
5. For writes: ALWAYS confirm the target range and data with the user before writing
6. Use `FORMATTED_VALUE` render option for human-readable output

$ARGUMENTS - Optional: spreadsheet ID/URL, sheet name, range, or action (read, write, append, create)
