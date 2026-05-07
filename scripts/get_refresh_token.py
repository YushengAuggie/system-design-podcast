#!/usr/bin/env python3
"""One-time OAuth2 flow to obtain a YouTube refresh token.

Usage:
    python scripts/get_refresh_token.py

This opens a browser for Google sign-in, then prints the refresh token
to add to your .env file.
"""

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = Path(__file__).parent.parent / "client_secret.json"


def main() -> None:
    if not CLIENT_SECRET_FILE.exists():
        print(f"ERROR: {CLIENT_SECRET_FILE} not found.")
        print("Download it from Google Cloud Console → Credentials → OAuth 2.0 Client.")
        raise SystemExit(1)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        scopes=SCOPES,
    )

    # This opens a browser window for consent
    creds = flow.run_local_server(port=8085, prompt="consent", access_type="offline")

    print("\n✅ Authorization successful!\n")
    print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")

    # Also save token.json as backup
    token_path = CLIENT_SECRET_FILE.parent / "token.json"
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    token_path.write_text(json.dumps(token_data, indent=2))
    print(f"\nToken also saved to {token_path}")
    print("\nAdd these to your .env file, then you're good to go! 🎉")


if __name__ == "__main__":
    main()
