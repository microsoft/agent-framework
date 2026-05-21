# Copyright (c) Microsoft. All rights reserved.

import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_framework import MCPStreamableHTTPTool
from agent_framework.exceptions import ToolException


async def test_connect_initialization_failure_keeps_original_error_when_cleanup_raises_exception_group():
    exception_group_type = getattr(sys.modules["builtins"], "ExceptionGroup", None)
    if exception_group_type is None:
        pytest.skip("ExceptionGroup is only available on Python 3.11+")

    tool = MCPStreamableHTTPTool(name="test", url="http://example.com")

    mock_transport = (Mock(), Mock())
    mock_context_manager = Mock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_context_manager.__aexit__ = AsyncMock(
        side_effect=exception_group_type("unhandled errors in a TaskGroup", [ConnectionError("cleanup failed")])
    )
    tool.get_mcp_client = Mock(return_value=mock_context_manager)

    mock_session = Mock()
    mock_session.initialize = AsyncMock(side_effect=ConnectionError("Server not ready"))

    with patch("mcp.client.session.ClientSession") as mock_session_class:
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(ToolException) as exc_info:
            await tool.connect()

    assert "MCP server failed to initialize" in str(exc_info.value)
    assert "Server not ready" in str(exc_info.value)
