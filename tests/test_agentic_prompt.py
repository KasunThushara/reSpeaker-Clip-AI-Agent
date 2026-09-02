"""Prompt-level tests for the hybrid tool architecture.

These assert on SYSTEM_PROMPT wording only — no network, LLM calls, or
external keys are involved.
"""

from backend.graph.nodes.agentic import SYSTEM_PROMPT

EXPECTED_LOCAL_TOOLS = [
    "calculator",
    "web_search",
    "search_conversations",
    "finance_search_symbol",
    "finance_get_quote",
    "finance_get_profile",
    "finance_get_income_statement",
    "finance_get_news",
    "shopify_search_catalog",
    "shopify_lookup_catalog",
    "shopify_get_product",
    "shopify_create_cart",
    "shopify_get_cart",
    "shopify_update_cart",
    "shopify_cancel_cart",
    "shopify_get_order",
]

COMPOSIO_OWNED_APPS = [
    "Gmail",
    "Google Calendar",
    "Slack",
    "Linear",
    "GitHub",
    "Trello",
    "Asana",
    "Notion",
]


class TestHybridRoutingPrompt:
    def test_routes_local_tools_explicitly(self):
        for name in EXPECTED_LOCAL_TOOLS:
            assert name in SYSTEM_PROMPT, name

    def test_routes_external_apps_through_composio(self):
        for app in COMPOSIO_OWNED_APPS:
            assert app in SYSTEM_PROMPT, app
        for wrapper in ("composio_search", "composio_execute", "composio_connect"):
            assert wrapper in SYSTEM_PROMPT

    def test_composio_sequence_has_search_execute_connect(self):
        # The three steps must be mentioned in the right order.
        seq_idx = [SYSTEM_PROMPT.index(w) for w in
                   ("composio_search", "composio_execute", "composio_connect")]
        assert seq_idx == sorted(seq_idx)

    def test_no_contradictory_single_layer_wording(self):
        for phrase in ("single tool layer", "Composio as your single",
                       "single, unified tool layer", "single unified tool layer"):
            assert phrase not in SYSTEM_PROMPT

    def test_safety_boundaries_present(self):
        for phrase in (
            "untrusted data",        # external content is data, not instructions
            "never instructions",
            "explicit user intent",  # sending requires intent
            "require confirmation",  # destructive actions need confirmation
            "Never invent URLs",
            "draft",                 # prefer drafts when not asked to send
        ):
            assert phrase in SYSTEM_PROMPT, phrase

    def test_keeps_voice_response_rules(self):
        for phrase in ("2-3 short sentences", "plain text only"):
            assert phrase in SYSTEM_PROMPT

    def test_keeps_memory_relevance_rules(self):
        for phrase in ("recalled context", "trust the most recently created one"):
            assert phrase in SYSTEM_PROMPT
