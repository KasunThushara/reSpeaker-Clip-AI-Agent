from backend.graph.state import AgentState


def router_node(state: AgentState) -> dict:
    return {"route": "simple"}
