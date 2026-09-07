import json
import time
import uuid
from decimal import Decimal
from urllib.parse import urlparse

import httpx
from langchain_core.tools import tool

from config import settings


GLOBAL_CATALOG_ENDPOINT = "https://catalog.shopify.com/api/ucp/mcp"
SHOPIFY_AUTH_ENDPOINT = "https://api.shopify.com/auth/access_token"
MAX_DESCRIPTION_CHARS = 300
# MAX_MEDIA_ITEMS = 1
MAX_VARIANTS = 5
SHOPIFY_TIMEOUT = httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0)
AUTH_TIMEOUT = httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0)
TOKEN_SAFETY_MARGIN_SECONDS = 60
ZERO_DECIMAL_CURRENCIES = {
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "ISK",
    "JPY",
    "KMF",
    "KRW",
    "PYG",
    "RWF",
    "UGX",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
}


def _format_catalog_prices(value):
    if isinstance(value, list):
        return [_format_catalog_prices(item) for item in value]
    if not isinstance(value, dict):
        return value

    formatted = {
        key: _format_catalog_prices(item) for key, item in value.items()
    }
    amount = value.get("amount")
    currency = value.get("currency")
    if isinstance(amount, (int, float)) and isinstance(currency, str):
        currency = currency.upper()
        divisor = 1 if currency in ZERO_DECIMAL_CURRENCIES else 100
        major_amount = Decimal(str(amount)) / divisor
        formatted["amount_minor"] = amount
        formatted["amount"] = f"{major_amount:.0f}" if divisor == 1 else f"{major_amount:.2f}"
        formatted["formatted"] = f"{formatted['amount']} {currency}"
        formatted["currency"] = currency
    return formatted


def _compact_catalog(value):
    if isinstance(value, list):
        return [_compact_catalog(item) for item in value]
    if not isinstance(value, dict):
        if isinstance(value, str) and len(value) > MAX_DESCRIPTION_CHARS:
            suffix = "..."
            return value[: MAX_DESCRIPTION_CHARS - len(suffix)].rstrip() + suffix
        return value

    compacted = {
        key: _compact_catalog(item) for key, item in value.items()
    }
    if "products" in compacted and isinstance(compacted["products"], list):
        compacted["products"] = [
            _compact_product(product) for product in compacted["products"]
        ]
    return compacted


def _compact_product(product):
    if not isinstance(product, dict):
        return product
    compacted = {
        key: _compact_catalog(value) for key, value in product.items()
    }
    for key in ("description", "media", "variants"):
        compacted.pop(key, None)
    if product.get("description"):
        compacted["description"] = _compact_catalog(product["description"])
    if product.get("variants"):
        compacted["variants"] = [
            _compact_variant(variant)
            for variant in product["variants"][:MAX_VARIANTS]
        ]
    if isinstance(product.get("seller"), dict):
        compacted["seller"] = {
            key: product["seller"].get(key)
            for key in ("name", "domain", "url")
            if product["seller"].get(key)
        }
    return compacted


def _compact_variant(variant):
    if not isinstance(variant, dict):
        return variant
    fields = (
        "id",
        "title",
        "price",
        "availability",
        "options",
        "url",
    )
    compacted = {
        key: _compact_catalog(variant[key])
        for key in fields
        if key in variant
    }
    # Surface the merchant domain so the agent can pass it directly to
    # cart/order tools without parsing the product URL itself.
    url = variant.get("url")
    if isinstance(url, str) and url:
        domain = urlparse(url).netloc
        if domain:
            compacted["shop_domain"] = domain
    return compacted


def _shop_domain_endpoint(shop_domain: str) -> str:
    """Build the merchant's UCP MCP endpoint from a shop domain.

    Accepts a bare domain ("shop.example.com"), a full URL
    ("https://shop.example.com/products/foo"), or a myshopify domain.
    Extracts the hostname so full product URLs also work.
    """
    value = shop_domain.strip().rstrip("/")
    if not value:
        raise ValueError("shop_domain is required")
    if "://" in value:
        domain = urlparse(value).netloc
    elif value.startswith("www.") or "." in value:
        domain = value
    else:
        domain = value
    if not domain:
        raise ValueError(f"Could not extract a domain from: {shop_domain}")
    return f"https://{domain}/api/ucp/mcp"


_order_token_cache = {"token": "", "expires_at": 0.0}


def _get_order_access_token() -> str:
    """Return a cached Global API JWT with read_global_api_orders scope.

    Tokens last 60 minutes; we refresh slightly early to avoid expiry
    mid-request. Returns an empty string when credentials aren't configured.
    """
    now = time.time()
    if _order_token_cache["token"] and now < _order_token_cache["expires_at"]:
        return _order_token_cache["token"]

    client_id = settings.SHOPIFY_CLIENT_ID
    client_secret = settings.SHOPIFY_CLIENT_SECRET
    if not client_id or not client_secret:
        return ""

    try:
        response = httpx.post(
            SHOPIFY_AUTH_ENDPOINT,
            json={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            timeout=AUTH_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return f"__ERROR__{exc}"

    token = data.get("access_token", "")
    expires_in = data.get("expires_in", 0)
    if token and isinstance(expires_in, (int, float)):
        _order_token_cache["token"] = token
        _order_token_cache["expires_at"] = now + expires_in - TOKEN_SAFETY_MARGIN_SECONDS
    return token


def _call_shopify(
    tool_name: str,
    arguments: dict,
    endpoint: str = GLOBAL_CATALOG_ENDPOINT,
    bearer_token: str = "",
    idempotency_key: str = "",
) -> str:
    meta = {"ucp-agent": {"profile": settings.SHOPIFY_AGENT_PROFILE}}
    if idempotency_key:
        meta["idempotency-key"] = idempotency_key
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": 1,
        "params": {
            "name": tool_name,
            "arguments": {"meta": meta},
        },
    }
    payload["params"]["arguments"].update(arguments)
    try:
        headers = {}
        bearer = bearer_token or settings.SHOPIFY_ACCESS_TOKEN
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        response = httpx.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=SHOPIFY_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException:
        return "Shopify request timed out. Please try the product search again."
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        return f"Shopify request failed: {exc}"

    if "error" in data:
        return f"Shopify returned an error: {json.dumps(data['error'], ensure_ascii=False)}"
    result = data.get("result", {})
    if result.get("isError"):
        return f"Shopify tool failed: {json.dumps(result, ensure_ascii=False)}"
    content = result.get("structuredContent", result.get("content", result))
    return json.dumps(
        _compact_catalog(_format_catalog_prices(content)),
        ensure_ascii=False,
    )


@tool
def shopify_search_catalog(
    query: str,
    address_country: str = "",
    limit: int = 5,
    cursor: str = "",
) -> str:
    """Search products across Shopify merchants with Global Catalog.
    Use this when a customer asks to find, browse, compare, or discover products
    from any Shopify merchant. Do not use web_search for product discovery."""
    catalog = {"query": query}
    if address_country:
        catalog["context"] = {"address_country": address_country}
    pagination = {"limit": max(1, min(limit, 250))}
    if cursor:
        pagination["cursor"] = cursor
    catalog["pagination"] = pagination
    return _call_shopify("search_catalog", {"catalog": catalog})


@tool
def shopify_lookup_catalog(ids: list[str]) -> str:
    """Look up Shopify products or variants by their product or variant IDs.
    Use this after a catalog search when product details are needed for known IDs."""
    if not ids:
        return "Shopify lookup requires at least one product or variant ID."
    return _call_shopify("lookup_catalog", {"catalog": {"ids": ids[:50]}})


@tool
def shopify_get_product(
    product_id: str,
    selected: list[dict] | None = None,
) -> str:
    """Get full details for one product in Shopify Global Catalog, optionally selecting options.
    Use this when the customer asks for details, options, or availability of a
    specific product found in Global Catalog. Selected options
    use objects such as {"name": "Color", "label": "Blue"}."""
    catalog = {"id": product_id}
    if selected:
        catalog["selected"] = selected
    return _call_shopify("get_product", {"catalog": catalog})


@tool
def shopify_create_cart(
    shop_domain: str,
    line_items: list[dict],
    address_country: str = "",
    address_region: str = "",
    postal_code: str = "",
) -> str:
    """Create a shopping cart at a Shopify merchant with the given line items.
    Use this when the customer has chosen products and wants to build a cart,
    estimate totals, or get a shareable cart link. Each line item needs
    {"quantity": 1, "item": {"id": "gid://shopify/ProductVariant/123"}}.
    shop_domain comes from the shop_domain field of a catalog search result
    (e.g. "www.skullcandy.com"), or the domain the customer mentioned."""
    try:
        endpoint = _shop_domain_endpoint(shop_domain)
    except ValueError as exc:
        return f"Shopify cart error: {exc}"
    cart = {"line_items": line_items}
    context = {
        key: value
        for key, value in (
            ("address_country", address_country),
            ("address_region", address_region),
            ("postal_code", postal_code),
        )
        if value
    }
    if context:
        cart["context"] = context
    return _call_shopify("create_cart", {"cart": cart}, endpoint=endpoint)


@tool
def shopify_get_cart(shop_domain: str, cart_id: str) -> str:
    """Retrieve the current state of a cart at a Shopify merchant.
    Use this to refresh estimated totals, check cart contents, or verify the
    cart still exists before checkout. cart_id looks like
    "gid://shopify/Cart/cart_abc123". shop_domain is the merchant's domain,
    e.g. "www.skullcandy.com"."""
    try:
        endpoint = _shop_domain_endpoint(shop_domain)
    except ValueError as exc:
        return f"Shopify cart error: {exc}"
    return _call_shopify("get_cart", {"id": cart_id}, endpoint=endpoint)


@tool
def shopify_update_cart(
    shop_domain: str,
    cart_id: str,
    line_items: list[dict],
    address_country: str = "",
    address_region: str = "",
    postal_code: str = "",
) -> str:
    """Replace the contents of a cart at a Shopify merchant (PUT semantics).
    Use this when the customer changes quantities or removes items. Send the
    FULL desired line_items array: anything omitted is removed from the cart.
    Each line item needs {"quantity": 1, "item": {"id": "gid://shopify/ProductVariant/123"}}.
    shop_domain is the merchant's domain, e.g. "www.skullcandy.com"."""
    try:
        endpoint = _shop_domain_endpoint(shop_domain)
    except ValueError as exc:
        return f"Shopify cart error: {exc}"
    cart = {"line_items": line_items}
    context = {
        key: value
        for key, value in (
            ("address_country", address_country),
            ("address_region", address_region),
            ("postal_code", postal_code),
        )
        if value
    }
    if context:
        cart["context"] = context
    return _call_shopify("update_cart", {"id": cart_id, "cart": cart}, endpoint=endpoint)


@tool
def shopify_cancel_cart(shop_domain: str, cart_id: str) -> str:
    """Cancel an active cart at a Shopify merchant.
    Use this when the customer abandons the purchase or wants to start over.
    The cart is removed and cannot be used again. shop_domain is the
    merchant's domain, e.g. "www.skullcandy.com"."""
    try:
        endpoint = _shop_domain_endpoint(shop_domain)
    except ValueError as exc:
        return f"Shopify cart error: {exc}"
    return _call_shopify(
        "cancel_cart",
        {"id": cart_id},
        endpoint=endpoint,
        idempotency_key=str(uuid.uuid4()),
    )


@tool
def shopify_get_order(shop_domain: str, order_id: str) -> str:
    """Fetch the current state of an order placed through this agent at a Shopify merchant.
    Use this when the customer asks "Where's my order?" or about order status,
    fulfillment, tracking, or refunds. order_id looks like
    "gid://shopify/Order/123456". shop_domain is the merchant's domain,
    e.g. "www.skullcandy.com". Requires Shopify client credentials to be
    configured; only orders placed through this agent are accessible."""
    try:
        endpoint = _shop_domain_endpoint(shop_domain)
    except ValueError as exc:
        return f"Shopify order error: {exc}"

    token = _get_order_access_token()
    if token.startswith("__ERROR__"):
        return f"Shopify authentication failed: {token[len('__ERROR__'):]}"
    if not token:
        return (
            "Shopify order lookup is not configured. Set SHOPIFY_CLIENT_ID and "
            "SHOPIFY_CLIENT_SECRET to enable order tracking."
        )
    return _call_shopify(
        "get_order",
        {"id": order_id},
        endpoint=endpoint,
        bearer_token=token,
    )