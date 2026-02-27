#!/usr/bin/env python3
"""
Follow Up Boss MCP Server

Provides Claude Code with direct access to the Follow Up Boss CRM API.
Supports querying people, creating notes, and managing leads.

Usage:
    FUB_API_KEY=your_key python server.py

MCP Tools Exposed:
    - search_people: Search contacts in FUB
    - get_person: Get detailed person info
    - create_note: Add a note to a person
    - get_calls: Get recent call records
    - get_events: Get activity events
    - get_users: Get team members
"""

import base64
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from tenacity import retry, stop_after_attempt, wait_exponential

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Configuration
FUB_API_KEY = os.getenv('FUB_API_KEY')
FUB_BASE_URL = os.getenv('FUB_BASE_URL', 'https://api.followupboss.com/v1')

# Initialize MCP server
server = Server("fub")


def get_auth_header() -> dict:
    """Get authorization header for FUB API."""
    if not FUB_API_KEY:
        raise ValueError("FUB_API_KEY environment variable not set")
    credentials = base64.b64encode(f"{FUB_API_KEY}:".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
async def fub_request(method: str, endpoint: str, params: dict = None, json_data: dict = None) -> dict:
    """Make a request to the FUB API with retry logic."""
    url = f"{FUB_BASE_URL}/{endpoint}"
    headers = get_auth_header()

    async with httpx.AsyncClient(timeout=30) as client:
        if method == "GET":
            response = await client.get(url, headers=headers, params=params)
        elif method == "POST":
            response = await client.post(url, headers=headers, json=json_data)
        elif method == "PUT":
            response = await client.put(url, headers=headers, json=json_data)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if response.status_code == 429:
            # Rate limited - raise to trigger retry
            raise Exception("Rate limited by FUB API")

        response.raise_for_status()
        return response.json()


def format_person(person: dict) -> str:
    """Format a person record for display."""
    lines = []
    name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
    lines.append(f"Name: {name or 'N/A'}")
    lines.append(f"ID: {person.get('id', 'N/A')}")

    if person.get('emails'):
        emails = [e.get('value', '') for e in person['emails']]
        lines.append(f"Email: {', '.join(emails)}")

    if person.get('phones'):
        phones = [f"{p.get('value', '')} ({p.get('type', '')})" for p in person['phones']]
        lines.append(f"Phone: {', '.join(phones)}")

    lines.append(f"Stage: {person.get('stage', 'N/A')}")
    lines.append(f"Source: {person.get('source', 'N/A')}")

    if person.get('assignedTo'):
        lines.append(f"Assigned To: {person.get('assignedTo', 'N/A')}")

    if person.get('tags'):
        lines.append(f"Tags: {', '.join(person['tags'])}")

    if person.get('created'):
        lines.append(f"Created: {person.get('created', '')[:10]}")

    return "\n".join(lines)


# =============================================================================
# MCP Tool Definitions
# =============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name="search_people",
            description="""Search for contacts in Follow Up Boss.

Examples:
- Search by name: query="John Smith"
- Search by email: query="john@example.com"
- Search by phone: query="8285551234"
- Filter by stage: stage="Lead"
- Filter by source: source="Zillow"
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (name, email, or phone)"
                    },
                    "stage": {
                        "type": "string",
                        "description": "Filter by stage (Lead, Prospect, Active Client, Past Client, etc.)"
                    },
                    "source": {
                        "type": "string",
                        "description": "Filter by lead source"
                    },
                    "assignedTo": {
                        "type": "string",
                        "description": "Filter by assigned user ID"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 25)",
                        "default": 25
                    }
                }
            }
        ),
        Tool(
            name="get_person",
            description="Get detailed information about a specific person by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "integer",
                        "description": "The FUB person ID"
                    }
                },
                "required": ["person_id"]
            }
        ),
        Tool(
            name="create_note",
            description="""Create a note on a person's record.

Use this to log important information, conversation summaries, or action items.
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "integer",
                        "description": "The FUB person ID"
                    },
                    "subject": {
                        "type": "string",
                        "description": "Note subject/title"
                    },
                    "body": {
                        "type": "string",
                        "description": "Note content"
                    }
                },
                "required": ["person_id", "body"]
            }
        ),
        Tool(
            name="get_calls",
            description="""Get recent call records.

Returns call log entries with duration, outcome, and associated contacts.
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "integer",
                        "description": "Filter by person ID"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Get calls from last N days (default 7)",
                        "default": 7
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 50)",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="get_events",
            description="""Get activity events (website visits, property views, etc.).

Shows behavioral signals from lead activity.
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "integer",
                        "description": "Filter by person ID"
                    },
                    "event_type": {
                        "type": "string",
                        "description": "Filter by event type (PropertyViewed, PropertyFavorited, Registration, etc.)"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Get events from last N days (default 7)",
                        "default": 7
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 50)",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="get_users",
            description="Get list of team members/users in the FUB account.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_recent_leads",
            description="""Get recently created or updated leads.

Shows new leads that need attention.
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Get leads from last N days (default 3)",
                        "default": 3
                    },
                    "stage": {
                        "type": "string",
                        "description": "Filter by stage"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 25)",
                        "default": 25
                    }
                }
            }
        ),
        Tool(
            name="update_person_stage",
            description="""Update a person's stage in the pipeline.

Common stages: Lead, Prospect, Active Client, Past Client, Trash
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "integer",
                        "description": "The FUB person ID"
                    },
                    "stage": {
                        "type": "string",
                        "description": "New stage value"
                    }
                },
                "required": ["person_id", "stage"]
            }
        )
    ]


# =============================================================================
# Tool Implementations
# =============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""

    if not FUB_API_KEY:
        return [TextContent(type="text", text="Error: FUB_API_KEY not configured")]

    try:
        if name == "search_people":
            result = await search_people(arguments)
        elif name == "get_person":
            result = await get_person(arguments)
        elif name == "create_note":
            result = await create_note(arguments)
        elif name == "get_calls":
            result = await get_calls(arguments)
        elif name == "get_events":
            result = await get_events(arguments)
        elif name == "get_users":
            result = await get_users()
        elif name == "get_recent_leads":
            result = await get_recent_leads(arguments)
        elif name == "update_person_stage":
            result = await update_person_stage(arguments)
        else:
            result = f"Unknown tool: {name}"
    except Exception as e:
        result = f"Error: {str(e)}"

    return [TextContent(type="text", text=result)]


async def search_people(args: dict) -> str:
    """Search for people in FUB."""
    params = {
        "limit": min(args.get("limit", 25), 100),
        "includeTrash": "false"
    }

    if args.get("query"):
        params["query"] = args["query"]
    if args.get("stage"):
        params["stage"] = args["stage"]
    if args.get("source"):
        params["source"] = args["source"]
    if args.get("assignedTo"):
        params["assignedTo"] = args["assignedTo"]

    data = await fub_request("GET", "people", params=params)
    people = data.get("people", [])

    if not people:
        return "No people found matching your criteria."

    lines = [f"=== Found {len(people)} People ===", ""]

    for i, person in enumerate(people, 1):
        lines.append(f"--- {i}. ---")
        lines.append(format_person(person))
        lines.append("")

    return "\n".join(lines)


async def get_person(args: dict) -> str:
    """Get detailed person info."""
    person_id = args.get("person_id")
    if not person_id:
        return "Error: person_id is required"

    data = await fub_request("GET", f"people/{person_id}")

    lines = ["=== Person Details ===", ""]
    lines.append(format_person(data))

    # Add more details if available
    if data.get('addresses'):
        lines.append("")
        lines.append("Addresses:")
        for addr in data['addresses']:
            parts = [addr.get('street', ''), addr.get('city', ''), addr.get('state', ''), addr.get('code', '')]
            lines.append(f"  {', '.join(p for p in parts if p)}")

    if data.get('price'):
        lines.append("")
        lines.append(f"Budget: ${data.get('price', 0):,}")

    if data.get('background'):
        lines.append("")
        lines.append(f"Background: {data.get('background', '')[:500]}")

    # FUB link
    lines.append("")
    lines.append(f"FUB Link: https://app.followupboss.com/2/people/view/{person_id}")

    return "\n".join(lines)


async def create_note(args: dict) -> str:
    """Create a note on a person."""
    person_id = args.get("person_id")
    body = args.get("body")

    if not person_id or not body:
        return "Error: person_id and body are required"

    note_data = {
        "personId": person_id,
        "body": body
    }

    if args.get("subject"):
        note_data["subject"] = args["subject"]

    await fub_request("POST", "notes", json_data=note_data)

    try:
        from src.core.fub_audit import log_fub_write
        log_fub_write(module='mcp_server', operation='create_note',
                      endpoint='notes', http_method='POST',
                      fub_person_id=person_id,
                      payload_summary=body[:200] if body else None)
    except Exception:
        pass

    return f"Note created successfully on person {person_id}"


async def get_calls(args: dict) -> str:
    """Get call records."""
    params = {
        "limit": min(args.get("limit", 50), 100)
    }

    if args.get("person_id"):
        params["personId"] = args["person_id"]

    days = args.get("days", 7)
    since = (datetime.now() - timedelta(days=days)).isoformat()
    params["dateFrom"] = since[:10]

    data = await fub_request("GET", "calls", params=params)
    calls = data.get("calls", [])

    if not calls:
        return f"No calls found in the last {days} days."

    lines = [f"=== Recent Calls ({len(calls)}) ===", ""]

    for call in calls:
        lines.append(f"Date: {call.get('created', '')[:16]}")
        lines.append(f"  Person: {call.get('personName', 'Unknown')}")
        lines.append(f"  Duration: {call.get('duration', 0)} seconds")
        lines.append(f"  Outcome: {call.get('outcome', 'N/A')}")
        lines.append(f"  Agent: {call.get('userName', 'N/A')}")
        if call.get('note'):
            lines.append(f"  Note: {call.get('note', '')[:100]}...")
        lines.append("")

    return "\n".join(lines)


async def get_events(args: dict) -> str:
    """Get activity events."""
    params = {
        "limit": min(args.get("limit", 50), 100)
    }

    if args.get("person_id"):
        params["personId"] = args["person_id"]

    if args.get("event_type"):
        params["type"] = args["event_type"]

    days = args.get("days", 7)
    since = (datetime.now() - timedelta(days=days)).isoformat()
    params["dateFrom"] = since[:10]

    data = await fub_request("GET", "events", params=params)
    events = data.get("events", [])

    if not events:
        return f"No events found in the last {days} days."

    lines = [f"=== Activity Events ({len(events)}) ===", ""]

    for event in events:
        lines.append(f"Date: {event.get('created', '')[:16]}")
        lines.append(f"  Type: {event.get('type', 'N/A')}")
        lines.append(f"  Person: {event.get('personName', 'Unknown')}")
        if event.get('property'):
            lines.append(f"  Property: {event.get('property', '')}")
        lines.append("")

    return "\n".join(lines)


async def get_users() -> str:
    """Get team members."""
    data = await fub_request("GET", "users")
    users = data.get("users", [])

    if not users:
        return "No users found."

    lines = ["=== Team Members ===", ""]

    for user in users:
        lines.append(f"Name: {user.get('name', 'N/A')}")
        lines.append(f"  ID: {user.get('id', 'N/A')}")
        lines.append(f"  Email: {user.get('email', 'N/A')}")
        lines.append(f"  Role: {user.get('role', 'N/A')}")
        lines.append("")

    return "\n".join(lines)


async def get_recent_leads(args: dict) -> str:
    """Get recently created leads."""
    days = args.get("days", 3)
    since = (datetime.now() - timedelta(days=days)).isoformat()

    params = {
        "limit": min(args.get("limit", 25), 100),
        "sort": "-created",
        "createdAfter": since[:10]
    }

    if args.get("stage"):
        params["stage"] = args["stage"]

    data = await fub_request("GET", "people", params=params)
    people = data.get("people", [])

    if not people:
        return f"No new leads in the last {days} days."

    lines = [f"=== New Leads (Last {days} Days) ===", ""]

    for i, person in enumerate(people, 1):
        lines.append(f"{i}. {person.get('firstName', '')} {person.get('lastName', '')}")
        lines.append(f"   Created: {person.get('created', '')[:10]}")
        lines.append(f"   Source: {person.get('source', 'N/A')}")
        if person.get('emails'):
            lines.append(f"   Email: {person['emails'][0].get('value', '')}")
        if person.get('phones'):
            lines.append(f"   Phone: {person['phones'][0].get('value', '')}")
        lines.append("")

    return "\n".join(lines)


async def update_person_stage(args: dict) -> str:
    """Update person's stage."""
    person_id = args.get("person_id")
    stage = args.get("stage")

    if not person_id or not stage:
        return "Error: person_id and stage are required"

    await fub_request("PUT", f"people/{person_id}", json_data={"stage": stage})

    try:
        from src.core.fub_audit import log_fub_write
        log_fub_write(module='mcp_server', operation='update_stage',
                      endpoint=f'people/{person_id}', http_method='PUT',
                      fub_person_id=person_id,
                      payload_summary=f'stage={stage}')
    except Exception:
        pass

    return f"Updated person {person_id} to stage '{stage}'"


# =============================================================================
# Main Entry Point
# =============================================================================

async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
