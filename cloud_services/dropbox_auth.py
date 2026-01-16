#!/usr/bin/env python3
"""
Dropbox OAuth2 Authentication - Authentication handler for Dropbox API.

Uses PKCE flow for secure desktop application authentication.
Stores tokens in dropbox_token.json for reuse across sessions.
"""

import os
import json
from typing import Optional
from pathlib import Path

import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect

# Default paths
DEFAULT_TOKEN_FILE = "dropbox_token.json"


class DropboxAuth:
    """
    Dropbox OAuth2 authentication handler.

    Manages credentials, tokens, and client instantiation for Dropbox API.
    Uses App Folder access (scoped to /Apps/<app_name>/).

    Usage:
        auth = DropboxAuth()
        client = auth.client  # Returns authenticated Dropbox client
    """

    def __init__(
        self,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        token_file: Optional[str] = None,
    ):
        """
        Initialize Dropbox authentication.

        Args:
            app_key: Dropbox app key (from developer console)
            app_secret: Dropbox app secret
            token_file: Path to store/load tokens
        """
        self.app_key = app_key or os.getenv("DROPBOX_APP_KEY", "")
        self.app_secret = app_secret or os.getenv("DROPBOX_APP_SECRET", "")
        self.token_file = token_file or self._find_token_file()
        self._client: Optional[dropbox.Dropbox] = None

    def _find_token_file(self) -> str:
        """Find token file in common locations."""
        # Check environment variable
        env_token = os.getenv("DROPBOX_TOKEN_FILE")
        if env_token:
            return env_token

        # Check common locations
        locations = [
            DEFAULT_TOKEN_FILE,
            os.path.expanduser("~/dropbox_token.json"),
            os.path.expanduser("~/.config/canvas-parent-cli/dropbox_token.json"),
        ]

        for loc in locations:
            if os.path.exists(loc):
                return loc

        return DEFAULT_TOKEN_FILE

    @property
    def client(self) -> Optional[dropbox.Dropbox]:
        """Get authenticated Dropbox client (lazy load)."""
        if self._client is None:
            self._client = self._load_or_create_client()
        return self._client

    def _load_or_create_client(self) -> Optional[dropbox.Dropbox]:
        """Load existing credentials or run OAuth flow."""
        # Try to load existing token
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r") as f:
                    token_data = json.load(f)

                access_token = token_data.get("access_token")
                refresh_token = token_data.get("refresh_token")

                if refresh_token and self.app_key:
                    # Create client with refresh token
                    client = dropbox.Dropbox(
                        oauth2_access_token=access_token,
                        oauth2_refresh_token=refresh_token,
                        app_key=self.app_key,
                        app_secret=self.app_secret,
                    )

                    # Test if token is valid by checking refresh
                    try:
                        client.check_and_refresh_access_token()
                        # Save updated token
                        self._save_token(
                            client._oauth2_access_token,
                            refresh_token,
                        )
                        return client
                    except Exception as e:
                        print(f"Token refresh failed: {e}")
                        # Fall through to re-authenticate

                elif access_token:
                    # Try with just access token (may be expired)
                    client = dropbox.Dropbox(oauth2_access_token=access_token)
                    try:
                        # Test if valid
                        client.users_get_current_account()
                        return client
                    except Exception:
                        pass  # Fall through to re-authenticate

            except Exception as e:
                print(f"Failed to load token: {e}")

        # Run OAuth flow for new credentials
        return self._run_oauth_flow()

    def _run_oauth_flow(self) -> Optional[dropbox.Dropbox]:
        """Run interactive OAuth2 authorization flow with PKCE."""
        if not self.app_key:
            raise ValueError(
                "Dropbox app key not configured.\n"
                "Set DROPBOX_APP_KEY in .env file.\n"
                "Get credentials from: https://www.dropbox.com/developers/apps"
            )

        print("\n" + "=" * 60)
        print("DROPBOX AUTHORIZATION REQUIRED")
        print("=" * 60)

        # Create OAuth flow with PKCE (no redirect needed)
        auth_flow = DropboxOAuth2FlowNoRedirect(
            consumer_key=self.app_key,
            consumer_secret=self.app_secret,
            token_access_type="offline",  # Get refresh token
            use_pkce=True,
        )

        authorize_url = auth_flow.start()

        print("\n1. Open this URL in a browser:\n")
        print(authorize_url)
        print("\n2. Click 'Allow' to authorize the application")
        print("3. Copy the authorization code and paste it below\n")

        auth_code = input("Enter authorization code: ").strip()

        if not auth_code:
            print("No code provided")
            return None

        try:
            oauth_result = auth_flow.finish(auth_code)

            # Save tokens
            self._save_token(
                oauth_result.access_token,
                oauth_result.refresh_token,
            )

            print("\nAuthorization successful!")

            # Create and return client
            return dropbox.Dropbox(
                oauth2_access_token=oauth_result.access_token,
                oauth2_refresh_token=oauth_result.refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret,
            )

        except Exception as e:
            print(f"Authorization failed: {e}")
            return None

    def _save_token(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
    ) -> None:
        """Save tokens to file."""
        try:
            token_data = {
                "access_token": access_token,
                "refresh_token": refresh_token,
            }

            # Ensure directory exists
            token_path = Path(self.token_file)
            token_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.token_file, "w") as f:
                json.dump(token_data, f, indent=2)

        except Exception as e:
            print(f"Failed to save token: {e}")

    def is_authenticated(self) -> bool:
        """Check if we have a valid client."""
        if self.client is None:
            return False

        try:
            self.client.users_get_current_account()
            return True
        except Exception:
            return False

    def get_user_email(self) -> Optional[str]:
        """Get the authenticated user's email address."""
        try:
            if self.client:
                account = self.client.users_get_current_account()
                return account.email
        except Exception:
            pass
        return None

    def revoke_credentials(self) -> bool:
        """Revoke current credentials and delete token file."""
        try:
            if self.client:
                try:
                    self.client.auth_token_revoke()
                except Exception:
                    pass  # May fail if already revoked

            if os.path.exists(self.token_file):
                os.remove(self.token_file)

            self._client = None
            return True

        except Exception as e:
            print(f"Failed to revoke credentials: {e}")
            return False


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Dropbox OAuth2 Authentication Test")
    print("=" * 50)

    auth = DropboxAuth()

    if not auth.app_key:
        print("\nDropbox app not configured.")
        print("\nTo set up Dropbox:")
        print("1. Go to https://www.dropbox.com/developers/apps")
        print("2. Create a new app (App folder access)")
        print("3. Copy App key and App secret")
        print("4. Add to .env:")
        print("   DROPBOX_APP_KEY=your_key")
        print("   DROPBOX_APP_SECRET=your_secret")
        exit(1)

    print(f"\nApp key: {auth.app_key[:8]}...")
    print(f"Token file: {auth.token_file}")

    print("\nAttempting authentication...")
    if auth.is_authenticated():
        print("Authentication: SUCCESS")

        email = auth.get_user_email()
        if email:
            print(f"Authenticated as: {email}")

        # Test account info
        try:
            account = auth.client.users_get_current_account()
            print(f"Display name: {account.name.display_name}")
        except Exception as e:
            print(f"Failed to get account info: {e}")
    else:
        print("Authentication: FAILED")
