# Copyright (c) Microsoft. All rights reserved.

"""Tests for type definitions in _types.py."""

from agent_framework_ag_ui._types import AgentState, AGUIRequest, PredictStateConfig, RunMetadata


class TestPredictStateConfig:
    """Test PredictStateConfig TypedDict."""

    def test_predict_state_config_creation(self) -> None:
        """Test creating a PredictStateConfig dict."""
        config: PredictStateConfig = {
            "state_key": "document",
            "tool": "write_document",
            "tool_argument": "content",
        }

        assert config["state_key"] == "document"
        assert config["tool"] == "write_document"
        assert config["tool_argument"] == "content"

    def test_predict_state_config_with_none_tool_argument(self) -> None:
        """Test PredictStateConfig with None tool_argument."""
        config: PredictStateConfig = {
            "state_key": "status",
            "tool": "update_status",
            "tool_argument": None,
        }

        assert config["state_key"] == "status"
        assert config["tool"] == "update_status"
        assert config["tool_argument"] is None

    def test_predict_state_config_type_validation(self) -> None:
        """Test that PredictStateConfig validates field types at runtime."""
        config: PredictStateConfig = {
            "state_key": "test",
            "tool": "test_tool",
            "tool_argument": "arg",
        }

        assert isinstance(config["state_key"], str)
        assert isinstance(config["tool"], str)
        assert isinstance(config["tool_argument"], (str, type(None)))


class TestRunMetadata:
    """Test RunMetadata TypedDict."""

    def test_run_metadata_creation(self) -> None:
        """Test creating a RunMetadata dict."""
        metadata: RunMetadata = {
            "run_id": "run-123",
            "thread_id": "thread-456",
            "predict_state": [
                {
                    "state_key": "document",
                    "tool": "write_document",
                    "tool_argument": "content",
                }
            ],
        }

        assert metadata["run_id"] == "run-123"
        assert metadata["thread_id"] == "thread-456"
        assert metadata["predict_state"] is not None
        assert len(metadata["predict_state"]) == 1
        assert metadata["predict_state"][0]["state_key"] == "document"

    def test_run_metadata_with_none_predict_state(self) -> None:
        """Test RunMetadata with None predict_state."""
        metadata: RunMetadata = {
            "run_id": "run-789",
            "thread_id": "thread-012",
            "predict_state": None,
        }

        assert metadata["run_id"] == "run-789"
        assert metadata["thread_id"] == "thread-012"
        assert metadata["predict_state"] is None

    def test_run_metadata_empty_predict_state(self) -> None:
        """Test RunMetadata with empty predict_state list."""
        metadata: RunMetadata = {
            "run_id": "run-345",
            "thread_id": "thread-678",
            "predict_state": [],
        }

        assert metadata["run_id"] == "run-345"
        assert metadata["thread_id"] == "thread-678"
        assert metadata["predict_state"] == []


class TestAgentState:
    """Test AgentState TypedDict."""

    def test_agent_state_creation(self) -> None:
        """Test creating an AgentState dict."""
        state: AgentState = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ]
        }

        assert state["messages"] is not None
        assert len(state["messages"]) == 2
        assert state["messages"][0]["role"] == "user"
        assert state["messages"][1]["role"] == "assistant"

    def test_agent_state_with_none_messages(self) -> None:
        """Test AgentState with None messages."""
        state: AgentState = {"messages": None}

        assert state["messages"] is None

    def test_agent_state_empty_messages(self) -> None:
        """Test AgentState with empty messages list."""
        state: AgentState = {"messages": []}

        assert state["messages"] == []

    def test_agent_state_complex_messages(self) -> None:
        """Test AgentState with complex message structures."""
        state: AgentState = {
            "messages": [
                {
                    "role": "user",
                    "content": "Test",
                    "metadata": {"timestamp": "2025-10-30"},
                },
                {
                    "role": "assistant",
                    "content": "Response",
                    "tool_calls": [{"name": "search", "args": {}}],
                },
            ]
        }

        assert state["messages"] is not None
        assert len(state["messages"]) == 2
        assert "metadata" in state["messages"][0]
        assert "tool_calls" in state["messages"][1]


class TestAGUIRequest:
    """Test AGUIRequest Pydantic model."""

    def test_agui_request_minimal(self) -> None:
        """Test creating AGUIRequest with only required fields."""
        request = AGUIRequest(messages=[{"role": "user", "content": "Hello"}])

        assert len(request.messages) == 1
        assert request.messages[0]["content"] == "Hello"
        assert request.run_id is None
        assert request.thread_id is None
        assert request.state is None
        assert request.tools is None
        assert request.context is None
        assert request.forwarded_props is None
        assert request.parent_run_id is None

    def test_agui_request_all_fields(self) -> None:
        """Test creating AGUIRequest with all fields populated."""
        request = AGUIRequest(
            messages=[{"role": "user", "content": "Hello"}],
            run_id="run-123",
            thread_id="thread-456",
            state={"counter": 0},
            tools=[{"name": "search", "description": "Search tool"}],
            context=[{"type": "document", "content": "Some context"}],
            forwarded_props={"custom_key": "custom_value"},
            parent_run_id="parent-run-789",
        )

        assert request.run_id == "run-123"
        assert request.thread_id == "thread-456"
        assert request.state == {"counter": 0}
        assert request.tools == [{"name": "search", "description": "Search tool"}]
        assert request.context == [{"type": "document", "content": "Some context"}]
        assert request.forwarded_props == {"custom_key": "custom_value"}
        assert request.parent_run_id == "parent-run-789"

    def test_agui_request_model_dump_excludes_none(self) -> None:
        """Test that model_dump(exclude_none=True) excludes None fields."""
        request = AGUIRequest(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"name": "my_tool"}],
            context=[{"id": "ctx1"}],
        )

        dumped = request.model_dump(exclude_none=True)

        assert "messages" in dumped
        assert "tools" in dumped
        assert "context" in dumped
        assert "run_id" not in dumped
        assert "thread_id" not in dumped
        assert "state" not in dumped
        assert "forwarded_props" not in dumped
        assert "parent_run_id" not in dumped

    def test_agui_request_model_dump_includes_all_set_fields(self) -> None:
        """Test that model_dump preserves all explicitly set fields.

        This is critical for the fix - ensuring tools, context, forwarded_props,
        and parent_run_id are not stripped during request validation.
        """
        request = AGUIRequest(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"name": "client_tool", "parameters": {"type": "object"}}],
            context=[{"type": "snippet", "content": "code here"}],
            forwarded_props={"auth_token": "secret", "user_id": "user-1"},
            parent_run_id="parent-456",
        )

        dumped = request.model_dump(exclude_none=True)

        # Verify all fields are preserved (the main bug fix)
        assert dumped["tools"] == [{"name": "client_tool", "parameters": {"type": "object"}}]
        assert dumped["context"] == [{"type": "snippet", "content": "code here"}]
        assert dumped["forwarded_props"] == {"auth_token": "secret", "user_id": "user-1"}
        assert dumped["parent_run_id"] == "parent-456"
