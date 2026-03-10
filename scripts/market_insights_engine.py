#!/usr/bin/env python3
"""
Market Insights Engine

Two-tier system for generating fresh, contextual market insights:
  Tier 1: Automated anomaly detection from TMO data trends
  Tier 2: Curated seasonal content as fallback when data is stable

Entry point: generate_fresh_insights(region, report_date, conn) -> list[str]
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSIGHTS_FILE = BASE_DIR / "data" / "market_insights.json"
DB_PATH = BASE_DIR / "data" / "dreams.db"


def _load_curated_insights():
    """Load the curated seasonal insights JSON."""
    if not INSIGHTS_FILE.exists():
        return {"seasonal": {}, "overrides": {}}
    with open(INSIGHTS_FILE) as f:
        return json.load(f)


def _get_trend_data(conn, region, limit=12):
    """Get recent Market Totals rows for a region, ordered oldest to newest."""
    rows = conn.execute("""
        SELECT report_date, active_listings, pending_listings, pending_ratio,
               months_inventory, closed_listings_6mo, avg_sale_price,
               list_to_sale_ratio, avg_dom_sold
        FROM tmo_market_data
        WHERE region = ? AND price_range = 'Market Totals'
        ORDER BY report_date DESC
        LIMIT ?
    """, (region, limit)).fetchall()
    return list(reversed(rows))  # oldest first


def _detect_anomalies(trend, region, report_date):
    """Tier 1: Detect notable patterns in the data. Returns list of insight strings."""
    insights = []
    if len(trend) < 2:
        return insights

    latest = trend[-1]
    prev = trend[-2]

    # --- Threshold crossings: market type shift ---
    mi = latest["months_inventory"]
    mi_prev = prev["months_inventory"]
    if mi is not None and mi_prev is not None:
        # Crossed below 4.0 (entered seller's market)
        if mi < 4.0 and mi_prev >= 4.0:
            insights.append(
                f"Market shift: inventory dropped below 4 months ({mi:.1f}), "
                f"moving {region} into seller's market territory."
            )
        # Crossed above 6.0 (entered buyer's market)
        elif mi > 6.0 and mi_prev <= 6.0:
            insights.append(
                f"Market shift: inventory rose above 6 months ({mi:.1f}), "
                f"moving {region} into buyer's market territory."
            )
        # Crossed from buyer's back to balanced
        elif mi <= 6.0 and mi_prev > 6.0:
            insights.append(
                f"Inventory has tightened to {mi:.1f} months, "
                f"bringing {region} back into balanced market range."
            )

    # --- Consecutive direction streaks ---
    if len(trend) >= 4:
        actives = [r["active_listings"] for r in trend if r["active_listings"] is not None]
        if len(actives) >= 4:
            # Check for consecutive rises
            rising = all(actives[i] > actives[i-1] for i in range(-3, 0))
            falling = all(actives[i] < actives[i-1] for i in range(-3, 0))
            streak_len = 3
            # Extend streak check
            for i in range(len(actives) - 4, -1, -1):
                if rising and actives[i+1] > actives[i]:
                    streak_len += 1
                elif falling and actives[i+1] < actives[i]:
                    streak_len += 1
                else:
                    break

            if rising and streak_len >= 3:
                insights.append(
                    f"Active listings have risen {streak_len} consecutive weeks in {region}, "
                    f"signaling growing inventory for buyers."
                )
            elif falling and streak_len >= 3:
                insights.append(
                    f"Active listings have declined {streak_len} consecutive weeks in {region}, "
                    f"tightening supply for buyers."
                )

    # --- Period highs/lows ---
    if len(trend) >= 6:
        all_prices = [r["avg_sale_price"] for r in trend if r["avg_sale_price"] is not None]
        current_price = latest["avg_sale_price"]
        if all_prices and current_price is not None:
            if current_price >= max(all_prices):
                insights.append(
                    f"Average sale price in {region} has reached a tracking-period high "
                    f"of ${current_price:,.0f}."
                )
            elif current_price <= min(all_prices):
                insights.append(
                    f"Average sale price in {region} is at a tracking-period low "
                    f"of ${current_price:,.0f}, potentially creating opportunity for buyers."
                )

        all_dom = [r["avg_dom_sold"] for r in trend if r["avg_dom_sold"] is not None]
        current_dom = latest["avg_dom_sold"]
        if all_dom and current_dom is not None:
            if current_dom <= min(all_dom) and current_dom < 60:
                insights.append(
                    f"Days on market has hit a low of {current_dom} days in {region}. "
                    f"Homes are selling faster than any point in our tracking period."
                )

    # --- Big week-over-week swings ---
    active_now = latest["active_listings"]
    active_prev = prev["active_listings"]
    if active_now and active_prev and active_prev > 0:
        pct = abs(active_now - active_prev) / active_prev * 100
        if pct > 15:
            direction = "jumped" if active_now > active_prev else "dropped"
            insights.append(
                f"Active listings {direction} {pct:.0f}% week-over-week in {region} "
                f"(from {active_prev} to {active_now}), a significant swing worth watching."
            )

    price_now = latest["avg_sale_price"]
    price_prev = prev["avg_sale_price"]
    if price_now and price_prev and price_prev > 0:
        pct = abs(price_now - price_prev) / price_prev * 100
        if pct > 3:
            direction = "rose" if price_now > price_prev else "fell"
            insights.append(
                f"Average sale price {direction} {pct:.1f}% this week in {region} "
                f"(${price_prev:,.0f} to ${price_now:,.0f})."
            )

    pr_now = latest["pending_ratio"]
    pr_prev = prev["pending_ratio"]
    if pr_now and pr_prev and pr_prev > 0:
        pct = abs(pr_now - pr_prev) / pr_prev * 100
        if pct > 20:
            direction = "surged" if pr_now > pr_prev else "pulled back"
            insights.append(
                f"Pending ratio {direction} {pct:.0f}% in {region} "
                f"({pr_prev*100:.1f}% to {pr_now*100:.1f}%), "
                f"indicating a notable shift in buyer activity."
            )

    return insights


def _get_seasonal_insight(report_date):
    """Tier 2: Get a seasonal insight based on the month."""
    data = _load_curated_insights()

    # Check for date-specific override first
    overrides = data.get("overrides", {})
    if report_date in overrides:
        return overrides[report_date]

    # Fall back to month-keyed seasonal content
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    month_key = dt.strftime("%m")
    seasonal = data.get("seasonal", {})

    tips = seasonal.get(month_key, [])
    if not tips:
        return None

    # Rotate through tips based on the week number within the month
    week_of_month = (dt.day - 1) // 7
    return tips[week_of_month % len(tips)]


def generate_fresh_insights(region, report_date, conn=None):
    """
    Generate fresh market insights for a region and date.

    Returns a list of insight strings. Tier 1 (data-driven) insights come first,
    followed by a Tier 2 (seasonal) fallback if needed to ensure at least one
    fresh insight is always present.

    Args:
        region: Region name (e.g., "Macon County")
        report_date: ISO date string (e.g., "2026-03-08")
        conn: Optional sqlite3 connection. If None, opens one.

    Returns:
        List of insight strings (typically 1-3 items)
    """
    close_conn = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        close_conn = True

    try:
        trend = _get_trend_data(conn, region)
        anomalies = _detect_anomalies(trend, region, report_date)

        # Always try to include a seasonal insight
        seasonal = _get_seasonal_insight(report_date)

        # Combine: anomalies first, then seasonal if we have room
        insights = anomalies[:3]  # cap anomalies at 3
        if seasonal and len(insights) < 3:
            insights.append(seasonal)

        # If nothing was detected at all, at least return the seasonal
        if not insights and seasonal:
            insights = [seasonal]

        return insights
    finally:
        if close_conn:
            conn.close()


if __name__ == "__main__":
    """Quick test: show insights for all regions at the latest date."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    regions = [r[0] for r in conn.execute(
        "SELECT DISTINCT region FROM tmo_market_data ORDER BY region"
    ).fetchall()]

    latest_date = conn.execute(
        "SELECT MAX(report_date) FROM tmo_market_data"
    ).fetchone()[0]

    print(f"Fresh insights for {latest_date}:\n")
    for region in regions:
        insights = generate_fresh_insights(region, latest_date, conn)
        print(f"  {region}:")
        for ins in insights:
            print(f"    * {ins}")
        print()

    conn.close()
