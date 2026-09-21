# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import httpx2
import pytest
from agent_framework import Agent, Content, Message
from agent_framework.exceptions import (
    ChatClientException,
    ChatClientInvalidAuthException,
    ChatClientInvalidRequestException,
    ChatClientInvalidResponseException,
    SettingNotFoundError,
)
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Noul,
    Question,
    SystemOneResponse,
    TypeSafeAPIConnectionError,
    TypeSafeAPIResponseValidationError,
    TypeSafeAuthenticationError,
    TypeSafeBadRequestError,
    TypeSafeError,
    TypeSafeInternalServerError,
    TypeSafePermissionDeniedError,
    TypeSafeUnprocessableEntityError,
)

from agent_framework_typesafe import TypeSafeChatClient, TypeSafeChatOptions


class StubSystemOneResponse(SystemOneResponse):
    """SystemOneResponse with deterministic request metadata."""

    @property
    def request_id(self) -> str:
        """Return a deterministic request identifier."""
        return "request-123"


class StubTypeSafeClient:
    """In-memory stand-in for AsyncTypeSafeClient."""

    def __init__(
        self,
        response: SystemOneResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or make_response()
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def system_one(
        self,
        state: Any,
        questions: Mapping[str, Question],
        *,
        model: str | None = None,
        response_model: type[SystemOneResponse] | None = None,
        **kwargs: Any,
    ) -> SystemOneResponse:
        self.calls.append({
            "state": state,
            "questions": questions,
            "model": model,
            "response_model": response_model,
            **kwargs,
        })
        if self.error is not None:
            raise self.error
        return self.response

    async def aclose(self) -> None:
        self.closed = True


def make_response() -> StubSystemOneResponse:
    """Create a representative TypeSafe response."""
    return StubSystemOneResponse.model_validate({
        "model": "jev-latest",
        "usage": {"input_tokens": 12, "output_tokens": 4},
        "answers": {"urgent": {"type": "noul", "noul": 0.9}},
    })


def make_client(stub: StubTypeSafeClient | None = None, *, model: str | None = None) -> TypeSafeChatClient:
    """Create a TypeSafeChatClient with an injected stub SDK client."""
    return TypeSafeChatClient(
        async_client=cast(AsyncTypeSafeClient, stub or StubTypeSafeClient()),
        model=model,
    )


def questions() -> dict[str, Question]:
    """Create a valid question mapping."""
    return {"urgent": Noul(instructions="Is this urgent?")}


def test_construction_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    with pytest.raises(SettingNotFoundError, match="TypeSafe API key is required"):
        TypeSafeChatClient()


def test_construction_rejects_api_key_with_injected_client() -> None:
    with pytest.raises(ValueError, match="either 'api_key' or 'async_client'"):
        TypeSafeChatClient(
            api_key="test-key",
            async_client=cast(AsyncTypeSafeClient, StubTypeSafeClient()),
        )


async def test_close_leaves_injected_client_open() -> None:
    stub = StubTypeSafeClient()
    client = make_client(stub)

    await client.close()

    assert not stub.closed


async def test_context_manager_closes_owned_client(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubTypeSafeClient()
    monkeypatch.setattr(
        "agent_framework_typesafe._chat_client.AsyncTypeSafeClient",
        lambda **_: stub,
    )

    async with TypeSafeChatClient(api_key="test-key"):
        pass

    assert stub.closed


def test_streaming_is_rejected_immediately() -> None:
    client = make_client()

    with pytest.raises(ChatClientInvalidRequestException, match="streaming"):
        client.get_response(
            [Message("user", ["hello"])],
            stream=True,
            options={"questions": questions()},
        )


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({}, "non-empty questions"),
        ({"questions": questions(), "temperature": 0.2}, "temperature"),
        ({"questions": questions(), "tools": [object()]}, "does not support tools"),
        ({"questions": questions(), "tool_choice": "required"}, "required tool choice"),
        ({"questions": questions(), "response_format": dict}, "SystemOneResponse"),
    ],
)
async def test_invalid_options_are_rejected(options: dict[str, Any], message: str) -> None:
    client = make_client()

    with pytest.raises(ChatClientInvalidRequestException, match=message):
        await client.get_response(
            [Message("user", ["hello"])],
            options=cast(TypeSafeChatOptions, options),
        )


async def test_non_text_content_is_rejected() -> None:
    client = make_client()
    message = Message("user", [Content.from_uri("https://example.com/image.png", media_type="image/png")])

    with pytest.raises(ChatClientInvalidRequestException, match="only supports text"):
        await client.get_response([message], options={"questions": questions()})


async def test_empty_text_messages_are_rejected() -> None:
    client = make_client()

    with pytest.raises(ChatClientInvalidRequestException, match="non-empty text message"):
        await client.get_response([Message("user", [""])], options={"questions": questions()})


async def test_client_kwargs_are_rejected() -> None:
    client = make_client()

    with pytest.raises(ChatClientInvalidRequestException, match="client-specific arguments"):
        await client.get_response(
            [Message("user", ["hello"])],
            options={"questions": questions()},
            client_kwargs={"unsupported": True},
        )


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"questions": questions(), "model": 123}, "model must be a string"),
        ({"questions": questions(), "instructions": ["invalid"]}, "instructions must be a string"),
    ],
)
async def test_invalid_common_option_types_are_rejected(options: dict[str, Any], message: str) -> None:
    client = make_client()

    with pytest.raises(ChatClientInvalidRequestException, match=message):
        await client.get_response(
            [Message("user", ["hello"])],
            options=cast(TypeSafeChatOptions, options),
        )


async def test_request_and_response_mapping() -> None:
    stub = StubTypeSafeClient()
    client = make_client(stub, model="jev-latest")

    response = await client.get_response(
        [
            Message("user", ["first"]),
            Message("assistant", ["second"]),
        ],
        options={
            "questions": questions(),
            "instructions": "Evaluate the conversation.",
            "model": "jev-preview",
        },
    )

    assert stub.calls == [
        {
            "state": {
                "messages": [
                    {"role": "user", "content": "first"},
                    {"role": "assistant", "content": "second"},
                ],
                "instructions": "Evaluate the conversation.",
            },
            "questions": questions(),
            "model": "jev-preview",
            "response_model": SystemOneResponse,
        }
    ]
    assert response.response_id == "request-123"
    assert response.model == "jev-latest"
    assert response.finish_reason == "stop"
    assert response.usage_details == {
        "input_token_count": 12,
        "output_token_count": 4,
        "total_token_count": 16,
    }
    assert response.value is stub.response
    assert response.raw_representation is stub.response
    assert '"urgent"' in response.text


async def test_unexpected_sdk_exception_is_wrapped() -> None:
    client = make_client(StubTypeSafeClient(error=RuntimeError("unexpected")))

    with pytest.raises(ChatClientException, match="TypeSafe request failed"):
        await client.get_response(
            [Message("user", ["hello"])],
            options={"questions": questions()},
        )


async def test_unexpected_response_type_is_rejected() -> None:
    stub = StubTypeSafeClient()
    stub.response = cast(SystemOneResponse, object())
    client = make_client(stub)

    with pytest.raises(ChatClientInvalidResponseException, match="does not match SystemOneResponse"):
        await client.get_response(
            [Message("user", ["hello"])],
            options={"questions": questions()},
        )


async def test_response_format_subclass_is_forwarded() -> None:
    stub = StubTypeSafeClient()
    client = make_client(stub)

    await client.get_response(
        [Message("user", ["hello"])],
        options={
            "questions": questions(),
            "response_format": StubSystemOneResponse,
        },
    )

    assert stub.calls[0]["response_model"] is StubSystemOneResponse


async def test_agent_integration_preserves_structured_value() -> None:
    stub = StubTypeSafeClient()
    agent = Agent(
        client=make_client(stub),
        name="Evaluator",
        instructions="Evaluate the request.",
    )

    response = await agent.run(
        "Please help now.",
        options=cast(Any, {"questions": questions()}),
    )

    assert response.value is stub.response
    assert stub.calls[0]["state"]["instructions"] == "Evaluate the request."


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            TypeSafeAuthenticationError(401, {}, httpx2.Headers()),
            ChatClientInvalidAuthException,
        ),
        (
            TypeSafePermissionDeniedError(403, {}, httpx2.Headers()),
            ChatClientInvalidAuthException,
        ),
        (
            TypeSafeBadRequestError(400, {}, httpx2.Headers()),
            ChatClientInvalidRequestException,
        ),
        (
            TypeSafeUnprocessableEntityError(422, {}, httpx2.Headers()),
            ChatClientInvalidRequestException,
        ),
        (
            TypeSafeAPIResponseValidationError(200, {}, httpx2.Headers(), "answers.urgent"),
            ChatClientInvalidResponseException,
        ),
        (
            TypeSafeAPIConnectionError("connection failed"),
            ChatClientException,
        ),
        (
            TypeSafeInternalServerError(500, {}, httpx2.Headers()),
            ChatClientException,
        ),
        (
            TypeSafeError("invalid local request"),
            ChatClientInvalidRequestException,
        ),
    ],
)
async def test_sdk_errors_are_translated(error: Exception, expected: type[Exception]) -> None:
    client = make_client(StubTypeSafeClient(error=error))

    with pytest.raises(expected):
        await client.get_response(
            [Message("user", ["hello"])],
            options={"questions": questions()},
        )
