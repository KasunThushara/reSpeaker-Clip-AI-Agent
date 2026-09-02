"""Tool registry — hybrid architecture.

Three tool sources feed the agent:

1. **Local tools** (always available; graceful degradation without keys):
   - ``web_search`` (Tavily), ``calculator``
   - ``search_conversations`` (Pinecone + DB join)
   - 5 FMP finance tools and 8 Shopify Global Catalog/UCP buyer-flow tools
2. **Composio wrappers** (``composio_search`` / ``composio_execute`` /
   ``composio_connect``) — the generic external-app gateway for Gmail,
   Google Calendar, Slack, Linear, GitHub, Trello, Asana, Notion and any
   other Composio-supported app. Added only when ``COMPOSIO_API_KEY`` is set.

Lifecycle capabilities (Mem0 recall/save, conversation history,
Supabase/SQLite persistence, async summarization/embedding/Pinecone
indexing) are NOT tools and remain outside this registry.
"""

from backend.tools.search import web_search
from backend.tools.calculator import calculator
from backend.tools.conversation_search import search_conversations
from backend.tools.finance import (
    finance_search_symbol,
    finance_get_quote,
    finance_get_profile,
    finance_get_income_statement,
    finance_get_news,
)
from backend.tools.shopify import (
    shopify_search_catalog,
    shopify_lookup_catalog,
    shopify_get_product,
    shopify_create_cart,
    shopify_get_cart,
    shopify_update_cart,
    shopify_cancel_cart,
    shopify_get_order,
)
from backend.tools.composio import get_composio_tools

# Deterministic order: local tools first, then the Composio gateway wrappers.
# External SaaS integrations (Gmail, Calendar, Slack, Linear, ...) are owned
# by the Composio gateway, not registered here as direct tools.
LOCAL_TOOLS = [
    web_search,
    calculator,
    search_conversations,
    finance_search_symbol,
    finance_get_quote,
    finance_get_profile,
    finance_get_income_statement,
    finance_get_news,
    shopify_search_catalog,
    shopify_lookup_catalog,
    shopify_get_product,
    shopify_create_cart,
    shopify_get_cart,
    shopify_update_cart,
    shopify_cancel_cart,
    shopify_get_order,
]


def get_available_tools() -> list:
    """Return the tools the agent can use, based on what is configured.

    Local tools are always returned (each degrades gracefully when its
    backing service is not configured). Composio wrappers are appended only
    when ``COMPOSIO_API_KEY`` is present, so the app keeps working without
    Composio. Ordering is stable and duplicates are impossible.
    """
    tools = list(LOCAL_TOOLS)
    tools.extend(get_composio_tools())
    return tools
