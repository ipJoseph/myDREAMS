#!/usr/bin/env python3
"""
DREAMS Database MCP Server

Provides Claude Code with direct access to the myDREAMS SQLite database.
Supports querying leads, properties, activities, and generating reports.

Usage:
    python server.py

MCP Tools Exposed:
    - query_leads: Search and filter leads
    - query_properties: Search properties with criteria
    - query_activities: Get lead activity history
    - run_sql: Execute read-only SQL queries
    - get_stats: Get database statistics
    - match_leads_to_property: Find leads matching a property
    - get_lead_details: Get comprehensive lead information
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

# Initialize MCP server
server = Server("dreams-db")


def get_connection() -> sqlite3.Connection:
    """Get a read-only database connection."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    """Convert sqlite3.Row objects to dictionaries."""
    return [dict(row) for row in rows]


def format_results(rows: list[dict], limit: int = 50) -> str:
    """Format query results as readable text."""
    if not rows:
        return "No results found."

    # Truncate if too many results
    total = len(rows)
    if total > limit:
        rows = rows[:limit]

    result_lines = []
    for i, row in enumerate(rows, 1):
        result_lines.append(f"--- Result {i} ---")
        for key, value in row.items():
            if value is not None:
                result_lines.append(f"  {key}: {value}")

    if total > limit:
        result_lines.append(f"\n... and {total - limit} more results (showing first {limit})")

    return "\n".join(result_lines)


# =============================================================================
# MCP Tool Definitions
# =============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name="query_leads",
            description="""Search and filter leads/contacts in the database.

Examples:
- Find hot leads: min_heat=70
- Find buyers in a city: lead_type="buyer", city="Asheville"
- Find recently active: days_since_activity=7
- Find by stage: stage="active"
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Search term for name, email, or phone"
                    },
                    "stage": {
                        "type": "string",
                        "description": "Lead stage (lead, prospect, client, past_client, trash)"
                    },
                    "lead_type": {
                        "type": "string",
                        "description": "Lead type (buyer, seller, both, investor)"
                    },
                    "min_heat": {
                        "type": "integer",
                        "description": "Minimum heat score (0-100)"
                    },
                    "min_priority": {
                        "type": "integer",
                        "description": "Minimum priority score (0-100)"
                    },
                    "city": {
                        "type": "string",
                        "description": "Filter by preferred city"
                    },
                    "days_since_activity": {
                        "type": "integer",
                        "description": "Maximum days since last activity"
                    },
                    "assigned_to": {
                        "type": "string",
                        "description": "Filter by assigned agent"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 25)",
                        "default": 25
                    },
                    "order_by": {
                        "type": "string",
                        "description": "Sort field (priority_score, heat_score, updated_at)",
                        "default": "priority_score"
                    }
                }
            }
        ),
        Tool(
            name="query_properties",
            description="""Search properties in the database.

Examples:
- Find by city: city="Asheville"
- Find by price range: min_price=200000, max_price=400000
- Find active listings: status="active"
- Find by beds/baths: min_beds=3, min_baths=2
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Search term for address or MLS number"
                    },
                    "city": {
                        "type": "string",
                        "description": "City name"
                    },
                    "county": {
                        "type": "string",
                        "description": "County name"
                    },
                    "status": {
                        "type": "string",
                        "description": "Property status (active, pending, sold, off_market)"
                    },
                    "min_price": {
                        "type": "integer",
                        "description": "Minimum price"
                    },
                    "max_price": {
                        "type": "integer",
                        "description": "Maximum price"
                    },
                    "min_beds": {
                        "type": "integer",
                        "description": "Minimum bedrooms"
                    },
                    "min_baths": {
                        "type": "number",
                        "description": "Minimum bathrooms"
                    },
                    "min_sqft": {
                        "type": "integer",
                        "description": "Minimum square footage"
                    },
                    "min_acreage": {
                        "type": "number",
                        "description": "Minimum acreage"
                    },
                    "added_for": {
                        "type": "string",
                        "description": "Filter by client name (added_for field)"
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
            name="query_activities",
            description="""Get activity history for leads.

Examples:
- Get all activity for a lead: lead_id="abc123"
- Get recent website visits: activity_type="website_visit", days=7
- Get property views: activity_type="property_view"
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "string",
                        "description": "Specific lead ID"
                    },
                    "activity_type": {
                        "type": "string",
                        "description": "Activity type (website_visit, property_view, property_favorite, call, text, email)"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Limit to last N days",
                        "default": 30
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
            name="run_sql",
            description="""Execute a read-only SQL query against the database.

Only SELECT queries are allowed. Use this for custom queries not covered by other tools.

Available tables:
- leads: Contact/lead records with scoring
- lead_activities: Behavioral signals
- contact_events: Website visits, property views
- contact_communications: Calls, texts, emails
- contact_scoring_history: Score trends over time
- properties: Property listings
- property_changes: Price/status change history
- matches: Lead-property matching results
- intake_forms: Buyer requirement forms
- property_packages: Client property collections
- system_settings: Configuration values
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL SELECT query to execute"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum rows to return (default 100)",
                        "default": 100
                    }
                },
                "required": ["sql"]
            }
        ),
        Tool(
            name="get_stats",
            description="Get database statistics and summary metrics.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_lead_details",
            description="""Get comprehensive details for a specific lead.

Includes: contact info, scores, requirements, recent activity, matched properties.
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "string",
                        "description": "Lead ID (UUID or FUB ID)"
                    },
                    "email": {
                        "type": "string",
                        "description": "Lead email address"
                    },
                    "name": {
                        "type": "string",
                        "description": "Lead name (first or last)"
                    }
                }
            }
        ),
        Tool(
            name="match_leads_to_property",
            description="""Find leads whose requirements match a property.

Analyzes lead requirements and returns potential buyer matches.
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "property_id": {
                        "type": "string",
                        "description": "Property ID"
                    },
                    "address": {
                        "type": "string",
                        "description": "Property address"
                    },
                    "price": {
                        "type": "integer",
                        "description": "Property price"
                    },
                    "city": {
                        "type": "string",
                        "description": "Property city"
                    },
                    "beds": {
                        "type": "integer",
                        "description": "Number of bedrooms"
                    },
                    "min_match_score": {
                        "type": "integer",
                        "description": "Minimum match score (0-100)",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="get_call_list",
            description="""Generate today's priority call list.

Returns leads sorted by priority with contact info and context.
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum leads to return",
                        "default": 20
                    },
                    "min_priority": {
                        "type": "integer",
                        "description": "Minimum priority score",
                        "default": 30
                    }
                }
            }
        )
    ]


# =============================================================================
# Tool Implementations
# =============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""

    try:
        if name == "query_leads":
            result = await query_leads(arguments)
        elif name == "query_properties":
            result = await query_properties(arguments)
        elif name == "query_activities":
            result = await query_activities(arguments)
        elif name == "run_sql":
            result = await run_sql(arguments)
        elif name == "get_stats":
            result = await get_stats()
        elif name == "get_lead_details":
            result = await get_lead_details(arguments)
        elif name == "match_leads_to_property":
            result = await match_leads_to_property(arguments)
        elif name == "get_call_list":
            result = await get_call_list(arguments)
        else:
            result = f"Unknown tool: {name}"
    except Exception as e:
        result = f"Error: {str(e)}"

    return [TextContent(type="text", text=result)]


async def query_leads(args: dict) -> str:
    """Query leads with filters."""
    conn = get_connection()

    query = """
        SELECT
            id, first_name, last_name, email, phone,
            stage, type as lead_type,
            heat_score, value_score, relationship_score, priority_score,
            assigned_user_name,
            last_activity_at, updated_at
        FROM leads
        WHERE 1=1
    """
    params = []

    if args.get("search"):
        query += " AND (first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR phone LIKE ?)"
        search = f"%{args['search']}%"
        params.extend([search, search, search, search])

    if args.get("stage"):
        query += " AND stage = ?"
        params.append(args["stage"])

    if args.get("lead_type"):
        query += " AND type = ?"
        params.append(args["lead_type"])

    if args.get("min_heat"):
        query += " AND heat_score >= ?"
        params.append(args["min_heat"])

    if args.get("min_priority"):
        query += " AND priority_score >= ?"
        params.append(args["min_priority"])

    if args.get("city"):
        query += " AND preferred_cities LIKE ?"
        params.append(f"%{args['city']}%")

    if args.get("days_since_activity"):
        cutoff = (datetime.now() - timedelta(days=args["days_since_activity"])).isoformat()
        query += " AND last_activity_at >= ?"
        params.append(cutoff)

    if args.get("assigned_to"):
        query += " AND assigned_user_name LIKE ?"
        params.append(f"%{args['assigned_to']}%")

    order_by = args.get("order_by", "priority_score")
    if order_by in ["priority_score", "heat_score", "value_score", "updated_at"]:
        query += f" ORDER BY {order_by} DESC"

    limit = min(args.get("limit", 25), 100)
    query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return format_results(rows_to_dicts(rows), limit)


async def query_properties(args: dict) -> str:
    """Query properties with filters."""
    conn = get_connection()

    query = """
        SELECT
            id, address, city, state, zip, county,
            price, beds, baths, sqft, acreage,
            status, days_on_market, mls_number,
            listing_agent_name, added_for,
            created_at
        FROM properties
        WHERE 1=1
    """
    params = []

    if args.get("search"):
        query += " AND (address LIKE ? OR mls_number LIKE ?)"
        search = f"%{args['search']}%"
        params.extend([search, search])

    if args.get("city"):
        query += " AND city LIKE ?"
        params.append(f"%{args['city']}%")

    if args.get("county"):
        query += " AND county LIKE ?"
        params.append(f"%{args['county']}%")

    if args.get("status"):
        query += " AND status = ?"
        params.append(args["status"])

    if args.get("min_price"):
        query += " AND price >= ?"
        params.append(args["min_price"])

    if args.get("max_price"):
        query += " AND price <= ?"
        params.append(args["max_price"])

    if args.get("min_beds"):
        query += " AND beds >= ?"
        params.append(args["min_beds"])

    if args.get("min_baths"):
        query += " AND baths >= ?"
        params.append(args["min_baths"])

    if args.get("min_sqft"):
        query += " AND sqft >= ?"
        params.append(args["min_sqft"])

    if args.get("min_acreage"):
        query += " AND acreage >= ?"
        params.append(args["min_acreage"])

    if args.get("added_for"):
        query += " AND added_for LIKE ?"
        params.append(f"%{args['added_for']}%")

    query += " ORDER BY created_at DESC"

    limit = min(args.get("limit", 25), 100)
    query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return format_results(rows_to_dicts(rows), limit)


async def query_activities(args: dict) -> str:
    """Query lead activities."""
    conn = get_connection()

    query = """
        SELECT
            e.id, e.contact_id, e.event_type, e.event_source,
            e.property_address, e.event_data, e.occurred_at,
            l.first_name, l.last_name
        FROM contact_events e
        LEFT JOIN leads l ON e.contact_id = l.id
        WHERE 1=1
    """
    params = []

    if args.get("lead_id"):
        query += " AND e.contact_id = ?"
        params.append(args["lead_id"])

    if args.get("activity_type"):
        query += " AND e.event_type = ?"
        params.append(args["activity_type"])

    days = args.get("days", 30)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    query += " AND e.occurred_at >= ?"
    params.append(cutoff)

    query += " ORDER BY e.occurred_at DESC"

    limit = min(args.get("limit", 50), 200)
    query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return format_results(rows_to_dicts(rows), limit)


async def run_sql(args: dict) -> str:
    """Execute read-only SQL query."""
    sql = args.get("sql", "").strip()

    # Security: Only allow SELECT queries
    if not sql.upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."

    # Block dangerous keywords
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "ATTACH"]
    sql_upper = sql.upper()
    for keyword in dangerous:
        if keyword in sql_upper:
            return f"Error: {keyword} operations are not allowed."

    conn = get_connection()

    try:
        limit = min(args.get("limit", 100), 500)

        # Add LIMIT if not present
        if "LIMIT" not in sql.upper():
            sql += f" LIMIT {limit}"

        rows = conn.execute(sql).fetchall()
        conn.close()

        return format_results(rows_to_dicts(rows), limit)
    except Exception as e:
        conn.close()
        return f"SQL Error: {str(e)}"


async def get_stats() -> str:
    """Get database statistics."""
    conn = get_connection()

    stats = {}

    # Lead counts
    stats["total_leads"] = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    stats["active_leads"] = conn.execute("SELECT COUNT(*) FROM leads WHERE stage NOT IN ('trash', 'closed')").fetchone()[0]
    stats["hot_leads"] = conn.execute("SELECT COUNT(*) FROM leads WHERE heat_score >= 70").fetchone()[0]

    # Property counts
    stats["total_properties"] = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    stats["active_listings"] = conn.execute("SELECT COUNT(*) FROM properties WHERE status = 'active'").fetchone()[0]
    stats["pending_listings"] = conn.execute("SELECT COUNT(*) FROM properties WHERE status = 'pending'").fetchone()[0]

    # Activity counts
    stats["total_events"] = conn.execute("SELECT COUNT(*) FROM contact_events").fetchone()[0]
    stats["events_last_7_days"] = conn.execute(
        "SELECT COUNT(*) FROM contact_events WHERE occurred_at >= datetime('now', '-7 days')"
    ).fetchone()[0]

    # Communication counts
    stats["total_calls"] = conn.execute("SELECT COUNT(*) FROM contact_communications WHERE comm_type = 'call'").fetchone()[0]
    stats["total_texts"] = conn.execute("SELECT COUNT(*) FROM contact_communications WHERE comm_type = 'text'").fetchone()[0]

    # Scoring history
    stats["scoring_snapshots"] = conn.execute("SELECT COUNT(*) FROM contact_scoring_history").fetchone()[0]

    # Recent activity
    recent = conn.execute("""
        SELECT stage, COUNT(*) as count
        FROM leads
        GROUP BY stage
        ORDER BY count DESC
    """).fetchall()
    stats["leads_by_stage"] = {row[0]: row[1] for row in recent}

    conn.close()

    # Format output
    lines = ["=== DREAMS Database Statistics ===", ""]
    lines.append("LEADS:")
    lines.append(f"  Total: {stats['total_leads']}")
    lines.append(f"  Active: {stats['active_leads']}")
    lines.append(f"  Hot (heat >= 70): {stats['hot_leads']}")
    lines.append(f"  By Stage: {json.dumps(stats['leads_by_stage'])}")
    lines.append("")
    lines.append("PROPERTIES:")
    lines.append(f"  Total: {stats['total_properties']}")
    lines.append(f"  Active: {stats['active_listings']}")
    lines.append(f"  Pending: {stats['pending_listings']}")
    lines.append("")
    lines.append("ACTIVITY:")
    lines.append(f"  Total Events: {stats['total_events']}")
    lines.append(f"  Events (7 days): {stats['events_last_7_days']}")
    lines.append(f"  Total Calls: {stats['total_calls']}")
    lines.append(f"  Total Texts: {stats['total_texts']}")
    lines.append(f"  Scoring Snapshots: {stats['scoring_snapshots']}")

    return "\n".join(lines)


async def get_lead_details(args: dict) -> str:
    """Get comprehensive lead details."""
    conn = get_connection()

    # Find the lead
    if args.get("lead_id"):
        lead = conn.execute("SELECT * FROM leads WHERE id = ? OR fub_id = ?",
                           (args["lead_id"], args["lead_id"])).fetchone()
    elif args.get("email"):
        lead = conn.execute("SELECT * FROM leads WHERE email = ?",
                           (args["email"],)).fetchone()
    elif args.get("name"):
        lead = conn.execute("SELECT * FROM leads WHERE first_name LIKE ? OR last_name LIKE ?",
                           (f"%{args['name']}%", f"%{args['name']}%")).fetchone()
    else:
        conn.close()
        return "Error: Provide lead_id, email, or name to search."

    if not lead:
        conn.close()
        return "Lead not found."

    lead_dict = dict(lead)
    lead_id = lead_dict["id"]

    # Get recent activities
    activities = conn.execute("""
        SELECT event_type, property_address, occurred_at
        FROM contact_events
        WHERE contact_id = ?
        ORDER BY occurred_at DESC
        LIMIT 10
    """, (lead_id,)).fetchall()

    # Get communications
    comms = conn.execute("""
        SELECT comm_type, direction, agent_name, occurred_at
        FROM contact_communications
        WHERE contact_id = ?
        ORDER BY occurred_at DESC
        LIMIT 5
    """, (lead_id,)).fetchall()

    # Get requirements
    requirements = conn.execute("""
        SELECT * FROM contact_requirements WHERE contact_id = ?
    """, (lead_id,)).fetchone()

    conn.close()

    # Format output
    lines = [f"=== Lead Details: {lead_dict.get('first_name', '')} {lead_dict.get('last_name', '')} ===", ""]

    lines.append("CONTACT INFO:")
    lines.append(f"  ID: {lead_id}")
    lines.append(f"  Email: {lead_dict.get('email', 'N/A')}")
    lines.append(f"  Phone: {lead_dict.get('phone', 'N/A')}")
    lines.append(f"  Stage: {lead_dict.get('stage', 'N/A')}")
    lines.append(f"  Type: {lead_dict.get('type', 'N/A')}")
    lines.append(f"  Source: {lead_dict.get('source', 'N/A')}")
    lines.append(f"  Assigned To: {lead_dict.get('assigned_user_name', 'N/A')}")
    lines.append("")

    lines.append("SCORES:")
    lines.append(f"  Heat: {lead_dict.get('heat_score', 0)}")
    lines.append(f"  Value: {lead_dict.get('value_score', 0)}")
    lines.append(f"  Relationship: {lead_dict.get('relationship_score', 0)}")
    lines.append(f"  Priority: {lead_dict.get('priority_score', 0)}")
    lines.append("")

    if requirements:
        req = dict(requirements)
        lines.append("REQUIREMENTS:")
        if req.get('min_price') or req.get('max_price'):
            lines.append(f"  Price: ${req.get('min_price', 0):,} - ${req.get('max_price', 0):,}")
        if req.get('min_beds'):
            lines.append(f"  Beds: {req.get('min_beds')}+")
        if req.get('min_baths'):
            lines.append(f"  Baths: {req.get('min_baths')}+")
        if req.get('preferred_cities'):
            lines.append(f"  Cities: {req.get('preferred_cities')}")
        if req.get('preferred_counties'):
            lines.append(f"  Counties: {req.get('preferred_counties')}")
        lines.append("")

    if activities:
        lines.append("RECENT ACTIVITY:")
        for act in activities:
            lines.append(f"  {act[2][:10]}: {act[0]} - {act[1] or 'N/A'}")
        lines.append("")

    if comms:
        lines.append("RECENT COMMUNICATIONS:")
        for comm in comms:
            lines.append(f"  {comm[3][:10]}: {comm[0]} ({comm[1]}) - {comm[2] or 'N/A'}")

    return "\n".join(lines)


async def match_leads_to_property(args: dict) -> str:
    """Find leads whose requirements match a property."""
    conn = get_connection()

    price = args.get("price", 0)
    city = args.get("city", "")
    beds = args.get("beds", 0)
    min_score = args.get("min_match_score", 50)

    # Find leads with matching requirements
    query = """
        SELECT
            l.id, l.first_name, l.last_name, l.email, l.phone,
            l.heat_score, l.priority_score,
            r.min_price, r.max_price, r.min_beds, r.preferred_cities
        FROM leads l
        LEFT JOIN contact_requirements r ON l.id = r.contact_id
        WHERE l.stage NOT IN ('trash', 'closed')
        AND l.type IN ('buyer', 'both')
    """

    leads = conn.execute(query).fetchall()
    conn.close()

    matches = []
    for lead in leads:
        lead_dict = dict(lead)
        score = 0
        reasons = []

        # Price match (40 points)
        min_p = lead_dict.get("min_price") or 0
        max_p = lead_dict.get("max_price") or 999999999
        if min_p <= price <= max_p:
            score += 40
            reasons.append("price in range")
        elif price > 0 and max_p > 0:
            # Partial credit if close
            if price <= max_p * 1.1:
                score += 20
                reasons.append("price slightly over budget")

        # Location match (30 points)
        pref_cities = lead_dict.get("preferred_cities") or ""
        if city and city.lower() in pref_cities.lower():
            score += 30
            reasons.append("city match")

        # Beds match (20 points)
        min_beds = lead_dict.get("min_beds") or 0
        if beds >= min_beds:
            score += 20
            reasons.append("beds match")

        # Activity bonus (10 points)
        if lead_dict.get("heat_score", 0) >= 50:
            score += 10
            reasons.append("active buyer")

        if score >= min_score:
            matches.append({
                "lead_id": lead_dict["id"],
                "name": f"{lead_dict.get('first_name', '')} {lead_dict.get('last_name', '')}",
                "email": lead_dict.get("email"),
                "phone": lead_dict.get("phone"),
                "heat_score": lead_dict.get("heat_score", 0),
                "match_score": score,
                "reasons": ", ".join(reasons)
            })

    # Sort by match score
    matches.sort(key=lambda x: x["match_score"], reverse=True)

    if not matches:
        return "No matching leads found."

    lines = [f"=== Matching Leads (min score: {min_score}) ===", ""]
    for i, m in enumerate(matches[:20], 1):
        lines.append(f"{i}. {m['name']} (Score: {m['match_score']})")
        lines.append(f"   Email: {m['email']}, Phone: {m['phone']}")
        lines.append(f"   Heat: {m['heat_score']}, Reasons: {m['reasons']}")
        lines.append("")

    return "\n".join(lines)


async def get_call_list(args: dict) -> str:
    """Generate priority call list."""
    conn = get_connection()

    limit = args.get("limit", 20)
    min_priority = args.get("min_priority", 30)

    query = """
        SELECT
            l.id, l.first_name, l.last_name, l.email, l.phone,
            l.stage, l.type, l.source,
            l.heat_score, l.priority_score,
            l.last_activity_at, l.assigned_user_name,
            l.fub_id
        FROM leads l
        WHERE l.stage NOT IN ('trash', 'closed')
        AND l.priority_score >= ?
        AND l.phone IS NOT NULL
        ORDER BY l.priority_score DESC
        LIMIT ?
    """

    leads = conn.execute(query, (min_priority, limit)).fetchall()
    conn.close()

    if not leads:
        return f"No leads with priority >= {min_priority} found."

    lines = [f"=== Priority Call List (Top {len(leads)}) ===", ""]
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    for i, lead in enumerate(leads, 1):
        l = dict(lead)
        lines.append(f"{i}. {l.get('first_name', '')} {l.get('last_name', '')} (Priority: {l.get('priority_score', 0)})")
        lines.append(f"   Phone: {l.get('phone', 'N/A')}")
        lines.append(f"   Email: {l.get('email', 'N/A')}")
        lines.append(f"   Stage: {l.get('stage', 'N/A')} | Type: {l.get('type', 'N/A')} | Heat: {l.get('heat_score', 0)}")
        if l.get('last_activity_at'):
            lines.append(f"   Last Activity: {l.get('last_activity_at', '')[:10]}")
        if l.get('fub_id'):
            lines.append(f"   FUB: https://app.followupboss.com/2/people/view/{l.get('fub_id')}")
        lines.append("")

    return "\n".join(lines)


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
