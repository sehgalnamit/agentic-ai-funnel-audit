from __future__ import annotations

from dataclasses import dataclass
import hmac
import os
from typing import Any, Callable


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    allowed_roles: set[str]
    required_fields: set[str]
    handler: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class ToolGateway:
    """MCP-facing, zero-trust boundary for governed tool execution.

    The gateway validates an explicit schema, authenticates the calling gateway,
    checks the agent role, and exposes only allow-listed tools.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def describe(self, roles: list[str]) -> list[dict[str, Any]]:
        role_set = set(roles)
        return [
            {"name": tool.name, "required_fields": sorted(tool.required_fields)}
            for tool in self._tools.values()
            if role_set & tool.allowed_roles
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any], identity: dict[str, Any], gateway_token: str | None) -> dict[str, Any]:
        self._authenticate_gateway(gateway_token)
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ToolGatewayError("Tool is not allow-listed.", status_code=404)
        if not isinstance(arguments, dict):
            raise ToolGatewayError("Tool arguments must be an object.")
        missing = tool.required_fields - set(arguments)
        if missing:
            raise ToolGatewayError(f"Tool arguments are missing: {', '.join(sorted(missing))}.")
        roles = set(identity.get("roles") or [])
        if not roles & tool.allowed_roles:
            raise ToolGatewayError("Agent role is not authorized for this tool.", status_code=403)
        return tool.handler(arguments, identity)

    def _authenticate_gateway(self, gateway_token: str | None) -> None:
        expected = os.getenv("AGENTIC_TOOL_GATEWAY_TOKEN", "")
        if not expected:
            raise ToolGatewayError("Tool gateway token is not configured.", status_code=503)
        if not gateway_token or not hmac.compare_digest(gateway_token, expected):
            raise ToolGatewayError("Tool gateway authentication failed.", status_code=401)


class ToolGatewayError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
