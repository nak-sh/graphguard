"""MCP server exposing read-only tools, dry runs, and approval-token execution."""

from __future__ import annotations

import os
import secrets
from typing import Any

from apps.actions.executor import ActionExecutor
from apps.graph_tools.tools import GraphTools

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    try:
        # MCP SDK 2 renamed FastMCP to MCPServer while retaining the tool
        # decorator shape used below.
        from mcp.server.mcpserver import MCPServer as FastMCP
    except ImportError:
        FastMCP = None


def build_server():
    if FastMCP is None:
        raise RuntimeError("mcp is not installed; install requirements.txt")
    tools = GraphTools(
        host=os.getenv("GRAPHGUARD_DB_HOST", "localhost"),
        port=int(os.getenv("GRAPHGUARD_DB_PORT", "6379")),
        graph_name=os.getenv("GRAPHGUARD_GRAPH_NAME", "graphguard"),
    )
    executor = ActionExecutor(
        host=os.getenv("GRAPHGUARD_DB_HOST", "localhost"),
        port=int(os.getenv("GRAPHGUARD_DB_PORT", "6379")),
        graph_name=os.getenv("GRAPHGUARD_GRAPH_NAME", "graphguard"),
        require_incident=True,
    )
    server = FastMCP("GraphGuard")

    @server.tool()
    def get_entity_summary(entity_id: str) -> dict[str, Any]:
        return tools.get_entity_summary(entity_id).model_dump()

    @server.tool()
    def get_neighborhood(entity_id: str, max_hops: int = 4, limit: int = 200) -> dict[str, Any]:
        return tools.get_neighborhood(entity_id, max_hops=max_hops, limit=limit).model_dump()

    @server.tool()
    def find_shared_infrastructure(entity_id: str, kind: str = "device") -> list[dict[str, Any]]:
        return [item.model_dump() for item in tools.find_shared_infrastructure(entity_id, kind=kind)]

    @server.tool()
    def trace_money_paths(source_id: str, target_id: str | None = None, max_hops: int = 5) -> list[dict[str, Any]]:
        return [item.model_dump() for item in tools.trace_money_paths(source_id, target_id=target_id, max_hops=max_hops)]

    @server.tool()
    def detect_transfer_cycles(entity_id: str, max_hops: int = 6) -> list[dict[str, Any]]:
        return [item.model_dump() for item in tools.detect_transfer_cycles(entity_id, max_hops=max_hops)]

    @server.tool()
    def dry_run_action(incident_id: str, proposed_action_id: str) -> dict[str, Any]:
        incident = tools.get_incident(incident_id)
        if not incident:
            return {"success": False, "error": "incident not found"}
        action = next((item for item in incident.get("proposed_actions", []) if item.get("action_id") == proposed_action_id), None)
        if not action:
            return {"success": False, "error": "proposed action not found"}
        return executor.dry_run_action(action, policy_tier=action.get("tier"))

    @server.tool()
    def execute_action(incident_id: str, proposed_action_id: str, approval_token: str, idempotency_key: str) -> dict[str, Any]:
        expected = os.getenv("GRAPHGUARD_MCP_APPROVAL_TOKEN")
        if not expected or not secrets.compare_digest(approval_token, expected):
            return {"success": False, "error": "explicit MCP approval token required"}
        incident = tools.get_incident(incident_id)
        if not incident:
            return {"success": False, "error": "incident not found"}
        action = next((item for item in incident.get("proposed_actions", []) if item.get("action_id") == proposed_action_id), None)
        if not action:
            return {"success": False, "error": "proposed action not found"}
        return executor.execute_action(action, incident_id=incident_id, proposed_action_id=proposed_action_id, policy_tier=action.get("tier"), idempotency_key=idempotency_key, actor="mcp")

    return server


if __name__ == "__main__":
    import asyncio
    server = build_server()
    if hasattr(server, "run_stdio_async"):
        asyncio.run(server.run_stdio_async())
    else:
        server.run(transport="stdio")
