# Copyright (c) Microsoft. All rights reserved.

"""Tests for the AgentEvalConverter, FoundryEvals, and eval helper functions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import AgentExecutorResponse, AgentResponse, Content, FunctionTool, Message, WorkflowEvent
from agent_framework._evaluation import (
    AgentEvalConverter,
    ConversationSplit,
    EvalItem,
    EvalNotPassedError,
    EvalResults,
    _extract_agent_eval_data,
    _extract_overall_query,
    evaluate_agent,
    evaluate_workflow,
)
from agent_framework._workflows._workflow import WorkflowRunResult
from openai import AsyncOpenAI

from agent_framework_foundry._foundry_evals import (
    FoundryEvals,
    _build_item_schema,
    _build_testing_criteria,
    _extract_per_evaluator,
    _extract_result_counts,
    _filter_tool_evaluators,
    _resolve_default_evaluators,
    _resolve_evaluator,
    _resolve_openai_client,
)


class _AsyncPage:
    """Async-iterable mock for OpenAI SDK pagination pages."""

    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def __aiter__(self) -> _AsyncPage:
        self._iter = iter(self._items)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


def _make_tool(name: str) -> MagicMock:
    """Create a mock FunctionTool for use in tests."""
    t = MagicMock()
    t.name = name
    t.description = f"{name} tool"
    t.parameters = MagicMock(return_value={"type": "object"})
    return t


@dataclass
class _MockResultCounts:
    """Mock matching the OpenAI SDK ResultCounts Pydantic model shape."""

    passed: int = 0
    failed: int = 0
    errored: int = 0
    total: int = 0


def _rc(passed: int = 0, failed: int = 0, errored: int = 0) -> _MockResultCounts:
    """Shorthand to create a ResultCounts-compatible mock."""
    return _MockResultCounts(passed=passed, failed=failed, errored=errored, total=passed + failed + errored)


# ---------------------------------------------------------------------------
# _resolve_evaluator
# ---------------------------------------------------------------------------


class TestResolveEvaluator:
    def test_short_name(self) -> None:
        assert _resolve_evaluator("relevance") == "builtin.relevance"
        assert _resolve_evaluator("tool_call_accuracy") == "builtin.tool_call_accuracy"
        assert _resolve_evaluator("violence") == "builtin.violence"

    def test_already_qualified(self) -> None:
        assert _resolve_evaluator("builtin.relevance") == "builtin.relevance"
        assert _resolve_evaluator("builtin.custom") == "builtin.custom"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown evaluator 'bogus'"):
            _resolve_evaluator("bogus")


# ---------------------------------------------------------------------------
# AgentEvalConverter.convert_message
# ---------------------------------------------------------------------------


class TestConvertMessage:
    def test_user_text_message(self) -> None:
        msg = Message("user", ["Hello, world!"])
        result = AgentEvalConverter.convert_message(msg)
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": [{"type": "text", "text": "Hello, world!"}]}

    def test_system_message(self) -> None:
        msg = Message("system", ["You are helpful."])
        result = AgentEvalConverter.convert_message(msg)
        assert result[0] == {"role": "system", "content": [{"type": "text", "text": "You are helpful."}]}

    def test_assistant_text_message(self) -> None:
        msg = Message("assistant", ["Here is the answer."])
        result = AgentEvalConverter.convert_message(msg)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == [{"type": "text", "text": "Here is the answer."}]
        assert len(result[0]["content"]) == 1

    def test_assistant_with_tool_call(self) -> None:
        msg = Message(
            "assistant",
            [
                Content.from_function_call(
                    call_id="call_1",
                    name="get_weather",
                    arguments=json.dumps({"location": "Seattle"}),
                ),
            ],
        )
        result = AgentEvalConverter.convert_message(msg)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        tc = result[0]["content"][0]
        assert tc["type"] == "tool_call"
        assert tc["tool_call_id"] == "call_1"
        assert tc["name"] == "get_weather"
        assert tc["arguments"] == {"location": "Seattle"}

    def test_assistant_text_and_tool_call(self) -> None:
        msg = Message(
            "assistant",
            [
                Content.from_text("Let me check that."),
                Content.from_function_call(
                    call_id="call_2",
                    name="search",
                    arguments={"query": "flights"},
                ),
            ],
        )
        result = AgentEvalConverter.convert_message(msg)
        assert len(result) == 1
        assert result[0]["content"][0] == {"type": "text", "text": "Let me check that."}
        tc = result[0]["content"][1]
        assert tc["type"] == "tool_call"
        assert tc["arguments"] == {"query": "flights"}

    def test_tool_result_message(self) -> None:
        msg = Message(
            "tool",
            [
                Content.from_function_result(
                    call_id="call_1",
                    result="72°F, sunny",
                ),
            ],
        )
        result = AgentEvalConverter.convert_message(msg)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_1"
        assert result[0]["content"] == [{"type": "tool_result", "tool_result": "72°F, sunny"}]

    def test_multiple_tool_results(self) -> None:
        msg = Message(
            "tool",
            [
                Content.from_function_result(call_id="call_1", result="r1"),
                Content.from_function_result(call_id="call_2", result="r2"),
            ],
        )
        result = AgentEvalConverter.convert_message(msg)
        assert len(result) == 2
        assert result[0]["tool_call_id"] == "call_1"
        assert result[1]["tool_call_id"] == "call_2"

    def test_non_string_result_kept_as_object(self) -> None:
        msg = Message(
            "tool",
            [
                Content.from_function_result(
                    call_id="call_1",
                    result={"temp": 72, "unit": "F"},
                ),
            ],
        )
        result = AgentEvalConverter.convert_message(msg)
        tr = result[0]["content"][0]
        assert tr["type"] == "tool_result"
        assert tr["tool_result"] == {"temp": 72, "unit": "F"}

    def test_empty_message(self) -> None:
        msg = Message("user", [])
        result = AgentEvalConverter.convert_message(msg)
        assert result[0] == {"role": "user", "content": [{"type": "text", "text": ""}]}

    def test_user_image_from_data(self) -> None:
        """Image created via Content.from_data() emits input_image."""
        img = Content.from_data(data=b"\x89PNG\r\n\x1a\n", media_type="image/png")
        msg = Message("user", [img])
        result = AgentEvalConverter.convert_message(msg)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        part = result[0]["content"][0]
        assert part["type"] == "input_image"
        assert part["image_url"].startswith("data:image/png;base64,")
        assert part["detail"] == "auto"

    def test_user_image_from_uri(self) -> None:
        """Image created via Content.from_uri() with an external URL."""
        img = Content.from_uri("https://example.com/photo.jpg", media_type="image/jpeg")
        msg = Message("user", [img])
        result = AgentEvalConverter.convert_message(msg)
        assert len(result) == 1
        part = result[0]["content"][0]
        assert part["type"] == "input_image"
        assert part["image_url"] == "https://example.com/photo.jpg"
        assert part["detail"] == "auto"

    def test_user_image_uri_without_media_type(self) -> None:
        """URI content without media_type still emits input_image (no detail key)."""
        img = Content("uri", uri="https://example.com/pic.png")
        msg = Message("user", [img])
        result = AgentEvalConverter.convert_message(msg)
        part = result[0]["content"][0]
        assert part["type"] == "input_image"
        assert part["image_url"] == "https://example.com/pic.png"
        assert "detail" not in part

    def test_mixed_text_and_image(self) -> None:
        """Message with text + image produces both content parts."""
        msg = Message(
            "user",
            [
                Content.from_text("What's in this image?"),
                Content.from_uri("https://example.com/cat.jpg", media_type="image/jpeg"),
            ],
        )
        result = AgentEvalConverter.convert_message(msg)
        assert len(result) == 1
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][0] == {"type": "text", "text": "What's in this image?"}
        assert result[0]["content"][1]["type"] == "input_image"
        assert result[0]["content"][1]["image_url"] == "https://example.com/cat.jpg"


# ---------------------------------------------------------------------------
# AgentEvalConverter.convert_messages
# ---------------------------------------------------------------------------


class TestConvertMessages:
    def test_full_conversation(self) -> None:
        messages = [
            Message("user", ["What's the weather?"]),
            Message(
                "assistant",
                [Content.from_function_call(call_id="c1", name="get_weather", arguments='{"loc": "SEA"}')],
            ),
            Message("tool", [Content.from_function_result(call_id="c1", result="Sunny")]),
            Message("assistant", ["It's sunny in Seattle!"]),
        ]
        result = AgentEvalConverter.convert_messages(messages)
        assert len(result) == 4
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"][0]["type"] == "tool_call"
        assert result[1]["content"][0]["name"] == "get_weather"
        assert result[2]["role"] == "tool"
        assert result[2]["content"][0]["type"] == "tool_result"
        assert result[3]["role"] == "assistant"
        assert result[3]["content"] == [{"type": "text", "text": "It's sunny in Seattle!"}]

    def test_multimodal_conversation_preserves_images(self) -> None:
        """Full conversation with image content flows through convert_messages."""
        messages = [
            Message(
                "user",
                [
                    Content.from_text("Describe this image"),
                    Content.from_uri("https://example.com/photo.jpg", media_type="image/jpeg"),
                ],
            ),
            Message("assistant", ["This is a photo of a sunset over the ocean."]),
        ]
        result = AgentEvalConverter.convert_messages(messages)
        assert len(result) == 2
        # User message has text + image
        user_content = result[0]["content"]
        assert len(user_content) == 2
        assert user_content[0] == {"type": "text", "text": "Describe this image"}
        assert user_content[1]["type"] == "input_image"
        assert user_content[1]["image_url"] == "https://example.com/photo.jpg"
        # Assistant response is text
        assert result[1]["content"] == [{"type": "text", "text": "This is a photo of a sunset over the ocean."}]


# ---------------------------------------------------------------------------
# AgentEvalConverter.extract_tools
# ---------------------------------------------------------------------------


class TestExtractTools:
    def test_extracts_function_tools(self) -> None:
        tool = FunctionTool(
            name="get_weather",
            description="Get weather for a location",
            func=lambda location: f"Sunny in {location}",
        )
        agent = MagicMock()
        agent.default_options = {"tools": [tool]}

        result = AgentEvalConverter.extract_tools(agent)
        assert len(result) == 1
        assert result[0]["name"] == "get_weather"
        assert result[0]["description"] == "Get weather for a location"
        assert "parameters" in result[0]

    def test_skips_non_function_tools(self) -> None:
        agent = MagicMock()
        agent.default_options = {"tools": [{"type": "web_search"}, "some_string"]}

        result = AgentEvalConverter.extract_tools(agent)
        assert len(result) == 0

    def test_no_tools(self) -> None:
        agent = MagicMock()
        agent.default_options = {}
        assert AgentEvalConverter.extract_tools(agent) == []

    def test_no_default_options(self) -> None:
        agent = MagicMock(spec=[])  # No attributes
        assert AgentEvalConverter.extract_tools(agent) == []


# ---------------------------------------------------------------------------
# AgentEvalConverter.to_eval_item (now returns EvalItem)
# ---------------------------------------------------------------------------


class TestToEvalItem:
    def test_string_query(self) -> None:
        response = AgentResponse(messages=[Message("assistant", ["The weather is sunny."])])
        item = AgentEvalConverter.to_eval_item(query="What's the weather?", response=response)

        assert isinstance(item, EvalItem)
        assert item.query == "What's the weather?"
        assert item.response == "The weather is sunny."
        assert len(item.conversation) == 2
        assert item.conversation[0].role == "user"
        assert item.conversation[1].role == "assistant"

    def test_message_query(self) -> None:
        input_msgs = [
            Message("system", ["Be helpful."]),
            Message("user", ["Hello"]),
        ]
        response = AgentResponse(messages=[Message("assistant", ["Hi there!"])])
        item = AgentEvalConverter.to_eval_item(query=input_msgs, response=response)

        assert item.query == "Hello"  # Only user messages
        assert len(item.conversation) == 3  # system + user + assistant

    def test_with_context(self) -> None:
        response = AgentResponse(messages=[Message("assistant", ["Answer."])])
        item = AgentEvalConverter.to_eval_item(
            query="Question?",
            response=response,
            context="Some reference document.",
        )
        assert item.context == "Some reference document."

    def test_with_explicit_tools(self) -> None:
        tool = FunctionTool(
            name="search",
            description="Search the web",
            func=lambda q: f"Results for {q}",
        )
        response = AgentResponse(messages=[Message("assistant", ["Found it."])])
        item = AgentEvalConverter.to_eval_item(
            query="Find info",
            response=response,
            tools=[tool],
        )
        assert item.tools is not None
        assert len(item.tools) == 1
        assert item.tools[0].name == "search"

    def test_with_agent_tools(self) -> None:
        tool = FunctionTool(name="calc", description="Calculate", func=lambda x: str(x))
        agent = MagicMock()
        agent.default_options = {"tools": [tool]}

        response = AgentResponse(messages=[Message("assistant", ["42"])])
        item = AgentEvalConverter.to_eval_item(
            query="What is 6*7?",
            response=response,
            agent=agent,
        )
        assert item.tools is not None
        assert item.tools[0].name == "calc"

    def test_explicit_tools_override_agent(self) -> None:
        agent_tool = FunctionTool(name="agent_tool", description="from agent", func=lambda: "")
        explicit_tool = FunctionTool(name="explicit_tool", description="explicit", func=lambda: "")

        agent = MagicMock()
        agent.default_options = {"tools": [agent_tool]}

        response = AgentResponse(messages=[Message("assistant", ["Done"])])
        item = AgentEvalConverter.to_eval_item(
            query="Test",
            response=response,
            agent=agent,
            tools=[explicit_tool],
        )
        assert item.tools is not None
        assert len(item.tools) == 1
        assert item.tools[0].name == "explicit_tool"

    def test_split_messages_format(self) -> None:
        """split_messages() should split conversation at last user message."""
        response = AgentResponse(messages=[Message("assistant", ["Answer"])])
        item = AgentEvalConverter.to_eval_item(
            query="Q",
            response=response,
            tools=[FunctionTool(name="t", description="d", func=lambda: "")],
        )
        query_msgs, response_msgs = item.split_messages()
        # Single-turn: query has just the user msg, response has the assistant msg
        assert len(query_msgs) == 1
        assert query_msgs[0].role == "user"
        assert len(response_msgs) == 1
        assert response_msgs[0].role == "assistant"
        # Tools preserved on item
        assert item.tools is not None
        assert len(item.tools) == 1
        assert item.tools[0].name == "t"

    def test_split_messages_multiturn_preserves_interleaving(self) -> None:
        """Multi-turn split_messages() splits at last user message, preserving interleaving."""
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's sunny in Seattle."]),
            Message("user", ["And tomorrow?"]),
            Message("assistant", [Content(type="function_call", name="get_forecast")]),
            Message("tool", [Content(type="function_result", result="Rain expected")]),
            Message("assistant", ["Rain is expected tomorrow."]),
        ]
        item = EvalItem(conversation=conversation)
        query_msgs, response_msgs = item.split_messages()
        # query_messages: everything up to and including the last user message
        assert len(query_msgs) == 3  # user, assistant, user
        assert query_msgs[0].role == "user"
        assert query_msgs[1].role == "assistant"  # interleaved!
        assert query_msgs[2].role == "user"
        # response_messages: everything after the last user message
        assert len(response_msgs) == 3  # assistant(tool_call), tool, assistant
        assert response_msgs[0].role == "assistant"
        assert response_msgs[1].role == "tool"
        assert response_msgs[2].role == "assistant"

    def test_split_messages_full_split(self) -> None:
        """ConversationSplit.FULL splits after the first user message."""
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's 62°F in Seattle."]),
            Message("user", ["And tomorrow?"]),
            Message("assistant", ["Rain is expected tomorrow."]),
        ]
        item = EvalItem(conversation=conversation)
        query_msgs, response_msgs = item.split_messages(split=ConversationSplit.FULL)
        # query_messages: just the first user message
        assert len(query_msgs) == 1
        assert query_msgs[0].role == "user"
        assert query_msgs[0].text == "What's the weather?"
        # response_messages: everything after the first user message
        assert len(response_msgs) == 3
        assert response_msgs[0].role == "assistant"
        assert response_msgs[1].role == "user"
        assert response_msgs[2].role == "assistant"

    def test_split_messages_full_split_with_system(self) -> None:
        """FULL split includes system messages before the first user message in query."""
        conversation = [
            Message("system", ["You are a weather assistant."]),
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's sunny."]),
        ]
        item = EvalItem(conversation=conversation)
        query_msgs, response_msgs = item.split_messages(split=ConversationSplit.FULL)
        # query includes system + first user
        assert len(query_msgs) == 2
        assert query_msgs[0].role == "system"
        assert query_msgs[1].role == "user"
        assert len(response_msgs) == 1

    def test_split_messages_full_split_with_tools(self) -> None:
        """FULL split puts all tool interactions in response_messages."""
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", [Content(type="function_call", name="get_weather")]),
            Message("tool", [Content(type="function_result", result="62°F")]),
            Message("assistant", ["It's 62°F."]),
            Message("user", ["Thanks!"]),
            Message("assistant", ["You're welcome!"]),
        ]
        item = EvalItem(conversation=conversation)
        query_msgs, response_msgs = item.split_messages(split=ConversationSplit.FULL)
        assert len(query_msgs) == 1
        assert len(response_msgs) == 5

    def test_split_messages_last_turn_is_default(self) -> None:
        """Default split_messages() uses LAST_TURN split."""
        conversation = [
            Message("user", ["Hello"]),
            Message("assistant", ["Hi there"]),
            Message("user", ["Bye"]),
            Message("assistant", ["Goodbye"]),
        ]
        item = EvalItem(conversation=conversation)
        q_default, r_default = item.split_messages()
        q_explicit, r_explicit = item.split_messages(split=ConversationSplit.LAST_TURN)
        assert [m.role for m in q_default] == [m.role for m in q_explicit]
        assert [m.text for m in q_default] == [m.text for m in q_explicit]
        assert [m.role for m in r_default] == [m.role for m in r_explicit]
        assert [m.text for m in r_default] == [m.text for m in r_explicit]

    def test_per_turn_items_simple(self) -> None:
        """per_turn_items produces one EvalItem per user message."""
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's 62°F."]),
            Message("user", ["And tomorrow?"]),
            Message("assistant", ["Rain expected."]),
        ]
        items = EvalItem.per_turn_items(conversation)
        assert len(items) == 2

        # Turn 1
        assert items[0].query == "What's the weather?"
        assert items[0].response == "It's 62°F."
        assert len(items[0].conversation) == 2

        # Turn 2 — includes cumulative context; query joins all user texts in query split
        assert items[1].query == "What's the weather? And tomorrow?"
        assert items[1].response == "Rain expected."
        assert len(items[1].conversation) == 4

    def test_per_turn_items_with_tools(self) -> None:
        """per_turn_items handles tool calls within a turn."""
        conversation = [
            Message("user", ["Check weather"]),
            Message("assistant", [Content(type="function_call", name="get_weather")]),
            Message("tool", [Content(type="function_result", result="sunny")]),
            Message("assistant", ["It's sunny."]),
            Message("user", ["Thanks"]),
            Message("assistant", ["You're welcome!"]),
        ]
        tool_objs = [_make_tool("get_weather")]
        items = EvalItem.per_turn_items(conversation, tools=tool_objs)
        assert len(items) == 2

        # Turn 1: response includes tool_call, tool_result, and final assistant
        assert items[0].response == "It's sunny."
        assert items[0].tools == tool_objs
        assert len(items[0].conversation) == 4  # user, assistant(tool), tool, assistant

        # Turn 2
        assert items[1].response == "You're welcome!"
        assert len(items[1].conversation) == 6  # full conversation

    def test_per_turn_items_empty(self) -> None:
        """per_turn_items returns empty list when no user messages."""
        items = EvalItem.per_turn_items([Message("assistant", ["Hello"])])
        assert items == []

    def test_per_turn_items_single_turn(self) -> None:
        """per_turn_items with single turn produces one item."""
        conversation = [
            Message("user", ["Hi"]),
            Message("assistant", ["Hello!"]),
        ]
        items = EvalItem.per_turn_items(conversation)
        assert len(items) == 1
        assert items[0].query == "Hi"
        assert items[0].response == "Hello!"

    def test_custom_splitter_callable(self) -> None:
        """Custom callable splitter is used by split_messages()."""
        conversation = [
            Message("user", ["Remember my name is Alice"]),
            Message("assistant", ["Got it, Alice!"]),
            Message("user", ["What's the capital of France?"]),
            Message("assistant", [Content(type="function_call", name="retrieve_memory", call_id="m1")]),
            Message("tool", [Content(type="function_result", call_id="m1", result="User name: Alice")]),
            Message("assistant", ["The capital of France is Paris, Alice!"]),
        ]

        def split_before_memory(conv):
            """Split just before the memory retrieval tool call."""
            for i, msg in enumerate(conv):
                for c in msg.contents:
                    if c.name == "retrieve_memory":
                        return conv[:i], conv[i:]
            return EvalItem._split_last_turn_static(conv)

        item = EvalItem(conversation=conversation)
        query_msgs, response_msgs = item.split_messages(split=split_before_memory)

        # split_before_memory finds "retrieve_memory" at conv[3] (assistant tool_call msg)
        # query = conv[:3] = [user, assistant, user]
        # response = conv[3:] = [assistant(tool_call), tool, assistant]
        assert len(query_msgs) == 3
        assert query_msgs[-1].role == "user"
        assert len(response_msgs) == 3
        assert response_msgs[0].role == "assistant"  # the tool_call msg

    def test_custom_splitter_with_fallback(self) -> None:
        """Custom splitter falls back to _split_last_turn_static when pattern not found."""
        conversation = [
            Message("user", ["Hello"]),
            Message("assistant", ["Hi there!"]),
        ]

        def split_before_memory(conv):
            for i, msg in enumerate(conv):
                for c in msg.contents:
                    if c.name == "retrieve_memory":
                        return conv[:i], conv[i:]
            return EvalItem._split_last_turn_static(conv)

        item = EvalItem(conversation=conversation)
        query_msgs, response_msgs = item.split_messages(split=split_before_memory)
        # Falls back to last-turn split
        assert len(query_msgs) == 1
        assert query_msgs[0].role == "user"
        assert len(response_msgs) == 1
        assert response_msgs[0].role == "assistant"

    def test_custom_splitter_lambda(self) -> None:
        """A lambda works as a custom splitter."""
        conversation = [
            Message("user", ["A"]),
            Message("assistant", ["B"]),
            Message("user", ["C"]),
            Message("assistant", ["D"]),
        ]
        # Split at index 2 (arbitrary)
        item = EvalItem(conversation=conversation)
        query_msgs, response_msgs = item.split_messages(split=lambda conv: (conv[:2], conv[2:]))
        assert len(query_msgs) == 2
        assert len(response_msgs) == 2

    def test_split_strategy_on_item_used_by_split_messages(self) -> None:
        """split_strategy field on EvalItem is used as default by split_messages()."""
        conversation = [
            Message("user", ["First"]),
            Message("assistant", ["Response 1"]),
            Message("user", ["Second"]),
            Message("assistant", ["Response 2"]),
        ]
        item = EvalItem(
            conversation=conversation,
            split_strategy=ConversationSplit.FULL,
        )
        # split_messages() with no split arg should use item.split_strategy
        query_msgs, response_msgs = item.split_messages()
        assert len(query_msgs) == 1  # FULL: just first user msg
        assert query_msgs[0].text == "First"
        assert len(response_msgs) == 3

    def test_explicit_split_overrides_item_split_strategy(self) -> None:
        """Explicit split= arg to split_messages() overrides item.split_strategy."""
        conversation = [
            Message("user", ["First"]),
            Message("assistant", ["Response 1"]),
            Message("user", ["Second"]),
            Message("assistant", ["Response 2"]),
        ]
        item = EvalItem(
            conversation=conversation,
            split_strategy=ConversationSplit.FULL,
        )
        # Explicit split= should override split_strategy
        query_msgs, response_msgs = item.split_messages(split=ConversationSplit.LAST_TURN)
        assert len(query_msgs) == 3  # LAST_TURN: up to last user
        assert query_msgs[-1].text == "Second"
        assert len(response_msgs) == 1

    def test_no_split_defaults_to_last_turn(self) -> None:
        """When neither split= nor split_strategy is set, defaults to LAST_TURN."""
        conversation = [
            Message("user", ["Hello"]),
            Message("assistant", ["Hi"]),
        ]
        item = EvalItem(conversation=conversation)
        assert item.split_strategy is None
        query_msgs, response_msgs = item.split_messages()
        assert len(query_msgs) == 1
        assert query_msgs[0].role == "user"


# ---------------------------------------------------------------------------
# _build_testing_criteria
# ---------------------------------------------------------------------------


class TestBuildTestingCriteria:
    def test_without_data_mapping(self) -> None:
        criteria = _build_testing_criteria(["relevance", "coherence"], "gpt-4o")
        assert len(criteria) == 2
        assert criteria[0]["evaluator_name"] == "builtin.relevance"
        assert criteria[0]["initialization_parameters"] == {"deployment_name": "gpt-4o"}
        assert "data_mapping" not in criteria[0]

    def test_with_data_mapping(self) -> None:
        criteria = _build_testing_criteria(["relevance", "groundedness"], "gpt-4o", include_data_mapping=True)
        assert "data_mapping" in criteria[0]
        # Quality evaluators should NOT have conversation
        assert criteria[0]["data_mapping"] == {
            "query": "{{item.query}}",
            "response": "{{item.response}}",
        }
        # Groundedness has an extra context mapping
        assert "context" in criteria[1]["data_mapping"]
        assert "conversation" not in criteria[1]["data_mapping"]

    def test_tool_evaluator_includes_tool_definitions(self) -> None:
        criteria = _build_testing_criteria(["relevance", "tool_call_accuracy"], "gpt-4o", include_data_mapping=True)
        # relevance: string query/response
        assert criteria[0]["data_mapping"]["query"] == "{{item.query}}"
        assert criteria[0]["data_mapping"]["response"] == "{{item.response}}"
        assert "tool_definitions" not in criteria[0]["data_mapping"]
        # tool_call_accuracy: array query/response + tool_definitions
        assert criteria[1]["data_mapping"]["query"] == "{{item.query_messages}}"
        assert criteria[1]["data_mapping"]["response"] == "{{item.response_messages}}"
        assert criteria[1]["data_mapping"]["tool_definitions"] == "{{item.tool_definitions}}"

    def test_agent_evaluators_use_message_arrays(self) -> None:
        agent_evals = ["task_adherence", "intent_resolution", "task_completion"]
        criteria = _build_testing_criteria(agent_evals, "gpt-4o", include_data_mapping=True)
        for c in criteria:
            assert c["data_mapping"]["query"] == "{{item.query_messages}}", f"{c['name']}"
            assert c["data_mapping"]["response"] == "{{item.response_messages}}", f"{c['name']}"

    def test_quality_evaluators_use_strings(self) -> None:
        quality_evals = ["coherence", "relevance", "fluency"]
        criteria = _build_testing_criteria(quality_evals, "gpt-4o", include_data_mapping=True)
        for c in criteria:
            assert c["data_mapping"]["query"] == "{{item.query}}", f"{c['name']}"
            assert c["data_mapping"]["response"] == "{{item.response}}", f"{c['name']}"

    def test_similarity_includes_ground_truth(self) -> None:
        criteria = _build_testing_criteria(["similarity"], "gpt-4o", include_data_mapping=True)
        assert criteria[0]["data_mapping"]["ground_truth"] == "{{item.ground_truth}}"

    def test_all_tool_evaluators_include_tool_definitions(self) -> None:
        tool_evals = [
            "tool_call_accuracy",
            "tool_selection",
            "tool_input_accuracy",
            "tool_output_utilization",
            "tool_call_success",
        ]
        criteria = _build_testing_criteria(tool_evals, "gpt-4o", include_data_mapping=True)
        for c in criteria:
            assert "tool_definitions" in c["data_mapping"], f"{c['name']} missing tool_definitions"


# ---------------------------------------------------------------------------
# _build_item_schema
# ---------------------------------------------------------------------------


class TestBuildItemSchema:
    def test_without_context(self) -> None:
        schema = _build_item_schema(has_context=False)
        assert "context" not in schema["properties"]
        assert schema["required"] == ["query", "response"]

    def test_with_context(self) -> None:
        schema = _build_item_schema(has_context=True)
        assert "context" in schema["properties"]

    def test_with_tools(self) -> None:
        schema = _build_item_schema(has_tools=True)
        assert "tool_definitions" in schema["properties"]

    def test_with_ground_truth(self) -> None:
        schema = _build_item_schema(has_ground_truth=True)
        assert "ground_truth" in schema["properties"]

    def test_with_context_and_tools(self) -> None:
        schema = _build_item_schema(has_context=True, has_tools=True)
        assert "context" in schema["properties"]
        assert "tool_definitions" in schema["properties"]


# ---------------------------------------------------------------------------
# FoundryEvals (constructor, name, select, evaluate via dataset)
# ---------------------------------------------------------------------------


class TestFoundryEvals:
    def test_constructor_with_openai_client(self) -> None:
        mock_client = MagicMock()
        fe = FoundryEvals(client=mock_client, model="gpt-4o")
        assert fe.name == "Microsoft Foundry"

    def test_constructor_with_project_client(self) -> None:
        mock_oai = MagicMock(spec=AsyncOpenAI)
        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = mock_oai
        fe = FoundryEvals(project_client=mock_project, model="gpt-4o")
        assert fe.name == "Microsoft Foundry"
        mock_project.get_openai_client.assert_called_once()

    def test_constructor_no_client_auto_creates_from_env(self) -> None:
        """When no client/project_client given, auto-creates FoundryChatClient from env."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True), pytest.raises((ValueError, Exception)):
            FoundryEvals(model="gpt-4o")

    def test_name_property(self) -> None:
        fe = FoundryEvals(client=MagicMock(), model="gpt-4o")
        assert fe.name == "Microsoft Foundry"

    def test_evaluators_passed_in_constructor(self) -> None:
        fe = FoundryEvals(
            client=MagicMock(),
            model="gpt-4o",
            evaluators=["relevance", "coherence"],
        )
        assert fe._evaluators == ["relevance", "coherence"]

    async def test_evaluate_calls_evals_api(self) -> None:
        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_123"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_456"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=2)
        mock_completed.report_url = "https://portal.azure.com/eval/run_456"
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        # Mock output_items.list so _fetch_output_items exercises the full flow
        mock_output_item = MagicMock()
        mock_output_item.id = "output_item_1"
        mock_output_item.status = "pass"
        mock_output_item.sample = MagicMock(error=None, usage=None, input=[], output=[])
        mock_result = MagicMock(status="pass", score=5, reason="Relevant response")
        mock_result.name = "relevance"  # MagicMock(name=...) sets display name, not .name attr
        mock_output_item.results = [mock_result]
        mock_client.evals.runs.output_items.list = AsyncMock(return_value=_AsyncPage([mock_output_item]))

        items = [
            EvalItem(conversation=[Message("user", ["Hello"]), Message("assistant", ["Hi there!"])]),
            EvalItem(conversation=[Message("user", ["Weather?"]), Message("assistant", ["Sunny."])]),
        ]

        fe = FoundryEvals(
            client=mock_client,
            model="gpt-4o",
            evaluators=[FoundryEvals.RELEVANCE],
        )
        results = await fe.evaluate(items)

        assert isinstance(results, EvalResults)
        assert results.status == "completed"
        assert results.eval_id == "eval_123"
        assert results.run_id == "run_456"
        assert results.report_url == "https://portal.azure.com/eval/run_456"
        assert results.all_passed
        assert results.passed == 2
        assert results.failed == 0

        # Verify per-item output_items were fetched
        assert len(results.items) == 1
        assert results.items[0].item_id == "output_item_1"
        assert results.items[0].status == "pass"
        assert len(results.items[0].scores) == 1
        assert results.items[0].scores[0].name == "relevance"
        assert results.items[0].scores[0].score == 5

        # Verify evals.create was called with correct structure
        create_call = mock_client.evals.create.call_args
        assert create_call.kwargs["name"] == "Agent Framework Eval"
        assert create_call.kwargs["data_source_config"]["type"] == "custom"

        # Verify evals.runs.create was called with JSONL data source
        run_call = mock_client.evals.runs.create.call_args
        assert run_call.kwargs["data_source"]["type"] == "jsonl"
        content = run_call.kwargs["data_source"]["source"]["content"]
        assert len(content) == 2

    async def test_evaluate_uses_default_evaluators(self) -> None:
        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_1"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_1"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        fe = FoundryEvals(client=mock_client, model="gpt-4o")
        await fe.evaluate([EvalItem(conversation=[Message("user", ["Hi"]), Message("assistant", ["Hello"])])])

        # Verify default evaluators were used
        create_call = mock_client.evals.create.call_args
        criteria = create_call.kwargs["testing_criteria"]
        names = {c["name"] for c in criteria}
        assert "relevance" in names
        assert "coherence" in names
        assert "task_adherence" in names

    async def test_evaluate_uses_dataset_path(self) -> None:
        """Items use the JSONL dataset path."""
        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_ds"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_ds"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        items = [
            EvalItem(
                conversation=[Message("user", ["What's the weather?"]), Message("assistant", ["Sunny"])],
            ),
        ]

        fe = FoundryEvals(client=mock_client, model="gpt-4o")
        await fe.evaluate(items)

        run_call = mock_client.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "jsonl"
        content = ds["source"]["content"]
        assert content[0]["item"]["query"] == "What's the weather?"

    async def test_evaluate_with_tool_items_uses_dataset_path(self) -> None:
        """Items with tool_definitions use the dataset path."""
        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_tool"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_tool"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        items = [
            EvalItem(
                conversation=[Message("user", ["Do the thing"]), Message("assistant", ["Done"])],
                tools=[_make_tool("my_tool")],
            ),
        ]

        fe = FoundryEvals(
            client=mock_client,
            model="gpt-4o",
            evaluators=[FoundryEvals.TOOL_CALL_ACCURACY],
        )
        await fe.evaluate(items)

        run_call = mock_client.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "jsonl"
        assert "tool_definitions" in ds["source"]["content"][0]["item"]

    async def test_evaluate_ground_truth_in_dataset(self) -> None:
        """Items with expected_output include ground_truth in the JSONL payload."""
        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_gt"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_gt"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        items = [
            EvalItem(
                conversation=[Message("user", ["What is 2+2?"]), Message("assistant", ["4"])],
                expected_output="4",
            ),
        ]

        fe = FoundryEvals(
            client=mock_client,
            model="gpt-4o",
            evaluators=[FoundryEvals.SIMILARITY],
        )
        await fe.evaluate(items)

        # Verify ground_truth appears in JSONL data
        run_call = mock_client.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "jsonl"
        assert ds["source"]["content"][0]["item"]["ground_truth"] == "4"

        # Verify item_schema includes ground_truth
        create_call = mock_client.evals.create.call_args
        schema = create_call.kwargs["data_source_config"]["item_schema"]
        assert "ground_truth" in schema["properties"]

    async def test_evaluate_image_content_in_dataset(self) -> None:
        """Image content in conversations is preserved in the JSONL payload."""
        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_img"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_img"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        items = [
            EvalItem(
                conversation=[
                    Message(
                        "user",
                        [
                            Content.from_text("Describe this image"),
                            Content.from_uri("https://example.com/photo.jpg", media_type="image/jpeg"),
                        ],
                    ),
                    Message("assistant", ["A beautiful sunset over the ocean."]),
                ],
            ),
        ]

        fe = FoundryEvals(client=mock_client, model="gpt-4o")
        await fe.evaluate(items)

        run_call = mock_client.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "jsonl"
        item_data = ds["source"]["content"][0]["item"]

        # query_messages should contain the image
        query_msgs = item_data["query_messages"]
        user_msg = query_msgs[0]
        assert user_msg["role"] == "user"
        assert len(user_msg["content"]) == 2
        assert user_msg["content"][0] == {"type": "text", "text": "Describe this image"}
        assert user_msg["content"][1]["type"] == "input_image"
        assert user_msg["content"][1]["image_url"] == "https://example.com/photo.jpg"

    async def test_evaluate_with_project_client(self) -> None:
        mock_oai = MagicMock(spec=AsyncOpenAI)
        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = mock_oai

        mock_eval = MagicMock()
        mock_eval.id = "eval_pc"
        mock_oai.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_pc"
        mock_oai.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_oai.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        fe = FoundryEvals(project_client=mock_project, model="gpt-4o")
        results = await fe.evaluate([EvalItem(conversation=[Message("user", ["Hi"]), Message("assistant", ["Hello"])])])

        assert results.status == "completed"
        mock_project.get_openai_client.assert_called_once()


# ---------------------------------------------------------------------------
# FoundryEvals constants
# ---------------------------------------------------------------------------


class TestEvaluators:
    def test_constants_resolve(self) -> None:
        assert _resolve_evaluator(FoundryEvals.RELEVANCE) == "builtin.relevance"
        assert _resolve_evaluator(FoundryEvals.TOOL_CALL_ACCURACY) == "builtin.tool_call_accuracy"
        assert _resolve_evaluator(FoundryEvals.VIOLENCE) == "builtin.violence"
        assert _resolve_evaluator(FoundryEvals.INTENT_RESOLUTION) == "builtin.intent_resolution"

    def test_all_constants_are_valid(self) -> None:
        for attr in dir(FoundryEvals):
            if attr.startswith("_"):
                continue
            value = getattr(FoundryEvals, attr)
            if isinstance(value, str):
                _resolve_evaluator(value)  # should not raise


# ---------------------------------------------------------------------------
# _resolve_default_evaluators
# ---------------------------------------------------------------------------


class TestResolveDefaultEvaluators:
    def test_explicit_evaluators_passthrough(self) -> None:
        result = _resolve_default_evaluators([FoundryEvals.VIOLENCE])
        assert result == [FoundryEvals.VIOLENCE]

    def test_none_gives_defaults(self) -> None:
        result = _resolve_default_evaluators(None)
        assert FoundryEvals.RELEVANCE in result
        assert FoundryEvals.COHERENCE in result
        assert FoundryEvals.TASK_ADHERENCE in result
        assert FoundryEvals.TOOL_CALL_ACCURACY not in result

    def test_none_with_tool_items_adds_tool_eval(self) -> None:
        items = [
            EvalItem(
                conversation=[Message("user", ["search for stuff"]), Message("assistant", ["found it"])],
                tools=[_make_tool("search")],
            ),
        ]
        result = _resolve_default_evaluators(None, items=items)
        assert FoundryEvals.TOOL_CALL_ACCURACY in result

    def test_explicit_evaluators_ignore_tool_items(self) -> None:
        items = [
            EvalItem(
                conversation=[Message("user", ["search"]), Message("assistant", ["found"])],
                tools=[_make_tool("search")],
            ),
        ]
        result = _resolve_default_evaluators([FoundryEvals.RELEVANCE], items=items)
        assert result == [FoundryEvals.RELEVANCE]


# ---------------------------------------------------------------------------
# _filter_tool_evaluators
# ---------------------------------------------------------------------------


class TestFilterToolEvaluators:
    def test_keeps_tool_evaluators_when_items_have_tools(self) -> None:
        items = [
            EvalItem(conversation=[Message("user", ["q"]), Message("assistant", ["r"])], tools=[_make_tool("t")]),
        ]
        result = _filter_tool_evaluators(
            ["relevance", "tool_call_accuracy"],
            items,
        )
        assert "relevance" in result
        assert "tool_call_accuracy" in result

    def test_removes_tool_evaluators_when_no_tools(self) -> None:
        items = [
            EvalItem(conversation=[Message("user", ["q"]), Message("assistant", ["r"])]),
        ]
        result = _filter_tool_evaluators(
            ["relevance", "tool_call_accuracy"],
            items,
        )
        assert "relevance" in result
        assert "tool_call_accuracy" not in result

    def test_raises_when_all_filtered(self) -> None:
        items = [
            EvalItem(conversation=[Message("user", ["q"]), Message("assistant", ["r"])]),
        ]
        with pytest.raises(ValueError, match="require tool definitions"):
            _filter_tool_evaluators(
                ["tool_call_accuracy", "tool_selection"],
                items,
            )


# ---------------------------------------------------------------------------
# EvalResults
# ---------------------------------------------------------------------------


class TestEvalResults:
    def test_all_passed_true(self) -> None:
        r = EvalResults(
            provider="test",
            eval_id="e",
            run_id="r",
            status="completed",
            result_counts={"passed": 3, "failed": 0, "errored": 0},
        )
        assert r.all_passed
        assert r.passed == 3
        assert r.failed == 0
        assert r.total == 3

    def test_all_passed_false_on_failure(self) -> None:
        r = EvalResults(
            provider="test",
            eval_id="e",
            run_id="r",
            status="completed",
            result_counts={"passed": 2, "failed": 1, "errored": 0},
        )
        assert not r.all_passed
        assert r.failed == 1

    def test_all_passed_false_on_error(self) -> None:
        r = EvalResults(
            provider="test",
            eval_id="e",
            run_id="r",
            status="completed",
            result_counts={"passed": 2, "failed": 0, "errored": 1},
        )
        assert not r.all_passed

    def test_all_passed_false_on_non_completed(self) -> None:
        r = EvalResults(
            provider="test",
            eval_id="e",
            run_id="r",
            status="timeout",
            result_counts={"passed": 2, "failed": 0, "errored": 0},
        )
        assert not r.all_passed

    def test_all_passed_false_on_empty(self) -> None:
        r = EvalResults(
            provider="test",
            eval_id="e",
            run_id="r",
            status="completed",
            result_counts={"passed": 0, "failed": 0, "errored": 0},
        )
        assert not r.all_passed

    def test_raise_for_status_succeeds(self) -> None:
        r = EvalResults(
            provider="test",
            eval_id="e",
            run_id="r",
            status="completed",
            result_counts={"passed": 1, "failed": 0, "errored": 0},
        )
        r.raise_for_status()  # should not raise

    def test_raise_for_status_raises(self) -> None:
        r = EvalResults(
            provider="test",
            eval_id="e",
            run_id="r",
            status="completed",
            result_counts={"passed": 1, "failed": 1, "errored": 0},
        )
        with pytest.raises(EvalNotPassedError, match="1 passed, 1 failed"):
            r.raise_for_status()

    def test_raise_for_status_custom_message(self) -> None:
        r = EvalResults(provider="test", eval_id="e", run_id="r", status="failed")
        with pytest.raises(EvalNotPassedError, match="custom error"):
            r.raise_for_status("custom error")

    def test_none_result_counts(self) -> None:
        r = EvalResults(provider="test", eval_id="e", run_id="r", status="completed")
        assert r.passed == 0
        assert r.failed == 0
        assert r.total == 0
        assert not r.all_passed


# ---------------------------------------------------------------------------
# _resolve_openai_client
# ---------------------------------------------------------------------------


class TestResolveOpenAIClient:
    def test_explicit_client(self) -> None:
        mock_client = MagicMock()
        assert _resolve_openai_client(client=mock_client) is mock_client

    def test_project_client(self) -> None:
        mock_oai = MagicMock(spec=AsyncOpenAI)
        mock_project = MagicMock()
        mock_project.get_openai_client.return_value = mock_oai

        result = _resolve_openai_client(project_client=mock_project)
        assert result is mock_oai
        mock_project.get_openai_client.assert_called_once()

    def test_explicit_takes_precedence(self) -> None:
        mock_client = MagicMock()
        mock_project = MagicMock()

        result = _resolve_openai_client(client=mock_client, project_client=mock_project)
        assert result is mock_client
        mock_project.get_openai_client.assert_not_called()

    def test_neither_raises(self) -> None:
        with pytest.raises(ValueError, match="Provide either"):
            _resolve_openai_client()


# ---------------------------------------------------------------------------
# evaluate_agent with responses= (core function, uses FoundryEvals as evaluator)
# ---------------------------------------------------------------------------


class TestEvaluateAgentWithResponses:
    async def test_responses_without_queries_raises(self) -> None:
        mock_oai = MagicMock()
        response = AgentResponse(messages=[Message("assistant", ["Hello"])])

        with pytest.raises(ValueError, match="Provide 'queries' alongside 'responses'"):
            await evaluate_agent(
                responses=response,
                evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
            )

    async def test_fallback_to_dataset_with_query(self) -> None:
        """Non-Responses-API: falls back to dataset path when query is provided."""
        mock_oai = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_fb"
        mock_oai.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_fb"
        mock_oai.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = "https://portal.azure.com/eval"
        mock_completed.per_testing_criteria_results = None
        mock_oai.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        response = AgentResponse(messages=[Message("assistant", ["It's sunny."])])

        results = await evaluate_agent(
            responses=response,
            queries=["What's the weather?"],
            evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
        )

        assert results[0].status == "completed"
        assert results[0].all_passed

        # Should use jsonl data source (dataset path), not azure_ai_responses
        run_call = mock_oai.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "jsonl"
        content = ds["source"]["content"]
        assert len(content) == 1
        assert content[0]["item"]["query"] == "What's the weather?"
        assert content[0]["item"]["response"] == "It's sunny."

    async def test_fallback_with_agent_extracts_tools(self) -> None:
        """Non-Responses-API with agent: tool definitions are included in the eval item."""
        mock_oai = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_tools"
        mock_oai.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_tools"
        mock_oai.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_oai.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        mock_agent = MagicMock()
        mock_agent.default_options = {
            "tools": [FunctionTool(name="my_tool", description="A test tool", func=lambda x: x)]
        }

        response = AgentResponse(messages=[Message("assistant", ["Result."])])

        results = await evaluate_agent(
            responses=response,
            queries=["Do the thing"],
            agent=mock_agent,
            evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
        )

        assert results[0].status == "completed"

        run_call = mock_oai.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        content = ds["source"]["content"]
        item = content[0]["item"]
        assert "tool_definitions" in item
        tool_defs = item["tool_definitions"]
        assert any(t["name"] == "my_tool" for t in tool_defs)

    async def test_fallback_multiple_responses_with_queries(self) -> None:
        """Non-Responses-API with multiple responses requires matching queries."""
        mock_oai = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_multi_fb"
        mock_oai.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_multi_fb"
        mock_oai.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=2)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_oai.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        responses = [
            AgentResponse(messages=[Message("assistant", ["Answer 1"])]),
            AgentResponse(messages=[Message("assistant", ["Answer 2"])]),
        ]

        results = await evaluate_agent(
            responses=responses,
            queries=["Question 1", "Question 2"],
            evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
        )

        assert results[0].passed == 2
        run_call = mock_oai.evals.runs.create.call_args
        content = run_call.kwargs["data_source"]["source"]["content"]
        assert len(content) == 2
        assert content[0]["item"]["query"] == "Question 1"
        assert content[1]["item"]["query"] == "Question 2"

    async def test_query_response_count_mismatch_raises(self) -> None:
        """Mismatched query and response counts should raise."""
        mock_oai = MagicMock()

        responses = [
            AgentResponse(messages=[Message("assistant", ["A1"])]),
            AgentResponse(messages=[Message("assistant", ["A2"])]),
        ]

        with pytest.raises(ValueError, match="queries but"):
            await evaluate_agent(
                responses=responses,
                queries=["Q1", "Q2", "Q3"],
                evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
            )

    async def test_tool_evaluators_with_query_and_agent_uses_dataset_path(self) -> None:
        """Tool evaluators with query+agent uses dataset path."""
        mock_oai = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_tool"
        mock_oai.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_tool"
        mock_oai.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_oai.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        response = AgentResponse(
            messages=[Message("assistant", ["It's sunny"])],
        )

        agent = MagicMock()
        agent.default_options = {
            "tools": [
                FunctionTool(name="get_weather", description="Get weather", func=lambda: None),
            ]
        }

        fe = FoundryEvals(
            client=mock_oai,
            model="gpt-4o",
            evaluators=[FoundryEvals.TOOL_CALL_ACCURACY],
        )

        await evaluate_agent(
            responses=response,
            queries=["What's the weather?"],
            agent=agent,
            evaluators=fe,
        )

        # Verify it used the dataset path (jsonl), not Responses API path
        run_call = mock_oai.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "jsonl"

        # Verify tool_definitions are in the data items
        items = ds["source"]["content"]
        assert "tool_definitions" in items[0]["item"]


# ---------------------------------------------------------------------------
# EvalResults.sub_results
# ---------------------------------------------------------------------------


class TestEvalResultsSubResults:
    def test_sub_results_default_empty(self) -> None:
        r = EvalResults(
            provider="test",
            eval_id="e1",
            run_id="r1",
            status="completed",
            result_counts={"passed": 1, "failed": 0},
        )
        assert r.sub_results == {}
        assert r.all_passed

    def test_all_passed_checks_sub_results(self) -> None:
        parent = EvalResults(
            provider="test",
            eval_id="e1",
            run_id="r1",
            status="completed",
            result_counts={"passed": 2, "failed": 0},
            sub_results={
                "agent-a": EvalResults(
                    provider="test",
                    eval_id="e2",
                    run_id="r2",
                    status="completed",
                    result_counts={"passed": 1, "failed": 0},
                ),
                "agent-b": EvalResults(
                    provider="test",
                    eval_id="e3",
                    run_id="r3",
                    status="completed",
                    result_counts={"passed": 1, "failed": 1},
                ),
            },
        )
        assert not parent.all_passed  # agent-b has a failure

    def test_all_passed_with_all_sub_passing(self) -> None:
        parent = EvalResults(
            provider="test",
            eval_id="e1",
            run_id="r1",
            status="completed",
            result_counts={"passed": 2, "failed": 0},
            sub_results={
                "agent-a": EvalResults(
                    provider="test",
                    eval_id="e2",
                    run_id="r2",
                    status="completed",
                    result_counts={"passed": 1, "failed": 0},
                ),
            },
        )
        assert parent.all_passed

    def test_raise_for_status_includes_failed_agents(self) -> None:
        parent = EvalResults(
            provider="test",
            eval_id="e1",
            run_id="r1",
            status="completed",
            result_counts={"passed": 2, "failed": 0},
            sub_results={
                "good-agent": EvalResults(
                    provider="test",
                    eval_id="e2",
                    run_id="r2",
                    status="completed",
                    result_counts={"passed": 1, "failed": 0},
                ),
                "bad-agent": EvalResults(
                    provider="test",
                    eval_id="e3",
                    run_id="r3",
                    status="completed",
                    result_counts={"passed": 0, "failed": 1},
                ),
            },
        )
        with pytest.raises(EvalNotPassedError, match="bad-agent"):
            parent.raise_for_status()


# ---------------------------------------------------------------------------
# _extract_agent_eval_data
# ---------------------------------------------------------------------------


def _make_agent_exec_response(
    executor_id: str,
    response_text: str,
    user_messages: list[str] | None = None,
) -> AgentExecutorResponse:
    """Helper to build an AgentExecutorResponse for testing."""
    agent_response = AgentResponse(messages=[Message("assistant", [response_text])])
    full_conv: list[Message] = []
    if user_messages:
        for m in user_messages:
            full_conv.append(Message("user", [m]))
    full_conv.extend(agent_response.messages)
    return AgentExecutorResponse(
        executor_id=executor_id,
        agent_response=agent_response,
        full_conversation=full_conv,
    )


class TestExtractAgentEvalData:
    def test_extracts_single_agent(self) -> None:
        aer = _make_agent_exec_response("planner", "Plan is ready", ["Plan a trip"])

        events = [
            WorkflowEvent.executor_invoked("planner", "Plan a trip"),
            WorkflowEvent.executor_completed("planner", [aer]),
        ]
        result = WorkflowRunResult(events, [])

        data = _extract_agent_eval_data(result)
        assert len(data) == 1
        assert data[0]["executor_id"] == "planner"
        assert data[0]["response"].text == "Plan is ready"

    def test_extracts_multiple_agents(self) -> None:
        aer1 = _make_agent_exec_response("planner", "Plan done", ["Plan a trip"])
        aer2 = _make_agent_exec_response("booker", "Booked!", ["Book flight"])

        events = [
            WorkflowEvent.executor_invoked("planner", "Plan a trip"),
            WorkflowEvent.executor_completed("planner", [aer1]),
            WorkflowEvent.executor_invoked("booker", "Book flight"),
            WorkflowEvent.executor_completed("booker", [aer2]),
        ]
        result = WorkflowRunResult(events, [])

        data = _extract_agent_eval_data(result)
        assert len(data) == 2
        assert data[0]["executor_id"] == "planner"
        assert data[1]["executor_id"] == "booker"

    def test_skips_internal_executors(self) -> None:
        aer = _make_agent_exec_response("planner", "Done", ["Go"])

        events = [
            WorkflowEvent.executor_invoked("input-conversation", "hello"),
            WorkflowEvent.executor_completed("input-conversation", ["hello"]),
            WorkflowEvent.executor_invoked("planner", "Go"),
            WorkflowEvent.executor_completed("planner", [aer]),
            WorkflowEvent.executor_invoked("end", []),
            WorkflowEvent.executor_completed("end", None),
        ]
        result = WorkflowRunResult(events, [])

        data = _extract_agent_eval_data(result)
        assert len(data) == 1
        assert data[0]["executor_id"] == "planner"

    def test_resolves_agent_from_workflow(self) -> None:
        aer = _make_agent_exec_response("my-agent", "Done", ["Do it"])

        events = [
            WorkflowEvent.executor_invoked("my-agent", "Do it"),
            WorkflowEvent.executor_completed("my-agent", [aer]),
        ]
        result = WorkflowRunResult(events, [])

        # Build a mock workflow with AgentExecutor
        from agent_framework import AgentExecutor

        mock_agent = MagicMock()
        mock_agent.default_options = {"tools": []}
        mock_executor = MagicMock(spec=AgentExecutor)
        mock_executor.agent = mock_agent

        mock_workflow = MagicMock()
        mock_workflow.executors = {"my-agent": mock_executor}

        data = _extract_agent_eval_data(result, mock_workflow)
        assert len(data) == 1
        assert data[0]["agent"] is mock_agent


class TestExtractOverallQuery:
    def test_extracts_string_query(self) -> None:
        events = [WorkflowEvent.executor_invoked("input", "Plan a trip")]
        result = WorkflowRunResult(events, [])
        assert _extract_overall_query(result) == "Plan a trip"

    def test_extracts_message_query(self) -> None:
        msgs = [Message("user", ["What's the weather?"])]
        events = [WorkflowEvent.executor_invoked("input", msgs)]
        result = WorkflowRunResult(events, [])
        assert "What's the weather?" in (_extract_overall_query(result) or "")

    def test_returns_none_for_empty(self) -> None:
        result = WorkflowRunResult([], [])
        assert _extract_overall_query(result) is None


# ---------------------------------------------------------------------------
# evaluate_workflow (core function, uses FoundryEvals as evaluator)
# ---------------------------------------------------------------------------


class TestEvaluateWorkflow:
    def _mock_oai_client(self, eval_id: str = "eval_wf", run_id: str = "run_wf") -> MagicMock:
        mock_oai = MagicMock()
        mock_eval = MagicMock()
        mock_eval.id = eval_id
        mock_oai.evals.create = AsyncMock(return_value=mock_eval)
        mock_run = MagicMock()
        mock_run.id = run_id
        mock_oai.evals.runs.create = AsyncMock(return_value=mock_run)
        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = "https://portal.azure.com/eval"
        mock_completed.per_testing_criteria_results = None
        mock_oai.evals.runs.retrieve = AsyncMock(return_value=mock_completed)
        return mock_oai

    async def test_post_hoc_with_workflow_result(self) -> None:
        """Evaluate a workflow result that was already produced."""
        mock_oai = self._mock_oai_client()

        aer1 = _make_agent_exec_response("writer", "Draft written", ["Write about Paris"])
        aer2 = _make_agent_exec_response("reviewer", "Looks good!", ["Review: Draft written"])

        final_output = [Message("assistant", ["Final reviewed output"])]

        events = [
            WorkflowEvent.executor_invoked("input-conversation", "Write about Paris"),
            WorkflowEvent.executor_completed("input-conversation", None),
            WorkflowEvent.executor_invoked("writer", "Write about Paris"),
            WorkflowEvent.executor_completed("writer", [aer1]),
            WorkflowEvent.executor_invoked("reviewer", [aer1]),
            WorkflowEvent.executor_completed("reviewer", [aer2]),
            WorkflowEvent.output("end", final_output),
        ]
        wf_result = WorkflowRunResult(events, [])

        mock_workflow = MagicMock()
        mock_workflow.executors = {}

        results = await evaluate_workflow(
            workflow=mock_workflow,
            workflow_result=wf_result,
            evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
            include_overall=False,
        )

        assert results[0].status == "completed"
        assert "writer" in results[0].sub_results
        assert "reviewer" in results[0].sub_results
        assert len(results[0].sub_results) == 2

    async def test_with_queries_runs_workflow(self) -> None:
        """Passing queries= runs the workflow and evaluates."""
        mock_oai = self._mock_oai_client()

        aer = _make_agent_exec_response("agent", "Response", ["Query"])
        final_output = [Message("assistant", ["Final"])]

        events = [
            WorkflowEvent.executor_invoked("agent", "Test query"),
            WorkflowEvent.executor_completed("agent", [aer]),
            WorkflowEvent.output("end", final_output),
        ]
        wf_result = WorkflowRunResult(events, [])

        mock_workflow = MagicMock()
        mock_workflow.executors = {}
        mock_workflow.run = AsyncMock(return_value=wf_result)

        results = await evaluate_workflow(
            workflow=mock_workflow,
            queries=["Test query"],
            evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
            include_overall=False,
        )

        mock_workflow.run.assert_called_once_with("Test query")
        assert "agent" in results[0].sub_results

    async def test_overall_plus_per_agent(self) -> None:
        """Both overall and per-agent evals run by default."""
        mock_oai = self._mock_oai_client()

        aer = _make_agent_exec_response("planner", "Plan done", ["Plan trip"])
        final_output = [Message("assistant", ["Trip planned!"])]

        events = [
            WorkflowEvent.executor_invoked("input-conversation", "Plan trip"),
            WorkflowEvent.executor_completed("input-conversation", None),
            WorkflowEvent.executor_invoked("planner", "Plan trip"),
            WorkflowEvent.executor_completed("planner", [aer]),
            WorkflowEvent.output("end", final_output),
        ]
        wf_result = WorkflowRunResult(events, [])

        mock_workflow = MagicMock()
        mock_workflow.executors = {}

        results = await evaluate_workflow(
            workflow=mock_workflow,
            workflow_result=wf_result,
            evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
        )

        # Should have per-agent sub_results AND overall
        assert "planner" in results[0].sub_results
        assert results[0].status == "completed"
        # FoundryEvals.evaluate called twice: once for planner, once for overall
        assert mock_oai.evals.create.call_count == 2

    async def test_no_result_or_queries_raises(self) -> None:
        mock_oai = MagicMock()
        mock_workflow = MagicMock()

        with pytest.raises(ValueError, match="Provide either"):
            await evaluate_workflow(
                workflow=mock_workflow,
                evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
            )

    async def test_per_agent_only(self) -> None:
        """include_overall=False skips the overall eval."""
        mock_oai = self._mock_oai_client()

        aer = _make_agent_exec_response("agent-a", "Done", ["Do stuff"])

        events = [
            WorkflowEvent.executor_invoked("agent-a", "Do stuff"),
            WorkflowEvent.executor_completed("agent-a", [aer]),
        ]
        wf_result = WorkflowRunResult(events, [])

        mock_workflow = MagicMock()
        mock_workflow.executors = {}

        results = await evaluate_workflow(
            workflow=mock_workflow,
            workflow_result=wf_result,
            evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
            include_overall=False,
        )

        assert "agent-a" in results[0].sub_results
        # Only one eval call (per-agent), no overall
        assert mock_oai.evals.create.call_count == 1

    async def test_overall_eval_excludes_tool_evaluators(self) -> None:
        """Tool evaluators should not be passed to the overall workflow eval."""
        mock_oai = self._mock_oai_client()

        aer = _make_agent_exec_response("researcher", "Weather is sunny", ["What's the weather?"])

        events = [
            WorkflowEvent.executor_invoked("input-conversation", "What's the weather?"),
            WorkflowEvent.executor_completed("input-conversation", None),
            WorkflowEvent.executor_invoked("researcher", "What's the weather?"),
            WorkflowEvent.executor_completed("researcher", [aer]),
            WorkflowEvent.output("end", [Message("assistant", ["Weather is sunny"])]),
        ]
        wf_result = WorkflowRunResult(events, [])

        mock_workflow = MagicMock()
        mock_workflow.executors = {}

        fe = FoundryEvals(
            client=mock_oai,
            model="gpt-4o",
            evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY],
        )

        await evaluate_workflow(
            workflow=mock_workflow,
            workflow_result=wf_result,
            evaluators=fe,
        )

        # Should have 2 evals: one per-agent, one overall
        assert mock_oai.evals.create.call_count == 2

        # Check the overall eval's testing_criteria doesn't include tool_call_accuracy
        overall_call = mock_oai.evals.create.call_args_list[-1]
        overall_criteria = overall_call.kwargs["testing_criteria"]
        evaluator_names = [c["evaluator_name"] for c in overall_criteria]
        assert "builtin.tool_call_accuracy" not in evaluator_names
        assert "builtin.relevance" in evaluator_names

    async def test_per_agent_excludes_tool_evaluators_when_no_tools(self) -> None:
        """Sub-agents without tools should not get tool evaluators."""
        mock_oai = self._mock_oai_client()

        # researcher has tools, planner does not
        aer1 = _make_agent_exec_response("researcher", "Weather is sunny", ["Check weather"])
        aer2 = _make_agent_exec_response("planner", "Trip planned", ["Plan based on: sunny"])

        events = [
            WorkflowEvent.executor_invoked("researcher", "Check weather"),
            WorkflowEvent.executor_completed("researcher", [aer1]),
            WorkflowEvent.executor_invoked("planner", "Plan based on: sunny"),
            WorkflowEvent.executor_completed("planner", [aer2]),
        ]
        wf_result = WorkflowRunResult(events, [])

        from agent_framework import AgentExecutor

        # researcher has tools
        mock_researcher = MagicMock()
        mock_researcher.default_options = {
            "tools": [
                FunctionTool(name="get_weather", description="Get weather", func=lambda: None),
            ]
        }
        mock_researcher_executor = MagicMock(spec=AgentExecutor)
        mock_researcher_executor.agent = mock_researcher

        # planner has NO tools
        mock_planner = MagicMock()
        mock_planner.default_options = {"tools": []}
        mock_planner_executor = MagicMock(spec=AgentExecutor)
        mock_planner_executor.agent = mock_planner

        mock_workflow = MagicMock()
        mock_workflow.executors = {
            "researcher": mock_researcher_executor,
            "planner": mock_planner_executor,
        }

        fe = FoundryEvals(
            client=mock_oai,
            model="gpt-4o",
            evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY],
        )

        await evaluate_workflow(
            workflow=mock_workflow,
            workflow_result=wf_result,
            evaluators=fe,
            include_overall=False,
        )

        # Two sub-agent evals
        assert mock_oai.evals.create.call_count == 2

        # Find which call is for researcher vs planner by eval name
        for call in mock_oai.evals.create.call_args_list:
            criteria = call.kwargs["testing_criteria"]
            eval_names = [c["evaluator_name"] for c in criteria]
            name = call.kwargs["name"]
            if "planner" in name:
                assert "builtin.tool_call_accuracy" not in eval_names, (
                    "planner has no tools — should not get tool_call_accuracy"
                )
            elif "researcher" in name:
                assert "builtin.tool_call_accuracy" in eval_names, (
                    "researcher has tools — should get tool_call_accuracy"
                )

    async def test_expected_output_stamps_overall_items(self) -> None:
        """expected_output is stamped on overall items as ground_truth in the dataset."""
        mock_oai = self._mock_oai_client()

        aer = _make_agent_exec_response("agent", "Response", ["Query"])
        final_output = [Message("assistant", ["Final answer"])]

        events = [
            WorkflowEvent.executor_invoked("agent", "Test query"),
            WorkflowEvent.executor_completed("agent", [aer]),
            WorkflowEvent.output("end", final_output),
        ]
        wf_result = WorkflowRunResult(events, [])

        mock_workflow = MagicMock()
        mock_workflow.executors = {}
        mock_workflow.run = AsyncMock(return_value=wf_result)

        results = await evaluate_workflow(
            workflow=mock_workflow,
            queries=["Test query"],
            expected_output=["Expected answer"],
            evaluators=FoundryEvals(
                client=mock_oai,
                model="gpt-4o",
                evaluators=[FoundryEvals.SIMILARITY],
            ),
        )

        assert results[0].status == "completed"

        # Verify overall eval's dataset includes ground_truth
        # The overall eval is the last evals.runs.create call
        calls = mock_oai.evals.runs.create.call_args_list
        overall_call = calls[-1]
        ds = overall_call.kwargs["data_source"]
        overall_item = ds["source"]["content"][0]["item"]
        assert overall_item["ground_truth"] == "Expected answer"

    async def test_expected_output_with_num_repetitions(self) -> None:
        """expected_output is correctly stamped on overall items across multiple repetitions."""
        mock_oai = self._mock_oai_client()

        aer = _make_agent_exec_response("agent", "Response", ["Query"])
        final_output = [Message("assistant", ["Final answer"])]

        events = [
            WorkflowEvent.executor_invoked("agent", "Test query"),
            WorkflowEvent.executor_completed("agent", [aer]),
            WorkflowEvent.output("end", final_output),
        ]
        wf_result = WorkflowRunResult(events, [])

        mock_workflow = MagicMock()
        mock_workflow.executors = {}
        mock_workflow.run = AsyncMock(return_value=wf_result)

        results = await evaluate_workflow(
            workflow=mock_workflow,
            queries=["Test query"],
            expected_output=["Expected answer"],
            evaluators=FoundryEvals(
                client=mock_oai,
                model="gpt-4o",
                evaluators=[FoundryEvals.SIMILARITY],
            ),
            num_repetitions=2,
        )

        assert results[0].status == "completed"

        # workflow.run should be called twice (once per repetition)
        assert mock_workflow.run.call_count == 2

        # Verify all overall items have ground_truth stamped
        calls = mock_oai.evals.runs.create.call_args_list
        overall_call = calls[-1]
        ds = overall_call.kwargs["data_source"]
        items = ds["source"]["content"]
        assert len(items) == 2
        for item in items:
            assert item["item"]["ground_truth"] == "Expected answer"

    async def test_expected_output_length_mismatch_raises(self) -> None:
        """Mismatched queries and expected_output lengths raise ValueError."""
        mock_oai = MagicMock()
        mock_workflow = MagicMock()

        with pytest.raises(ValueError, match="expected_output"):
            await evaluate_workflow(
                workflow=mock_workflow,
                queries=["q1", "q2"],
                expected_output=["e1"],
                evaluators=FoundryEvals(client=mock_oai, model="gpt-4o"),
            )


# ---------------------------------------------------------------------------
# EvalItemResult and EvalScoreResult
# ---------------------------------------------------------------------------


class TestEvalItemResult:
    def test_status_properties(self) -> None:
        from agent_framework._evaluation import EvalItemResult

        passed = EvalItemResult(item_id="1", status="pass")
        assert passed.is_passed
        assert not passed.is_failed
        assert not passed.is_error

        failed = EvalItemResult(item_id="2", status="fail")
        assert not failed.is_passed
        assert failed.is_failed
        assert not failed.is_error

        errored = EvalItemResult(item_id="3", status="error")
        assert not errored.is_passed
        assert not errored.is_failed
        assert errored.is_error

        errored2 = EvalItemResult(item_id="4", status="errored")
        assert errored2.is_error

    def test_with_scores(self) -> None:
        from agent_framework._evaluation import EvalItemResult, EvalScoreResult

        scores = [
            EvalScoreResult(name="relevance", score=0.9, passed=True),
            EvalScoreResult(name="coherence", score=0.3, passed=False),
        ]
        item = EvalItemResult(item_id="1", status="fail", scores=scores)
        assert len(item.scores) == 2
        assert item.scores[0].passed is True
        assert item.scores[1].passed is False

    def test_with_error(self) -> None:
        from agent_framework._evaluation import EvalItemResult

        item = EvalItemResult(
            item_id="1",
            status="error",
            error_code="QueryExtractionError",
            error_message="Query list cannot be empty",
        )
        assert item.is_error
        assert item.error_code == "QueryExtractionError"

    def test_with_token_usage(self) -> None:
        from agent_framework._evaluation import EvalItemResult

        item = EvalItemResult(
            item_id="1",
            status="pass",
            token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
        assert item.token_usage is not None
        assert item.token_usage["total_tokens"] == 150


class TestEvalResultsWithItems:
    def test_item_status_properties(self) -> None:
        from agent_framework._evaluation import EvalItemResult

        results = EvalResults(
            provider="test",
            eval_id="e1",
            run_id="r1",
            status="completed",
            result_counts={"passed": 2, "failed": 1, "errored": 1},
            items=[
                EvalItemResult(item_id="1", status="pass"),
                EvalItemResult(item_id="2", status="pass"),
                EvalItemResult(item_id="3", status="fail"),
                EvalItemResult(item_id="4", status="error", error_code="QueryExtractionError"),
            ],
        )
        assert sum(1 for i in results.items if i.is_passed) == 2
        assert sum(1 for i in results.items if i.is_failed) == 1
        assert sum(1 for i in results.items if i.is_error) == 1

    def test_raise_for_status_includes_errored_items(self) -> None:
        from agent_framework._evaluation import EvalItemResult

        results = EvalResults(
            provider="test",
            eval_id="e1",
            run_id="r1",
            status="completed",
            result_counts={"passed": 0, "failed": 0, "errored": 2},
            items=[
                EvalItemResult(item_id="i1", status="error", error_code="QueryExtractionError"),
                EvalItemResult(item_id="i2", status="error", error_code="TimeoutError"),
            ],
        )
        with pytest.raises(EvalNotPassedError, match="Errored items: i1: QueryExtractionError"):
            results.raise_for_status()


# ---------------------------------------------------------------------------
# _fetch_output_items
# ---------------------------------------------------------------------------


class TestFetchOutputItems:
    async def test_fetches_and_converts_output_items(self) -> None:
        from agent_framework_foundry._foundry_evals import _fetch_output_items

        # Build mock output items matching the OpenAI SDK schema
        mock_result = MagicMock()
        mock_result.name = "relevance"
        mock_result.score = 0.85
        mock_result.passed = True
        mock_result.sample = None

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.total_tokens = 150
        mock_usage.cached_tokens = 0

        mock_input = MagicMock()
        mock_input.role = "user"
        mock_input.content = "What is the weather?"

        mock_output = MagicMock()
        mock_output.role = "assistant"
        mock_output.content = "It is sunny."

        mock_error = MagicMock()
        mock_error.code = ""
        mock_error.message = ""

        mock_sample = MagicMock()
        mock_sample.error = mock_error
        mock_sample.usage = mock_usage
        mock_sample.input = [mock_input]
        mock_sample.output = [mock_output]

        mock_oi = MagicMock()
        mock_oi.id = "oi_abc123"
        mock_oi.status = "pass"
        mock_oi.results = [mock_result]
        mock_oi.sample = mock_sample
        mock_oi.datasource_item = {"resp_id": "resp_xyz"}

        mock_client = MagicMock()
        mock_client.evals.runs.output_items.list = AsyncMock(return_value=_AsyncPage([mock_oi]))

        items = await _fetch_output_items(mock_client, "eval_1", "run_1")

        assert len(items) == 1
        item = items[0]
        assert item.item_id == "oi_abc123"
        assert item.status == "pass"
        assert item.is_passed
        assert len(item.scores) == 1
        assert item.scores[0].name == "relevance"
        assert item.scores[0].score == 0.85
        assert item.scores[0].passed is True
        assert item.response_id == "resp_xyz"
        assert item.input_text == "What is the weather?"
        assert item.output_text == "It is sunny."
        assert item.token_usage is not None
        assert item.token_usage["total_tokens"] == 150
        assert item.error_code is None

    async def test_handles_errored_item(self) -> None:
        from agent_framework_foundry._foundry_evals import _fetch_output_items

        mock_error = MagicMock()
        mock_error.code = "QueryExtractionError"
        mock_error.message = "Query list cannot be empty"

        mock_sample = MagicMock()
        mock_sample.error = mock_error
        mock_sample.usage = None
        mock_sample.input = []
        mock_sample.output = []

        mock_oi = MagicMock()
        mock_oi.id = "oi_err1"
        mock_oi.status = "error"
        mock_oi.results = []
        mock_oi.sample = mock_sample
        mock_oi.datasource_item = {}

        mock_client = MagicMock()
        mock_client.evals.runs.output_items.list = AsyncMock(return_value=_AsyncPage([mock_oi]))

        items = await _fetch_output_items(mock_client, "eval_1", "run_1")

        assert len(items) == 1
        item = items[0]
        assert item.is_error
        assert item.error_code == "QueryExtractionError"
        assert item.error_message == "Query list cannot be empty"
        assert len(item.scores) == 0

    async def test_handles_api_failure_gracefully(self) -> None:
        from agent_framework_foundry._foundry_evals import _fetch_output_items

        mock_client = MagicMock()
        mock_client.evals.runs.output_items.list = AsyncMock(side_effect=TypeError("API error"))

        items = await _fetch_output_items(mock_client, "eval_1", "run_1")
        assert items == []


# ---------------------------------------------------------------------------
# _poll_eval_run — timeout / failed / canceled paths
# ---------------------------------------------------------------------------


class TestPollEvalRun:
    async def test_timeout_returns_timeout_status(self) -> None:
        """Poll timeout returns EvalResults with status='timeout'."""
        from agent_framework_foundry._foundry_evals import _poll_eval_run

        mock_client = MagicMock()
        mock_pending = MagicMock()
        mock_pending.status = "queued"
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_pending)

        results = await _poll_eval_run(mock_client, "eval_1", "run_1", poll_interval=0.01, timeout=0.05)
        assert results.status == "timeout"
        assert results.eval_id == "eval_1"
        assert results.run_id == "run_1"

    async def test_failed_run_returns_error(self) -> None:
        """Failed run returns EvalResults with error message."""
        from agent_framework_foundry._foundry_evals import _poll_eval_run

        mock_client = MagicMock()
        mock_failed = MagicMock()
        mock_failed.status = "failed"
        mock_failed.error = "Model deployment unavailable"
        mock_failed.result_counts = None
        mock_failed.report_url = None
        mock_failed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_failed)

        results = await _poll_eval_run(mock_client, "eval_1", "run_1", poll_interval=0.01, timeout=5.0)
        assert results.status == "failed"
        assert results.error == "Model deployment unavailable"
        assert results.items == []

    async def test_canceled_run_returns_canceled_status(self) -> None:
        """Canceled run returns EvalResults with status='canceled'."""
        from agent_framework_foundry._foundry_evals import _poll_eval_run

        mock_client = MagicMock()
        mock_canceled = MagicMock()
        mock_canceled.status = "canceled"
        mock_canceled.error = None
        mock_canceled.result_counts = None
        mock_canceled.report_url = None
        mock_canceled.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_canceled)

        results = await _poll_eval_run(mock_client, "eval_1", "run_1", poll_interval=0.01, timeout=5.0)
        assert results.status == "canceled"
        assert results.error is None
        assert results.items == []


# ---------------------------------------------------------------------------
# evaluate_traces
# ---------------------------------------------------------------------------


class TestEvaluateTraces:
    async def test_raises_without_required_args(self) -> None:
        """Raises ValueError when no response_ids, trace_ids, or agent_id given."""
        from agent_framework_foundry._foundry_evals import evaluate_traces

        mock_client = MagicMock()
        with pytest.raises(ValueError, match="Provide at least one of"):
            await evaluate_traces(
                client=mock_client,
                model="gpt-4o",
            )

    async def test_response_ids_path(self) -> None:
        """evaluate_traces with response_ids uses the responses API path."""
        from agent_framework_foundry._foundry_evals import evaluate_traces

        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_tr"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_tr"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = "https://portal.azure.com/eval/run_tr"
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        mock_output_item = MagicMock()
        mock_output_item.id = "oi_resp"
        mock_output_item.status = "pass"
        mock_output_item.sample = MagicMock(error=None, usage=None, input=[], output=[])
        mock_result = MagicMock(status="pass", score=4)
        mock_result.name = "relevance"
        mock_output_item.results = [mock_result]
        mock_client.evals.runs.output_items.list = AsyncMock(return_value=_AsyncPage([mock_output_item]))

        results = await evaluate_traces(
            response_ids=["resp_abc", "resp_def"],
            client=mock_client,
            model="gpt-4o",
        )
        assert results.status == "completed"
        assert results.eval_id == "eval_tr"
        assert len(results.items) == 1
        assert results.items[0].item_id == "oi_resp"

        # Verify the response IDs are in the data source
        run_call = mock_client.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "azure_ai_responses"
        content = ds["item_generation_params"]["source"]["content"]
        assert len(content) == 2
        assert content[0]["item"]["resp_id"] == "resp_abc"

    async def test_trace_ids_path(self) -> None:
        """evaluate_traces with trace_ids builds azure_ai_traces data source."""
        from agent_framework_foundry._foundry_evals import evaluate_traces

        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_tid"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_tid"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=1)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        results = await evaluate_traces(
            trace_ids=["trace_1"],
            client=mock_client,
            model="gpt-4o",
        )
        assert results.status == "completed"

        run_call = mock_client.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "azure_ai_traces"
        assert ds["trace_ids"] == ["trace_1"]


# ---------------------------------------------------------------------------
# evaluate_foundry_target
# ---------------------------------------------------------------------------


class TestEvaluateFoundryTarget:
    async def test_happy_path(self) -> None:
        """evaluate_foundry_target creates eval + run and polls to completion."""
        from agent_framework_foundry._foundry_evals import evaluate_foundry_target

        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_tgt"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_tgt"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=2)
        mock_completed.report_url = "https://portal.azure.com/eval/run_tgt"
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        results = await evaluate_foundry_target(
            target={"type": "azure_ai_agent", "name": "my-agent"},
            test_queries=["Query 1", "Query 2"],
            client=mock_client,
            model="gpt-4o",
        )
        assert results.status == "completed"
        assert results.eval_id == "eval_tgt"
        assert results.all_passed

        # Verify the target and queries in data source
        run_call = mock_client.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "azure_ai_target_completions"
        assert ds["target"]["type"] == "azure_ai_agent"
        content = ds["source"]["content"]
        assert len(content) == 2
        assert content[0]["item"]["query"] == "Query 1"


# ---------------------------------------------------------------------------
# r3 review: _extract_result_counts paths
# ---------------------------------------------------------------------------


class TestExtractResultCounts:
    """Tests for all _extract_result_counts code paths."""

    def test_typed_counts(self) -> None:
        """ResultCounts-like object with all fields."""
        run = MagicMock()
        run.result_counts = _rc(passed=3, failed=1)
        result = _extract_result_counts(run)
        assert result == {"errored": 0, "failed": 1, "passed": 3, "total": 4}

    def test_none_result_counts(self):
        run = MagicMock()
        run.result_counts = None
        assert _extract_result_counts(run) is None


# ---------------------------------------------------------------------------
# r3 review: _extract_per_evaluator
# ---------------------------------------------------------------------------


class TestExtractPerEvaluator:
    """Tests for _extract_per_evaluator with mock data."""

    def test_with_per_testing_criteria_results(self):
        """Parses per_testing_criteria_results into per-evaluator breakdown."""

        @dataclass
        class CriteriaItem:
            testing_criteria: str
            passed: int
            failed: int

        run = MagicMock()
        run.per_testing_criteria_results = [
            CriteriaItem("relevance", 4, 1),
            CriteriaItem("coherence", 5, 0),
        ]
        result = _extract_per_evaluator(run)
        assert "relevance" in result
        assert result["relevance"] == {"passed": 4, "failed": 1}
        assert "coherence" in result
        assert result["coherence"] == {"passed": 5, "failed": 0}

    def test_with_testing_criteria_attr(self):
        """Uses testing_criteria field (the real SDK field name)."""

        @dataclass
        class CriteriaItem:
            testing_criteria: str
            passed: int
            failed: int

        run = MagicMock()
        run.per_testing_criteria_results = [CriteriaItem("fluency", 3, 2)]
        result = _extract_per_evaluator(run)
        assert "fluency" in result
        assert result["fluency"]["passed"] == 3

    def test_none_per_testing_criteria(self):
        run = MagicMock()
        run.per_testing_criteria_results = None
        assert _extract_per_evaluator(run) == {}


# ---------------------------------------------------------------------------
# r3 review: _resolve_openai_client async check
# ---------------------------------------------------------------------------


class TestResolveOpenaiClientAsyncCheck:
    """Tests for the async client runtime check."""

    def test_sync_client_raises(self):
        """A sync project_client raises TypeError (not an AsyncOpenAI instance)."""
        mock_project = MagicMock()
        sync_client = MagicMock()  # plain MagicMock, not isinstance(AsyncOpenAI)
        mock_project.get_openai_client.return_value = sync_client

        with pytest.raises(TypeError, match="sync client"):
            _resolve_openai_client(project_client=mock_project)


# ---------------------------------------------------------------------------
# r5 review: evaluator set consistency (replaces import-time asserts)
# ---------------------------------------------------------------------------


class TestEvaluatorSetConsistency:
    """Verify that _AGENT_EVALUATORS and _TOOL_EVALUATORS are subsets of _BUILTIN_EVALUATORS."""

    def test_agent_evaluators_subset(self):
        from agent_framework_foundry._foundry_evals import _AGENT_EVALUATORS, _BUILTIN_EVALUATORS

        diff = _AGENT_EVALUATORS - set(_BUILTIN_EVALUATORS.values())
        assert not diff, f"_AGENT_EVALUATORS has names not in _BUILTIN_EVALUATORS: {diff}"

    def test_tool_evaluators_subset(self):
        from agent_framework_foundry._foundry_evals import _BUILTIN_EVALUATORS, _TOOL_EVALUATORS

        diff = _TOOL_EVALUATORS - set(_BUILTIN_EVALUATORS.values())
        assert not diff, f"_TOOL_EVALUATORS has names not in _BUILTIN_EVALUATORS: {diff}"


# ---------------------------------------------------------------------------
# r5 review: evaluate_traces with agent_id only
# ---------------------------------------------------------------------------


class TestEvaluateTracesAgentId:
    async def test_agent_id_only_path(self) -> None:
        """evaluate_traces with agent_id only builds azure_ai_traces data source."""
        from agent_framework_foundry._foundry_evals import evaluate_traces

        mock_client = MagicMock()

        mock_eval = MagicMock()
        mock_eval.id = "eval_aid"
        mock_client.evals.create = AsyncMock(return_value=mock_eval)

        mock_run = MagicMock()
        mock_run.id = "run_aid"
        mock_client.evals.runs.create = AsyncMock(return_value=mock_run)

        mock_completed = MagicMock()
        mock_completed.status = "completed"
        mock_completed.result_counts = _rc(passed=2)
        mock_completed.report_url = None
        mock_completed.per_testing_criteria_results = None
        mock_client.evals.runs.retrieve = AsyncMock(return_value=mock_completed)

        mock_client.evals.runs.output_items.list = AsyncMock(return_value=_AsyncPage([]))

        results = await evaluate_traces(
            agent_id="my-agent",
            client=mock_client,
            model="gpt-4o",
            lookback_hours=24,
        )
        assert results.status == "completed"

        run_call = mock_client.evals.runs.create.call_args
        ds = run_call.kwargs["data_source"]
        assert ds["type"] == "azure_ai_traces"
        assert ds["agent_id"] == "my-agent"
        assert ds["lookback_hours"] == 24
        assert "trace_ids" not in ds


# ---------------------------------------------------------------------------
# r5 review: _filter_tool_evaluators raises ValueError
# ---------------------------------------------------------------------------


class TestFilterToolEvaluatorsRaises:
    def test_all_tool_evaluators_no_tools_raises(self):
        """All tool evaluators + no items with tools → ValueError."""
        items = [EvalItem(conversation=[Message("user", ["Hi"]), Message("assistant", ["Hello"])])]
        with pytest.raises(ValueError, match="require tool definitions"):
            _filter_tool_evaluators(["builtin.tool_call_accuracy", "builtin.tool_selection"], items)


# ---------------------------------------------------------------------------
# r5 review: evaluate_foundry_target validates target dict
# ---------------------------------------------------------------------------


class TestEvaluateFoundryTargetValidation:
    async def test_target_without_type_raises(self) -> None:
        """target dict without 'type' key raises ValueError."""
        from agent_framework_foundry._foundry_evals import evaluate_foundry_target

        mock_client = MagicMock()
        with pytest.raises(ValueError, match="'type' key"):
            await evaluate_foundry_target(
                target={"name": "my-agent"},  # missing "type"
                test_queries=["Hello"],
                client=mock_client,
                model="gpt-4o",
            )
