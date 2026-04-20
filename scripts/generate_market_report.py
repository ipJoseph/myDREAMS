#!/usr/bin/env python3
"""
Generate a professional one-page market report PDF from TMO data.

Produces a polished, client-ready PDF with charts, KPIs, and market insights
for a given region and report date.

Usage:
    python3 scripts/generate_market_report.py
    python3 scripts/generate_market_report.py --region "Macon County" --date 2026-03-08
    python3 scripts/generate_market_report.py --region "Carolina Smokies"
"""

import argparse
import io
import sqlite3
from datetime import datetime
from pathlib import Path

try:
    from scripts.market_insights_engine import generate_fresh_insights
except ImportError:
    from market_insights_engine import generate_fresh_insights

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "dreams.db"
OUTPUT_DIR = BASE_DIR / "reports"

# Brand colors
NAVY = "#1B2A4A"
TEAL = "#2E8B8B"
GOLD = "#C5A55A"
LIGHT_BG = "#F4F6F8"
WHITE = "#FFFFFF"
DARK_TEXT = "#1B2A4A"
MID_TEXT = "#4A5568"
GREEN = "#2D8B4E"
RED = "#C0392B"
WARM_GRAY = "#E8E6E1"


def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def get_db():
    """Get database connection (PostgreSQL via pg_adapter if DATABASE_URL set)."""
    from src.core.pg_adapter import get_db as _get_db
    return _get_db(DB_PATH)


def get_market_totals_trend(conn, region):
    """Get Market Totals for all dates for a region."""
    rows = conn.execute("""
        SELECT report_date, active_listings, pending_listings, pending_ratio,
               months_inventory, closed_listings_6mo, avg_sale_price,
               list_to_sale_ratio, avg_dom_sold, avg_dom_active
        FROM tmo_market_data
        WHERE region = ? AND price_range = 'Market Totals'
        ORDER BY report_date
    """, (region,)).fetchall()
    return rows


def get_price_segments(conn, region, date):
    """Get price segment data for a specific date."""
    return conn.execute("""
        SELECT price_range, price_range_min, price_range_max,
               active_listings, pending_listings, pending_ratio,
               months_inventory, closed_listings_6mo, avg_sale_price,
               list_to_sale_ratio, avg_dom_sold
        FROM tmo_market_data
        WHERE region = ? AND report_date = ? AND price_range != 'Market Totals'
        ORDER BY price_range_min
    """, (region, date)).fetchall()


def get_latest_date(conn, region):
    row = conn.execute("""
        SELECT MAX(report_date) FROM tmo_market_data WHERE region = ?
    """, (region,)).fetchone()
    return row[0] if row else None


def make_trend_chart(dates, values, color, ylabel, highlight_last=True):
    """Create a small sparkline-style trend chart, return as ImageReader."""
    fig, ax = plt.subplots(figsize=(3.4, 1.15), dpi=150)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    x = range(len(dates))
    ax.plot(x, values, color=color, linewidth=2.0, solid_capstyle="round")
    ax.fill_between(x, values, alpha=0.08, color=color)

    if highlight_last and values:
        ax.plot(len(values)-1, values[-1], "o", color=color, markersize=6, zorder=5)

    ax.set_xlim(0, len(values)-1)
    y_min = min(v for v in values if v is not None)
    y_max = max(v for v in values if v is not None)
    y_pad = (y_max - y_min) * 0.15 or 1
    ax.set_ylim(y_min - y_pad, y_max + y_pad)

    # Minimal axis styling
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#CBD5E0")
    ax.tick_params(left=False, labelleft=False)

    # Only show first, middle, and last date labels
    n = len(dates)
    tick_positions = [0, n//2, n-1]
    tick_labels = [dates[i][5:] for i in tick_positions]  # MM-DD format
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=7, color="#718096")
    ax.tick_params(axis="x", length=0, pad=3)

    plt.tight_layout(pad=0.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    buf.seek(0)
    return ImageReader(buf)


def make_price_distribution_chart(segments):
    """Create horizontal bar chart of active listings by price range."""
    fig, ax = plt.subplots(figsize=(3.4, 2.8), dpi=150)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    # Group into broader ranges for readability
    groups = {}
    for seg in segments:
        pr_min = seg["price_range_min"]
        if pr_min is None:
            continue
        if pr_min < 200000:
            label = "Under $200K"
            order = 0
        elif pr_min < 300000:
            label = "$200K-$300K"
            order = 1
        elif pr_min < 400000:
            label = "$300K-$400K"
            order = 2
        elif pr_min < 500000:
            label = "$400K-$500K"
            order = 3
        elif pr_min < 700000:
            label = "$500K-$700K"
            order = 4
        elif pr_min < 1000000:
            label = "$700K-$1M"
            order = 5
        else:
            label = "$1M+"
            order = 6

        if label not in groups:
            groups[label] = {"active": 0, "pending": 0, "order": order}
        groups[label]["active"] += seg["active_listings"] or 0
        groups[label]["pending"] += seg["pending_listings"] or 0

    sorted_groups = sorted(groups.items(), key=lambda x: x[1]["order"])
    labels = [g[0] for g in sorted_groups]
    active = [g[1]["active"] for g in sorted_groups]
    pending = [g[1]["pending"] for g in sorted_groups]

    y = range(len(labels))
    bars_a = ax.barh(y, active, height=0.4, color=TEAL, alpha=0.85, label="Active")
    bars_p = ax.barh([i + 0.42 for i in y], pending, height=0.35, color=GOLD, alpha=0.85, label="Pending")

    ax.set_yticks([i + 0.2 for i in y])
    ax.set_yticklabels(labels, fontsize=7.5, color=DARK_TEXT, fontweight="medium")
    ax.invert_yaxis()

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#CBD5E0")
    ax.tick_params(left=False, labelsize=7)
    ax.tick_params(axis="x", labelsize=7, colors="#718096")

    ax.legend(fontsize=7, loc="lower right", frameon=False)

    plt.tight_layout(pad=0.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    buf.seek(0)
    return ImageReader(buf)


def make_inventory_gauge(months):
    """Create a visual gauge for months of inventory."""
    fig, ax = plt.subplots(figsize=(1.6, 0.45), dpi=150)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    # Draw gauge bar
    ax.barh(0, 12, height=0.6, color="#E2E8F0", left=0)

    # Color coding: <4 = seller's, 4-6 = balanced, >6 = buyer's
    if months is not None:
        if months < 4:
            bar_color = "#E53E3E"  # red = hot seller's
        elif months <= 6:
            bar_color = GOLD
        else:
            bar_color = TEAL
        ax.barh(0, min(months, 12), height=0.6, color=bar_color, left=0)
        ax.plot(months, 0, "|", color=DARK_TEXT, markersize=20, markeredgewidth=2)

    # Labels
    ax.text(2, -0.65, "Seller's", fontsize=5.5, ha="center", color="#E53E3E", fontweight="bold")
    ax.text(5, -0.65, "Balanced", fontsize=5.5, ha="center", color=GOLD, fontweight="bold")
    ax.text(9, -0.65, "Buyer's", fontsize=5.5, ha="center", color=TEAL, fontweight="bold")

    ax.set_xlim(0, 12)
    ax.set_ylim(-1.0, 0.6)
    ax.axis("off")

    plt.tight_layout(pad=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    buf.seek(0)
    return ImageReader(buf)


def draw_kpi_card(c, x, y, w, h, label, value, subtext=None, change=None):
    """Draw a KPI metric card."""
    # Card background
    r, g, b = hex_to_rgb(WHITE)
    c.setFillColorRGB(r, g, b)
    c.setStrokeColorRGB(*hex_to_rgb("#E2E8F0"))
    c.setLineWidth(0.5)
    c.roundRect(x, y, w, h, 4, fill=1, stroke=1)

    # Label
    c.setFont("Helvetica", 6.5)
    c.setFillColorRGB(*hex_to_rgb(MID_TEXT))
    c.drawString(x + 8, y + h - 14, label.upper())

    # Value
    c.setFont("Helvetica-Bold", 18)
    c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
    c.drawString(x + 8, y + h - 36, str(value))

    # Change indicator
    if change is not None:
        if change > 0:
            arrow = "\u25B2"
            color = GREEN
            txt = f"{arrow} {change:+.1f}%"
        elif change < 0:
            arrow = "\u25BC"
            color = RED
            txt = f"{arrow} {change:+.1f}%"
        else:
            color = MID_TEXT
            txt = "0.0%"
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(*hex_to_rgb(color))
        val_width = c.stringWidth(str(value), "Helvetica-Bold", 18)
        c.drawString(x + 12 + val_width, y + h - 34, txt)

    # Subtext
    if subtext:
        c.setFont("Helvetica", 6)
        c.setFillColorRGB(*hex_to_rgb(MID_TEXT))
        c.drawString(x + 8, y + 5, subtext)


def generate_report(region, report_date=None, output_path=None):
    conn = get_db()

    if report_date is None:
        report_date = get_latest_date(conn, region)
    if not report_date:
        print(f"No data found for region: {region}")
        return

    trend = get_market_totals_trend(conn, region)
    segments = get_price_segments(conn, region, report_date)
    latest = [r for r in trend if r["report_date"] == report_date]
    if not latest:
        print(f"No data for {region} on {report_date}")
        return
    latest = latest[0]

    # Find previous month for comparison
    prev = None
    for i, r in enumerate(trend):
        if r["report_date"] == report_date and i > 0:
            prev = trend[i - 1]
            break

    # Calculate changes
    def pct_change(current, previous):
        if current is None or previous is None or previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    active_chg = pct_change(latest["active_listings"], prev["active_listings"]) if prev else None
    price_chg = pct_change(latest["avg_sale_price"], prev["avg_sale_price"]) if prev else None
    pending_chg = pct_change(latest["pending_listings"], prev["pending_listings"]) if prev else None
    dom_chg = pct_change(latest["avg_dom_sold"], prev["avg_dom_sold"]) if prev else None

    # Format report date for display
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    date_display = dt.strftime("%B %d, %Y")
    month_year = dt.strftime("%B %Y")

    # Output path
    if output_path is None:
        OUTPUT_DIR.mkdir(exist_ok=True)
        safe_region = region.replace(" ", "_")
        output_path = OUTPUT_DIR / f"market-report-{safe_region}-{report_date}.pdf"

    # Page setup
    w, h = letter  # 612 x 792
    c = canvas.Canvas(str(output_path), pagesize=letter)
    margin = 36  # 0.5 inch
    content_w = w - 2 * margin

    # =========================================================================
    # HEADER BAR
    # =========================================================================
    header_h = 62
    header_y = h - header_h
    c.setFillColorRGB(*hex_to_rgb(NAVY))
    c.rect(0, header_y, w, header_h, fill=1, stroke=0)

    # Title
    c.setFillColorRGB(*hex_to_rgb(WHITE))
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin, header_y + 30, f"{region} Market Report")

    c.setFont("Helvetica", 10)
    c.setFillColorRGB(*hex_to_rgb(GOLD))
    c.drawString(margin, header_y + 12, f"Single Family Residential  |  {date_display}")

    # Branding
    c.setFont("Helvetica-Bold", 10)
    c.setFillColorRGB(*hex_to_rgb(WHITE))
    c.drawRightString(w - margin, header_y + 32, "Jon Tharp Homes")
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(*hex_to_rgb(GOLD))
    c.drawRightString(w - margin, header_y + 18, "Keller Williams Realty")
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(*hex_to_rgb("#A0AEC0"))
    c.drawRightString(w - margin, header_y + 7, "wncmountain.homes")

    # =========================================================================
    # KPI CARDS ROW
    # =========================================================================
    kpi_y = header_y - 62
    card_w = content_w / 4 - 6
    card_h = 50

    # KPI 1: Active Listings
    draw_kpi_card(c, margin, kpi_y, card_w, card_h,
                  "Active Listings",
                  str(latest["active_listings"]),
                  subtext="Homes on market",
                  change=active_chg)

    # KPI 2: Avg Sale Price
    sale_price = latest["avg_sale_price"]
    price_str = f"${sale_price:,.0f}" if sale_price else "N/A"
    draw_kpi_card(c, margin + card_w + 8, kpi_y, card_w, card_h,
                  "Avg Sale Price",
                  price_str,
                  subtext="6-month rolling average",
                  change=price_chg)

    # KPI 3: Pending Sales
    draw_kpi_card(c, margin + 2*(card_w + 8), kpi_y, card_w, card_h,
                  "Pending Sales",
                  str(latest["pending_listings"]),
                  subtext="Under contract now",
                  change=pending_chg)

    # KPI 4: Days on Market
    dom_str = str(latest["avg_dom_sold"]) if latest["avg_dom_sold"] else "N/A"
    draw_kpi_card(c, margin + 3*(card_w + 8), kpi_y, card_w, card_h,
                  "Days on Market",
                  dom_str,
                  subtext="Avg for sold homes",
                  change=dom_chg)

    # =========================================================================
    # INVENTORY GAUGE
    # =========================================================================
    gauge_y = kpi_y - 48
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
    c.drawString(margin, gauge_y + 32, "MONTHS OF INVENTORY")

    months_inv = latest["months_inventory"]
    if months_inv is not None:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin + 175, gauge_y + 26, f"{months_inv:.1f}")
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(*hex_to_rgb(MID_TEXT))
        c.drawString(margin + 205, gauge_y + 28, "months")

    gauge_img = make_inventory_gauge(months_inv)
    c.drawImage(gauge_img, margin, gauge_y - 2, width=240, height=32,
                preserveAspectRatio=True, mask="auto")

    # Market condition label
    if months_inv is not None:
        if months_inv < 4:
            cond_text = "Seller's Market: Low supply favors sellers with stronger offers and faster sales."
            cond_color = "#E53E3E"
        elif months_inv <= 6:
            cond_text = "Balanced Market: Supply and demand are well-aligned for both buyers and sellers."
            cond_color = GOLD
        else:
            cond_text = "Buyer's Market: Higher supply means more options and negotiating power for buyers."
            cond_color = TEAL
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(*hex_to_rgb(cond_color))
        c.drawString(margin + 250, gauge_y + 12, cond_text)

    # List-to-Sale and Pending Ratio
    lsr = latest["list_to_sale_ratio"]
    pr = latest["pending_ratio"]
    c.setFont("Helvetica", 7.5)
    c.setFillColorRGB(*hex_to_rgb(MID_TEXT))
    lsr_text = f"List-to-Sale Ratio: {lsr*100:.1f}%" if lsr else ""
    pr_text = f"Pending Ratio: {pr*100:.1f}%" if pr else ""
    c.drawString(margin + 250, gauge_y, f"{lsr_text}     {pr_text}")

    # =========================================================================
    # CHARTS ROW
    # =========================================================================
    charts_y = gauge_y - 190

    # Left: Price Trend
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
    c.drawString(margin, charts_y + 178, "AVERAGE SALE PRICE TREND")

    dates = [r["report_date"] for r in trend]
    prices = [r["avg_sale_price"] for r in trend if r["avg_sale_price"]]
    if len(prices) == len(dates):
        price_chart = make_trend_chart(dates, prices, TEAL, "Price")
        c.drawImage(price_chart, margin - 4, charts_y + 5, width=260, height=88,
                    preserveAspectRatio=True, mask="auto")

    # Active Listings Trend (below price)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
    c.drawString(margin, charts_y + 82, "ACTIVE LISTINGS TREND")

    actives = [r["active_listings"] for r in trend]
    active_chart = make_trend_chart(dates, actives, NAVY, "Listings")
    c.drawImage(active_chart, margin - 4, charts_y - 88, width=260, height=88,
                preserveAspectRatio=True, mask="auto")

    # Right: Inventory Distribution
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
    c.drawString(margin + 280, charts_y + 178, "INVENTORY BY PRICE RANGE")

    dist_chart = make_price_distribution_chart(segments)
    c.drawImage(dist_chart, margin + 272, charts_y - 45, width=270, height=220,
                preserveAspectRatio=True, mask="auto")

    # =========================================================================
    # HOT SEGMENTS TABLE
    # =========================================================================
    table_y = charts_y - 118

    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
    c.drawString(margin, table_y + 15, "HOTTEST PRICE SEGMENTS")
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(*hex_to_rgb(MID_TEXT))
    c.drawString(margin + 160, table_y + 16, "(highest buyer activity)")

    # Table header
    col_x = [margin, margin + 110, margin + 168, margin + 226, margin + 298, margin + 370, margin + 440]
    headers = ["Price Range", "Active", "Pending", "Pending Ratio", "Months Supply", "Avg Sale Price", "DOM"]
    header_y = table_y
    c.setFillColorRGB(*hex_to_rgb(NAVY))
    c.rect(margin - 2, header_y - 3, content_w + 4, 14, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColorRGB(*hex_to_rgb(WHITE))
    for i, hdr in enumerate(headers):
        c.drawString(col_x[i], header_y, hdr)

    # Sort segments by pending ratio
    hot_segs = sorted(
        [s for s in segments if s["pending_ratio"] and s["active_listings"] and s["active_listings"] > 2],
        key=lambda s: s["pending_ratio"],
        reverse=True,
    )[:5]

    c.setFont("Helvetica", 7)
    for i, seg in enumerate(hot_segs):
        row_y = header_y - 14 - i * 13
        # Alternating row background
        if i % 2 == 0:
            c.setFillColorRGB(*hex_to_rgb(LIGHT_BG))
            c.rect(margin - 2, row_y - 3, content_w + 4, 13, fill=1, stroke=0)

        c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
        c.setFont("Helvetica", 7)
        c.drawString(col_x[0], row_y, seg["price_range"])
        c.drawString(col_x[1], row_y, str(seg["active_listings"] or ""))
        c.drawString(col_x[2], row_y, str(seg["pending_listings"] or ""))

        pr_val = seg["pending_ratio"]
        pr_str = f"{pr_val*100:.1f}%" if pr_val else ""
        # Color code the pending ratio
        if pr_val and pr_val >= 0.40:
            c.setFillColorRGB(*hex_to_rgb("#E53E3E"))
            c.setFont("Helvetica-Bold", 7)
        elif pr_val and pr_val >= 0.25:
            c.setFillColorRGB(*hex_to_rgb(GOLD))
            c.setFont("Helvetica-Bold", 7)
        c.drawString(col_x[3], row_y, pr_str)

        c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
        c.setFont("Helvetica", 7)
        mi_val = seg["months_inventory"]
        c.drawString(col_x[4], row_y, f"{mi_val:.1f}" if mi_val else "N/A")
        sp_val = seg["avg_sale_price"]
        c.drawString(col_x[5], row_y, f"${sp_val:,.0f}" if sp_val else "N/A")
        c.drawString(col_x[6], row_y, str(seg["avg_dom_sold"] or "N/A"))

    # =========================================================================
    # MARKET INSIGHTS
    # =========================================================================
    insights_y = table_y - 105

    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
    c.drawString(margin, insights_y + 8, "MARKET INSIGHTS")

    # Draw insight cards: fresh insights first, then data-driven fallbacks
    fresh = generate_fresh_insights(region, report_date, conn)
    data_insights = build_insights(latest, prev, trend, hot_segs, region)

    # Fresh insights take priority, fill remaining slots with data insights
    insights = fresh[:]
    for di in data_insights:
        if len(insights) >= 5:
            break
        # Avoid near-duplicates by checking for shared key phrases
        if not any(di[:40] in existing for existing in insights):
            insights.append(di)

    c.setFont("Helvetica", 7.5)
    bullet_y = insights_y - 8
    for insight in insights[:5]:
        # Bullet point
        c.setFillColorRGB(*hex_to_rgb(TEAL))
        c.circle(margin + 4, bullet_y + 2.5, 2, fill=1, stroke=0)
        c.setFillColorRGB(*hex_to_rgb(DARK_TEXT))
        c.drawString(margin + 12, bullet_y, insight)
        bullet_y -= 12

    # =========================================================================
    # FOOTER
    # =========================================================================
    footer_y = 24
    c.setFillColorRGB(*hex_to_rgb(NAVY))
    c.rect(0, 0, w, footer_y + 16, fill=1, stroke=0)

    c.setFont("Helvetica", 6.5)
    c.setFillColorRGB(*hex_to_rgb("#A0AEC0"))
    c.drawString(margin, footer_y,
                 f"Data: Carolina Smokies Association of REALTORS MLS  |  "
                 f"Report period: 6 months ending {date_display}  |  "
                 f"Compiled by TMOReport.com")

    c.setFont("Helvetica-Bold", 7)
    c.setFillColorRGB(*hex_to_rgb(GOLD))
    c.drawRightString(w - margin, footer_y,
                      "Jon Tharp Homes  |  Keller Williams  |  wncmountain.homes")

    c.setFont("Helvetica", 5.5)
    c.setFillColorRGB(*hex_to_rgb("#718096"))
    c.drawString(margin, footer_y - 10,
                 "This report is for informational purposes only and does not constitute real estate advice. "
                 "Data sourced from MLS; deemed reliable but not guaranteed.")

    c.save()
    print(f"Report saved: {output_path}")
    return output_path


def build_insights(latest, prev, trend, hot_segs, region):
    """Generate dynamic market insight bullets from the data."""
    insights = []

    months_inv = latest["months_inventory"]
    if months_inv is not None:
        if months_inv < 4:
            insights.append(
                f"With {months_inv:.1f} months of inventory, {region} remains a seller's market. "
                f"Well-priced homes are moving quickly, especially in the most active segments."
            )
        elif months_inv <= 6:
            insights.append(
                f"At {months_inv:.1f} months of inventory, the market is balanced, "
                f"giving both buyers and sellers reasonable leverage in negotiations."
            )
        else:
            insights.append(
                f"With {months_inv:.1f} months of inventory, buyers have more options and negotiating room. "
                f"Pricing strategy is more important than ever for sellers."
            )

    # Pending activity
    pr = latest["pending_ratio"]
    if pr is not None and prev and prev["pending_ratio"] is not None:
        pr_prev = prev["pending_ratio"]
        if pr > pr_prev:
            insights.append(
                f"Buyer activity is accelerating: pending ratio rose from "
                f"{pr_prev*100:.1f}% to {pr*100:.1f}%, signaling strengthening demand heading into spring."
            )
        elif pr < pr_prev * 0.9:
            insights.append(
                f"Pending sales ratio has softened to {pr*100:.1f}%, "
                f"suggesting a brief pause in buyer activity typical of the season."
            )

    # Price trend
    if len(trend) >= 6:
        first_price = trend[0]["avg_sale_price"]
        last_price = trend[-1]["avg_sale_price"]
        if first_price and last_price:
            total_chg = (last_price - first_price) / first_price * 100
            if total_chg > 0:
                insights.append(
                    f"Average sale prices are up {total_chg:.1f}% over our tracking period, "
                    f"rising from ${first_price:,.0f} to ${last_price:,.0f}."
                )
            else:
                insights.append(
                    f"Average sale prices have adjusted {total_chg:.1f}% over the tracking period, "
                    f"from ${first_price:,.0f} to ${last_price:,.0f}, reflecting a normalizing market."
                )

    # Hottest segments
    if hot_segs:
        top = hot_segs[0]
        insights.append(
            f"The {top['price_range']} range is seeing the strongest activity "
            f"with a {top['pending_ratio']*100:.0f}% pending ratio. "
            f"Buyers in this segment should be prepared to act quickly."
        )

    # DOM
    dom = latest["avg_dom_sold"]
    if dom:
        lsr = latest["list_to_sale_ratio"]
        lsr_str = f"{lsr*100:.1f}%" if lsr else ""
        insights.append(
            f"Homes are selling in an average of {dom} days with a {lsr_str} list-to-sale ratio, "
            f"confirming that correctly priced properties continue to perform well."
        )

    return insights


def main():
    parser = argparse.ArgumentParser(description="Generate market report PDF")
    parser.add_argument("--region", default="Macon County", help="Region name")
    parser.add_argument("--date", default=None, help="Report date (YYYY-MM-DD)")
    parser.add_argument("--output", default=None, help="Output PDF path")
    args = parser.parse_args()

    output = Path(args.output) if args.output else None
    generate_report(args.region, args.date, output)


if __name__ == "__main__":
    main()
