# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import ANY, AsyncMock, patch

from agent_framework import AIFunction
from agent_framework.cognee import cognee_add, cognee_search, get_cognee_tools


def test_cognee_tools_import() -> None:
    """Test that cognee tools can be imported."""
    assert cognee_add is not None
    assert cognee_search is not None
    assert get_cognee_tools is not None


def test_cognee_add_is_ai_function() -> None:
    """Test that cognee_add is an AIFunction."""
    assert isinstance(cognee_add, AIFunction)
    assert cognee_add.name == "cognee_add"


def test_cognee_search_is_ai_function() -> None:
    """Test that cognee_search is an AIFunction."""
    assert isinstance(cognee_search, AIFunction)
    assert cognee_search.name == "cognee_search"


def test_get_cognee_tools_returns_tuple() -> None:
    """Test that get_cognee_tools returns a tuple of tools."""
    add_tool, search_tool = get_cognee_tools("test-session")
    assert isinstance(add_tool, AIFunction)
    assert isinstance(search_tool, AIFunction)


def test_get_cognee_tools_generates_session_id() -> None:
    """Test that get_cognee_tools generates a session ID when not provided."""
    add_tool1, _ = get_cognee_tools()
    add_tool2, _ = get_cognee_tools()
    # Each call should have a different session ID
    assert add_tool1 is not add_tool2


class TestCogneeAddTool:
    """Test cognee_add tool."""

    @patch("agent_framework_cognee._tools._enqueue_add")
    async def test_cognee_add_calls_enqueue(self, mock_enqueue: AsyncMock) -> None:
        """Test that cognee_add calls _enqueue_add."""
        mock_enqueue.return_value = None

        result = await cognee_add.invoke(arguments=cognee_add.input_model(data="test data"))

        mock_enqueue.assert_called_once()
        assert result == "Item added to cognee and processed"

    @patch("agent_framework_cognee._tools._enqueue_add")
    async def test_cognee_add_with_node_set(self, mock_enqueue: AsyncMock) -> None:
        """Test that cognee_add passes node_set correctly."""
        mock_enqueue.return_value = None

        result = await cognee_add.invoke(arguments=cognee_add.input_model(data="test data", node_set=["session-123"]))

        mock_enqueue.assert_called_once_with("test data", node_set=["session-123"])
        assert result == "Item added to cognee and processed"


class TestCogneeSearchTool:
    """Test cognee_search tool."""

    @patch("agent_framework_cognee._tools.cognee")
    @patch("agent_framework_cognee._tools._add_queue")
    async def test_cognee_search_calls_search(self, mock_queue: AsyncMock, mock_cognee: AsyncMock) -> None:
        """Test that cognee_search calls cognee.search."""
        mock_queue.join = AsyncMock()
        mock_cognee.search = AsyncMock(return_value=[{"result": "test"}])

        result = await cognee_search.invoke(arguments=cognee_search.input_model(query_text="test query"))

        mock_cognee.search.assert_called_once_with("test query", node_type=ANY, node_name=None, top_k=100)
        assert result == [{"result": "test"}]


class TestSessionizedTools:
    """Test sessionized tools from get_cognee_tools."""

    @patch("agent_framework_cognee._tools._enqueue_add")
    async def test_sessionized_add_includes_session(self, mock_enqueue: AsyncMock) -> None:
        """Test that sessionized add tool includes session_id in node_set."""
        mock_enqueue.return_value = None

        add_tool, _ = get_cognee_tools("my-session")
        await add_tool.invoke(arguments=add_tool.input_model(data="test data"))

        mock_enqueue.assert_called_once_with("test data", node_set=["my-session"])

    @patch("agent_framework_cognee._tools.cognee")
    @patch("agent_framework_cognee._tools._add_queue")
    async def test_sessionized_search_includes_session(self, mock_queue: AsyncMock, mock_cognee: AsyncMock) -> None:
        """Test that sessionized search tool includes session_id in node_name."""
        mock_queue.join = AsyncMock()
        mock_cognee.search = AsyncMock(return_value=[])

        _, search_tool = get_cognee_tools("my-session")
        await search_tool.invoke(arguments=search_tool.input_model(query_text="query"))

        mock_cognee.search.assert_called_once_with("query", node_type=ANY, node_name=["my-session"], top_k=100)
