#!/usr/bin/env python3
"""
Generate the weekly call activity report for Feb 9-15, 2026.
Fixes from previous version:
  1. Correct day-of-week labels (Feb 9 = Monday, not Sunday)
  2. Resolve contact names via JOIN with leads table
  3. Convert UTC timestamps to EST (UTC-5) for correct daily grouping
"""

import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict
import html as html_mod

DB_PATH = "/home/bigeug/myDREAMS/data/dreams.db"
OUTPUT_PATH = "/home/bigeug/myDREAMS/reports/calls-week-2026-02-09.html"

# EST offset: UTC - 5 hours (February = Eastern Standard Time, no DST)
EST_OFFSET = timedelta(hours=-5)

QUERY = """
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
AND cc.occurred_at >= '2026-02-09' AND cc.occurred_at < '2026-02-16'
ORDER BY cc.occurred_at
"""

def parse_utc(ts_str):
    """Parse a UTC timestamp string to datetime."""
    ts_str = ts_str.rstrip("Z")
    return datetime.fromisoformat(ts_str)

def utc_to_est(dt):
    """Convert a naive UTC datetime to EST (UTC-5)."""
    return dt + EST_OFFSET

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

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(QUERY)
    rows = cur.fetchall()
    conn.close()

    # Parse all calls, converting to EST
    calls = []
    for occurred_at, direction, duration, status, contact_id, name in rows:
        utc_dt = parse_utc(occurred_at)
        est_dt = utc_to_est(utc_dt)
        calls.append({
            "utc_dt": utc_dt,
            "est_dt": est_dt,
            "est_date": est_dt.date(),
            "direction": direction,
            "duration": duration if duration else 0,
            "status": status,
            "contact_id": contact_id,
            "name": name,
        })

    # ---- Compute summary stats ----
    total_calls = len(calls)
    outbound = sum(1 for c in calls if c["direction"] == "outbound")
    inbound = sum(1 for c in calls if c["direction"] == "inbound")
    connected = sum(1 for c in calls if c["status"] == "completed")
    total_duration = sum(c["duration"] for c in calls)

    # ---- Daily breakdown ----
    # Week: Feb 9 (Mon) through Feb 15 (Sun)
    from datetime import date
    week_dates = [date(2026, 2, 9) + timedelta(days=i) for i in range(7)]
    day_names = {
        date(2026, 2, 9): "Mon 2/9",
        date(2026, 2, 10): "Tue 2/10",
        date(2026, 2, 11): "Wed 2/11",
        date(2026, 2, 12): "Thu 2/12",
        date(2026, 2, 13): "Fri 2/13",
        date(2026, 2, 14): "Sat 2/14",
        date(2026, 2, 15): "Sun 2/15",
    }
    day_full_names = {
        date(2026, 2, 9): "Monday, February 9",
        date(2026, 2, 10): "Tuesday, February 10",
        date(2026, 2, 11): "Wednesday, February 11",
        date(2026, 2, 12): "Thursday, February 12",
        date(2026, 2, 13): "Friday, February 13",
        date(2026, 2, 14): "Saturday, February 14",
        date(2026, 2, 15): "Sunday, February 15",
    }

    daily_stats = OrderedDict()
    for d in week_dates:
        daily_stats[d] = {
            "made": 0, "received": 0, "total": 0,
            "connected": 0, "no_answer": 0, "duration": 0,
        }

    for c in calls:
        d = c["est_date"]
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

    # ---- Group calls by EST date for detail log ----
    calls_by_date = defaultdict(list)
    for c in calls:
        calls_by_date[c["est_date"]].append(c)

    # ---- Build HTML ----
    html_parts = []

    # Head
    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Call Activity Report | Feb 9&ndash;15, 2026</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f8fafc;
            color: #1a1a1a;
            padding: 32px;
            max-width: 1000px;
            margin: 0 auto;
        }
        h1 {
            font-size: 26px;
            font-weight: 800;
            margin-bottom: 4px;
        }
        .subtitle {
            font-size: 14px;
            color: #64748b;
            margin-bottom: 32px;
        }
        .section-title {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 14px;
            margin-top: 36px;
        }

        /* Summary Cards */
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 14px;
            margin-bottom: 12px;
        }
        .summary-card {
            background: white;
            border-radius: 10px;
            padding: 18px 16px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }
        .summary-card .value {
            font-size: 32px;
            font-weight: 800;
            line-height: 1;
            margin-bottom: 4px;
        }
        .summary-card .label {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #64748b;
        }
        .total .value { color: #1e3a5f; }
        .outbound .value { color: #2563eb; }
        .inbound .value { color: #16a34a; }
        .connected .value { color: #7c3aed; }
        .duration .value { color: #ea580c; font-size: 24px; }

        /* Summary Table */
        .summary-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            margin-bottom: 32px;
        }
        .summary-table th {
            background: #f8fafc;
            padding: 10px 14px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #64748b;
            text-align: center;
            border-bottom: 2px solid #e2e8f0;
        }
        .summary-table th:first-child { text-align: left; }
        .summary-table td {
            padding: 10px 14px;
            font-size: 14px;
            text-align: center;
            border-bottom: 1px solid #f1f5f9;
        }
        .summary-table td:first-child {
            text-align: left;
            font-weight: 600;
        }
        .summary-table tr:last-child td {
            border-bottom: none;
        }
        .summary-table .total-row {
            background: #f0f9ff;
            font-weight: 700;
        }
        .summary-table .total-row td { border-top: 2px solid #bfdbfe; }
        .summary-table .weekend td { color: #94a3b8; }

        /* Detail Table */
        .detail-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            font-size: 13px;
        }
        .detail-table th {
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
        }
        .detail-table td {
            padding: 8px 12px;
            border-bottom: 1px solid #f1f5f9;
            vertical-align: middle;
        }
        .detail-table tr:hover { background: #f8fafc; }

        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
        }
        .badge.outbound { background: #eff6ff; color: #2563eb; }
        .badge.inbound { background: #f0fdf4; color: #16a34a; }
        .badge.no-answer { color: #d97706; }
        .badge.bad-number { color: #dc2626; }
        .badge.left-message { color: #7c3aed; }

        .day-divider td {
            background: #f1f5f9;
            font-weight: 700;
            font-size: 12px;
            color: #475569;
            padding: 6px 12px;
        }

        .duration-bar {
            display: inline-block;
            height: 6px;
            background: #3b82f6;
            border-radius: 3px;
            margin-left: 6px;
            vertical-align: middle;
            opacity: 0.5;
        }

        .footer {
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
            margin-top: 32px;
            padding-top: 16px;
            border-top: 1px solid #e2e8f0;
        }

        @media print {
            body { padding: 16px; }
            .detail-table th { position: static; }
        }
    </style>
</head>
<body>
""")

    # Title
    html_parts.append(f"""
<h1>Call Activity Report</h1>
<p class="subtitle">Joseph Williams &mdash; Week of February 9&ndash;15, 2026 &mdash; All times EST (UTC&minus;5) &mdash; Source: FUB via DREAMS</p>
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

    # Daily Summary Table
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

    week_made = 0
    week_received = 0
    week_total = 0
    week_connected = 0
    week_no_answer = 0
    week_duration = 0

    for d in week_dates:
        s = daily_stats[d]
        label = day_names[d]
        is_weekend = d.weekday() >= 5  # 5=Sat, 6=Sun

        week_made += s["made"]
        week_received += s["received"]
        week_total += s["total"]
        week_connected += s["connected"]
        week_no_answer += s["no_answer"]
        week_duration += s["duration"]

        row_class = ' class="weekend"' if is_weekend else ""
        talk_time = format_duration_long(s["duration"]) if s["duration"] > 0 else "&mdash;"

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

    html_parts.append(f"""        <tr class="total-row">
            <td>Week Total</td>
            <td>{week_made}</td>
            <td>{week_received}</td>
            <td>{week_total}</td>
            <td>{week_connected}</td>
            <td>{week_no_answer}</td>
            <td>{format_duration_long(week_duration)}</td>
        </tr>
    </tbody>
</table>
""")

    # Detail Table
    html_parts.append("""
<!-- Detail Table -->
<h2 class="section-title">Call Detail Log</h2>
<table class="detail-table">
    <thead>
        <tr>
            <th>Date</th>
            <th>Time (EST)</th>
            <th>Direction</th>
            <th>Contact</th>
            <th>Status</th>
            <th>Duration</th>
        </tr>
    </thead>
    <tbody>
""")

    # Determine max duration for bar scaling
    max_dur = max((c["duration"] for c in calls), default=1)
    LONG_CALL_THRESHOLD = 600  # 10 minutes = show duration bar

    for d in week_dates:
        day_calls = calls_by_date.get(d, [])

        # Day divider row
        html_parts.append(f'        <tr class="day-divider"><td colspan="6">{esc(day_full_names[d])}</td></tr>\n')

        if not day_calls:
            html_parts.append(f'        <tr><td colspan="6" style="color:#94a3b8; font-style:italic; text-align:center; padding:8px;">No calls</td></tr>\n')
            continue

        for c in day_calls:
            est = c["est_dt"]
            date_short = f"{est.month}/{est.day}"
            time_str = format_time_12h(est)

            # Direction badge
            if c["direction"] == "outbound":
                dir_badge = '<span class="badge outbound">Made</span>'
            else:
                dir_badge = '<span class="badge inbound">Received</span>'

            # Contact name
            contact_name = esc(c["name"])

            # Status
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

            # Duration
            dur_secs = c["duration"]
            if dur_secs and dur_secs > 0:
                dur_str = format_duration(dur_secs)
                # Add bar for long calls
                if dur_secs >= LONG_CALL_THRESHOLD:
                    bar_width = max(10, int(60 * dur_secs / max_dur))
                    dur_str += f' <span class="duration-bar" style="width:{bar_width}px;"></span>'
            else:
                dur_str = "&mdash;"

            html_parts.append(
                f'        <tr>'
                f'<td>{date_short}</td>'
                f'<td>{time_str}</td>'
                f'<td>{dir_badge}</td>'
                f'<td>{contact_name}</td>'
                f'<td>{status_html}</td>'
                f'<td>{dur_str}</td>'
                f'</tr>\n'
            )

    html_parts.append("""    </tbody>
</table>
""")

    # Footer
    html_parts.append("""
<div class="footer">
    Generated by DREAMS &mdash; All times Eastern Standard Time (UTC&minus;5)<br>
    Data source: Follow Up Boss call log synced to DREAMS database
</div>

</body>
</html>
""")

    # Write output
    html_content = "".join(html_parts)
    with open(OUTPUT_PATH, "w") as f:
        f.write(html_content)

    print(f"Report generated: {OUTPUT_PATH}")
    print(f"Total calls: {total_calls}")
    print(f"Outbound: {outbound}, Inbound: {inbound}")
    print(f"Connected: {connected}")
    print(f"Total talk time: {format_duration_long(total_duration)}")
    print()

    # Print daily breakdown for verification
    print("Daily breakdown (EST):")
    for d in week_dates:
        s = daily_stats[d]
        print(f"  {day_names[d]}: {s['total']} calls ({s['made']} out, {s['received']} in), {s['connected']} connected, {format_duration_long(s['duration'])}")


if __name__ == "__main__":
    main()
