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
from backend.tools.calendar import (
    calendar_list_events,
    calendar_quick_add,
    calendar_create_event,
    calendar_update_event,
    calendar_delete_event,
    calendar_find_free_time,
    _fmt_event,
    _parse_days,
    _reset_service as _reset_calendar_service,
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
    _format_message,
    _user_map,
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


class TestCalendar:
    def test_tools_are_defined(self):
        assert calendar_list_events.name == "calendar_list_events"
        assert calendar_quick_add.name == "calendar_quick_add"
        assert calendar_create_event.name == "calendar_create_event"
        assert calendar_update_event.name == "calendar_update_event"
        assert calendar_delete_event.name == "calendar_delete_event"
        assert calendar_find_free_time.name == "calendar_find_free_time"

    def test_unauthorized_returns_message(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "GMAIL_TOKEN_FILE", str(tmp_path / "missing.json"))
        _reset_calendar_service()
        for tool_fn, args in (
            (calendar_list_events, {"days": 7}),
            (calendar_quick_add, {"text": "dentist tomorrow 3pm"}),
            (calendar_create_event, {"title": "Meeting", "start": "2026-08-29T14:00:00+08:00"}),
            (calendar_update_event, {"event_id": "abc", "title": "New"}),
            (calendar_delete_event, {"event_id": "abc"}),
            (calendar_find_free_time, {"date": "2026-08-29"}),
        ):
            result = tool_fn.invoke(args)
            assert "unavailable" in result

    def test_quick_add_requires_text(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "GMAIL_TOKEN_FILE", str(tmp_path / "missing.json"))
        _reset_calendar_service()
        assert "required" in calendar_quick_add.invoke({"text": "  "})

    def test_create_event_requires_fields(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "GMAIL_TOKEN_FILE", str(tmp_path / "missing.json"))
        _reset_calendar_service()
        assert "required" in calendar_create_event.invoke({"title": "", "start": ""})

    def test_update_event_requires_field(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "GMAIL_TOKEN_FILE", str(tmp_path / "missing.json"))
        _reset_calendar_service()
        assert "required" in calendar_update_event.invoke({"event_id": "  "})
        assert "At least one" in calendar_update_event.invoke(
            {"event_id": "abc", "title": "", "start": "", "end": ""}
        )

    def test_delete_event_requires_id(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "GMAIL_TOKEN_FILE", str(tmp_path / "missing.json"))
        _reset_calendar_service()
        assert "required" in calendar_delete_event.invoke({"event_id": ""})

    def test_find_free_time_requires_date(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "GMAIL_TOKEN_FILE", str(tmp_path / "missing.json"))
        _reset_calendar_service()
        assert "required" in calendar_find_free_time.invoke({"date": ""})

    def test_fmt_event_formats_fields(self):
        event = {
            "id": "evt1",
            "summary": "Team standup",
            "start": {"dateTime": "2026-08-29T09:30:00+08:00"},
            "end": {"dateTime": "2026-08-29T09:45:00+08:00"},
            "location": "Room 4",
        }
        line = _fmt_event(event)
        assert "evt1" in line
        assert "Team standup" in line
        assert "09:30" in line
        assert "Room 4" in line

    def test_fmt_event_handles_all_day(self):
        event = {
            "id": "evt2",
            "summary": "Holiday",
            "start": {"date": "2026-10-01"},
            "end": {"date": "2026-10-02"},
        }
        line = _fmt_event(event)
        assert "2026-10-01" in line
        assert "Holiday" in line

    def test_parse_days_clamps_range(self):
        from datetime import datetime

        lo, hi = _parse_days(0)
        assert (hi - lo) >= datetime.now() - datetime.now()  # same-day minimum
        lo, hi = _parse_days(365)
        assert (hi - lo).days <= 31  # capped at 31 days

    def test_calendar_tools_are_registered(self):
        from backend.tools import get_available_tools

        names = [tool.name for tool in get_available_tools()]
        for expected in (
            "calendar_list_events",
            "calendar_quick_add",
            "calendar_create_event",
            "calendar_update_event",
            "calendar_delete_event",
            "calendar_find_free_time",
        ):
            assert expected in names


class TestSlack:
    def test_tools_are_defined(self):
        assert slack_list_channels.name == "slack_list_channels"
        assert slack_read_channel.name == "slack_read_channel"
        assert slack_read_thread.name == "slack_read_thread"
        assert slack_search_messages.name == "slack_search_messages"
        assert slack_send_message.name == "slack_send_message"
        assert slack_schedule_message.name == "slack_schedule_message"
        assert slack_add_reminder.name == "slack_add_reminder"
        assert slack_list_users.name == "slack_list_users"
        assert slack_set_dnd.name == "slack_set_dnd"

    def test_unconfigured_returns_message(self, monkeypatch):
        monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "")
        monkeypatch.setattr(settings, "SLACK_USER_TOKEN", "")
        for tool_fn, args in (
            (slack_list_channels, {}),
            (slack_read_channel, {"channel": "general"}),
            (slack_read_thread, {"channel": "general", "thread_ts": "123.456"}),
            (slack_search_messages, {"query": "deploy"}),
            (slack_send_message, {"channel": "general", "text": "hi"}),
            (slack_schedule_message, {"channel": "general", "text": "hi", "post_at": "1700000000"}),
            (slack_add_reminder, {"text": "check", "time": "in 1 hour"}),
            (slack_list_users, {}),
            (slack_set_dnd, {"duration_minutes": 60}),
        ):
            result = tool_fn.invoke(args)
            assert "not configured" in result or "needs a user token" in result

    def test_read_channel_requires_channel(self, monkeypatch):
        monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-fake")
        assert "required" in slack_read_channel.invoke({"channel": "  "})

    def test_search_requires_query(self, monkeypatch):
        monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-fake")
        assert "required" in slack_search_messages.invoke({"query": "  "})

    def test_send_message_requires_fields(self, monkeypatch):
        monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-fake")
        assert "required" in slack_send_message.invoke({"channel": "", "text": "hi"})
        assert "required" in slack_send_message.invoke({"channel": "general", "text": "  "})

    def test_reminder_requires_fields(self, monkeypatch):
        monkeypatch.setattr(settings, "SLACK_USER_TOKEN", "xoxp-fake")
        assert "required" in slack_add_reminder.invoke({"text": "", "time": "in 1 hour"})

    def test_reminder_needs_user_token(self, monkeypatch):
        monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-fake")
        monkeypatch.setattr(settings, "SLACK_USER_TOKEN", "")
        result = slack_add_reminder.invoke({"text": "check", "time": "in 1 hour"})
        assert "user token" in result

    def test_dnd_needs_user_token(self, monkeypatch):
        monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-fake")
        monkeypatch.setattr(settings, "SLACK_USER_TOKEN", "")
        result = slack_set_dnd.invoke({"duration_minutes": 60})
        assert "user token" in result

    def test_schedule_message_validates_post_at(self, monkeypatch):
        monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-fake")
        result = slack_schedule_message.invoke(
            {"channel": "general", "text": "hi", "post_at": "not-a-number"}
        )
        assert "timestamp" in result

    def test_format_message_maps_user(self):
        msg = {
            "ts": "1700000000.000100",
            "user": "U123",
            "text": "hello world",
            "reply_count": 2,
        }
        formatted = _format_message(msg, {"U123": "Alice"})
        assert formatted["user"] == "Alice"
        assert formatted["text"] == "hello world"
        assert formatted["replies"] == 2

    def test_format_message_truncates_long_text(self):
        msg = {"ts": "1", "user": "U1", "text": "x" * 5000}
        formatted = _format_message(msg, {})
        assert len(formatted["text"]) <= 3003
        assert formatted["text"].endswith("...")

    def test_user_map_prefers_display_name(self):
        members = [
            {
                "id": "U1",
                "name": "alice",
                "real_name": "Alice Smith",
                "profile": {"display_name": "alice_dev"},
            },
            {"id": "U2", "name": "bob", "real_name": "Bob Jones", "profile": {}},
        ]
        users = _user_map(members)
        assert users["U1"] == "alice_dev"
        assert users["U2"] == "Bob Jones"

    def test_slack_tools_are_registered(self):
        from backend.tools import get_available_tools

        names = [tool.name for tool in get_available_tools()]
        for expected in (
            "slack_list_channels",
            "slack_read_channel",
            "slack_read_thread",
            "slack_search_messages",
            "slack_send_message",
            "slack_schedule_message",
            "slack_add_reminder",
            "slack_list_users",
            "slack_set_dnd",
        ):
            assert expected in names
