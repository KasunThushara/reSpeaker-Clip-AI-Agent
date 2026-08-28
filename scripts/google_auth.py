"""One-time Google OAuth authorization (CLI fallback).

Covers Gmail AND Google Calendar (they share one token.json).

Run this when the in-app flow is unavailable (e.g. headless reSpeaker
device without a browser):

    python scripts/google_auth.py           # authorize (or refresh) token.json
    python scripts/google_auth.py --force   # delete token.json and re-authorize

Requires credentials.json (Desktop-app OAuth client from Google Cloud
Console) in the project root. Honors HTTPS_PROXY for both the local
redirect server's outbound token exchange and the browser flow.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings  # noqa: E402
from backend.tools.calendar import CALENDAR_SCOPES as GOOGLE_SCOPES  # noqa: E402
from backend.tools.gmail import _reset_service  # noqa: E402
from backend.tools.calendar import _reset_service as _reset_calendar_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorize Gmail OAuth access")
    parser.add_argument(
        "--force",
        action="store_true",
        help="delete the existing token.json and re-authorize",
    )
    args = parser.parse_args()

    if not os.path.exists(settings.GMAIL_CREDENTIALS_FILE):
        print(
            f"ERROR: {settings.GMAIL_CREDENTIALS_FILE} not found. Download the "
            "OAuth client (Desktop app type) from Google Cloud Console first."
        )
        return 1

    if args.force and os.path.exists(settings.GMAIL_TOKEN_FILE):
        os.remove(settings.GMAIL_TOKEN_FILE)
        print(f"Removed {settings.GMAIL_TOKEN_FILE}")

    if os.path.exists(settings.GMAIL_TOKEN_FILE):
        # Token exists: try a silent refresh instead of a new authorization.
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        import requests

        creds = Credentials.from_authorized_user_file(
            settings.GMAIL_TOKEN_FILE, GOOGLE_SCOPES
        )
        if creds.valid:
            print("Token is still valid, nothing to do.")
            return 0
        if creds.refresh_token:
            try:
                session = requests.Session()
                session.trust_env = True
                creds.refresh(Request(session=session))
                with open(settings.GMAIL_TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
                _reset_service()
                _reset_calendar_service()
                print("Token refreshed successfully.")
                return 0
            except Exception as e:
                print(f"Refresh failed ({e}); falling back to re-authorization.")

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        settings.GMAIL_CREDENTIALS_FILE, GOOGLE_SCOPES
    )
    print("Opening browser for Google authorization...")
    creds = flow.run_local_server(port=0, prompt="consent")

    with open(settings.GMAIL_TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    _reset_service()
    _reset_calendar_service()
    print(f"Authorized. Token saved to {settings.GMAIL_TOKEN_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
