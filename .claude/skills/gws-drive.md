# GWS Drive Skill

Manage Google Drive files and folders using the `gws` CLI.

## CLI Reference

```bash
# List files (most recent first)
gws drive files list --params '{"pageSize": 10, "orderBy": "modifiedTime desc", "fields": "files(id,name,mimeType,modifiedTime,size)"}'

# Search files by name
gws drive files list --params '{"q": "name contains '\''search term'\''", "pageSize": 20, "fields": "files(id,name,mimeType,modifiedTime)"}'

# Search by type
gws drive files list --params '{"q": "mimeType = '\''application/vnd.google-apps.spreadsheet'\''", "pageSize": 10}'

# Search in a specific folder
gws drive files list --params '{"q": "'\''FOLDER_ID'\'' in parents", "pageSize": 20}'

# Get file metadata
gws drive files get --params '{"fileId": "FILE_ID", "fields": "id,name,mimeType,modifiedTime,size,webViewLink"}'

# Download/export a file
gws drive files get --params '{"fileId": "FILE_ID", "alt": "media"}' --output /path/to/output

# Export Google Doc as PDF
gws drive files export --params '{"fileId": "FILE_ID", "mimeType": "application/pdf"}' --output /path/to/output.pdf

# Upload a file
gws drive files create --json '{"name": "filename.txt", "parents": ["FOLDER_ID"]}' --upload /path/to/file

# Create a folder
gws drive files create --json '{"name": "New Folder", "mimeType": "application/vnd.google-apps.folder"}'

# Move a file (add new parent, remove old)
gws drive files update --params '{"fileId": "FILE_ID", "addParents": "NEW_FOLDER_ID", "removeParents": "OLD_FOLDER_ID"}'

# Auto-paginate through all results
gws drive files list --params '{"pageSize": 100, "q": "trashed=false"}' --page-all --page-limit 5
```

## Common MIME Types

| Type | MIME |
|------|------|
| Google Doc | application/vnd.google-apps.document |
| Google Sheet | application/vnd.google-apps.spreadsheet |
| Google Slides | application/vnd.google-apps.presentation |
| Folder | application/vnd.google-apps.folder |
| PDF | application/pdf |

## Query Syntax (for the `q` parameter)

- `name contains 'term'` - file name contains term
- `mimeType = 'type'` - exact MIME type match
- `'FOLDER_ID' in parents` - files in a folder
- `trashed = false` - exclude trashed files
- `modifiedTime > '2026-01-01T00:00:00'` - modified after date
- Combine with `and`: `name contains 'report' and mimeType = 'application/pdf'`

## Notes

- If you get a 403 "insufficient scopes" error, the Drive scope may need to be re-authorized. Run `gws auth login` and approve the Drive scope.
- Always include `fields` parameter to limit response size.
- Use `--page-all` for large result sets.
- Default output format is JSON. Use `--format table` for readable output.

## Instructions

When the user asks to find, search, list, download, upload, or manage files in Google Drive:

1. Clarify what they need if the request is ambiguous
2. Run the appropriate `gws drive` command
3. Present results clearly (file name, link, date, size)
4. For downloads, confirm the output path

$ARGUMENTS - Optional: search query, file ID, or action (list, search, upload, download)
