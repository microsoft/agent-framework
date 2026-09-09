# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import importlib.util
import logging
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, Content, ResponseStream
from agent_framework.observability import OBSERVABILITY_SETTINGS
from agent_framework.openai import OpenAIChatClient

MODULE_PATH = Path(__file__).parents[1] / "main.py"
SPEC = importlib.util.spec_from_file_location("telegram_hosted_agent_main", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
main = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = main
SPEC.loader.exec_module(main)


def _message_update(text: str = "hello", **message_fields: Any) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 2,
            "from": {"id": 123, "is_bot": False, "first_name": "Test"},
            "chat": {"id": 123, "type": "private"},
            "date": 1,
            "text": text,
            **message_fields,
        },
    }


def _response(status_code: int, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("POST", "https://api.telegram.org/redacted"),
    )


def _empty_stream() -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
    async def updates() -> AsyncIterator[AgentResponseUpdate]:
        return
        yield  # pragma: no cover

    return ResponseStream(updates(), finalizer=AgentResponse.from_updates)


def test_sensitive_telemetry_is_enabled_and_dependency_logging_is_suppressed() -> None:
    assert logging.getLogger("agent_framework").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
    assert OBSERVABILITY_SETTINGS.enable_sensitive_data is True


async def test_runtime_configures_azure_monitor_with_sensitive_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEY_VAULT_URL", "https://sample.vault.azure.net")
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://sample.documents.azure.com")
    monkeypatch.setenv("AZURE_COSMOS_DATABASE_NAME", "telegram")
    monkeypatch.setenv("AZURE_COSMOS_CONTAINER_NAME", "history")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://sample.services.ai.azure.com/api/projects/sample")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.6-luna")

    client = SimpleNamespace(configure_azure_monitor=AsyncMock())
    agent_constructor = Mock(return_value=SimpleNamespace())
    monkeypatch.setattr(main, "DefaultAzureCredential", Mock(return_value=SimpleNamespace()))
    monkeypatch.setattr(main, "SecretClient", Mock(return_value=SimpleNamespace()))
    monkeypatch.setattr(main, "CosmosHistoryProvider", Mock(return_value=SimpleNamespace()))
    monkeypatch.setattr(main, "FoundryChatClient", Mock(return_value=client))
    monkeypatch.setattr(main, "Agent", agent_constructor)
    monkeypatch.setattr(main.httpx, "AsyncClient", Mock(return_value=SimpleNamespace()))
    monkeypatch.setattr(main, "_runtime", None)

    await main.get_runtime()

    client.configure_azure_monitor.assert_awaited_once_with(
        enable_sensitive_data=True,
        enable_live_metrics=True,
    )
    assert agent_constructor.call_args.kwargs["instructions"] == main.AGENT_INSTRUCTIONS
    monkeypatch.setattr(main, "_runtime", None)


@pytest.mark.parametrize("ingress_secret", [None, "wrong-secret"])
async def test_invoke_rejects_unauthenticated_ingress_before_dispatch(
    ingress_secret: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets = SimpleNamespace(
        get_secret=AsyncMock(return_value=SimpleNamespace(value="expected-secret")),
    )
    runtime = cast(Any, SimpleNamespace(secrets=secrets))
    dispatch = AsyncMock()
    monkeypatch.setattr(main, "get_runtime", AsyncMock(return_value=runtime))
    monkeypatch.setattr(main, "dispatch_channel", dispatch)
    headers = {main.INGRESS_SECRET_HEADER: ingress_secret} if ingress_secret is not None else {}
    request = cast(
        Any,
        SimpleNamespace(
            headers=headers,
            json=AsyncMock(return_value={"channel": "telegram", **_message_update()}),
        ),
    )

    response = await main.handle_invoke(request)

    assert response.status_code == 401
    dispatch.assert_not_awaited()


async def test_invoke_dispatches_authenticated_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    secrets = SimpleNamespace(
        get_secret=AsyncMock(return_value=SimpleNamespace(value="expected-secret")),
    )
    runtime = cast(Any, SimpleNamespace(secrets=secrets))
    dispatch = AsyncMock()
    payload = {"channel": "telegram", **_message_update()}
    monkeypatch.setattr(main, "get_runtime", AsyncMock(return_value=runtime))
    monkeypatch.setattr(main, "get_request_context", Mock(return_value=SimpleNamespace(session_id="123")))
    monkeypatch.setattr(main, "dispatch_channel", dispatch)
    request = cast(
        Any,
        SimpleNamespace(
            headers={main.INGRESS_SECRET_HEADER: "expected-secret"},
            json=AsyncMock(return_value=payload),
        ),
    )

    response = await main.handle_invoke(request)

    assert response.status_code == 200
    dispatch.assert_awaited_once_with(payload, "123", runtime)


async def test_dispatches_telegram_without_channel_field(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = AsyncMock()
    monkeypatch.setattr(main, "handle_telegram_update", handler)
    runtime = cast(Any, SimpleNamespace())

    await main.dispatch_channel({"channel": "telegram", **_message_update()}, "session-1", runtime)

    handler_call = handler.await_args
    assert handler_call is not None
    update = handler_call.args[0]
    assert update["update_id"] == 1
    assert "channel" not in update
    assert handler_call.args[1:] == ("session-1", runtime)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"update_id": 1}, "Missing channel"),
        ({"channel": "email"}, "Unsupported channel: email"),
    ],
)
async def test_rejects_missing_or_unsupported_channel(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        await main.dispatch_channel(payload, "session-1", cast(Any, SimpleNamespace()))


async def test_new_clears_durable_history(monkeypatch: pytest.MonkeyPatch) -> None:
    history = SimpleNamespace(clear=AsyncMock())
    runtime = cast(Any, SimpleNamespace(history=history))
    execute = AsyncMock(return_value={})
    monkeypatch.setattr(main, "execute_telegram_operation", execute)

    await main.handle_telegram_update(_message_update("/new"), "123", runtime)

    history.clear.assert_awaited_once_with("123")
    execute_call = execute.await_args
    assert execute_call is not None
    operation = execute_call.args[1]
    assert operation["method"] == "sendMessage"
    assert operation["payload"]["chat_id"] == 123
    assert "empty history" in operation["payload"]["text"]


async def test_rejects_mismatched_session_before_telegram_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = SimpleNamespace(clear=AsyncMock())
    runtime = cast(Any, SimpleNamespace(history=history))
    execute = AsyncMock(return_value={})
    monkeypatch.setattr(main, "execute_telegram_operation", execute)

    with pytest.raises(ValueError, match="chat id does not match"):
        await main.handle_telegram_update(_message_update("/new"), "different-chat", runtime)

    history.clear.assert_not_awaited()
    execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("/start", "Telegram assistant"),
        ("/help", "/new"),
    ],
)
async def test_application_commands_bypass_model(
    command: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = AsyncMock(return_value={})
    agent = SimpleNamespace(run=Mock())
    runtime = cast(Any, SimpleNamespace(agent=agent))
    monkeypatch.setattr(main, "execute_telegram_operation", execute)

    await main.handle_telegram_update(_message_update(command), "123", runtime)

    execute_call = execute.await_args
    assert execute_call is not None
    assert expected in execute_call.args[1]["payload"]["text"]
    agent.run.assert_not_called()


async def test_callback_is_acknowledged_then_streamed_with_apim_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _empty_stream()
    session = object()
    agent = SimpleNamespace(
        create_session=Mock(return_value=session),
        run=Mock(return_value=stream),
    )
    runtime = cast(Any, SimpleNamespace(agent=agent))
    telegram_to_run = AsyncMock(return_value={"messages": ["confirm"], "options": {}, "stream": True})
    monkeypatch.setattr(main, "telegram_to_run", telegram_to_run)
    deliver = AsyncMock()
    monkeypatch.setattr(main, "deliver_stream", deliver)

    operations: list[str] = []

    async def execute(_: Any, operation: Any) -> dict[str, Any]:
        operations.append(operation["method"])
        return {"message_id": 42} if operation["method"] == "sendMessage" else {}

    monkeypatch.setattr(main, "execute_telegram_operation", execute)
    update = {
        "update_id": 1,
        "callback_query": {
            "id": "callback-1",
            "from": {"id": 123},
            "data": "confirm",
            "message": {"message_id": 2, "chat": {"id": 123, "type": "private"}},
        },
    }

    await main.handle_telegram_update(update, "123", runtime)

    assert operations[:2] == ["answerCallbackQuery", "sendMessage"]
    telegram_to_run.assert_awaited_once()
    telegram_to_run_call = telegram_to_run.await_args
    assert telegram_to_run_call is not None
    assert telegram_to_run_call.kwargs["stream"] is True
    agent.create_session.assert_called_once_with(session_id="123")
    agent.run.assert_called_once_with(["confirm"], session=session, options={}, stream=True)
    deliver.assert_awaited_once_with(runtime, stream, chat_id=123, message_id=42)


async def test_resolves_media_to_bounded_data_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = "must-not-leak"
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"image-bytes",
                headers={"content-length": "11"},
                request=request,
            )
        )
    )
    runtime = cast(Any, SimpleNamespace(bot_token=sentinel, http=http))
    execute = AsyncMock(return_value={"file_path": "photos/file.jpg", "file_size": 11})
    monkeypatch.setattr(main, "execute_telegram_operation", execute)

    result = await main.resolve_telegram_file("file-id", runtime, media_type="image/jpeg")
    await http.aclose()

    assert result == "data:image/jpeg;base64,aW1hZ2UtYnl0ZXM="
    assert sentinel not in result


@pytest.mark.parametrize(
    "message_fields",
    [
        {"voice": {"file_id": "voice-1", "mime_type": "audio/ogg"}},
        {"video": {"file_id": "video-1", "mime_type": "video/mp4"}},
        {"document": {"file_id": "document-1", "mime_type": "text/plain"}},
    ],
)
async def test_rejects_media_the_model_serializer_does_not_support(
    message_fields: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = AsyncMock(return_value={})
    agent = SimpleNamespace(run=Mock())
    runtime = cast(Any, SimpleNamespace(agent=agent))
    monkeypatch.setattr(main, "execute_telegram_operation", execute)

    await main.handle_telegram_update(_message_update(text="", **message_fields), "123", runtime)

    execute_call = execute.await_args
    assert execute_call is not None
    operation = execute_call.args[1]
    assert operation["method"] == "sendMessage"
    assert "photos, PDF documents, and MP3 or WAV audio" in operation["payload"]["text"]
    agent.run.assert_not_called()


async def test_normalizes_telegram_mpeg_audio_for_model_serialization(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = _empty_stream()
    agent = SimpleNamespace(
        create_session=Mock(return_value=object()),
        run=Mock(return_value=stream),
    )
    runtime = cast(Any, SimpleNamespace(agent=agent))
    monkeypatch.setattr(
        main,
        "resolve_telegram_file",
        AsyncMock(return_value="data:audio/mp3;base64,bXAz"),
    )
    monkeypatch.setattr(
        main,
        "execute_telegram_operation",
        AsyncMock(return_value={"message_id": 42}),
    )
    monkeypatch.setattr(main, "deliver_stream", AsyncMock())

    await main.handle_telegram_update(
        _message_update(text="", audio={"file_id": "audio-1", "mime_type": "audio/mpeg"}),
        "123",
        runtime,
    )

    messages = agent.run.call_args.args[0]
    content = messages[0].contents[0]
    assert content.type == "data"
    assert content.media_type == "audio/mp3"
    assert content.uri == "data:audio/mp3;base64,bXAz"
    serialized = OpenAIChatClient(
        api_key="test",
        model="test",
    )._prepare_content_for_openai(  # pyright: ignore[reportPrivateUsage]
        "user",
        content,
    )
    assert serialized == {
        "type": "input_audio",
        "input_audio": {"data": "data:audio/mp3;base64,bXAz", "format": "mp3"},
    }


@pytest.mark.parametrize(
    ("media_type", "expected_type"),
    [
        ("image/jpeg", "input_image"),
        ("application/pdf", "input_file"),
        ("audio/mp3", "input_audio"),
        ("audio/wav", "input_audio"),
    ],
)
def test_supported_media_types_serialize_for_foundry(
    media_type: str,
    expected_type: str,
) -> None:
    content = Content.from_uri(uri=f"data:{media_type};base64,dGVzdA==", media_type=media_type)

    serialized = OpenAIChatClient(
        api_key="test",
        model="test",
    )._prepare_content_for_openai(  # pyright: ignore[reportPrivateUsage]
        "user",
        content,
    )

    assert serialized["type"] == expected_type


async def test_rejects_media_over_size_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    http = SimpleNamespace(stream=Mock())
    runtime = cast(Any, SimpleNamespace(http=http))
    monkeypatch.setattr(
        main,
        "execute_telegram_operation",
        AsyncMock(return_value={"file_path": "large.bin", "file_size": main.MAX_MEDIA_BYTES + 1}),
    )

    assert await main.resolve_telegram_file("large-file", runtime) is None
    http.stream.assert_not_called()
    assert main.MAX_MEDIA_BYTES == 1024 * 1024


async def test_stops_media_stream_when_download_exceeds_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "MAX_MEDIA_BYTES", 4)
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"12345", request=request))
    )
    runtime = cast(Any, SimpleNamespace(bot_token="test-value", http=http))
    monkeypatch.setattr(
        main,
        "execute_telegram_operation",
        AsyncMock(return_value={"file_path": "large.bin"}),
    )

    result = await main.resolve_telegram_file("large-file", runtime)
    await http.aclose()

    assert result is None


async def test_unresolved_media_preserves_caption() -> None:
    update = _message_update(
        text="",
        caption="describe this",
        photo=[{"file_id": "photo-1", "file_size": 10}],
    )

    run = await main.telegram_to_run(update, resolve_file_url=AsyncMock(return_value=None), stream=True)

    assert run["messages"][0].text == "describe this"
    assert run["stream"] is True


async def test_telegram_error_never_contains_bot_token() -> None:
    sentinel = "must-not-leak"
    http = SimpleNamespace(
        post=AsyncMock(
            return_value=_response(
                400,
                {"ok": False, "description": "Bad Request: chat not found"},
            )
        )
    )
    runtime = cast(Any, SimpleNamespace(bot_token=sentinel, http=http))
    operation = {"method": "sendMessage", "payload": {"chat_id": 1, "text": "hello"}}

    with pytest.raises(RuntimeError) as exc_info:
        await main.execute_telegram_operation(runtime, operation)

    assert sentinel not in str(exc_info.value)


async def test_transport_error_does_not_chain_token_bearing_url() -> None:
    sentinel = "must-not-leak"
    request = httpx.Request("POST", f"https://api.telegram.org/bot{sentinel}/sendMessage")
    runtime = cast(
        Any,
        SimpleNamespace(
            bot_token=sentinel,
            http=SimpleNamespace(post=AsyncMock(side_effect=httpx.ConnectError("connection failed", request=request))),
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await main.execute_telegram_operation(
            runtime,
            {"method": "sendMessage", "payload": {"chat_id": 1, "text": "hello"}},
        )

    assert sentinel not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


async def test_unchanged_edit_is_the_only_ignored_telegram_error() -> None:
    unchanged = SimpleNamespace(
        bot_token="test-value",
        http=SimpleNamespace(
            post=AsyncMock(
                return_value=_response(
                    400,
                    {"ok": False, "description": "Bad Request: message is not modified"},
                )
            )
        ),
    )
    operation = {"method": "editMessageText", "payload": {"chat_id": 1, "message_id": 2, "text": "same"}}
    assert await main.execute_telegram_operation(cast(Any, unchanged), operation) == {}

    other_error = SimpleNamespace(
        bot_token="test-value",
        http=SimpleNamespace(
            post=AsyncMock(
                return_value=_response(
                    400,
                    {"ok": False, "description": "Bad Request: message cannot be edited"},
                )
            )
        ),
    )
    with pytest.raises(RuntimeError, match="message cannot be edited"):
        await main.execute_telegram_operation(cast(Any, other_error), operation)


async def test_cumulative_edits_are_throttled(monkeypatch: pytest.MonkeyPatch) -> None:
    async def operations(*_: Any, **__: Any) -> AsyncIterator[dict[str, Any]]:
        yield {"method": "editMessageText", "payload": {"text": "hel"}}
        yield {"method": "editMessageText", "payload": {"text": "hello"}}

    monotonic = Mock(side_effect=[1.0, 1.0, 1.1, 1.4])
    sleep = AsyncMock()
    execute = AsyncMock(return_value={})
    monkeypatch.setattr(main, "_stream_operations", operations)
    monkeypatch.setattr(main, "execute_telegram_operation", execute)

    await main.deliver_stream(
        cast(Any, SimpleNamespace()),
        _empty_stream(),
        chat_id=1,
        message_id=42,
        clock=monotonic,
        sleep=sleep,
    )

    sleep.assert_awaited_once_with(pytest.approx(0.3))
    assert [item.args[1]["payload"]["text"] for item in execute.await_args_list] == ["hel", "hello"]


async def test_image_only_stream_deletes_placeholder_and_sends_photo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def updates() -> AsyncIterator[AgentResponseUpdate]:
        yield AgentResponseUpdate(
            contents=[Content.from_uri(uri="https://example.com/cat.png", media_type="image/png")],
            role="assistant",
        )

    stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)
    agent = SimpleNamespace(
        create_session=Mock(return_value=object()),
        run=Mock(return_value=stream),
    )
    runtime = cast(Any, SimpleNamespace(agent=agent))
    monkeypatch.setattr(
        main,
        "telegram_to_run",
        AsyncMock(return_value={"messages": ["photo"], "options": {}, "stream": True}),
    )
    methods: list[str] = []

    async def execute(_: Any, operation: Any) -> dict[str, Any]:
        methods.append(operation["method"])
        return {"message_id": 42} if operation["method"] == "sendMessage" else {}

    monkeypatch.setattr(main, "execute_telegram_operation", execute)

    await main.handle_telegram_update(_message_update("show a cat"), "123", runtime)

    assert methods == ["sendMessage", "deleteMessage", "sendPhoto"]


async def test_requires_response_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = SimpleNamespace(
        create_session=Mock(return_value=object()),
        run=Mock(return_value=object()),
    )
    runtime = cast(Any, SimpleNamespace(agent=agent))
    monkeypatch.setattr(
        main,
        "telegram_to_run",
        AsyncMock(return_value={"messages": ["hello"], "options": {}, "stream": True}),
    )
    monkeypatch.setattr(main, "execute_telegram_operation", AsyncMock(return_value={"message_id": 42}))

    with pytest.raises(RuntimeError, match="response stream"):
        await main.handle_telegram_update(_message_update(), "123", runtime)
