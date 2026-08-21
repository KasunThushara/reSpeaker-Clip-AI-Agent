import logging

import httpx
from langchain_core.tools import tool

from config import settings

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"

TASK_PROP = "Task"
STATUS_PROP = "Status"
STATUS_TODO = "To Do"
STATUS_DONE = "Done"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _get_task_title(page: dict) -> str:
    try:
        return "".join(t["plain_text"] for t in page["properties"][TASK_PROP]["title"])
    except (KeyError, TypeError):
        return "(untitled)"


def _get_status(page: dict) -> str:
    try:
        select = page["properties"][STATUS_PROP]["select"]
        return select["name"] if select else "No Status"
    except (KeyError, TypeError):
        return "No Status"


_data_source_cache = {}


def _get_data_source_id() -> str:
    """Resolve the data source id for the configured database (new API)."""
    db_id = settings.NOTION_DATABASE_ID
    if db_id in _data_source_cache:
        return _data_source_cache[db_id]
    resp = httpx.get(f"{NOTION_API}/databases/{db_id}", headers=_headers(), timeout=15)
    resp.raise_for_status()
    data_sources = resp.json().get("data_sources", [])
    if not data_sources:
        raise RuntimeError("Database has no data source")
    ds_id = data_sources[0]["id"]
    _data_source_cache[db_id] = ds_id
    return ds_id


def _query_database(filter_payload: dict | None = None) -> list[dict]:
    data_source_id = _get_data_source_id()
    payload = {"page_size": 100}
    if filter_payload:
        payload["filter"] = filter_payload
    resp = httpx.post(
        f"{NOTION_API}/data_sources/{data_source_id}/query",
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def _find_task_page(task_keyword: str) -> str | None:
    try:
        results = _query_database(
            {"property": TASK_PROP, "title": {"contains": task_keyword}}
        )
    except Exception:
        return None
    return results[0]["id"] if results else None


@tool
def add_todo(task: str) -> str:
    """Add a task to the user's Notion to-do list."""
    try:
        payload = {
            "parent": {"database_id": settings.NOTION_DATABASE_ID},
            "properties": {
                TASK_PROP: {"title": [{"text": {"content": task}}]},
                STATUS_PROP: {"select": {"name": STATUS_TODO}},
            },
        }
        resp = httpx.post(f"{NOTION_API}/pages", headers=_headers(), json=payload, timeout=15)
        resp.raise_for_status()
        return f"Added task: {task}"
    except Exception as e:
        return f"Error adding task: {e}"


@tool
def list_todos() -> str:
    """List all tasks in the user's Notion to-do list with their status."""
    try:
        results = _query_database()
    except Exception as e:
        return f"Error listing tasks: {e}"
    if not results:
        return "Your to-do list is empty."
    lines = [f"{i}. {_get_task_title(p)} ({_get_status(p)})" for i, p in enumerate(results, 1)]
    return "\n".join(lines)


@tool
def complete_todo(task: str) -> str:
    """Mark a task as Done in the user's Notion to-do list. Pass the task name or a keyword."""
    page_id = _find_task_page(task)
    if not page_id:
        return f"Task not found: {task}"
    try:
        resp = httpx.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers=_headers(),
            json={"properties": {STATUS_PROP: {"select": {"name": STATUS_DONE}}}},
            timeout=15,
        )
        resp.raise_for_status()
        return f"Marked as done: {task}"
    except Exception as e:
        return f"Error completing task: {e}"


@tool
def delete_todo(task: str) -> str:
    """Delete a task from the user's Notion to-do list. Pass the task name or a keyword."""
    page_id = _find_task_page(task)
    if not page_id:
        return f"Task not found: {task}"
    try:
        resp = httpx.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers=_headers(),
            json={"in_trash": True},
            timeout=15,
        )
        resp.raise_for_status()
        return f"Deleted task: {task}"
    except Exception as e:
        return f"Error deleting task: {e}"


def get_notion_tools() -> list:
    if not settings.NOTION_API_KEY or not settings.NOTION_DATABASE_ID:
        logger.warning(
            "Notion not configured: set NOTION_API_KEY and NOTION_DATABASE_ID"
        )
        return []
    return [add_todo, list_todos, complete_todo, delete_todo]


def _find_database_id(name: str) -> str | None:
    try:
        resp = httpx.post(
            f"{NOTION_API}/search",
            headers=_headers(),
            json={
                "query": name,
                "filter": {
                    "property": "object",
                    "value": "data_source",
                    "in_trash": False,
                },
                "page_size": 10,
            },
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Notion search failed: %s", e)
        return None
    for r in resp.json().get("results", []):
        title = "".join(t.get("plain_text", "") for t in r.get("title", []))
        if title.lower() == name.lower():
            return r["id"]
    return None


def _create_parent_page(title: str) -> str:
    payload = {
        "parent": {"type": "workspace", "workspace": True},
        "properties": {"title": [{"text": {"content": title}}]},
    }
    resp = httpx.post(f"{NOTION_API}/pages", headers=_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()["id"]


def _create_database(parent_page_id: str, name: str) -> str:
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"text": {"content": name}}],
        "initial_data_source": {
            "properties": {
                TASK_PROP: {"title": {}},
                STATUS_PROP: {"select": {"options": [{"name": STATUS_TODO}, {"name": STATUS_DONE}]}},
            }
        },
    }
    resp = httpx.post(f"{NOTION_API}/databases", headers=_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()["id"]


def setup_notion_database(db_name: str = "To-Do List") -> str:
    """Create (or find) the Notion to-do database and return its database_id.

    Run once after setting NOTION_API_KEY, then paste the returned ID into .env
    as NOTION_DATABASE_ID.
    """
    if not settings.NOTION_API_KEY:
        raise RuntimeError("NOTION_API_KEY is not set")
    existing = _find_database_id(db_name)
    if existing:
        logger.info("Found existing database '%s': %s", db_name, existing)
        return existing
    parent = _create_parent_page("Voice Assistant Todo")
    db_id = _create_database(parent, db_name)
    logger.info("Created database '%s': %s", db_name, db_id)
    return db_id
