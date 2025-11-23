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

    def test_agui_request_creation_with_defaults(self) -> None:
        """Test creating AGUIRequest with default values."""
        request = AGUIRequest()

        assert request.messages == []
        assert request.run_id is None
        assert request.thread_id is None
        assert request.state is None

    def test_agui_request_with_messages(self) -> None:
        """Test AGUIRequest with messages."""
        request = AGUIRequest(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ]
        )

        assert len(request.messages) == 2
        assert request.messages[0]["role"] == "user"
        assert request.messages[1]["role"] == "assistant"

    def test_agui_request_with_all_fields(self) -> None:
        """Test AGUIRequest with all fields populated."""
        request = AGUIRequest(
            messages=[{"role": "user", "content": "Test"}],
            run_id="run-123",
            thread_id="thread-456",
            state={"document": "Hello world"},
        )

        assert len(request.messages) == 1
        assert request.run_id == "run-123"
        assert request.thread_id == "thread-456"
        assert request.state == {"document": "Hello world"}

    def test_agui_request_model_dump(self) -> None:
        """Test AGUIRequest model_dump method."""
        request = AGUIRequest(
            messages=[{"role": "user", "content": "Test"}],
            run_id="run-123",
        )

        data = request.model_dump()
        assert "messages" in data
        assert "run_id" in data
        assert "thread_id" in data
        assert "state" in data

    def test_agui_request_model_dump_exclude_none(self) -> None:
        """Test AGUIRequest model_dump with exclude_none."""
        request = AGUIRequest(
            messages=[{"role": "user", "content": "Test"}],
            run_id="run-123",
        )

        data = request.model_dump(exclude_none=True)
        assert "messages" in data
        assert "run_id" in data
        assert "thread_id" not in data
        assert "state" not in data

    def test_agui_request_allows_extra_fields(self) -> None:
        """Test AGUIRequest allows extra fields."""
        request = AGUIRequest(
            messages=[],
            custom_field="custom_value",
        )

        data = request.model_dump()
        assert data["custom_field"] == "custom_value"

    def test_agui_request_from_dict(self) -> None:
        """Test creating AGUIRequest from dict."""
        data = {
            "messages": [{"role": "user", "content": "Hello"}],
            "run_id": "run-789",
            "thread_id": "thread-012",
            "state": {"key": "value"},
        }

        request = AGUIRequest(**data)

        assert len(request.messages) == 1
        assert request.run_id == "run-789"
        assert request.thread_id == "thread-012"
        assert request.state == {"key": "value"}

    def test_agui_request_json_schema(self) -> None:
        """Test AGUIRequest generates proper JSON schema."""
        schema = AGUIRequest.model_json_schema()

        assert "properties" in schema
        assert "messages" in schema["properties"]
        assert "run_id" in schema["properties"]
        assert "thread_id" in schema["properties"]
        assert "state" in schema["properties"]

        # Verify descriptions are present
        assert "description" in schema["properties"]["messages"]
        assert "description" in schema["properties"]["run_id"]
