#!/usr/bin/env python3
"""
TMO Weekly Pipeline: Automated Download, Parse, Generate, Notify

Orchestrates the full TMO report workflow:
  1. Download new PDFs from Gmail (gws CLI)
  2. Parse new PDFs into tmo_market_data table
  3. Generate 5 regional market report PDFs (with fresh insights)
  4. Email reports to Eugy with summary

Designed to run daily via cron. Most days exits quickly (no new reports).
On report day, runs the full pipeline.

Usage:
    python3 scripts/tmo_weekly_pipeline.py              # Full run
    python3 scripts/tmo_weekly_pipeline.py --dry-run     # Parse + detect, no writes
    python3 scripts/tmo_weekly_pipeline.py --no-email    # Full run, skip email
    python3 scripts/tmo_weekly_pipeline.py --force       # Bypass state checks
    python3 scripts/tmo_weekly_pipeline.py --skip-download  # Skip Gmail download step
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.download_tmo_reports import download_new_reports
from scripts.parse_tmo_reports import parse_new_reports
from scripts.generate_market_report import generate_report
from scripts.market_insights_engine import generate_fresh_insights

DB_PATH = PROJECT_ROOT / "data" / "dreams.db"
STATE_FILE = PROJECT_ROOT / "data" / "tmo_pipeline_state.json"
REPORTS_DIR = PROJECT_ROOT / "reports"

REGIONS = [
    "Carolina Smokies",
    "Haywood County",
    "Jackson County",
    "Macon County",
    "Swain County",
]


def load_state():
    """Load pipeline state from JSON file."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    """Save pipeline state to JSON file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_latest_report_date():
    """Query the database for the most recent TMO report date."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    row = conn.execute(
        "SELECT MAX(report_date) FROM tmo_market_data"
    ).fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def get_region_summary(conn, region, report_date):
    """Get Market Totals summary for a region at a given date."""
    row = conn.execute("""
        SELECT active_listings, pending_listings, pending_ratio,
               months_inventory, avg_sale_price, avg_dom_sold,
               list_to_sale_ratio
        FROM tmo_market_data
        WHERE region = ? AND report_date = ? AND price_range = 'Market Totals'
    """, (region, report_date)).fetchone()

    if not row:
        return None

    # Get previous date for comparison
    prev = conn.execute("""
        SELECT avg_sale_price
        FROM tmo_market_data
        WHERE region = ? AND report_date < ? AND price_range = 'Market Totals'
        ORDER BY report_date DESC LIMIT 1
    """, (region, report_date)).fetchone()

    price_change = None
    if row["avg_sale_price"] and prev and prev["avg_sale_price"]:
        price_change = (row["avg_sale_price"] - prev["avg_sale_price"]) / prev["avg_sale_price"] * 100

    mi = row["months_inventory"]
    if mi is not None:
        if mi < 4:
            market_type = "Seller's"
            market_type_class = "type-sellers"
        elif mi <= 6:
            market_type = "Balanced"
            market_type_class = "type-balanced"
        else:
            market_type = "Buyer's"
            market_type_class = "type-buyers"
    else:
        market_type = "N/A"
        market_type_class = ""

    return {
        "name": region,
        "active_listings": row["active_listings"] or 0,
        "avg_sale_price": f"${row['avg_sale_price']:,.0f}" if row["avg_sale_price"] else "N/A",
        "price_change": f"{price_change:+.1f}%" if price_change is not None else "N/A",
        "change_class": "change-up" if (price_change and price_change > 0) else "change-down" if (price_change and price_change < 0) else "",
        "months_inventory": f"{mi:.1f}" if mi is not None else "N/A",
        "market_type": market_type,
        "market_type_class": market_type_class,
    }


def step_download(args):
    """Step 1: Download new TMO PDFs from Gmail."""
    print("\n=== Step 1: Download new reports from Gmail ===")
    if args.skip_download:
        print("  Skipped (--skip-download)")
        return True
    if args.dry_run:
        print("  Skipped (dry run)")
        return True

    try:
        count = download_new_reports()
        print(f"  Downloaded {count} new PDFs")
        return True
    except Exception as e:
        print(f"  ERROR downloading: {e}")
        return False


def step_parse(args):
    """Step 2: Parse new PDFs into the database."""
    print("\n=== Step 2: Parse new PDFs into database ===")
    result = parse_new_reports(dry_run=args.dry_run)

    if result["processed"] == 0:
        print("  No new PDFs to parse")
        return None  # Signal: nothing new

    if result["errors"]:
        print(f"  WARNING: {len(result['errors'])} parse errors")

    return result


def step_generate(report_date, args):
    """Step 3: Generate market report PDFs for all regions."""
    print(f"\n=== Step 3: Generate market reports for {report_date} ===")
    REPORTS_DIR.mkdir(exist_ok=True)

    generated = []
    for region in REGIONS:
        safe_name = region.replace(" ", "_")
        output_path = REPORTS_DIR / f"market-report-{safe_name}-{report_date}.pdf"

        if output_path.exists() and not args.force:
            print(f"  EXISTS: {output_path.name}")
            generated.append(output_path)
            continue

        try:
            result = generate_report(region, report_date, output_path)
            if result:
                generated.append(Path(result))
        except Exception as e:
            print(f"  ERROR generating {region}: {e}")

    print(f"  Generated {len(generated)} reports")
    return generated


def step_email(report_date, report_paths, args):
    """Step 4: Email reports to Eugy."""
    print(f"\n=== Step 4: Email reports ===")
    if args.no_email:
        print("  Skipped (--no-email)")
        return True
    if args.dry_run:
        print("  Skipped (dry run)")
        return True

    try:
        from apps.automation.email_service import send_template_email
        from apps.automation import config
    except ImportError as e:
        print(f"  ERROR: Could not import email service: {e}")
        return False

    # Build email context
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    date_display = dt.strftime("%B %d, %Y")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    region_summaries = []
    region_insights_list = []
    for region in REGIONS:
        summary = get_region_summary(conn, region, report_date)
        if summary:
            region_summaries.append(summary)

        insights = generate_fresh_insights(region, report_date, conn)
        if insights:
            region_insights_list.append({
                "name": region,
                "insights": insights[:2],  # Limit to 2 per region in email
            })

    conn.close()

    # Build attachments list
    attachments = []
    for path in report_paths:
        if path.exists():
            with open(path, "rb") as f:
                attachments.append((path.name, f.read(), "application/pdf"))

    recipient = config.WEEKLY_SUMMARY_RECIPIENT or config.SMTP_USERNAME
    subject = f"TMO Market Reports Ready: {date_display}"

    context = {
        "report_date_display": date_display,
        "regions": region_summaries,
        "region_insights": region_insights_list,
        "attachment_count": len(attachments),
    }

    success = send_template_email(
        to=recipient,
        subject=subject,
        template_name="tmo_reports_ready.html",
        context=context,
        attachments=attachments,
    )

    if success:
        print(f"  Email sent to {recipient}")
    else:
        print(f"  ERROR: Failed to send email to {recipient}")

    return success


def main():
    parser = argparse.ArgumentParser(description="TMO Weekly Pipeline")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and detect only, no writes or email")
    parser.add_argument("--no-email", action="store_true",
                        help="Run full pipeline but skip email notification")
    parser.add_argument("--force", action="store_true",
                        help="Bypass state checks, regenerate even if already processed")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip the Gmail download step (use existing PDFs)")
    args = parser.parse_args()

    print(f"TMO Weekly Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Flags: dry_run={args.dry_run}, no_email={args.no_email}, "
          f"force={args.force}, skip_download={args.skip_download}")

    state = load_state()

    # Step 1: Download
    if not step_download(args):
        print("\nPipeline aborted: download failed")
        sys.exit(1)

    # Step 2: Parse
    parse_result = step_parse(args)

    # Determine report date
    report_date = get_latest_report_date()
    if not report_date:
        print("\nNo TMO data in database. Nothing to generate.")
        sys.exit(0)

    # Guard: don't re-email old reports.
    # If no new PDFs were parsed this run, the report_date comes from
    # whatever is already in the DB (which may be stale if the DB was
    # overwritten by a PRD sync). Only proceed if:
    #   (a) new PDFs were actually parsed this run, OR
    #   (b) --force flag is set
    if not args.force and not args.dry_run:
        last_processed = state.get("last_report_date")
        if parse_result is None:
            # No new data this run. Don't re-send anything.
            print(f"\nNo new TMO data parsed. Latest in DB is {report_date} "
                  f"(last sent: {last_processed}). Skipping.")
            sys.exit(0)

    print(f"\nReport date: {report_date}")

    # Step 3: Generate PDFs
    if args.dry_run:
        print("\n=== Step 3: Generate market reports (dry run) ===")
        print("  Skipped (dry run)")
        report_paths = []
    else:
        report_paths = step_generate(report_date, args)

    # Step 4: Email
    if report_paths:
        step_email(report_date, report_paths, args)

    # Save state
    if not args.dry_run:
        state["last_run"] = datetime.now().isoformat()
        state["last_report_date"] = report_date
        state["reports_generated"] = len(report_paths)
        state["email_sent"] = not args.no_email
        save_state(state)
        print(f"\nState saved to {STATE_FILE}")

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
