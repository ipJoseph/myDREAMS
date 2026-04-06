#!/usr/bin/env python3
"""Download TMO report PDFs from Gmail via the Gmail API.

Uses OAuth refresh token stored at .secrets/gmail_token.json
(created by gmail_auth_setup.py). No interactive auth required.
"""
import base64
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = PROJECT_ROOT / ".secrets"
TOKEN_FILE = SECRETS_DIR / "gmail_token.json"
OUTPUT_DIR = PROJECT_ROOT / "data" / "tmo-reports"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    """Build an authenticated Gmail API service."""
    if not TOKEN_FILE.exists():
        print(f"ERROR: Token file not found at {TOKEN_FILE}", file=sys.stderr)
        print("Run: python3 scripts/gmail_auth_setup.py", file=sys.stderr)
        sys.exit(1)

    with open(TOKEN_FILE) as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=SCOPES,
    )

    # Refresh if expired (uses the permanent refresh token)
    if creds.expired or not creds.valid:
        creds.refresh(Request())
        # Save refreshed access token back
        token_data["token"] = creds.token
        with open(TOKEN_FILE, "w") as f:
            json.dump(token_data, f, indent=2)

    return build("gmail", "v1", credentials=creds)


def get_all_tmo_message_ids(service):
    """Fetch all TMO email message IDs using pagination."""
    ids = []
    page_token = None
    while True:
        results = service.users().messages().list(
            userId="me",
            q="subject:TMO has:attachment filename:pdf",
            maxResults=50,
            pageToken=page_token,
        ).execute()

        for m in results.get("messages", []):
            ids.append(m["id"])

        page_token = results.get("nextPageToken")
        if not page_token:
            break
    return ids


def download_attachments(service, msg_id):
    """Download all PDF attachments from a message."""
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    subject = headers.get("Subject", "")
    date = headers.get("Date", "")
    print(f"\n{subject} ({date})")

    downloaded = 0
    skipped = 0

    def _save_pdf(data, outpath, filename):
        """Decode base64url PDF data and write to disk."""
        pdf = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        outpath.write_bytes(pdf)
        print(f"  SAVED: {filename} ({len(pdf) // 1024} KB)")

    def process_parts(part):
        nonlocal downloaded, skipped
        filename = part.get("filename", "")
        if filename and filename.lower().endswith(".pdf") and "tmo" in filename.lower():
            outpath = OUTPUT_DIR / filename
            # Check root dir and county subdirectories (parse step moves files there)
            if outpath.exists() or any(OUTPUT_DIR.glob(f"*/{filename}")):
                print(f"  SKIP (exists): {filename}")
                skipped += 1
                return

            attachment_id = part.get("body", {}).get("attachmentId")
            if not attachment_id:
                body_data = part.get("body", {}).get("data", "")
                if body_data:
                    _save_pdf(body_data, outpath, filename)
                    downloaded += 1
                return

            att = service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=attachment_id
            ).execute()
            if att and "data" in att:
                _save_pdf(att["data"], outpath, filename)
                downloaded += 1

        for p in part.get("parts", []):
            process_parts(p)

    process_parts(msg["payload"])
    return downloaded, skipped


def download_new_reports():
    """Download new TMO report PDFs from Gmail.

    Returns:
        Number of new PDFs downloaded.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Searching Gmail for TMO reports...")
    service = get_gmail_service()
    ids = get_all_tmo_message_ids(service)
    print(f"Found {len(ids)} emails with TMO attachments")

    total = 0
    consecutive_all_exist = 0
    for i, msg_id in enumerate(ids):
        downloaded, skipped = download_attachments(service, msg_id)
        total += downloaded
        if downloaded == 0 and skipped > 0:
            # This email had TMO PDFs but they all existed already
            consecutive_all_exist += 1
            # Gmail returns newest first; if 5 consecutive emails had
            # all files already on disk, older emails will too.
            if consecutive_all_exist >= 5:
                remaining = len(ids) - i - 1
                if remaining > 0:
                    print(f"  (skipping {remaining} older emails — all recent files exist)")
                break
        else:
            consecutive_all_exist = 0

    print(f"Downloaded {total} new PDFs to {OUTPUT_DIR}")
    return total


def main():
    total = download_new_reports()
    existing = len(list(OUTPUT_DIR.glob("*.pdf")))
    print(f"Total PDFs in folder: {existing}")


if __name__ == "__main__":
    main()
