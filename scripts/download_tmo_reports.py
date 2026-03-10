#!/usr/bin/env python3
"""Download all TMO report PDFs from Gmail via gws CLI."""
import json
import subprocess
import base64
import os
import sys
import tempfile

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'tmo-reports')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_gws(*args, params=None):
    """Run a gws command and return parsed JSON."""
    cmd = list(args)
    if params:
        cmd += ['--params', json.dumps(params)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Try stderr first, then stdout for error messages
        err = result.stderr.strip() or result.stdout.strip()
        print(f'  ERROR: {err[:200]}', file=sys.stderr)
        return None
    return json.loads(result.stdout)


def get_all_tmo_message_ids():
    """Fetch all TMO email message IDs using pagination."""
    ids = []
    page_token = None
    while True:
        params = {
            'userId': 'me',
            'q': 'subject:TMO has:attachment filename:pdf',
            'maxResults': 50,
        }
        if page_token:
            params['pageToken'] = page_token
        data = run_gws('gws', 'gmail', 'users', 'messages', 'list', params=params)
        if not data:
            break
        for m in data.get('messages', []):
            ids.append(m['id'])
        page_token = data.get('nextPageToken')
        if not page_token:
            break
    return ids


def download_attachments(msg_id):
    """Download all PDF attachments from a message."""
    msg = run_gws('gws', 'gmail', 'users', 'messages', 'get', params={
        'userId': 'me',
        'id': msg_id,
        'format': 'full',
    })
    if not msg:
        return 0

    headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
    subject = headers.get('Subject', '')
    date = headers.get('Date', '')
    print(f'\n{subject} ({date})')

    downloaded = 0

    def process_parts(part):
        nonlocal downloaded
        filename = part.get('filename', '')
        if filename and filename.lower().endswith('.pdf') and 'tmo' in filename.lower():
            outpath = os.path.join(OUTPUT_DIR, filename)
            if os.path.exists(outpath):
                print(f'  SKIP (exists): {filename}')
                return

            attachment_id = part.get('body', {}).get('attachmentId')
            if not attachment_id:
                # Try inline body data
                body_data = part.get('body', {}).get('data', '')
                if body_data:
                    pdf = decode_base64url(body_data)
                    with open(outpath, 'wb') as f:
                        f.write(pdf)
                    print(f'  SAVED: {filename} ({len(pdf) // 1024} KB)')
                    downloaded += 1
                return

            # Fetch attachment via gws
            att = run_gws(
                'gws', 'gmail', 'users', 'messages', 'attachments', 'get',
                params={
                    'userId': 'me',
                    'messageId': msg_id,
                    'id': attachment_id,
                }
            )
            if att and 'data' in att:
                pdf = decode_base64url(att['data'])
                with open(outpath, 'wb') as f:
                    f.write(pdf)
                print(f'  SAVED: {filename} ({len(pdf) // 1024} KB)')
                downloaded += 1

        for p in part.get('parts', []):
            process_parts(p)

    process_parts(msg['payload'])
    return downloaded


def decode_base64url(data):
    """Decode URL-safe base64 data from Gmail API."""
    raw = data.replace('-', '+').replace('_', '/')
    pad = 4 - len(raw) % 4
    if pad < 4:
        raw += '=' * pad
    return base64.b64decode(raw)


def download_new_reports():
    """Download new TMO report PDFs from Gmail.

    Importable function for use by the pipeline orchestrator.

    Returns:
        Number of new PDFs downloaded.
    """
    print('Searching Gmail for TMO reports...')
    ids = get_all_tmo_message_ids()
    print(f'Found {len(ids)} emails with TMO attachments')

    total = 0
    for msg_id in ids:
        total += download_attachments(msg_id)

    print(f'Downloaded {total} new PDFs to {os.path.abspath(OUTPUT_DIR)}')
    return total


def main():
    total = download_new_reports()
    existing = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.pdf')])
    print(f'Total PDFs in folder: {existing}')


if __name__ == '__main__':
    main()
