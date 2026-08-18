from backend.tools.calculator import calculator
from backend.tools.search import web_search


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
