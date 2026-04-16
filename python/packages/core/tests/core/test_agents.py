# Copyright (c) Microsoft. All rights reserved.

import contextlib
import inspect
import json
from collections.abc import AsyncIterable, Awaitable, Callable, MutableSequence, Sequence
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pytest import raises

from agent_framework import (
    GROUP_ANNOTATION_KEY,
    GROUP_TOKEN_COUNT_KEY,
    Agent,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    ChatContext,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    ContextProvider,
    FunctionTool,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    ResponseStream,
    SessionContext,
    SlidingWindowStrategy,
    SupportsAgentRun,
    SupportsChatGetResponse,
    TruncationStrategy,
    chat_middleware,
    tool,
)
from agent_framework._agents import _get_tool_name, _merge_options, _sanitize_agent_name
from agent_framework._mcp import MCPTool, _build_prefixed_mcp_name, _normalize_mcp_name
from agent_framework._middleware import FunctionInvocationContext
from agent_framework.exceptions import AgentInvalidRequestException, ChatClientInvalidResponseException


class _FixedTokenizer:
    def __init__(self, token_count: int) -> None:
        self.token_count = token_count

    def count_tokens(self, text: str) -> int:
        return self.token_count


class _ConnectedMCPTool(MCPTool):
    def __init__(self, name: str, function_names: list[str], *, tool_name_prefix: str | None = None) -> None:
        super().__init__(name=name, tool_name_prefix=tool_name_prefix)
        self.is_connected = True
        self._functions = []
        for function_name in function_names:
            normalized_name = _normalize_mcp_name(function_name)
            exposed_name = _build_prefixed_mcp_name(normalized_name, self.tool_name_prefix)
            self._functions.append(
                FunctionTool(
                    func=lambda value=function_name: value,
                    name=exposed_name,
                    description=f"{function_name} from {name}",
                    additional_properties={
                        "_mcp_remote_name": function_name,
                        "_mcp_normalized_name": normalized_name,
                    },
                )
            )

    def get_mcp_client(self) -> contextlib.AbstractAsyncContextManager[Any]:
        raise NotImplementedError


class _RecordingHistoryProvider(HistoryProvider):
    def __init__(self, source_id: str = "recording_history") -> None:
        super().__init__(source_id=source_id)

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        if state is None:
            return []
        state["get_call_count"] = state.get("get_call_count", 0) + 1
        return list(cast(list[Message], state.get("messages", [])))

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if state is None:
            return
        state["save_call_count"] = state.get("save_call_count", 0) + 1
        state.setdefault("messages", []).extend(messages)


class _ResponseIdRecordingHistoryProvider(_RecordingHistoryProvider):
    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        state.setdefault("response_ids", []).append(context.response.response_id if context.response else None)
        await super().after_run(agent=agent, session=session, context=context, state=state)


def test_agent_session_type(agent_session: AgentSession) -> None:
    assert isinstance(agent_session, AgentSession)


def test_agent_type(agent: SupportsAgentRun) -> None:
    assert isinstance(agent, SupportsAgentRun)


async def test_agent_run(agent: SupportsAgentRun) -> None:
    response = await agent.run("test")
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "Response"


async def test_agent_run_with_content(agent: SupportsAgentRun) -> None:
    response = await agent.run(Content.from_text("test"))
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "Response"


async def test_agent_run_streaming(agent: SupportsAgentRun) -> None:
    async def collect_updates(
        updates: AsyncIterable[AgentResponseUpdate],
    ) -> list[AgentResponseUpdate]:
        return [u async for u in updates]

    updates = await collect_updates(agent.run("test", stream=True))
    assert len(updates) == 1
    assert updates[0].text == "Response"


def test_chat_client_agent_type(client: SupportsChatGetResponse) -> None:
    chat_client_agent = Agent(client=client)
    assert isinstance(chat_client_agent, SupportsAgentRun)


def test_chat_client_agent_uses_client_model_attribute(chat_client_base) -> None:
    chat_client_base.model = "claude-model"  # type: ignore[attr-defined]

    agent = Agent(client=chat_client_base)

    assert agent.default_options["model"] == "claude-model"
    assert "model_id" not in agent.default_options


def test_chat_client_agent_prefers_default_model_over_client_model(chat_client_base) -> None:
    chat_client_base.model = "legacy-model"  # type: ignore[attr-defined]

    agent = Agent(client=chat_client_base, default_options={"model": "claude-model"})

    assert agent.default_options["model"] == "claude-model"
    assert "model_id" not in agent.default_options


def test_agent_init_docstring_surfaces_raw_agent_constructor_docs() -> None:
    docstring = inspect.getdoc(Agent.__init__)

    assert docstring is not None
    assert "client: The chat client to use for the agent." in docstring
    assert "middleware: List of middleware to intercept agent and function invocations." in docstring


def test_agent_run_docstring_surfaces_raw_agent_runtime_docs() -> None:
    docstring = inspect.getdoc(Agent.run)

    assert docstring is not None
    assert "Run the agent with the given messages and options." in docstring
    assert "function_invocation_kwargs: Keyword arguments forwarded to tool invocation." in docstring
    assert "middleware: Optional per-run agent, chat, and function middleware." in docstring


def test_agent_run_is_defined_on_agent_class() -> None:
    signature = inspect.signature(Agent.run)

    assert Agent.run.__qualname__ == "Agent.run"
    assert "middleware" in signature.parameters


async def test_chat_client_agent_init(client: SupportsChatGetResponse) -> None:
    agent_id = str(uuid4())
    agent = Agent(client=client, id=agent_id, description="Test")

    assert agent.id == agent_id
    assert agent.name is None
    assert agent.description == "Test"


async def test_chat_client_agent_init_with_name(
    client: SupportsChatGetResponse,
) -> None:
    agent_id = str(uuid4())
    agent = Agent(client=client, id=agent_id, name="Test Agent", description="Test")

    assert agent.id == agent_id
    assert agent.name == "Test Agent"
    assert agent.description == "Test"


def test_agent_init_rejects_direct_additional_properties(client: SupportsChatGetResponse) -> None:
    with pytest.raises(TypeError):
        Agent(client=client, legacy_key="legacy-value")


async def test_chat_client_agent_run(client: SupportsChatGetResponse) -> None:
    agent = Agent(client=client)

    result = await agent.run("Hello")

    assert result.text == "test response"


async def test_chat_client_agent_run_streaming(client: SupportsChatGetResponse) -> None:
    agent = Agent(client=client)

    result = await AgentResponse.from_update_generator(agent.run("Hello", stream=True))

    assert result.text == "test streaming response another update"


async def test_chat_client_agent_streaming_response_format_from_default_options(
    client: SupportsChatGetResponse,
) -> None:
    """AgentResponse.value must be parsed when response_format is set in default_options and streaming."""
    from pydantic import BaseModel

    class Greeting(BaseModel):
        greeting: str

    json_text = '{"greeting": "Hello"}'
    client.streaming_responses.append(  # type: ignore[attr-defined]
        [
            ChatResponseUpdate(
                contents=[Content.from_text(json_text)],
                role="assistant",
                finish_reason="stop",
            )
        ]
    )

    agent = Agent(client=client, default_options={"response_format": Greeting})
    stream = agent.run("Hello", stream=True)
    async for _ in stream:
        pass
    result = await stream.get_final_response()

    assert result.text == json_text
    assert result.value is not None
    assert isinstance(result.value, Greeting)
    assert result.value.greeting == "Hello"


async def test_chat_client_agent_streaming_response_format_from_run_options(
    client: SupportsChatGetResponse,
) -> None:
    """AgentResponse.value must be parsed when response_format is passed via run() options kwarg."""
    from pydantic import BaseModel

    class Greeting(BaseModel):
        greeting: str

    json_text = '{"greeting": "Hi"}'
    client.streaming_responses.append(  # type: ignore[attr-defined]
        [
            ChatResponseUpdate(
                contents=[Content.from_text(json_text)],
                role="assistant",
                finish_reason="stop",
            )
        ]
    )

    agent = Agent(client=client)
    stream = agent.run("Hello", stream=True, options={"response_format": Greeting})
    async for _ in stream:
        pass
    result = await stream.get_final_response()

    assert result.text == json_text
    assert result.value is not None
    assert isinstance(result.value, Greeting)
    assert result.value.greeting == "Hi"


async def test_chat_client_agent_response_format_dict_from_default_options(
    client: SupportsChatGetResponse,
) -> None:
    """AgentResponse.value should parse JSON dicts from default_options response_format."""
    json_text = json.dumps({"greeting": "Hello"})
    client.responses.append(ChatResponse(messages=Message(role="assistant", contents=[json_text])))  # type: ignore[attr-defined]

    agent = Agent(
        client=client,
        default_options={"response_format": {"type": "object", "properties": {"greeting": {"type": "string"}}}},
    )
    result = await agent.run("Hello")

    assert result.text == json_text
    assert result.value is not None
    assert isinstance(result.value, dict)
    assert result.value["greeting"] == "Hello"


async def test_chat_client_agent_streaming_response_format_dict_from_run_options(
    client: SupportsChatGetResponse,
) -> None:
    """Agent streaming should preserve mapping response_format and parse the final value as a dict."""
    json_text = json.dumps({"greeting": "Hi"})
    client.streaming_responses.append(  # type: ignore[attr-defined]
        [
            ChatResponseUpdate(
                contents=[Content.from_text(json_text)],
                role="assistant",
                finish_reason="stop",
            )
        ]
    )

    agent = Agent(client=client)
    stream = agent.run(
        "Hello",
        stream=True,
        options={"response_format": {"type": "object", "properties": {"greeting": {"type": "string"}}}},
    )
    async for _ in stream:
        pass
    result = await stream.get_final_response()

    assert result.text == json_text
    assert result.value is not None
    assert isinstance(result.value, dict)
    assert result.value["greeting"] == "Hi"


async def test_chat_client_agent_create_session(
    client: SupportsChatGetResponse,
) -> None:
    agent = Agent(client=client)
    session = agent.create_session()

    assert isinstance(session, AgentSession)


async def test_chat_client_agent_prepare_session_and_messages(
    client: SupportsChatGetResponse,
) -> None:
    from agent_framework._sessions import InMemoryHistoryProvider

    agent = Agent(client=client, context_providers=[InMemoryHistoryProvider()])
    message = Message(role="user", contents=["Hello"])
    session = AgentSession()
    session.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID] = {"messages": [message]}

    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Test"])],
    )
    result_messages = session_context.get_messages(include_input=True)

    assert len(result_messages) == 2
    assert result_messages[0].text == "Hello"
    assert result_messages[1].text == "Test"


async def test_prepare_session_does_not_mutate_agent_chat_options(
    client: SupportsChatGetResponse,
) -> None:
    tool = {"type": "code_interpreter"}
    agent = Agent(client=client, tools=[tool])

    assert agent.default_options.get("tools") is not None
    base_tools = agent.default_options["tools"]
    session = agent.create_session()

    _, prepared_chat_options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Test"])],
    )

    assert prepared_chat_options.get("tools") is not None
    assert base_tools is not prepared_chat_options["tools"]

    prepared_chat_options["tools"].append({"type": "code_interpreter"})  # type: ignore[arg-type]
    assert len(agent.default_options["tools"]) == 1


async def test_prepare_run_context_handles_function_kwargs(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    agent = Agent(client=chat_client_base)
    session = agent.create_session()

    ctx = await agent._prepare_run_context(  # type: ignore[reportPrivateUsage]
        messages="Hello",
        session=session,
        tools=None,
        options={
            "temperature": 0.4,
            "additional_function_arguments": {"from_options": "options-value"},
        },
        compaction_strategy=None,
        tokenizer=None,
        function_invocation_kwargs={"runtime_key": "runtime-value"},
        client_kwargs={"client_key": "client-value"},
    )

    assert ctx["chat_options"]["temperature"] == 0.4
    assert "additional_function_arguments" not in ctx["chat_options"]
    assert ctx["function_invocation_kwargs"]["from_options"] == "options-value"
    assert ctx["function_invocation_kwargs"]["runtime_key"] == "runtime-value"
    assert "session" not in ctx["function_invocation_kwargs"]
    assert ctx["client_kwargs"]["client_key"] == "client-value"
    assert ctx["client_kwargs"]["session"] is session


async def test_chat_agent_persists_history_per_service_call(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    provider = _RecordingHistoryProvider()

    @tool(name="lookup_weather", approval_mode="never_require")
    def lookup_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    session = AgentSession()
    session.state[provider.source_id] = {
        "messages": [
            Message(role="user", contents=["Earlier question"]),
            Message(role="assistant", contents=["Earlier answer"]),
        ]
    }
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_1",
                        name="lookup_weather",
                        arguments='{"location": "Seattle"}',
                    )
                ],
            ),
            response_id="resp_call_1",
        ),
        ChatResponse(
            messages=Message(role="assistant", contents=["It is sunny in Seattle."]), response_id="resp_call_2"
        ),
    ]

    agent = Agent(
        client=chat_client_base,
        tools=[lookup_weather],
        context_providers=[provider],
        require_per_service_call_history_persistence=True,
    )

    result = await agent.run("What's the weather in Seattle?", session=session)

    provider_state = session.state[provider.source_id]
    stored_messages = cast(list[Message], provider_state["messages"])

    assert result.text == "It is sunny in Seattle."
    assert result.response_id is None
    assert chat_client_base.call_count == 2
    assert provider_state["get_call_count"] == 2
    assert provider_state["save_call_count"] == 2
    assert stored_messages[-1].text == "It is sunny in Seattle."
    assert session.service_session_id is None


async def test_chat_agent_persists_history_per_service_call_streaming(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    provider = _RecordingHistoryProvider()

    @tool(name="lookup_weather", approval_mode="never_require")
    def lookup_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    session = AgentSession()
    session.state[provider.source_id] = {
        "messages": [
            Message(role="user", contents=["Earlier question"]),
            Message(role="assistant", contents=["Earlier answer"]),
        ]
    }
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[
                    Content.from_function_call(
                        call_id="call_1",
                        name="lookup_weather",
                        arguments='{"location": "Seattle"}',
                    )
                ],
                role="assistant",
                finish_reason="stop",
                response_id="resp_call_1",
            )
        ],
        [
            ChatResponseUpdate(
                contents=[Content.from_text("It is sunny in Seattle.")],
                role="assistant",
                finish_reason="stop",
                response_id="resp_call_2",
            )
        ],
    ]

    agent = Agent(
        client=chat_client_base,
        tools=[lookup_weather],
        context_providers=[provider],
        require_per_service_call_history_persistence=True,
    )

    stream = agent.run("What's the weather in Seattle?", session=session, stream=True)
    async for _ in stream:
        pass
    result = await stream.get_final_response()

    provider_state = session.state[provider.source_id]
    stored_messages = cast(list[Message], provider_state["messages"])

    assert result.text == "It is sunny in Seattle."
    assert result.response_id is None
    assert chat_client_base.call_count == 2
    assert provider_state["get_call_count"] == 2
    assert provider_state["save_call_count"] == 2
    assert stored_messages[-1].text == "It is sunny in Seattle."
    assert session.service_session_id is None


async def test_streaming_per_service_call_persistence_hides_response_id_from_after_run(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    provider = _ResponseIdRecordingHistoryProvider()

    @tool(name="lookup_weather", approval_mode="never_require")
    def lookup_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    session = AgentSession()
    session.state[provider.source_id] = {"messages": []}
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[
                    Content.from_function_call(
                        call_id="call_1",
                        name="lookup_weather",
                        arguments='{"location": "Seattle"}',
                    )
                ],
                role="assistant",
                finish_reason="stop",
                response_id="resp_call_1",
            )
        ],
        [
            ChatResponseUpdate(
                contents=[Content.from_text("It is sunny in Seattle.")],
                role="assistant",
                finish_reason="stop",
                response_id="resp_call_2",
            )
        ],
    ]

    agent = Agent(
        client=chat_client_base,
        tools=[lookup_weather],
        context_providers=[provider],
        require_per_service_call_history_persistence=True,
    )

    stream = agent.run("What's the weather in Seattle?", session=session, stream=True)
    async for _ in stream:
        pass
    result = await stream.get_final_response()

    provider_state = session.state[provider.source_id]

    assert result.response_id is None
    assert provider_state["response_ids"] == [None, None]


async def test_per_service_call_persistence_uses_real_service_storage_when_client_stores_by_default(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    provider = _RecordingHistoryProvider()

    @tool(name="lookup_weather", approval_mode="never_require")
    def lookup_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    chat_client_base.STORES_BY_DEFAULT = True  # type: ignore[attr-defined]

    session = AgentSession()
    session.state[provider.source_id] = {"messages": []}
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_1",
                        name="lookup_weather",
                        arguments='{"location": "Seattle"}',
                    )
                ],
            ),
            conversation_id="resp_service_managed",
            response_id="resp_call_1",
        ),
        ChatResponse(
            messages=Message(role="assistant", contents=["It is sunny in Seattle."]),
            conversation_id="resp_service_managed",
            response_id="resp_call_2",
        ),
    ]

    agent = Agent(
        client=chat_client_base,
        tools=[lookup_weather],
        context_providers=[provider],
        require_per_service_call_history_persistence=True,
    )

    result = await agent.run("What's the weather in Seattle?", session=session)

    provider_state = session.state[provider.source_id]

    assert result.text == "It is sunny in Seattle."
    assert result.response_id == "resp_call_2"
    assert chat_client_base.call_count == 2
    assert "get_call_count" not in provider_state
    assert "save_call_count" not in provider_state
    assert session.service_session_id == "resp_service_managed"


async def test_service_storage_updates_session_handle_per_service_call_before_non_streaming_failure(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    provider = _RecordingHistoryProvider()

    @tool(name="lookup_weather", approval_mode="never_require")
    def lookup_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    chat_client_base.STORES_BY_DEFAULT = True  # type: ignore[attr-defined]

    session = AgentSession()
    session.state[provider.source_id] = {"messages": []}
    first_response = ChatResponse(
        messages=Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id="call_1",
                    name="lookup_weather",
                    arguments='{"location": "Seattle"}',
                )
            ],
        ),
        conversation_id="resp_call_1",
        response_id="resp_call_1",
    )
    mock_get_non_streaming_response = AsyncMock(
        side_effect=[first_response, RuntimeError("service down")],
    )

    agent = Agent(
        client=chat_client_base,
        tools=[lookup_weather],
        context_providers=[provider],
        require_per_service_call_history_persistence=True,
    )

    with (
        patch.object(chat_client_base, "_get_non_streaming_response", new=mock_get_non_streaming_response),
        pytest.raises(RuntimeError, match="service down"),
    ):
        await agent.run("What's the weather in Seattle?", session=session)

    assert mock_get_non_streaming_response.await_count == 2
    assert session.service_session_id == "resp_call_1"


async def test_service_storage_updates_session_handle_per_service_call_before_streaming_failure(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    provider = _RecordingHistoryProvider()

    @tool(name="lookup_weather", approval_mode="never_require")
    def lookup_weather(location: str) -> str:
        return f"Weather in {location}: sunny"

    chat_client_base.STORES_BY_DEFAULT = True  # type: ignore[attr-defined]

    session = AgentSession()
    session.state[provider.source_id] = {"messages": []}

    async def _first_stream_updates() -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(
            contents=[
                Content.from_function_call(
                    call_id="call_1",
                    name="lookup_weather",
                    arguments='{"location": "Seattle"}',
                )
            ],
            role="assistant",
            finish_reason="stop",
        )

    def _finalize_first_stream(_updates: Sequence[ChatResponseUpdate]) -> ChatResponse[Any]:
        return ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_1",
                        name="lookup_weather",
                        arguments='{"location": "Seattle"}',
                    )
                ],
            ),
            conversation_id="resp_call_1",
            response_id="resp_call_1",
        )

    first_stream = ResponseStream(_first_stream_updates(), finalizer=_finalize_first_stream)
    mock_get_streaming_response = MagicMock(side_effect=[first_stream, RuntimeError("service down")])

    agent = Agent(
        client=chat_client_base,
        tools=[lookup_weather],
        context_providers=[provider],
        require_per_service_call_history_persistence=True,
    )

    with (
        patch.object(chat_client_base, "_get_streaming_response", new=mock_get_streaming_response),
        pytest.raises(RuntimeError, match="service down"),
    ):
        stream = agent.run("What's the weather in Seattle?", session=session, stream=True)
        async for _ in stream:
            pass

    assert mock_get_streaming_response.call_count == 2
    assert session.service_session_id == "resp_call_1"


async def test_chat_agent_without_per_service_call_persistence_preserves_response_id(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(role="assistant", contents=["Hello"]),
            response_id="resp_call_1",
        )
    ]

    agent = Agent(
        client=chat_client_base,
        context_providers=[InMemoryHistoryProvider()],
    )

    result = await agent.run("Hello", session=AgentSession(), options={"store": False})

    assert result.response_id == "resp_call_1"


async def test_per_service_call_persistence_rejects_real_service_conversation_id(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    provider = _RecordingHistoryProvider()
    chat_client_base.STORES_BY_DEFAULT = True  # type: ignore[attr-defined]
    session = AgentSession()
    session.state[provider.source_id] = {"messages": []}
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(role="assistant", contents=["Hello"]),
            conversation_id="resp_service_managed",
        )
    ]

    agent = Agent(
        client=chat_client_base,
        context_providers=[provider],
        require_per_service_call_history_persistence=True,
    )

    with pytest.raises(
        ChatClientInvalidResponseException,
        match="require_per_service_call_history_persistence cannot be used",
    ):
        await agent.run("Hello", session=session, options={"store": False})


async def test_per_service_call_persistence_rejects_existing_conversation_id_when_service_not_storing_history(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    provider = _RecordingHistoryProvider()
    session = AgentSession()
    session.state[provider.source_id] = {"messages": []}

    agent = Agent(
        client=chat_client_base,
        context_providers=[provider],
        require_per_service_call_history_persistence=True,
    )

    with pytest.raises(
        AgentInvalidRequestException,
        match="require_per_service_call_history_persistence cannot be used",
    ):
        await agent.run("Hello", session=session, options={"store": False, "conversation_id": "existing_conversation"})


async def test_chat_client_agent_run_with_session(chat_client_base: SupportsChatGetResponse) -> None:
    mock_response = ChatResponse(
        messages=[Message(role="assistant", contents=[Content.from_text("test response")])],
        conversation_id="123",
    )
    chat_client_base.run_responses = [mock_response]
    agent = Agent(
        client=chat_client_base,
        tools={"type": "code_interpreter"},
    )
    session = agent.get_session(service_session_id="123")

    result = await agent.run("Hello", session=session)
    assert result.text == "test response"

    assert session.service_session_id == "123"


async def test_chat_client_agent_updates_existing_session_id_non_streaming(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[Message(role="assistant", contents=[Content.from_text("test response")])],
            conversation_id="resp_new_123",
        )
    ]

    agent = Agent(client=chat_client_base)
    session = agent.get_session(service_session_id="resp_old_123")

    await agent.run("Hello", session=session)
    assert session.service_session_id == "resp_new_123"


async def test_chat_client_agent_update_session_id_streaming_uses_conversation_id(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_text("stream part 1")],
                role="assistant",
                response_id="resp_stream_123",
                conversation_id="conv_stream_456",
            ),
            ChatResponseUpdate(
                contents=[Content.from_text(" stream part 2")],
                role="assistant",
                response_id="resp_stream_123",
                conversation_id="conv_stream_456",
                finish_reason="stop",
            ),
        ]
    ]

    agent = Agent(client=chat_client_base)
    session = agent.create_session()

    stream = agent.run("Hello", session=session, stream=True)
    async for _ in stream:
        pass
    result = await stream.get_final_response()
    assert result.text == "stream part 1 stream part 2"
    assert session.service_session_id == "conv_stream_456"


async def test_chat_client_agent_updates_existing_session_id_streaming(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_text("stream part 1")],
                role="assistant",
                response_id="resp_stream_123",
                conversation_id="resp_new_456",
            ),
            ChatResponseUpdate(
                contents=[Content.from_text(" stream part 2")],
                role="assistant",
                response_id="resp_stream_123",
                conversation_id="resp_new_456",
                finish_reason="stop",
            ),
        ]
    ]

    agent = Agent(client=chat_client_base)
    session = agent.get_session(service_session_id="resp_old_456")

    stream = agent.run("Hello", session=session, stream=True)
    async for _ in stream:
        pass
    await stream.get_final_response()
    assert session.service_session_id == "resp_new_456"


async def test_chat_client_agent_update_session_id_streaming_does_not_use_response_id(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_text("stream response without conversation id")],
                role="assistant",
                response_id="resp_only_123",
                finish_reason="stop",
            ),
        ]
    ]

    agent = Agent(client=chat_client_base)
    session = agent.create_session()

    stream = agent.run("Hello", session=session, stream=True)
    async for _ in stream:
        pass
    result = await stream.get_final_response()
    assert result.text == "stream response without conversation id"
    assert session.service_session_id is None


async def test_chat_client_agent_streaming_session_id_set_without_get_final_response(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Test that session.service_session_id is set during streaming iteration.

    This verifies the eager propagation of conversation_id via transform hook,
    which is needed for multi-turn flows (e.g. hosted MCP approval) where the
    user iterates the stream and then makes a follow-up call without calling
    get_final_response().
    """
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_text("part 1")],
                role="assistant",
                response_id="resp_123",
                conversation_id="resp_123",
            ),
            ChatResponseUpdate(
                contents=[Content.from_text(" part 2")],
                role="assistant",
                response_id="resp_123",
                conversation_id="resp_123",
                finish_reason="stop",
            ),
        ]
    ]

    agent = Agent(client=chat_client_base)
    session = agent.create_session()
    assert session.service_session_id is None

    # Only iterate — do NOT call get_final_response()
    async for _ in agent.run("Hello", session=session, stream=True):
        pass

    assert session.service_session_id == "resp_123"


async def test_chat_client_agent_streaming_session_history_saved_without_get_final_response(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Test that session history is saved after streaming iteration without get_final_response().

    Auto-finalization on iteration completion should trigger after_run providers,
    persisting conversation history to the session.
    """
    from agent_framework._sessions import InMemoryHistoryProvider

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_text("Hello Alice!")],
                role="assistant",
                response_id="resp_1",
                finish_reason="stop",
            ),
        ]
    ]

    agent = Agent(client=chat_client_base)
    session = agent.create_session()

    # Only iterate — do NOT call get_final_response()
    async for _ in agent.run("My name is Alice", session=session, stream=True):
        pass

    chat_messages: list[Message] = session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {}).get("messages", [])
    assert len(chat_messages) == 2
    assert chat_messages[0].text == "My name is Alice"
    assert chat_messages[1].text == "Hello Alice!"


async def test_chat_client_agent_update_session_messages(
    client: SupportsChatGetResponse,
) -> None:
    from agent_framework._sessions import InMemoryHistoryProvider

    agent = Agent(client=client)
    session = agent.create_session()

    result = await agent.run("Hello", session=session)
    assert result.text == "test response"

    assert session.service_session_id is None

    chat_messages: list[Message] = session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {}).get("messages", [])

    assert chat_messages is not None
    assert len(chat_messages) == 2
    assert chat_messages[0].text == "Hello"
    assert chat_messages[1].text == "test response"


async def test_chat_client_agent_update_session_conversation_id_missing(
    client: SupportsChatGetResponse,
) -> None:
    agent = Agent(client=client)
    session = agent.get_session(service_session_id="123")

    # With the session-based API, service_session_id is managed directly on the session
    assert session.service_session_id == "123"


async def test_chat_client_agent_default_author_name(
    client: SupportsChatGetResponse,
) -> None:
    # Name is not specified here, so default name should be used
    agent = Agent(client=client)

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "UnnamedAgent"


async def test_chat_client_agent_author_name_as_agent_name(
    client: SupportsChatGetResponse,
) -> None:
    # Name is specified here, so it should be used as author name
    agent = Agent(client=client, name="TestAgent")

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAgent"


async def test_chat_client_agent_author_name_is_used_from_response(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[Content.from_text("test response")],
                    author_name="TestAuthor",
                )
            ]
        )
    ]

    agent = Agent(client=chat_client_base, tools={"type": "code_interpreter"})

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAuthor"


# Mock context provider for testing
class MockContextProvider(ContextProvider):
    def __init__(self, messages: list[Message] | None = None) -> None:
        super().__init__(source_id="mock")
        self.context_messages = messages
        self.before_run_called = False
        self.after_run_called = False
        self.new_messages: list[Message] = []
        self.last_service_session_id: str | None = None

    async def before_run(self, *, agent: Any, session: Any, context: Any, state: Any) -> None:
        self.before_run_called = True
        if self.context_messages:
            context.extend_messages(self, self.context_messages)

    async def after_run(self, *, agent: Any, session: Any, context: Any, state: Any) -> None:
        self.after_run_called = True
        if session:
            self.last_service_session_id = session.service_session_id
        if context.response:
            self.new_messages.extend(context.input_messages)
            self.new_messages.extend(context.response.messages)


async def test_chat_agent_context_providers_model_before_run(
    client: SupportsChatGetResponse,
) -> None:
    """Test that context providers' before_run is called during agent run."""
    mock_provider = MockContextProvider(messages=[Message(role="system", contents=["Test context instructions"])])
    agent = Agent(client=client, context_providers=[mock_provider])

    await agent.run("Hello")

    assert mock_provider.before_run_called


async def test_chat_agent_context_providers_after_run(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Test that context providers' after_run is called during agent run."""
    mock_provider = MockContextProvider()
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[Message(role="assistant", contents=[Content.from_text("test response")])],
            conversation_id="test-thread-id",
        )
    ]

    agent = Agent(client=chat_client_base, context_providers=[mock_provider])

    session = agent.get_session(service_session_id="test-thread-id")
    await agent.run("Hello", session=session)

    assert mock_provider.after_run_called
    assert mock_provider.last_service_session_id == "test-thread-id"


async def test_chat_agent_context_providers_messages_adding(
    client: SupportsChatGetResponse,
) -> None:
    """Test that context providers' after_run is called during agent run."""
    mock_provider = MockContextProvider()
    agent = Agent(client=client, context_providers=[mock_provider])

    await agent.run("Hello")

    assert mock_provider.after_run_called
    # Should be called with both input and response messages
    assert len(mock_provider.new_messages) >= 2


async def test_chat_agent_context_instructions_in_messages(
    client: SupportsChatGetResponse,
) -> None:
    """Test that AI context instructions are included in messages."""
    mock_provider = MockContextProvider(messages=[Message(role="system", contents=["Context-specific instructions"])])
    agent = Agent(
        client=client,
        instructions="Agent instructions",
        context_providers=[mock_provider],
    )

    # We need to test the _prepare_session_and_messages method directly
    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=None, input_messages=[Message(role="user", contents=["Hello"])]
    )
    messages = session_context.get_messages(include_input=True)

    # Should have context instructions, and user message
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].text == "Context-specific instructions"
    assert messages[1].role == "user"
    assert messages[1].text == "Hello"
    # instructions system message is added by a client


async def test_chat_agent_no_context_instructions(
    client: SupportsChatGetResponse,
) -> None:
    """Test behavior when AI context has no instructions."""
    mock_provider = MockContextProvider()
    agent = Agent(
        client=client,
        instructions="Agent instructions",
        context_providers=[mock_provider],
    )

    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=None, input_messages=[Message(role="user", contents=["Hello"])]
    )
    messages = session_context.get_messages(include_input=True)

    # Should have agent instructions and user message only
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].text == "Hello"


async def test_chat_agent_run_stream_context_providers(
    client: SupportsChatGetResponse,
) -> None:
    """Test that context providers work with run method."""
    mock_provider = MockContextProvider(messages=[Message(role="system", contents=["Stream context instructions"])])
    agent = Agent(client=client, context_providers=[mock_provider])

    # Collect all stream updates and get final response
    stream = agent.run("Hello", stream=True)
    updates: list[AgentResponseUpdate] = []
    async for update in stream:
        updates.append(update)
    # Get final response to trigger post-processing hooks (including context provider notification)
    await stream.get_final_response()

    # Verify context provider was called
    assert mock_provider.before_run_called
    assert mock_provider.after_run_called


async def test_chat_agent_context_providers_with_service_session_id(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Test context providers with service-managed session."""
    mock_provider = MockContextProvider()
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[Message(role="assistant", contents=[Content.from_text("test response")])],
            conversation_id="service-thread-123",
        )
    ]

    agent = Agent(client=chat_client_base, context_providers=[mock_provider])

    # Use existing service-managed session
    session = agent.get_session(service_session_id="existing-thread-id")
    await agent.run("Hello", session=session)

    # after_run should be called
    assert mock_provider.after_run_called


# Tests for as_tool method
async def test_chat_agent_as_tool_basic(client: SupportsChatGetResponse) -> None:
    """Test basic as_tool functionality."""
    agent = Agent(client=client, name="TestAgent", description="Test agent for as_tool")

    tool = agent.as_tool()

    assert tool.name == "TestAgent"
    assert tool.description == "Test agent for as_tool"
    assert tool.approval_mode == "never_require"
    assert hasattr(tool, "func")
    assert tool.input_model is None


async def test_chat_agent_as_tool_custom_parameters(
    client: SupportsChatGetResponse,
) -> None:
    """Test as_tool with custom parameters."""
    agent = Agent(client=client, name="TestAgent", description="Original description")

    tool = agent.as_tool(
        name="CustomTool",
        description="Custom description",
        arg_name="query",
        arg_description="Custom input description",
        approval_mode="always_require",
    )

    assert tool.name == "CustomTool"
    assert tool.description == "Custom description"
    assert tool.approval_mode == "always_require"

    # Check that the input model has the custom field name
    schema = tool.parameters()
    assert "query" in schema["properties"]
    assert schema["properties"]["query"]["description"] == "Custom input description"


async def test_chat_agent_as_tool_defaults(client: SupportsChatGetResponse) -> None:
    """Test as_tool with default parameters."""
    agent = Agent(
        client=client,
        name="TestAgent",
        # No description provided
    )

    tool = agent.as_tool()

    assert tool.name == "TestAgent"
    assert tool.description == ""  # Should default to empty string

    # Check default input field
    schema = tool.parameters()
    assert "task" in schema["properties"]
    assert "Task for TestAgent" in schema["properties"]["task"]["description"]


async def test_chat_agent_as_tool_no_name(client: SupportsChatGetResponse) -> None:
    """Test as_tool when agent has no name (should raise ValueError)."""
    agent = Agent(client=client)  # No name provided

    # Should raise ValueError since agent has no name
    with raises(ValueError, match="Agent tool name cannot be None"):
        agent.as_tool()


async def test_chat_agent_as_tool_function_execution(
    client: SupportsChatGetResponse,
) -> None:
    """Test that the generated FunctionTool can be executed."""
    agent = Agent(client=client, name="TestAgent", description="Test agent")

    tool = agent.as_tool()

    # Test function execution
    result = await tool.invoke(arguments={"task": "Hello"})

    # Should return the agent's response text as a list of Content items
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].text == "test streaming response another update"  # From mock streaming client


async def test_chat_agent_as_tool_with_stream_callback(
    client: SupportsChatGetResponse,
) -> None:
    """Test as_tool with stream callback functionality."""
    agent = Agent(client=client, name="StreamingAgent")

    # Collect streaming updates
    collected_updates: list[AgentResponseUpdate] = []

    def stream_callback(update: AgentResponseUpdate) -> None:
        collected_updates.append(update)

    tool = agent.as_tool(stream_callback=stream_callback)

    # Execute the tool
    result = await tool.invoke(arguments={"task": "Hello"})

    # Should have collected streaming updates
    assert len(collected_updates) > 0
    assert isinstance(result, list)
    result_text = result[0].text
    # Result should be concatenation of all streaming updates
    expected_text = "".join(update.text for update in collected_updates)
    assert result_text == expected_text


async def test_chat_agent_as_tool_with_custom_arg_name(
    client: SupportsChatGetResponse,
) -> None:
    """Test as_tool with custom argument name."""
    agent = Agent(client=client, name="CustomArgAgent")

    tool = agent.as_tool(arg_name="prompt", arg_description="Custom prompt input")

    # Test that the custom argument name works
    result = await tool.invoke(arguments={"prompt": "Test prompt"})
    assert isinstance(result, list)
    assert result[0].text == "test streaming response another update"


async def test_chat_agent_as_tool_with_async_stream_callback(
    client: SupportsChatGetResponse,
) -> None:
    """Test as_tool with async stream callback functionality."""
    agent = Agent(client=client, name="AsyncStreamingAgent")

    # Collect streaming updates using an async callback
    collected_updates: list[AgentResponseUpdate] = []

    async def async_stream_callback(update: AgentResponseUpdate) -> None:
        collected_updates.append(update)

    tool = agent.as_tool(stream_callback=async_stream_callback)

    # Execute the tool
    result = await tool.invoke(arguments={"task": "Hello"})

    # Should have collected streaming updates
    assert len(collected_updates) > 0
    assert isinstance(result, list)
    result_text = result[0].text
    # Result should be concatenation of all streaming updates
    expected_text = "".join(update.text for update in collected_updates)
    assert result_text == expected_text


async def test_chat_agent_as_tool_name_sanitization(
    client: SupportsChatGetResponse,
) -> None:
    """Test as_tool name sanitization."""
    test_cases = [
        ("Invoice & Billing Agent", "Invoice_Billing_Agent"),
        ("Travel & Logistics Agent", "Travel_Logistics_Agent"),
        ("Agent@Company.com", "Agent_Company_com"),
        ("Agent___Multiple___Underscores", "Agent_Multiple_Underscores"),
        ("123Agent", "_123Agent"),  # Test digit prefix handling
        ("9to5Helper", "_9to5Helper"),  # Another digit prefix case
        ("@@@", "agent"),  # Test empty sanitization fallback
    ]

    for agent_name, expected_tool_name in test_cases:
        agent = Agent(client=client, name=agent_name, description="Test agent")
        tool = agent.as_tool()
        assert tool.name == expected_tool_name, f"Expected {expected_tool_name}, got {tool.name} for input {agent_name}"


async def test_chat_agent_as_tool_propagate_session_true(client: SupportsChatGetResponse) -> None:
    """Test that propagate_session=True forwards the session to the sub-agent."""
    agent = Agent(client=client, name="SubAgent", description="Sub agent")
    tool = agent.as_tool(propagate_session=True)

    parent_session = AgentSession(session_id="parent-session-123")
    parent_session.state["shared_key"] = "shared_value"

    original_run = agent.run
    captured_session = None

    def capturing_run(*args: Any, **kwargs: Any) -> Any:
        nonlocal captured_session
        captured_session = kwargs.get("session")
        return original_run(*args, **kwargs)

    agent.run = capturing_run  # type: ignore[assignment, method-assign]

    await tool.invoke(
        context=FunctionInvocationContext(
            function=tool,
            arguments={"task": "Hello"},
            session=parent_session,
        )
    )

    assert captured_session is parent_session
    assert captured_session.session_id == "parent-session-123"
    assert captured_session.state["shared_key"] == "shared_value"


async def test_chat_agent_as_tool_propagate_session_false_by_default(client: SupportsChatGetResponse) -> None:
    """Test that propagate_session defaults to False and does not forward the session."""
    agent = Agent(client=client, name="SubAgent", description="Sub agent")
    tool = agent.as_tool()  # default: propagate_session=False

    parent_session = AgentSession(session_id="parent-session-456")

    original_run = agent.run
    captured_session = None

    def capturing_run(*args: Any, **kwargs: Any) -> Any:
        nonlocal captured_session
        captured_session = kwargs.get("session")
        return original_run(*args, **kwargs)

    agent.run = capturing_run  # type: ignore[assignment, method-assign]

    await tool.invoke(
        context=FunctionInvocationContext(
            function=tool,
            arguments={"task": "Hello"},
            session=parent_session,
        )
    )

    assert captured_session is None


async def test_chat_agent_as_tool_propagate_session_shares_state(client: SupportsChatGetResponse) -> None:
    """Test that a propagated session allows the sub-agent to read and write parent state."""
    agent = Agent(client=client, name="SubAgent", description="Sub agent")
    tool = agent.as_tool(propagate_session=True)

    parent_session = AgentSession(session_id="shared-session")
    parent_session.state["counter"] = 0

    original_run = agent.run
    captured_session = None

    def capturing_run(*args: Any, **kwargs: Any) -> Any:
        nonlocal captured_session
        captured_session = kwargs.get("session")
        if captured_session:
            captured_session.state["counter"] += 1
        return original_run(*args, **kwargs)

    agent.run = capturing_run  # type: ignore[assignment, method-assign]

    await tool.invoke(
        context=FunctionInvocationContext(
            function=tool,
            arguments={"task": "Hello"},
            session=parent_session,
        )
    )

    assert parent_session.state["counter"] == 1


async def test_chat_agent_as_mcp_server_basic(client: SupportsChatGetResponse) -> None:
    """Test basic as_mcp_server functionality."""
    agent = Agent(client=client, name="TestAgent", description="Test agent for MCP")

    # Create MCP server with default parameters
    server = agent.as_mcp_server()

    # Verify server is created
    assert server is not None
    assert hasattr(server, "name")
    assert hasattr(server, "version")


async def test_chat_agent_run_with_mcp_tools(client: SupportsChatGetResponse) -> None:
    """Test run method with MCP tools to cover MCP tool handling code."""
    agent = Agent(client=client, name="TestAgent", description="Test agent")

    # Create a mock MCP tool
    mock_mcp_tool = MagicMock(spec=MCPTool)
    mock_mcp_tool.name = "mock-mcp"
    mock_mcp_tool.is_connected = False
    mock_mcp_tool.functions = [MagicMock()]

    # Mock the async context manager entry
    mock_mcp_tool.__aenter__ = AsyncMock(return_value=mock_mcp_tool)
    mock_mcp_tool.__aexit__ = AsyncMock(return_value=None)

    # Test run with MCP tools - this should hit the MCP tool handling code
    with contextlib.suppress(Exception):
        # We expect this to fail since we're using mocks, but we want to exercise the code path
        await agent.run(messages="Test message", tools=[mock_mcp_tool])


async def test_chat_agent_with_local_mcp_tools(client: SupportsChatGetResponse) -> None:
    """Test agent initialization with local MCP tools."""
    # Create a mock MCP tool
    mock_mcp_tool = MagicMock(spec=MCPTool)
    mock_mcp_tool.name = "mock-mcp"
    mock_mcp_tool.is_connected = False
    mock_mcp_tool.__aenter__ = AsyncMock(return_value=mock_mcp_tool)
    mock_mcp_tool.__aexit__ = AsyncMock(return_value=None)

    # Test agent with MCP tools in constructor
    with contextlib.suppress(Exception):
        agent = Agent(
            client=client,
            name="TestAgent",
            description="Test agent",
            tools=[mock_mcp_tool],
        )
        # Test async context manager with MCP tools
        async with agent:
            pass


async def test_mcp_tools_not_duplicated_when_passed_as_runtime_tools(
    chat_client_base: Any,
) -> None:
    """Test that MCP tool functions from self.mcp_tools are not duplicated when already present in runtime tools."""
    captured_options: list[dict[str, Any]] = []

    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(dict(options))
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create FunctionTool instances that simulate expanded MCP functions
    mcp_func_a = FunctionTool(func=lambda: "a", name="tool_a", description="Tool A")
    mcp_func_b = FunctionTool(func=lambda: "b", name="tool_b", description="Tool B")

    # Create a mock MCP tool that is already connected (simulates turn 2)
    mock_mcp_tool = MagicMock(spec=MCPTool)
    mock_mcp_tool.name = "mock-mcp"
    mock_mcp_tool.is_connected = True
    mock_mcp_tool.functions = [mcp_func_a, mcp_func_b]
    mock_mcp_tool.__aenter__ = AsyncMock(return_value=mock_mcp_tool)
    mock_mcp_tool.__aexit__ = AsyncMock(return_value=None)

    # Agent has the MCP tool in its constructor (stored in self.mcp_tools)
    agent = Agent(client=chat_client_base, name="TestAgent", tools=[mock_mcp_tool])

    # Simulate AG-UI turn 2: pass already-expanded MCP functions + a client tool as runtime tools
    client_tool = FunctionTool(func=lambda: "client", name="client_tool", description="Client tool")
    runtime_tools = [mcp_func_a, mcp_func_b, client_tool]

    await agent.run("hello", tools=runtime_tools)

    # Verify the chat client received each tool exactly once
    assert len(captured_options) >= 1
    tool_names = [t.name for t in captured_options[0]["tools"]]
    assert tool_names.count("tool_a") == 1, f"tool_a duplicated: {tool_names}"
    assert tool_names.count("tool_b") == 1, f"tool_b duplicated: {tool_names}"
    assert "client_tool" in tool_names
    assert len(tool_names) == 3


async def test_agent_run_raises_on_local_and_agent_mcp_name_conflict(chat_client_base: Any) -> None:
    local_tool = FunctionTool(
        func=lambda: "local",
        name="delete_all_data",
        description="Local protected tool",
        approval_mode="always_require",
    )
    agent = Agent(
        client=chat_client_base,
        name="TestAgent",
        tools=[_ConnectedMCPTool(name="dangerous-mcp", function_names=["delete_all_data"])],
    )

    with raises(ValueError, match="tool_name_prefix"):
        await agent.run("hello", tools=[local_tool])


async def test_agent_run_raises_on_runtime_local_and_runtime_mcp_name_conflict(chat_client_base: Any) -> None:
    local_tool = FunctionTool(
        func=lambda: "local",
        name="delete_all_data",
        description="Local protected tool",
        approval_mode="always_require",
    )
    runtime_mcp = _ConnectedMCPTool(name="dangerous-mcp", function_names=["delete_all_data"])
    agent = Agent(client=chat_client_base, name="TestAgent")

    with raises(ValueError, match="tool_name_prefix"):
        await agent.run("hello", tools=[local_tool, runtime_mcp])


async def test_agent_run_raises_on_duplicate_agent_mcp_names(chat_client_base: Any) -> None:
    agent = Agent(
        client=chat_client_base,
        name="TestAgent",
        tools=[
            _ConnectedMCPTool(name="docs-mcp", function_names=["search"]),
            _ConnectedMCPTool(name="github-mcp", function_names=["search"]),
        ],
    )

    with raises(ValueError, match="tool_name_prefix"):
        await agent.run("hello")


async def test_agent_run_accepts_prefixed_mcp_tools(chat_client_base: Any) -> None:
    captured_options: list[dict[str, Any]] = []

    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(dict(options))
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    local_tool = FunctionTool(func=lambda: "local", name="search", description="Local search tool")
    agent = Agent(
        client=chat_client_base,
        name="TestAgent",
        tools=[_ConnectedMCPTool(name="docs-mcp", function_names=["search"], tool_name_prefix="docs")],
    )

    await agent.run("hello", tools=[local_tool])

    tool_names = [tool.name for tool in captured_options[0]["tools"]]
    assert tool_names == ["search", "docs_search"]


async def test_agent_tool_without_context_does_not_receive_session(chat_client_base: Any) -> None:
    """Verify tools without FunctionInvocationContext no longer receive injected session kwargs."""

    captured: dict[str, Any] = {}

    @tool(name="echo_session_info", approval_mode="never_require")
    def echo_session_info(text: str, **kwargs: Any) -> str:  # type: ignore[reportUnknownParameterType]
        session = kwargs.get("session")
        captured["has_session"] = session is not None
        captured["has_state"] = session.state is not None if isinstance(session, AgentSession) else False
        return f"echo: {text}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="1",
                        name="echo_session_info",
                        arguments='{"text": "hello"}',
                    )
                ],
            )
        ),
        ChatResponse(messages=Message(role="assistant", contents=["done"])),
    ]

    agent = Agent(client=chat_client_base, tools=[echo_session_info])
    session = agent.create_session()

    result = await agent.run("hello", session=session)

    assert result.text == "done"
    assert captured.get("has_session") is False
    assert captured.get("has_state") is False


async def test_agent_tool_receives_explicit_session_via_function_invocation_context_kwargs(
    chat_client_base: Any,
) -> None:
    """Verify ctx-based tools receive the session via FunctionInvocationContext.session."""

    captured: dict[str, Any] = {}

    @tool(name="capture_session_context", approval_mode="never_require")
    def capture_session_context(text: str, ctx: FunctionInvocationContext) -> str:
        captured["session"] = ctx.session
        captured["has_state"] = ctx.session.state is not None if isinstance(ctx.session, AgentSession) else False
        return f"echo: {text}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="1",
                        name="capture_session_context",
                        arguments='{"text": "hello"}',
                    )
                ],
            )
        ),
        ChatResponse(messages=Message(role="assistant", contents=["done"])),
    ]

    agent = Agent(client=chat_client_base, tools=[capture_session_context])
    session = agent.create_session()

    result = await agent.run("hello", session=session)

    assert result.text == "done"
    assert captured["session"] is session
    assert captured["has_state"] is True


async def test_chat_agent_tool_choice_run_level_overrides_agent_level(chat_client_base: Any, tool_tool: Any) -> None:
    """Verify that tool_choice passed to run() overrides agent-level tool_choice."""

    captured_options: list[dict[str, Any]] = []

    # Store the original inner method
    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(options)
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create agent with agent-level tool_choice="auto" and a tool (tools required for tool_choice to be meaningful)
    agent = Agent(
        client=chat_client_base,
        tools=[tool_tool],
        default_options={"tool_choice": "auto"},
    )

    # Run with run-level tool_choice="required"
    await agent.run("Hello", options={"tool_choice": "required"})

    # Verify the client received tool_choice="required", not "auto"
    assert len(captured_options) >= 1
    assert captured_options[0]["tool_choice"] == "required"


async def test_chat_agent_tool_choice_agent_level_used_when_run_level_not_specified(
    chat_client_base: Any, tool_tool: Any
) -> None:
    """Verify that agent-level tool_choice is used when run() doesn't specify one."""
    captured_options: list[ChatOptions] = []

    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(options)
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create agent with agent-level tool_choice="required" and a tool
    agent = Agent(
        client=chat_client_base,
        tools=[tool_tool],
        default_options={"tool_choice": "required"},
    )

    # Run without specifying tool_choice
    await agent.run("Hello")

    # Verify the client received tool_choice="required" from agent-level
    assert len(captured_options) >= 1
    assert captured_options[0]["tool_choice"] == "required"
    # older code compared to ToolMode constants; ensure value is 'required'
    assert captured_options[0]["tool_choice"] == "required"


async def test_chat_agent_tool_choice_none_at_run_preserves_agent_level(chat_client_base: Any, tool_tool: Any) -> None:
    """Verify that tool_choice=None at run() uses agent-level default."""
    captured_options: list[ChatOptions] = []

    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(options)
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create agent with agent-level tool_choice="auto" and a tool
    agent = Agent(
        client=chat_client_base,
        tools=[tool_tool],
        default_options={"tool_choice": "auto"},
    )

    # Run with explicitly passing None (same as not specifying)
    await agent.run("Hello", options={"tool_choice": None})

    # Verify the client received tool_choice="auto" from agent-level
    assert len(captured_options) >= 1
    assert captured_options[0]["tool_choice"] == "auto"


async def test_chat_agent_compaction_overrides_client_defaults(chat_client_base: Any) -> None:
    captured_roles: list[list[str]] = []
    captured_token_counts: list[list[int | None]] = []
    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_roles.append([message.role for message in messages])
        captured_token_counts.append([
            group.get(GROUP_TOKEN_COUNT_KEY) if isinstance(group, dict) else None
            for group in (message.additional_properties.get(GROUP_ANNOTATION_KEY) for message in messages)
        ])
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner
    chat_client_base.function_invocation_configuration["enabled"] = False
    chat_client_base.compaction_strategy = TruncationStrategy(max_n=1, compact_to=1)
    chat_client_base.tokenizer = _FixedTokenizer(5)

    agent = Agent(
        client=chat_client_base,
        compaction_strategy=SlidingWindowStrategy(keep_last_groups=2),
        tokenizer=_FixedTokenizer(9),
    )

    await agent.run([
        Message(role="user", contents=["Hello"]),
        Message(role="assistant", contents=["Previous response"]),
    ])

    assert captured_roles == [["user", "assistant"]]
    assert captured_token_counts == [[9, 9]]


async def test_chat_agent_uses_client_compaction_defaults_when_agent_unset(chat_client_base: Any) -> None:
    captured_roles: list[list[str]] = []
    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_roles.append([message.role for message in messages])
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner
    chat_client_base.function_invocation_configuration["enabled"] = False
    chat_client_base.compaction_strategy = TruncationStrategy(max_n=1, compact_to=1)

    agent = Agent(client=chat_client_base)

    await agent.run([
        Message(role="user", contents=["Hello"]),
        Message(role="assistant", contents=["Previous response"]),
    ])

    assert captured_roles == [["assistant"]]


async def test_chat_agent_run_level_compaction_and_tokenizer_override_agent_defaults(chat_client_base: Any) -> None:
    captured_roles: list[list[str]] = []
    captured_token_counts: list[list[int | None]] = []
    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_roles.append([message.role for message in messages])
        captured_token_counts.append([
            group.get(GROUP_TOKEN_COUNT_KEY) if isinstance(group, dict) else None
            for group in (message.additional_properties.get(GROUP_ANNOTATION_KEY) for message in messages)
        ])
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner
    chat_client_base.function_invocation_configuration["enabled"] = False

    agent = Agent(
        client=chat_client_base,
        compaction_strategy=SlidingWindowStrategy(keep_last_groups=2),
        tokenizer=_FixedTokenizer(9),
    )

    await agent.run(
        [
            Message(role="user", contents=["Hello"]),
            Message(role="assistant", contents=["Previous response"]),
        ],
        compaction_strategy=TruncationStrategy(max_n=1, compact_to=1),
        tokenizer=_FixedTokenizer(23),
    )

    assert captured_roles == [["assistant"]]
    assert captured_token_counts == [[23]]


# region Test _merge_options


def test_merge_options_basic():
    """Test _merge_options merges two dicts with override precedence."""
    base = {"key1": "value1", "key2": "value2"}
    override = {"key2": "new_value2", "key3": "value3"}

    result = _merge_options(base, override)

    assert result["key1"] == "value1"
    assert result["key2"] == "new_value2"
    assert result["key3"] == "value3"


def test_merge_options_none_values_ignored():
    """Test _merge_options ignores None values in override."""
    base = {"key1": "value1"}
    override = {"key1": None, "key2": "value2"}

    result = _merge_options(base, override)

    assert result["key1"] == "value1"  # None didn't override
    assert result["key2"] == "value2"


def test_merge_options_runtime_model_overrides_default_model() -> None:
    """Test _merge_options lets a runtime model override a default model."""
    result = _merge_options({"model": "default-model"}, {"model": "runtime-model"})

    assert result["model"] == "runtime-model"


def test_merge_options_preserves_base_model_without_override() -> None:
    """Test _merge_options preserves the base model when there is no override."""
    result = _merge_options({"model": "preferred-model"}, {})

    assert result["model"] == "preferred-model"


def test_merge_options_tools_combined():
    """Test _merge_options raises when distinct tools share the same name."""

    class MockTool:
        def __init__(self, name):
            self.name = name

    tool1 = MockTool("tool1")
    tool2 = MockTool("tool2")
    tool3 = MockTool("tool1")  # Duplicate name

    base = {"tools": [tool1]}
    override = {"tools": [tool2, tool3]}

    with raises(ValueError, match="Duplicate tool name 'tool1'"):
        _merge_options(base, override)


def test_merge_options_dict_tools_combined():
    """Test _merge_options combines dict-defined tool lists without duplicates."""
    base = {
        "tools": [
            {"type": "function", "function": {"name": "tool_a"}},
        ]
    }
    override = {
        "tools": [
            {"type": "function", "function": {"name": "tool_b"}},
        ]
    }

    result = _merge_options(base, override)

    assert len(result["tools"]) == 2
    names = [_get_tool_name(t) for t in result["tools"]]
    assert "tool_a" in names
    assert "tool_b" in names


def test_merge_options_dict_tools_deduplicates():
    """Test _merge_options raises on duplicate dict-defined tool names."""
    base = {
        "tools": [
            {"type": "function", "function": {"name": "tool_a"}},
        ]
    }
    override = {
        "tools": [
            {"type": "function", "function": {"name": "tool_a"}},
            {"type": "function", "function": {"name": "tool_b"}},
        ]
    }

    with raises(ValueError, match="Duplicate tool name 'tool_a'"):
        _merge_options(base, override)


def test_merge_options_mixed_tools_combined():
    """Test _merge_options combines object and dict-defined tools."""

    class MockTool:
        def __init__(self, name):
            self.name = name

    base = {"tools": [MockTool("tool_a")]}
    override = {
        "tools": [
            {"type": "function", "function": {"name": "tool_b"}},
        ]
    }

    result = _merge_options(base, override)

    assert len(result["tools"]) == 2
    names = [_get_tool_name(t) for t in result["tools"]]
    assert "tool_a" in names
    assert "tool_b" in names


def test_merge_options_mixed_tools_deduplicates():
    """Test _merge_options raises when a dict tool and object tool share the same name."""

    class MockTool:
        def __init__(self, name):
            self.name = name

    base = {"tools": [MockTool("tool_a")]}
    override = {
        "tools": [
            {"type": "function", "function": {"name": "tool_a"}},
        ]
    }

    with raises(ValueError, match="Duplicate tool name 'tool_a'"):
        _merge_options(base, override)


def test_merge_options_nameless_tools_not_deduplicated():
    """Test that tools with no extractable name (None) are not falsely deduplicated."""
    base = {
        "tools": [
            {"type": "function"},  # no 'function.name' -> _get_tool_name returns None
        ]
    }
    override = {
        "tools": [
            {"type": "function"},  # also returns None
        ]
    }

    result = _merge_options(base, override)

    # Both nameless tools should be kept (None is excluded from dedup set)
    assert len(result["tools"]) == 2


def test_merge_options_same_tool_object_kept_once():
    """Test _merge_options silently keeps a repeated reference to the same tool object once."""

    class MockTool:
        def __init__(self, name):
            self.name = name

    tool_a = MockTool("tool_a")

    result = _merge_options({"tools": [tool_a]}, {"tools": [tool_a]})

    assert result["tools"] == [tool_a]


def test_get_tool_name_dict_no_function_key():
    """_get_tool_name returns None for a dict without a 'function' key."""
    assert _get_tool_name({"type": "function"}) is None


def test_get_tool_name_dict_function_not_dict():
    """_get_tool_name returns None when 'function' value is not a dict."""
    assert _get_tool_name({"function": "not_a_dict"}) is None


def test_get_tool_name_dict_function_no_name():
    """_get_tool_name returns None when 'function' dict has no 'name' key."""
    assert _get_tool_name({"function": {"description": "does stuff"}}) is None


def test_get_tool_name_object_no_name_attr():
    """_get_tool_name returns None for an object without a 'name' attribute."""
    assert _get_tool_name(object()) is None


def test_get_tool_name_non_dict_non_object():
    """_get_tool_name returns None for non-dict inputs like int or string."""
    assert _get_tool_name(42) is None
    assert _get_tool_name("tool_name") is None


def test_get_tool_name_valid_dict():
    """_get_tool_name extracts name from a well-formed dict tool."""
    tool_dict = {"type": "function", "function": {"name": "my_tool"}}
    assert _get_tool_name(tool_dict) == "my_tool"


def test_get_tool_name_valid_object():
    """_get_tool_name extracts name from an object with a name attribute."""

    class MockTool:
        def __init__(self, name):
            self.name = name

    assert _get_tool_name(MockTool("my_tool")) == "my_tool"


def test_merge_options_logit_bias_merged():
    """Test _merge_options merges logit_bias dicts."""
    base = {"logit_bias": {"token1": 1.0}}
    override = {"logit_bias": {"token2": 2.0}}

    result = _merge_options(base, override)

    assert result["logit_bias"]["token1"] == 1.0
    assert result["logit_bias"]["token2"] == 2.0


def test_merge_options_metadata_merged():
    """Test _merge_options merges metadata dicts."""
    base = {"metadata": {"key1": "value1"}}
    override = {"metadata": {"key2": "value2"}}

    result = _merge_options(base, override)

    assert result["metadata"]["key1"] == "value1"
    assert result["metadata"]["key2"] == "value2"


def test_merge_options_instructions_concatenated():
    """Test _merge_options concatenates instructions."""
    base = {"instructions": "First instruction."}
    override = {"instructions": "Second instruction."}

    result = _merge_options(base, override)

    assert "First instruction." in result["instructions"]
    assert "Second instruction." in result["instructions"]
    assert "\n" in result["instructions"]


# endregion


# region Test _sanitize_agent_name


def test_sanitize_agent_name_none():
    """Test _sanitize_agent_name returns None for None input."""
    assert _sanitize_agent_name(None) is None


def test_sanitize_agent_name_valid():
    """Test _sanitize_agent_name returns valid names unchanged."""
    assert _sanitize_agent_name("valid_name") == "valid_name"
    assert _sanitize_agent_name("ValidName123") == "ValidName123"


def test_sanitize_agent_name_replaces_invalid_chars():
    """Test _sanitize_agent_name replaces invalid characters."""
    result = _sanitize_agent_name("Agent Name!")
    # Should replace spaces and special chars with underscores
    assert " " not in result
    assert "!" not in result


# endregion


# region Test SupportsAgentRun.create_session


@pytest.mark.asyncio
async def test_agent_create_session(chat_client_base: SupportsChatGetResponse, tool_tool: FunctionTool):
    """Test that create_session returns a new AgentSession."""
    agent = Agent(client=chat_client_base, tools=[tool_tool])

    session = agent.create_session()

    assert session is not None
    assert isinstance(session, AgentSession)


@pytest.mark.asyncio
async def test_agent_create_session_with_context_providers(
    chat_client_base: SupportsChatGetResponse, tool_tool: FunctionTool
):
    """Test that create_session works when context_providers are set on the agent."""

    class TestContextProvider(ContextProvider):
        def __init__(self):
            super().__init__(source_id="test")

    provider = TestContextProvider()
    agent = Agent(client=chat_client_base, tools=[tool_tool], context_providers=[provider])

    session = agent.create_session()

    assert session is not None
    assert agent.context_providers[0] is provider


@pytest.mark.asyncio
async def test_agent_get_session_with_service_session_id(
    chat_client_base: SupportsChatGetResponse, tool_tool: FunctionTool
):
    """Test that get_session creates a session with service_session_id."""
    agent = Agent(client=chat_client_base, tools=[tool_tool])

    session = agent.get_session(service_session_id="test-thread-123")

    assert session is not None
    assert session.service_session_id == "test-thread-123"


def test_agent_session_from_dict(chat_client_base: SupportsChatGetResponse, tool_tool: FunctionTool):
    """Test AgentSession.from_dict restores a session from serialized state."""
    # Create serialized session state
    serialized_state = {
        "type": "session",
        "session_id": "test-session",
        "service_session_id": None,
        "state": {},
    }

    session = AgentSession.from_dict(serialized_state)

    assert session is not None
    assert isinstance(session, AgentSession)
    assert session.session_id == "test-session"


# endregion


# region Test Agent initialization edge cases


def test_chat_agent_calls_update_agent_name_on_client():
    """Test that Agent calls _update_agent_name_and_description on client if available."""
    mock_client = MagicMock()
    mock_client._update_agent_name_and_description = MagicMock()

    Agent(
        client=mock_client,
        name="TestAgent",
        description="Test description",
    )

    assert mock_client._update_agent_name_and_description.call_count == 1
    mock_client._update_agent_name_and_description.assert_called_with("TestAgent", "Test description")


@pytest.mark.asyncio
async def test_chat_agent_context_provider_adds_tools_when_agent_has_none(
    chat_client_base: SupportsChatGetResponse,
):
    """Test that context provider tools are used when agent has no default tools."""

    @tool
    def context_tool(text: str) -> str:
        """A tool provided by context."""
        return text

    class ToolContextProvider(ContextProvider):
        def __init__(self):
            super().__init__(source_id="tool-context")

        async def before_run(self, *, agent, session, context, state):
            context.extend_tools("tool-context", [context_tool])

    provider = ToolContextProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    # Agent starts with empty tools list
    assert agent.default_options.get("tools") == []

    # Run the agent and verify context tools are added
    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=None, input_messages=[Message(role="user", contents=["Hello"])]
    )

    # The context tools should now be in the options
    assert options.get("tools") is not None
    assert len(options["tools"]) == 1


@pytest.mark.asyncio
async def test_chat_agent_context_provider_adds_instructions_when_agent_has_none(
    chat_client_base: SupportsChatGetResponse,
):
    """Test that context provider instructions are used when agent has no default instructions."""

    class InstructionContextProvider(ContextProvider):
        def __init__(self):
            super().__init__(source_id="instruction-context")

        async def before_run(self, *, agent, session, context, state):
            context.extend_instructions("instruction-context", "Context-provided instructions")

    provider = InstructionContextProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    # Verify agent has no default instructions
    assert agent.default_options.get("instructions") is None

    # Run the agent and verify context instructions are available
    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=None, input_messages=[Message(role="user", contents=["Hello"])]
    )

    # The context instructions should now be in the options
    assert options.get("instructions") == "Context-provided instructions"


async def test_chat_agent_context_provider_adds_middleware_when_agent_has_none(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Test that context provider middleware is collected during preparation."""

    @chat_middleware
    async def context_chat_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        await call_next()

    class MiddlewareContextProvider(ContextProvider):
        def __init__(self) -> None:
            super().__init__(source_id="middleware-context")

        async def before_run(self, *, agent, session, context, state) -> None:
            context.extend_middleware("middleware-context", context_chat_middleware)

    agent = Agent(client=chat_client_base, context_providers=[MiddlewareContextProvider()])

    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=None,
        input_messages=[Message(role="user", contents=["Hello"])],
    )

    assert session_context.middleware["middleware-context"] == [context_chat_middleware]
    assert session_context.get_middleware() == [context_chat_middleware]


# region STORES_BY_DEFAULT tests


async def test_stores_by_default_skips_inmemory_injection(
    client: SupportsChatGetResponse,
) -> None:
    """Client with STORES_BY_DEFAULT=True should not auto-inject InMemoryHistoryProvider."""
    from agent_framework._sessions import InMemoryHistoryProvider

    # Simulate a client that stores by default
    client.STORES_BY_DEFAULT = True  # type: ignore[attr-defined]

    agent = Agent(client=client)
    session = agent.create_session()

    await agent.run("Hello", session=session)

    # No InMemoryHistoryProvider should have been injected
    assert not any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)


async def test_stores_by_default_false_injects_inmemory(
    client: SupportsChatGetResponse,
) -> None:
    """Client with STORES_BY_DEFAULT=False (default) should auto-inject InMemoryHistoryProvider."""
    from agent_framework._sessions import InMemoryHistoryProvider

    agent = Agent(client=client)
    session = agent.create_session()

    await agent.run("Hello", session=session)

    # InMemoryHistoryProvider should have been injected
    assert any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)


async def test_stores_by_default_with_store_false_injects_inmemory(
    client: SupportsChatGetResponse,
) -> None:
    """Client with STORES_BY_DEFAULT=True but store=False should still inject InMemoryHistoryProvider."""
    from agent_framework._sessions import InMemoryHistoryProvider

    client.STORES_BY_DEFAULT = True  # type: ignore[attr-defined]

    agent = Agent(client=client)
    session = agent.create_session()

    await agent.run("Hello", session=session, options={"store": False})

    # User explicitly disabled server storage, so InMemoryHistoryProvider should be injected
    assert any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)


async def test_store_true_skips_inmemory_injection(
    client: SupportsChatGetResponse,
) -> None:
    """Explicitly setting store=True should not auto-inject InMemoryHistoryProvider."""
    from agent_framework._sessions import InMemoryHistoryProvider

    agent = Agent(client=client)
    session = agent.create_session()

    await agent.run("Hello", session=session, options={"store": True})

    # User explicitly enabled server storage, so InMemoryHistoryProvider should not be injected
    assert not any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)


async def test_stores_by_default_with_store_false_in_default_options_injects_inmemory(
    client: SupportsChatGetResponse,
) -> None:
    """Client with STORES_BY_DEFAULT=True but store=False in default_options should inject InMemoryHistoryProvider.

    This covers the regression where store=False is set via Agent(..., default_options={"store": False})
    with no per-run override while the client has STORES_BY_DEFAULT=True.
    """
    from agent_framework._sessions import InMemoryHistoryProvider

    client.STORES_BY_DEFAULT = True  # type: ignore[attr-defined]

    # Set store=False at agent initialization via default_options, not at run-time
    agent = Agent(client=client, default_options={"store": False})
    session = agent.create_session()

    # Run without any per-run options override
    await agent.run("Hello", session=session)

    # User explicitly disabled server storage in default_options, so InMemoryHistoryProvider should be injected
    assert any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)


async def test_shared_local_storage_cross_provider_responses_history_does_not_leak_fc_id() -> None:
    """Responses-specific replay metadata should stay local to Responses when session storage is shared."""
    from openai.types.chat.chat_completion import ChatCompletion, Choice
    from openai.types.chat.chat_completion_message import ChatCompletionMessage

    from agent_framework._sessions import InMemoryHistoryProvider
    from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient

    @tool(approval_mode="never_require")
    def search_hotels(city: str) -> str:
        return f"Found 3 hotels in {city}"

    responses_client = OpenAIChatClient(model="test-model", api_key="test-key")
    responses_agent = Agent(
        client=responses_client,
        tools=[search_hotels],
        default_options={"store": False},
    )
    session = responses_agent.create_session()

    responses_tool_call = MagicMock()
    responses_tool_call.type = "function_call"
    responses_tool_call.id = "fc_provider123"
    responses_tool_call.call_id = "call_1"
    responses_tool_call.name = "search_hotels"
    responses_tool_call.arguments = '{"city": "Paris"}'
    responses_tool_call.status = "completed"

    responses_first = MagicMock()
    responses_first.output_parsed = None
    responses_first.metadata = {}
    responses_first.usage = None
    responses_first.id = "resp_1"
    responses_first.model = "test-model"
    responses_first.created_at = 1000000000
    responses_first.status = "completed"
    responses_first.finish_reason = "tool_calls"
    responses_first.incomplete = None
    responses_first.output = [responses_tool_call]

    responses_text_item = MagicMock()
    responses_text_item.type = "message"
    responses_text_content = MagicMock()
    responses_text_content.type = "output_text"
    responses_text_content.text = "Hotel Lutetia is the cheapest option."
    responses_text_item.content = [responses_text_content]

    responses_second = MagicMock()
    responses_second.output_parsed = None
    responses_second.metadata = {}
    responses_second.usage = None
    responses_second.id = "resp_2"
    responses_second.model = "test-model"
    responses_second.created_at = 1000000001
    responses_second.status = "completed"
    responses_second.finish_reason = "stop"
    responses_second.incomplete = None
    responses_second.output = [responses_text_item]

    with patch.object(
        responses_client.client.responses,
        "create",
        side_effect=[responses_first, responses_second],
    ) as mock_responses_create:
        responses_result = await responses_agent.run("Find me a hotel in Paris", session=session)

    assert responses_result.text == "Hotel Lutetia is the cheapest option."
    assert any(isinstance(provider, InMemoryHistoryProvider) for provider in responses_agent.context_providers)

    shared_messages = session.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID]["messages"]
    shared_function_call = next(
        content for message in shared_messages for content in message.contents if content.type == "function_call"
    )
    assert shared_function_call.additional_properties is not None
    assert shared_function_call.additional_properties.get("fc_id") == "fc_provider123"

    responses_replay_input = mock_responses_create.call_args_list[1].kwargs["input"]
    responses_replay_call = next(item for item in responses_replay_input if item.get("type") == "function_call")
    assert responses_replay_call["id"] == "fc_provider123"

    chat_client = OpenAIChatCompletionClient(model="test-model", api_key="test-key")
    chat_agent = Agent(client=chat_client)

    chat_response = ChatCompletion(
        id="chatcmpl-test",
        object="chat.completion",
        created=1234567890,
        model="gpt-4o-mini",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content="The cheapest option is still Hotel Lutetia."),
                finish_reason="stop",
            )
        ],
    )

    with patch.object(
        chat_client.client.chat.completions,
        "create",
        new=AsyncMock(return_value=chat_response),
    ) as mock_chat_create:
        chat_result = await chat_agent.run("Which option is cheapest?", session=session)

    assert chat_result.text == "The cheapest option is still Hotel Lutetia."

    chat_request_messages = mock_chat_create.call_args.kwargs["messages"]
    assistant_tool_call_message = next(
        message for message in chat_request_messages if message.get("role") == "assistant" and message.get("tool_calls")
    )
    assert assistant_tool_call_message["tool_calls"][0]["id"] == "call_1"
    assert assistant_tool_call_message["tool_calls"][0]["function"]["name"] == "search_hotels"

    tool_result_message = next(
        message
        for message in chat_request_messages
        if message.get("role") == "tool" and message.get("tool_call_id") == "call_1"
    )
    assert tool_result_message["content"] == "Found 3 hotels in Paris"
    assert "fc_provider123" not in json.dumps(chat_request_messages)


# region as_tool user_input_request propagation


async def test_as_tool_raises_on_user_input_request(client: SupportsChatGetResponse) -> None:
    """Test that as_tool raises when the wrapped sub-agent requests user input."""
    from agent_framework.exceptions import UserInputRequiredException

    consent_content = Content.from_oauth_consent_request(
        consent_link="https://login.microsoftonline.com/consent",
    )
    client.streaming_responses = [  # type: ignore[attr-defined]
        [ChatResponseUpdate(contents=[consent_content], role="assistant")],
    ]

    agent = Agent(client=client, name="OAuthAgent", description="Agent requiring consent")
    agent_tool = agent.as_tool()

    with raises(UserInputRequiredException) as exc_info:
        await agent_tool.invoke(arguments={"task": "Do something"})

    assert len(exc_info.value.contents) == 1
    assert exc_info.value.contents[0].type == "oauth_consent_request"
    assert exc_info.value.contents[0].consent_link == "https://login.microsoftonline.com/consent"
