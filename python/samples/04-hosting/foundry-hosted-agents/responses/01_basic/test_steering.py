# Copyright (c) Microsoft. All rights reserved.

"""Steering integration test for ResponsesHostServer.

Verifies steerable_conversations=True with a slow mock agent running on a
real local HTTP server (Hypercorn).  No Foundry deployment is required.

Design
------
Two concurrent HTTP requests drive the steering flow:

  1. Turn 1 — foreground streaming POST; the slow mock agent takes ~2.4 s to
     finish.  The SSE stream is read in real-time to extract the response_id
     from the ``response.created`` event.

  2. Turn 2 — sent 0.5 s after turn 1 starts, with ``previous_response_id``
     pointing at turn 1.  With ``steerable_conversations=True`` the server
     queues turn 2 (status=queued) instead of returning 409 conflict.

  3. The steering signal fires in turn 1's handler.  Turn 1 emits
     ``response.completed`` with partial output and its SSE stream ends.

  4. The framework drains the queue and runs turn 2.  Polling
     ``GET /responses/{id}`` confirms it reaches ``completed``.

Run with:
    uv run python test_steering.py       (from the 01_basic/ directory)

Expected output:
    Server started on 127.0.0.1:18088
    [turn 1] streaming started  id=resp_...
    [turn 2] status=queued      id=resp_...   <- queued instead of 409
    [turn 1] stream ended: response.completed <- steered-out turn completed cleanly
    [turn 2] polled: in_progress
    [turn 2] polled: completed               <- steered turn ran and finished
    PASS: steering flow completed successfully
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from typing import Any

import httpx

_PORT = 18088
_BASE = f"http://127.0.0.1:{_PORT}"


# ---------------------------------------------------------------------------
# Minimal slow mock agent — streams N chunks with a configurable delay.
# ---------------------------------------------------------------------------


def _build_slow_agent(*, chunks: int = 8, delay: float = 0.3) -> Any:
    """Return a mock agent that streams *chunks* text updates *delay* seconds apart."""
    from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, ResponseStream

    class SlowAgent:
        def run(  # type: ignore[override]
            self, *args: object, stream: bool = False, **kwargs: object
        ) -> Any:
            # sync def (not async def): returns the right type based on stream kwarg.
            if stream:
                async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                    for i in range(chunks):
                        await asyncio.sleep(delay)
                        yield AgentResponseUpdate(
                            contents=[Content.from_text(f"chunk {i} ")],
                            role="assistant",
                        )

                return ResponseStream(_gen())  # type: ignore[arg-type]

            async def _result() -> AgentResponse:
                await asyncio.sleep(delay)
                return AgentResponse(
                    messages=[Message("assistant", [Content.from_text("done")])]
                )

            return _result()

    return SlowAgent()


# ---------------------------------------------------------------------------
# Hypercorn server lifecycle helper
# ---------------------------------------------------------------------------


async def _start_server(app: Any, port: int) -> asyncio.Event:
    """Start *app* on 127.0.0.1:*port* via Hypercorn; return a shutdown Event."""
    import hypercorn.asyncio
    import hypercorn.config

    config = hypercorn.config.Config()
    config.bind = [f"127.0.0.1:{port}"]
    config.graceful_timeout = 1.0
    config.loglevel = "WARNING"

    shutdown_event = asyncio.Event()
    asyncio.create_task(
        hypercorn.asyncio.serve(app, config, shutdown_trigger=shutdown_event.wait),
        name="hypercorn-serve",
    )
    # Wait until the server is accepting connections.
    for _ in range(40):
        await asyncio.sleep(0.1)
        try:
            async with httpx.AsyncClient() as probe:
                await probe.get(f"http://127.0.0.1:{port}/readiness", timeout=0.5)
            break
        except Exception:  # noqa: BLE001
            pass
    else:
        raise RuntimeError(f"Server did not start within 4 s on port {port}")

    return shutdown_event


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------


def _parse_sse_chunk(chunk: str) -> dict[str, Any] | None:
    """Return parsed event data from a single SSE text chunk, or None."""
    for line in chunk.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[len("data: "):])  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass
    return None


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


async def run_steering_test() -> None:
    import uuid

    from agent_framework_foundry_hosting import ResponsesHostServer
    from azure.ai.agentserver.responses import InMemoryResponseProvider

    # Use a unique conversation ID per run to avoid conflicts with stale
    # task state from previous test runs.
    conv_id = f"steer-test-{uuid.uuid4().hex[:8]}"

    agent = _build_slow_agent(chunks=8, delay=0.3)  # ~2.4 s to complete naturally
    server = ResponsesHostServer(
        agent,
        store=InMemoryResponseProvider(),
        steerable_conversations=True,
    )

    shutdown_event = await _start_server(server, _PORT)
    print(f"Server started on 127.0.0.1:{_PORT}")

    try:
        # Use limits to allow many concurrent requests on the same host.
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=5)
        async with httpx.AsyncClient(base_url=_BASE, timeout=60, limits=limits) as client:
            r1_id: str | None = None
            r1_id_ready = asyncio.Event()
            r1_terminal: str | None = None

            # -------------------------------------------------------------- #
            # Strategy: send both turns concurrently using asyncio.          #
            # Turn 1 streams SSE inline (blocks until agent finishes or is   #
            # steered).  Turn 2 is sent 0.5 s later while turn 1 is still   #
            # running.  Both turns share the same conversation ID — no need  #
            # to pass turn 1's response_id to turn 2.                        #
            # -------------------------------------------------------------- #

            async def stream_turn1() -> None:
                nonlocal r1_id, r1_terminal
                async with client.stream(
                    "POST",
                    "/responses",
                    # "conversation" (not "conversation_id") is the b8 field.
                    # Both turns carry the same value → same multi-turn task.
                    # store=True ensures the multi-turn resilient task is used.
                    json={
                        "model": "test-model",
                        "input": "start counting slowly",
                        "stream": True,
                        "store": True,
                        "conversation": conv_id,
                    },
                ) as response:
                    assert response.status_code == 200, (
                        f"Turn 1 failed: {response.status_code}"
                    )
                    async for chunk in response.aiter_text():
                        event = _parse_sse_chunk(chunk)
                        if event is None:
                            continue
                        et = event.get("type", "")
                        if et == "response.created" and r1_id is None:
                            r1_id = event["response"]["id"]
                            r1_id_ready.set()
                        if et in ("response.completed", "response.failed", "response.cancelled"):
                            r1_terminal = et.split(".")[-1]
                            break

            # -------------------------------------------------------------- #
            # Task 2 — wait 0.5 s then steer the conversation.              #
            # -------------------------------------------------------------- #
            async def send_turn2() -> dict[str, Any]:
                # Give turn 1 time to start its handler before we steer.
                await asyncio.sleep(0.5)

                r2 = await client.post(
                    "/responses",
                    json={
                        "model": "test-model",
                        "input": "stop counting, tell me a joke",
                        # background=True so the POST returns immediately with
                        # status=queued (the acceptance response) instead of
                        # blocking until the handler runs.
                        "background": True,
                        "store": True,
                        # same conversation value → queued into the running steerable task
                        "conversation": conv_id,
                    },
                )
                assert r2.status_code == 200, f"Turn 2 POST failed: {r2.status_code} {r2.text}"
                return r2.json()  # type: ignore[no-any-return]

            t1_task = asyncio.create_task(stream_turn1())
            r2_body = await send_turn2()

            r2_id = r2_body["id"]
            r2_status = r2_body["status"]
            print(f"[turn 1] streaming started  id={r1_id or '(id not yet seen)'}")
            print(f"[turn 2] status={r2_status:<14} id={r2_id}")

            assert r2_status == "queued", (
                f"Expected status=queued (turn 2 queued behind turn 1), got {r2_status!r}.\n"
                "  status=conflict  → steerable_conversations may not be enabled.\n"
                "  status=failed    → the steerable task may have already completed.\n"
                "  Note: requires 'conversation' field on both turns to share the same task."
            )

            # Wait for turn 1 to terminate (it was steered out).
            await t1_task
            print(f"[turn 1] terminal: response.{r1_terminal}")
            assert r1_terminal == "completed", (
                f"Turn 1 should reach completed when steered, got {r1_terminal!r}.\n"
                "  None or 'failed' → the cancellation terminal fix may be missing."
            )

            # -------------------------------------------------------------- #
            # Poll turn 2 until terminal.                                    #
            # -------------------------------------------------------------- #
            for _ in range(80):
                await asyncio.sleep(0.25)
                s2 = (await client.get(f"/responses/{r2_id}")).json()["status"]
                print(f"[turn 2] polled: {s2}")
                if s2 in ("completed", "failed", "cancelled"):
                    break
            else:
                raise AssertionError("Turn 2 never reached a terminal state within the timeout")

            assert s2 == "completed", f"Expected turn 2 to complete, got {s2!r}"

    finally:
        shutdown_event.set()
        await asyncio.sleep(1.5)  # allow graceful shutdown

    print("PASS: steering flow completed successfully")


if __name__ == "__main__":
    try:
        asyncio.run(run_steering_test())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
