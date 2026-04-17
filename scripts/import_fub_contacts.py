"""
Phase E: Import 72 FUB contacts, archive the rest.

Run on PRD: /opt/mydreams/venv/bin/python scripts/import_fub_contacts.py
Run on DEV: .venv/bin/python scripts/import_fub_contacts.py

Safe to run multiple times (idempotent).
"""
import os
import sqlite3
import uuid
from datetime import datetime

DB_PATH = os.getenv("DREAMS_DB_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "dreams.db"
))

IMPORT_EMAILS = [
    "sydwilliams@comcast.net", "alisontilley@yahoo.com", "colinallen2010@gmail.com",
    "afrauenfelder@msn.com", "pinkpeachapple123@gmail.com", "habichw@hotmail.com",
    "bhollenbck7@gmail.com", "cathyhhamiltom@gmail.com", "atozbuilders1@aol.com",
    "cllafforthun@gmail.com", "crystallail@gmail.com", "daleison1951@icloud.com",
    "dalekohl@gmail.com", "danmadden90@yahoo.com", "graydonohoe061876@gmail.com",
    "dawn.nichols@evsck12.com", "donnaapexauto@gmail.com", "donna28806@yahoo.com",
    "auriel77@gmail.com", "emily.olinger@yahoo.com", "belle07us@yahoo.com",
    "estielow@gmail.com", "wrighte2011@gmail.com", "55chevy.gb@gmail.com",
    "grichie60@gmail.com", "glendacook98@yahoo.com", "gwenkeough@gmail.com",
    "hgrotheer3@outlook.com", "ceo@allenhammett.com", "jjs.sharpe@gmail.com",
    "kisrealtyinvestments@gmail.com", "jeffpucciano@yahoo.com", "llathren@sc.rr.com",
    "wallois@verizon.net", "julio@wehouston.com", "kavi892@gmail.com",
    "kevinpjames8993@gmail.com", "lwskvn56@yahoo.com", "kevin@daytonaluxury.com",
    "hulme.kim@gmail.com", "larryraymes@yahoo.com", "lriggs6@ec.rr.com",
    "fofsarasota@gmail.com", "redwolftwo@icloud.com", "meremaxwell@gmail.com",
    "mecheek17@gmail.com", "mmcabee50@yahoo.com", "mjholcomb@gmail.com",
    "morganthomas@att.net", "pamelakelley2026@gmail.com", "tuxedohomecare@gmail.com",
    "paulszak@gmail.com", "jungletrout@gmail.com", "rex@servicepro9505.com",
    "rvmeshev@live.com", "lonesomedove122@yahoo.com", "scox1760@gmail.com",
    "sbertrand@allenharrisonco.com", "warriordadsc@gmail.com", "steven.legg1022@gmail.com",
    "spcarlen@gmail.com", "skennedynatpat@gmail.com", "joseph@josephwilliams.biz",
    "tom.kenney5@gmail.com", "allentown13@gmail.com", "tomharner5@gmail.com",
    "tom_protich@verizon.net", "vruff65@gmail.com", "tunamarinade3@gmail.com",
    "joseph@ncpropertyinvestments.com", "doloresinsweden@icloud.com",
]

# Thomas (Gene) Yarborough has no email, match by phone
IMPORT_PHONES = {"7065083064": ("Thomas (Gene)", "Yarborough")}

# New contacts not in the snapshot
NEW_CONTACTS = [
    {"first": "Dolores", "last": "Williams", "email": "doloresinsweden@icloud.com",
     "phone": "6786546496"},
    {"first": "Joseph", "last": "Williams", "email": "joseph@ncpropertyinvestments.com",
     "phone": "8282839003"},
]


def main():
    now = datetime.now().isoformat()
    print(f"Database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")

    # Add archive_status column if missing
    try:
        conn.execute("ALTER TABLE leads ADD COLUMN archive_status TEXT")
        print("Added archive_status column")
    except sqlite3.OperationalError:
        print("archive_status column already exists")

    # Add phone to users if missing
    try:
        conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        print("Added phone column to users")
    except sqlite3.OperationalError:
        pass

    # Step 1: Archive all existing contacts
    result = conn.execute(
        "UPDATE leads SET archive_status = 'archived_jth_pivot' "
        "WHERE archive_status IS NULL OR archive_status = 'active'"
    )
    print(f"Archived {result.rowcount} existing contacts")

    # Step 2: Activate matched by email
    activated = 0
    for email in IMPORT_EMAILS:
        r = conn.execute(
            "UPDATE leads SET archive_status = 'active', "
            "source = 'Initial FUB Import', contact_group = 'scored' "
            "WHERE LOWER(email) = ?",
            (email.lower(),)
        )
        activated += r.rowcount

    # Step 3: Activate matched by phone (no-email contacts)
    for phone, (fn, ln) in IMPORT_PHONES.items():
        r = conn.execute(
            "UPDATE leads SET archive_status = 'active', "
            "source = 'Initial FUB Import', contact_group = 'scored' "
            "WHERE phone = ?",
            (phone,)
        )
        if r.rowcount == 0:
            # Try without formatting
            r = conn.execute(
                "UPDATE leads SET archive_status = 'active', "
                "source = 'Initial FUB Import', contact_group = 'scored' "
                "WHERE REPLACE(REPLACE(REPLACE(phone,'-',''),'(',''),')','') = ?",
                (phone,)
            )
        activated += r.rowcount

    # Step 4: Create contacts that don't exist yet
    for new in NEW_CONTACTS:
        exists = conn.execute(
            "SELECT id FROM leads WHERE LOWER(email) = ?",
            (new["email"].lower(),)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO leads (id, first_name, last_name, email, phone, "
                "source, stage, type, contact_group, archive_status, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'Initial FUB Import', 'Lead', "
                "'buyer', 'scored', 'active', ?, ?)",
                (str(uuid.uuid4()), new["first"], new["last"],
                 new["email"], new["phone"], now, now)
            )
            activated += 1
            print(f"Created new contact: {new['first']} {new['last']}")
        else:
            # Already exists, just make sure it's active
            conn.execute(
                "UPDATE leads SET archive_status = 'active', "
                "source = 'Initial FUB Import', contact_group = 'scored' "
                "WHERE id = ?",
                (exists[0],)
            )

    conn.commit()

    # Verify
    active = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE archive_status = 'active'"
    ).fetchone()[0]
    archived = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE archive_status = 'archived_jth_pivot'"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    print(f"\n=== IMPORT COMPLETE ===")
    print(f"  Activated:  {activated}")
    print(f"  Active:     {active}")
    print(f"  Archived:   {archived}")
    print(f"  Total:      {total}")

    conn.close()


if __name__ == "__main__":
    main()
