"""Composio tool source — lightweight self-written tools (方案 A).

Instead of loading Composio's verbose session meta tools
(COMPOSIO_SEARCH_TOOLS / COMPOSIO_MULTI_EXECUTE_TOOL / ... whose JSON schemas
total ~3700 tokens and blew past Groq's 8000 TPM limit), we expose three tiny
LangChain ``@tool`` wrappers that call the session's low-level APIs directly:

- ``composio_search(query)``   -> ``session.search()``     (runtime discovery)
- ``composio_execute(slug, args)`` -> ``session.execute()`` (run a tool)
- ``composio_connect(toolkit)``    -> ``session.authorize()`` (get a Connect Link)

This keeps the full runtime "discover -> connect -> execute" capability while
cutting the tool-schema footprint from ~3700 tokens to ~150 tokens.

Auth is Composio-managed: when a tool needs an account, ``composio_connect``
returns a Connect Link (a *.composio.dev URL). The frontend detects that link
and renders it for the user to open (see ``maybeOfferComposioConnect`` in
frontend/static/js/app.js).

Degradation: when COMPOSIO_API_KEY is not configured, ``get_composio_tools()``
returns an empty list (like every other tool module's "not configured"
behavior), so the app keeps running without Composio.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from langchain_core.tools import tool

from config import settings

logger = logging.getLogger(__name__)

_client = None      # composio.Composio instance (lazy)
_session = None     # composio ToolRouterSession (lazy)
_ready = False      # session init attempted (success or failure)

# slug -> input schema dict cache, so repeated searches never re-fetch the
# same tool schema from the Composio backend.
_schema_cache = {}

MAX_TOOLS = 10       # cap the number of search matches shown to the model
MAX_DESC = 120       # truncate each tool description
MAX_RESULT = 2000    # final hard cap on execute output
MAX_STR = 200        # truncate individual strings inside a result


def _compact(obj, depth: int = 0):
    """Compress a nested tool result for the model: drop `*_url` noise, shrink
    long strings, cap deeply nested structures, and keep all scalar fields
    (counts like ``stargazers_count`` are the answer to most lookups)."""
    if depth > 4:
        return None
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            # *_url fields are verbatim API endpoints — pure noise for the LLM.
            if isinstance(k, str) and k.endswith("_url") and isinstance(v, str):
                continue
            c = _compact(v, depth + 1)
            if c is None and v is not None and not isinstance(v, (bool,)):
                continue
            out[k] = c
        return out
    if isinstance(obj, list):
        if len(obj) > 5:
            return [_compact(x, depth + 1) for x in obj[:5]] + [
                f"...({len(obj) - 5} more items)"
            ]
        return [_compact(x, depth + 1) for x in obj]
    if isinstance(obj, str):
        return obj if len(obj) <= MAX_STR else obj[:MAX_STR] + "..."
    return obj


def _get_session():
    """Lazily create (once) and return the Composio session, or None.

    The session ties a stable user_id to Composio-managed connections. It is
    created on first *use* (not at import / agent-build time) so that a missing
    key or unreachable backend never blocks agent construction.
    """
    global _client, _session, _ready

    if _ready:
        return _session

    if not settings.COMPOSIO_API_KEY:
        _session = None
        _ready = True
        return None

    try:
        from composio import Composio
        from composio_langgraph import LanggraphProvider

        _client = Composio(
            provider=LanggraphProvider(),
            api_key=settings.COMPOSIO_API_KEY,
        )
        # toolkits whitelist keeps the search space small; the sandbox is
        # disabled so workbench/bash capabilities are not exposed.
        _session = _client.create(
            user_id=settings.USER_ID,
            toolkits=settings.COMPOSIO_TOOLKITS,
            sandbox={"enable": False},
        )
        logger.info(
            "Composio session %s ready (toolkits=%s)",
            _session.session_id,
            settings.COMPOSIO_TOOLKITS,
        )
    except Exception as e:  # bad key, backend unreachable, ...
        logger.warning("Composio unavailable: %s", e)
        _session = None
    _ready = True
    return _session


def _f(obj, name, default=None):
    """Read a field tolerantly from a Pydantic model or a dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _required_params(input_schema) -> list:
    """Extract the required parameter names from a JSON schema dict."""
    if not isinstance(input_schema, dict):
        return []
    required = input_schema.get("required")
    if not isinstance(required, list):
        return []
    return [str(r) for r in required]


def _get_full_schema(slug: str):
    """Fetch a tool's full input schema by slug (for tools whose search result
    only carries a schema_ref, i.e. ``has_full_schema=False``).  Results are
    cached in ``_schema_cache`` so repeated searches are cheap."""
    global _client
    if slug in _schema_cache:
        return _schema_cache[slug]
    if _client is None:
        return None
    try:
        tool = _client.tools.get_raw_composio_tool_by_slug(slug)
        schema = getattr(tool, "input_parameters", None)
    except Exception:
        schema = None
    _schema_cache[slug] = schema
    return schema


def _backfill_schemas(schemas: dict, sl_gen) -> None:
    """Parallel backfill of missing input_schema for REF tools in a search."""
    missing = [
        slug for slug in sl_gen
        if slug in schemas
        and not _f(schemas[slug], "input_schema", None)
        and _f(schemas[slug], "has_full_schema", None) is False
        and slug not in _schema_cache
    ]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_get_full_schema, missing))


def _guess_toolkit(tool_slug: str) -> str:
    """Infer the toolkit slug from a tool slug (e.g. TRELLO_* -> 'trello').

    Most Composio tool slugs are prefixed with the toolkit name. Fall back to
    whatever COMPOSIO_TOOLKITS holds when inference is ambiguous."""
    if tool_slug and "_" in tool_slug:
        prefix = tool_slug.split("_")[0].lower()
        if prefix:
            return prefix
    return (settings.COMPOSIO_TOOLKITS[0] if settings.COMPOSIO_TOOLKITS else "unknown")


@tool
def composio_search(query: str) -> str:
    """Search Composio for the app tools that match a natural-language request.
    Returns matching tool slugs, short descriptions, and required arguments.
    Call this FIRST when a task needs an app (GitHub, etc.) not covered by the
    built-in tools, then call composio_execute with the returned slug."""
    session = _get_session()
    if session is None:
        return "Composio is unavailable: not configured."

    try:
        resp = session.search(query=query)
    except Exception as e:
        return f"Composio search failed: {e}"

    schemas = _f(resp, "tool_schemas", None) or {}

    # Pre-fetch any missing schemas in parallel (REF tools, ~0.4s each serially)
    # before building the output, instead of one blocking call per tool.
    _backfill_schemas(schemas, schemas.keys())

    seen = []
    lines = []

    def add(slug, toolk="", desc=""):
        if slug in seen or len(lines) >= MAX_TOOLS:
            return
        seen.append(slug)
        d = (desc or "")[:MAX_DESC]
        params = []
        ts = schemas.get(slug)
        if ts is not None:
            schema = _f(ts, "input_schema", None)
            if not schema and _f(ts, "has_full_schema", None) is False:
                schema = _schema_cache.get(slug) or _get_full_schema(slug)
            params = _required_params(schema)
        suffix = f" | 需要参数: {', '.join(params)}" if params else ""
        lines.append(f"{slug}{(' (' + toolk + ')') if toolk else ''}: {d}{suffix}")

    # Prefer the deduplicated tool_schemas map (slug -> description + schema).
    for slug, ts in schemas.items():
        add(slug, _f(ts, "toolkit", ""), _f(ts, "description", ""))

    # Fallback: slugs referenced in results when tool_schemas is empty.
    if not lines:
        for r in _f(resp, "results", []) or []:
            for s in (_f(r, "primary_tool_slugs", []) or []) + (_f(r, "related_tool_slugs", []) or []):
                add(s)

    return "\n".join(lines) if lines else "No matching Composio tools found."


@tool
def composio_execute(tool_slug: str, arguments: str) -> str:
    """Execute a Composio tool whose slug was returned by composio_search.
    Pass 'arguments' as a JSON object string matching the tool's required args."""
    session = _get_session()
    if session is None:
        return "Composio is unavailable: not configured."

    try:
        args = json.loads(arguments) if arguments and arguments.strip() else {}
    except ValueError:
        return f"arguments must be valid JSON; got: {arguments}"
    if not isinstance(args, dict):
        return "arguments must be a JSON object."

    try:
        resp = session.execute(tool_slug, arguments=args)
    except Exception as e:
        # 最关键:未连接时 execute 抛 BadRequestError(400),而不是返回 error 字段。
        # 必须识别出来并引导模型走 composio_connect,否则模型会反复换工具重试,
        # 跑满 recursion limit(表现就是你看到的"卡 2 分钟")。
        msg = str(e)
        low = msg.lower()
        if "no active connection" in low or "noactiveconnection" in low or "no_active_connection" in low:
            # 尽力从异常/参数里推断 toolkit slug 回给模型
            hint = ""
            if isinstance(args, dict):
                hint = ""
            return (
                f"该工具尚未连接对应账号。请先调用 composio_connect(toolkit='{_guess_toolkit(tool_slug)}') "
                f"获取连接链接让用户授权,授权完成后再重新调用 composio_execute。原始错误: {msg[:200]}"
            )
        return f"Composio execute failed: {msg[:300]}"

    error = _f(resp, "error", None)
    if error:
        return f"执行失败: {error}"

    data = _f(resp, "data", None)
    text = json.dumps(_compact(data), ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT:
        text = text[:MAX_RESULT] + f"... (截断, 共 {len(text)} 字符)"
    return text


@tool
def composio_connect(toolkit: str) -> str:
    """When a Composio tool needs an account connection, call this to get an
    authorization link for the user. Pass the toolkit slug (e.g. 'github')."""
    session = _get_session()
    if session is None:
        return "Composio is unavailable: not configured."

    try:
        req = session.authorize(toolkit)
    except Exception as e:
        return f"Composio connect failed: {e}"

    url = _f(req, "redirect_url", None)
    if not url:
        return f"Could not create a connection link for {toolkit}."
    return f"请打开此链接连接 {toolkit}: {url}"


def get_composio_tools() -> list:
    """Return the lightweight Composio tools (方案 A: no verbose meta tools).

    Returns [] when COMPOSIO_API_KEY is missing, so the registry can always
    call this unconditionally. The session itself is created lazily on first
    tool use, not here.
    """
    if not settings.COMPOSIO_API_KEY:
        return []
    return [composio_search, composio_execute, composio_connect]


def composio_enabled() -> bool:
    """True when the Composio tool source is active."""
    return bool(settings.COMPOSIO_API_KEY and _get_session() is not None)