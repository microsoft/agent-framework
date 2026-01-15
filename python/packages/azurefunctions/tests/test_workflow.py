# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for workflow orchestration functions."""

import json
from dataclasses import dataclass
from typing import Any

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
    ChatMessage,
)
from agent_framework._workflows._edge import (
    FanInEdgeGroup,
    FanOutEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
    SwitchCaseEdgeGroupCase,
    SwitchCaseEdgeGroupDefault,
)

from agent_framework_azurefunctions._workflow import (
    _extract_message_content,
    _extract_message_content_from_dict,
    build_agent_executor_response,
    route_message_through_edge_groups,
)


class TestRouteMessageThroughEdgeGroups:
    """Test suite for route_message_through_edge_groups function."""

    def test_single_edge_group_routes_when_condition_matches(self) -> None:
        """Test SingleEdgeGroup routes when condition is satisfied."""
        group = SingleEdgeGroup(source_id="src", target_id="tgt", condition=lambda m: True)

        targets = route_message_through_edge_groups([group], "src", "any message")

        assert targets == ["tgt"]

    def test_single_edge_group_does_not_route_when_condition_fails(self) -> None:
        """Test SingleEdgeGroup does not route when condition fails."""
        group = SingleEdgeGroup(source_id="src", target_id="tgt", condition=lambda m: False)

        targets = route_message_through_edge_groups([group], "src", "any message")

        assert targets == []

    def test_single_edge_group_ignores_different_source(self) -> None:
        """Test SingleEdgeGroup ignores messages from different sources."""
        group = SingleEdgeGroup(source_id="src", target_id="tgt", condition=lambda m: True)

        targets = route_message_through_edge_groups([group], "other_src", "any message")

        assert targets == []

    def test_switch_case_with_selection_func(self) -> None:
        """Test SwitchCaseEdgeGroup uses selection_func."""

        def select_first_target(msg: Any, targets: list[str]) -> list[str]:
            return [targets[0]]

        group = SwitchCaseEdgeGroup(
            source_id="src",
            cases=[
                SwitchCaseEdgeGroupCase(condition=lambda m: True, target_id="target_a"),
                SwitchCaseEdgeGroupDefault(target_id="target_b"),
            ],
        )
        # Manually set the selection function
        group._selection_func = select_first_target

        targets = route_message_through_edge_groups([group], "src", "test")

        assert targets == ["target_a"]

    def test_switch_case_without_selection_func_broadcasts(self) -> None:
        """Test SwitchCaseEdgeGroup without selection_func broadcasts to all."""
        group = SwitchCaseEdgeGroup(
            source_id="src",
            cases=[
                SwitchCaseEdgeGroupCase(condition=lambda m: True, target_id="target_a"),
                SwitchCaseEdgeGroupDefault(target_id="target_b"),
            ],
        )
        group._selection_func = None

        targets = route_message_through_edge_groups([group], "src", "test")

        assert set(targets) == {"target_a", "target_b"}

    def test_fan_out_with_selection_func(self) -> None:
        """Test FanOutEdgeGroup uses selection_func."""

        def select_all(msg: Any, targets: list[str]) -> list[str]:
            return targets

        group = FanOutEdgeGroup(
            source_id="src",
            target_ids=["fan_a", "fan_b", "fan_c"],
            selection_func=select_all,
        )

        targets = route_message_through_edge_groups([group], "src", "broadcast")

        assert set(targets) == {"fan_a", "fan_b", "fan_c"}

    def test_fan_in_is_not_routed_directly(self) -> None:
        """Test FanInEdgeGroup is handled separately (not routed here)."""
        group = FanInEdgeGroup(
            source_ids=["src_a", "src_b"],
            target_id="aggregator",
        )

        # Fan-in should not add targets through this function
        targets = route_message_through_edge_groups([group], "src_a", "message")

        assert targets == []

    def test_multiple_edge_groups_aggregated(self) -> None:
        """Test that targets from multiple edge groups are aggregated."""
        group1 = SingleEdgeGroup(source_id="src", target_id="t1", condition=lambda m: True)
        group2 = SingleEdgeGroup(source_id="src", target_id="t2", condition=lambda m: True)

        targets = route_message_through_edge_groups([group1, group2], "src", "msg")

        assert set(targets) == {"t1", "t2"}


class TestBuildAgentExecutorResponse:
    """Test suite for build_agent_executor_response function."""

    def test_builds_response_with_text(self) -> None:
        """Test building response with plain text."""
        response = build_agent_executor_response(
            executor_id="my_executor",
            response_text="Hello, world!",
            structured_response=None,
            previous_message="User input",
        )

        assert response.executor_id == "my_executor"
        assert response.agent_run_response.text == "Hello, world!"
        assert len(response.full_conversation) == 2  # User + Assistant

    def test_builds_response_with_structured_response(self) -> None:
        """Test building response with structured JSON response."""
        structured = {"answer": 42, "reason": "because"}

        response = build_agent_executor_response(
            executor_id="calc",
            response_text="Original text",
            structured_response=structured,
            previous_message="Calculate",
        )

        # Structured response overrides text
        assert response.agent_run_response.text == json.dumps(structured)

    def test_conversation_includes_previous_string_message(self) -> None:
        """Test that string previous_message is included in conversation."""
        response = build_agent_executor_response(
            executor_id="exec",
            response_text="Response",
            structured_response=None,
            previous_message="User said this",
        )

        assert len(response.full_conversation) == 2
        assert response.full_conversation[0].role.value == "user"
        assert response.full_conversation[0].text == "User said this"
        assert response.full_conversation[1].role.value == "assistant"

    def test_conversation_extends_previous_agent_executor_response(self) -> None:
        """Test that previous AgentExecutorResponse's conversation is extended."""
        # Create a previous response with conversation history
        previous = AgentExecutorResponse(
            executor_id="prev",
            agent_run_response=AgentRunResponse(messages=[ChatMessage(role="assistant", text="Previous")]),
            full_conversation=[
                ChatMessage(role="user", text="First"),
                ChatMessage(role="assistant", text="Previous"),
            ],
        )

        response = build_agent_executor_response(
            executor_id="current",
            response_text="Current response",
            structured_response=None,
            previous_message=previous,
        )

        # Should have 3 messages: First + Previous + Current
        assert len(response.full_conversation) == 3
        assert response.full_conversation[0].text == "First"
        assert response.full_conversation[1].text == "Previous"
        assert response.full_conversation[2].text == "Current response"


class TestExtractMessageContent:
    """Test suite for _extract_message_content function."""

    def test_extract_from_string(self) -> None:
        """Test extracting content from plain string."""
        result = _extract_message_content("Hello, world!")

        assert result == "Hello, world!"

    def test_extract_from_agent_executor_response_with_text(self) -> None:
        """Test extracting from AgentExecutorResponse with text."""
        response = AgentExecutorResponse(
            executor_id="exec",
            agent_run_response=AgentRunResponse(messages=[ChatMessage(role="assistant", text="Response text")]),
        )

        result = _extract_message_content(response)

        assert result == "Response text"

    def test_extract_from_agent_executor_response_with_messages(self) -> None:
        """Test extracting from AgentExecutorResponse with messages."""
        response = AgentExecutorResponse(
            executor_id="exec",
            agent_run_response=AgentRunResponse(
                messages=[
                    ChatMessage(role="user", text="First"),
                    ChatMessage(role="assistant", text="Last message"),
                ]
            ),
        )

        result = _extract_message_content(response)

        # AgentRunResponse.text concatenates all message texts
        assert result == "FirstLast message"

    def test_extract_from_agent_executor_request(self) -> None:
        """Test extracting from AgentExecutorRequest."""
        request = AgentExecutorRequest(
            messages=[
                ChatMessage(role="user", text="First"),
                ChatMessage(role="user", text="Last request"),
            ]
        )

        result = _extract_message_content(request)

        assert result == "Last request"

    def test_extract_from_dict_agent_executor_request(self) -> None:
        """Test extracting from serialized AgentExecutorRequest dict."""
        msg_dict = {
            "messages": [
                {
                    "type": "chat_message",
                    "contents": [{"type": "text", "text": "Hello from dict"}],
                }
            ]
        }

        result = _extract_message_content(msg_dict)

        assert result == "Hello from dict"

    def test_extract_returns_empty_for_unknown_type(self) -> None:
        """Test that unknown types return empty string."""
        result = _extract_message_content(12345)

        assert result == ""


class TestExtractMessageContentFromDict:
    """Test suite for _extract_message_content_from_dict function."""

    def test_extract_from_messages_with_contents(self) -> None:
        """Test extracting from messages with contents structure."""
        msg_dict = {"messages": [{"contents": [{"type": "text", "text": "Content text"}]}]}

        result = _extract_message_content_from_dict(msg_dict)

        assert result == "Content text"

    def test_extract_from_messages_with_direct_text(self) -> None:
        """Test extracting from messages with direct text field."""
        msg_dict = {"messages": [{"text": "Direct text"}]}

        result = _extract_message_content_from_dict(msg_dict)

        assert result == "Direct text"

    def test_extract_from_agent_run_response(self) -> None:
        """Test extracting from agent_run_response dict."""
        msg_dict = {"agent_run_response": {"text": "Response text"}}

        result = _extract_message_content_from_dict(msg_dict)

        assert result == "Response text"

    def test_extract_from_agent_run_response_with_messages(self) -> None:
        """Test extracting from agent_run_response with messages."""
        msg_dict = {"agent_run_response": {"messages": [{"contents": [{"type": "text", "text": "Nested content"}]}]}}

        result = _extract_message_content_from_dict(msg_dict)

        assert result == "Nested content"

    def test_extract_returns_empty_for_empty_dict(self) -> None:
        """Test that empty dict returns empty string."""
        result = _extract_message_content_from_dict({})

        assert result == ""

    def test_extract_returns_empty_for_empty_messages(self) -> None:
        """Test that empty messages list returns empty string."""
        result = _extract_message_content_from_dict({"messages": []})

        assert result == ""


class TestEdgeGroupIntegration:
    """Integration tests for edge group routing with realistic scenarios."""

    def test_conditional_routing_by_message_type(self) -> None:
        """Test routing based on message content/type."""

        @dataclass
        class SpamResult:
            is_spam: bool
            reason: str

        def is_spam_condition(msg: Any) -> bool:
            if isinstance(msg, SpamResult):
                return msg.is_spam
            return False

        def is_not_spam_condition(msg: Any) -> bool:
            if isinstance(msg, SpamResult):
                return not msg.is_spam
            return False

        spam_group = SingleEdgeGroup(
            source_id="detector",
            target_id="spam_handler",
            condition=is_spam_condition,
        )
        legit_group = SingleEdgeGroup(
            source_id="detector",
            target_id="email_handler",
            condition=is_not_spam_condition,
        )

        # Test spam message
        spam_msg = SpamResult(is_spam=True, reason="Suspicious content")
        targets = route_message_through_edge_groups([spam_group, legit_group], "detector", spam_msg)
        assert targets == ["spam_handler"]

        # Test legitimate message
        legit_msg = SpamResult(is_spam=False, reason="Clean")
        targets = route_message_through_edge_groups([spam_group, legit_group], "detector", legit_msg)
        assert targets == ["email_handler"]

    def test_fan_out_to_multiple_workers(self) -> None:
        """Test fan-out to multiple parallel workers."""

        def select_all_workers(msg: Any, targets: list[str]) -> list[str]:
            return targets

        group = FanOutEdgeGroup(
            source_id="coordinator",
            target_ids=["worker_1", "worker_2", "worker_3"],
            selection_func=select_all_workers,
        )

        targets = route_message_through_edge_groups([group], "coordinator", {"task": "process"})

        assert len(targets) == 3
        assert set(targets) == {"worker_1", "worker_2", "worker_3"}
