from backend.graph.router import router_node
from backend.graph.state import AgentState
from backend.graph.graph import build_graph


def _make_state(transcript: str) -> AgentState:
    return {
        "messages": [],
        "transcript": transcript,
        "route": "",
        "response": "",
        "error": None,
    }


def test_router_returns_simple():
    state = _make_state("hello")
    result = router_node(state)
    assert result["route"] == "simple"


def test_graph_routes_to_simple():
    graph = build_graph()
    state = _make_state("what is I2S?")
    result = graph.invoke(state)
    assert result["route"] == "simple"
    assert len(result["response"]) > 0


def test_graph_returns_nonempty_response():
    graph = build_graph()
    state = _make_state("Say hello in one word.")
    result = graph.invoke(state)
    assert result["route"] == "simple"
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0
