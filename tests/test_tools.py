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
