# GWS Calendar Skill

Manage Google Calendar events using the `gws` CLI.

## CLI Reference

```bash
# List calendars
gws calendar calendarList list --params '{"maxResults": 50}'

# List upcoming events (primary calendar)
gws calendar events list --params '{"calendarId": "primary", "timeMin": "2026-03-16T00:00:00Z", "maxResults": 10, "singleEvents": true, "orderBy": "startTime"}'

# List events for a date range
gws calendar events list --params '{"calendarId": "primary", "timeMin": "2026-03-16T00:00:00Z", "timeMax": "2026-03-23T00:00:00Z", "singleEvents": true, "orderBy": "startTime"}'

# List today's events
gws calendar events list --params '{"calendarId": "primary", "timeMin": "2026-03-16T00:00:00Z", "timeMax": "2026-03-17T00:00:00Z", "singleEvents": true, "orderBy": "startTime"}'

# Search events by text
gws calendar events list --params '{"calendarId": "primary", "q": "showing", "singleEvents": true, "orderBy": "startTime", "maxResults": 20}'

# Get a specific event
gws calendar events get --params '{"calendarId": "primary", "eventId": "EVENT_ID"}'

# Create an event
gws calendar events insert --params '{"calendarId": "primary"}' --json '{
  "summary": "Property Showing",
  "location": "123 Main St, Asheville, NC",
  "description": "Showing for buyer client",
  "start": {"dateTime": "2026-03-17T14:00:00", "timeZone": "America/New_York"},
  "end": {"dateTime": "2026-03-17T15:00:00", "timeZone": "America/New_York"}
}'

# Create an event with attendees
gws calendar events insert --params '{"calendarId": "primary", "sendUpdates": "all"}' --json '{
  "summary": "Meeting",
  "start": {"dateTime": "2026-03-17T10:00:00", "timeZone": "America/New_York"},
  "end": {"dateTime": "2026-03-17T11:00:00", "timeZone": "America/New_York"},
  "attendees": [{"email": "person@example.com"}]
}'

# Create an all-day event
gws calendar events insert --params '{"calendarId": "primary"}' --json '{
  "summary": "Closing Day",
  "start": {"date": "2026-03-20"},
  "end": {"date": "2026-03-21"}
}'

# Update an event
gws calendar events update --params '{"calendarId": "primary", "eventId": "EVENT_ID"}' --json '{
  "summary": "Updated Title",
  "start": {"dateTime": "2026-03-17T15:00:00", "timeZone": "America/New_York"},
  "end": {"dateTime": "2026-03-17T16:00:00", "timeZone": "America/New_York"}
}'

# Delete an event
gws calendar events delete --params '{"calendarId": "primary", "eventId": "EVENT_ID"}'

# List events from a specific calendar (use calendar ID from calendarList)
gws calendar events list --params '{"calendarId": "CALENDAR_ID", "timeMin": "2026-03-16T00:00:00Z", "singleEvents": true, "orderBy": "startTime", "maxResults": 10}'
```

## Known Calendars

- `primary` - Main calendar
- Follow Up Boss calendar (check `calendarList list` for the ID)

## Time Zone

All times should use `America/New_York` (Eastern) unless specified otherwise.

## Instructions

When the user asks about their schedule, events, or wants to create/modify calendar events:

1. Use today's date for relative references ("today", "tomorrow", "this week")
2. Always use `singleEvents: true` and `orderBy: startTime` for readable output
3. Present events with: time, title, location (if set), and attendees (if any)
4. For creating events: confirm details (title, time, location, attendees) before creating
5. For deleting/modifying: confirm the specific event with the user first
6. Default to `primary` calendar unless the user specifies otherwise

$ARGUMENTS - Optional: date, search query, event ID, or action (today, week, create, search)
