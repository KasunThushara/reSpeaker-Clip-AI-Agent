"""Composio toolkit selection endpoints (side panel).

- GET  /api/composio/toolkits        -> { "toolkits": [...], "selected": [...] }
- POST /api/composio/toolkits        -> body {"toolkits": [...]} ; rebuilds the
  Composio session so the change takes effect immediately (no restart).
- GET  /api/composio/auth/status?toolkit=trello -> { "connected": true/false }
"""

from flask import Blueprint, jsonify, request

from backend.tools.composio import (
    get_composio_toolkits,
    set_composio_toolkits,
    list_composio_toolkits,
    is_toolkit_connected,
    list_connected_toolkits,
    get_pending_link,
)

composio_bp = Blueprint("composio", __name__)


@composio_bp.route("/composio/toolkits", methods=["GET"])
def get_toolkits():
    return jsonify({
        "toolkits": list_composio_toolkits(),
        "selected": get_composio_toolkits(),
    })


@composio_bp.route("/composio/toolkits", methods=["POST"])
def update_toolkits():
    data = request.get_json(silent=True) or {}
    toolkits = data.get("toolkits")
    if not isinstance(toolkits, list):
        return jsonify({"error": "`toolkits` must be a list"}), 400
    set_composio_toolkits(toolkits)
    return jsonify({"selected": get_composio_toolkits()})


@composio_bp.route("/composio/auth/status", methods=["GET"])
def auth_status():
    toolkit = request.args.get("toolkit", "")
    if not toolkit:
        return jsonify({"error": "`toolkit` query param is required"}), 400
    return jsonify({"connected": is_toolkit_connected(toolkit)})


@composio_bp.route("/composio/auth/connected", methods=["GET"])
def auth_connected():
    return jsonify({"connected": list_connected_toolkits()})


@composio_bp.route("/composio/connect/link", methods=["GET"])
def connect_link():
    link = get_pending_link()
    if not link:
        return jsonify({"error": "no pending connection link"}), 404
    toolkit, url = link
    return jsonify({"toolkit": toolkit, "redirect_url": url})