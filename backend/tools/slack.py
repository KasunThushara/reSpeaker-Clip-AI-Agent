import json
import logging

import httpx
from langchain_core.tools import tool

from config import settings

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"
SLACK_TIMEOUT = httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0)

MAX_CHANNELS = 20
MAX_MESSAGES = 10
MAX_SEARCH_RESULTS = 5
MAX_USERS = 30
MAX_TEXT_CHARS = 3000

SLACK_UNAVAILABLE = (
    "Slack tools are not configured: set SLACK_BOT_TOKEN in .env "
    "(a bot token from a Slack App installed to your workspace, starts with xoxb-)."
)
SLACK_USER_UNAVAILABLE = (
    "This Slack tool needs a user token: set SLACK_USER_TOKEN in .env "
    "(a user token from the same Slack App, starts with xoxp-)."
)


def _slack_get(method: str, params: dict, token: str | None = None) -> dict | str:
    """Call a Slack Web API method with GET. Returns parsed JSON or an error string."""
    try:
        response = httpx.get(
            f"{SLACK_API_BASE}/{method}",
            params=params,
            headers={"Authorization": f"Bearer {token or settings.SLACK_BOT_TOKEN}"},
            timeout=SLACK_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException:
        return "Slack request timed out. Please try again."
    except (httpx.HTTPError, ValueError) as exc:
        return f"Slack request failed: {exc}"

    if not data.get("ok"):
        return f"Slack error: {data.get('error', 'unknown error')}"
    return data


def _slack_post(method: str, payload: dict, token: str | None = None) -> dict | str:
    """Call a Slack Web API method with JSON POST. Returns parsed JSON or an error string."""
    try:
        response = httpx.post(
            f"{SLACK_API_BASE}/{method}",
            json=payload,
            headers={"Authorization": f"Bearer {token or settings.SLACK_BOT_TOKEN}"},
            timeout=SLACK_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException:
        return "Slack request timed out. Please try again."
    except (httpx.HTTPError, ValueError) as exc:
        return f"Slack request failed: {exc}"

    if not data.get("ok"):
        return f"Slack error: {data.get('error', 'unknown error')}"
    return data


def _compact_text(value: str, limit: int = MAX_TEXT_CHARS) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _format_message(msg: dict, users: dict[str, str]) -> dict:
    """Compact a Slack message into the fields the agent needs."""
    user_id = msg.get("user") or msg.get("bot_id") or ""
    return {
        "ts": msg.get("ts", ""),
        "user": users.get(user_id, user_id),
        "text": _compact_text(msg.get("text", "")),
        "replies": msg.get("reply_count", 0),
        "thread_ts": msg.get("thread_ts", ""),
    }


def _user_map(members: list[dict]) -> dict[str, str]:
    """Map user/bot IDs to display names."""
    users = {}
    for m in members:
        uid = m.get("id", "")
        if not uid:
            continue
        name = (
            m.get("profile", {}).get("display_name")
            or m.get("real_name")
            or m.get("name")
            or uid
        )
        users[uid] = name
    return users


@tool
def slack_list_channels(limit: int = 20) -> str:
    """List the Slack channels the bot can see in the workspace.
    Use this first when the user asks about Slack channels or wants to read
    messages but no channel was specified. limit is the maximum number of
    channels to return."""
    if not settings.SLACK_BOT_TOKEN:
        return SLACK_UNAVAILABLE

    data = _slack_get(
        "conversations.list",
        {"types": "public_channel", "limit": max(1, min(limit, MAX_CHANNELS))},
    )
    if isinstance(data, str):
        return data

    lines = []
    for ch in data.get("channels", []):
        lines.append(f"- #{ch.get('name', '')} (id: {ch.get('id', '')})")
    return "\n".join(lines) if lines else "No channels found."


@tool
def slack_read_channel(channel: str, limit: int = 5) -> str:
    """Read recent messages from a Slack channel.
    Use this when the user asks what's new on Slack or wants to catch up on a
    channel. channel can be a channel name like "general" or a channel ID
    beginning with C. Returns the most recent messages with sender names."""
    if not settings.SLACK_BOT_TOKEN:
        return SLACK_UNAVAILABLE
    channel = (channel or "").strip().lstrip("#")
    if not channel:
        return "Channel name or ID is required."

    # Resolve a channel name to its ID via conversations.list.
    channel_id = channel
    if not channel.startswith("C"):
        listing = _slack_get("conversations.list", {"types": "public_channel", "limit": 200})
        if isinstance(listing, str):
            return listing
        match = next(
            (c for c in listing.get("channels", []) if c.get("name") == channel),
            None,
        )
        if not match:
            return f"Channel #{channel} not found. Use slack_list_channels to see available channels."
        channel_id = match["id"]

    history = _slack_get(
        "conversations.history",
        {"channel": channel_id, "limit": max(1, min(limit, MAX_MESSAGES))},
    )
    if isinstance(history, str):
        return history

    # Fetch member names so messages read naturally.
    members = _slack_get("users.list", {"limit": MAX_USERS})
    users = _user_map(members.get("members", [])) if isinstance(members, dict) else {}

    messages = [
        _format_message(m, users)
        for m in reversed(history.get("messages", []))
        if not m.get("subtype")
    ]
    if not messages:
        return f"No recent messages in #{channel}."

    lines = [f"Recent messages in #{channel}:"]
    for m in messages:
        reply_note = f" ({m['replies']} replies)" if m["replies"] else ""
        lines.append(f"- {m['user']}: {m['text']}{reply_note}")
    return "\n".join(lines)


@tool
def slack_read_thread(channel: str, thread_ts: str) -> str:
    """Read all replies in a Slack message thread.
    Use this when the user asks about the replies to a specific message.
    channel is the channel name or ID; thread_ts is the ts value of the
    parent message returned by slack_read_channel."""
    if not settings.SLACK_BOT_TOKEN:
        return SLACK_UNAVAILABLE
    channel = (channel or "").strip().lstrip("#")
    if not channel or not (thread_ts or "").strip():
        return "Channel and thread_ts are required."

    channel_id = channel
    if not channel.startswith("C"):
        listing = _slack_get("conversations.list", {"types": "public_channel", "limit": 200})
        if isinstance(listing, str):
            return listing
        match = next(
            (c for c in listing.get("channels", []) if c.get("name") == channel),
            None,
        )
        if not match:
            return f"Channel #{channel} not found."
        channel_id = match["id"]

    replies = _slack_get(
        "conversations.replies",
        {"channel": channel_id, "ts": thread_ts.strip(), "limit": MAX_MESSAGES},
    )
    if isinstance(replies, str):
        return replies

    members = _slack_get("users.list", {"limit": MAX_USERS})
    users = _user_map(members.get("members", [])) if isinstance(members, dict) else {}

    messages = [
        _format_message(m, users)
        for m in replies.get("messages", [])
        if not m.get("subtype")
    ]
    if not messages:
        return "No replies found in that thread."

    lines = ["Thread replies:"]
    for m in messages:
        lines.append(f"- {m['user']}: {m['text']}")
    return "\n".join(lines)


@tool
def slack_search_messages(query: str, limit: int = 5) -> str:
    """Search messages across the Slack workspace.
    Use this when the user asks to find discussions or messages about a topic
    in Slack. Requires the search:read scope and a paid Slack plan."""
    if not settings.SLACK_BOT_TOKEN:
        return SLACK_UNAVAILABLE
    query = (query or "").strip()
    if not query:
        return "Search query is required."

    data = _slack_get(
        "search.messages",
        {"query": query, "count": max(1, min(limit, MAX_SEARCH_RESULTS))},
    )
    if isinstance(data, str):
        return data

    matches = data.get("messages", {}).get("matches", [])
    if not matches:
        return f"No Slack messages found for: {query}"

    lines = []
    for m in matches:
        channel = m.get("channel", {}).get("name", "")
        user = m.get("username") or m.get("user", "")
        lines.append(
            f"- #{channel} | {user}: {_compact_text(m.get('text', ''), 200)}"
        )
    return "\n".join(lines)


@tool
def slack_send_message(channel: str, text: str) -> str:
    """Send a message to a Slack channel or DM.
    Use this ONLY when the user explicitly asks to send a Slack message.
    channel can be a channel name like "general", a channel ID, or a user
    name to DM (the bot opens/uses the DM)."""
    if not settings.SLACK_BOT_TOKEN:
        return SLACK_UNAVAILABLE
    channel = (channel or "").strip().lstrip("#")
    text = (text or "").strip()
    if not channel or not text:
        return "Channel and message text are required."

    # A user name means "DM this person": resolve via users.list + conversations.open.
    channel_id = channel
    if not channel.startswith(("C", "D")):
        listing = _slack_get("conversations.list", {"types": "public_channel", "limit": 200})
        if isinstance(listing, str):
            return listing
        match = next(
            (c for c in listing.get("channels", []) if c.get("name") == channel),
            None,
        )
        if match:
            channel_id = match["id"]
        else:
            members = _slack_get("users.list", {"limit": MAX_USERS})
            if not isinstance(members, dict):
                return members
            users = _user_map(members.get("members", []))
            user_id = next(
                (uid for uid, name in users.items() if name.lower() == channel.lower()),
                None,
            )
            if not user_id:
                return f"No channel or user named '{channel}' found."
            dm = _slack_post("conversations.open", {"users": user_id})
            if isinstance(dm, str):
                return dm
            channel_id = dm.get("channel", {}).get("id", "")
            if not channel_id:
                return f"Could not open a DM with {channel}."

    data = _slack_post("chat.postMessage", {"channel": channel_id, "text": text})
    if isinstance(data, str):
        return data
    return f"Message sent to {channel}."


@tool
def slack_schedule_message(channel: str, text: str, post_at: str) -> str:
    """Schedule a Slack message to be sent later.
    Use this when the user asks to send a message at a specific future time,
    e.g. "tomorrow 9am". post_at is a Unix timestamp (seconds) for when the
    message should be sent; compute it from the current time."""
    if not settings.SLACK_BOT_TOKEN:
        return SLACK_UNAVAILABLE
    channel = (channel or "").strip().lstrip("#")
    text = (text or "").strip()
    if not channel or not text or not (post_at or "").strip():
        return "Channel, message text, and post_at timestamp are required."

    try:
        post_at_int = int(float(post_at))
    except ValueError:
        return "post_at must be a Unix timestamp in seconds."

    channel_id = channel
    if not channel.startswith(("C", "D")):
        listing = _slack_get("conversations.list", {"types": "public_channel", "limit": 200})
        if isinstance(listing, str):
            return listing
        match = next(
            (c for c in listing.get("channels", []) if c.get("name") == channel),
            None,
        )
        if not match:
            return f"Channel #{channel} not found."
        channel_id = match["id"]

    data = _slack_post(
        "chat.scheduleMessage",
        {"channel": channel_id, "text": text, "post_at": post_at_int},
    )
    if isinstance(data, str):
        return data
    return f"Message scheduled for {post_at_int} in {channel}."


@tool
def slack_add_reminder(text: str, time: str) -> str:
    """Create a Slack reminder for the user via Slackbot.
    Use this when the user asks to be reminded about something, e.g.
    "remind me to check the deploy in 2 hours". time is a natural language
    string like "in 2 hours", "tomorrow at 9am", or "on Friday".
    Requires a user token (SLACK_USER_TOKEN)."""
    if not settings.SLACK_USER_TOKEN:
        return SLACK_USER_UNAVAILABLE
    text = (text or "").strip()
    time = (time or "").strip()
    if not text or not time:
        return "Reminder text and time are required."

    data = _slack_post("reminders.add", {"text": text, "time": time}, token=settings.SLACK_USER_TOKEN)
    if isinstance(data, str):
        return data
    return f"Reminder set: {text} ({time})."


@tool
def slack_list_users(limit: int = 30) -> str:
    """List the people in the Slack workspace with their display names.
    Use this when the user asks who is on Slack or needs to find someone to
    mention or DM. limit is the maximum number of people to return."""
    if not settings.SLACK_BOT_TOKEN:
        return SLACK_UNAVAILABLE

    data = _slack_get("users.list", {"limit": max(1, min(limit, MAX_USERS))})
    if isinstance(data, str):
        return data

    lines = []
    for m in data.get("members", []):
        if m.get("deleted") or m.get("is_bot"):
            continue
        name = (
            m.get("profile", {}).get("display_name")
            or m.get("real_name")
            or m.get("name")
            or m.get("id")
        )
        lines.append(f"- {name}")
    return "\n".join(lines) if lines else "No users found."


@tool
def slack_set_dnd(duration_minutes: int = 60) -> str:
    """Turn on Slack Do Not Disturb (snooze notifications) for a duration.
    Use this when the user asks to pause or mute Slack notifications, e.g.
    "mute Slack for an hour". Set duration_minutes to 0 to end snooze early.
    Requires a user token (SLACK_USER_TOKEN)."""
    if not settings.SLACK_USER_TOKEN:
        return SLACK_USER_UNAVAILABLE

    if duration_minutes <= 0:
        data = _slack_post("dnd.endSnooze", {}, token=settings.SLACK_USER_TOKEN)
    else:
        data = _slack_post(
            "dnd.setSnooze",
            {"num_minutes": min(duration_minutes, 24 * 60)},
            token=settings.SLACK_USER_TOKEN,
        )
    if isinstance(data, str):
        return data
    if duration_minutes <= 0:
        return "Do Not Disturb snooze ended."
    return f"Do Not Disturb enabled for {duration_minutes} minutes."
