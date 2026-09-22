# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

import httpx2
import pytest
from agent_framework import Agent, Content, FunctionTool, Message
from agent_framework._mcp import MCPTool
from agent_framework.exceptions import (
    ChatClientException,
    ChatClientInvalidAuthException,
    ChatClientInvalidRequestException,
    ChatClientInvalidResponseException,
    SettingNotFoundError,
)
from pydantic import BaseModel
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    Noul,
    Questions,
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

from agent_framework_typesafe import RawTypeSafeChatClient, TypeSafeChatClient, TypeSafeChatOptions


class _ConnectedMCPTool(MCPTool):
    """Connected MCP stand-in exposing discovered FunctionTool objects."""

    def __init__(self, function: FunctionTool) -> None:
        super().__init__(name="test-mcp")
        self.is_connected = True
        self._functions = [function]

    def get_mcp_client(self) -> contextlib.AbstractAsyncContextManager[Any]:  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
        raise NotImplementedError


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
        responses: list[SystemOneResponse] | None = None,
        responder: Callable[[Questions], SystemOneResponse] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or make_response()
        self.responses = list(responses or [])
        self.responder = responder
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def system_one(
        self,
        state: Any,
        questions: Questions,
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
        if self.responder is not None:
            return self.responder(questions)
        if self.responses:
            return self.responses.pop(0)
        return self.response

    async def aclose(self) -> None:
        self.closed = True


def make_response(answers: dict[str, dict[str, Any]] | None = None) -> StubSystemOneResponse:
    """Create a representative TypeSafe response."""
    return StubSystemOneResponse.model_validate({
        "model": "jev-latest",
        "usage": {"input_tokens": 12, "output_tokens": 4},
        "answers": answers or {"urgent": {"type": "noul", "noul": 0.9}},
    })


def make_client(stub: StubTypeSafeClient | None = None, *, model: str | None = None) -> TypeSafeChatClient:
    """Create a TypeSafeChatClient with an injected stub SDK client."""
    return TypeSafeChatClient(
        async_client=cast(AsyncTypeSafeClient, stub or StubTypeSafeClient()),
        model=model,
    )


def questions() -> Questions:
    """Create a valid question mapping."""
    return {"urgent": Noul(instructions="Is this urgent?")}


def test_public_client_layers_raw_client() -> None:
    assert issubclass(TypeSafeChatClient, RawTypeSafeChatClient)


def test_construction_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    with pytest.raises(SettingNotFoundError, match="TYPESAFE_API_KEY"):
        TypeSafeChatClient()


def test_injected_client_takes_precedence_over_api_key() -> None:
    stub = StubTypeSafeClient()

    client = TypeSafeChatClient(
        api_key="test-key",
        async_client=cast(AsyncTypeSafeClient, stub),
    )

    assert client.client is stub


def test_construction_resolves_environment_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubTypeSafeClient()
    captured: dict[str, Any] = {}
    monkeypatch.setenv("TYPESAFE_API_KEY", "environment-key")
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-preview")
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://typesafe.example/")

    def create_client(**kwargs: Any) -> StubTypeSafeClient:
        captured.update(kwargs)
        return stub

    monkeypatch.setattr(
        "agent_framework_typesafe._chat_client.AsyncTypeSafeClient",
        create_client,
    )

    client = TypeSafeChatClient()

    assert client.client is stub
    assert client.model == "jev-preview"
    assert client.base_url == "https://typesafe.example/"
    assert client.service_url() == "https://typesafe.example/v1/systemone"
    assert captured["api_key"] == "environment-key"
    assert captured["model"] == "jev-preview"
    assert captured["base_url"] == "https://typesafe.example/"


def test_construction_resolves_selected_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stub = StubTypeSafeClient()
    captured: dict[str, Any] = {}
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TYPESAFE_API_KEY=file-key\nTYPESAFE_DEFAULT_MODEL=file-model\nTYPESAFE_BASE_URL=https://file.example/\n",
        encoding="utf-8",
    )

    def create_client(**kwargs: Any) -> StubTypeSafeClient:
        captured.update(kwargs)
        return stub

    monkeypatch.setattr(
        "agent_framework_typesafe._chat_client.AsyncTypeSafeClient",
        create_client,
    )

    client = TypeSafeChatClient(env_file_path=str(env_path))

    assert client.model == "file-model"
    assert client.base_url == "https://file.example/"
    assert client.service_url() == "https://file.example/v1/systemone"
    assert captured["api_key"] == "file-key"
    assert captured["base_url"] == "https://file.example/"


def test_injected_client_ignores_ambient_model_and_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubTypeSafeClient()
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "ambient-model")
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://ambient.example")

    client = TypeSafeChatClient(async_client=cast(AsyncTypeSafeClient, stub))

    assert client.model is None
    assert client.base_url is None
    assert client.service_url() == "Unknown"


def test_injected_client_accepts_explicit_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubTypeSafeClient()
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "ambient-model")

    client = TypeSafeChatClient(
        async_client=cast(AsyncTypeSafeClient, stub),
        model="explicit-model",
    )

    assert client.model == "explicit-model"


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


async def test_streaming_is_rejected_on_consumption() -> None:
    client = make_client()

    stream = client.get_response(
        [Message("user", ["hello"])],
        stream=True,
        options={"response_format": questions()},
    )
    with pytest.raises(ChatClientInvalidRequestException, match="streaming"):
        _ = [update async for update in stream]


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({}, "non-empty typesafe_sdk.Questions"),
        ({"response_format": {}}, "non-empty typesafe_sdk.Questions"),
        ({"response_format": questions(), "questions": questions()}, "questions"),
        ({"response_format": questions(), "temperature": 0.2}, "temperature"),
        ({"response_format": questions(), "tools": [object()]}, "FunctionTool"),
        ({"response_format": questions(), "tool_choice": "required"}, "no tools"),
        ({"response_format": questions(), "allow_multiple_tool_calls": True}, "one tool call"),
        ({"response_format": SystemOneResponse}, "non-empty typesafe_sdk.Questions"),
        ({"response_format": {1: Noul(instructions="invalid")}}, "question IDs must be strings"),
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

    with pytest.raises(ChatClientInvalidRequestException, match="only supports text and function"):
        await client.get_response([message], options={"response_format": questions()})


async def test_empty_text_messages_are_rejected() -> None:
    client = make_client()

    with pytest.raises(ChatClientInvalidRequestException, match="non-empty text message"):
        await client.get_response([Message("user", [""])], options={"response_format": questions()})


async def test_rich_function_result_content_is_rejected() -> None:
    client = make_client()
    rich_result = Content.from_function_result(
        call_id="call-1",
        result=[Content.from_uri("https://example.com/chart.png", media_type="image/png")],
    )

    with pytest.raises(ChatClientInvalidRequestException, match="text items only"):
        await client.get_response(
            [
                Message("user", ["show a chart"]),
                Message("tool", [rich_result]),
            ],
            options={"response_format": questions()},
        )


def test_text_function_result_items_are_serialized() -> None:
    result = Content.from_function_result(
        call_id="call-1",
        result=[Content.from_text("first"), Content.from_text("second")],
    )

    state = RawTypeSafeChatClient._build_state(  # pyright: ignore[reportPrivateUsage]
        [Message("user", ["run"]), Message("tool", [result])],
        instructions=None,
    )

    assert state["messages"][1]["contents"][0] == {
        "type": "function_result",
        "call_id": "call-1",
        "result": "first\nsecond",
        "items": [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ],
    }


def test_simple_mcp_result_wrapper_is_unwrapped() -> None:
    result = RawTypeSafeChatClient._get_current_turn_function_result_texts(  # pyright: ignore[reportPrivateUsage]
        [
            Message(
                "tool",
                [Content.from_function_result(call_id="call-1", result='{"result": "Paris is sunny."}')],
            )
        ]
    )

    assert result == ["Paris is sunny."]


async def test_client_kwargs_are_rejected() -> None:
    client = make_client()

    with pytest.raises(ChatClientInvalidRequestException, match="client-specific arguments"):
        await client.get_response(
            [Message("user", ["hello"])],
            options={"response_format": questions()},
            client_kwargs={"unsupported": True},
        )


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"response_format": questions(), "model": 123}, "model must be a string"),
        ({"response_format": questions(), "instructions": ["invalid"]}, "instructions must be a string"),
    ],
)
async def test_invalid_common_option_types_are_rejected(options: dict[str, Any], message: str) -> None:
    client = make_client()

    with pytest.raises(ChatClientInvalidRequestException, match=message):
        await client.get_response(
            [Message("user", ["hello"])],
            options=cast(TypeSafeChatOptions, options),
        )


async def test_invalid_model_is_rejected_before_tool_compilation(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client()

    def fail_if_called(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("tool compilation should not run")

    monkeypatch.setattr(
        "agent_framework_typesafe._chat_client.compile_tool_call_plan",
        fail_if_called,
    )

    with pytest.raises(ChatClientInvalidRequestException, match="model must be a string"):
        await client.get_response(
            [Message("user", ["hello"])],
            options=cast(TypeSafeChatOptions, {"response_format": questions(), "model": 123}),
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
            "response_format": questions(),
            "instructions": "Evaluate the conversation.",
            "model": "jev-preview",
        },
    )

    assert stub.calls == [
        {
            "state": {
                "messages": [
                    {"role": "user", "contents": [{"type": "text", "text": "first"}]},
                    {"role": "assistant", "contents": [{"type": "text", "text": "second"}]},
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
            options={"response_format": questions()},
        )


async def test_unexpected_response_type_is_rejected() -> None:
    stub = StubTypeSafeClient()
    stub.response = cast(SystemOneResponse, object())
    client = make_client(stub)

    with pytest.raises(ChatClientInvalidResponseException, match="does not match SystemOneResponse"):
        await client.get_response(
            [Message("user", ["hello"])],
            options={"response_format": questions()},
        )


async def test_questions_response_format_forces_system_one_response_model() -> None:
    stub = StubTypeSafeClient()
    client = make_client(stub)

    await client.get_response(
        [Message("user", ["hello"])],
        options={"response_format": questions()},
    )

    assert stub.calls[0]["questions"] == questions()
    assert stub.calls[0]["response_model"] is SystemOneResponse


async def test_agent_integration_preserves_structured_value() -> None:
    stub = StubTypeSafeClient()
    agent = Agent(
        client=make_client(stub),
        name="Evaluator",
        instructions="Evaluate the request.",
    )

    response = await agent.run(
        "Please help now.",
        options=cast(Any, {"response_format": questions()}),
    )

    assert response.value is stub.response
    assert isinstance(response.value, SystemOneResponse)
    assert stub.calls[0]["state"]["instructions"] == "Evaluate the request."


async def test_raw_client_decodes_closed_set_arguments_and_omits_optional_defaults() -> None:
    class ToolArguments(BaseModel):
        value: Literal[1, "1"]
        unit: Literal["celsius", "fahrenheit"] = "celsius"
        detailed: bool
        tags: list[Literal["forecast", "alerts"]]

    function = FunctionTool(
        name="inspect",
        description="Inspect a configured item.",
        func=lambda **kwargs: kwargs,
        input_model=ToolArguments,
    )
    response = make_response({
        "urgent": {"type": "noul", "noul": 0.1},
        "__af_tool__.t0.a0.value": {
            "type": "choice",
            "choice": "v1",
            "confidence": 1.0,
            "probabilities": {"v0": 0.0, "v1": 1.0},
        },
        "__af_tool__.t0.a1.present": {"type": "noul", "noul": 0.0},
        "__af_tool__.t0.a1.value": {
            "type": "choice",
            "choice": "v0",
            "confidence": 1.0,
            "probabilities": {"v0": 1.0, "v1": 0.0},
        },
        "__af_tool__.t0.a2.value": {"type": "noul", "noul": 0.9},
        "__af_tool__.t0.a3.m0": {"type": "noul", "noul": 0.2},
        "__af_tool__.t0.a3.m1": {"type": "noul", "noul": 0.8},
    })
    client = RawTypeSafeChatClient(async_client=cast(AsyncTypeSafeClient, StubTypeSafeClient(response=response)))

    result = await client.get_response(
        [Message("user", ["inspect string one in detail with alerts"])],
        options={
            "response_format": questions(),
            "tools": [function],
            "tool_choice": {"mode": "required", "required_function_name": "inspect"},
        },
    )

    assert result.text == ""
    assert result.value is None
    assert result.finish_reason == "tool_calls"
    call = result.messages[0].contents[0]
    assert call.type == "function_call"
    assert call.name == "inspect"
    assert call.parse_arguments() == {
        "value": "1",
        "detailed": True,
        "tags": ["alerts"],
    }


async def test_no_tool_route_filters_internal_answers() -> None:
    function = FunctionTool(name="list_symbols", description="List symbols", func=lambda: "symbols")
    response = make_response({
        "urgent": {"type": "noul", "noul": 0.9},
        "__af_tool__.route": {
            "type": "choice",
            "choice": "none",
            "confidence": 1.0,
            "probabilities": {"t0": 0.0, "none": 1.0},
        },
    })
    client = RawTypeSafeChatClient(async_client=cast(AsyncTypeSafeClient, StubTypeSafeClient(response=response)))

    result = await client.get_response(
        [Message("user", ["No tool needed"])],
        options={"response_format": questions(), "tools": [function]},
    )

    assert isinstance(result.value, SystemOneResponse)
    assert set(result.value.answers) == {"urgent"}
    assert "__af_tool__" not in result.text


async def test_local_tool_executes_once_then_returns_structured_response() -> None:
    calls: list[tuple[str, bool]] = []

    class WeatherArguments(BaseModel):
        city: Literal["Seattle", "Paris"]
        detailed: bool

    def weather(city: str, detailed: bool) -> str:
        calls.append((city, detailed))
        return f"Weather for {city}; detailed={detailed}"

    function = FunctionTool(
        name="weather",
        description="Get weather for a supported city.",
        func=weather,
        input_model=WeatherArguments,
    )
    stub = StubTypeSafeClient(
        responses=[
            make_response({
                "urgent": {"type": "noul", "noul": 0.1},
                "__af_tool__.route": {
                    "type": "choice",
                    "choice": "t0",
                    "confidence": 1.0,
                    "probabilities": {"t0": 1.0, "none": 0.0},
                },
                "__af_tool__.t0.a0.value": {
                    "type": "choice",
                    "choice": "v0",
                    "confidence": 1.0,
                    "probabilities": {"v0": 1.0, "v1": 0.0},
                },
                "__af_tool__.t0.a1.value": {"type": "noul", "noul": 0.9},
            }),
            make_response({"urgent": {"type": "noul", "noul": 0.8}}),
        ]
    )
    agent = Agent(client=make_client(stub), tools=[function])

    response = await agent.run(
        "Give me detailed Seattle weather.",
        options=cast(Any, {"response_format": questions()}),
    )

    assert calls == [("Seattle", True)]
    assert isinstance(response.value, SystemOneResponse)
    assert set(response.value.answers) == {"urgent"}
    assert response.text == "Weather for Seattle; detailed=True"
    assert len(stub.calls) == 2
    assert "__af_tool__.route" in stub.calls[0]["questions"]
    assert set(stub.calls[1]["questions"]) == {"urgent"}
    tool_results = [
        content
        for message in stub.calls[1]["state"]["messages"]
        for content in message["contents"]
        if content["type"] == "function_result"
    ]
    assert tool_results == [
        {
            "type": "function_result",
            "call_id": cast(str, tool_results[0]["call_id"]),
            "result": "Weather for Seattle; detailed=True",
            "items": [{"type": "text", "text": "Weather for Seattle; detailed=True"}],
        }
    ]


async def test_agent_expands_and_executes_compatible_mcp_tool() -> None:
    executions: list[bool] = []

    def refresh_cache() -> str:
        executions.append(True)
        return "refreshed"

    function = FunctionTool(
        name="refresh_cache",
        description="Refresh a cache.",
        func=refresh_cache,
        input_model={},
    )
    mcp_tool = _ConnectedMCPTool(function)
    stub = StubTypeSafeClient(
        responses=[
            make_response({
                "urgent": {"type": "noul", "noul": 0.1},
                "__af_tool__.route": {
                    "type": "choice",
                    "choice": "t0",
                    "confidence": 1.0,
                    "probabilities": {"t0": 1.0, "none": 0.0},
                },
            }),
            make_response({"urgent": {"type": "noul", "noul": 0.6}}),
        ]
    )
    agent = Agent(client=make_client(stub), tools=[mcp_tool])

    response = await agent.run("Refresh the cache.", options=cast(Any, {"response_format": questions()}))

    assert executions == [True]
    assert isinstance(response.value, SystemOneResponse)
    assert response.text == "refreshed"
    assert stub.calls[0]["questions"]["__af_tool__.route"]


async def test_direct_mcp_tool_requires_agent_expansion() -> None:
    mcp_tool = _ConnectedMCPTool(FunctionTool(name="noop", func=lambda: "done", input_model={}))
    client = make_client()

    with pytest.raises(ChatClientInvalidRequestException, match="Pass MCPTool objects through Agent.run"):
        await client.get_response(
            [Message("user", ["run"])],
            options=cast(Any, {"response_format": questions(), "tools": [mcp_tool]}),
        )


async def test_required_unsupported_tool_schema_is_rejected() -> None:
    function = FunctionTool(
        name="search",
        description="Search arbitrary text.",
        func=lambda query: query,
        input_model={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    client = RawTypeSafeChatClient(async_client=cast(AsyncTypeSafeClient, StubTypeSafeClient()))

    with pytest.raises(ChatClientInvalidRequestException, match="no supported tools remain"):
        await client.get_response(
            [Message("user", ["search"])],
            options={
                "response_format": questions(),
                "tools": [function],
                "tool_choice": "required",
            },
        )


async def test_tool_approval_pauses_before_execution() -> None:
    executions: list[bool] = []

    def guarded() -> str:
        executions.append(True)
        return "done"

    function = FunctionTool(
        name="guarded",
        description="Run a guarded action.",
        func=guarded,
        input_model={},
        approval_mode="always_require",
    )
    stub = StubTypeSafeClient(
        response=make_response({
            "urgent": {"type": "noul", "noul": 0.1},
            "__af_tool__.route": {
                "type": "choice",
                "choice": "t0",
                "confidence": 1.0,
                "probabilities": {"t0": 1.0, "none": 0.0},
            },
        })
    )
    agent = Agent(client=make_client(stub), tools=[function])

    response = await agent.run("Run the guarded action.", options=cast(Any, {"response_format": questions()}))

    assert executions == []
    assert any(
        content.type == "function_approval_request" for message in response.messages for content in message.contents
    )


async def test_session_can_route_a_tool_on_later_independent_runs() -> None:
    executions: list[int] = []

    def increment() -> str:
        executions.append(len(executions) + 1)
        return str(executions[-1])

    function = FunctionTool(name="increment", description="Increment a counter.", func=increment, input_model={})
    route_response = {
        "urgent": {"type": "noul", "noul": 0.1},
        "__af_tool__.route": {
            "type": "choice",
            "choice": "t0",
            "confidence": 1.0,
            "probabilities": {"t0": 1.0, "none": 0.0},
        },
    }
    stub = StubTypeSafeClient(
        responses=[
            make_response(route_response),
            make_response({"urgent": {"type": "noul", "noul": 0.6}}),
            make_response(route_response),
            make_response({"urgent": {"type": "noul", "noul": 0.7}}),
        ]
    )
    agent = Agent(client=make_client(stub), tools=[function])
    session = agent.create_session()

    first = await agent.run("Increment once.", session=session, options=cast(Any, {"response_format": questions()}))
    second = await agent.run("Increment again.", session=session, options=cast(Any, {"response_format": questions()}))

    assert executions == [1, 2]
    assert isinstance(first.value, SystemOneResponse)
    assert isinstance(second.value, SystemOneResponse)
    assert len(stub.calls) == 4


async def test_multiple_tool_roundtrips_return_consolidated_results() -> None:
    forecasts = {
        "Seattle": "Seattle is rainy and 18 C.",
        "Amsterdam": "Amsterdam is sunny and 24 C.",
    }
    executions: list[str] = []

    class WeatherArguments(BaseModel):
        city: Literal["Seattle", "Amsterdam"]

    def weather(city: str) -> str:
        executions.append(city)
        return forecasts[city]

    function = FunctionTool(
        name="weather",
        description="Get weather for Seattle or Amsterdam.",
        func=weather,
        input_model=WeatherArguments,
    )
    stub = StubTypeSafeClient(
        responses=[
            make_response({
                "better_city": {
                    "type": "choice",
                    "choice": "Seattle",
                    "confidence": 0.5,
                    "probabilities": {"Seattle": 0.5, "Amsterdam": 0.5},
                },
                "__af_tool__.route": {
                    "type": "choice",
                    "choice": "t0",
                    "confidence": 1.0,
                    "probabilities": {"t0": 1.0, "none": 0.0},
                },
                "__af_tool__.t0.a0.value": {
                    "type": "choice",
                    "choice": "v0",
                    "confidence": 1.0,
                    "probabilities": {"v0": 1.0, "v1": 0.0},
                },
            }),
            make_response({
                "better_city": {
                    "type": "choice",
                    "choice": "Amsterdam",
                    "confidence": 0.6,
                    "probabilities": {"Seattle": 0.4, "Amsterdam": 0.6},
                },
                "__af_tool__.route": {
                    "type": "choice",
                    "choice": "t0",
                    "confidence": 1.0,
                    "probabilities": {"t0": 1.0, "none": 0.0},
                },
                "__af_tool__.t0.a0.value": {
                    "type": "choice",
                    "choice": "v1",
                    "confidence": 1.0,
                    "probabilities": {"v0": 0.0, "v1": 1.0},
                },
            }),
            make_response({
                "better_city": {
                    "type": "choice",
                    "choice": "Amsterdam",
                    "confidence": 1.0,
                    "probabilities": {"Seattle": 0.0, "Amsterdam": 1.0},
                },
                "__af_tool__.route": {
                    "type": "choice",
                    "choice": "none",
                    "confidence": 1.0,
                    "probabilities": {"t0": 0.0, "none": 1.0},
                },
            }),
        ]
    )
    client = TypeSafeChatClient(
        async_client=cast(AsyncTypeSafeClient, stub),
        function_invocation_configuration={"max_function_calls": 4},
    )
    agent = Agent(client=client, tools=[function])

    response = await agent.run(
        "Compare Seattle and Amsterdam weather.",
        options=cast(
            Any,
            {
                "response_format": {
                    "better_city": Choice(
                        instructions="Which city has better weather based on the tool results?",
                        criteria={"Seattle": None, "Amsterdam": None},
                    )
                }
            },
        ),
    )

    assert executions == ["Seattle", "Amsterdam"]
    assert response.text == ("Seattle is rainy and 18 C.\nAmsterdam is sunny and 24 C.\nbetter_city: Amsterdam")


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
            options={"response_format": questions()},
        )
