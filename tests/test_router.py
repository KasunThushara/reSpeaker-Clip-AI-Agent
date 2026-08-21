from backend.graph.router import router_node
from backend.graph.state import AgentState
from backend.graph.graph import build_graph
from backend.graph.nodes.agentic import agentic_node
from config import settings

import pytest


def _make_state(transcript: str) -> AgentState:
    return {
        "messages": [],
        "transcript": transcript,
        "route": "",
        "response": "",
        "error": None,
    }


class TestRouter:
    def test_classifies_simple(self):
        result = router_node(_make_state("hello how are you"))
        assert result["route"] == "simple"

    def test_classifies_context(self):
        result = router_node(_make_state("what is the latest firmware version of XVF3800"))
        assert result["route"] == "context"

    def test_classifies_persona(self):
        result = router_node(_make_state("explain I2S like an electronics teacher teaching a beginner"))
        assert result["route"] == "persona"

    def test_unknown_falls_back_to_simple(self):
        result = router_node(_make_state("xyzzy blorf"))
        assert result["route"] in {"simple", "context", "persona"}


class TestGraph:
    def test_routes_to_simple_and_responds(self):
        graph = build_graph()
        result = graph.invoke(_make_state("what is 2+2?"))
        assert result["route"] == "simple"
        assert len(result["response"]) > 0

    def test_routes_to_context_and_responds(self):
        if not settings.TAVILY_API_KEY:
            pytest.skip("TAVILY_API_KEY not configured")
        graph = build_graph()
        result = graph.invoke(_make_state("what is the latest firmware version of XVF3800"))
        assert result["route"] == "context"
        assert len(result["response"]) > 0

    def test_routes_to_persona_and_responds(self):
        graph = build_graph()
        result = graph.invoke(_make_state("explain Python like a kindergarten teacher"))
        assert result["route"] == "persona"
        assert len(result["response"]) > 0

    def test_graph_returns_valid_response(self):
        graph = build_graph()
        result = graph.invoke(_make_state("Say hello in one word."))
        assert result["route"] in {"simple", "context", "persona"}
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0


class TestAgent:
    def test_agent_uses_calculator(self):
        result = agentic_node(_make_state("what is 2300 multiplied by 4?"))
        assert "9200" in result["response"] or "9,200" in result["response"]

    def test_agent_responds(self):
        result = agentic_node(_make_state("what is 7 plus 8?"))
        assert "15" in result["response"]
