"""In-app Google OAuth flow for Gmail.

Exposes two endpoints:
- GET /api/gmail/auth/start   -> {"auth_url": ...} (or {"status": "already_authorized"})
- GET /api/gmail/auth/status  -> {"authorized": true/false}

The flow reuses the Desktop-app credentials.json and listens for Google's
redirect on a random loopback port (allowed for Desktop clients), so no
Console configuration change is needed. The token exchange happens inside
the WSGI handler before the success page is rendered, which means the
postMessage notification the page sends to the frontend can only arrive
after token.json is already written (no race).
"""

import json
import os
import threading
import wsgiref.simple_server
import wsgiref.util

from flask import Blueprint, jsonify

from config import settings
from backend.tools.calendar import CALENDAR_SCOPES as GOOGLE_SCOPES
from backend.tools.gmail import _reset_service
from backend.tools.calendar import _reset_service as _reset_calendar_service

google_auth_bp = Blueprint("google_auth", __name__)

_lock = threading.Lock()
_pending = {"status": "idle", "auth_url": None, "error": None}

# The success/error pages notify the opener window via postMessage and then
# close themselves. '*' origin because the popup lives on a random port.
_SUCCESS_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Google account connected</title></head>
<body style="font-family:sans-serif;text-align:center;padding-top:60px">
<h2>&#9989; Google account connected</h2>
<p>Gmail and Google Calendar are ready.</p>
<p>Returning to your conversation...</p>
<script>
  if (window.opener) {
    window.opener.postMessage({type: "gmail_authorized"}, "*");
  }
  setTimeout(function () { window.close(); }, 1500);
</script>
</body></html>"""

_ERROR_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Authorization failed</title></head>
<body style="font-family:sans-serif;text-align:center;padding-top:60px">
<h2>&#9888;&#65039; Google authorization failed</h2>
<p>{message}</p>
<p>You can close this window and try again.</p>
<script>
  if (window.opener) {{
    window.opener.postMessage({{type: "gmail_auth_error", error: {message_json}}}, "*");
  }}
</script>
</body></html>"""


def _has_refresh_token() -> bool:
    try:
        with open(settings.GMAIL_TOKEN_FILE) as f:
            return bool(json.load(f).get("refresh_token"))
    except (OSError, ValueError):
        return False


def _save_credentials(creds) -> None:
    with open(settings.GMAIL_TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def _run_flow():
    """Run the OAuth flow in this thread: wait for the redirect, exchange
    the code, persist the token. Mirrors InstalledAppFlow.run_local_server
    but split apart so the auth URL can be returned to the caller first."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        settings.GMAIL_CREDENTIALS_FILE, GOOGLE_SCOPES
    )
    result = {"html": _SUCCESS_PAGE, "error": None}

    def wsgi_app(environ, start_response):
        start_response("200 OK", [("Content-type", "text/html; charset=utf-8")])
        uri = wsgiref.util.request_uri(environ)
        try:
            # oauthlib refuses http:// authorization responses unless
            # OAUTHLIB_INSECURE_TRANSPORT is set. The official
            # run_local_server() sidesteps this by rewriting the scheme to
            # https before calling fetch_token (the token request itself
            # still goes to Google over real https), so we do the same.
            flow.fetch_token(authorization_response=uri.replace("http", "https"))
            _save_credentials(flow.credentials)
            _reset_service()
            _reset_calendar_service()
            _pending["status"] = "authorized"
            return [_SUCCESS_PAGE.encode("utf-8")]
        except Exception as e:  # user denied, network error, ...
            result["error"] = str(e)
            _pending["status"] = "error"
            _pending["error"] = str(e)
            message_json = json.dumps(str(e))
            page = _ERROR_PAGE.format(message=str(e), message_json=message_json)
            return [page.encode("utf-8")]

    server = wsgiref.simple_server.make_server("127.0.0.1", 0, wsgi_app)
    try:
        flow.redirect_uri = f"http://127.0.0.1:{server.server_port}/"
        auth_url, _state = flow.authorization_url(prompt="consent")
        _pending["auth_url"] = auth_url
        _pending["status"] = "waiting"
        # Block this (daemon) thread until Google redirects back once.
        server.handle_request()
    finally:
        server.server_close()


@google_auth_bp.route("/gmail/auth/start", methods=["GET"])
def google_auth_start():
    if not os.path.exists(settings.GMAIL_CREDENTIALS_FILE):
        return jsonify({
            "error": (
                "credentials.json not found. Download the OAuth client "
                "(Desktop app type) from Google Cloud Console and place it "
                "in the project root."
            )
        }), 500

    with _lock:
        if _pending["status"] == "waiting":
            # An authorization is already in flight; reuse its URL.
            return jsonify({"auth_url": _pending["auth_url"]})
        if _has_refresh_token():
            return jsonify({"status": "already_authorized"})

        _pending["status"] = "starting"
        _pending["auth_url"] = None
        _pending["error"] = None
        t = threading.Thread(target=_run_flow, daemon=True)
        t.start()

        # Wait briefly until the worker has generated the auth URL.
        for _ in range(50):
            if _pending["auth_url"]:
                break
            if _pending["status"] == "error":
                break
            threading.Event().wait(0.1)

        if not _pending["auth_url"]:
            _pending["status"] = "error"
            return jsonify({"error": _pending["error"] or "failed to start"}), 500
        return jsonify({"auth_url": _pending["auth_url"]})


@google_auth_bp.route("/gmail/auth/status", methods=["GET"])
def google_auth_status():
    return jsonify({"authorized": _has_refresh_token()})
