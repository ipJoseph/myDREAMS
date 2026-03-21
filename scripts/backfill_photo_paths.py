#!/usr/bin/env python3
"""Backfill photo_local_path for listings that have photos on disk but not in DB."""

import sqlite3
import time
from pathlib import Path

DB = Path(__file__).parent.parent / 'data' / 'dreams.db'
PHOTOS = {
    'NavicaMLS': Path(__file__).parent.parent / 'data' / 'photos' / 'navica',
    'MountainLakesMLS': Path(__file__).parent.parent / 'data' / 'photos' / 'navica',
    'CanopyMLS': Path(__file__).parent.parent / 'data' / 'photos' / 'mlsgrid',
}


def main():
    conn = sqlite3.connect(str(DB), timeout=120)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=120000')
    conn.row_factory = sqlite3.Row

    # Index files once per directory
    print('Scanning photo directories...')
    file_index = {}
    for source, photos_dir in PHOTOS.items():
        if photos_dir not in file_index:
            stems = {}
            for f in photos_dir.iterdir():
                if f.is_file() and f.stat().st_size > 0:
                    stems[f.stem] = str(f)
            file_index[photos_dir] = stems
            print(f'  {photos_dir.name}: {len(stems):,} files indexed')

    total_updated = 0
    for source, photos_dir in PHOTOS.items():
        rows = conn.execute(
            'SELECT mls_number FROM listings WHERE mls_source = ? AND photo_local_path IS NULL',
            [source]
        ).fetchall()

        stems = file_index[photos_dir]
        updates = [
            (stems[row['mls_number']], row['mls_number'])
            for row in rows
            if row['mls_number'] in stems
        ]

        for i in range(0, len(updates), 100):
            batch = updates[i:i + 100]
            for attempt in range(10):
                try:
                    conn.executemany(
                        'UPDATE listings SET photo_local_path = ? WHERE mls_number = ?',
                        batch
                    )
                    conn.commit()
                    break
                except sqlite3.OperationalError as e:
                    if 'locked' in str(e) and attempt < 9:
                        time.sleep(1)
                    else:
                        raise
            done = min(i + 100, len(updates))
            if done % 5000 == 0 or done == len(updates):
                print(f'  {source}: {done:,}/{len(updates):,} written')

        print(f'{source}: {len(rows):,} missing -> {len(updates):,} backfilled')
        total_updated += len(updates)

    conn.close()
    print(f'Total backfilled: {total_updated:,}')


if __name__ == '__main__':
    main()
