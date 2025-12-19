import argparse
import sqlite3
import csv

from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "vendors.db"


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                last_contacted TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def add_vendor(
    name: str,
    category: str,
    email: str | None,
    phone: str | None,
    notes: str | None,
) -> None:
    now = datetime.utcnow().isoformat()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO vendors (
                name, category, email, phone,
                last_contacted, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, category, email, phone, now, notes, now),
        )

def list_vendors() -> None:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, category, email, phone, last_contacted
            FROM vendors
            ORDER BY name
            """
        ).fetchall()

    if not rows:
        print("No vendors found.")
        return

    for row in rows:
        vid, name, category, email, phone, last_contacted = row
        print(
            f"[{vid}] {name} | {category} | "
            f"{email or '-'} | {phone or '-'} | "
            f"last contacted: {last_contacted}"
        )


def export_csv(path: str) -> None:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                name,
                category,
                email,
                phone,
                last_contacted,
                notes,
                created_at
            FROM vendors
            ORDER BY name
            """
        ).fetchall()

    if not rows:
        print("No vendors to export.")
        return

    headers = [
        "id",
        "name",
        "category",
        "email",
        "phone",
        "last_contacted",
        "notes",
        "created_at",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"Exported {len(rows)} vendors to {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vendor Directory")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add-vendor", help="Add a new vendor")
    add.add_argument("--name", required=True)
    add.add_argument("--category", required=True)
    add.add_argument("--email")
    add.add_argument("--phone")
    add.add_argument("--notes")

    subparsers.add_parser("list-vendors", help="List all vendors")

    export = subparsers.add_parser("export-csv", help="Export vendors to CSV")
    export.add_argument(
        "--path",
        default="vendors.csv",
        help="Output CSV file path (default: vendors.csv)",
    )

    return parser.parse_args()


def main() -> None:
    init_db()
    args = parse_args()

    if args.command == "add-vendor":
        add_vendor(
            name=args.name,
            category=args.category,
            email=args.email,
            phone=args.phone,
            notes=args.notes,
        )
        print(f"Vendor added: {args.name}")

    elif args.command == "list-vendors":
        list_vendors()

    elif args.command == "export-csv":
        export_csv(args.path)


if __name__ == "__main__":
    main()
