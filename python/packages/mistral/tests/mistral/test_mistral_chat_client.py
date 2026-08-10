# Copyright (c) Microsoft. All rights reserved.

import json
import logging
import os
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import pytest
from agent_framework import Agent, ChatResponse, Content, Message, tool
from agent_framework.exceptions import (
    ChatClientException,
    ChatClientInvalidAuthException,
    ChatClientInvalidRequestException,
    ChatClientInvalidResponseException,
)
from pydantic import BaseModel

import agent_framework_mistral._chat_client as chat_client_module
from agent_framework_mistral import MistralChatClient, MistralChatOptions
from agent_framework_mistral._chat_client import _sanitize_tool_call_id  # pyright: ignore[reportPrivateUsage]

# region: Helpers


def make_response_payload(
    content: Any = None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "stop",
    usage: dict[str, Any] | None = None,
    choices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if choices is None:
        message: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls is not None:
            message["tool_calls"] = tool_calls
        choices = [{"index": 0, "finish_reason": finish_reason, "message": message}]
    return {
        "id": "resp-id",
        "object": "chat.completion",
        "model": "mistral-small-latest",
        "created": 1722249600,
        "usage": usage or {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
        "choices": choices,
    }


def make_chunk_payload(
    content: Any = None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str | None = None,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    delta: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    return {
        "id": "chunk-id",
        "model": "mistral-small-latest",
        "created": 1722249600,
        "usage": usage,
        "choices": [{"index": 0, "finish_reason": finish_reason, "delta": delta}],
    }


def tool_call_payload(
    name: str,
    arguments: Any,
    call_id: str | None = None,
    index: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "function", "function": {"name": name, "arguments": arguments}}
    if call_id is not None:
        payload["id"] = call_id
    if index is not None:
        payload["index"] = index
    return payload


def sse_bytes(*chunks: dict[str, Any]) -> bytes:
    body = b"".join(f"data: {json.dumps(chunk)}\n\n".encode() for chunk in chunks)
    return body + b"data: [DONE]\n\n"


class MockMistral:
    """Routes requests to a queue of responses and records request bodies."""

    def __init__(self, responses: Sequence[httpx.Response]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        return self._responses.pop(0)

    @property
    def last_request(self) -> dict[str, Any]:
        return self.requests[-1]


def make_client(*responses: httpx.Response) -> tuple[MistralChatClient, MockMistral]:
    server = MockMistral(responses)
    http_client = httpx.AsyncClient(
        base_url="https://api.mistral.ai",
        transport=httpx.MockTransport(server.handler),
    )
    client = MistralChatClient(model="mistral-small-latest", client=http_client)
    return client, server


def json_response(payload: Any) -> httpx.Response:
    return httpx.Response(200, json=payload)


def stream_response(*chunks: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, content=sse_bytes(*chunks), headers={"content-type": "text/event-stream"})


# region: Construction


def test_mistral_chat_construction_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_CHAT_MODEL", "mistral-large-latest")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    client = MistralChatClient()
    assert client.model == "mistral-large-latest"


def test_mistral_chat_construction_with_params() -> None:
    client = MistralChatClient(model="mistral-large-latest", api_key="test-key")
    assert client.model == "mistral-large-latest"
    assert client.client.headers["Authorization"] == "Bearer test-key"


def test_mistral_chat_construction_with_server_url() -> None:
    client = MistralChatClient(
        model="mistral-large-latest",
        api_key="test-key",
        server_url="https://custom.mistral.ai",
    )
    assert client.service_url() == "https://custom.mistral.ai"
    assert str(client.client.base_url) == "https://custom.mistral.ai"


def test_mistral_chat_construction_with_client_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    http_client = httpx.AsyncClient(base_url="https://api.mistral.ai")
    client = MistralChatClient(model="mistral-large-latest", client=http_client)
    assert client.client is http_client


def test_mistral_chat_construction_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    from agent_framework.exceptions import SettingNotFoundError

    with pytest.raises(SettingNotFoundError):
        MistralChatClient(model="mistral-large-latest")


def test_mistral_chat_service_url_default() -> None:
    client = MistralChatClient(model="mistral-large-latest", api_key="test-key")
    assert client.service_url() == "https://api.mistral.ai"


async def test_mistral_chat_close_only_closes_owned_client() -> None:
    owned = MistralChatClient(model="mistral-large-latest", api_key="test-key")
    await owned.close()
    assert owned.client.is_closed

    http_client = httpx.AsyncClient(base_url="https://custom.mistral.ai")
    injected = MistralChatClient(model="mistral-large-latest", client=http_client)
    assert injected.service_url() == "https://custom.mistral.ai"

    await injected.close()

    assert not http_client.is_closed
    await http_client.aclose()


async def test_mistral_chat_missing_model_raises_at_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISTRAL_CHAT_MODEL", raising=False)
    http_client = httpx.AsyncClient(base_url="https://api.mistral.ai")
    client = MistralChatClient(client=http_client, api_key="test-key")
    with pytest.raises(ValueError, match="Mistral model is required"):
        await client.get_response([Message("user", ["hi"])])


# region: Request preparation


async def test_get_response_marks_feature_used(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from agent_framework_mistral._feature_usage import FeatureIndex

    mark = MagicMock()
    monkeypatch.setattr(chat_client_module, "mark_feature_used", mark)
    client, _ = make_client(json_response(make_response_payload(content="ok")))

    await client.get_response([Message("user", ["hi"])])

    mark.assert_called_once_with(FeatureIndex.MISTRAL)


async def test_get_response_basic() -> None:
    client, server = make_client(json_response(make_response_payload(content="hello")))

    response = await client.get_response([Message("user", ["hi"])])

    assert isinstance(response, ChatResponse)
    assert response.text == "hello"
    assert response.finish_reason == "stop"
    assert response.usage_details == {
        "input_token_count": 5,
        "output_token_count": 7,
        "total_token_count": 12,
    }
    assert server.last_request["model"] == "mistral-small-latest"
    assert server.last_request["messages"] == [{"role": "user", "content": "hi"}]


async def test_get_response_includes_cached_input_tokens() -> None:
    client, _ = make_client(
        json_response(
            make_response_payload(
                content="hello",
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 7,
                    "total_tokens": 107,
                    "prompt_tokens_details": {"cached_tokens": 80},
                },
            )
        )
    )

    response = await client.get_response([Message("user", ["hi"])])

    assert response.usage_details is not None
    assert response.usage_details["cache_read_input_token_count"] == 80


@pytest.mark.parametrize("cached_tokens", ["80", 80.5, True, False])
async def test_get_response_ignores_invalid_cached_input_tokens(cached_tokens: Any) -> None:
    client, _ = make_client(
        json_response(
            make_response_payload(
                content="hello",
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 7,
                    "total_tokens": 107,
                    "prompt_tokens_details": {"cached_tokens": cached_tokens},
                },
            )
        )
    )

    response = await client.get_response([Message("user", ["hi"])])

    assert response.usage_details is not None
    assert "prompt/cached_tokens" not in response.usage_details
    assert "cache_read_input_token_count" not in response.usage_details


@pytest.mark.parametrize(
    ("status_code", "expected_exception"),
    [
        (401, ChatClientInvalidAuthException),
        (400, ChatClientInvalidRequestException),
        (500, ChatClientException),
    ],
)
async def test_get_response_http_error_wrapped(
    status_code: int,
    expected_exception: type[ChatClientException],
) -> None:
    client, _ = make_client(httpx.Response(status_code, json={"message": "request failed"}))

    with pytest.raises(expected_exception, match=f"status {status_code}"):
        await client.get_response([Message("user", ["hi"])])


async def test_get_response_network_error_wrapped() -> None:
    def raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    http_client = httpx.AsyncClient(
        base_url="https://api.mistral.ai",
        transport=httpx.MockTransport(raise_connect_error),
    )
    client = MistralChatClient(model="mistral-small-latest", client=http_client)

    with pytest.raises(ChatClientException, match="Mistral chat request failed"):
        await client.get_response([Message("user", ["hi"])])


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, content=b"{"), "response was invalid"),
        (json_response([]), "must be a JSON object"),
        (json_response({"choices": ["not-an-object"]}), "response was invalid"),
    ],
)
async def test_get_response_invalid_payload_wrapped(response: httpx.Response, message: str) -> None:
    client, _ = make_client(response)

    with pytest.raises(ChatClientInvalidResponseException, match=message):
        await client.get_response([Message("user", ["hi"])])


async def test_get_response_option_mapping() -> None:
    client, server = make_client(json_response(make_response_payload(content="ok")))

    options: MistralChatOptions = {
        "temperature": 0.5,
        "max_tokens": 100,
        "seed": 42,
        "allow_multiple_tool_calls": False,
        "safe_prompt": True,
        "stop": ["END"],
        "guardrails": [{"name": "test-guardrail"}],
        "prompt_cache_key": "shared-prefix",
        "reasoning_effort": "high",
    }
    await client.get_response([Message("user", ["hi"])], options=options)

    request = server.last_request
    assert request["temperature"] == 0.5
    assert request["max_tokens"] == 100
    assert request["random_seed"] == 42
    assert request["parallel_tool_calls"] is False
    assert request["safe_prompt"] is True
    assert request["stop"] == ["END"]
    assert "n" not in request
    assert request["guardrails"] == [{"name": "test-guardrail"}]
    assert request["prompt_cache_key"] == "shared-prefix"
    assert request["reasoning_effort"] == "high"
    assert "seed" not in request
    assert "allow_multiple_tool_calls" not in request


async def test_get_response_instructions_prepended_as_system_message() -> None:
    client, server = make_client(json_response(make_response_payload(content="ok")))

    await client.get_response([Message("user", ["hi"])], options={"instructions": "Be brief."})

    assert server.last_request["messages"][0] == {"role": "system", "content": "Be brief."}
    assert "instructions" not in server.last_request


async def test_get_response_model_override() -> None:
    client, server = make_client(json_response(make_response_payload(content="ok")))

    await client.get_response([Message("user", ["hi"])], options={"model": "mistral-large-latest"})

    assert server.last_request["model"] == "mistral-large-latest"


async def test_message_conversion_roles() -> None:
    client, server = make_client(json_response(make_response_payload(content="ok")))

    messages = [
        Message("system", ["You are helpful."]),
        Message("user", ["Question?"]),
        Message(
            "assistant",
            [
                Content.from_text(text="Let me check."),
                Content.from_function_call(call_id="call123AB", name="lookup", arguments='{"q": "x"}'),
            ],
        ),
        Message("tool", [Content.from_function_result(call_id="call123AB", result="42")]),
    ]
    await client.get_response(messages)

    sent = server.last_request["messages"]
    assert sent[0] == {"role": "system", "content": "You are helpful."}
    assert sent[1] == {"role": "user", "content": "Question?"}
    assert sent[2]["role"] == "assistant"
    assert sent[2]["content"] == "Let me check."
    assert sent[2]["tool_calls"] == [
        {"id": "call123AB", "type": "function", "function": {"name": "lookup", "arguments": '{"q": "x"}'}}
    ]
    assert sent[3]["role"] == "tool"
    assert sent[3]["tool_call_id"] == "call123AB"
    assert sent[3]["content"] == "42"


async def test_message_conversion_image_content() -> None:
    client, server = make_client(json_response(make_response_payload(content="ok")))

    messages = [
        Message(
            "user",
            [
                Content.from_text(text="What is this?"),
                Content.from_uri(uri="https://example.com/image.png", media_type="image/png"),
            ],
        ),
    ]
    await client.get_response(messages)

    chunks = server.last_request["messages"][0]["content"]
    assert chunks[0] == {"type": "text", "text": "What is this?"}
    assert chunks[1] == {"type": "image_url", "image_url": "https://example.com/image.png"}


def test_message_conversion_edge_cases(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="agent_framework.mistral")
    client, _ = make_client()

    messages = client._prepare_mistral_messages(  # pyright: ignore[reportPrivateUsage]
        [
            Message("developer", ["ignored"]),
            Message("user", [Content.from_error(message="ignored")]),
        ]
    )
    assert messages == [{"role": "user", "content": ""}]

    assert (
        client._convert_data_or_uri_content(  # pyright: ignore[reportPrivateUsage]
            Content("uri", media_type="image/png")
        )
        is None
    )
    assert client._convert_data_or_uri_content(  # pyright: ignore[reportPrivateUsage]
        Content.from_uri(uri="https://example.com/file.pdf", media_type="application/pdf")
    ) == {"type": "document_url", "document_url": "https://example.com/file.pdf"}
    assert (
        client._convert_data_or_uri_content(  # pyright: ignore[reportPrivateUsage]
            Content.from_uri(uri="https://example.com/audio.mp3", media_type="audio/mpeg")
        )
        is None
    )
    assert "Skipping unsupported message role" in caplog.text
    assert "Skipping unsupported user content type" in caplog.text


def test_assistant_and_tool_message_edge_cases(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = make_client()
    assistant = client._format_assistant_message(  # pyright: ignore[reportPrivateUsage]
        Message(
            "assistant",
            [Content.from_function_call(call_id="call", name="lookup", arguments={"query": "x"})],
        )
    )
    assert assistant["tool_calls"][0]["function"]["arguments"] == {"query": "x"}

    rich_result = Content.from_function_result(
        call_id="call",
        result=[
            Content.from_text("text result"),
            Content.from_uri(uri="https://example.com/image.png", media_type="image/png"),
        ],
    )
    named_result = Content("function_result", call_id="call", name="lookup", result=None)
    tool_messages = client._format_tool_messages(  # pyright: ignore[reportPrivateUsage]
        Message("tool", [Content.from_text("ignored"), rich_result, named_result])
    )
    assert tool_messages[0]["content"] == "text result"
    assert tool_messages[1]["content"] == ""
    assert tool_messages[1]["name"] == "lookup"
    assert "Rich content items will be omitted" in caplog.text


def test_result_to_text_variants() -> None:
    client, _ = make_client()
    assert client._result_to_text(None) == ""  # pyright: ignore[reportPrivateUsage]
    assert client._result_to_text("result") == "result"  # pyright: ignore[reportPrivateUsage]
    assert client._result_to_text({"value": 42}) == '{"value": 42}'  # pyright: ignore[reportPrivateUsage]
    assert "object" in client._result_to_text(object())  # pyright: ignore[reportPrivateUsage]


def test_sanitize_tool_call_id() -> None:
    assert _sanitize_tool_call_id("abc123XYZ") == "abc123XYZ"
    sanitized = _sanitize_tool_call_id("call_abc-123-too-long")
    assert len(sanitized) == 9
    assert sanitized.isalnum()
    assert sanitized == _sanitize_tool_call_id("call_abc-123-too-long")


async def test_tools_and_tool_choice() -> None:
    client, server = make_client(json_response(make_response_payload(content="ok")))

    @tool(approval_mode="never_require")
    def get_weather(location: str) -> str:
        """Get the weather."""
        return "sunny"

    await client.get_response(
        [Message("user", ["hi"])],
        options={"tools": [get_weather], "tool_choice": "auto"},
    )

    request = server.last_request
    assert request["tool_choice"] == "auto"
    assert len(request["tools"]) == 1
    assert request["tools"][0]["type"] == "function"
    assert request["tools"][0]["function"]["name"] == "get_weather"


async def test_tool_choice_required_function() -> None:
    client, server = make_client(json_response(make_response_payload(content="ok")))

    @tool(approval_mode="never_require")
    def get_weather(location: str) -> str:
        """Get the weather."""
        return "sunny"

    await client.get_response(
        [Message("user", ["hi"])],
        options={
            "tools": [get_weather],
            "tool_choice": {"mode": "required", "required_function_name": "get_weather"},
        },
    )

    assert server.last_request["tool_choice"] == {"type": "function", "function": {"name": "get_weather"}}


def test_tool_preparation_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _ = make_client()
    native_tool = {"type": "web_search"}
    assert client._prepare_tools([native_tool]) == [native_tool]  # pyright: ignore[reportPrivateUsage]
    assert (
        client._prepare_tool_choice(  # pyright: ignore[reportPrivateUsage]
            {"mode": "auto", "allowed_tools": ["lookup"]}
        )
        == "auto"
    )
    assert client._prepare_tool_choice("none") == "none"  # pyright: ignore[reportPrivateUsage]
    assert client._prepare_tool_choice("required") == "required"  # pyright: ignore[reportPrivateUsage]

    monkeypatch.setattr(chat_client_module, "validate_tool_mode", lambda _: {"mode": "unsupported"})
    assert client._prepare_tool_choice("auto") is None  # pyright: ignore[reportPrivateUsage]
    assert "Unsupported tool_choice mode" in caplog.text


async def test_response_format_pydantic_model() -> None:
    client, server = make_client(json_response(make_response_payload(content='{"answer": "42"}')))

    class Answer(BaseModel):
        answer: str

    response = await client.get_response([Message("user", ["hi"])], options={"response_format": Answer})

    response_format = server.last_request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "Answer"
    assert response_format["json_schema"]["schema"] == Answer.model_json_schema()
    assert response_format["json_schema"]["strict"] is True
    assert response.value is not None
    assert response.value.answer == "42"


async def test_response_format_json_object() -> None:
    client, server = make_client(json_response(make_response_payload(content="{}")))

    await client.get_response([Message("user", ["hi"])], options={"response_format": {"type": "json_object"}})

    assert server.last_request["response_format"] == {"type": "json_object"}


async def test_response_format_json_schema_omits_unset_strict() -> None:
    client, server = make_client(json_response(make_response_payload(content="{}")))

    await client.get_response(
        [Message("user", ["hi"])],
        options={
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": {"type": "object"}},
            }
        },
    )

    json_schema = server.last_request["response_format"]["json_schema"]
    assert "strict" not in json_schema


def test_response_format_edge_cases(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = make_client()
    assert client._prepare_response_format("json") == {"type": "json_object"}  # pyright: ignore[reportPrivateUsage]
    assert client._prepare_response_format("yaml") is None  # pyright: ignore[reportPrivateUsage]
    assert client._prepare_response_format(  # pyright: ignore[reportPrivateUsage]
        {
            "type": "json_schema",
            "json_schema": {
                "name": "Answer",
                "schema_definition": {"type": "object"},
                "strict": False,
            },
        }
    ) == {
        "type": "json_schema",
        "json_schema": {
            "name": "Answer",
            "schema": {"type": "object"},
            "strict": False,
        },
    }
    raw_schema = {"title": "Answer", "type": "object"}
    assert client._prepare_response_format(raw_schema) == {  # pyright: ignore[reportPrivateUsage]
        "type": "json_schema",
        "json_schema": {"name": "Answer", "schema": raw_schema, "strict": True},
    }
    assert client._prepare_response_format(object()) is None  # pyright: ignore[reportPrivateUsage]
    assert "Unsupported response_format" in caplog.text


# region: Response parsing


async def test_parse_tool_calls() -> None:
    client, _ = make_client(
        json_response(
            make_response_payload(
                tool_calls=[tool_call_payload("get_weather", '{"location": "Paris"}', call_id="abc123XYZ")],
                finish_reason="tool_calls",
            )
        )
    )

    response = await client.get_response([Message("user", ["hi"])])

    assert response.finish_reason == "tool_calls"
    calls = [c for c in response.messages[0].contents if c.type == "function_call"]
    assert len(calls) == 1
    assert calls[0].call_id == "abc123XYZ"
    assert calls[0].name == "get_weather"
    assert calls[0].parse_arguments() == {"location": "Paris"}


async def test_parse_empty_choices_returns_empty_assistant_message() -> None:
    client, _ = make_client(json_response(make_response_payload(choices=[])))

    response = await client.get_response([Message("user", ["hi"])])

    assert len(response.messages) == 1
    assert response.messages[0].role == "assistant"
    assert response.messages[0].contents == []


async def test_parse_thinking_chunks() -> None:
    content = [
        {"type": "thinking", "thinking": [{"type": "text", "text": "reasoning..."}]},
        {"type": "text", "text": "answer"},
    ]
    client, _ = make_client(json_response(make_response_payload(content=content)))

    response = await client.get_response([Message("user", ["hi"])])

    contents = response.messages[0].contents
    assert contents[0].type == "text_reasoning"
    assert contents[0].text == "reasoning..."
    assert response.text == "answer"


def test_response_content_edge_cases() -> None:
    client, _ = make_client()
    contents = client._parse_message_contents(  # pyright: ignore[reportPrivateUsage]
        {
            "content": [
                {"type": "thinking", "thinking": "reasoning"},
                {"type": "unsupported"},
            ],
            "tool_calls": [
                tool_call_payload("mapping", {"value": 1}, call_id="abc123XYZ"),
                tool_call_payload("missing", None, call_id="def456UVW"),
            ],
        }
    )
    calls = [content for content in contents if content.type == "function_call"]
    assert contents[0].text == "reasoning"
    assert calls[0].arguments == {"value": 1}
    assert calls[1].arguments == "None"
    assert client._format_created_at("invalid") is None  # pyright: ignore[reportPrivateUsage]
    assert client._thinking_to_text({"thinking": object()}) == ""  # pyright: ignore[reportPrivateUsage]


async def test_parse_finish_reason_model_length() -> None:
    client, _ = make_client(json_response(make_response_payload(content="x", finish_reason="model_length")))

    response = await client.get_response([Message("user", ["hi"])])

    assert response.finish_reason == "length"


async def test_function_invocation_loop() -> None:
    client, server = make_client(
        json_response(
            make_response_payload(
                tool_calls=[tool_call_payload("get_weather", '{"location": "Paris"}', call_id="abc123XYZ")],
                finish_reason="tool_calls",
            )
        ),
        json_response(make_response_payload(content="It is sunny in Paris.")),
    )

    @tool(approval_mode="never_require")
    def get_weather(location: str) -> str:
        """Get the weather."""
        return f"sunny in {location}"

    response = await client.get_response(
        [Message("user", ["Weather in Paris?"])],
        options={"tools": [get_weather]},
    )

    assert response.text == "It is sunny in Paris."
    assert len(server.requests) == 2
    assert any(m["role"] == "tool" for m in server.requests[1]["messages"])


# region: Streaming


async def test_streaming_response() -> None:
    client, server = make_client(
        stream_response(
            make_chunk_payload(content="Hel"),
            make_chunk_payload(content="lo"),
            make_chunk_payload(
                finish_reason="stop",
                usage={
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                    "prompt_tokens_details": {"cached_tokens": 2},
                },
            ),
        )
    )

    stream = client.get_response([Message("user", ["hi"])], stream=True)
    updates = [update async for update in stream]
    assert [u.text for u in updates] == ["Hel", "lo", ""]

    response = await stream.get_final_response()
    assert response.text == "Hello"
    assert response.finish_reason == "stop"
    assert response.usage_details == {
        "input_token_count": 3,
        "output_token_count": 2,
        "total_token_count": 5,
        "prompt/cached_tokens": 2,
        "cache_read_input_token_count": 2,
    }
    assert server.last_request["stream"] is True


async def test_streaming_tool_calls() -> None:
    client, _ = make_client(
        stream_response(
            make_chunk_payload(
                tool_calls=[tool_call_payload("get_weather", '{"location": "Paris"}', call_id="abc123XYZ")],
                finish_reason="tool_calls",
            ),
        )
    )

    stream = client.get_response([Message("user", ["hi"])], stream=True)
    updates = [update async for update in stream]

    calls = [c for u in updates for c in u.contents if c.type == "function_call"]
    assert len(calls) == 1
    assert calls[0].name == "get_weather"


async def test_streaming_fragmented_tool_call_coalesces() -> None:
    """Real streams carry the ID and name only on the first fragment; later fragments carry argument pieces."""
    client, _ = make_client(
        stream_response(
            make_chunk_payload(
                tool_calls=[tool_call_payload("get_weather", '{"loc', call_id="abc123XYZ", index=0)],
            ),
            make_chunk_payload(
                tool_calls=[tool_call_payload("", 'ation": "Paris"}', index=0)],
                finish_reason="tool_calls",
            ),
        )
    )

    stream = client.get_response([Message("user", ["hi"])], stream=True)
    async for _ in stream:
        pass
    response = await stream.get_final_response()

    calls = [c for c in response.messages[0].contents if c.type == "function_call"]
    assert len(calls) == 1
    assert calls[0].call_id == "abc123XYZ"
    assert calls[0].name == "get_weather"
    assert calls[0].parse_arguments() == {"location": "Paris"}


async def test_streaming_interleaved_parallel_tool_calls() -> None:
    """Continuation fragments without IDs must merge into the call with the same index, not the preceding one."""
    client, _ = make_client(
        stream_response(
            make_chunk_payload(
                tool_calls=[tool_call_payload("get_weather", '{"loc', call_id="abc123XYZ", index=0)],
            ),
            make_chunk_payload(
                tool_calls=[tool_call_payload("get_time", '{"tz', call_id="def456UVW", index=1)],
            ),
            make_chunk_payload(
                tool_calls=[tool_call_payload("", 'ation": "Paris"}', index=0)],
            ),
            make_chunk_payload(
                tool_calls=[tool_call_payload("", '": "CET"}', index=1)],
                finish_reason="tool_calls",
            ),
        )
    )

    stream = client.get_response([Message("user", ["hi"])], stream=True)
    async for _ in stream:
        pass
    response = await stream.get_final_response()

    calls = [c for c in response.messages[0].contents if c.type == "function_call"]
    assert len(calls) == 2
    by_id = {c.call_id: c for c in calls}
    assert by_id["abc123XYZ"].name == "get_weather"
    assert by_id["abc123XYZ"].parse_arguments() == {"location": "Paris"}
    assert by_id["def456UVW"].name == "get_time"
    assert by_id["def456UVW"].parse_arguments() == {"tz": "CET"}


async def test_streaming_parallel_calls_without_indexes() -> None:
    client, _ = make_client(
        stream_response(
            make_chunk_payload(
                tool_calls=[
                    tool_call_payload("get_weather", {"location": "Paris"}, call_id="abc123XYZ"),
                    tool_call_payload("get_time", {"tz": "CET"}, call_id="def456UVW"),
                ],
                finish_reason="tool_calls",
            )
        )
    )

    stream = client.get_response([Message("user", ["hi"])], stream=True)
    response = await stream.get_final_response()

    calls = [content for content in response.messages[0].contents if content.type == "function_call"]
    assert [call.call_id for call in calls] == ["abc123XYZ", "def456UVW"]
    assert calls[0].arguments == {"location": "Paris"}


async def test_streaming_reused_index_flushes_previous_call() -> None:
    client, _ = make_client(
        stream_response(
            make_chunk_payload(tool_calls=[tool_call_payload("first", '{"value": 1}', call_id="abc123XYZ", index=0)]),
            make_chunk_payload(
                tool_calls=[tool_call_payload("second", '{"value": 2}', call_id="def456UVW", index=0)],
                finish_reason="tool_calls",
            ),
        )
    )

    stream = client.get_response([Message("user", ["hi"])], stream=True)
    response = await stream.get_final_response()

    calls = [content for content in response.messages[0].contents if content.type == "function_call"]
    assert [call.name for call in calls] == ["first", "second"]


async def test_streaming_mid_stream_error_wrapped() -> None:
    """Exceptions raised while iterating the stream surface as ChatClientException."""

    class ExplodingStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield f"data: {json.dumps(make_chunk_payload(content='partial'))}\n\n".encode()
            raise ConnectionError("connection dropped")

    client, _ = make_client(
        httpx.Response(200, stream=ExplodingStream(), headers={"content-type": "text/event-stream"})
    )

    stream = client.get_response([Message("user", ["hi"])], stream=True)
    with pytest.raises(ChatClientException, match="Mistral streaming chat request failed"):
        async for _ in stream:
            pass


async def test_streaming_http_error_wrapped() -> None:
    client, _ = make_client(httpx.Response(429, json={"message": "rate limited"}))

    stream = client.get_response([Message("user", ["hi"])], stream=True)
    with pytest.raises(ChatClientException, match="status 429"):
        async for _ in stream:
            pass


def test_parse_sse_line_variants() -> None:
    payload = make_chunk_payload(content="hello")
    assert MistralChatClient._parse_sse_line(f"data:{json.dumps(payload)}") == payload  # pyright: ignore[reportPrivateUsage]
    assert MistralChatClient._parse_sse_line("") is None  # pyright: ignore[reportPrivateUsage]
    assert MistralChatClient._parse_sse_line("event: message") is None  # pyright: ignore[reportPrivateUsage]
    assert MistralChatClient._parse_sse_line("data:") is None  # pyright: ignore[reportPrivateUsage]
    assert MistralChatClient._parse_sse_line("data: [DONE]") is None  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(ChatClientInvalidResponseException, match="malformed SSE"):
        MistralChatClient._parse_sse_line("data: {")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ChatClientInvalidResponseException, match="must be a JSON object"):
        MistralChatClient._parse_sse_line("data: []")  # pyright: ignore[reportPrivateUsage]


async def test_streaming_tool_call_flushed_without_finish_chunk() -> None:
    """A stream that ends without a finish chunk still emits accumulated calls."""
    client, _ = make_client(
        stream_response(
            make_chunk_payload(
                tool_calls=[tool_call_payload("get_weather", '{"location": "Paris"}', call_id="abc123XYZ", index=0)],
            ),
        )
    )

    stream = client.get_response([Message("user", ["hi"])], stream=True)
    async for _ in stream:
        pass
    response = await stream.get_final_response()

    calls = [c for c in response.messages[0].contents if c.type == "function_call"]
    assert len(calls) == 1
    assert calls[0].call_id == "abc123XYZ"
    assert calls[0].parse_arguments() == {"location": "Paris"}


# region: Integration Tests

skip_if_mistral_chat_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("MISTRAL_CHAT_MODEL", "") in ("", "test-model") or os.getenv("MISTRAL_API_KEY", "") == "",
    reason="No real Mistral chat model or API key provided; skipping integration tests.",
)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_mistral_chat_integration_tests_disabled
async def test_mistral_chat_integration_basic() -> None:
    client = MistralChatClient()
    try:
        response = await client.get_response([Message("user", ["Reply with exactly the word: hello"])])

        assert response.text
        assert response.usage_details is not None
    finally:
        await client.close()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_mistral_chat_integration_tests_disabled
async def test_mistral_chat_integration_streaming() -> None:
    client = MistralChatClient()
    try:
        stream = client.get_response([Message("user", ["Count from 1 to 5."])], stream=True)
        updates = [update async for update in stream]

        assert updates
        response = await stream.get_final_response()
        assert response.text
    finally:
        await client.close()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_mistral_chat_integration_tests_disabled
async def test_mistral_chat_integration_agent_with_tool() -> None:
    @tool(approval_mode="never_require")
    def get_secret_word() -> str:
        """Get the secret word."""
        return "pineapple"

    client = MistralChatClient()
    agent = Agent(
        client=client,
        instructions="Use the get_secret_word tool and reply with its result.",
        tools=get_secret_word,
    )
    try:
        result = await agent.run("What is the secret word?")

        assert "pineapple" in result.text.lower()
    finally:
        await client.close()
