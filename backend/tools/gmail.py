import os

from langchain_core.tools import tool

from config import settings


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

MAX_RESULTS = 5
MAX_SNIPPET_CHARS = 100
MAX_BODY_CHARS = 2000
GMAIL_HTTP_TIMEOUT = 15

GMAIL_UNAVAILABLE = (
    "Gmail tools are unavailable: the user's Google account is not connected yet. "
    "Tell the user (in their language) that Gmail is NOT CONNECTED and they "
    "need to connect their Google account first (a connect button should "
    "appear in the chat UI). "
    "Do not retry the tool call in this turn."
)

_service = None


def _reset_service() -> None:
    """Drop the cached Gmail service (used by tests)."""
    global _service
    _service = None


def _save_token(creds) -> None:
    """Persist refreshed credentials so the next start skips re-auth."""
    try:
        with open(settings.GMAIL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    except OSError:
        pass


def _get_service():
    """Build (and cache) an authenticated Gmail service client.

    Returns None when the token file is missing, i.e. the user has not run
    the one-time authorization script yet.

    httplib2 (used by googleapiclient) ignores HTTPS_PROXY/HTTP_PROXY env
    vars, so when a proxy is configured we pass an explicit ProxyInfo.
    """
    global _service
    if _service is not None:
        return _service
    if not os.path.exists(settings.GMAIL_TOKEN_FILE):
        return None

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(settings.GMAIL_TOKEN_FILE, GMAIL_SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            return None
        # requests.Session honors HTTPS_PROXY env vars; give the refresh
        # call an explicit timeout so it cannot hang forever.
        import requests

        session = requests.Session()
        session.trust_env = True
        creds.refresh(Request(session=session))
        _save_token(creds)

    proxy_url = (
        os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or ""
    ).strip()
    if proxy_url:
        import httplib2
        from urllib.parse import urlparse

        from google_auth_httplib2 import AuthorizedHttp

        parsed = urlparse(proxy_url if "//" in proxy_url else f"http://{proxy_url}")
        http = AuthorizedHttp(
            creds,
            http=httplib2.Http(
                timeout=GMAIL_HTTP_TIMEOUT,
                proxy_info=httplib2.ProxyInfo(
                    proxy_type=httplib2.socks.PROXY_TYPE_HTTP,
                    proxy_host=parsed.hostname,
                    proxy_port=parsed.port or 7897,
                    proxy_user=parsed.username or None,
                    proxy_pass=parsed.password or None,
                ),
            ),
        )
        _service = build("gmail", "v1", http=http, static_discovery=True)
    else:
        _service = build("gmail", "v1", credentials=creds, static_discovery=True)
    return _service


def _decode_data(data: str) -> str:
    """Decode a base64url-encoded message body (Gmail omits padding)."""
    import base64

    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")


def _header(payload: dict, name: str) -> str:
    """Return a header value from a message payload (case-insensitive)."""
    for header in payload.get("headers") or []:
        if (header.get("name") or "").lower() == name.lower():
            return header.get("value") or ""
    return ""


def _strip_html(html: str) -> str:
    """Crude HTML-to-text conversion, enough for voice output."""
    import re

    text = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    return re.sub(r"\n\s*\n+|\s{2,}", lambda m: "\n" if "\n" in m.group() else " ", text).strip()


def _extract_body(payload: dict) -> str:
    """Walk the MIME tree: prefer text/plain, fall back to stripped HTML."""
    plain, html = "", ""
    queue = [payload]
    while queue:
        part = queue.pop(0)
        data = (part.get("body") or {}).get("data")
        if data:
            mime = part.get("mimeType") or ""
            if mime == "text/plain" and not plain:
                plain = _decode_data(data)
            elif mime == "text/html" and not html:
                html = _decode_data(data)
        queue.extend(part.get("parts") or [])
    if not plain and not html:
        data = (payload.get("body") or {}).get("data")
        if data:
            decoded = _decode_data(data)
            html = decoded if "html" in (payload.get("mimeType") or "") else decoded
            plain = "" if html is decoded else decoded
    return plain or _strip_html(html)


def _compact_message(msg: dict, body_chars: int = 0) -> dict:
    """Keep only the fields the agent needs from a message response."""
    payload = msg.get("payload") or {}
    result = {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from": _header(payload, "From"),
        "to": _header(payload, "To"),
        "subject": _header(payload, "Subject"),
        "date": _header(payload, "Date"),
        "snippet": (msg.get("snippet") or "")[:MAX_SNIPPET_CHARS],
    }
    if body_chars:
        body = _extract_body(payload) or msg.get("snippet") or ""
        result["body"] = body[:body_chars]
    return result


def _build_raw(to: str, subject: str, body: str) -> str:
    """Build a base64url-encoded RFC 2822 message ready for the API."""
    import base64
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


@tool
def gmail_search_messages(query: str, max_results: int = MAX_RESULTS) -> str:
    """Search the user's Gmail mailbox. Supports Gmail search syntax such as
    'from:alice@example.com', 'subject:invoice', 'is:unread',
    'newer_than:1d', or plain keywords. Returns the newest matching
    messages with id, subject, sender, date, and a short snippet. Use the
    returned id with gmail_get_message to read the full body."""
    try:
        service = _get_service()
        if service is None:
            return GMAIL_UNAVAILABLE
        max_results = max(1, min(int(max_results), 10))
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = response.get("messages") or []
        if not messages:
            return f"No messages found matching '{query}'."

        lines = []
        for i, item in enumerate(messages, start=1):
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=item["id"], format="metadata")
                .execute()
            )
            compact = _compact_message(detail)
            lines.append(
                f"{i}. id {compact['id']}: \"{compact['subject'] or '(no subject)'}\" "
                f"from {compact['from'] or 'unknown'} ({compact['date']}) — {compact['snippet']}"
            )
        return f"Found {len(lines)} messages for '{query}':\n" + "\n".join(lines)
    except Exception as e:
        return f"Gmail search failed: {e}"


@tool
def gmail_get_message(message_id: str) -> str:
    """Read one Gmail message by id (the id returned by gmail_search_messages).
    Returns sender, recipient, subject, date, and the plain-text body
    (truncated)."""
    if not message_id or not message_id.strip():
        return "message_id is required."
    try:
        service = _get_service()
        if service is None:
            return GMAIL_UNAVAILABLE
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id.strip(), format="full")
            .execute()
        )
        compact = _compact_message(msg, body_chars=MAX_BODY_CHARS)
        return (
            f"From: {compact['from']}\n"
            f"To: {compact['to']}\n"
            f"Subject: {compact['subject']}\n"
            f"Date: {compact['date']}\n"
            f"Body: {compact['body'] or compact['snippet']}"
        )
    except Exception as e:
        return f"Reading message failed: {e}"


@tool
def gmail_create_draft(to: str, subject: str, body: str) -> str:
    """Create a Gmail draft (NOT sent). Use this when the user wants to
    compose, write, or reply to an email but has not explicitly asked to
    send it. The user can review and send it from Gmail themselves."""
    if not (to and to.strip() and subject and subject.strip() and body and body.strip()):
        return "to, subject, and body are all required."
    try:
        service = _get_service()
        if service is None:
            return GMAIL_UNAVAILABLE
        raw = _build_raw(to.strip(), subject.strip(), body.strip())
        draft = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )
        return f"Draft created (id: {draft.get('id')}) to {to}: '{subject}'."
    except Exception as e:
        return f"Creating draft failed: {e}"


@tool
def gmail_send_message(to: str, subject: str, body: str) -> str:
    """Send an email immediately from the user's Gmail account. Only use
    when the user EXPLICITLY asks to send an email right now; otherwise
    prefer gmail_create_draft so the user can review it first."""
    if not (to and to.strip() and subject and subject.strip() and body and body.strip()):
        return "to, subject, and body are all required."
    try:
        service = _get_service()
        if service is None:
            return GMAIL_UNAVAILABLE
        raw = _build_raw(to.strip(), subject.strip(), body.strip())
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        return f"Message sent to {to}: '{subject}' (id: {sent.get('id')})."
    except Exception as e:
        return f"Sending message failed: {e}"


@tool
def gmail_list_labels(limit: int = 50) -> str:
    """List the labels in the user's Gmail account (e.g. INBOX, STARRED,
    and custom labels). Useful for understanding how mail is organized.
    limit is the maximum number of labels to return."""
    try:
        service = _get_service()
        if service is None:
            return GMAIL_UNAVAILABLE
        response = service.users().labels().list(userId="me").execute()
        names = [
            label.get("name")
            for label in response.get("labels") or []
            if label.get("name")
        ][:max(1, min(limit, 100))]
        if not names:
            return "No labels found."
        return "Labels: " + ", ".join(names)
    except Exception as e:
        return f"Listing labels failed: {e}"
