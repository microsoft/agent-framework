# Copyright (c) Microsoft. All rights reserved.

"""Fixtures for Foundry Hosting tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from agent_framework import Agent, AgentSession, Content, Message

    from agent_framework_foundry_hosting import (
        InvocationsHostServer,
        InvocationsWorkflowHostServer,
        ResponsesHostServer,
        ResponsesWorkflowHostServer,
    )


@pytest.fixture
def approval_session() -> Callable[[Content], AgentSession]:
    from agent_framework import AgentSession
    from agent_framework._tools import _store_pending_approval_requests

    def create(request: Content) -> AgentSession:
        session = AgentSession()
        _store_pending_approval_requests(session, [request])
        return session

    return create


@pytest.fixture
def native_approval_agent(request: pytest.FixtureRequest) -> tuple[Agent, list[str], list[list[Message]]]:
    from agent_framework import (
        Agent,
        BaseChatClient,
        ChatOptions,
        ChatResponse,
        ChatResponseUpdate,
        Content,
        FunctionInvocationLayer,
        ResponseStream,
        tool,
    )

    executions: list[str] = []
    calls: list[list[Message]] = []
    paths: tuple[str, ...] = getattr(request, "param", ("/safe",))

    @tool(approval_mode="always_require")
    def delete_file(path: str) -> str:
        """Record a protected operation without accessing the filesystem."""
        executions.append(path)
        return "deleted"

    class ApprovalClient(FunctionInvocationLayer[ChatOptions], BaseChatClient[ChatOptions]):
        def _inner_get_response(
            self, *, messages: Sequence[Message], stream: bool, options: Mapping[str, Any], **kwargs: Any
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            calls.append(list(messages))
            contents = (
                [
                    Content.from_function_call(
                        f"provider-call-{index}" if index else "provider-call",
                        "delete_file",
                        arguments={"path": path},
                        id=f"native-call-{index}" if index else "native-call",
                    )
                    for index, path in enumerate(paths)
                ]
                if len(calls) == 1
                else [Content.from_text("done")]
            )

            async def updates() -> AsyncIterator[ChatResponseUpdate]:
                yield ChatResponseUpdate(role="assistant", contents=contents)

            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

    return Agent[ChatOptions](client=ApprovalClient(), tools=[delete_file]), executions, calls


@pytest.fixture(autouse=True)
def disable_agentserver_external_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep package regressions offline, including SDK resource detection and exporters."""
    monkeypatch.setattr("azure.ai.agentserver.core._tracing._configure_tracing", lambda **kwargs: None)


@pytest.fixture(autouse=True)
def isolate_local_agentserver_state_root(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test attempt an independent local AgentServer state root."""
    # pytest-retry bypasses the report hooks needed by tmp_path's teardown bookkeeping.
    with TemporaryDirectory(prefix="agentserver-test-") as directory:
        monkeypatch.setenv("AGENTSERVER_STATE_ROOT", str(Path(directory) / "agentserver-state"))
        yield


@pytest.fixture(
    params=[
        "ResponsesHostServer",
        "ResponsesWorkflowHostServer",
        "InvocationsHostServer",
        "InvocationsWorkflowHostServer",
    ]
)
def host_type(
    request: pytest.FixtureRequest,
) -> type[ResponsesHostServer | ResponsesWorkflowHostServer | InvocationsHostServer | InvocationsWorkflowHostServer]:
    import agent_framework_foundry_hosting

    return getattr(agent_framework_foundry_hosting, request.param)


@pytest.fixture
def host_constructor(
    host_type: type[
        ResponsesHostServer | ResponsesWorkflowHostServer | InvocationsHostServer | InvocationsWorkflowHostServer
    ],
) -> partial[Any]:
    settings: dict[str, Any]
    if "Workflow" in host_type.__name__:
        settings = {
            "workflow": lambda request: pytest.fail("Construction must not invoke the workflow factory."),
            "parse_input": lambda request: pytest.fail("Construction must not invoke the parser."),
        }
    else:
        settings = {"agent": lambda request: pytest.fail("Construction must not invoke the agent factory.")}
    return partial(host_type, **settings)
