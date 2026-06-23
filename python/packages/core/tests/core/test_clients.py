# Copyright (c) Microsoft. All rights reserved.


from typing import Any
from unittest.mock import patch

import pytest

from agent_framework import (
    GROUP_ANNOTATION_KEY,
    GROUP_TOKEN_COUNT_KEY,
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    SlidingWindowStrategy,
    SupportsChatGetResponse,
    ToolResultCompactionStrategy,
    TruncationStrategy,
    tool,
)


class _FixedTokenizer:
    def __init__(self, token_count: int) -> None:
        self.token_count = token_count

    def count_tokens(self, text: str) -> int:
        return self.token_count


def test_chat_client_type(client: SupportsChatGetResponse):
    assert isinstance(client, SupportsChatGetResponse)


async def test_chat_client_get_response(client: SupportsChatGetResponse):
    response = await client.get_response([Message(role="user", contents=["Hello"])])
    assert response.text == "test response"
    assert response.messages[0].role == "assistant"


async def test_chat_client_get_response_streaming(client: SupportsChatGetResponse):
    async for update in client.get_response([Message(role="user", contents=["Hello"])], stream=True):
        assert update.text == "test streaming response " or update.text == "another update"
        assert update.role == "assistant"


def test_base_client(chat_client_base: SupportsChatGetResponse):
    assert isinstance(chat_client_base, BaseChatClient)
    assert isinstance(chat_client_base, SupportsChatGetResponse)


def test_base_client_rejects_direct_additional_properties(chat_client_base: SupportsChatGetResponse) -> None:
    with pytest.raises(TypeError):
        type(chat_client_base)(legacy_key="legacy-value")  # type: ignore[call-arg]  # pyrefly: ignore[bad-instantiation, unexpected-keyword]  # ty: ignore[unknown-argument]


def test_base_client_as_agent_uses_explicit_additional_properties(chat_client_base: SupportsChatGetResponse) -> None:
    agent = chat_client_base.as_agent(additional_properties={"team": "core"})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    assert agent.additional_properties == {"team": "core"}


def test_base_client_as_agent_rejects_function_invocation_configuration(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    with pytest.raises(
        TypeError,
        match=r"as_agent\(\) got an unexpected keyword argument 'function_invocation_configuration'",
    ):
        chat_client_base.as_agent(function_invocation_configuration={"enabled": False})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]


async def test_base_client_get_response_uses_explicit_client_kwargs(chat_client_base: SupportsChatGetResponse) -> None:
    async def fake_inner_get_response(**kwargs):
        assert kwargs["trace_id"] == "trace-123"
        assert "function_invocation_kwargs" not in kwargs
        return ChatResponse(messages=[Message(role="assistant", contents=["ok"])])

    with patch.object(
        chat_client_base,
        "_inner_get_response",
        side_effect=fake_inner_get_response,
    ) as mock_inner_get_response:
        await chat_client_base.get_response(
            [Message(role="user", contents=["hello"])],
            function_invocation_kwargs={"tool_request_id": "tool-123"},
            client_kwargs={"trace_id": "trace-123"},
        )
        mock_inner_get_response.assert_called_once()


async def test_base_client_get_response(chat_client_base: SupportsChatGetResponse):
    response = await chat_client_base.get_response([Message(role="user", contents=["Hello"])])
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "test response - Hello"


async def test_base_client_get_response_streaming(chat_client_base: SupportsChatGetResponse):
    async for update in chat_client_base.get_response([Message(role="user", contents=["Hello"])], stream=True):
        assert update.text == "update - Hello" or update.text == "another update"


async def test_base_client_applies_compaction_before_non_streaming_inner_call(
    chat_client_base: SupportsChatGetResponse,
):
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.compaction_strategy = TruncationStrategy(max_n=1, compact_to=1)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    captured_roles: list[list[str]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    async def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        captured_roles.append([message.role for message in messages])
        return await original(messages=messages, options=options, **kwargs)

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined, method-assign]  # ty: ignore[unresolved-attribute]
    await chat_client_base.get_response([
        Message(role="user", contents=["Hello"]),
        Message(role="assistant", contents=["Previous response"]),
    ])
    assert captured_roles == [["assistant"]]


async def test_base_client_applies_compaction_before_streaming_inner_call(
    chat_client_base: SupportsChatGetResponse,
):
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.compaction_strategy = TruncationStrategy(max_n=1, compact_to=1)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    captured_roles: list[list[str]] = []
    original = chat_client_base._get_streaming_response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ):
        captured_roles.append([message.role for message in messages])
        return original(messages=messages, options=options, **kwargs)

    chat_client_base._get_streaming_response = _capture  # type: ignore[attr-defined, method-assign]  # ty: ignore[unresolved-attribute]
    async for _ in chat_client_base.get_response(
        [
            Message(role="user", contents=["Hello"]),
            Message(role="assistant", contents=["Previous response"]),
        ],
        stream=True,
    ):
        pass
    assert captured_roles == [["assistant"]]


async def test_base_client_per_call_compaction_override_applies_before_inner_call(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    captured_roles: list[list[str]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    async def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        captured_roles.append([message.role for message in messages])
        return await original(messages=messages, options=options, **kwargs)

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined, method-assign]  # ty: ignore[unresolved-attribute]
    await chat_client_base.get_response(
        [
            Message(role="user", contents=["Hello"]),
            Message(role="assistant", contents=["Previous response"]),
        ],
        compaction_strategy=TruncationStrategy(max_n=1, compact_to=1),
    )
    assert captured_roles == [["assistant"]]


async def test_base_client_per_call_tokenizer_override_annotates_messages(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    captured_token_counts: list[list[int | None]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

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

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined, method-assign]  # ty: ignore[unresolved-attribute]
    await chat_client_base.get_response(
        [
            Message(role="user", contents=["Hello"]),
            Message(role="assistant", contents=["Previous response"]),
        ],
        compaction_strategy=SlidingWindowStrategy(keep_last_groups=2),
        tokenizer=_FixedTokenizer(17),
    )
    assert captured_token_counts == [[17, 17]]


async def test_base_client_per_call_tokenizer_override_without_strategy_annotates_messages(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    captured_token_counts: list[list[int | None]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

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

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined, method-assign]  # ty: ignore[unresolved-attribute]
    await chat_client_base.get_response(
        [
            Message(role="user", contents=["Hello"]),
            Message(role="assistant", contents=["Previous response"]),
        ],
        tokenizer=_FixedTokenizer(17),
    )
    assert captured_token_counts == [[17, 17]]


async def test_base_client_default_tokenizer_without_strategy_annotates_messages(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.function_invocation_configuration["enabled"] = False  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.tokenizer = _FixedTokenizer(19)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    captured_token_counts: list[list[int | None]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

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

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined, method-assign]  # ty: ignore[unresolved-attribute]
    await chat_client_base.get_response([
        Message(role="user", contents=["Hello"]),
        Message(role="assistant", contents=["Previous response"]),
    ])
    assert captured_token_counts == [[19, 19]]


def _tool_call_response(call_id: str, location: str) -> ChatResponse:
    return ChatResponse(
        messages=Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id=call_id,
                    name="lookup_weather",
                    arguments=f'{{"location": "{location}"}}',
                )
            ],
        ),
        response_id=f"resp_{call_id}",
    )


def _is_tool_result_summary(message: Message) -> bool:
    text = message.text or ""
    return message.role == "assistant" and text.startswith("[Tool results:")


async def test_function_loop_persists_inserted_summaries_across_iterations(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    # Regression test for #4991: compaction inserts summary messages and excludes the
    # originals. Across tool-loop iterations the exclusion flags persisted (shared Message
    # objects) but the inserted summaries were dropped (they only lived on a throwaway copy),
    # so older tool groups were silently lost with no summary representing them.
    chat_client_base.function_invocation_configuration["enabled"] = True  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.function_invocation_configuration["max_iterations"] = 3  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.compaction_strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=1)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    @tool(name="lookup_weather", approval_mode="never_require")
    def lookup_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    chat_client_base.run_responses = [  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        _tool_call_response("call_1", "London"),
        _tool_call_response("call_2", "Paris"),
        _tool_call_response("call_3", "Tokyo"),
    ]

    captured_inputs: list[list[Message]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    async def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        captured_inputs.append(list(messages))
        return await original(messages=messages, options=options, **kwargs)

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined, method-assign]  # ty: ignore[unresolved-attribute]

    await chat_client_base.get_response(
        [Message(role="user", contents=["What is the weather in London?"])],
        options={"tools": [lookup_weather]},  # type: ignore[typeddict-unknown-key]
    )

    # The final model call should represent every compacted tool group with a summary.
    # Two older tool groups get collapsed (London, Paris) while the last (Tokyo) is kept.
    final_input = captured_inputs[-1]
    summaries = [message for message in final_input if _is_tool_result_summary(message)]
    summary_text = " ".join(message.text or "" for message in summaries)

    assert len(summaries) == 2, [message.text for message in final_input]
    assert "London" in summary_text
    assert "Paris" in summary_text


def _tool_call_update(call_id: str, location: str) -> list[ChatResponseUpdate]:
    return [
        ChatResponseUpdate(
            contents=[
                Content.from_function_call(
                    call_id=call_id,
                    name="lookup_weather",
                    arguments=f'{{"location": "{location}"}}',
                )
            ],
            role="assistant",
            finish_reason="stop",
            response_id=f"resp_{call_id}",
        )
    ]


async def test_function_loop_persists_inserted_summaries_across_iterations_streaming(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    # Streaming counterpart of the #4991 regression test: the summary persistence fix in
    # ``_prepare_messages_for_model_call`` must cover the streaming tool loop too.
    chat_client_base.function_invocation_configuration["enabled"] = True  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.function_invocation_configuration["max_iterations"] = 3  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.compaction_strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=1)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    @tool(name="lookup_weather", approval_mode="never_require")
    def lookup_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    chat_client_base.streaming_responses = [  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        _tool_call_update("call_1", "London"),
        _tool_call_update("call_2", "Paris"),
        _tool_call_update("call_3", "Tokyo"),
    ]

    captured_inputs: list[list[Message]] = []
    original = chat_client_base._get_streaming_response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ):
        captured_inputs.append(list(messages))
        return original(messages=messages, options=options, **kwargs)

    chat_client_base._get_streaming_response = _capture  # type: ignore[attr-defined, method-assign]  # ty: ignore[unresolved-attribute]

    stream = chat_client_base.get_response(
        [Message(role="user", contents=["What is the weather in London?"])],
        stream=True,
        options={"tools": [lookup_weather]},  # type: ignore[typeddict-unknown-key]
    )
    async for _ in stream:
        pass

    final_input = captured_inputs[-1]
    summaries = [message for message in final_input if _is_tool_result_summary(message)]
    summary_text = " ".join(message.text or "" for message in summaries)

    assert len(summaries) == 2, [message.text for message in final_input]
    assert "London" in summary_text
    assert "Paris" in summary_text


async def test_function_loop_compaction_conversation_id_mode_does_not_resend_history(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    # In conversation-id mode the server owns prior context, so the tool loop clears
    # ``prepped_messages`` and only sends the latest message. Compaction must not fight that
    # by re-inserting summaries or re-sending earlier turns.
    chat_client_base.function_invocation_configuration["enabled"] = True  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.function_invocation_configuration["max_iterations"] = 3  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.compaction_strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=1)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    @tool(name="lookup_weather", approval_mode="never_require")
    def lookup_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    def _conversation_tool_call(call_id: str, location: str) -> ChatResponse:
        response = _tool_call_response(call_id, location)
        response.conversation_id = "conv_1"
        return response

    chat_client_base.run_responses = [  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        _conversation_tool_call("call_1", "London"),
        _conversation_tool_call("call_2", "Paris"),
        _conversation_tool_call("call_3", "Tokyo"),
    ]

    captured_inputs: list[list[Message]] = []
    original = chat_client_base._get_non_streaming_response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    async def _capture(
        *,
        messages: list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        captured_inputs.append(list(messages))
        return await original(messages=messages, options=options, **kwargs)

    chat_client_base._get_non_streaming_response = _capture  # type: ignore[attr-defined, method-assign]  # ty: ignore[unresolved-attribute]

    await chat_client_base.get_response(
        [Message(role="user", contents=["What is the weather in London?"])],
        options={"tools": [lookup_weather]},  # type: ignore[typeddict-unknown-key]
    )

    # After the conversation id is established the loop only forwards the latest message,
    # so subsequent model calls never receive the full history or summary messages.
    for sent in captured_inputs[1:]:
        assert len(sent) <= 1, [message.text for message in sent]
        assert not any(_is_tool_result_summary(message) for message in sent)


def test_base_client_as_agent_does_not_copy_client_compaction_defaults(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    strategy = TruncationStrategy(max_n=1, compact_to=1)
    tokenizer = _FixedTokenizer(11)
    chat_client_base.compaction_strategy = strategy  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    chat_client_base.tokenizer = tokenizer  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    agent = chat_client_base.as_agent(name="shared-client-agent")  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    assert agent.compaction_strategy is None  # type: ignore[attr-defined]
    assert agent.tokenizer is None  # type: ignore[attr-defined]


async def test_chat_client_instructions_handling(chat_client_base: SupportsChatGetResponse):
    instructions = "You are a helpful assistant."

    async def fake_inner_get_response(**kwargs):
        return ChatResponse(messages=[Message(role="assistant", contents=["ok"])])

    with patch.object(
        chat_client_base,
        "_inner_get_response",
        side_effect=fake_inner_get_response,
    ) as mock_inner_get_response:
        await chat_client_base.get_response(
            [Message(role="user", contents=["hello"])], options={"instructions": instructions}
        )
        mock_inner_get_response.assert_called_once()
        _, kwargs = mock_inner_get_response.call_args
        messages = kwargs.get("messages", [])
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].text == "hello"

        from agent_framework._types import prepend_instructions_to_messages

        appended_messages = prepend_instructions_to_messages(
            [Message(role="user", contents=["hello"])],
            instructions,
        )
        assert len(appended_messages) == 2
        assert appended_messages[0].role == "system"
        assert appended_messages[0].text == "You are a helpful assistant."
        assert appended_messages[1].role == "user"
        assert appended_messages[1].text == "hello"
