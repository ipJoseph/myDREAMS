#!/usr/bin/env python3
"""One-time OAuth setup for Gmail API access.

Run this interactively once:
    python3 scripts/gmail_auth_setup.py

It opens a browser for Google consent, then saves a refresh token
to .secrets/gmail_token.json. The TMO pipeline uses this token for
permanent, unattended Gmail access.
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SECRETS_DIR = Path(__file__).resolve().parent.parent / ".secrets"
CLIENT_SECRETS = SECRETS_DIR / "oauth_client.json"
TOKEN_FILE = SECRETS_DIR / "gmail_token.json"

# Read-only Gmail access — minimal scope
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    if not CLIENT_SECRETS.exists():
        print(f"ERROR: Client secrets not found at {CLIENT_SECRETS}")
        print("Download OAuth client credentials from Google Cloud Console.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)

    # This opens a browser for consent
    creds = flow.run_local_server(
        port=8090,
        access_type="offline",
        prompt="consent",  # Forces refresh token generation
    )

    # Save the token
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    TOKEN_FILE.chmod(0o600)
    print(f"\nToken saved to {TOKEN_FILE}")
    print(f"Refresh token: {'YES' if creds.refresh_token else 'NO (problem!)'}")
    print("\nGmail API access is now configured for unattended use.")


if __name__ == "__main__":
    main()
