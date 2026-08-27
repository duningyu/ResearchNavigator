"""Official MCP SDK v2 compatibility with an explicit offline import fallback.

The fallback exists only so source/tests can be inspected in environments where PyPI is
unreachable. Production execution must install ``mcp[cli]>=2,<3``; the server reports this
state rather than pretending the SDK is active.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

_official_server_factory: Any = None
try:  # pragma: no cover - exercised when the official dependency is installed
    from mcp.server import MCPServer

    _official_server_factory = MCPServer
    MCP_SDK_AVAILABLE = True
except ImportError:  # current sandbox has no network/package cache
    MCP_SDK_AVAILABLE = False

F = TypeVar("F", bound=Callable[..., Any])
_REGISTRY: dict[int, set[str]] = {}


class _FallbackMCPServer:
    def __init__(self, name: str) -> None:
        self.name = name

    def tool(self, *, name: str | None = None, **_: object) -> Callable[[F], F]:
        def decorate(function: F) -> F:
            return function

        return decorate

    def run(self, *, transport: str = "stdio") -> None:
        raise RuntimeError(
            "Official MCP SDK is not installed. Install with `uv sync --extra dev` "
            "or `uv pip install 'mcp[cli]>=2,<3'` before starting the stdio server."
        )


def create_server(name: str) -> Any:
    server = _official_server_factory(name) if MCP_SDK_AVAILABLE else _FallbackMCPServer(name)
    _REGISTRY[id(server)] = set()
    return server


def register_tool(server: Any, name: str) -> Callable[[F], F]:
    """Register a typed function and retain a deterministic contract registry."""

    def decorate(function: F) -> F:
        _REGISTRY.setdefault(id(server), set()).add(name)
        decorated = server.tool(name=name, structured_output=True)(function)
        return cast(F, decorated)

    return decorate


def registered_tool_names(server: object) -> set[str]:
    return set(_REGISTRY.get(id(server), set()))
