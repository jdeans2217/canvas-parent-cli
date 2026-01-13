#!/usr/bin/env python3
"""
Google OAuth Setup Script

Run this script to authenticate with Google APIs.
It will open a browser for you to sign in and authorize access.

Usage:
    python setup_google_auth.py
"""

import os
import sys

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Scopes needed for all services
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def main():
    print("Google OAuth Setup")
    print("=" * 50)

    # Check for credentials file
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"\nError: {CREDENTIALS_FILE} not found!")
        print("\nTo set up Google OAuth:")
        print("1. Go to https://console.cloud.google.com/apis/credentials")
        print("2. Create OAuth 2.0 Client ID (Desktop application)")
        print("3. Download the JSON file")
        print("4. Save it as 'credentials.json' in this directory")
        sys.exit(1)

    # Check for existing valid token
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            if creds and creds.valid:
                print(f"\nAlready authenticated!")
                print(f"Token file: {TOKEN_FILE}")
                print("\nTo re-authenticate, delete token.json and run again.")
                sys.exit(0)
            elif creds and creds.expired and creds.refresh_token:
                print("\nRefreshing expired token...")
                creds.refresh(Request())
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
                print("Token refreshed successfully!")
                sys.exit(0)
        except Exception as e:
            print(f"Error loading existing token: {e}")

    # Run OAuth flow
    print(f"\nCredentials file: {CREDENTIALS_FILE}")
    print(f"Requesting {len(SCOPES)} scopes...")
    print("\nStarting OAuth flow...")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)

        # Try local server (opens browser)
        try:
            creds = flow.run_local_server(
                port=8080,
                success_message="Authentication successful! You may close this window.",
                open_browser=True,
            )
        except Exception as e:
            print(f"\nBrowser auth failed: {e}")
            print("\nFalling back to manual authentication...")

            # Manual flow
            flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
            auth_url, _ = flow.authorization_url(prompt="consent")

            print("\n" + "=" * 60)
            print("MANUAL AUTHORIZATION")
            print("=" * 60)
            print("\n1. Open this URL in your browser:\n")
            print(auth_url)
            print("\n2. Sign in with your Google account")
            print("3. Click 'Allow' to grant permissions")
            print("4. Copy the authorization code shown")
            print("\n")

            auth_code = input("Paste the authorization code here: ").strip()

            if not auth_code:
                print("No code provided. Exiting.")
                sys.exit(1)

            flow.fetch_token(code=auth_code)
            creds = flow.credentials

        # Save token
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

        print("\n" + "=" * 50)
        print("SUCCESS! Authentication complete.")
        print("=" * 50)
        print(f"\nToken saved to: {TOKEN_FILE}")
        print("\nYou can now use the following commands:")
        print("  python -m cli.send_report --test")
        print("  python -m cli.sync_calendar --list")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
