# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import MutableMapping
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import Agent, Content, FunctionTool, Message, ResponseStream
from agent_framework._settings import SecretString
from boto3.session import Session as Boto3Session
from botocore.client import BaseClient

from agent_framework_bedrock import BedrockChatClient, BedrockEmbeddingClient
from agent_framework_bedrock._chat_client import BedrockSettings
from agent_framework_bedrock._feature_usage import FeatureIndex


class _StubBedrockRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "modelId": kwargs["modelId"],
            "responseId": "resp-123",
            "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
            "output": {
                "completionReason": "end_turn",
                "message": {
                    "id": "msg-1",
                    "role": "assistant",
                    "content": [{"text": "Bedrock says hi"}],
                },
            },
        }


class _StubEventStream(list[dict[str, Any]]):
    closed = False

    def close(self) -> None:
        self.closed = True


class _StubBedrockStreamRuntime(_StubBedrockRuntime):
    def __init__(self, events: list[dict[str, Any]]) -> None:
        super().__init__()
        self.stream = _StubEventStream(events)

    def converse_stream(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"stream": self.stream}


def _make_client() -> BedrockChatClient:
    """Create a BedrockChatClient with a stub runtime for unit tests."""
    return BedrockChatClient(
        model="amazon.titan-text",
        region="us-west-2",
        client=_StubBedrockRuntime(),  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )


def test_agent_accepts_bedrock_chat_client() -> None:
    client = _make_client()
    agent = Agent(client=client, instructions="test agent")
    assert agent.client is client


async def test_get_response_invokes_bedrock_runtime() -> None:
    stub = _StubBedrockRuntime()
    client = BedrockChatClient(
        model="amazon.titan-text",
        region="us-west-2",
        client=stub,  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )

    messages = [
        Message(role="system", contents=[Content.from_text(text="You are concise.")]),
        Message(role="user", contents=[Content.from_text(text="hello")]),
    ]

    with patch("agent_framework_bedrock._chat_client.mark_feature_used") as mark_feature_used:
        response = await client.get_response(messages=messages, options={"max_tokens": 32})

    mark_feature_used.assert_called_once_with(FeatureIndex.BEDROCK)
    assert stub.calls, "Expected the runtime client to be called"
    payload = stub.calls[0]
    assert payload["modelId"] == "amazon.titan-text"
    assert payload["messages"][0]["content"][0]["text"] == "hello"
    assert response.messages[0].contents[0].text == "Bedrock says hi"
    assert response.usage_details and response.usage_details["input_token_count"] == 10


async def test_stream_yields_updates_as_converse_stream_events_arrive() -> None:
    """stream=True should use ConverseStream and yield text, tool call, finish and usage updates per event."""
    stub = _StubBedrockStreamRuntime([
        {"messageStart": {"role": "assistant"}},
        {"contentBlockDelta": {"delta": {"text": "Checking"}, "contentBlockIndex": 0}},
        {"contentBlockDelta": {"delta": {"text": " the weather."}, "contentBlockIndex": 0}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {
            "contentBlockStart": {
                "start": {"toolUse": {"toolUseId": "call-1", "name": "get_weather"}},
                "contentBlockIndex": 1,
            }
        },
        {"contentBlockDelta": {"delta": {"toolUse": {"input": '{"city":'}}, "contentBlockIndex": 1}},
        {"contentBlockDelta": {"delta": {"toolUse": {"input": ' "Rome"}'}}, "contentBlockIndex": 1}},
        {"contentBlockStop": {"contentBlockIndex": 1}},
        {"messageStop": {"stopReason": "tool_use"}},
        {
            "metadata": {
                "usage": {"inputTokens": 47, "outputTokens": 18, "totalTokens": 65},
                "metrics": {"latencyMs": 9},
            }
        },
    ])
    client = BedrockChatClient(
        model="us.openai.gpt-6-sol",
        region="us-east-1",
        client=stub,  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )

    stream = client._inner_get_response(
        messages=[Message(role="user", contents=[Content.from_text(text="Weather in Rome?")])], options={}, stream=True
    )
    assert isinstance(stream, ResponseStream)
    updates = [update async for update in stream]
    response = await stream.get_final_response()

    assert [update.text for update in updates if update.text] == ["Checking", " the weather."]
    assert all(update.role == "assistant" for update in updates)
    assert response.text == "Checking the weather."
    function_call = next(content for content in response.messages[0].contents if content.type == "function_call")
    assert function_call.call_id == "call-1"
    assert function_call.name == "get_weather"
    assert function_call.parse_arguments() == {"city": "Rome"}
    assert response.finish_reason == "tool_calls"
    assert response.usage_details and response.usage_details["output_token_count"] == 18
    assert response.model == "us.openai.gpt-6-sol"
    assert stub.stream.closed


def test_build_request_requires_non_system_messages() -> None:
    client = BedrockChatClient(
        model="amazon.titan-text",
        region="us-west-2",
        client=_StubBedrockRuntime(),  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )

    messages = [Message(role="system", contents=[Content.from_text(text="Only system text")])]

    with pytest.raises(ValueError):
        client._prepare_options(messages, {})


def test_prepare_options_tool_choice_none_omits_tool_config() -> None:
    """When tool_choice='none', toolConfig must be omitted entirely.

    Bedrock's Converse API only accepts 'auto', 'any', or 'tool' as valid
    toolChoice keys. Sending {"none": {}} causes a ParamValidationError.
    The fix omits toolConfig so the model won't attempt tool calls.

    Fixes #4529.
    """
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    # Even when tools are provided, tool_choice="none" should strip toolConfig
    options: dict[str, Any] = {
        "tool_choice": "none",
        "tools": [
            {"toolSpec": {"name": "get_weather", "description": "Get weather", "inputSchema": {"json": {}}}},
        ],
    }

    request = client._prepare_options(messages, options)

    assert "toolConfig" not in request, (
        f"toolConfig should be omitted when tool_choice='none', got: {request.get('toolConfig')}"
    )


def test_prepare_options_tool_choice_auto_includes_tool_config() -> None:
    """When tool_choice='auto', toolConfig.toolChoice should be {'auto': {}}."""
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    options: dict[str, Any] = {
        "tool_choice": "auto",
        "tools": [
            {"toolSpec": {"name": "get_weather", "description": "Get weather", "inputSchema": {"json": {}}}},
        ],
    }

    request = client._prepare_options(messages, options)

    assert "toolConfig" in request
    assert request["toolConfig"]["toolChoice"] == {"auto": {}}


def test_prepare_options_tool_choice_required_includes_any() -> None:
    """When tool_choice='required' (no specific function), toolChoice should be {'any': {}}."""
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    options: dict[str, Any] = {
        "tool_choice": "required",
        "tools": [
            {"toolSpec": {"name": "get_weather", "description": "Get weather", "inputSchema": {"json": {}}}},
        ],
    }

    request = client._prepare_options(messages, options)

    assert "toolConfig" in request
    assert request["toolConfig"]["toolChoice"] == {"any": {}}


def test_prepare_options_tool_choice_auto_without_tools_omits_tool_config() -> None:
    """When tool_choice='auto' but no tools are provided, toolConfig must be omitted.

    Without tools, setting toolChoice would cause a ParamValidationError from Bedrock.
    """
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    options: dict[str, Any] = {
        "tool_choice": "auto",
    }

    request = client._prepare_options(messages, options)

    assert "toolConfig" not in request, (
        f"toolConfig should be omitted when no tools are provided, got: {request.get('toolConfig')}"
    )


def test_prepare_options_tool_choice_required_without_tools_raises() -> None:
    """When tool_choice='required' but no tools are provided, a ValueError must be raised."""
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    options: dict[str, Any] = {
        "tool_choice": "required",
    }

    with pytest.raises(ValueError, match="tool_choice='required' requires at least one tool"):
        client._prepare_options(messages, options)


def test_process_converse_response_preserves_non_ascii_in_json_block() -> None:
    """Non-ASCII text in a Bedrock ``json`` content block must be preserved, not \\uXXXX-escaped.

    The Converse API can return structured ``json`` content blocks. These are serialized to
    text via ``json.dumps``; without ``ensure_ascii=False`` CJK characters and emoji are escaped
    to ``\\uXXXX`` sequences and surface garbled to the user.
    """
    client = _make_client()
    json_payload = {"greeting": "你好世界", "emoji": "🎉"}
    response: dict[str, Any] = {
        "modelId": "amazon.titan-text",
        "output": {
            "completionReason": "end_turn",
            "message": {
                "role": "assistant",
                "content": [{"json": json_payload}],
            },
        },
    }

    chat_response = client._process_converse_response(response)

    text = chat_response.messages[0].text
    assert "你好世界" in text
    assert "🎉" in text
    # Must not be escaped to Unicode code points.
    assert "\\u" not in text
    # Serialized text must remain valid JSON that round-trips to the original payload.
    assert json.loads(text) == json_payload


def test_parse_usage_surfaces_cache_tokens() -> None:
    """Bedrock Converse reports cache token counts when prompt caching is used."""
    client = _make_client()

    details = client._parse_usage({
        "inputTokens": 10,
        "outputTokens": 5,
        "totalTokens": 15,
        "cacheReadInputTokens": 8,
        "cacheWriteInputTokens": 3,
    })

    assert details is not None
    assert details["input_token_count"] == 10
    assert details["cache_read_input_token_count"] == 8
    assert details["cache_creation_input_token_count"] == 3


def test_parse_usage_returns_none_when_no_recognized_keys() -> None:
    """A truthy usage payload with no recognized keys yields None, not an empty mapping."""
    client = _make_client()

    assert client._parse_usage({"unexpected": 1}) is None
    assert client._parse_usage({}) is None
    assert client._parse_usage(None) is None


def test_init_uses_boto3_session_when_runtime_client_not_supplied() -> None:
    """BedrockChatClient should build a runtime client from a provided boto3 session."""

    class _FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []
            self.region_name: str | None = None

        def client(self, service_name: str, *, region_name: str, config: Any) -> _StubBedrockRuntime:
            self.calls.append({"service_name": service_name, "region_name": region_name, "config": config})
            return _StubBedrockRuntime()

    session = _FakeSession()

    client = BedrockChatClient(
        model="amazon.titan-text",
        region="us-west-2",
        boto3_session=cast(Boto3Session, session),
    )

    assert isinstance(client._bedrock_client, _StubBedrockRuntime)
    assert session.calls == [
        {
            "service_name": "bedrock-runtime",
            "region_name": "us-west-2",
            "config": session.calls[0]["config"],
        }
    ]


@pytest.mark.parametrize("secret_type", [str, SecretString], ids=["str", "secret"])
@pytest.mark.parametrize(
    ("client_type", "module"),
    [(BedrockChatClient, "_chat_client"), (BedrockEmbeddingClient, "_embedding_client")],
    ids=["chat", "embedding"],
)
def test_constructor_unwraps_session_credentials(
    secret_type: type[str] | type[SecretString],
    client_type: type[BedrockChatClient] | type[BedrockEmbeddingClient],
    module: str,
) -> None:
    session = MagicMock(region_name="eu-west-1")
    session.client.return_value = _StubBedrockRuntime()
    with patch(f"agent_framework_bedrock.{module}.Boto3Session", return_value=session) as session_cls:
        client = client_type(
            model="test-model",
            region="eu-west-1",
            access_key=secret_type("access"),
            secret_key=secret_type("secret"),
            session_token=secret_type("token"),
        )

    assert client.model == "test-model"
    session_cls.assert_called_once_with(
        region_name="eu-west-1",
        aws_access_key_id="access",
        aws_secret_access_key="secret",
        aws_session_token="token",
    )
    assert all(type(value) is str for value in session_cls.call_args.kwargs.values())


def test_create_session_uses_secret_values() -> None:
    """Bedrock session creation should unwrap configured secret values."""
    settings: BedrockSettings = {
        "region": "eu-west-1",
        "access_key": SecretString("access"),
        "secret_key": SecretString("secret"),
        "session_token": SecretString("token"),
    }

    with patch("agent_framework_bedrock._chat_client.Boto3Session", return_value=MagicMock()) as session_cls:
        BedrockChatClient._create_session(settings)

    session_cls.assert_called_once_with(
        region_name="eu-west-1",
        aws_access_key_id="access",
        aws_secret_access_key="secret",
        aws_session_token="token",
    )
    assert all(type(value) is str for value in session_cls.call_args.kwargs.values())
    assert isinstance(settings["secret_key"], SecretString)
    assert str(settings["secret_key"]) == "**********"


def test_invoke_converse_requires_mapping_response() -> None:
    """Non-mapping Bedrock responses should be rejected."""

    class _BadRuntime:
        def converse(self, **_: Any) -> list[str]:
            return ["not", "a", "mapping"]

    from agent_framework.exceptions import ChatClientInvalidResponseException

    client = BedrockChatClient(
        model="amazon.titan-text",
        region="us-west-2",
        client=cast(BaseClient, _BadRuntime()),
    )

    with pytest.raises(ChatClientInvalidResponseException, match="must be a mapping"):
        client._invoke_converse({"modelId": "amazon.titan-text"})


def test_prepare_options_requires_model_when_unset() -> None:
    """Preparing options without a configured model should raise."""
    client = _make_client()
    client.model = None  # type: ignore[assignment]

    with pytest.raises(ValueError, match="Bedrock model is required"):
        client._prepare_options([Message(role="user", contents=[Content.from_text(text="hello")])], {})


def test_prepare_options_adds_instructions_and_sampling_settings() -> None:
    """Instructions and inference settings should be translated into Bedrock request fields."""
    client = _make_client()
    messages = [
        Message(role="system", contents=[Content.from_text(text="Original system prompt")]),
        Message(role="user", contents=[Content.from_text(text="hello")]),
    ]

    request = client._prepare_options(
        messages,
        {
            "instructions": "Runtime instructions",
            "temperature": 0.2,
            "top_p": 0.9,
            "stop": ["DONE"],
            "max_tokens": 5,
        },
    )

    assert request["system"] == [{"text": "Runtime instructions"}, {"text": "Original system prompt"}]
    assert request["inferenceConfig"] == {
        "maxTokens": 5,
        "temperature": 0.2,
        "topP": 0.9,
        "stopSequences": ["DONE"],
    }


def test_prepare_options_unsupported_tool_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected tool modes should raise a clear error."""
    from agent_framework_bedrock import _chat_client as chat_client_module

    client = _make_client()
    monkeypatch.setattr(chat_client_module, "validate_tool_mode", lambda _: {"mode": "unexpected"})

    with pytest.raises(ValueError, match="Unsupported tool mode for Bedrock: unexpected"):
        client._prepare_options(
            [Message(role="user", contents=[Content.from_text(text="hello")])],
            {"tool_choice": "auto"},
        )


def test_prepare_bedrock_messages_skips_unsupported_content_and_unmatched_tool_results() -> None:
    """Unsupported user content and orphaned tool results should be dropped."""
    client = _make_client()
    messages = [
        Message(role="user", contents=[Content.from_data(data=b"x", media_type="application/octet-stream")]),
        Message(role="tool", contents=[Content.from_function_result(call_id="call-1", result={"answer": 42})]),
        Message(role="user", contents=[Content.from_text(text="hello")]),
    ]

    prompts, conversation = client._prepare_bedrock_messages(messages)

    assert prompts == []
    assert conversation == [{"role": "user", "content": [{"text": "hello"}]}]


@pytest.mark.parametrize(
    ("media_type", "image_format"),
    [("image/png", "png"), ("image/jpeg", "jpeg"), ("image/jpg", "jpeg"), ("IMAGE/PNG", "png")],
)
async def test_get_response_sends_user_images_as_image_blocks(media_type: str, image_format: str) -> None:
    """Image data in a user message should be sent as a Converse image block."""
    stub = _StubBedrockRuntime()
    client = BedrockChatClient(
        model="us.openai.gpt-6-sol",
        region="us-east-1",
        client=stub,  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )
    image_bytes = b"fake-image-bytes"
    message = Message(
        role="user",
        contents=[
            Content.from_text(text="What color is this image?"),
            Content.from_data(data=image_bytes, media_type=media_type),
        ],
    )

    await client.get_response([message])

    assert stub.calls[0]["messages"][0]["content"] == [
        {"text": "What color is this image?"},
        {"image": {"format": image_format, "source": {"bytes": image_bytes}}},
    ]


def test_prepare_bedrock_messages_skips_images_outside_user_messages() -> None:
    """Image data in assistant messages should still be skipped."""
    client = _make_client()
    messages = [
        Message(role="user", contents=[Content.from_text(text="Draw a square.")]),
        Message(
            role="assistant",
            contents=[Content.from_text(text="Here it is."), Content.from_data(data=b"x", media_type="image/png")],
        ),
    ]

    _, conversation = client._prepare_bedrock_messages(messages)

    assert conversation[1] == {"role": "assistant", "content": [{"text": "Here it is."}]}


@pytest.mark.parametrize("media_type", ["image/bmp", "image/svg+xml"])
def test_prepare_bedrock_messages_skips_unsupported_image_formats(
    media_type: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Images in formats Converse rejects should be skipped with a warning so the rest of the request still works."""
    client = _make_client()
    message = Message(
        role="user",
        contents=[Content.from_text(text="Describe this."), Content.from_data(data=b"x", media_type=media_type)],
    )

    with caplog.at_level(logging.WARNING, logger="agent_framework.bedrock"):
        _, conversation = client._prepare_bedrock_messages([message])

    assert conversation == [{"role": "user", "content": [{"text": "Describe this."}]}]
    assert media_type in caplog.text


def test_align_tool_results_handles_pending_edge_cases() -> None:
    """Tool result alignment should preserve valid blocks and drop invalid or extra results."""
    client = _make_client()
    mixed_blocks = cast(
        list[dict[str, Any]],
        [
            "keep-me",
            {"text": "note"},
            {"toolResult": {"content": []}},
            {"toolResult": {"content": []}},
        ],
    )

    aligned = client._align_tool_results_with_pending(
        mixed_blocks,
        deque(["call-1"]),
    )
    unmatched = client._align_tool_results_with_pending(
        [{"toolResult": {"toolUseId": "other", "content": []}}],
        deque(["call-1"]),
    )

    assert aligned[0] == "keep-me"
    assert aligned[1] == {"text": "note"}
    assert aligned[2]["toolResult"]["toolUseId"] == "call-1"
    assert len(aligned) == 3
    assert unmatched == []


def test_convert_content_to_bedrock_block_handles_errors_and_missing_items() -> None:
    """Function result conversion should serialize items, rich content warnings, and fallback results."""
    client = _make_client()
    diagnostic = "test-token-value at /srv/private/tool.py"
    rich_result = Content.from_function_result(
        call_id="call-1",
        result=[Content.from_text(text="summary"), Content.from_data(data=b"x", media_type="image/png")],
        exception=diagnostic,
    )
    restored_rich_result = Content.from_dict(rich_result.to_dict())
    fallback_result = Content.from_function_result(call_id="call-2", result={"answer": 42})
    fallback_result.items = None

    rich_block = client._convert_content_to_bedrock_block(restored_rich_result)
    fallback_block = client._convert_content_to_bedrock_block(fallback_result)

    assert rich_block == {
        "toolResult": {
            "toolUseId": "call-1",
            "content": [{"text": "summary"}],
            "status": "error",
        }
    }
    assert diagnostic not in str(rich_block)

    empty_diagnostic_block = client._convert_content_to_bedrock_block(
        Content.from_function_result(call_id="call-empty", result="failed", exception="")
    )
    assert empty_diagnostic_block is not None
    assert empty_diagnostic_block["toolResult"]["status"] == "error"

    assert fallback_block == {
        "toolResult": {
            "toolUseId": "call-2",
            "content": [{"json": {"answer": 42}}],
            "status": "success",
        }
    }
    assert client._convert_content_to_bedrock_block(Content.from_data(data=b"x", media_type="text/plain")) is None


def test_tool_result_helpers_cover_text_json_and_sequence_values() -> None:
    """Tool result helpers should normalize text, JSON, sequences, and custom objects."""
    client = _make_client()

    class _Serializable:
        def to_dict(self) -> dict[str, int]:
            return {"value": 1}

    assert client._convert_tool_result_to_blocks("plain text") == [{"text": "plain text"}]
    assert client._convert_prepared_tool_result_to_blocks([{"answer": 1}, "done"]) == [
        {"json": {"answer": 1}},
        {"text": "done"},
    ]
    assert client._convert_prepared_tool_result_to_blocks([]) == [{"text": ""}]
    assert client._normalize_tool_result_value(("a", 2)) == {"json": ["a", 2]}
    assert client._normalize_tool_result_value(Content.from_text(text="hello")) == {"text": "hello"}
    assert client._normalize_tool_result_value(_Serializable()) == {"json": {"value": 1}}


def test_prepare_tools_parse_message_contents_and_finish_reason_helpers() -> None:
    """Helper methods should ignore unsupported values and preserve Bedrock response semantics."""
    client = _make_client()
    mixed_tools = cast(
        list[FunctionTool | MutableMapping[str, Any]],
        [
            object(),
            {"toolSpec": {"name": "keep", "description": "desc", "inputSchema": {"json": {}}}},
        ],
    )

    prepared_tools = client._prepare_tools(mixed_tools)
    error_result = client._parse_message_contents([{"toolResult": {"status": "failure", "content": [{"text": "bad"}]}}])
    unsupported_result = client._parse_message_contents([{"image": "ignored"}])

    assert prepared_tools == {
        "tools": [{"toolSpec": {"name": "keep", "description": "desc", "inputSchema": {"json": {}}}}]
    }
    assert client._generate_tool_call_id().startswith("tool-call-")
    assert error_result[0].exception == "Bedrock tool result status: failure"
    assert error_result[0].result == "bad"
    assert unsupported_result == []
    assert client._map_finish_reason(None) is None
    assert client._convert_bedrock_tool_result_to_value(None) is None
    assert client._convert_bedrock_tool_result_to_value([{"text": "ok"}]) == "ok"
    assert client._convert_bedrock_tool_result_to_value([{"json": {"x": 1}}, 7]) == [{"x": 1}, 7]
    assert client._convert_bedrock_tool_result_to_value({"json": {"x": 1}}) == {"x": 1}
    assert client._convert_bedrock_tool_result_to_value({"text": "ok"}) == "ok"


def test_parse_message_contents_requires_tool_use_name() -> None:
    """Malformed toolUse blocks should raise a client response error."""
    from agent_framework.exceptions import ChatClientInvalidResponseException

    client = _make_client()

    with pytest.raises(ChatClientInvalidResponseException, match="missing required tool name"):
        client._parse_message_contents([{"toolUse": {"toolUseId": "call-1"}}])
