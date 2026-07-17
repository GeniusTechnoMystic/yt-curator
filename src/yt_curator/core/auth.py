"""
OAuth 2.0 authentication for YouTube Data API v3.

Provides browser-based first-time auth and stores a refresh token in
~/.config/yt-curator/credentials.json for subsequent headless use.
"""

import json
import webbrowser
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes needed for full playlist read/write
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# Read-only scope — sufficient for inventory scans
SCOPES_READONLY = [
    "https://www.googleapis.com/auth/youtube.readonly",
]

CONFIG_DIR = Path.home() / ".config" / "yt-curator"
TOKEN_FILE = CONFIG_DIR / "token.json"
CLIENT_SECRET_FILE = CONFIG_DIR / "client_secret.json"


def get_credentials(read_only: bool = False) -> Credentials:
    """Obtain valid OAuth 2.0 credentials.

    1. Load stored token from ``token.json`` (refresh if expired).
    2. If no valid token, run the OAuth flow using ``client_secret.json``.
    3. Save the new/refreshed token for next time.

    Args:
        read_only: If True, use youtube.readonly scope (no write access).

    Returns:
        Google OAuth2 Credentials object.

    Raises:
        FileNotFoundError: If ``client_secret.json`` is missing and no
            stored token is available.
    """
    creds: Credentials | None = None

    # Load existing token
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except (ValueError, json.JSONDecodeError):
            creds = None

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except Exception:
            creds = None

    # Valid and not expired
    if creds and creds.valid:
        return creds

    # Need full auth flow
    if not CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            f"No OAuth credentials found at {CLIENT_SECRET_FILE}\n"
            f"Create a Google Cloud project, enable YouTube Data API v3,\n"
            f"download OAuth 2.0 client credentials, and save them to:\n"
            f"  {CLIENT_SECRET_FILE}\n\n"
            f"See: https://developers.google.com/youtube/v3/getting-started"
        )

    scopes = SCOPES_READONLY if read_only else SCOPES
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), scopes)
    creds = flow.run_local_server(port=8080, open_browser=True)
    _save_token(creds)
    return creds


def _save_token(creds: Credentials) -> None:
    """Persist credentials to token.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    # Secure the token file
    TOKEN_FILE.chmod(0o600)


def has_valid_token(read_only: bool = False) -> bool:
    """Check if a usable OAuth token exists without triggering a flow.

    Args:
        read_only: If True, checks for a token with at least read-only scope.
    """
    if not TOKEN_FILE.exists():
        return False
    try:
        scopes = SCOPES_READONLY if read_only else SCOPES
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), scopes)
        return creds.valid or (creds.expired and creds.refresh_token is not None)
    except Exception:
        return False


def get_api_key() -> str | None:
    """Read a YouTube API key from config if present."""
    key_file = CONFIG_DIR / "api_key.txt"
    if key_file.exists():
        return key_file.read_text().strip()
    return None
