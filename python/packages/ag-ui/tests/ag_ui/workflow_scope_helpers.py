# Copyright (c) Microsoft. All rights reserved.

"""Helpers for AG-UI tests of workflow-owned agent sessions and authorization scopes."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Literal

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentSession,
    ChatResponseUpdate,
    Content,
    InMemoryHistoryProvider,
    Message,
    ToolApprovalMiddleware,
    Workflow,
    WorkflowBuilder,
    create_always_approve_tool_response,
    tool,
)
from conftest import StreamingChatClientStub  # pyrefly: ignore[missing-import] # pyright: ignore[reportMissingImports]
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sse_helpers import parse_sse_response  # pyrefly: ignore[missing-import] # pyright: ignore[reportMissingImports]

from agent_framework_ag_ui import AGUIRequest, InMemoryAGUIThreadSnapshotStore, add_agent_framework_fastapi_endpoint

ScopeMode = Literal["authorization", "snapshot"]

REPLY_TEXT = "model-reply"
GATED_TOOL_NAME = "gated_action"
INVOKE_PREFIX = "invoke:"
PRINCIPALS = ("alice", "bob")


class RecordingChatClient(StreamingChatClientStub):
    """Stub chat client that records what every model call received and which session was behind it.

    A user message that starts with ``invoke:`` makes the model request the approval-gated tool.
    """

    def __init__(self) -> None:
        super().__init__(self._respond)
        self.calls: list[list[tuple[str, str]]] = []
        self.sessions: list[AgentSession | None] = []
        self.executed: list[str] = []

    async def _respond(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> AsyncIterator[ChatResponseUpdate]:
        del options, kwargs
        self.calls.append([(message.role, message.text) for message in messages])
        self.sessions.append(self.last_session)
        last = messages[-1] if messages else None
        if last is not None and last.role == "user" and last.text.startswith(INVOKE_PREFIX):
            contents = [
                Content.from_function_call(
                    call_id=str(uuid.uuid4()),
                    id=str(uuid.uuid4()),
                    name=GATED_TOOL_NAME,
                    arguments={"value": last.text.removeprefix(INVOKE_PREFIX)},
                )
            ]
        else:
            contents = [Content.from_text(REPLY_TEXT)]
        yield ChatResponseUpdate(role="assistant", contents=contents, message_id=str(uuid.uuid4()))

    def saw(self, marker: str, *, call: int = -1) -> bool:
        """Whether the model-bound messages of one call (the last by default) contain ``marker``."""
        return any(marker in text for _, text in self.calls[call])


def build_agent(client: RecordingChatClient, *, standing_approvals: bool = False) -> Agent[Any]:
    """Build an agent whose history lives in its session and whose gated tool records its executions."""

    @tool(name=GATED_TOOL_NAME, approval_mode="always_require")
    def gated_action(value: str) -> str:
        client.executed.append(value)
        return f"completed:{value}"

    return Agent(
        client=client,
        name="worker",
        tools=[gated_action],
        context_providers=[InMemoryHistoryProvider(source_id="history")],
        middleware=[ToolApprovalMiddleware()] if standing_approvals else [],
    )


def build_workflow(agent: Agent[Any], *, session: AgentSession | None = None) -> Workflow:
    """Build a new workflow around a new ``AgentExecutor``.

    The executor owns a new ``AgentSession`` unless ``session`` injects an existing one.
    """
    executor = AgentExecutor(agent, id="worker", session=session)
    return WorkflowBuilder(start_executor=executor, output_from=[executor]).build()


class UnhashableSession(AgentSession):
    """Session that compares by value. A class that defines ``__eq__`` alone is unhashable."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, UnhashableSession) and self.session_id == other.session_id


class EqualSession(AgentSession):
    """Session whose instances all compare equal and share one hash, whatever their state."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EqualSession)

    def __hash__(self) -> int:
        return 0


class UnhashableExecutor(AgentExecutor):
    """Executor that compares by id. A class that defines ``__eq__`` alone is unhashable."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, UnhashableExecutor) and self.id == other.id


def build_unhashable_executor_workflow(agent: Agent[Any]) -> Workflow:
    """Build a new workflow around an ``AgentExecutor`` subclass that is unhashable."""
    executor = UnhashableExecutor(agent, id="worker")
    return WorkflowBuilder(start_executor=executor, output_from=[executor]).build()


async def _authenticated_scope(authorization: str = Header(default="")) -> str:
    principal = authorization.removeprefix("token-")
    if principal not in PRINCIPALS:
        raise HTTPException(status_code=401)
    return f"principal:{principal}"


def _forwarded_scope(request: AGUIRequest) -> str:
    assert request.forwarded_props is not None
    return f"principal:{request.forwarded_props['principal']}"


def build_app(
    runner: Any,
    scope_mode: ScopeMode | Literal["single_user"],
    *,
    persist_snapshots: bool = False,
) -> FastAPI:
    """Register ``runner`` with the authorization mode under test."""
    app = FastAPI()
    options: dict[str, Any] = {"keepalive_seconds": None}
    if persist_snapshots:
        options["snapshot_store"] = InMemoryAGUIThreadSnapshotStore()
    if scope_mode == "authorization":
        options["authorization_scope_resolver"] = _authenticated_scope
    elif scope_mode == "snapshot":
        options["snapshot_scope_resolver"] = _forwarded_scope
    else:
        options["single_user"] = True
    add_agent_framework_fastapi_endpoint(app, runner, **options)
    return app


def post_run(
    http: TestClient,
    principal: str,
    thread_id: str,
    text: str | None = None,
    *,
    resume: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """POST one AG-UI run as ``principal`` with a fresh message id and consume the whole SSE stream."""
    body: dict[str, Any] = {
        "threadId": thread_id,
        "runId": f"run-{uuid.uuid4()}",
        "messages": [] if text is None else [{"id": f"message-{uuid.uuid4()}", "role": "user", "content": text}],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {"principal": principal},
    }
    if resume is not None:
        body["resume"] = resume
    with http.stream("POST", "/", json=body, headers={"Authorization": f"token-{principal}"}) as response:
        content = b"".join(response.iter_bytes())
    assert response.status_code == 200
    return parse_sse_response(content)


def event_types(events: Sequence[Mapping[str, Any]]) -> list[str]:
    return [event["type"] for event in events]


def run_error_codes(events: Sequence[Mapping[str, Any]]) -> list[str | None]:
    return [event.get("code") for event in events if event["type"] == "RUN_ERROR"]


def assistant_text(events: Sequence[Mapping[str, Any]]) -> str:
    return "".join(event["delta"] for event in events if event["type"] == "TEXT_MESSAGE_CONTENT")


def interrupts(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        interrupt
        for event in events
        if event["type"] == "RUN_FINISHED"
        for interrupt in event.get("outcome", {}).get("interrupts", [])
    ]


def always_approve_resume(interrupt: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Answer an approval interrupt with a standing "always approve" decision for the gated tool."""
    request = Content.from_dict(interrupt["metadata"]["agent_framework"]["value"])
    response = create_always_approve_tool_response(request)
    return [{"interruptId": interrupt["id"], "status": "resolved", "payload": response.to_dict()}]
