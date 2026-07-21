# Copyright (c) Microsoft. All rights reserved.

"""HTTP round-trip tests: POST -> FastAPI route -> JSON/SSE response.

These exercise the same wiring as the `local_responses` sample: helpers from
`agent_framework_hosting_responses` convert between the Responses protocol and
Agent Framework run values, `agent_framework_hosting`'s `AgentState` /
`SessionStore` hold shared execution state, and a small FastAPI route owns
everything else (parsing, policy, response construction). Requests go through
`httpx.AsyncClient` with `ASGITransport` -- no real server process or live
model is involved.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Mapping
from typing import Any, Literal, overload

import httpx
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    Content,
    Message,
    ResponseStream,
)
from agent_framework_hosting import AgentState
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_from_streaming_run,
    responses_session_id,
    responses_to_run,
)


class _StubAgent:
    """Deterministic ``SupportsAgentRun`` stub that tracks session continuity.

    Each call records the ``session_id`` of the ``AgentSession`` it was
    invoked with and a per-session turn counter, so tests can assert that a
    chain of requests reused one session instead of silently starting fresh
    ones.
    """

    id = "stub-agent"
    name: str | None = "stub-agent"
    description: str | None = "stub agent for HTTP round-trip tests"

    def __init__(self) -> None:
        self.session_ids_seen: list[str | None] = []
        self.turn_counts: dict[str | None, int] = {}
        self.session_turn_counts_seen: list[int] = []

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(self, service_session_id: Any, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id, service_session_id=service_session_id)

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        session_id = session.session_id if session is not None else None
        self.session_ids_seen.append(session_id)
        self.turn_counts[session_id] = self.turn_counts.get(session_id, 0) + 1
        session_turn = int(session.state.get("turn_count", 0)) + 1 if session is not None else 1
        if session is not None:
            session.state["turn_count"] = session_turn
        self.session_turn_counts_seen.append(session_turn)
        text = f"turn {session_turn} for session {session_id}"

        if stream:

            async def _stream() -> AsyncIterator[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[Content.from_text(text=text)], role="assistant")

            return ResponseStream(_stream(), finalizer=lambda updates: AgentResponse.from_updates(updates))

        async def _get_response() -> AgentResponse[Any]:
            return AgentResponse(messages=Message(role="assistant", contents=[Content.from_text(text=text)]))

        return _get_response()


def _build_app(agent: _StubAgent) -> FastAPI:
    """Build a minimal FastAPI app mirroring the `local_responses` sample's route."""
    app = FastAPI()
    state = AgentState(agent)

    @app.post("/responses", response_model=None)
    async def responses(body: dict[str, Any] = Body(...)) -> JSONResponse | StreamingResponse:  # noqa: B008
        try:
            run = responses_to_run(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session_id, is_conversation_id = responses_session_id(body)
        conversation_id = session_id if is_conversation_id else None
        response_id = create_response_id()

        target = await state.get_target()
        lookup_id = session_id or response_id
        session = await state.get_or_create_session(lookup_id)

        if run["stream"]:
            stream = target.run(run["messages"], stream=True, session=session)
            if not isinstance(stream, ResponseStream):
                raise HTTPException(status_code=500, detail="agent did not return a response stream")

            async def stream_events() -> AsyncIterator[str]:
                async for event in responses_from_streaming_run(
                    stream,
                    response_id=response_id,
                    session_id=session_id,
                ):
                    yield event
                if conversation_id is not None:
                    await state.set_session(conversation_id, session)
                else:
                    await state.set_session(response_id, session)

            return StreamingResponse(
                stream_events(),
                media_type="text/event-stream",
            )

        result = await target.run(run["messages"], session=session)
        if conversation_id is not None:
            await state.set_session(conversation_id, session)
        else:
            await state.set_session(response_id, session)
        return JSONResponse(responses_from_run(result, response_id=response_id, session_id=session_id))

    return app


async def _post(app: FastAPI, payload: dict[str, Any]) -> httpx.Response:
    """Send a POST /responses request through the ASGI app, no real socket involved."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/responses", json=payload, timeout=30)


def _parse_sse_events(body: str) -> list[dict[str, Any]]:
    """Parse SSE text into a list of `{"event": ..., "data": ...}` dicts."""
    events: list[dict[str, Any]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event_type: str | None = None
        data: str | None = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        if event_type is not None and data is not None:
            events.append({"event": event_type, "data": json.loads(data)})
    return events


class TestNonStreamingRoundTrip:
    async def test_returns_responses_shaped_payload(self) -> None:
        app = _build_app(_StubAgent())
        response = await _post(app, {"input": "hello"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["object"] == "response"
        assert payload["status"] == "completed"
        assert payload["id"].startswith("resp_")
        assert any(item["type"] == "message" for item in payload["output"])

    async def test_invalid_input_returns_400_not_500(self) -> None:
        app = _build_app(_StubAgent())
        response = await _post(app, {})

        assert response.status_code == 400
        assert "input" in response.json()["detail"]


class TestStreamingRoundTrip:
    async def test_stream_emits_created_delta_and_completed_events(self) -> None:
        app = _build_app(_StubAgent())
        response = await _post(app, {"input": "hello", "stream": True})

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events = _parse_sse_events(response.text)
        event_types = [e["event"] for e in events]
        assert event_types[0] == "response.created"
        assert event_types[-1] == "response.completed"
        assert "response.output_text.delta" in event_types

        completed = events[-1]["data"]["response"]
        assert completed["status"] == "completed"
        assert completed["id"].startswith("resp_")


class TestSessionContinuity:
    """Regression coverage for the `previous_response_id` aliasing fix.

    `previous_response_id` rotates every turn. Without aliasing the newly
    minted response id to the same session, turn 3 would silently resolve to
    a brand-new, empty session instead of the one from turns 1-2.
    """

    async def test_previous_response_id_chain_preserves_session_across_three_turns(self) -> None:
        agent = _StubAgent()
        app = _build_app(agent)

        turn1 = await _post(app, {"input": "hi"})
        assert turn1.status_code == 200
        turn2 = await _post(app, {"input": "still there?", "previous_response_id": turn1.json()["id"]})
        assert turn2.status_code == 200
        turn3 = await _post(app, {"input": "still there?", "previous_response_id": turn2.json()["id"]})
        assert turn3.status_code == 200

        assert len(agent.session_ids_seen) == 3
        # All three turns must have run against the same underlying session,
        # not three independent ones.
        first_session_id = agent.session_ids_seen[0]
        assert first_session_id is not None
        assert agent.session_ids_seen == [first_session_id] * 3
        assert agent.turn_counts[first_session_id] == 3
        assert agent.session_turn_counts_seen == [1, 2, 3]

    async def test_previous_response_id_supports_independent_branches(self) -> None:
        agent = _StubAgent()
        app = _build_app(agent)

        root = await _post(app, {"input": "root"})
        branch_one, branch_two = await asyncio.gather(
            _post(app, {"input": "branch one", "previous_response_id": root.json()["id"]}),
            _post(app, {"input": "branch two", "previous_response_id": root.json()["id"]}),
        )
        await asyncio.gather(
            _post(app, {"input": "continue one", "previous_response_id": branch_one.json()["id"]}),
            _post(app, {"input": "continue two", "previous_response_id": branch_two.json()["id"]}),
        )

        assert agent.session_turn_counts_seen == [1, 2, 2, 3, 3]

    async def test_conversation_id_preserves_session_across_turns(self) -> None:
        agent = _StubAgent()
        app = _build_app(agent)

        turn1 = await _post(app, {"input": "hi", "conversation_id": "conv_stable"})
        assert turn1.status_code == 200
        turn2 = await _post(app, {"input": "still there?", "conversation_id": "conv_stable"})
        assert turn2.status_code == 200

        assert agent.session_ids_seen == ["conv_stable", "conv_stable"]
        assert agent.turn_counts["conv_stable"] == 2
        assert agent.session_turn_counts_seen == [1, 2]

    async def test_unrelated_requests_get_independent_sessions(self) -> None:
        agent = _StubAgent()
        app = _build_app(agent)

        first = await _post(app, {"input": "hi"})
        second = await _post(app, {"input": "unrelated"})

        assert first.status_code == 200
        assert second.status_code == 200
        assert agent.session_ids_seen[0] != agent.session_ids_seen[1]
