#!/usr/bin/env python3
"""
Fetch FUB Users - Get team members from Follow Up Boss

This script fetches all users from the FUB account to:
1. Understand the team structure
2. Map ownerId to user names
3. Identify the current user's ID for filtering "my leads"
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
import requests

load_dotenv(PROJECT_ROOT / ".env")

FUB_API_KEY = os.getenv("FUB_API_KEY")
FUB_BASE_URL = "https://api.followupboss.com/v1"


def fetch_users():
    """Fetch all users from FUB."""
    session = requests.Session()
    session.auth = (FUB_API_KEY, "")
    session.headers["Accept"] = "application/json"

    url = f"{FUB_BASE_URL}/users"
    response = session.get(url, timeout=30)
    response.raise_for_status()

    data = response.json()
    return data.get("users", [])


def fetch_current_user():
    """Fetch the current authenticated user (me)."""
    session = requests.Session()
    session.auth = (FUB_API_KEY, "")
    session.headers["Accept"] = "application/json"

    url = f"{FUB_BASE_URL}/me"
    response = session.get(url, timeout=30)
    response.raise_for_status()

    return response.json()


def main():
    print("=" * 60)
    print("FUB Users Report")
    print("=" * 60)

    # Fetch current user first
    print("\n📍 Current Authenticated User (You):")
    print("-" * 40)
    try:
        me = fetch_current_user()
        print(json.dumps(me, indent=2))
        my_id = me.get("id")
        print(f"\n✅ Your FUB User ID: {my_id}")
    except Exception as e:
        print(f"❌ Error fetching current user: {e}")
        my_id = None

    # Fetch all users
    print("\n👥 All Team Members:")
    print("-" * 40)
    try:
        users = fetch_users()
        print(f"Total users: {len(users)}\n")

        for user in users:
            user_id = user.get("id")
            name = user.get("name", "Unknown")
            email = user.get("email", "")
            role = user.get("role", "")
            is_me = " 👈 (YOU)" if user_id == my_id else ""

            print(f"  ID: {user_id}")
            print(f"  Name: {name}{is_me}")
            print(f"  Email: {email}")
            print(f"  Role: {role}")
            print()

        # Print summary for .env configuration
        print("\n" + "=" * 60)
        print("📝 Add to your .env file:")
        print("-" * 40)
        if my_id:
            print(f'FUB_MY_USER_ID="{my_id}"')

        # Print user ID mapping for reference
        print("\n# FUB User ID Mapping:")
        for user in users:
            print(f'# {user.get("id")} = {user.get("name")}')

    except Exception as e:
        print(f"❌ Error fetching users: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
