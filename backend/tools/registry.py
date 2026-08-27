from backend.tools.search import web_search
from backend.tools.calculator import calculator
from backend.tools.notion import get_notion_tools
from backend.tools.conversation_search import search_conversations
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


def get_available_tools() -> list:
    """Return the tools the agent can use, based on what is configured."""
    tools = [web_search, calculator, search_conversations] + get_notion_tools()
    tools.extend([
        shopify_search_catalog,
        shopify_lookup_catalog,
        shopify_get_product,
        shopify_create_cart,
        shopify_get_cart,
        shopify_update_cart,
        shopify_cancel_cart,
        shopify_get_order,
    ])
    return tools
