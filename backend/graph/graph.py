from langgraph.graph import StateGraph, END
from backend.graph.state import AgentState
from backend.graph.router import router_node
from backend.graph.nodes.simple import simple_node


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("simple", simple_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        lambda state: state["route"],
        {"simple": "simple"},
    )

    graph.add_edge("simple", END)

    return graph.compile()
