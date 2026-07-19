"""MCP stdio server exposing governed, read-only enterprise tools."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .knowledge_base import load_knowledge_base
from .tool_gateway import ToolDefinition, ToolGateway

mcp = FastMCP("agentic-ai-funnel-audit")
gateway = ToolGateway()


def _search(arguments: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    knowledge_base = load_knowledge_base(arguments.get("knowledge_base_mode"))
    hits = knowledge_base.search(
        domain=str(arguments["domain"]),
        query=str(arguments["query"]),
        limit=min(10, max(1, int(arguments.get("limit", 3)))),
        access_context=identity,
    )
    return {"hits": [hit.to_dict() for hit in hits]}


gateway.register(
    ToolDefinition(
        name="knowledge.search",
        allowed_roles={"auditor", "retriever", "reviewer"},
        required_fields={"domain", "query"},
        handler=_search,
    )
)


@mcp.tool()
def knowledge_search(domain: str, query: str, limit: int = 3) -> dict[str, Any]:
    """Retrieve authorized KB evidence through the zero-trust tool gateway."""
    role = os.getenv("AGENTIC_MCP_WORKLOAD_ROLE", "retriever")
    return gateway.execute(
        "knowledge.search",
        {"domain": domain, "query": query, "limit": limit},
        {"roles": [role]},
        os.getenv("AGENTIC_TOOL_GATEWAY_TOKEN"),
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
