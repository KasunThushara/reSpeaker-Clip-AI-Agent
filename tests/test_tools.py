from backend.tools.calculator import calculator
from backend.tools.search import web_search
from backend.tools.notion import (
    get_notion_tools,
    add_todo,
    list_todos,
    complete_todo,
    delete_todo,
)
from backend.tools.conversation_search import search_conversations
from backend.tools.finance import (
    finance_search_symbol,
    finance_get_quote,
    finance_get_profile,
    finance_get_income_statement,
    finance_get_news,
    _fmt,
    _compact_quote,
)
from backend.tools.shopify import (
    shopify_search_catalog,
    shopify_lookup_catalog,
    shopify_create_cart,
    shopify_get_cart,
    shopify_update_cart,
    shopify_cancel_cart,
    shopify_get_order,
    _shop_domain_endpoint,
)
from backend.tools.gmail import (
    gmail_search_messages,
    gmail_get_message,
    gmail_create_draft,
    gmail_send_message,
    gmail_list_labels,
    _compact_message,
    _decode_data,
    _build_raw,
    _reset_service,
)
from config import settings


class TestCalculator:
    def test_addition(self):
        assert calculator.invoke({"expression": "2 + 3"}) == "5"

    def test_multiplication(self):
        assert calculator.invoke({"expression": "2300 * 4"}) == "9200"

    def test_precedence(self):
        assert calculator.invoke({"expression": "2 + 3 * 4"}) == "14"

    def test_power(self):
        assert calculator.invoke({"expression": "2 ** 10"}) == "1024"

    def test_invalid_expression(self):
        result = calculator.invoke({"expression": "import os"})
        assert result.startswith("Error:")

    def test_division_by_zero(self):
        result = calculator.invoke({"expression": "1 / 0"})
        assert result.startswith("Error:")


class TestWebSearch:
    def test_tool_is_defined(self):
        assert web_search.name == "web_search"
        assert "Search the web" in web_search.description


class TestNotion:
    def test_notion_tools_return_empty_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(settings, "NOTION_API_KEY", "")
        monkeypatch.setattr(settings, "NOTION_DATABASE_ID", "")
        assert get_notion_tools() == []

    def test_notion_tool_names(self, monkeypatch):
        monkeypatch.setattr(settings, "NOTION_API_KEY", "ntn_test")
        monkeypatch.setattr(settings, "NOTION_DATABASE_ID", "test-db-id")
        tools = get_notion_tools()
        assert [t.name for t in tools] == [
            "add_todo",
            "list_todos",
            "complete_todo",
            "delete_todo",
        ]

    def test_tool_descriptions_mention_todo(self):
        assert "to-do list" in add_todo.description
        assert "to-do list" in list_todos.description
        assert "to-do list" in complete_todo.description
        assert "to-do list" in delete_todo.description


class TestConversationSearch:
    def test_returns_not_configured_without_key(self, monkeypatch):
        monkeypatch.setattr(settings, "PINECONE_API_KEY", "")
        result = search_conversations.invoke({"query": "usb"})
        assert "not configured" in result

    def test_tool_is_in_registry(self):
        from backend.tools import get_available_tools

        names = [t.name for t in get_available_tools()]
        assert "search_conversations" in names


class TestFinance:
    def test_tools_are_defined(self):
        assert finance_search_symbol.name == "finance_search_symbol"
        assert finance_get_quote.name == "finance_get_quote"
        assert finance_get_profile.name == "finance_get_profile"
        assert finance_get_income_statement.name == "finance_get_income_statement"
        assert finance_get_news.name == "finance_get_news"

    def test_unconfigured_returns_message(self, monkeypatch):
        monkeypatch.setattr(settings, "FMP_API_KEY", "")
        for tool_fn in (
            finance_search_symbol,
            finance_get_quote,
            finance_get_profile,
            finance_get_income_statement,
            finance_get_news,
        ):
            result = tool_fn.invoke({"symbol": "AAPL"} if "query" not in tool_fn.args else {"query": "Apple"})
            assert "not configured" in result

    def test_income_statement_validates_period(self, monkeypatch):
        monkeypatch.setattr(settings, "FMP_API_KEY", "test-key")
        result = finance_get_income_statement.invoke(
            {"symbol": "AAPL", "period": "monthly"}
        )
        assert "annual" in result

    def test_fmt_compact_numbers(self):
        assert _fmt(3_450_000_000_000) == "3.45T"
        assert _fmt(12_500_000_000) == "12.50B"
        assert _fmt(2_000_000) == "2.00M"
        assert _fmt(3.5) == "3.5"
        assert _fmt(42) == "42"

    def test_compact_quote_keeps_key_fields(self):
        q = _compact_quote(
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "price": 227.5,
                "change": 1.2,
                "changesPercentage": 0.53,
                "dayLow": 225.0,
                "dayHigh": 228.0,
                "previousClose": 226.3,
                "volume": 50_000_000,
                "marketCap": 3_450_000_000_000,
                "currency": "USD",
                "exchange": "NASDAQ",
                "unwantedField": "dropped",
            }
        )
        assert q["symbol"] == "AAPL"
        assert q["change_percent"] == 0.53
        assert q["volume"] == "50.00M"
        assert q["market_cap"] == "3.45T"
        assert "unwantedField" not in q

    def test_finance_tools_are_registered(self):
        from backend.tools import get_available_tools

        names = [tool.name for tool in get_available_tools()]
        for expected in (
            "finance_search_symbol",
            "finance_get_quote",
            "finance_get_profile",
            "finance_get_income_statement",
            "finance_get_news",
        ):
            assert expected in names


class TestShopify:
    def test_tools_are_defined(self):
        assert shopify_search_catalog.name == "shopify_search_catalog"
        assert shopify_lookup_catalog.name == "shopify_lookup_catalog"

    def test_lookup_requires_ids(self):
        assert "requires" in shopify_lookup_catalog.invoke({"ids": []})

    def test_shopify_tools_are_registered_when_configured(self, monkeypatch):
        from backend.tools import get_available_tools

        names = [tool.name for tool in get_available_tools()]
        assert "shopify_search_catalog" in names


class TestShopifyCartAndOrder:
    def test_shop_domain_endpoint(self):
        assert (
            _shop_domain_endpoint("shop.example.com")
            == "https://shop.example.com/api/ucp/mcp"
        )
        assert (
            _shop_domain_endpoint("https://shop.example.com/")
            == "https://shop.example.com/api/ucp/mcp"
        )

    def test_shop_domain_endpoint_accepts_full_product_url(self):
        assert (
            _shop_domain_endpoint(
                "https://www.skullcandy.com/products/crusher-anc-2?variant=123"
            )
            == "https://www.skullcandy.com/api/ucp/mcp"
        )

    def test_compact_variant_surfaces_shop_domain(self):
        from backend.tools.shopify import _compact_variant

        variant = {
            "id": "gid://shopify/ProductVariant/1",
            "title": "Test",
            "url": "https://www.skullcandy.com/products/crusher-anc-2",
        }
        result = _compact_variant(variant)
        assert result["shop_domain"] == "www.skullcandy.com"

    def test_shop_domain_endpoint_requires_domain(self):
        import pytest

        with pytest.raises(ValueError):
            _shop_domain_endpoint("   ")

    def test_cart_tools_are_defined(self):
        assert shopify_create_cart.name == "shopify_create_cart"
        assert shopify_get_cart.name == "shopify_get_cart"
        assert shopify_update_cart.name == "shopify_update_cart"
        assert shopify_cancel_cart.name == "shopify_cancel_cart"
        assert shopify_get_order.name == "shopify_get_order"

    def test_cart_tools_require_shop_domain(self):
        result = shopify_create_cart.invoke(
            {"shop_domain": "", "line_items": []}
        )
        assert "required" in result

    def test_get_order_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "SHOPIFY_CLIENT_ID", "")
        monkeypatch.setattr(settings, "SHOPIFY_CLIENT_SECRET", "")
        import backend.tools.shopify as shopify_module

        shopify_module._order_token_cache["token"] = ""
        shopify_module._order_token_cache["expires_at"] = 0.0
        result = shopify_get_order.invoke(
            {"shop_domain": "shop.example.com", "order_id": "gid://shopify/Order/1"}
        )
        assert "not configured" in result

    def test_cart_and_order_tools_are_registered(self):
        from backend.tools import get_available_tools

        names = [tool.name for tool in get_available_tools()]
        for expected in (
            "shopify_create_cart",
            "shopify_get_cart",
            "shopify_update_cart",
            "shopify_cancel_cart",
            "shopify_get_order",
        ):
            assert expected in names


class TestGmail:
    def test_tools_are_defined(self):
        assert gmail_search_messages.name == "gmail_search_messages"
        assert gmail_get_message.name == "gmail_get_message"
        assert gmail_create_draft.name == "gmail_create_draft"
        assert gmail_send_message.name == "gmail_send_message"
        assert gmail_list_labels.name == "gmail_list_labels"

    def test_unauthorized_returns_message(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "GMAIL_TOKEN_FILE", str(tmp_path / "missing.json"))
        _reset_service()
        for tool_fn, args in (
            (gmail_search_messages, {"query": "test"}),
            (gmail_get_message, {"message_id": "abc123"}),
            (gmail_create_draft, {"to": "a@b.com", "subject": "s", "body": "b"}),
            (gmail_send_message, {"to": "a@b.com", "subject": "s", "body": "b"}),
            (gmail_list_labels, {}),
        ):
            result = tool_fn.invoke(args)
            assert "unavailable" in result

    def test_get_message_requires_id(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "GMAIL_TOKEN_FILE", str(tmp_path / "missing.json"))
        _reset_service()
        assert "required" in gmail_get_message.invoke({"message_id": "  "})

    def test_draft_requires_fields(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "GMAIL_TOKEN_FILE", str(tmp_path / "missing.json"))
        _reset_service()
        result = gmail_create_draft.invoke({"to": "", "subject": "s", "body": "b"})
        assert "required" in result

    def test_decode_data_handles_missing_padding(self):
        # "Hello" encoded as base64url without padding
        assert _decode_data("SGVsbG8") == "Hello"

    def test_compact_message_keeps_key_fields(self):
        msg = {
            "id": "msg1",
            "threadId": "t1",
            "snippet": "short snippet",
            "payload": {
                "headers": [
                    {"name": "From", "value": "alice@example.com"},
                    {"name": "Subject", "value": "Hello"},
                    {"name": "Date", "value": "Mon, 1 Jan 2026 10:00:00 +0000"},
                ],
                "mimeType": "text/plain",
                "body": {"data": "SGVsbG8"},
            },
        }
        compact = _compact_message(msg, body_chars=100)
        assert compact["from"] == "alice@example.com"
        assert compact["subject"] == "Hello"
        assert compact["body"] == "Hello"
        assert "snippet" in compact

    def test_build_raw_encodes_message(self):
        import base64

        raw = _build_raw("bob@example.com", "Hi", "Body text")
        decoded = base64.urlsafe_b64decode(raw).decode()
        assert "bob@example.com" in decoded
        assert "Hi" in decoded
        assert "Body text" in decoded

    def test_gmail_tools_are_registered(self):
        from backend.tools import get_available_tools

        names = [tool.name for tool in get_available_tools()]
        for expected in (
            "gmail_search_messages",
            "gmail_get_message",
            "gmail_create_draft",
            "gmail_send_message",
            "gmail_list_labels",
        ):
            assert expected in names
