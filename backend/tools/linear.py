"""Linear issue-tracker tools.

Talks to Linear's GraphQL API (https://api.linear.app/graphql) with a
personal API key (Settings -> Security & access). The key is sent in the
Authorization header WITHOUT a Bearer prefix, which is Linear's convention
for personal keys. httpx honors HTTPS_PROXY automatically, so no proxy
workaround is needed (unlike the Google tools).
"""

import httpx
from langchain_core.tools import tool

from config import settings

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_TIMEOUT = httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0)

MAX_ISSUES = 10
MAX_TEAMS = 20
MAX_DESCRIPTION_CHARS = 300

LINEAR_UNAVAILABLE = (
    "Linear tools are not configured: set LINEAR_API_KEY in .env "
    "(a personal API key from Linear Settings -> Security & access)."
)

# Issue priority labels (Linear convention: 0 none, 1 urgent, 2 high,
# 3 medium, 4 low).
PRIORITY_LABELS = {0: "none", 1: "urgent", 2: "high", 3: "medium", 4: "low"}


def _linear_query(query: str, variables: dict | None = None) -> dict | str:
    """Run one GraphQL request against Linear.

    Returns the parsed "data" object, or an error string. GraphQL APIs can
    return HTTP 200 with an errors array, so errors are checked separately
    from transport failures.
    """
    try:
        response = httpx.post(
            LINEAR_API_URL,
            json={"query": query, "variables": variables or {}},
            headers={
                "Authorization": settings.LINEAR_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=LINEAR_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException:
        return "Linear request timed out. Please try again."
    except (httpx.HTTPError, ValueError) as exc:
        return f"Linear request failed: {exc}"

    errors = payload.get("errors")
    if errors:
        messages = "; ".join(e.get("message", "unknown error") for e in errors)
        return f"Linear error: {messages}"
    return payload.get("data") or {}


def _compact_text(value: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _fmt_issue(issue: dict, include_description: bool = False) -> str:
    """Format one issue compactly: id: "title" [state] @assignee."""
    identifier = issue.get("identifier") or issue.get("id") or "?"
    title = issue.get("title") or "(no title)"
    state = (issue.get("state") or {}).get("name") or ""
    assignee = (issue.get("assignee") or {}).get("name") or ""
    line = f'{identifier}: "{title}"'
    if state:
        line += f" [{state}]"
    if assignee:
        line += f" @{assignee}"
    if include_description:
        description = _compact_text(issue.get("description") or "")
        if description:
            line += f" — {description}"
    return line


def _fmt_team(team: dict) -> str:
    """Format one team: - name (id: ..., key: KEY)."""
    return f"- {team.get('name', '')} (id: {team.get('id', '')}, key: {team.get('key', '')})"


def _clamp_priority(priority: int) -> int:
    return max(0, min(int(priority), 4))


@tool
def linear_list_teams() -> str:
    """List the Linear teams in the workspace. Use this first when the user
    wants to create an issue — creating requires a team id from this list."""
    if not settings.LINEAR_API_KEY:
        return LINEAR_UNAVAILABLE
    data = _linear_query(
        """
        query Teams {
          teams(first: %d) {
            nodes { id name key }
          }
        }
        """
        % MAX_TEAMS
    )
    if isinstance(data, str):
        return data
    teams = (data.get("teams") or {}).get("nodes") or []
    if not teams:
        return "No teams found in the Linear workspace."
    return "Linear teams:\n" + "\n".join(_fmt_team(t) for t in teams)


@tool
def linear_list_my_issues(state: str = "open", limit: int = 10) -> str:
    """List the Linear issues assigned to the current user.
    state filters the result: "open" (default, not done/canceled), "done",
    or "all". limit caps how many issues to return (max 10). Use this when
    the user asks about their own tasks or what they have left to do."""
    if not settings.LINEAR_API_KEY:
        return LINEAR_UNAVAILABLE
    limit = max(1, min(int(limit), MAX_ISSUES))
    state = (state or "open").strip().lower()

    state_filter = ""
    if state == "open":
        state_filter = 'state: { type: { nin: ["completed", "canceled"] } },'
    elif state == "done":
        state_filter = 'state: { type: { eq: "completed" } },'

    data = _linear_query(
        """
        query MyIssues {
          issues(
            first: %d
            filter: {
              assignee: { isMe: { eq: true } },
              %s
            }
            orderBy: updatedAt
          ) {
            nodes {
              id identifier title updatedAt
              state { name }
              assignee { name }
            }
          }
        }
        """
        % (limit, state_filter)
    )
    if isinstance(data, str):
        return data
    issues = (data.get("issues") or {}).get("nodes") or []
    if not issues:
        return f"No {state} issues assigned to you."
    lines = [_fmt_issue(i) for i in issues]
    return f"Your {state} issues ({len(lines)}):\n" + "\n".join(lines)


@tool
def linear_search_issues(query: str, limit: int = 10) -> str:
    """Search Linear issues by keyword in the title or description.
    Use this when the user asks to find issues about a topic. limit caps
    how many issues to return (max 10)."""
    if not settings.LINEAR_API_KEY:
        return LINEAR_UNAVAILABLE
    query = (query or "").strip()
    if not query:
        return "query is required."
    limit = max(1, min(int(limit), MAX_ISSUES))

    data = _linear_query(
        """
        query Search($q: String!, $first: Int!) {
          issues(
            first: $first
            filter: { or: [
              { title: { contains: $q } },
              { description: { contains: $q } }
            ] }
          ) {
            nodes {
              id identifier title
              state { name }
              assignee { name }
            }
          }
        }
        """,
        {"q": query, "first": limit},
    )
    if isinstance(data, str):
        return data
    issues = (data.get("issues") or {}).get("nodes") or []
    if not issues:
        return f"No issues found matching \"{query}\"."
    lines = [_fmt_issue(i) for i in issues]
    return f"Found {len(lines)} issue(s) matching \"{query}\":\n" + "\n".join(lines)


@tool
def linear_get_issue(issue_id: str) -> str:
    """Get one Linear issue's details by id or identifier (e.g. 'ENG-42'
    or its UUID). Returns title, state, assignee, priority, dates, and a
    truncated description."""
    if not settings.LINEAR_API_KEY:
        return LINEAR_UNAVAILABLE
    issue_id = (issue_id or "").strip()
    if not issue_id:
        return "issue_id is required."

    data = _linear_query(
        """
        query Issue($id: String!) {
          issue(id: $id) {
            id identifier title description
            priority createdAt updatedAt dueDate
            state { name }
            assignee { name }
          }
        }
        """,
        {"id": issue_id},
    )
    if isinstance(data, str):
        return data
    issue = data.get("issue")
    if not issue:
        return f"Issue {issue_id} not found."
    priority = issue.get("priority") or 0
    line = _fmt_issue(issue, include_description=True)
    return (
        f"{line}\n"
        f"priority: {PRIORITY_LABELS.get(priority, priority)} | "
        f"created: {issue.get('createdAt', '?')} | "
        f"updated: {issue.get('updatedAt', '?')} | "
        f"due: {issue.get('dueDate') or 'none'}"
    )


@tool
def linear_create_issue(
    title: str,
    team_id: str,
    description: str = "",
    priority: int = 0,
) -> str:
    """Create a new Linear issue. title and team_id are required; get
    team_id from linear_list_teams. description is optional markdown.
    priority is 0 none (default), 1 urgent, 2 high, 3 medium, 4 low.
    Returns the created issue's identifier."""
    if not settings.LINEAR_API_KEY:
        return LINEAR_UNAVAILABLE
    if not (title or "").strip():
        return "title is required."
    if not (team_id or "").strip():
        return "team_id is required (use linear_list_teams to find it)."

    issue_input: dict = {
        "title": title.strip(),
        "teamId": team_id.strip(),
    }
    if (description or "").strip():
        issue_input["description"] = description.strip()
    priority = _clamp_priority(priority)
    if priority:
        issue_input["priority"] = priority

    data = _linear_query(
        """
        mutation Create($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { id identifier title }
          }
        }
        """,
        {"input": issue_input},
    )
    if isinstance(data, str):
        return data
    result = data.get("issueCreate") or {}
    if not result.get("success"):
        return "Creating issue failed."
    issue = result.get("issue") or {}
    return f"Issue created: {_fmt_issue(issue)}"


@tool
def linear_update_issue(
    issue_id: str,
    title: str = "",
    state: str = "",
    priority: int = -1,
) -> str:
    """Update an existing Linear issue by id or identifier (e.g. 'ENG-42').
    Only the fields you provide are changed: title, state (a workflow
    state name like 'Done' or 'In Progress'), and/or priority (0 none,
    1 urgent, 2 high, 3 medium, 4 low). Use state 'Done' to mark an issue
    complete. Returns the updated issue."""
    if not settings.LINEAR_API_KEY:
        return LINEAR_UNAVAILABLE
    issue_id = (issue_id or "").strip()
    if not issue_id:
        return "issue_id is required."
    if not any(((title or "").strip(), (state or "").strip(), priority >= 0)):
        return "At least one of title, state, or priority is required."

    issue_input: dict = {}
    if (title or "").strip():
        issue_input["title"] = title.strip()
    if priority >= 0:
        issue_input["priority"] = _clamp_priority(priority)

    # Resolve a state name (e.g. "Done") to its workflow-state id.
    if (state or "").strip():
        state_name = state.strip()
        current = _linear_query(
            """
            query IssueTeam($id: String!) {
              issue(id: $id) {
                team { id }
              }
            }
            """,
            {"id": issue_id},
        )
        if isinstance(current, str):
            return current
        team = (current.get("issue") or {}).get("team") or {}
        team_id = team.get("id")
        if not team_id:
            return f"Issue {issue_id} not found."
        states = _linear_query(
            """
            query States($teamId: ID!) {
              workflowStates(
                first: 50
                filter: { team: { id: { eq: $teamId } } }
              ) {
                nodes { id name }
              }
            }
            """,
            {"teamId": team_id},
        )
        if isinstance(states, str):
            return states
        nodes = (states.get("workflowStates") or {}).get("nodes") or []
        match = next(
            (s for s in nodes if s.get("name", "").lower() == state_name.lower()),
            None,
        )
        if not match:
            available = ", ".join(s.get("name", "") for s in nodes) or "none"
            return (
                f"State \"{state_name}\" not found for this team. "
                f"Available states: {available}"
            )
        issue_input["stateId"] = match["id"]

    data = _linear_query(
        """
        mutation Update($id: String!, $input: IssueUpdateInput!) {
          issueUpdate(id: $id, input: $input) {
            success
            issue {
              id identifier title
              state { name }
              assignee { name }
            }
          }
        }
        """,
        {"id": issue_id, "input": issue_input},
    )
    if isinstance(data, str):
        return data
    result = data.get("issueUpdate") or {}
    if not result.get("success"):
        return "Updating issue failed."
    issue = result.get("issue") or {}
    return f"Issue updated: {_fmt_issue(issue)}"
