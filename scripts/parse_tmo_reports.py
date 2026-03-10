#!/usr/bin/env python3
"""
Parse TMO (Total Market Overview) PDF reports into the DREAMS database.

Each PDF is a single-page table of market statistics by price range for a
specific region/county. This script:
  1. Extracts the table data from each PDF using pdfplumber
  2. Parses region name and report date from the PDF header
  3. Cleans and normalizes all values
  4. Inserts/replaces rows into tmo_market_data (upsert on unique index)
  5. Moves processed PDFs into region subfolders

Usage:
    python3 scripts/parse_tmo_reports.py
    python3 scripts/parse_tmo_reports.py --dry-run
"""

import argparse
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pdfplumber

BASE_DIR = Path(__file__).resolve().parent.parent
TMO_DIR = BASE_DIR / "data" / "tmo-reports"
DB_PATH = BASE_DIR / "data" / "dreams.db"

# Map filename prefixes to canonical region names and subfolder names
REGION_MAP = {
    "Carolina_Smokies": ("Carolina Smokies", "Carolina_Smokies"),
    "HaywoodCounty": ("Haywood County", "Haywood_County"),
    "JacksonCounty": ("Jackson County", "Jackson_County"),
    "Macon_County": ("Macon County", "Macon_County"),
    "Swain_County": ("Swain County", "Swain_County"),
}


def clean_dollar(val: str) -> float | None:
    """Parse spaced dollar strings like '$ 3 67,946' into 367946.0."""
    if not val or val.strip().upper() == "N/A":
        return None
    # Remove $, spaces, commas
    cleaned = val.replace("$", "").replace(",", "").replace(" ", "").strip()
    if not cleaned:
        return None
    return float(cleaned)


def clean_percent(val: str) -> float | None:
    """Parse '95.8%' into 0.958, handle N/A."""
    if not val or val.strip().upper() == "N/A":
        return None
    cleaned = val.replace("%", "").strip()
    if not cleaned:
        return None
    return round(float(cleaned) / 100.0, 4)


def clean_int(val: str) -> int | None:
    """Parse integer string, handle N/A and commas."""
    if not val or val.strip().upper() == "N/A":
        return None
    cleaned = val.replace(",", "").strip()
    if not cleaned:
        return None
    return int(float(cleaned))


def clean_float(val: str) -> float | None:
    """Parse float string, handle N/A."""
    if not val or val.strip().upper() == "N/A":
        return None
    cleaned = val.strip()
    if not cleaned:
        return None
    return float(cleaned)


def parse_price_range(raw: str):
    """Parse price range string into (display, min, max).

    Examples:
        '$1-$99999'           -> ('$1-$99999', 1, 99999)
        '$100000-\\n$124999'  -> ('$100000-$124999', 100000, 124999)
        '$2000000\\n+'        -> ('$2000000+', 2000000, None)
        'Market\\nTotals'     -> ('Market Totals', None, None)
    """
    cleaned = raw.replace("\n", "").replace(" ", "")

    if "total" in cleaned.lower() or "market" in cleaned.lower():
        return ("Market Totals", None, None)

    # Handle $2000000+ pattern
    plus_match = re.match(r"\$(\d[\d,]*)\+", cleaned)
    if plus_match:
        min_val = int(plus_match.group(1).replace(",", ""))
        return (f"${min_val}+", min_val, None)

    # Handle $X-$Y pattern
    range_match = re.match(r"\$(\d[\d,]*)-\$(\d[\d,]*)", cleaned)
    if range_match:
        min_val = int(range_match.group(1).replace(",", ""))
        max_val = int(range_match.group(2).replace(",", ""))
        return (f"${min_val}-${max_val}", min_val, max_val)

    # Fallback
    return (cleaned, None, None)


def parse_header(page) -> tuple[str, str, str]:
    """Extract region, property type, and date from PDF header text.

    Returns (region, property_type, iso_date).
    """
    text = page.extract_text()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Line 0: region name (e.g. "Macon County" or "Carolina Smokies - All Areas")
    region_raw = lines[0]

    # Line 1: "(Single Family Residential) March 8, 2026"
    type_date_line = lines[1]

    # Extract property type from parentheses
    prop_type = "SFR"
    ptype_match = re.search(r"\(([^)]+)\)", type_date_line)
    if ptype_match:
        prop_text = ptype_match.group(1).strip()
        if "single family" in prop_text.lower():
            prop_type = "SFR"
        else:
            prop_type = prop_text

    # Extract date
    date_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        type_date_line,
    )
    if date_match:
        date_str = f"{date_match.group(1)} {date_match.group(2)}, {date_match.group(3)}"
        dt = datetime.strptime(date_str, "%B %d, %Y")
        iso_date = dt.strftime("%Y-%m-%d")
    else:
        raise ValueError(f"Could not parse date from: {type_date_line}")

    # Normalize region name: strip suffixes, fix casing
    region = region_raw.replace(" - All Areas", "").strip()
    # Handle all-caps like "JACKSON COUNTY" -> "Jackson County"
    if region == region.upper():
        region = region.title()

    return region, prop_type, iso_date


def parse_pdf(pdf_path: Path) -> list[dict]:
    """Parse a single TMO PDF and return list of row dicts.

    Handles two table formats:
      - 13 columns: includes "Months of Inventory" (Carolina Smokies, Macon, Swain)
      - 12 columns: no "Months of Inventory" (Haywood, Jackson)
    """
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        region, prop_type, report_date = parse_header(page)

        tables = page.extract_tables()
        if not tables:
            raise ValueError(f"No table found in {pdf_path.name}")

        table = tables[0]
        ncols = len(table[0])

        # Skip header row (index 0), process data rows
        for raw_row in table[1:]:
            if len(raw_row) < ncols:
                continue

            price_display, price_min, price_max = parse_price_range(raw_row[0])

            if ncols >= 13:
                # Full format: Price, Active, Pending, PendRatio, MonthsInv,
                #   Expired, Closed, AvgOrigList, AvgFinalList, AvgSale,
                #   ListToSale, DOMSold, DOMActive
                row = {
                    "months_inventory": clean_float(raw_row[4]),
                    "expired_listings_6mo": clean_int(raw_row[5]),
                    "closed_listings_6mo": clean_int(raw_row[6]),
                    "avg_original_list_price": clean_dollar(raw_row[7]),
                    "avg_final_list_price": clean_dollar(raw_row[8]),
                    "avg_sale_price": clean_dollar(raw_row[9]),
                    "list_to_sale_ratio": clean_percent(raw_row[10]),
                    "avg_dom_sold": clean_int(raw_row[11]),
                    "avg_dom_active": clean_int(raw_row[12]),
                }
            else:
                # 12-col format (no Months of Inventory): Price, Active,
                #   Pending, PendRatio, Expired, Closed, AvgOrigList,
                #   AvgFinalList, AvgSale, ListToSale, DOMSold, DOMActive
                row = {
                    "months_inventory": None,
                    "expired_listings_6mo": clean_int(raw_row[4]),
                    "closed_listings_6mo": clean_int(raw_row[5]),
                    "avg_original_list_price": clean_dollar(raw_row[6]),
                    "avg_final_list_price": clean_dollar(raw_row[7]),
                    "avg_sale_price": clean_dollar(raw_row[8]),
                    "list_to_sale_ratio": clean_percent(raw_row[9]),
                    "avg_dom_sold": clean_int(raw_row[10]),
                    "avg_dom_active": clean_int(raw_row[11]),
                }

            # Common fields for both formats
            row.update({
                "region": region,
                "property_type": prop_type,
                "report_date": report_date,
                "price_range": price_display,
                "price_range_min": price_min,
                "price_range_max": price_max,
                "active_listings": clean_int(raw_row[1]),
                "pending_listings": clean_int(raw_row[2]),
                "pending_ratio": clean_percent(raw_row[3]),
                "source_file": pdf_path.name,
            })
            rows.append(row)

    return rows


def region_folder_for_file(filename: str) -> str | None:
    """Determine the region subfolder name from a TMO filename."""
    # Extract region key from filename: TMO-{RegionKey}(...)-MM-DD-YYYY.pdf
    match = re.match(r"TMO-([A-Za-z_]+?)(?:\(|\-\d)", filename)
    if match:
        key = match.group(1)
        if key in REGION_MAP:
            return REGION_MAP[key][1]
    return None


def insert_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert or replace rows into tmo_market_data. Returns count inserted."""
    sql = """
        INSERT OR REPLACE INTO tmo_market_data (
            region, property_type, report_date, price_range,
            price_range_min, price_range_max,
            active_listings, pending_listings, pending_ratio, months_inventory,
            expired_listings_6mo, closed_listings_6mo,
            avg_original_list_price, avg_final_list_price, avg_sale_price,
            list_to_sale_ratio, avg_dom_sold, avg_dom_active, source_file
        ) VALUES (
            :region, :property_type, :report_date, :price_range,
            :price_range_min, :price_range_max,
            :active_listings, :pending_listings, :pending_ratio, :months_inventory,
            :expired_listings_6mo, :closed_listings_6mo,
            :avg_original_list_price, :avg_final_list_price, :avg_sale_price,
            :list_to_sale_ratio, :avg_dom_sold, :avg_dom_active, :source_file
        )
    """
    count = 0
    for row in rows:
        conn.execute(sql, row)
        count += 1
    return count


def _ensure_table(conn):
    """Create tmo_market_data table if it doesn't exist."""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tmo_market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT NOT NULL,
            property_type TEXT NOT NULL,
            report_date TEXT NOT NULL,
            price_range TEXT NOT NULL,
            price_range_min INTEGER,
            price_range_max INTEGER,
            active_listings INTEGER,
            pending_listings INTEGER,
            pending_ratio REAL,
            months_inventory REAL,
            expired_listings_6mo INTEGER,
            closed_listings_6mo INTEGER,
            avg_original_list_price REAL,
            avg_final_list_price REAL,
            avg_sale_price REAL,
            list_to_sale_ratio REAL,
            avg_dom_sold INTEGER,
            avg_dom_active INTEGER,
            source_file TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tmo_region_date_range
            ON tmo_market_data(region, report_date, price_range)
    """)
    conn.commit()


def parse_new_reports(dry_run=False):
    """Parse any new TMO PDFs in the tmo-reports directory.

    Importable function for use by the pipeline orchestrator.

    Args:
        dry_run: If True, parse PDFs but don't write to DB or move files.

    Returns:
        dict with keys: processed (int), total_rows (int), errors (list),
                        report_dates (set of date strings), regions (set of region names)
    """
    pdf_files = sorted(TMO_DIR.glob("TMO-*.pdf"))

    result = {
        "processed": 0,
        "total_rows": 0,
        "errors": [],
        "report_dates": set(),
        "regions": set(),
    }

    if not pdf_files:
        print("No TMO PDF files found to process.")
        return result

    print(f"Found {len(pdf_files)} TMO PDFs to process")

    # Create region subfolders
    for _, folder_name in REGION_MAP.values():
        (TMO_DIR / folder_name).mkdir(exist_ok=True)

    conn = None
    if not dry_run:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        _ensure_table(conn)

    for pdf_path in pdf_files:
        try:
            rows = parse_pdf(pdf_path)

            if not dry_run and conn:
                count = insert_rows(conn, rows)
                result["total_rows"] += count

            result["processed"] += 1

            # Track which dates and regions we processed
            for row in rows:
                result["report_dates"].add(row["region"] and row["report_date"])
                result["regions"].add(row["region"])

            # Move file into region subfolder
            folder = region_folder_for_file(pdf_path.name)
            if folder and not dry_run:
                dest = TMO_DIR / folder / pdf_path.name
                shutil.move(str(pdf_path), str(dest))

            status = f"{len(rows)} rows" + (f" -> {folder}/" if folder else "")
            print(f"  OK: {pdf_path.name} ({status})")

        except Exception as e:
            result["errors"].append((pdf_path.name, str(e)))
            print(f"  ERROR: {pdf_path.name}: {e}")

    if not dry_run and conn and result["processed"] > 0:
        conn.commit()
        conn.close()

    print(f"Summary: {result['processed']}/{len(pdf_files)} files, {result['total_rows']} rows")
    return result


def main():
    parser = argparse.ArgumentParser(description="Parse TMO report PDFs into database")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't write to DB or move files")
    args = parser.parse_args()

    result = parse_new_reports(dry_run=args.dry_run)

    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for name, err in result["errors"]:
            print(f"  {name}: {err}")


if __name__ == "__main__":
    main()
