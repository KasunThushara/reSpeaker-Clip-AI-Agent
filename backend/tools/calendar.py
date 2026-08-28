import os
from datetime import datetime, timedelta

from langchain_core.tools import tool

from config import settings
from backend.tools.gmail import GMAIL_SCOPES, _reset_service as _reset_gmail_service

# Calendar shares the Google account connection (token.json) with Gmail.
CALENDAR_SCOPES = GMAIL_SCOPES + [
    "https://www.googleapis.com/auth/calendar",
]

MAX_EVENTS = 10
MAX_DESCRIPTION_CHARS = 300
CALENDAR_HTTP_TIMEOUT = 15

CALENDAR_UNAVAILABLE = (
    "Calendar tools are unavailable: the user's Google account is not connected yet. "
    "Tell the user (in their language) that Google Calendar is NOT CONNECTED and "
    "they need to connect their Google account first (a connect button should "
    "appear in the chat UI). "
    "Do not retry the tool call in this turn."
)

_service = None


def _reset_service() -> None:
    """Drop the cached Calendar service (used by tests)."""
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
    """Build (and cache) an authenticated Calendar service client.

    Returns None when the token file is missing, i.e. the user has not
    connected their Google account yet. Mirrors gmail._get_service,
    including the httplib2 proxy workaround (httplib2 ignores
    HTTPS_PROXY env vars, so we pass an explicit ProxyInfo).
    """
    global _service
    if _service is not None:
        return _service
    if not os.path.exists(settings.GMAIL_TOKEN_FILE):
        return None

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(
        settings.GMAIL_TOKEN_FILE, CALENDAR_SCOPES
    )
    if not creds.valid:
        if not creds.refresh_token:
            return None
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
                timeout=CALENDAR_HTTP_TIMEOUT,
                proxy_info=httplib2.ProxyInfo(
                    proxy_type=httplib2.socks.PROXY_TYPE_HTTP,
                    proxy_host=parsed.hostname,
                    proxy_port=parsed.port or 7897,
                    proxy_user=parsed.username or None,
                    proxy_pass=parsed.password or None,
                ),
            ),
        )
        _service = build("calendar", "v3", http=http, static_discovery=True)
    else:
        _service = build("calendar", "v3", credentials=creds, static_discovery=True)
    return _service


def _fmt_event(event: dict, include_description: bool = False) -> str:
    """Format one Calendar event for compact LLM/voice output."""
    start = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date") or "?"
    end = (event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get("date") or "?"
    line = f"id {event.get('id')}: \"{event.get('summary') or '(no title)'}\" {start} → {end}"
    location = event.get("location")
    if location:
        line += f" @ {location}"
    if include_description:
        description = (event.get("description") or "")[:MAX_DESCRIPTION_CHARS]
        if description:
            line += f" — {description}"
    return line


def _parse_days(days: int) -> tuple[datetime, datetime]:
    """Clamp the requested day range and return (time_min, time_max)."""
    now = datetime.now()
    days = max(1, min(int(days), 31))
    return now, now + timedelta(days=days)


@tool
def calendar_list_events(days: int = 7, query: str = "") -> str:
    """List the user's upcoming Google Calendar events. days is how many
    days ahead to look (1-31, default 7); query optionally filters events
    by keyword in the title/description. Returns each event's id, title,
    start and end times, and location. Use the returned id with
    calendar_update_event or calendar_delete_event."""
    try:
        service = _get_service()
        if service is None:
            return CALENDAR_UNAVAILABLE
        time_min, time_max = _parse_days(days)
        kwargs = {
            "calendarId": "primary",
            "timeMin": time_min.isoformat() + "Z",
            "timeMax": time_max.isoformat() + "Z",
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": MAX_EVENTS,
        }
        if query and query.strip():
            kwargs["q"] = query.strip()
        response = service.events().list(**kwargs).execute()
        events = response.get("items") or []
        if not events:
            return f"No upcoming events found in the next {days} day(s)."
        lines = [_fmt_event(e) for e in events]
        return f"Found {len(lines)} upcoming event(s):\n" + "\n".join(lines)
    except Exception as e:
        return f"Listing events failed: {e}"


@tool
def calendar_quick_add(text: str) -> str:
    """Create a Google Calendar event from a natural-language sentence,
    e.g. 'dentist appointment tomorrow at 3pm' or 'team standup every
    weekday at 9:30am'. Google parses the time and recurrence itself, so
    pass the user's wording as-is. Returns the created event."""
    if not text or not text.strip():
        return "text is required."
    try:
        service = _get_service()
        if service is None:
            return CALENDAR_UNAVAILABLE
        event = (
            service.events()
            .quickAdd(calendarId="primary", text=text.strip())
            .execute()
        )
        return f"Event created: {_fmt_event(event)}"
    except Exception as e:
        return f"Creating event failed: {e}"


@tool
def calendar_create_event(
    title: str,
    start: str,
    end: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """Create a Google Calendar event with explicit times. start and end
    are ISO 8601 strings WITH timezone offset, e.g.
    '2026-08-29T14:00:00+08:00'. end is optional for all-day or
    point-in-time events. Prefer calendar_quick_add when the user gives
    a natural-language time; use this when exact times are known."""
    if not (title and title.strip() and start and start.strip()):
        return "title and start are required."
    try:
        service = _get_service()
        if service is None:
            return CALENDAR_UNAVAILABLE
        body: dict = {"summary": title.strip()}
        if "T" in start:
            body["start"] = {"dateTime": start.strip()}
            if end and end.strip():
                body["end"] = {"dateTime": end.strip()}
            else:
                body["end"] = {"dateTime": start.strip()}
        else:
            body["start"] = {"date": start.strip()}
            body["end"] = {"date": (end or start).strip()}
        if description and description.strip():
            body["description"] = description.strip()
        if location and location.strip():
            body["location"] = location.strip()
        event = service.events().insert(calendarId="primary", body=body).execute()
        return f"Event created: {_fmt_event(event)}"
    except Exception as e:
        return f"Creating event failed: {e}"


@tool
def calendar_update_event(event_id: str, title: str = "", start: str = "", end: str = "") -> str:
    """Update an existing Google Calendar event by id (the id returned by
    calendar_list_events). Only the fields you provide are changed: title,
    start, and/or end (ISO 8601 with timezone offset, e.g.
    '2026-08-29T15:00:00+08:00'). Returns the updated event."""
    if not event_id or not event_id.strip():
        return "event_id is required."
    if not any((title and title.strip(), start and start.strip(), end and end.strip())):
        return "At least one of title, start, or end must be provided."
    try:
        service = _get_service()
        if service is None:
            return CALENDAR_UNAVAILABLE
        body: dict = {}
        if title and title.strip():
            body["summary"] = title.strip()
        if start and start.strip():
            key = "dateTime" if "T" in start else "date"
            body["start"] = {key: start.strip()}
        if end and end.strip():
            key = "dateTime" if "T" in end else "date"
            body["end"] = {key: end.strip()}
        event = (
            service.events()
            .patch(calendarId="primary", eventId=event_id.strip(), body=body)
            .execute()
        )
        return f"Event updated: {_fmt_event(event)}"
    except Exception as e:
        return f"Updating event failed: {e}"


@tool
def calendar_delete_event(event_id: str) -> str:
    """Delete a Google Calendar event by id (the id returned by
    calendar_list_events). This cannot be undone — confirm with the user
    before deleting."""
    if not event_id or not event_id.strip():
        return "event_id is required."
    try:
        service = _get_service()
        if service is None:
            return CALENDAR_UNAVAILABLE
        service.events().delete(
            calendarId="primary", eventId=event_id.strip()
        ).execute()
        return f"Event {event_id.strip()} deleted."
    except Exception as e:
        return f"Deleting event failed: {e}"


@tool
def calendar_find_free_time(date: str, start_hour: int = 8, end_hour: int = 20) -> str:
    """Find free (unbooked) time slots on a given date, e.g. '2026-08-29'.
    start_hour/end_hour limit the working window to search (default 8-20,
    24h clock). Returns the busy intervals and the free gaps between
    them."""
    if not date or not date.strip():
        return "date is required (YYYY-MM-DD)."
    try:
        service = _get_service()
        if service is None:
            return CALENDAR_UNAVAILABLE
        day = date.strip()
        start_hour = max(0, min(int(start_hour), 23))
        end_hour = max(start_hour + 1, min(int(end_hour), 24))
        time_min = f"{day}T{start_hour:02d}:00:00"
        time_max = f"{day}T{end_hour:02d}:00:00"
        response = (
            service.freebusy()
            .query(
                body={
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "items": [{"id": "primary"}],
                }
            )
            .execute()
        )
        busy = sorted(
            (period.get("start"), period.get("end"))
            for cal in (response.get("calendars") or {}).values()
            for period in cal.get("busy") or []
        )
        if not busy:
            return f"No busy periods on {day} between {start_hour}:00 and {end_hour}:00 — the whole window is free."
        busy_lines = [f"  busy: {s} → {e}" for s, e in busy]
        # Compute free gaps inside the window.
        free_lines = []
        cursor = time_min
        for s, e in busy:
            if s and s > cursor:
                free_lines.append(f"  free: {cursor} → {s}")
            if e and e > cursor:
                cursor = e
        if cursor < time_max:
            free_lines.append(f"  free: {cursor} → {time_max}")
        return (
            f"Schedule for {day} ({start_hour}:00–{end_hour}:00):\n"
            + "\n".join(busy_lines + free_lines)
        )
    except Exception as e:
        return f"Finding free time failed: {e}"
