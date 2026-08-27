from backend.llm.client import llm
from backend.graph.state import AgentState
from backend.utils.text import strip_thinking

ROUTER_PROMPT = """You are a routing classifier.

Classify the user question into exactly ONE of these categories:

simple
context
persona

Rules:

simple:
- General questions
- Explanations
- Normal conversations
- No external tools or special personality required

context:
- Questions that may require external information or tools
- Requests to create, update, or manage data in external tools such as
  Notion (to-do lists, notes, databases), calendars, or any tool-based task
- For example: "make a to-do list in Notion", "add a task", "create a note",
  "what's on my calendar", "schedule something"
- Questions about the user's device, files, or stored information

persona:
- The user explicitly requests a style, personality, teaching style,
  role, or special behavior

Return ONLY one word:
simple
context
persona

User question:
"""

VALID_ROUTES = {"simple", "context", "persona"}

TOOL_KEYWORDS = (
    "notion",
    "to-do",
    "todo",
    "task list",
    "to do list",
    "calendar",
    "schedule",
    "reminder",
    "note down",
    "create a task",
    "add a task",
    "shopify",
    "product",
    "products",
    "buy",
    "purchase",
    "cart",
    "add to cart",
    "checkout",
    "order",
    "track",
    "tracking",
    "订单",
    "购物车",
    "加购",
    "下单",
    "物流",
    "快递",
    "发货",
    "退货",
    "退款",
    "stock",
    "stocks",
    "stock price",
    "share price",
    "ticker",
    "market cap",
    "earnings",
    "revenue",
    "financial",
    "finance",
    "forex",
    "exchange rate",
    "bitcoin",
    "ethereum",
    "crypto",
    "cryptocurrency",
    "gold price",
    "s&p",
    "nasdaq",
    "dow jones",
    "股价",
    "股票",
    "行情",
    "市值",
    "财报",
    "营收",
    "净利润",
    "利润",
    "汇率",
    "美元",
    "欧元",
    "日元",
    "比特币",
    "以太坊",
    "加密货币",
    "数字货币",
    "金价",
    "黄金",
    "原油",
    "石油",
    "纳斯达克",
    "标普",
    "道琼斯",
    "美股",
    "A股",
    "港股",
    "涨停",
    "跌停",
)


def router_node(state: AgentState) -> dict:
    question = state["transcript"]

    if any(kw in question.lower() for kw in TOOL_KEYWORDS):
        return {"route": "context"}

    result = llm.invoke(ROUTER_PROMPT + question)
    route = strip_thinking(result.content).strip().lower()

    if route not in VALID_ROUTES:
        route = "simple"

    return {"route": route}
