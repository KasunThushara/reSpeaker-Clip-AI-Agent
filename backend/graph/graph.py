from typing import Literal

from langgraph.graph import StateGraph, START, END

from backend.graph.state import AgentState
from backend.graph.router import router_node
from backend.graph.nodes.simple import simple_node
from backend.graph.nodes.agentic import agentic_node
from backend.graph.nodes.persona import persona_node


def route_after_router(state: AgentState) -> Literal["simple", "context", "persona"]:
    return state["route"]


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("router", router_node)
    builder.add_node("simple", simple_node)
    builder.add_node("context", agentic_node)
    builder.add_node("persona", persona_node)

    builder.add_edge(START, "router")

    builder.add_conditional_edges(
        "router",
        route_after_router,
        {
            "simple": "simple",
            "context": "context",
            "persona": "persona",
        },
    )

    builder.add_edge("simple", END)
    builder.add_edge("context", END)
    builder.add_edge("persona", END)

    return builder.compile()
