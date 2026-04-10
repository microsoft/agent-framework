# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import Content, FunctionTool, Message
from google.genai import types
from pydantic import BaseModel

from agent_framework_gemini import GeminiChatClient, GeminiChatOptions, ThinkingConfig

skip_if_no_api_key = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set; skipping integration tests.",
)

_TEST_MODEL = "gemini-2.5-flash"

# stub helpers


def _make_part(
    *,
    text: str | None = None,
    thought: bool = False,
    function_call: tuple[str, str, dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock types.Part.

    Args:
        text: Text content of the part.
        thought: Whether this is a thinking/reasoning part.
        function_call: Tuple of (id, name, args) if this is a function call part.
    """
    part = MagicMock()
    part.text = text
    part.thought = thought
    part.function_response = None

    if function_call:
        mock_function_call = MagicMock()
        mock_function_call.id, mock_function_call.name, mock_function_call.args = function_call
        part.function_call = mock_function_call
    else:
        part.function_call = None

    return part


def _make_response(
    parts: list[MagicMock],
    *,
    finish_reason: str | None = "STOP",
    model_version: str = "gemini-2.5-flash-001",
    prompt_tokens: int | None = 10,
    output_tokens: int | None = 5,
    total_tokens: int | None = 15,
) -> MagicMock:
    """Build a mock types.GenerateContentResponse."""
    response = MagicMock()
    candidate = MagicMock()
    candidate.content.parts = parts

    if finish_reason:
        candidate.finish_reason.name = finish_reason
    else:
        candidate.finish_reason = None

    response.candidates = [candidate]
    response.model_version = model_version

    if prompt_tokens is not None or output_tokens is not None:
        usage = MagicMock()
        usage.prompt_token_count = prompt_tokens
        usage.candidates_token_count = output_tokens
        usage.total_token_count = total_tokens
        response.usage_metadata = usage
    else:
        response.usage_metadata = None

    return response


async def _async_iter(items: list[Any]):
    """Async generator used to simulate generate_content_stream results."""
    for item in items:
        yield item


def _make_gemini_client(
    model: str = "gemini-2.5-flash",
    mock_client: MagicMock | None = None,
) -> tuple[GeminiChatClient, MagicMock]:
    """Return a (GeminiChatClient, mock_genai_client) pair."""
    mock = mock_client or MagicMock()
    client = GeminiChatClient(client=mock, model=model)
    return client, mock


# settings & initialisation


def test_model_stored_on_instance() -> None:
    client, _ = _make_gemini_client(model="gemini-2.5-pro")
    assert client.model == "gemini-2.5-pro"


def test_client_created_from_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    client = GeminiChatClient(model="gemini-2.5-flash")
    assert client.model == "gemini-2.5-flash"


def test_missing_api_key_raises_when_no_client_injected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiChatClient(model="gemini-2.5-flash")


async def test_missing_model_raises_on_get_response() -> None:
    client, mock = _make_gemini_client(model=None)  # type: ignore[arg-type]
    mock.aio.models.generate_content = AsyncMock()

    with pytest.raises(ValueError, match="model"):
        await client.get_response(messages=[Message(role="user", contents=[Content.from_text("hi")])])


# text response


async def test_get_response_returns_text() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hello!")]))

    response = await client.get_response(messages=[Message(role="user", contents=[Content.from_text("Hi")])])

    assert response.messages[0].text == "Hello!"


async def test_get_response_model_from_response() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(
        return_value=_make_response([_make_part(text="Hi")], model_version="gemini-2.5-pro-002")
    )

    response = await client.get_response(messages=[Message(role="user", contents=[Content.from_text("Hi")])])

    assert response.model == "gemini-2.5-pro-002"


async def test_get_response_uses_model_from_options() -> None:
    client, mock = _make_gemini_client(model="gemini-2.5-flash")
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"model": "gemini-2.5-pro"},
    )

    call_kwargs = mock.aio.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-pro"


async def test_get_response_usage_details() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(
        return_value=_make_response(
            [_make_part(text="Hi")],
            prompt_tokens=20,
            output_tokens=8,
            total_tokens=28,
        )
    )

    response = await client.get_response(messages=[Message(role="user", contents=[Content.from_text("Hi")])])

    assert response.usage_details is not None
    assert response.usage_details["input_token_count"] == 20
    assert response.usage_details["output_token_count"] == 8
    assert response.usage_details["total_token_count"] == 28


async def test_get_response_no_usage_when_metadata_absent() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(
        return_value=_make_response([_make_part(text="Hi")], prompt_tokens=None, output_tokens=None)
    )

    response = await client.get_response(messages=[Message(role="user", contents=[Content.from_text("Hi")])])

    assert not response.usage_details


# finish reasons


@pytest.mark.parametrize(
    ("gemini_reason", "expected"),
    [
        ("STOP", "stop"),
        ("MAX_TOKENS", "length"),
        ("SAFETY", "content_filter"),
        ("RECITATION", "content_filter"),
        ("BLOCKLIST", "content_filter"),
        ("PROHIBITED_CONTENT", "content_filter"),
        ("SPII", "content_filter"),
        ("MALFORMED_FUNCTION_CALL", "tool_calls"),
        ("OTHER", None),
    ],
)
async def test_finish_reason_mapping(gemini_reason: str, expected: str | None) -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(
        return_value=_make_response([_make_part(text="Hi")], finish_reason=gemini_reason)
    )

    response = await client.get_response(messages=[Message(role="user", contents=[Content.from_text("Hi")])])

    assert response.finish_reason == expected


# message conversion


async def test_system_message_extracted_to_system_instruction() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[
            Message(role="system", contents=[Content.from_text("You are concise.")]),
            Message(role="user", contents=[Content.from_text("Hi")]),
        ]
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.system_instruction == "You are concise."


async def test_multiple_system_messages_concatenated() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[
            Message(role="system", contents=[Content.from_text("Be concise.")]),
            Message(role="system", contents=[Content.from_text("Use bullet points.")]),
            Message(role="user", contents=[Content.from_text("Hi")]),
        ]
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert "Be concise." in config.system_instruction
    assert "Use bullet points." in config.system_instruction


async def test_instructions_option_merged_with_system_instruction() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[
            Message(role="system", contents=[Content.from_text("Be concise.")]),
            Message(role="user", contents=[Content.from_text("Hi")]),
        ],
        options={"instructions": "Always respond in French."},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert "Always respond in French." in config.system_instruction
    assert "Be concise." in config.system_instruction


async def test_instructions_option_without_system_message() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"instructions": "Be helpful."},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.system_instruction == "Be helpful."


async def test_assistant_role_mapped_to_model() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Sure")]))

    await client.get_response(
        messages=[
            Message(role="user", contents=[Content.from_text("Hello")]),
            Message(role="assistant", contents=[Content.from_text("Hi there")]),
            Message(role="user", contents=[Content.from_text("Follow up")]),
        ]
    )

    contents: list[types.Content] = mock.aio.models.generate_content.call_args.kwargs["contents"]
    roles = [c.role for c in contents]
    assert roles == ["user", "model", "user"]


async def test_tool_messages_collapsed_into_single_user_message() -> None:
    """Consecutive tool messages must be collapsed into one role='user' message
    with multiple functionResponse parts (parallel tool call pattern).
    """
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Done")]))

    await client.get_response(
        messages=[
            Message(role="user", contents=[Content.from_text("Run both")]),
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="c1", name="tool_a", arguments={}),
                    Content.from_function_call(call_id="c2", name="tool_b", arguments={}),
                ],
            ),
            Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="res_a")]),
            Message(role="tool", contents=[Content.from_function_result(call_id="c2", result="res_b")]),
        ]
    )

    contents: list[types.Content] = mock.aio.models.generate_content.call_args.kwargs["contents"]
    # user, model (with 2 function calls), user (with 2 function responses)
    assert contents[-1].role == "user"
    assert len(contents[-1].parts) == 2


async def test_function_result_name_resolved_from_call_history() -> None:
    """function_result name must come from the matching function_call in history."""
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Done")]))

    await client.get_response(
        messages=[
            Message(role="user", contents=[Content.from_text("Go")]),
            Message(
                role="assistant",
                contents=[Content.from_function_call(call_id="call-42", name="get_weather", arguments={})],
            ),
            Message(role="tool", contents=[Content.from_function_result(call_id="call-42", result="sunny")]),
        ]
    )

    contents: list[types.Content] = mock.aio.models.generate_content.call_args.kwargs["contents"]
    tool_user_msg = contents[-1]
    assert tool_user_msg.role == "user"
    function_response = tool_user_msg.parts[0].function_response
    assert function_response.name == "get_weather"
    assert function_response.id == "call-42"


async def test_function_result_resolved_when_call_id_was_generated() -> None:
    """When a function_call has no call_id and a fallback is generated, the subsequent
    function_result referencing that generated ID must still resolve the function name.
    """
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Done")]))

    generated_id = "tool-call-generated-123"
    with patch.object(client, "_generate_tool_call_id", return_value=generated_id):
        await client.get_response(
            messages=[
                Message(role="user", contents=[Content.from_text("Go")]),
                Message(
                    role="assistant",
                    contents=[Content.from_function_call(call_id=None, name="get_weather", arguments={})],  # type: ignore[arg-type]
                ),
                Message(
                    role="tool",
                    contents=[Content.from_function_result(call_id=generated_id, result="sunny")],
                ),
            ]
        )

    contents: list[types.Content] = mock.aio.models.generate_content.call_args.kwargs["contents"]
    tool_turn = next(c for c in contents if c.role == "user" and any(p.function_response for p in c.parts))
    assert tool_turn.parts[0].function_response.name == "get_weather"
    assert tool_turn.parts[0].function_response.id == generated_id


async def test_function_result_without_matching_call_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    """A function_result with no prior function_call in history should be skipped with a warning."""
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Done")]))

    with caplog.at_level(logging.WARNING, logger="agent_framework.gemini"):
        await client.get_response(
            messages=[
                Message(role="user", contents=[Content.from_text("Go")]),
                Message(
                    role="tool",
                    contents=[Content.from_function_result(call_id="unknown-id", result="oops")],
                ),
                Message(role="user", contents=[Content.from_text("What happened?")]),
            ]
        )

    assert any("unknown-id" in r.message or "function_result" in r.message.lower() for r in caplog.records)


async def test_message_with_only_unsupported_content_type_is_skipped() -> None:
    """A user message whose contents produce no convertible parts is dropped from the request."""
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Done")]))

    await client.get_response(
        messages=[
            Message(role="user", contents=[Content.from_function_result(call_id="x", result="y")]),
            Message(role="user", contents=[Content.from_text("Follow up")]),
        ]
    )

    contents: list[types.Content] = mock.aio.models.generate_content.call_args.kwargs["contents"]
    assert len(contents) == 1
    assert contents[0].parts[0].text == "Follow up"


async def test_non_function_result_content_in_tool_message_is_skipped() -> None:
    """Unexpected content types inside a tool message are silently ignored."""
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Done")]))

    await client.get_response(
        messages=[
            Message(role="user", contents=[Content.from_text("Hi")]),
            Message(role="tool", contents=[Content.from_text("unexpected")]),
        ]
    )

    contents: list[types.Content] = mock.aio.models.generate_content.call_args.kwargs["contents"]
    assert len(contents) == 1


# thinking parts


async def test_thinking_parts_are_silently_skipped() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(
        return_value=_make_response([
            _make_part(text="I should think first...", thought=True),
            _make_part(text="The answer is 42."),
        ])
    )

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("What is the answer?")])]
    )

    assert len(response.messages[0].contents) == 1
    assert response.messages[0].text == "The answer is 42."


# generation config options


async def test_prepare_config_temperature() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"temperature": 0.3},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.temperature == 0.3


async def test_prepare_config_max_tokens() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"max_tokens": 512},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.max_output_tokens == 512


async def test_prepare_config_top_p_and_top_k() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"top_p": 0.9, "top_k": 40},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.top_p == 0.9
    assert config.top_k == 40


async def test_prepare_config_stop_sequences() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"stop": ["END", "STOP"]},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.stop_sequences == ["END", "STOP"]


async def test_prepare_config_seed() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"seed": 42},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.seed == 42


async def test_prepare_config_frequency_and_presence_penalty() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"frequency_penalty": 0.5, "presence_penalty": 0.2},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.frequency_penalty == 0.5
    assert config.presence_penalty == 0.2


# thinking config


async def test_thinking_config_budget() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))
    tc: ThinkingConfig = {"thinking_budget": 1024}

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"thinking_config": tc},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert isinstance(config.thinking_config, types.ThinkingConfig)
    assert config.thinking_config.thinking_budget == 1024


async def test_thinking_config_level() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))
    tc: ThinkingConfig = {"thinking_level": types.ThinkingLevel.HIGH}

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"thinking_config": tc},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert isinstance(config.thinking_config, types.ThinkingConfig)
    assert config.thinking_config.thinking_level == types.ThinkingLevel.HIGH


# structured output


async def test_response_format_sets_json_mime_type() -> None:
    from pydantic import BaseModel

    class Reply(BaseModel):
        text: str

    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="{}")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"response_format": Reply},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"


async def test_response_format_populates_value_on_chat_response() -> None:
    """When response_format is a Pydantic model, ChatResponse.value must be parsed from the response text."""
    from pydantic import BaseModel

    class Reply(BaseModel):
        text: str

    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text='{"text": "hello"}')]))

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"response_format": Reply},
    )

    assert response.value == Reply(text="hello")


async def test_response_schema_added_to_config() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="{}")]))
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"response_schema": schema},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema == schema


async def test_streaming_response_format_passed_to_build_response_stream() -> None:
    """Verifies that response_format is forwarded to _build_response_stream when streaming
    so that structured output parsing works correctly on the final assembled response.
    """
    from unittest.mock import patch

    from pydantic import BaseModel

    class Reply(BaseModel):
        text: str

    client, mock = _make_gemini_client()
    chunks = [_make_response([_make_part(text='{"text": "hello"}')], finish_reason="STOP")]
    mock.aio.models.generate_content_stream = AsyncMock(return_value=_async_iter(chunks))

    with patch.object(client, "_build_response_stream", wraps=client._build_response_stream) as spy:
        stream = client.get_response(
            messages=[Message(role="user", contents=[Content.from_text("Hi")])],
            options={"response_format": Reply},
            stream=True,
        )
        async for _ in stream:
            pass

    _, kwargs = spy.call_args
    assert kwargs.get("response_format") is Reply


# tool calling


async def test_function_call_in_response_mapped_to_content() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(
        return_value=_make_response([_make_part(function_call=("call-1", "get_weather", {"city": "Berlin"}))])
    )

    response = await client.get_response(messages=[Message(role="user", contents=[Content.from_text("Weather?")])])

    fc = response.messages[0].contents[0]
    assert fc.type == "function_call"
    assert fc.name == "get_weather"
    assert fc.call_id == "call-1"


async def test_function_call_missing_id_gets_fallback() -> None:
    """Older Gemini models may omit function_call.id — a UUID fallback must be generated."""
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(
        return_value=_make_response([
            _make_part(function_call=(None, "search", {"q": "test"}))  # id is None
        ])
    )

    response = await client.get_response(messages=[Message(role="user", contents=[Content.from_text("Search")])])

    fc = response.messages[0].contents[0]
    assert fc.call_id is not None
    assert len(fc.call_id) > 0


async def test_function_tool_converted_to_function_declaration() -> None:
    def get_weather(city: str) -> str:
        """Get the weather for a city."""
        return "sunny"

    tool = FunctionTool(name="get_weather", func=get_weather)
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Done")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Weather?")])],
        options={"tools": [tool]},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.tools is not None
    assert len(config.tools) == 1
    function_declaration = config.tools[0].function_declarations[0]
    assert function_declaration.name == "get_weather"


async def test_callable_tool_resolved_via_validate_options() -> None:
    """Raw callables passed as tools must be normalized by _validate_options into FunctionTools
    and reach the Gemini config as function declarations.
    """

    def get_weather(city: str) -> str:
        """Get the weather for a city."""
        return "sunny"

    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Done")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Weather?")])],
        options={"tools": [get_weather]},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.tools is not None
    function_declaration = config.tools[0].function_declarations[0]
    assert function_declaration.name == "get_weather"


# _coerce_to_dict


def test_coerce_to_dict_with_dict_input() -> None:
    assert GeminiChatClient._coerce_to_dict({"key": "value"}) == {"key": "value"}


def test_coerce_to_dict_with_json_string() -> None:
    assert GeminiChatClient._coerce_to_dict('{"key": "value"}') == {"key": "value"}


def test_coerce_to_dict_with_plain_string() -> None:
    assert GeminiChatClient._coerce_to_dict("some text") == {"result": "some text"}


def test_coerce_to_dict_with_none() -> None:
    assert GeminiChatClient._coerce_to_dict(None) == {"result": ""}


def test_coerce_to_dict_with_numeric_value() -> None:
    assert GeminiChatClient._coerce_to_dict(42) == {"result": "42"}


def test_coerce_to_dict_with_json_array_string() -> None:
    assert GeminiChatClient._coerce_to_dict("[1, 2, 3]") == {"result": "[1, 2, 3]"}


def test_coerce_to_dict_with_json_string_literal() -> None:
    assert GeminiChatClient._coerce_to_dict('"hello"') == {"result": '"hello"'}


# tool choice


def _get_function_calling_mode(config: types.GenerateContentConfig) -> str:
    return config.tool_config.function_calling_config.mode


def _make_dummy_tool() -> FunctionTool:
    def dummy(x: int) -> int:
        """Dummy."""
        return x

    return FunctionTool(name="dummy", func=dummy)


async def _get_config_for_tool_choice(tool_choice: str) -> types.GenerateContentConfig:
    tool = _make_dummy_tool()
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={"tools": [tool], "tool_choice": tool_choice},
    )

    return mock.aio.models.generate_content.call_args.kwargs["config"]


async def test_tool_choice_auto_maps_to_AUTO() -> None:
    config = await _get_config_for_tool_choice("auto")
    assert _get_function_calling_mode(config) == "AUTO"


async def test_tool_choice_none_maps_to_NONE() -> None:
    config = await _get_config_for_tool_choice("none")
    assert _get_function_calling_mode(config) == "NONE"


async def test_tool_choice_required_maps_to_ANY() -> None:
    config = await _get_config_for_tool_choice("required")
    assert _get_function_calling_mode(config) == "ANY"


async def test_tool_choice_required_with_name_sets_allowed_function_names() -> None:
    tool = _make_dummy_tool()
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        options={
            "tools": [tool],
            "tool_choice": {"mode": "required", "required_function_name": "dummy"},
        },
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    function_calling_config = config.tool_config.function_calling_config
    assert function_calling_config.mode == "ANY"
    assert "dummy" in function_calling_config.allowed_function_names


async def test_unknown_tool_choice_mode_is_ignored() -> None:
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Hi")]))

    with patch("agent_framework_gemini._chat_client.validate_tool_mode", return_value={"mode": "unsupported"}):
        await client.get_response(
            messages=[Message(role="user", contents=[Content.from_text("Hi")])],
            options={"tool_choice": "auto"},
        )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert not hasattr(config, "tool_config") or config.tool_config is None


# built-in tool factories


def test_get_web_search_tool_returns_google_search_tool() -> None:
    """get_web_search_tool returns a types.Tool with google_search set."""
    tool = GeminiChatClient.get_web_search_tool()
    assert isinstance(tool, types.Tool)
    assert tool.google_search is not None


def test_get_web_search_tool_forwards_kwargs() -> None:
    """Keyword arguments are passed through to types.GoogleSearch."""
    tool = GeminiChatClient.get_web_search_tool(exclude_domains=["example.com"])
    assert tool.google_search is not None
    assert tool.google_search.exclude_domains == ["example.com"]


def test_get_code_interpreter_tool_returns_code_execution_tool() -> None:
    """get_code_interpreter_tool returns a types.Tool with code_execution set."""
    tool = GeminiChatClient.get_code_interpreter_tool()
    assert isinstance(tool, types.Tool)
    assert tool.code_execution is not None


def test_get_maps_grounding_tool_returns_google_maps_tool() -> None:
    """get_maps_grounding_tool returns a types.Tool with google_maps set."""
    tool = GeminiChatClient.get_maps_grounding_tool()
    assert isinstance(tool, types.Tool)
    assert tool.google_maps is not None


def test_get_maps_grounding_tool_forwards_kwargs() -> None:
    """Keyword arguments are passed through to types.GoogleMaps."""
    tool = GeminiChatClient.get_maps_grounding_tool(enable_widget=True)
    assert tool.google_maps is not None
    assert tool.google_maps.enable_widget is True


def test_get_file_search_tool_returns_file_search_tool() -> None:
    """get_file_search_tool returns a types.Tool with file_search set."""
    tool = GeminiChatClient.get_file_search_tool(file_search_store_names=["stores/my-store"])
    assert isinstance(tool, types.Tool)
    assert tool.file_search is not None
    assert tool.file_search.file_search_store_names == ["stores/my-store"]


def test_get_file_search_tool_forwards_kwargs() -> None:
    """Keyword arguments are passed through to types.FileSearch."""
    tool = GeminiChatClient.get_file_search_tool(
        file_search_store_names=["stores/my-store"],
        top_k=5,
        metadata_filter="type='pdf'",
    )
    assert tool.file_search is not None
    assert tool.file_search.top_k == 5
    assert tool.file_search.metadata_filter == "type='pdf'"


def test_get_mcp_tool_returns_mcp_server_tool() -> None:
    """get_mcp_tool returns a types.Tool with a single McpServer entry."""
    tool = GeminiChatClient.get_mcp_tool(name="my-mcp", url="https://mcp.example.com/sse")
    assert isinstance(tool, types.Tool)
    assert tool.mcp_servers is not None
    assert len(tool.mcp_servers) == 1
    server = tool.mcp_servers[0]
    assert server.name == "my-mcp"
    assert server.streamable_http_transport is not None
    assert server.streamable_http_transport.url == "https://mcp.example.com/sse"


def test_get_mcp_tool_forwards_transport_kwargs() -> None:
    """Transport keyword arguments are passed through to StreamableHttpTransport."""
    tool = GeminiChatClient.get_mcp_tool(
        name="secure-mcp",
        url="https://mcp.example.com/sse",
        headers={"Authorization": "Bearer token"},
    )
    server = tool.mcp_servers[0]  # type: ignore[index]
    assert server.streamable_http_transport.headers == {"Authorization": "Bearer token"}


async def test_types_tool_passed_in_tools_list_is_forwarded() -> None:
    """A types.Tool in the tools list is passed through directly to the Gemini config."""
    client, mock = _make_gemini_client()
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([_make_part(text="Result")]))
    search_tool = GeminiChatClient.get_web_search_tool()

    await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Search")])],
        options={"tools": [search_tool]},
    )

    config: types.GenerateContentConfig = mock.aio.models.generate_content.call_args.kwargs["config"]
    assert config.tools is not None
    assert any(tool.google_search for tool in config.tools)


async def test_function_response_part_in_response_mapped_to_content() -> None:
    """A function_response part echoed back in a model response is mapped to a function_result Content."""
    client, mock = _make_gemini_client()
    part = MagicMock()
    part.text = None
    part.thought = False
    part.function_call = None
    part.function_response = MagicMock()
    part.function_response.id = "call-99"
    part.function_response.response = {"result": "done"}
    mock.aio.models.generate_content = AsyncMock(return_value=_make_response([part]))

    response = await client.get_response(messages=[Message(role="user", contents=[Content.from_text("Hi")])])

    assert response.messages[0].contents[0].type == "function_result"


# streaming


async def test_streaming_yields_text_chunks() -> None:
    client, mock = _make_gemini_client()
    chunks = [
        _make_response([_make_part(text="Hello ")], finish_reason=None, prompt_tokens=None, output_tokens=None),
        _make_response([_make_part(text="world!")], finish_reason="STOP"),
    ]
    mock.aio.models.generate_content_stream = AsyncMock(return_value=_async_iter(chunks))

    stream = client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        stream=True,
    )

    updates = [update async for update in stream]
    text = "".join(u.text or "" for u in updates)
    assert "Hello" in text
    assert "world" in text


async def test_streaming_function_call_emitted_immediately() -> None:
    """Function calls in streaming chunks must be emitted as they arrive, not deferred."""
    client, mock = _make_gemini_client()
    chunks = [
        _make_response(
            [_make_part(function_call=("call-1", "search", {"q": "test"}))],
            finish_reason=None,
            prompt_tokens=None,
            output_tokens=None,
        ),
        _make_response([_make_part(text="Done")], finish_reason="STOP"),
    ]
    mock.aio.models.generate_content_stream = AsyncMock(return_value=_async_iter(chunks))

    stream = client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Search")])],
        stream=True,
    )

    all_contents = []
    async for update in stream:
        all_contents.extend(update.contents)

    function_calls = [c for c in all_contents if c.type == "function_call"]
    assert len(function_calls) == 1
    assert function_calls[0].name == "search"


async def test_streaming_finish_reason_only_on_last_chunk() -> None:
    client, mock = _make_gemini_client()
    chunks = [
        _make_response([_make_part(text="Hello ")], finish_reason=None, prompt_tokens=None, output_tokens=None),
        _make_response([_make_part(text="world!")], finish_reason="STOP"),
    ]
    mock.aio.models.generate_content_stream = AsyncMock(return_value=_async_iter(chunks))

    stream = client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        stream=True,
    )

    updates = [update async for update in stream]
    assert updates[0].finish_reason is None
    assert updates[-1].finish_reason == "stop"


async def test_streaming_usage_only_on_final_chunk() -> None:
    client, mock = _make_gemini_client()
    chunks = [
        _make_response([_make_part(text="Hello ")], finish_reason=None, prompt_tokens=None, output_tokens=None),
        _make_response([_make_part(text="world!")], finish_reason="STOP", prompt_tokens=10, output_tokens=5),
    ]
    mock.aio.models.generate_content_stream = AsyncMock(return_value=_async_iter(chunks))

    stream = client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        stream=True,
    )

    updates = [update async for update in stream]
    assert not any(c.type == "usage" for c in updates[0].contents)
    assert any(c.type == "usage" for c in updates[-1].contents)


async def test_streaming_get_final_response() -> None:
    """get_final_response() must return a fully assembled ChatResponse after the stream is exhausted."""
    client, mock = _make_gemini_client()
    chunks = [
        _make_response([_make_part(text="Hello ")], finish_reason=None, prompt_tokens=None, output_tokens=None),
        _make_response([_make_part(text="world!")], finish_reason="STOP", prompt_tokens=10, output_tokens=5),
    ]
    mock.aio.models.generate_content_stream = AsyncMock(return_value=_async_iter(chunks))

    stream = client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Hi")])],
        stream=True,
    )

    async for _ in stream:
        pass

    final = await stream.get_final_response()

    assert final.messages[0].text == "Hello world!"
    assert final.finish_reason == "stop"
    assert final.usage_details is not None
    assert final.usage_details["input_token_count"] == 10
    assert final.usage_details["output_token_count"] == 5


# The Gemini API returns a list of candidates, each representing a possible response from the model.
# In practice only one candidate is returned, but the list can be empty or None if the request
# was blocked by safety filters or the API returned an unexpected response.


@pytest.mark.parametrize("candidates", [None, []])
async def test_empty_candidates_returns_empty_message(candidates: list | None) -> None:
    """An API response with no candidates must not raise and must return an empty assistant message."""
    client, mock = _make_gemini_client()
    response = _make_response([])
    response.candidates = candidates
    mock.aio.models.generate_content = AsyncMock(return_value=response)

    result = await client.get_response(messages=[Message(role="user", contents=[Content.from_text("Hi")])])

    assert result.messages[0].role == "assistant"
    assert result.messages[0].contents == []
    assert result.finish_reason is None


@pytest.mark.parametrize("candidates", [None, []])
async def test_empty_candidates_in_stream_does_not_raise(candidates: list | None) -> None:
    """A streaming chunk with no candidates must not raise and must yield an empty update."""
    client, mock = _make_gemini_client()
    chunk = _make_response([], finish_reason=None, prompt_tokens=None, output_tokens=None)
    chunk.candidates = candidates
    mock.aio.models.generate_content_stream = AsyncMock(return_value=_async_iter([chunk]))

    updates = [
        update
        async for update in client.get_response(
            messages=[Message(role="user", contents=[Content.from_text("Hi")])],
            stream=True,
        )
    ]

    assert len(updates) == 1
    assert updates[0].contents == []
    assert updates[0].finish_reason is None


# service_url


def test_service_url() -> None:
    client, _ = _make_gemini_client()
    assert client.service_url() == "https://generativelanguage.googleapis.com"


# integration tests


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_basic_chat() -> None:
    """Basic request/response round-trip returns a non-empty text reply."""
    client = GeminiChatClient(model=_TEST_MODEL)
    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Reply with the single word: hello")])]
    )

    assert response.messages
    assert response.messages[0].text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_streaming() -> None:
    """Streaming yields multiple chunks that together form a non-empty response."""
    client = GeminiChatClient(model=_TEST_MODEL)
    stream = client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Count from 1 to 5.")])],
        stream=True,
    )

    chunks = [update async for update in stream]
    assert len(chunks) > 0
    full_text = "".join(u.text or "" for u in chunks)
    assert full_text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_structured_output() -> None:
    """Structured output with a Pydantic response_format returns a parsed value via response.value."""

    class Answer(BaseModel):
        answer: str

    client = GeminiChatClient(model=_TEST_MODEL)

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("What is the capital of Germany?")])],
        options={"response_format": Answer},
    )

    assert response.value is not None
    assert isinstance(response.value, Answer)
    assert response.value.answer


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_tool_calling() -> None:
    """Model invokes the registered tool when asked a question that requires it."""

    def get_temperature(city: str) -> str:
        """Return the current temperature for a city."""
        return f"22°C in {city}"

    tool = FunctionTool(name="get_temperature", func=get_temperature)
    client = GeminiChatClient(model=_TEST_MODEL)

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("What is the temperature in Berlin?")])],
        options={"tools": [tool], "tool_choice": "required"},
    )

    function_calls = [c for c in response.messages[0].contents if c.type == "function_call"]
    assert len(function_calls) >= 1
    assert function_calls[0].name == "get_temperature"


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_thinking_config() -> None:
    """Model accepts a thinking budget and returns a non-empty text reply."""
    options: GeminiChatOptions = {"thinking_config": ThinkingConfig(thinking_budget=512)}
    client = GeminiChatClient(model=_TEST_MODEL)

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("What is 17 * 34?")])],
        options=options,
    )

    assert response.messages
    assert response.messages[0].text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_google_search_grounding() -> None:
    """Google Search grounding returns a non-empty response for a current-events question."""
    client = GeminiChatClient(model=_TEST_MODEL)

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("What is the latest stable version of Python?")])],
        options={"tools": [GeminiChatClient.get_web_search_tool()]},
    )

    assert response.messages
    assert response.messages[0].text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_google_maps_grounding() -> None:
    """Google Maps grounding returns a non-empty response for a location-based question."""
    client = GeminiChatClient(model=_TEST_MODEL)

    response = await client.get_response(
        messages=[
            Message(
                role="user",
                contents=[Content.from_text("What are some highly rated restaurants in Karlsruhe city center?")],
            )
        ],
        options={"tools": [GeminiChatClient.get_maps_grounding_tool()]},
    )

    assert response.messages
    assert response.messages[0].text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_code_execution() -> None:
    """Code execution tool produces a non-empty response for a computation request."""
    client = GeminiChatClient(model=_TEST_MODEL)

    response = await client.get_response(
        messages=[
            Message(
                role="user",
                contents=[Content.from_text("Compute the sum of the first 100 natural numbers using code.")],
            )
        ],
        options={"tools": [GeminiChatClient.get_code_interpreter_tool()]},
    )

    assert response.messages
    assert response.messages[0].text
