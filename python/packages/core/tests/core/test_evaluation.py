# Copyright (c) Microsoft. All rights reserved.

"""Tests for provider-neutral evaluation item construction and splitting."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from agent_framework import AgentEvalConverter as ExportedAgentEvalConverter
from agent_framework._evaluation import AgentEvalConverter, ConversationSplit, EvalItem, _to_eval_item
from agent_framework._tools import FunctionTool
from agent_framework._types import AgentResponse, Content, Message


class TestAgentEvalConverterCompatibility:
    def test_root_export_is_legacy_converter(self) -> None:
        assert ExportedAgentEvalConverter is AgentEvalConverter

    def test_convert_messages_preserves_legacy_foundry_wire_format(self) -> None:
        messages = [
            Message("user", ["What's the weather?"]),
            Message(
                "assistant",
                [Content.from_function_call(call_id="call_1", name="get_weather", arguments={"city": "Seattle"})],
            ),
        ]

        with pytest.warns(DeprecationWarning, match="AgentEvalConverter"):
            converted = AgentEvalConverter.convert_messages(messages)

        assert converted == [
            {"role": "user", "content": [{"type": "text", "text": "What's the weather?"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_call",
                        "tool_call_id": "call_1",
                        "name": "get_weather",
                        "arguments": {"city": "Seattle"},
                    }
                ],
            },
        ]

    def test_to_eval_item_delegates_to_provider_neutral_builder(self) -> None:
        response = AgentResponse(messages=[Message("assistant", ["Sunny."])])

        with pytest.warns(DeprecationWarning, match="AgentEvalConverter"):
            item = AgentEvalConverter.to_eval_item(query="Weather?", response=response)

        assert item.query == "Weather?"
        assert item.response == "Sunny."


class TestToEvalItem:
    def test_string_query(self) -> None:
        response = AgentResponse(messages=[Message("assistant", ["The weather is sunny."])])
        item = _to_eval_item(query="What's the weather?", response=response)

        assert item.query == "What's the weather?"
        assert item.response == "The weather is sunny."
        assert [message.role for message in item.conversation] == ["user", "assistant"]

    def test_message_query(self) -> None:
        input_messages = [
            Message("system", ["Be helpful."]),
            Message("user", ["Hello"]),
        ]
        response = AgentResponse(messages=[Message("assistant", ["Hi there!"])])

        item = _to_eval_item(query=input_messages, response=response)

        assert item.query == "Hello"
        assert len(item.conversation) == 3

    def test_with_context(self) -> None:
        response = AgentResponse(messages=[Message("assistant", ["Answer."])])

        item = _to_eval_item(
            query="Question?",
            response=response,
            context="Some reference document.",
        )

        assert item.context == "Some reference document."

    def test_with_explicit_tools(self) -> None:
        def search(query: str) -> str:
            """Search the web."""
            return f"Results for {query}"

        response = AgentResponse(messages=[Message("assistant", ["Found it."])])

        item = _to_eval_item(query="Find info", response=response, tools=[search])

        assert item.tools is not None
        assert len(item.tools) == 1
        assert item.tools[0].name == "search"

    def test_with_agent_and_mcp_tools(self) -> None:
        agent_tool = FunctionTool(name="calculate", description="Calculate", func=lambda value: str(value))
        mcp_tool = FunctionTool(name="search", description="Search", func=lambda query: query)
        agent = MagicMock()
        agent.default_options = {"tools": [agent_tool]}
        agent.mcp_tools = [MagicMock(functions=[agent_tool, mcp_tool])]
        response = AgentResponse(messages=[Message("assistant", ["Done"])])

        item = _to_eval_item(query="Research this", response=response, agent=agent)

        assert item.tools == [agent_tool, mcp_tool]

    def test_explicit_tools_override_agent(self) -> None:
        agent_tool = FunctionTool(name="agent_tool", description="from agent", func=lambda: "")
        explicit_tool = FunctionTool(name="explicit_tool", description="explicit", func=lambda: "")
        agent = MagicMock()
        agent.default_options = {"tools": [agent_tool]}
        response = AgentResponse(messages=[Message("assistant", ["Done"])])

        item = _to_eval_item(
            query="Test",
            response=response,
            agent=agent,
            tools=[explicit_tool],
        )

        assert item.tools == [explicit_tool]


class TestEvalItemSplitting:
    def test_split_messages_format(self) -> None:
        tool = FunctionTool(name="test", description="Test", func=lambda: "")
        item = _to_eval_item(
            query="Q",
            response=AgentResponse(messages=[Message("assistant", ["Answer"])]),
            tools=[tool],
        )

        query_messages, response_messages = item.split_messages()

        assert [message.role for message in query_messages] == ["user"]
        assert [message.role for message in response_messages] == ["assistant"]
        assert item.tools == [tool]

    def test_multiturn_preserves_interleaving(self) -> None:
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's sunny in Seattle."]),
            Message("user", ["And tomorrow?"]),
            Message("assistant", [Content(type="function_call", name="get_forecast")]),
            Message("tool", [Content(type="function_result", result="Rain expected")]),
            Message("assistant", ["Rain is expected tomorrow."]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages()

        assert [message.role for message in query_messages] == ["user", "assistant", "user"]
        assert [message.role for message in response_messages] == ["assistant", "tool", "assistant"]

    def test_full_split(self) -> None:
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's 62°F in Seattle."]),
            Message("user", ["And tomorrow?"]),
            Message("assistant", ["Rain is expected tomorrow."]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, ConversationSplit.FULL)
        )

        assert [message.text for message in query_messages] == ["What's the weather?"]
        assert [message.role for message in response_messages] == ["assistant", "user", "assistant"]

    def test_full_split_includes_system_message(self) -> None:
        conversation = [
            Message("system", ["You are a weather assistant."]),
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's sunny."]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, ConversationSplit.FULL)
        )

        assert [message.role for message in query_messages] == ["system", "user"]
        assert [message.role for message in response_messages] == ["assistant"]

    def test_full_split_puts_tool_interactions_in_response(self) -> None:
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", [Content(type="function_call", name="get_weather")]),
            Message("tool", [Content(type="function_result", result="62°F")]),
            Message("assistant", ["It's 62°F."]),
            Message("user", ["Thanks!"]),
            Message("assistant", ["You're welcome!"]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, ConversationSplit.FULL)
        )

        assert len(query_messages) == 1
        assert len(response_messages) == 5

    def test_last_turn_is_default(self) -> None:
        conversation = [
            Message("user", ["Hello"]),
            Message("assistant", ["Hi there"]),
            Message("user", ["Bye"]),
            Message("assistant", ["Goodbye"]),
        ]
        item = EvalItem(conversation=conversation)

        default_query, default_response = item.split_messages()
        explicit_query, explicit_response = item.split_messages(split=cast(Any, ConversationSplit.LAST_TURN))

        assert default_query == explicit_query
        assert default_response == explicit_response

    def test_per_turn_items(self) -> None:
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's 62°F."]),
            Message("user", ["And tomorrow?"]),
            Message("assistant", ["Rain expected."]),
        ]

        items = EvalItem.per_turn_items(conversation)

        assert len(items) == 2
        assert (items[0].query, items[0].response) == ("What's the weather?", "It's 62°F.")
        assert (items[1].query, items[1].response) == ("What's the weather? And tomorrow?", "Rain expected.")
        assert [len(item.conversation) for item in items] == [2, 4]

    def test_per_turn_items_preserve_tools(self) -> None:
        conversation = [
            Message("user", ["Check weather"]),
            Message("assistant", [Content(type="function_call", name="get_weather")]),
            Message("tool", [Content(type="function_result", result="sunny")]),
            Message("assistant", ["It's sunny."]),
            Message("user", ["Thanks"]),
            Message("assistant", ["You're welcome!"]),
        ]
        tool = FunctionTool(name="get_weather", description="Get weather")

        items = EvalItem.per_turn_items(conversation, tools=[tool])

        assert len(items) == 2
        assert items[0].tools == [tool]
        assert items[0].response == "It's sunny."
        assert items[1].response == "You're welcome!"

    def test_per_turn_items_without_user_messages(self) -> None:
        assert EvalItem.per_turn_items([Message("assistant", ["Hello"])]) == []

    def test_per_turn_items_single_turn(self) -> None:
        items = EvalItem.per_turn_items([
            Message("user", ["Hi"]),
            Message("assistant", ["Hello!"]),
        ])

        assert len(items) == 1
        assert (items[0].query, items[0].response) == ("Hi", "Hello!")

    def test_custom_splitter_callable(self) -> None:
        conversation = [
            Message("user", ["Remember my name is Alice"]),
            Message("assistant", ["Got it, Alice!"]),
            Message("user", ["What's the capital of France?"]),
            Message("assistant", [Content(type="function_call", name="retrieve_memory", call_id="m1")]),
            Message("tool", [Content(type="function_result", call_id="m1", result="User name: Alice")]),
            Message("assistant", ["The capital of France is Paris, Alice!"]),
        ]

        def split_before_memory(messages: list[Message]) -> tuple[list[Message], list[Message]]:
            for index, message in enumerate(messages):
                if any(content.name == "retrieve_memory" for content in message.contents):
                    return messages[:index], messages[index:]
            return EvalItem._split_last_turn_static(messages)

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, split_before_memory)
        )

        assert len(query_messages) == 3
        assert query_messages[-1].role == "user"
        assert len(response_messages) == 3
        assert response_messages[0].role == "assistant"

    def test_custom_splitter_fallback(self) -> None:
        conversation = [
            Message("user", ["Hello"]),
            Message("assistant", ["Hi there!"]),
        ]

        def split_before_memory(messages: list[Message]) -> tuple[list[Message], list[Message]]:
            for index, message in enumerate(messages):
                if any(content.name == "retrieve_memory" for content in message.contents):
                    return messages[:index], messages[index:]
            return EvalItem._split_last_turn_static(messages)

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, split_before_memory)
        )

        assert [message.role for message in query_messages] == ["user"]
        assert [message.role for message in response_messages] == ["assistant"]

    def test_custom_splitter_lambda(self) -> None:
        conversation = [
            Message("user", ["A"]),
            Message("assistant", ["B"]),
            Message("user", ["C"]),
            Message("assistant", ["D"]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, lambda messages: (messages[:2], messages[2:]))
        )

        assert len(query_messages) == 2
        assert len(response_messages) == 2

    def test_item_split_strategy_is_default(self) -> None:
        conversation = [
            Message("user", ["First"]),
            Message("assistant", ["Response 1"]),
            Message("user", ["Second"]),
            Message("assistant", ["Response 2"]),
        ]
        item = EvalItem(conversation=conversation, split_strategy=cast(Any, ConversationSplit.FULL))

        query_messages, response_messages = item.split_messages()

        assert [message.text for message in query_messages] == ["First"]
        assert len(response_messages) == 3

    def test_explicit_split_overrides_item_strategy(self) -> None:
        conversation = [
            Message("user", ["First"]),
            Message("assistant", ["Response 1"]),
            Message("user", ["Second"]),
            Message("assistant", ["Response 2"]),
        ]
        item = EvalItem(conversation=conversation, split_strategy=cast(Any, ConversationSplit.FULL))

        query_messages, response_messages = item.split_messages(split=cast(Any, ConversationSplit.LAST_TURN))

        assert len(query_messages) == 3
        assert query_messages[-1].text == "Second"
        assert len(response_messages) == 1

    def test_no_split_defaults_to_last_turn(self) -> None:
        item = EvalItem(
            conversation=[
                Message("user", ["Hello"]),
                Message("assistant", ["Hi"]),
            ]
        )

        query_messages, _ = item.split_messages()

        assert item.split_strategy is None
        assert [message.role for message in query_messages] == ["user"]
