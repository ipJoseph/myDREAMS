# GWS Gmail Skill

Read, search, and send email using the `gws` CLI.

## CLI Reference

```bash
# List recent messages
gws gmail users messages list --params '{"userId": "me", "maxResults": 10}'

# Search messages (Gmail search syntax)
gws gmail users messages list --params '{"userId": "me", "q": "from:someone@example.com", "maxResults": 10}'

# Search by subject
gws gmail users messages list --params '{"userId": "me", "q": "subject:MLS update", "maxResults": 10}'

# Search unread
gws gmail users messages list --params '{"userId": "me", "q": "is:unread", "maxResults": 10}'

# Search with date range
gws gmail users messages list --params '{"userId": "me", "q": "after:2026/03/01 before:2026/03/16", "maxResults": 20}'

# Get a specific message (full content)
gws gmail users messages get --params '{"userId": "me", "id": "MESSAGE_ID", "format": "full"}'

# Get message metadata only (headers: From, To, Subject, Date)
gws gmail users messages get --params '{"userId": "me", "id": "MESSAGE_ID", "format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]}'

# Send an email
gws gmail users messages send --params '{"userId": "me"}' --json '{"raw": "BASE64_ENCODED_RFC2822"}'

# List labels
gws gmail users labels list --params '{"userId": "me"}'

# Get messages by label
gws gmail users messages list --params '{"userId": "me", "labelIds": ["INBOX"], "maxResults": 10}'

# Trash a message
gws gmail users messages trash --params '{"userId": "me", "id": "MESSAGE_ID"}'

# Mark as read
gws gmail users messages modify --params '{"userId": "me", "id": "MESSAGE_ID"}' --json '{"removeLabelIds": ["UNREAD"]}'
```

## Gmail Search Operators (for the `q` parameter)

| Operator | Example | Meaning |
|----------|---------|---------|
| from: | from:jane@example.com | Sender |
| to: | to:john@example.com | Recipient |
| subject: | subject:showing | Subject contains |
| has:attachment | has:attachment | Has attachments |
| is:unread | is:unread | Unread messages |
| is:starred | is:starred | Starred |
| after: | after:2026/03/01 | After date |
| before: | before:2026/03/16 | Before date |
| label: | label:important | Has label |
| filename: | filename:pdf | Attachment name |

Combine operators: `from:client@example.com subject:offer after:2026/03/01`

## Sending Email

To send email, you need to construct an RFC 2822 message and base64url-encode it:

```bash
# Construct and send
echo -e "From: joseph@integritypursuits.com\nTo: recipient@example.com\nSubject: Your Subject\nContent-Type: text/plain; charset=utf-8\n\nEmail body here." | base64 -w 0 | tr '+/' '-_' | tr -d '=' > /tmp/email_encoded.txt
gws gmail users messages send --params '{"userId": "me"}' --json "{\"raw\": \"$(cat /tmp/email_encoded.txt)\"}"
```

## Instructions

When the user asks to read, search, or send email:

1. For reading/searching: run the list command with appropriate query, then fetch individual messages for details
2. For sending: ALWAYS confirm the recipient, subject, and body with the user before sending
3. Parse message headers (From, To, Subject, Date) from the response payload for clean display
4. Message bodies are base64-encoded in the API response; decode with `base64 -d` if needed
5. NEVER send email without explicit user confirmation of the content

$ARGUMENTS - Optional: search query, message ID, or action (inbox, search, send, read)
