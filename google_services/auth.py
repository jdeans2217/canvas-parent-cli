#!/usr/bin/env python3
"""
Google OAuth2 Authentication - Shared authentication for all Google services.

Handles OAuth2 flow, token storage, and credential management for:
- Gmail API
- Google Calendar API
- Google Docs API
- Google Drive API
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Service scopes - add more as needed
SCOPES = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
    ],
    "calendar": [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ],
    "docs": [
        "https://www.googleapis.com/auth/documents",
    ],
    "drive": [
        "https://www.googleapis.com/auth/drive",
    ],
}

# Service API versions
SERVICE_VERSIONS = {
    "gmail": ("gmail", "v1"),
    "calendar": ("calendar", "v3"),
    "docs": ("docs", "v1"),
    "drive": ("drive", "v3"),
}

# Default paths
DEFAULT_CREDENTIALS_FILE = "credentials.json"
DEFAULT_TOKEN_FILE = "token.json"


class GoogleAuth:
    """
    Google OAuth2 authentication handler.

    Manages credentials, tokens, and service instantiation for all
    Google Workspace APIs.

    Usage:
        auth = GoogleAuth()
        gmail_service = auth.get_service("gmail")
        calendar_service = auth.get_service("calendar")
    """

    def __init__(
        self,
        credentials_file: Optional[str] = None,
        token_file: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ):
        """
        Initialize Google authentication.

        Args:
            credentials_file: Path to OAuth2 client credentials JSON file
                (download from Google Cloud Console)
            token_file: Path to store/load user tokens
            scopes: List of OAuth scopes to request (uses all by default)
        """
        self.credentials_file = credentials_file or self._find_credentials_file()
        self.token_file = token_file or DEFAULT_TOKEN_FILE
        self.scopes = scopes or self._get_all_scopes()
        self._credentials: Optional[Credentials] = None
        self._services: dict = {}

    def _find_credentials_file(self) -> str:
        """Find credentials file in common locations."""
        # Check environment variable
        env_creds = os.getenv("GOOGLE_CREDENTIALS_FILE")
        if env_creds and os.path.exists(env_creds):
            return env_creds

        # Check common locations
        locations = [
            DEFAULT_CREDENTIALS_FILE,
            os.path.expanduser("~/credentials.json"),
            os.path.expanduser("~/.config/canvas-parent-cli/credentials.json"),
        ]

        for loc in locations:
            if os.path.exists(loc):
                return loc

        return DEFAULT_CREDENTIALS_FILE

    def _get_all_scopes(self) -> List[str]:
        """Get all available scopes."""
        all_scopes = []
        for scope_list in SCOPES.values():
            all_scopes.extend(scope_list)
        return list(set(all_scopes))

    def _get_scopes_for_services(self, services: List[str]) -> List[str]:
        """Get scopes required for specific services."""
        scopes = []
        for service in services:
            if service in SCOPES:
                scopes.extend(SCOPES[service])
        return list(set(scopes))

    @property
    def credentials(self) -> Optional[Credentials]:
        """Get current credentials (lazy load)."""
        if self._credentials is None:
            self._credentials = self._load_or_create_credentials()
        return self._credentials

    def _load_or_create_credentials(self) -> Optional[Credentials]:
        """Load existing credentials or run OAuth flow."""
        creds = None

        # Try to load existing token
        if os.path.exists(self.token_file):
            try:
                # Load without scope validation - token scopes may differ from requested
                creds = Credentials.from_authorized_user_file(self.token_file)
            except Exception as e:
                print(f"Failed to load token: {e}")

        # Check if credentials are valid or can be refreshed
        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_credentials(creds)
                return creds
            except Exception as e:
                print(f"Failed to refresh token: {e}")
                # Fall through to re-authenticate

        # Run OAuth flow for new credentials
        return self._run_oauth_flow()

    def _run_oauth_flow(self) -> Optional[Credentials]:
        """Run interactive OAuth2 authorization flow."""
        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_file}\n"
                "Download OAuth2 client credentials from Google Cloud Console:\n"
                "1. Go to https://console.cloud.google.com/apis/credentials\n"
                "2. Create OAuth 2.0 Client ID (Desktop application)\n"
                "3. Download JSON and save as 'credentials.json'"
            )

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_file, self.scopes
            )

            # Try local server first
            try:
                creds = flow.run_local_server(
                    port=0,
                    success_message="Authentication successful! You may close this window.",
                    open_browser=True,
                )
            except Exception as browser_error:
                print(f"Browser auth failed: {browser_error}")
                print("\nUsing manual authentication...")
                creds = self._run_manual_flow(flow)

            if creds:
                self._save_credentials(creds)
            return creds

        except Exception as e:
            print(f"OAuth flow failed: {e}")
            return None

    def _run_manual_flow(self, flow: InstalledAppFlow) -> Optional[Credentials]:
        """Run manual OAuth flow for headless environments."""
        # Set redirect URI for manual/OOB flow
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"

        # Generate authorization URL
        auth_url, _ = flow.authorization_url(prompt="consent")

        print("\n" + "=" * 60)
        print("MANUAL AUTHORIZATION REQUIRED")
        print("=" * 60)
        print("\n1. Open this URL in a browser:\n")
        print(auth_url)
        print("\n2. Sign in and authorize the application")
        print("3. Copy the authorization code and paste it below\n")

        auth_code = input("Enter authorization code: ").strip()

        if not auth_code:
            print("No code provided")
            return None

        try:
            flow.fetch_token(code=auth_code)
            return flow.credentials
        except Exception as e:
            print(f"Failed to fetch token: {e}")
            return None

    def _save_credentials(self, creds: Credentials) -> None:
        """Save credentials to token file."""
        try:
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())
        except Exception as e:
            print(f"Failed to save token: {e}")

    def get_service(self, service_name: str) -> Any:
        """
        Get an authenticated Google API service.

        Args:
            service_name: One of 'gmail', 'calendar', 'docs', 'drive'

        Returns:
            Google API service object

        Raises:
            ValueError: If service_name is not recognized
            RuntimeError: If authentication fails
        """
        if service_name not in SERVICE_VERSIONS:
            raise ValueError(
                f"Unknown service: {service_name}. "
                f"Valid services: {list(SERVICE_VERSIONS.keys())}"
            )

        # Return cached service if available
        if service_name in self._services:
            return self._services[service_name]

        # Ensure we have valid credentials
        if not self.credentials:
            raise RuntimeError(
                "Failed to authenticate with Google. "
                "Please check your credentials file."
            )

        # Build and cache the service
        api_name, api_version = SERVICE_VERSIONS[service_name]
        service = build(api_name, api_version, credentials=self.credentials)
        self._services[service_name] = service

        return service

    def is_authenticated(self) -> bool:
        """Check if we have valid credentials."""
        return self.credentials is not None and self.credentials.valid

    def get_user_email(self) -> Optional[str]:
        """Get the authenticated user's email address."""
        try:
            gmail = self.get_service("gmail")
            profile = gmail.users().getProfile(userId="me").execute()
            return profile.get("emailAddress")
        except Exception:
            return None

    def revoke_credentials(self) -> bool:
        """Revoke current credentials and delete token file."""
        try:
            if self.credentials:
                # Note: Google doesn't always support programmatic revocation
                # But we can delete the local token
                pass

            if os.path.exists(self.token_file):
                os.remove(self.token_file)

            self._credentials = None
            self._services = {}
            return True

        except Exception as e:
            print(f"Failed to revoke credentials: {e}")
            return False


def get_authenticated_service(
    service_name: str,
    credentials_file: Optional[str] = None,
    token_file: Optional[str] = None,
) -> Any:
    """
    Convenience function to get an authenticated Google service.

    Args:
        service_name: One of 'gmail', 'calendar', 'docs', 'drive'
        credentials_file: Optional path to credentials file
        token_file: Optional path to token file

    Returns:
        Authenticated Google API service object
    """
    auth = GoogleAuth(
        credentials_file=credentials_file,
        token_file=token_file,
        scopes=SCOPES.get(service_name, []),
    )
    return auth.get_service(service_name)


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Google OAuth2 Authentication Test")
    print("=" * 50)

    auth = GoogleAuth()

    if not os.path.exists(auth.credentials_file):
        print(f"\nCredentials file not found: {auth.credentials_file}")
        print("\nTo set up Google OAuth2:")
        print("1. Go to https://console.cloud.google.com/apis/credentials")
        print("2. Create a new OAuth 2.0 Client ID (Desktop application)")
        print("3. Download the JSON file")
        print("4. Save it as 'credentials.json' in this directory")
        exit(1)

    print(f"\nCredentials file: {auth.credentials_file}")
    print(f"Token file: {auth.token_file}")
    print(f"Scopes: {len(auth.scopes)} requested")

    print("\nAttempting authentication...")
    if auth.is_authenticated():
        print("Authentication: SUCCESS")

        email = auth.get_user_email()
        if email:
            print(f"Authenticated as: {email}")

        # Test each service
        for service_name in SERVICE_VERSIONS.keys():
            try:
                service = auth.get_service(service_name)
                print(f"  {service_name}: OK")
            except Exception as e:
                print(f"  {service_name}: FAILED - {e}")
    else:
        print("Authentication: FAILED")
