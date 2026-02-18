#!/usr/bin/env python3
"""
Call Activity Report Generator

Generates an HTML report of call activity for any date range.
Reads from DREAMS SQLite database, converts UTC to Eastern time,
resolves contact names via leads table.

Usage:
    # Auto-detect previous completed week (Mon-Sun):
    python3 generate_calls_report.py

    # Specific week starting on a Monday:
    python3 generate_calls_report.py --week-start 2026-02-09

    # Arbitrary date range:
    python3 generate_calls_report.py --start-date 2026-02-10 --end-date 2026-02-14

    # Single day:
    python3 generate_calls_report.py --start-date 2026-02-12

    # Custom DB path:
    python3 generate_calls_report.py --db /path/to/dreams.db
"""

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict, OrderedDict
import html as html_mod

# Resolve paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_DB = os.path.join(PROJECT_ROOT, "data", "dreams.db")
DEFAULT_OUTPUT_DIR = SCRIPT_DIR  # reports/ directory

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def get_eastern_offset(dt_date):
    """Return UTC offset for US Eastern time on a given date.
    EST = UTC-5 (Nov-Mar), EDT = UTC-4 (Mar-Nov).
    DST starts 2nd Sunday in March, ends 1st Sunday in November.
    """
    year = dt_date.year

    # 2nd Sunday in March
    mar1 = date(year, 3, 1)
    dst_start = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7)

    # 1st Sunday in November
    nov1 = date(year, 11, 1)
    dst_end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)

    if dst_start <= dt_date < dst_end:
        return timedelta(hours=-4), "EDT"
    else:
        return timedelta(hours=-5), "EST"


def get_previous_monday():
    """Get the Monday of the most recently completed Mon-Sun week."""
    today = date.today()
    days_since_monday = today.weekday()  # 0 for Monday
    if days_since_monday == 0:
        return today - timedelta(days=7)
    else:
        return today - timedelta(days=days_since_monday + 7)


def parse_utc(ts_str):
    """Parse a UTC timestamp string to datetime."""
    return datetime.fromisoformat(ts_str.rstrip("Z"))


def format_duration(seconds):
    """Format duration in seconds to M:SS or H:MM:SS string."""
    if seconds is None or seconds == 0:
        return None
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_duration_long(seconds):
    """Format duration for summary display (e.g. '3h 22m 15s')."""
    if seconds is None or seconds == 0:
        return "0m 0s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0 or h > 0:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def format_duration_short(seconds):
    """Format duration for summary cards (e.g. '3h 22m')."""
    if seconds is None or seconds == 0:
        return "0m"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def format_time_12h(dt):
    """Format a datetime to 12-hour time string like '9:14 AM'."""
    return dt.strftime("%-I:%M %p")


def esc(text):
    """HTML-escape a string."""
    return html_mod.escape(str(text))


def _build_report_title(start_date, end_date):
    """Build human-readable title and subtitle for a date range."""
    single_day = (start_date == end_date)

    if single_day:
        day_name = start_date.strftime('%A')
        month = MONTH_NAMES[start_date.month]
        date_range_html = f"{day_name}, {month} {start_date.day}, {start_date.year}"
        title_range = f"{month[:3]} {start_date.day}, {start_date.year}"
        report_title = "Call Activity Report"
    else:
        start_month = MONTH_NAMES[start_date.month]
        end_month = MONTH_NAMES[end_date.month]
        if start_date.month == end_date.month:
            date_range_html = f"{start_month} {start_date.day}&ndash;{end_date.day}, {start_date.year}"
            title_range = f"{start_month[:3]} {start_date.day}-{end_date.day}, {start_date.year}"
        else:
            date_range_html = f"{start_month} {start_date.day} &ndash; {end_month} {end_date.day}, {start_date.year}"
            title_range = f"{start_month[:3]} {start_date.day} - {end_month[:3]} {end_date.day}, {start_date.year}"
        report_title = "Call Activity Report"

    return report_title, date_range_html, title_range


def _build_output_filename(start_date, end_date, output_dir):
    """Build the output filename based on date range."""
    if start_date == end_date:
        filename = f"calls-{start_date.isoformat()}.html"
    else:
        filename = f"calls-{start_date.isoformat()}-to-{end_date.isoformat()}.html"
    return os.path.join(output_dir, filename)


def generate_date_range_report(db_path, start_date, end_date, output_dir):
    """Generate a call report for an arbitrary date range.

    Args:
        db_path: Path to DREAMS SQLite database
        start_date: First day of the range (date object)
        end_date: Last day of the range, inclusive (date object)
        output_dir: Directory to write the HTML file

    Returns:
        Path to the generated HTML file

    Raises:
        ValueError: If dates are invalid or range exceeds 90 days
        FileNotFoundError: If database doesn't exist
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    if end_date < start_date:
        raise ValueError(f"end_date ({end_date}) is before start_date ({start_date})")

    range_days = (end_date - start_date).days + 1
    if range_days > 90:
        raise ValueError(f"Date range of {range_days} days exceeds 90-day maximum")

    single_day = (start_date == end_date)
    query_end = end_date + timedelta(days=1)  # exclusive upper bound

    # Determine Eastern timezone for this range
    et_offset, et_label = get_eastern_offset(start_date)

    # Build output path
    os.makedirs(output_dir, exist_ok=True)
    output_file = _build_output_filename(start_date, end_date, output_dir)

    # Query
    query = """
    SELECT
        cc.occurred_at,
        cc.direction,
        cc.duration_seconds,
        cc.status,
        cc.contact_id,
        COALESCE(l.first_name || ' ' || l.last_name, '[FUB #' || cc.contact_id || ']') as name
    FROM contact_communications cc
    LEFT JOIN leads l ON CAST(cc.contact_id AS TEXT) = CAST(l.fub_id AS TEXT)
    WHERE cc.comm_type = 'call'
    AND cc.occurred_at >= ? AND cc.occurred_at < ?
    ORDER BY cc.occurred_at
    """

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(query, (start_date.isoformat(), query_end.isoformat()))
    rows = cur.fetchall()
    conn.close()

    # Parse all calls, converting to Eastern time
    calls = []
    for occurred_at, direction, duration, status, contact_id, name in rows:
        utc_dt = parse_utc(occurred_at)
        et_dt = utc_dt + et_offset
        calls.append({
            "utc_dt": utc_dt,
            "et_dt": et_dt,
            "et_date": et_dt.date(),
            "direction": direction,
            "duration": duration if duration else 0,
            "status": status,
            "contact_id": contact_id,
            "name": name,
        })

    # Summary stats
    total_calls = len(calls)
    outbound = sum(1 for c in calls if c["direction"] == "outbound")
    inbound = sum(1 for c in calls if c["direction"] == "inbound")
    connected = sum(1 for c in calls if c["status"] == "completed")
    total_duration = sum(c["duration"] for c in calls)

    # Dynamic date iteration for the range
    range_dates = [start_date + timedelta(days=i) for i in range(range_days)]

    daily_stats = OrderedDict()
    for d in range_dates:
        daily_stats[d] = {
            "made": 0, "received": 0, "total": 0,
            "connected": 0, "no_answer": 0, "duration": 0,
        }

    for c in calls:
        d = c["et_date"]
        if d in daily_stats:
            daily_stats[d]["total"] += 1
            if c["direction"] == "outbound":
                daily_stats[d]["made"] += 1
            else:
                daily_stats[d]["received"] += 1
            if c["status"] == "completed":
                daily_stats[d]["connected"] += 1
            elif c["status"] in ("No Answer", "Left Message", "Bad Number"):
                daily_stats[d]["no_answer"] += 1
            daily_stats[d]["duration"] += c["duration"]

    # Group calls by Eastern date
    calls_by_date = defaultdict(list)
    for c in calls:
        calls_by_date[c["et_date"]].append(c)

    # Format helpers
    def day_short(d):
        return f"{DAY_ABBR[d.weekday()]} {d.month}/{d.day}"

    def day_full(d):
        return f"{d.strftime('%A')}, {MONTH_NAMES[d.month]} {d.day}"

    # Title and subtitle
    report_title, date_range_html, title_range = _build_report_title(start_date, end_date)
    et_offset_str = "4" if et_label == "EDT" else "5"

    # ---- Build HTML ----
    html_parts = []

    html_parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(report_title)} | {title_range}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f8fafc;
            color: #1a1a1a;
            padding: 32px;
            max-width: 1000px;
            margin: 0 auto;
        }}
        h1 {{
            font-size: 26px;
            font-weight: 800;
            margin-bottom: 4px;
        }}
        .subtitle {{
            font-size: 14px;
            color: #64748b;
            margin-bottom: 32px;
        }}
        .section-title {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 14px;
            margin-top: 36px;
        }}

        /* Summary Cards */
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 14px;
            margin-bottom: 12px;
        }}
        .summary-card {{
            background: white;
            border-radius: 10px;
            padding: 18px 16px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }}
        .summary-card .value {{
            font-size: 32px;
            font-weight: 800;
            line-height: 1;
            margin-bottom: 4px;
        }}
        .summary-card .label {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #64748b;
        }}
        .total .value {{ color: #1e3a5f; }}
        .outbound .value {{ color: #2563eb; }}
        .inbound .value {{ color: #16a34a; }}
        .connected .value {{ color: #7c3aed; }}
        .duration .value {{ color: #ea580c; font-size: 24px; }}

        /* Summary Table */
        .summary-table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            margin-bottom: 32px;
        }}
        .summary-table th {{
            background: #f8fafc;
            padding: 10px 14px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #64748b;
            text-align: center;
            border-bottom: 2px solid #e2e8f0;
        }}
        .summary-table th:first-child {{ text-align: left; }}
        .summary-table td {{
            padding: 10px 14px;
            font-size: 14px;
            text-align: center;
            border-bottom: 1px solid #f1f5f9;
        }}
        .summary-table td:first-child {{
            text-align: left;
            font-weight: 600;
        }}
        .summary-table tr:last-child td {{
            border-bottom: none;
        }}
        .summary-table .total-row {{
            background: #f0f9ff;
            font-weight: 700;
        }}
        .summary-table .total-row td {{ border-top: 2px solid #bfdbfe; }}
        .summary-table .weekend td {{ color: #94a3b8; }}

        /* Detail Table */
        .detail-table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            font-size: 13px;
        }}
        .detail-table th {{
            background: #f8fafc;
            padding: 9px 12px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #64748b;
            text-align: left;
            border-bottom: 2px solid #e2e8f0;
            position: sticky;
            top: 0;
        }}
        .detail-table td {{
            padding: 8px 12px;
            border-bottom: 1px solid #f1f5f9;
            vertical-align: middle;
        }}
        .detail-table tr:hover {{ background: #f8fafc; }}

        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
        }}
        .badge.outbound {{ background: #eff6ff; color: #2563eb; }}
        .badge.inbound {{ background: #f0fdf4; color: #16a34a; }}
        .badge.no-answer {{ color: #d97706; }}
        .badge.bad-number {{ color: #dc2626; }}
        .badge.left-message {{ color: #7c3aed; }}

        .day-divider td {{
            background: #f1f5f9;
            font-weight: 700;
            font-size: 12px;
            color: #475569;
            padding: 6px 12px;
        }}

        .duration-bar {{
            display: inline-block;
            height: 6px;
            background: #3b82f6;
            border-radius: 3px;
            margin-left: 6px;
            vertical-align: middle;
            opacity: 0.5;
        }}

        .footer {{
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
            margin-top: 32px;
            padding-top: 16px;
            border-top: 1px solid #e2e8f0;
        }}

        @media print {{
            body {{ padding: 16px; }}
            .detail-table th {{ position: static; }}
        }}
    </style>
</head>
<body>
""")

    # Title
    html_parts.append(f"""
<h1>{esc(report_title)}</h1>
<p class="subtitle">Joseph Williams | {date_range_html} | All times {et_label} (UTC&minus;{et_offset_str}) | Source: FUB via DREAMS</p>
""")

    # Summary Cards
    html_parts.append(f"""
<!-- Summary Cards -->
<div class="summary-grid">
    <div class="summary-card total">
        <div class="value">{total_calls}</div>
        <div class="label">Total Calls</div>
    </div>
    <div class="summary-card outbound">
        <div class="value">{outbound}</div>
        <div class="label">Made</div>
    </div>
    <div class="summary-card inbound">
        <div class="value">{inbound}</div>
        <div class="label">Received</div>
    </div>
    <div class="summary-card connected">
        <div class="value">{connected}</div>
        <div class="label">Connected</div>
    </div>
    <div class="summary-card duration">
        <div class="value">{format_duration_short(total_duration)}</div>
        <div class="label">Total Talk Time</div>
    </div>
</div>
""")

    # Daily Summary Table (skip for single-day reports)
    if not single_day:
        html_parts.append("""
<!-- Daily Summary Table -->
<h2 class="section-title">Daily Summary</h2>
<table class="summary-table">
    <thead>
        <tr>
            <th>Day</th>
            <th>Made</th>
            <th>Received</th>
            <th>Total</th>
            <th>Connected</th>
            <th>No Answer</th>
            <th>Talk Time</th>
        </tr>
    </thead>
    <tbody>
""")

        sum_made = sum_received = sum_total = 0
        sum_connected = sum_no_answer = sum_duration = 0

        for d in range_dates:
            s = daily_stats[d]
            label = day_short(d)
            is_weekend = d.weekday() >= 5

            sum_made += s["made"]
            sum_received += s["received"]
            sum_total += s["total"]
            sum_connected += s["connected"]
            sum_no_answer += s["no_answer"]
            sum_duration += s["duration"]

            row_class = ' class="weekend"' if is_weekend else ""
            talk_time = format_duration_long(s["duration"]) if s["duration"] > 0 else "&#8212;"

            html_parts.append(f"""        <tr{row_class}>
            <td>{esc(label)}</td>
            <td>{s["made"]}</td>
            <td>{s["received"]}</td>
            <td>{s["total"]}</td>
            <td>{s["connected"]}</td>
            <td>{s["no_answer"]}</td>
            <td>{talk_time}</td>
        </tr>
""")

        total_label = "Total" if range_days != 7 else "Week Total"
        html_parts.append(f"""        <tr class="total-row">
            <td>{total_label}</td>
            <td>{sum_made}</td>
            <td>{sum_received}</td>
            <td>{sum_total}</td>
            <td>{sum_connected}</td>
            <td>{sum_no_answer}</td>
            <td>{format_duration_long(sum_duration)}</td>
        </tr>
    </tbody>
</table>
""")

    # Detail Table
    html_parts.append(f"""
<!-- Detail Table -->
<h2 class="section-title">Call Detail Log</h2>
<table class="detail-table">
    <thead>
        <tr>
            <th>Date</th>
            <th>Time ({et_label})</th>
            <th>Direction</th>
            <th>Contact</th>
            <th>Status</th>
            <th>Duration</th>
        </tr>
    </thead>
    <tbody>
""")

    max_dur = max((c["duration"] for c in calls), default=1)
    LONG_CALL_THRESHOLD = 600  # 10 minutes

    for d in range_dates:
        day_calls = calls_by_date.get(d, [])
        html_parts.append(f'        <tr class="day-divider"><td colspan="6">{esc(day_full(d))}</td></tr>\n')

        if not day_calls:
            html_parts.append('        <tr><td colspan="6" style="color:#94a3b8; font-style:italic; text-align:center; padding:8px;">No calls</td></tr>\n')
            continue

        for c in day_calls:
            et = c["et_dt"]
            date_short_str = f"{et.month}/{et.day}"
            time_str = format_time_12h(et)

            if c["direction"] == "outbound":
                dir_badge = '<span class="badge outbound">Made</span>'
            else:
                dir_badge = '<span class="badge inbound">Received</span>'

            contact_name = esc(c["name"])

            status_raw = c["status"]
            if status_raw == "completed":
                status_html = "completed"
            elif status_raw == "No Answer":
                status_html = '<span class="badge no-answer">No Answer</span>'
            elif status_raw == "Left Message":
                status_html = '<span class="badge left-message">Left VM</span>'
            elif status_raw == "Bad Number":
                status_html = '<span class="badge bad-number">Bad Number</span>'
            else:
                status_html = esc(status_raw)

            dur_secs = c["duration"]
            if dur_secs and dur_secs > 0:
                dur_str = format_duration(dur_secs)
                if dur_secs >= LONG_CALL_THRESHOLD:
                    bar_width = max(10, int(60 * dur_secs / max_dur))
                    dur_str += f' <span class="duration-bar" style="width:{bar_width}px;"></span>'
            else:
                dur_str = "&#8212;"

            html_parts.append(
                f'        <tr>'
                f'<td>{date_short_str}</td>'
                f'<td>{time_str}</td>'
                f'<td>{dir_badge}</td>'
                f'<td>{contact_name}</td>'
                f'<td>{status_html}</td>'
                f'<td>{dur_str}</td>'
                f'</tr>\n'
            )

    now_str = datetime.now().strftime("%B %d, %Y at %-I:%M %p")
    html_parts.append(f"""    </tbody>
</table>

<div class="footer">
    Generated by DREAMS on {now_str} | All times {et_label} (UTC&minus;{et_offset_str})<br>
    Data source: Follow Up Boss call log synced to DREAMS database
</div>

</body>
</html>
""")

    html_content = "".join(html_parts)
    with open(output_file, "w") as f:
        f.write(html_content)

    return output_file


def generate_report(db_path, week_start, output_dir):
    """Generate the weekly call report for the week starting at week_start (Monday).

    Backward-compatible wrapper around generate_date_range_report().
    """
    if week_start.weekday() != 0:
        raise ValueError(f"{week_start} is not a Monday (weekday={week_start.weekday()})")

    week_end = week_start + timedelta(days=6)  # Sunday (inclusive)
    output_file = generate_date_range_report(db_path, week_start, week_end, output_dir)

    # Print summary for CLI usage
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    query_end = week_start + timedelta(days=7)
    cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN direction='outbound' THEN 1 ELSE 0 END),
               SUM(CASE WHEN direction='inbound' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),
               COALESCE(SUM(duration_seconds), 0)
        FROM contact_communications
        WHERE comm_type = 'call' AND occurred_at >= ? AND occurred_at < ?
    """, (week_start.isoformat(), query_end.isoformat()))
    row = cur.fetchone()
    conn.close()

    total, out_, in_, conn_, dur_ = row
    print(f"Report generated: {output_file}")
    print(f"Week: {week_start} to {week_end}")
    print(f"Total calls: {total}")
    print(f"Outbound: {out_}, Inbound: {in_}, Connected: {conn_}")
    print(f"Total talk time: {format_duration_long(dur_)}")

    return output_file


def main():
    parser = argparse.ArgumentParser(description="Generate call activity report")
    parser.add_argument(
        "--week-start",
        type=str,
        default=None,
        help="Monday start date (YYYY-MM-DD). Defaults to previous completed week."
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date for custom range (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date for custom range (YYYY-MM-DD). Defaults to start-date if omitted."
    )
    parser.add_argument(
        "--db",
        type=str,
        default=DEFAULT_DB,
        help=f"Path to DREAMS SQLite database (default: {DEFAULT_DB})"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for report (default: {DEFAULT_OUTPUT_DIR})"
    )
    args = parser.parse_args()

    # Determine which mode
    if args.start_date:
        # Custom date range mode
        start = date.fromisoformat(args.start_date)
        end = date.fromisoformat(args.end_date) if args.end_date else start

        if not os.path.exists(args.db):
            print(f"Error: Database not found at {args.db}")
            sys.exit(1)

        os.makedirs(args.output_dir, exist_ok=True)
        try:
            output_file = generate_date_range_report(args.db, start, end, args.output_dir)
            print(f"Report generated: {output_file}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        # Weekly mode (backward compatible)
        if args.week_start:
            week_start = date.fromisoformat(args.week_start)
            if week_start.weekday() != 0:
                print(f"Error: {week_start} is a {week_start.strftime('%A')}, not a Monday.")
                sys.exit(1)
        else:
            week_start = get_previous_monday()

        if not os.path.exists(args.db):
            print(f"Error: Database not found at {args.db}")
            sys.exit(1)

        os.makedirs(args.output_dir, exist_ok=True)
        try:
            generate_report(args.db, week_start, args.output_dir)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
