from backend.tools.calculator import calculator
from backend.tools.search import web_search
from backend.tools.notion import (
    get_notion_tools,
    add_todo,
    list_todos,
    complete_todo,
    delete_todo,
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
