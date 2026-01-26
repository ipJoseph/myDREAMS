# myDREAMS MCP Servers

Model Context Protocol (MCP) servers providing Claude Code with direct access to myDREAMS data and external services.

## Available Servers

### dreams-db
SQLite database access for leads, properties, activities, and analytics.

**Tools:**
- `query_leads` - Search and filter leads with scoring
- `query_properties` - Search properties by criteria
- `query_activities` - Get lead activity history
- `run_sql` - Execute read-only SQL queries
- `get_stats` - Database statistics and metrics
- `get_lead_details` - Comprehensive lead information
- `match_leads_to_property` - Find matching buyers
- `get_call_list` - Priority call list for today

### fub
Follow Up Boss CRM API access.

**Tools:**
- `search_people` - Search contacts in FUB
- `get_person` - Get detailed person info
- `create_note` - Add notes to contacts
- `get_calls` - Recent call records
- `get_events` - Activity events (views, visits)
- `get_users` - Team members
- `get_recent_leads` - New leads
- `update_person_stage` - Update pipeline stage

## Installation

1. Install dependencies:
```bash
cd /home/bigeug/myDREAMS
source .venv/bin/activate
pip install -r mcp-servers/requirements.txt
```

2. MCP servers are configured in `.mcp.json` and enabled in `.claude/settings.json`

3. Restart Claude Code to load the servers

## Manual Testing

Test the dreams-db server:
```bash
cd mcp-servers/dreams-db
./run.sh
```

Test the fub server:
```bash
cd mcp-servers/fub
./run.sh
```

## Configuration

Environment variables are loaded from `/home/bigeug/myDREAMS/.env`:
- `DREAMS_DB_PATH` - Path to SQLite database
- `FUB_API_KEY` - Follow Up Boss API key
- `FUB_BASE_URL` - FUB API base URL (default: https://api.followupboss.com/v1)

## Usage Examples

Once enabled, use natural language in Claude Code:

```
"Show me hot leads with heat score over 70"
→ Uses dreams-db.query_leads

"Find properties in Asheville under $400k"
→ Uses dreams-db.query_properties

"Get John Smith's contact details from FUB"
→ Uses fub.search_people + fub.get_person

"Add a note to lead 12345 about our call today"
→ Uses fub.create_note
```

## Adding New Servers

1. Create directory: `mcp-servers/new-server/`
2. Create `server.py` implementing MCP protocol
3. Create `run.sh` to launch the server
4. Add to `.mcp.json`
5. Add to `.claude/settings.json` enabledMcpjsonServers

## Troubleshooting

**Server won't start:**
- Check Python dependencies: `pip install -r requirements.txt`
- Verify environment variables in `.env`
- Check run.sh is executable: `chmod +x run.sh`

**Database errors:**
- Verify `DREAMS_DB_PATH` points to valid database
- Check file permissions on `data/dreams.db`

**FUB API errors:**
- Verify `FUB_API_KEY` is set and valid
- Check rate limits (429 responses)
