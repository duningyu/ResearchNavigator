from mcp_servers.compat import MCP_SDK_AVAILABLE
from mcp_servers.paper_access.server import mcp as paper_access
from mcp_servers.research_workspace.server import mcp as workspace
from mcp_servers.scholarly_search.server import mcp as scholarly


def test_all_mcp_servers_import_without_starting_stdio() -> None:
    assert scholarly is not None
    assert paper_access is not None
    assert workspace is not None
    assert isinstance(MCP_SDK_AVAILABLE, bool)
