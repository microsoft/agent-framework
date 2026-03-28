# Copyright (c) Microsoft. All rights reserved.


from typing import Any
from unittest.mock import patch

import pytest

from agent_framework import (
    GROUP_ANNOTATION_KEY,
    GROUP_TOKEN_COUNT_KEY,
    BaseChatClient,
    ChatResponse,
    Message,
    SlidingWindowStrategy,
    SupportsChatGetResponse,
    TruncationStrategy,
)


class _FixedTokenizer:
    def __init__(self, token_count: int) -> None:
        self.token_count = token_count

    def count_tokens(self, text: str) -> int:
        return self.token_count


def test_chat_client_type(client: SupportsChatGetResponse):
    assert isinstance(client, SupportsChatGetResponse)


async def test_chat_client_get_response(client: SupportsChatGetResponse):
    response = await client.get_response([Message(role="user", text="Hello")])
    assert response.text == "test response"
    assert response.messages[0].role == "assistant"


async def test_chat_client_get_response_streaming(client: SupportsChatGetResponse):
    async for update in client.get_response([Message(role="user", text="Hello")], stream=True):
        assert update.text == "test streaming response " or update.text == "another update"
        assert update.role == "assistant"


def test_base_client(chat_client_base: SupportsChatGetResponse):
    assert isinstance(chat_client_base, BaseChatClient)
    assert isinstance(chat_client_base, SupportsChatGetResponse)


def test_base_client_rejects_direct_additional_properties(chat_client_base: SupportsChatGetResponse) -> None:
    with pytest.raises(TypeError):
        type(chat_client_base)(legacy_key="legacy-value")


def test_base_client_as_agent_uses_explicit_additional_properties(chat_client_base: SupportsChatGetResponse) -> None:
    agent = chat_client_base.as_agent(additional_properties={"team": "core"})

    assert agent.additional_properties == {"team": "core"}


async def test_base_client_get_response_uses_explicit_client_kwargs(chat_client_base: SupportsChatGetResponse) -> None:
    async def fake_inner_get_response(**kwargs):
        assert kwargs["trace_id"] == "trace-123"
        assert "function_invocation_kwargs" not in kwargs
        return ChatResponse(messages=[Message(role="assistant", text="ok")])

    with patch.object(
        chat_client_base,
        "_inner_get_response",
        side_effect=fake_inner_get_response,
    ) as mock_inner_get_response:
        await chat_client_base.get_response(
            [Message(role="user", text="hello")],
            function_invocation_kwargs={"tool_request_id": "tool-123"},
            client_kwargs={"trace_id": "trace-123"},
        )
        mock_inner_get_response.assert_called_once()


async def test_base_client_get_response(chat_client_base: SupportsChatGetResponse):
    response = await chat_client_base.get_response([Message(role="user", text="Hello")])
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "test response - Hello"


async def test_base_client_get_response_streaming(chat_client_base: SupportsChatGetResponse):
    async for update in chat_client_base.get_response([Message(role="user", text="Hello")], stream=True):
        assert update.text == "update - Hello" or update.text == "another update"


async def test_base_client_applies_compaction_before_non_streaming_inner_call(
    chat_client_base: SupportsChatGetResponse,
):
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]
    chat_client_base.compaction_strategy = TruncationStrategy(max_n=1, compact_to=1)  # type: ignore[attr-defined]
    captured_roles: list[list[str]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]

    async def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        captured_roles.append([message.role for message in messages])
        return await original(messages=messages, options=options, **kwargs)

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined,method-assign]
    await chat_client_base.get_response([
        Message(role="user", text="Hello"),
        Message(role="assistant", text="Previous response"),
    ])
    assert captured_roles == [["assistant"]]


async def test_base_client_applies_compaction_before_streaming_inner_call(
    chat_client_base: SupportsChatGetResponse,
):
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]
    chat_client_base.compaction_strategy = TruncationStrategy(max_n=1, compact_to=1)  # type: ignore[attr-defined]
    captured_roles: list[list[str]] = []
    original = chat_client_base._get_streaming_response  # type: ignore[attr-defined]

    def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ):
        captured_roles.append([message.role for message in messages])
        return original(messages=messages, options=options, **kwargs)

    chat_client_base._get_streaming_response = _capture  # type: ignore[attr-defined,method-assign]
    async for _ in chat_client_base.get_response(
        [
            Message(role="user", text="Hello"),
            Message(role="assistant", text="Previous response"),
        ],
        stream=True,
    ):
        pass
    assert captured_roles == [["assistant"]]


async def test_base_client_per_call_compaction_override_applies_before_inner_call(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]
    captured_roles: list[list[str]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]

    async def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        captured_roles.append([message.role for message in messages])
        return await original(messages=messages, options=options, **kwargs)

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined,method-assign]
    await chat_client_base.get_response(
        [
            Message(role="user", text="Hello"),
            Message(role="assistant", text="Previous response"),
        ],
        compaction_strategy=TruncationStrategy(max_n=1, compact_to=1),
    )
    assert captured_roles == [["assistant"]]


async def test_base_client_per_call_tokenizer_override_annotates_messages(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]
    captured_token_counts: list[list[int | None]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]

    async def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        captured_token_counts.append([
            group.get(GROUP_TOKEN_COUNT_KEY) if isinstance(group, dict) else None
            for group in (message.additional_properties.get(GROUP_ANNOTATION_KEY) for message in messages)
        ])
        return await original(messages=messages, options=options, **kwargs)

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined,method-assign]
    await chat_client_base.get_response(
        [
            Message(role="user", text="Hello"),
            Message(role="assistant", text="Previous response"),
        ],
        compaction_strategy=SlidingWindowStrategy(keep_last_groups=2),
        tokenizer=_FixedTokenizer(17),
    )
    assert captured_token_counts == [[17, 17]]


async def test_base_client_per_call_tokenizer_override_without_strategy_annotates_messages(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]
    captured_token_counts: list[list[int | None]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]

    async def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        captured_token_counts.append([
            group.get(GROUP_TOKEN_COUNT_KEY) if isinstance(group, dict) else None
            for group in (message.additional_properties.get(GROUP_ANNOTATION_KEY) for message in messages)
        ])
        return await original(messages=messages, options=options, **kwargs)

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined,method-assign]
    await chat_client_base.get_response(
        [
            Message(role="user", text="Hello"),
            Message(role="assistant", text="Previous response"),
        ],
        tokenizer=_FixedTokenizer(17),
    )
    assert captured_token_counts == [[17, 17]]


async def test_base_client_default_tokenizer_without_strategy_annotates_messages(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]
    chat_client_base.tokenizer = _FixedTokenizer(19)  # type: ignore[attr-defined]
    captured_token_counts: list[list[int | None]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]

    async def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        captured_token_counts.append([
            group.get(GROUP_TOKEN_COUNT_KEY) if isinstance(group, dict) else None
            for group in (message.additional_properties.get(GROUP_ANNOTATION_KEY) for message in messages)
        ])
        return await original(messages=messages, options=options, **kwargs)

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined,method-assign]
    await chat_client_base.get_response([
        Message(role="user", text="Hello"),
        Message(role="assistant", text="Previous response"),
    ])
    assert captured_token_counts == [[19, 19]]


def test_base_client_as_agent_does_not_copy_client_compaction_defaults(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    strategy = TruncationStrategy(max_n=1, compact_to=1)
    tokenizer = _FixedTokenizer(11)
    chat_client_base.compaction_strategy = strategy  # type: ignore[attr-defined]
    chat_client_base.tokenizer = tokenizer  # type: ignore[attr-defined]

    agent = chat_client_base.as_agent(name="shared-client-agent")

    assert agent.compaction_strategy is None  # type: ignore[attr-defined]
    assert agent.tokenizer is None  # type: ignore[attr-defined]


async def test_chat_client_instructions_handling(chat_client_base: SupportsChatGetResponse):
    instructions = "You are a helpful assistant."

    async def fake_inner_get_response(**kwargs):
        return ChatResponse(messages=[Message(role="assistant", text="ok")])

    with patch.object(
        chat_client_base,
        "_inner_get_response",
        side_effect=fake_inner_get_response,
    ) as mock_inner_get_response:
        await chat_client_base.get_response(
            [Message(role="user", text="hello")], options={"instructions": instructions}
        )
        mock_inner_get_response.assert_called_once()
        _, kwargs = mock_inner_get_response.call_args
        messages = kwargs.get("messages", [])
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].text == "hello"

        from agent_framework._types import prepend_instructions_to_messages

        appended_messages = prepend_instructions_to_messages(
            [Message(role="user", text="hello")],
            instructions,
        )
        assert len(appended_messages) == 2
        assert appended_messages[0].role == "system"
        assert appended_messages[0].text == "You are a helpful assistant."
        assert appended_messages[1].role == "user"
        assert appended_messages[1].text == "hello"
