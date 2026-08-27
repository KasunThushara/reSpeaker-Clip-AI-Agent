import httpx
from langchain_core.tools import tool

from config import settings


FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_TIMEOUT = httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0)
MAX_NEWS_ITEMS = 5
MAX_STATEMENT_PERIODS = 4
MAX_PROFILE_CHARS = 300


def _fmp_get(path: str, params: dict) -> list | dict:
    """Call the FMP REST API and return the parsed JSON payload.

    Raises httpx.HTTPError on network/timeout failures and ValueError when
    the API responds with an error payload (FMP returns a JSON object with
    an "Error Message" key instead of a list).
    """
    params = {k: v for k, v in params.items() if v not in (None, "")}
    params["apikey"] = settings.FMP_API_KEY
    response = httpx.get(f"{FMP_BASE_URL}{path}", params=params, timeout=FMP_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and "Error Message" in data:
        raise ValueError(data["Error Message"])
    return data


def _fmt(value) -> str:
    """Format a number compactly for voice output (e.g. 3.45T, 12.5B)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value) if value is not None else ""
    if abs(value) >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _compact_quote(q: dict) -> dict:
    """Keep only the fields the agent needs from a quote response."""
    return {
        "symbol": q.get("symbol"),
        "name": q.get("name"),
        "price": q.get("price"),
        "change": q.get("change"),
        "change_percent": q.get("changesPercentage"),
        "open": q.get("open"),
        "day_high": q.get("dayHigh"),
        "day_low": q.get("dayLow"),
        "previous_close": q.get("previousClose"),
        "volume": _fmt(q.get("volume")),
        "market_cap": _fmt(q.get("marketCap")),
        "currency": q.get("currency"),
        "exchange": q.get("exchange"),
        "timestamp": q.get("timestamp"),
    }


def _compact_profile(p: dict) -> dict:
    """Keep only the fields the agent needs from a company profile."""
    return {
        "symbol": p.get("symbol"),
        "company_name": p.get("companyName"),
        "exchange": p.get("exchange"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "ceo": p.get("ceo"),
        "employees": p.get("fullTimeEmployees"),
        "headquarters": ", ".join(
            part
            for part in (p.get("city"), p.get("state"), p.get("country"))
            if part
        ),
        "website": p.get("website"),
        "description": (p.get("description") or "")[:MAX_PROFILE_CHARS],
        "market_cap": _fmt(p.get("mktCap")),
        "price": p.get("price"),
        "currency": p.get("currency"),
    }


def _compact_income_statement(s: dict) -> dict:
    """Keep only the headline figures from an income statement period."""
    return {
        "period": s.get("period"),
        "fiscal_year": s.get("calendarYear"),
        "revenue": _fmt(s.get("revenue")),
        "gross_profit": _fmt(s.get("grossProfit")),
        "operating_income": _fmt(s.get("operatingIncome")),
        "net_income": _fmt(s.get("netIncome")),
        "eps": s.get("eps"),
        "eps_diluted": s.get("epsdiluted"),
        "currency": s.get("currency"),
    }


@tool
def finance_search_symbol(query: str) -> str:
    """Search for stock ticker symbols by company name or partial symbol.
    Use this FIRST when the user mentions a company by name (e.g. "Apple",
    "特斯拉") and you need its ticker symbol before calling other finance
    tools. Returns symbol, company name, and exchange for each match."""
    if not settings.FMP_API_KEY:
        return "Finance tools are unavailable: FMP_API_KEY is not configured."

    try:
        results = _fmp_get("/search-name", {"query": query})
    except Exception as e:
        return f"Symbol search failed: {e}"

    if not results:
        return f"No companies found matching '{query}'."

    lines = []
    for r in results[:5]:
        lines.append(
            f"{r.get('symbol')} - {r.get('name')} ({r.get('exchange', 'N/A')})"
        )
    return "\n".join(lines)


@tool
def finance_get_quote(symbol: str) -> str:
    """Get a real-time quote for a stock, ETF, index, cryptocurrency, forex
    pair, or commodity. Examples: AAPL (Apple stock), BTCUSD (Bitcoin),
    EURUSD (euro/dollar exchange rate), GCUSD (gold), ^GSPC (S&P 500).
    The symbol must be a valid ticker, not a company name; use
    finance_search_symbol first if you only know the company name."""
    if not settings.FMP_API_KEY:
        return "Finance tools are unavailable: FMP_API_KEY is not configured."

    try:
        results = _fmp_get("/quote", {"symbol": symbol})
    except Exception as e:
        return f"Quote lookup failed: {e}"

    if not results:
        return (
            f"No quote found for '{symbol}'. Use finance_search_symbol to find "
            "the correct ticker."
        )

    q = _compact_quote(results[0] if isinstance(results, list) else results)
    change = q["change"]
    pct = q["change_percent"]
    direction = "up" if isinstance(change, (int, float)) and change >= 0 else "down"
    return (
        f"{q['name']} ({q['symbol']}): {q['price']} {q['currency']}, "
        f"{direction} {abs(change)} ({pct}%) today. "
        f"Range {q['day_low']}-{q['day_high']}, previous close "
        f"{q['previous_close']}. Market cap {q['market_cap']}."
    )


@tool
def finance_get_profile(symbol: str) -> str:
    """Get a company profile: sector, industry, CEO, headquarters, employee
    count, market cap, and a short business description. Use for questions
    like "what does this company do" or "tell me about Nvidia"."""
    if not settings.FMP_API_KEY:
        return "Finance tools are unavailable: FMP_API_KEY is not configured."

    try:
        results = _fmp_get("/profile", {"symbol": symbol})
    except Exception as e:
        return f"Profile lookup failed: {e}"

    if not results:
        return (
            f"No profile found for '{symbol}'. Use finance_search_symbol to "
            "find the correct ticker."
        )

    p = _compact_profile(results[0] if isinstance(results, list) else results)
    return (
        f"{p['company_name']} ({p['symbol']}), {p['exchange']}. "
        f"Sector: {p['sector']}; Industry: {p['industry']}. "
        f"CEO: {p['ceo']}. HQ: {p['headquarters']}. "
        f"Employees: {p['employees']}. Market cap: {p['market_cap']} "
        f"{p['currency']}. {p['description']}"
    )


@tool
def finance_get_income_statement(symbol: str, period: str = "annual") -> str:
    """Get revenue, gross profit, operating income, net income, and EPS for a
    company. period must be "annual" or "quarterly". Use for questions like
    "what was Apple's revenue last year" or "how much profit did Tesla make"."""
    if not settings.FMP_API_KEY:
        return "Finance tools are unavailable: FMP_API_KEY is not configured."

    if period not in ("annual", "quarterly"):
        return 'period must be "annual" or "quarterly".'

    try:
        results = _fmp_get(
            "/income-statement", {"symbol": symbol, "period": period}
        )
    except Exception as e:
        return f"Income statement lookup failed: {e}"

    if not results:
        return (
            f"No financial statements found for '{symbol}'. Use "
            "finance_search_symbol to find the correct ticker."
        )

    lines = []
    for s in results[:MAX_STATEMENT_PERIODS]:
        c = _compact_income_statement(s)
        lines.append(
            f"{c['period']} (FY{c['fiscal_year']}): revenue {c['revenue']}, "
            f"gross profit {c['gross_profit']}, operating income "
            f"{c['operating_income']}, net income {c['net_income']}, "
            f"EPS {c['eps']} ({c['currency']})"
        )
    return "\n".join(lines)


@tool
def finance_get_news(symbol: str) -> str:
    """Get the latest news articles about a specific stock or company.
    Use for questions like "any news about Tesla" or "what's happening with
    Nvidia stock"."""
    if not settings.FMP_API_KEY:
        return "Finance tools are unavailable: FMP_API_KEY is not configured."

    try:
        results = _fmp_get("/news/stock-latest", {"symbol": symbol})
    except Exception as e:
        return f"News lookup failed: {e}"

    if not results:
        return f"No recent news found for '{symbol}'."

    lines = []
    for n in results[:MAX_NEWS_ITEMS]:
        lines.append(
            f"- {n.get('publishedTime', '')} {n.get('title', '')} "
            f"(source: {n.get('publisher', n.get('site', 'N/A'))})"
        )
    return "\n".join(lines)
