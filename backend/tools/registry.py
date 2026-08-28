from backend.tools.search import web_search
from backend.tools.calculator import calculator
from backend.tools.notion import get_notion_tools
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
from backend.tools.gmail import (
    gmail_search_messages,
    gmail_get_message,
    gmail_create_draft,
    gmail_send_message,
    gmail_list_labels,
)
from backend.tools.slack import (
    slack_list_channels,
    slack_read_channel,
    slack_read_thread,
    slack_search_messages,
    slack_send_message,
    slack_schedule_message,
    slack_add_reminder,
    slack_list_users,
    slack_set_dnd,
)


def get_available_tools() -> list:
    """Return the tools the agent can use, based on what is configured."""
    tools = [web_search, calculator, search_conversations] + get_notion_tools()
    tools.extend([
        finance_search_symbol,
        finance_get_quote,
        finance_get_profile,
        finance_get_income_statement,
        finance_get_news,
    ])
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
    tools.extend([
        gmail_search_messages,
        gmail_get_message,
        gmail_create_draft,
        gmail_send_message,
        gmail_list_labels,
    ])
    tools.extend([
        slack_list_channels,
        slack_read_channel,
        slack_read_thread,
        slack_search_messages,
        slack_send_message,
        slack_schedule_message,
        slack_add_reminder,
        slack_list_users,
        slack_set_dnd,
    ])
    return tools
