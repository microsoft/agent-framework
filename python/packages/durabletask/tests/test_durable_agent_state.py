# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAgentState and related classes."""

import json
from datetime import datetime

import pytest
from agent_framework import Content, Message, UsageDetails

from agent_framework_durabletask._durable_agent_state import (
    DurableAgentState,
    DurableAgentStateContent,
    DurableAgentStateFunctionCallContent,
    DurableAgentStateMessage,
    DurableAgentStateRequest,
    DurableAgentStateTextContent,
    DurableAgentStateUnknownContent,
    DurableAgentStateUsage,
)
from agent_framework_durabletask._models import RunRequest


class TestDurableAgentStateRequestOrchestrationId:
    """Test suite for DurableAgentStateRequest orchestration_id field."""

    def test_request_with_orchestration_id(self) -> None:
        """Test creating a request with an orchestration_id."""
        request = DurableAgentStateRequest(
            correlation_id="corr-123",
            created_at=datetime.now(),
            messages=[
                DurableAgentStateMessage(
                    role="user",
                    contents=[DurableAgentStateTextContent(text="test")],
                )
            ],
            orchestration_id="orch-456",
        )

        assert request.orchestration_id == "orch-456"

    def test_request_to_dict_includes_orchestration_id(self) -> None:
        """Test that to_dict includes orchestrationId when set."""
        request = DurableAgentStateRequest(
            correlation_id="corr-123",
            created_at=datetime.now(),
            messages=[
                DurableAgentStateMessage(
                    role="user",
                    contents=[DurableAgentStateTextContent(text="test")],
                )
            ],
            orchestration_id="orch-789",
        )

        data = request.to_dict()

        assert "orchestrationId" in data
        assert data["orchestrationId"] == "orch-789"

    def test_request_to_dict_excludes_orchestration_id_when_none(self) -> None:
        """Test that to_dict excludes orchestrationId when not set."""
        request = DurableAgentStateRequest(
            correlation_id="corr-123",
            created_at=datetime.now(),
            messages=[
                DurableAgentStateMessage(
                    role="user",
                    contents=[DurableAgentStateTextContent(text="test")],
                )
            ],
        )

        data = request.to_dict()

        assert "orchestrationId" not in data

    def test_request_from_dict_with_orchestration_id(self) -> None:
        """Test from_dict correctly parses orchestrationId."""
        data = {
            "$type": "request",
            "correlationId": "corr-123",
            "createdAt": "2024-01-01T00:00:00Z",
            "messages": [{"role": "user", "contents": [{"$type": "text", "text": "test"}]}],
            "orchestrationId": "orch-from-dict",
        }

        request = DurableAgentStateRequest.from_dict(data)

        assert request.orchestration_id == "orch-from-dict"

    def test_request_from_run_request_with_orchestration_id(self) -> None:
        """Test from_run_request correctly transfers orchestration_id."""
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
            orchestration_id="orch-from-run-request",
        )

        durable_request = DurableAgentStateRequest.from_run_request(run_request)

        assert durable_request.orchestration_id == "orch-from-run-request"

    def test_request_from_run_request_without_orchestration_id(self) -> None:
        """Test from_run_request correctly handles missing orchestration_id."""
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
        )

        durable_request = DurableAgentStateRequest.from_run_request(run_request)

        assert durable_request.orchestration_id is None


class TestDurableAgentStateMessageCreatedAt:
    """Test suite for DurableAgentStateMessage created_at field handling."""

    def test_message_from_run_request_without_created_at_preserves_none(self) -> None:
        """Test from_run_request handles auto-populated created_at from RunRequest.

        When a RunRequest is created with None for created_at, RunRequest defaults it to
        current UTC time. The resulting DurableAgentStateMessage should have this timestamp.
        """
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
            created_at=None,  # RunRequest will default this to current time
        )

        durable_message = DurableAgentStateMessage.from_run_request(run_request)

        # RunRequest auto-populates created_at, so it should not be None
        assert durable_message.created_at is not None

    def test_message_from_run_request_with_created_at_parses_correctly(self) -> None:
        """Test from_run_request correctly parses a valid created_at timestamp."""
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
            created_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        durable_message = DurableAgentStateMessage.from_run_request(run_request)

        assert durable_message.created_at is not None
        assert durable_message.created_at.year == 2024
        assert durable_message.created_at.month == 1
        assert durable_message.created_at.day == 15


class TestDurableAgentState:
    """Test suite for DurableAgentState."""

    def test_schema_version(self) -> None:
        """Test that schema version is set correctly."""
        state = DurableAgentState()
        assert state.schema_version == "1.1.0"

    def test_to_dict_serialization(self) -> None:
        """Test that to_dict produces correct structure."""
        state = DurableAgentState()
        data = state.to_dict()

        assert "schemaVersion" in data
        assert "data" in data
        assert data["schemaVersion"] == "1.1.0"
        assert "conversationHistory" in data["data"]

    def test_from_dict_deserialization(self) -> None:
        """Test that from_dict restores state correctly."""
        original_data = {
            "schemaVersion": "1.1.0",
            "data": {
                "conversationHistory": [
                    {
                        "$type": "request",
                        "correlationId": "test-123",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "messages": [
                            {
                                "role": "user",
                                "contents": [{"$type": "text", "text": "Hello"}],
                            }
                        ],
                    }
                ]
            },
        }

        state = DurableAgentState.from_dict(original_data)

        assert state.schema_version == "1.1.0"
        assert len(state.data.conversation_history) == 1
        assert isinstance(state.data.conversation_history[0], DurableAgentStateRequest)

    def test_round_trip_serialization(self) -> None:
        """Test that round-trip serialization preserves data."""
        state = DurableAgentState()
        state.data.conversation_history.append(
            DurableAgentStateRequest(
                correlation_id="test-456",
                created_at=datetime.now(),
                messages=[
                    DurableAgentStateMessage(
                        role="user",
                        contents=[DurableAgentStateTextContent(text="Test message")],
                    )
                ],
            )
        )

        data = state.to_dict()
        restored = DurableAgentState.from_dict(data)

        assert restored.schema_version == state.schema_version
        assert len(restored.data.conversation_history) == len(state.data.conversation_history)
        assert restored.data.conversation_history[0].correlation_id == "test-456"

    def test_function_call_round_trip_preserves_string_arguments(self) -> None:
        """Function call arguments should remain strings across durable state replay."""
        original = Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id="call-123",
                    name="get_weather",
                    arguments='{"location":"Chicago"}',
                )
            ],
        )

        durable_message = DurableAgentStateMessage.from_chat_message(original)
        restored = durable_message.to_chat_message()

        assert restored.contents[0].type == "function_call"
        assert restored.contents[0].arguments == '{"location": "Chicago"}'

    def test_function_call_content_supports_legacy_mapping_arguments(self) -> None:
        """Existing persisted mapping arguments should still restore successfully."""
        content = DurableAgentStateFunctionCallContent(
            call_id="call-123",
            name="get_weather",
            arguments={"location": "Chicago"},
        )

        restored = content.to_ai_content()

        assert restored.type == "function_call"
        assert restored.arguments == '{"location": "Chicago"}'


class TestDurableAgentStateUsage:
    """Test suite for DurableAgentStateUsage."""

    def test_usage_init_with_defaults(self) -> None:
        """Test creating usage with default values."""
        usage = DurableAgentStateUsage()

        assert usage.input_token_count is None
        assert usage.output_token_count is None
        assert usage.total_token_count is None
        assert usage.extensionData is None

    def test_usage_init_with_values(self) -> None:
        """Test creating usage with specific values."""
        usage = DurableAgentStateUsage(
            input_token_count=100,
            output_token_count=200,
            total_token_count=300,
            extensionData={"custom_field": "value"},
        )

        assert usage.input_token_count == 100
        assert usage.output_token_count == 200
        assert usage.total_token_count == 300
        assert usage.extensionData == {"custom_field": "value"}

    def test_usage_to_dict(self) -> None:
        """Test that to_dict produces correct structure."""
        usage = DurableAgentStateUsage(
            input_token_count=50,
            output_token_count=75,
            total_token_count=125,
        )

        data = usage.to_dict()

        assert data["inputTokenCount"] == 50
        assert data["outputTokenCount"] == 75
        assert data["totalTokenCount"] == 125

    def test_usage_to_dict_with_extension_data(self) -> None:
        """Test that to_dict includes extensionData when present."""
        usage = DurableAgentStateUsage(
            input_token_count=10,
            output_token_count=20,
            total_token_count=30,
            extensionData={"provider_specific": 123},
        )

        data = usage.to_dict()

        assert "extensionData" in data
        assert data["extensionData"] == {"provider_specific": 123}

    def test_usage_from_dict(self) -> None:
        """Test that from_dict restores usage correctly."""
        data = {
            "inputTokenCount": 100,
            "outputTokenCount": 200,
            "totalTokenCount": 300,
            "extensionData": {"extra": "data"},
        }

        usage = DurableAgentStateUsage.from_dict(data)

        assert usage.input_token_count == 100
        assert usage.output_token_count == 200
        assert usage.total_token_count == 300
        assert usage.extensionData == {"extra": "data"}

    def test_usage_from_usage_details(self) -> None:
        """Test creating DurableAgentStateUsage from UsageDetails."""
        usage_details: UsageDetails = {
            "input_token_count": 150,
            "output_token_count": 250,
            "total_token_count": 400,
        }

        usage = DurableAgentStateUsage.from_usage(usage_details)

        assert usage is not None
        assert usage.input_token_count == 150
        assert usage.output_token_count == 250
        assert usage.total_token_count == 400

    def test_usage_from_usage_details_with_extension_fields(self) -> None:
        """Test that non-standard fields are captured in extensionData."""
        usage_details: UsageDetails = {
            "input_token_count": 100,
            "output_token_count": 200,
            "total_token_count": 300,
        }
        # Add provider-specific fields (UsageDetails is a TypedDict but allows extra keys)
        usage_details["prompt_tokens"] = 100  # type: ignore[typeddict-unknown-key]
        usage_details["completion_tokens"] = 200  # type: ignore[typeddict-unknown-key]

        usage = DurableAgentStateUsage.from_usage(usage_details)

        assert usage is not None
        assert usage.extensionData is not None
        assert usage.extensionData["prompt_tokens"] == 100
        assert usage.extensionData["completion_tokens"] == 200

    def test_usage_from_usage_none(self) -> None:
        """Test that from_usage returns None for None input."""
        usage = DurableAgentStateUsage.from_usage(None)

        assert usage is None

    def test_usage_to_usage_details(self) -> None:
        """Test converting back to UsageDetails."""
        usage = DurableAgentStateUsage(
            input_token_count=100,
            output_token_count=200,
            total_token_count=300,
        )

        details = usage.to_usage_details()

        assert details.get("input_token_count") == 100
        assert details.get("output_token_count") == 200
        assert details.get("total_token_count") == 300

    def test_usage_to_usage_details_with_extension_data(self) -> None:
        """Test that extensionData is merged into UsageDetails."""
        usage = DurableAgentStateUsage(
            input_token_count=50,
            output_token_count=75,
            total_token_count=125,
            extensionData={"prompt_tokens": 50, "completion_tokens": 75},
        )

        details = usage.to_usage_details()

        assert details.get("input_token_count") == 50
        assert details.get("output_token_count") == 75
        assert details.get("total_token_count") == 125
        # Extension data should be merged into the result
        assert details.get("prompt_tokens") == 50
        assert details.get("completion_tokens") == 75

    def test_usage_round_trip(self) -> None:
        """Test round-trip conversion from UsageDetails to DurableAgentStateUsage and back."""
        original: UsageDetails = {
            "input_token_count": 100,
            "output_token_count": 200,
            "total_token_count": 300,
        }

        usage = DurableAgentStateUsage.from_usage(original)
        assert usage is not None
        restored = usage.to_usage_details()

        assert restored.get("input_token_count") == original.get("input_token_count")
        assert restored.get("output_token_count") == original.get("output_token_count")
        assert restored.get("total_token_count") == original.get("total_token_count")


class TestDurableAgentStateUnknownContent:
    """Test suite for DurableAgentStateUnknownContent serialization."""

    def test_unknown_content_from_content_object_produces_serializable_dict(self) -> None:
        """Test that from_unknown_content serializes Content objects to dicts."""
        content = Content.from_mcp_server_tool_call(
            call_id="call-1",
            tool_name="search",
            server_name="learn-mcp",
            arguments={"query": "azure functions"},
        )

        unknown = DurableAgentStateUnknownContent.from_unknown_content(content)
        result = unknown.to_dict()

        # The content field should be a dict, not a Content object
        assert isinstance(result["content"], dict)
        assert result["content"]["type"] == "mcp_server_tool_call"

    def test_unknown_content_to_dict_is_json_serializable(self) -> None:
        """Test that to_dict output can be passed to json.dumps without error."""
        content = Content.from_mcp_server_tool_result(
            call_id="call-1",
            output="Azure Functions documentation...",
        )

        unknown = DurableAgentStateUnknownContent.from_unknown_content(content)
        result = unknown.to_dict()

        # This must not raise TypeError
        serialized = json.dumps(result)
        assert serialized is not None

    def test_unknown_content_round_trip_preserves_content(self) -> None:
        """Test that Content objects survive serialization and deserialization."""
        original = Content.from_mcp_server_tool_call(
            call_id="call-1",
            tool_name="fetch",
            server_name="learn-mcp",
            arguments={"url": "https://example.com"},
        )

        unknown = DurableAgentStateUnknownContent.from_unknown_content(original)
        restored = unknown.to_ai_content()

        assert restored.type == "mcp_server_tool_call"
        assert restored.tool_name == "fetch"
        assert restored.server_name == "learn-mcp"

    def test_unknown_content_from_plain_dict_unchanged(self) -> None:
        """Test that non-Content values are stored as-is."""
        plain = {"some": "data"}

        unknown = DurableAgentStateUnknownContent.from_unknown_content(plain)

        assert unknown.content == {"some": "data"}

    def test_unknown_content_to_ai_content_fallback_on_invalid_type_dict(self) -> None:
        """Test that to_ai_content falls back when dict has 'type' but is not valid Content."""
        invalid = {"type": "bogus_not_a_real_content_type", "extra": "stuff"}
        unknown = DurableAgentStateUnknownContent(content=invalid)

        result = unknown.to_ai_content()

        assert result.type == "unknown"
        assert result.additional_properties == {"content": invalid}

    def test_from_ai_content_unknown_type_produces_serializable_state(self) -> None:
        """Test that unknown content types in message conversion produce JSON-serializable state."""
        content = Content.from_mcp_server_tool_call(
            call_id="call-1",
            tool_name="search",
            server_name="learn-mcp",
            arguments={"query": "create function app"},
        )

        durable_content = DurableAgentStateContent.from_ai_content(content)
        data = durable_content.to_dict()

        # Must be fully JSON-serializable
        serialized = json.dumps(data)
        assert serialized is not None

    def test_state_with_mcp_content_is_json_serializable(self) -> None:
        """Test that full DurableAgentState with MCP content can be serialized to JSON.

        This reproduces the scenario from issue #4719 where agent state containing
        MCP tool content could not be serialized by Azure Durable Functions.
        """
        state = DurableAgentState()
        mcp_content = Content.from_mcp_server_tool_call(
            call_id="call-1",
            tool_name="search",
            server_name="learn-mcp",
            arguments={"query": "azure functions"},
        )
        message = DurableAgentStateMessage.from_chat_message(Message(role="assistant", contents=[mcp_content]))
        state.data.conversation_history.append(
            DurableAgentStateRequest(
                correlation_id="test-mcp",
                created_at=datetime.now(),
                messages=[message],
            )
        )

        state_dict = state.to_dict()

        # This simulates what Azure Durable Functions does with entity state
        serialized = json.dumps(state_dict)
        assert serialized is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
