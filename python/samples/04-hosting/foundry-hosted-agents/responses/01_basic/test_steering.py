# Copyright (c) Microsoft. All rights reserved.

"""Steering integration test for ResponsesHostServer.

Verifies steerable_conversations=True with a real FoundryChatClient agent
running on a local HTTP server (Hypercorn).

Setup
-----
Copy .env.example to .env and fill in your values:

    FOUNDRY_PROJECT_ENDPOINT=https://...
    AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o

Run ``az login`` first, then:

    uv run python test_steering.py       (from the 01_basic/ directory)

Design
------
Two concurrent HTTP requests drive the steering flow:

  1. Turn 1 — foreground streaming POST asking the agent for a long response.
     The SSE stream is consumed in real-time.

  2. Turn 2 — sent 2 s after turn 1 starts (while the agent is still streaming),
     with ``background=True`` and the same ``conversation`` value.  With
     ``steerable_conversations=True`` the server returns ``status=queued``
     instead of HTTP 409 conflict.

  3. The steering signal fires in turn 1's handler.  Turn 1 emits
     ``response.completed`` with partial output and its SSE stream ends.

  4. The framework drains the queue and runs turn 2.  Polling
     ``GET /responses/{id}`` confirms it reaches ``completed``.

Expected output:
    Server started on 127.0.0.1:18088
    [turn 1] streaming started  id=resp_...
    [turn 2] status=queued      id=resp_...   <- queued instead of 409
    [turn 1] terminal: response.completed     <- steered-out turn completed cleanly
    [turn 2] polled: in_progress
    [turn 2] polled: completed               <- steered turn ran and finished
    PASS: steering flow completed successfully
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

_PORT = 18088
_BASE = f"http://127.0.0.1:{_PORT}"


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
    """Run the steering integration test against a real Foundry agent."""
    import uuid

    from agent_framework.foundry import FoundryChatClient
    from agent_framework_foundry_hosting import ResponsesHostServer
    from azure.ai.agentserver.responses import InMemoryResponseProvider
    from azure.identity import AzureCliCredential

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )
    agent = client.as_agent(
        name="steering-test-agent",
        instructions=(
            "You are a helpful assistant. When asked to count or list things, "
            "produce a long response with many items so that streaming takes several seconds."
        ),
    )

    server = ResponsesHostServer(
        agent,
        store=InMemoryResponseProvider(),
        steerable_conversations=True,
    )

    # Use a unique conversation ID per run to avoid conflicts with stale
    # task state from previous test runs.
    conv_id = f"steer-test-{uuid.uuid4().hex[:8]}"

    shutdown_event = await _start_server(server, _PORT)
    print(f"Server started on 127.0.0.1:{_PORT}")

    try:
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=5)
        async with httpx.AsyncClient(base_url=_BASE, timeout=120, limits=limits) as http:
            r1_id: str | None = None
            r1_terminal: str | None = None

            # -------------------------------------------------------------- #
            # Turn 1 — stream a long response, read it in real-time.         #
            # -------------------------------------------------------------- #
            async def stream_turn1() -> None:
                nonlocal r1_id, r1_terminal
                async with http.stream(
                    "POST",
                    "/responses",
                    json={
                        "model": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                        "input": "Count from 1 to 100, one number per line.",
                        "stream": True,
                        "store": True,
                        # "conversation" (not "conversation_id") is the b8 field name.
                        # Both turns must carry the same value to share the same
                        # multi-turn steerable task.
                        "conversation": conv_id,
                    },
                ) as response:
                    assert response.status_code == 200, f"Turn 1 failed: {response.status_code}"
                    async for chunk in response.aiter_text():
                        event = _parse_sse_chunk(chunk)
                        if event is None:
                            continue
                        et = event.get("type", "")
                        if et == "response.created" and r1_id is None:
                            r1_id = event["response"]["id"]
                        if et in ("response.completed", "response.failed", "response.cancelled"):
                            r1_terminal = et.split(".")[-1]
                            break

            # -------------------------------------------------------------- #
            # Turn 2 — sent while turn 1 is still streaming.                 #
            # background=True returns status=queued immediately.             #
            # -------------------------------------------------------------- #
            async def send_turn2() -> dict[str, Any]:
                # Give turn 1 time to start streaming before we steer.
                await asyncio.sleep(2)

                r2 = await http.post(
                    "/responses",
                    json={
                        "model": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                        "input": "Stop — instead, tell me a short joke.",
                        "background": True,
                        "store": True,
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
                "  status=conflict   → steerable_conversations may not be enabled.\n"
                "  status=in_progress → turn 1 already completed before turn 2 arrived;\n"
                "                       try increasing the asyncio.sleep(2) in send_turn2.\n"
                "  Note: both turns must carry the same 'conversation' value."
            )

            # Wait for turn 1 to terminate (it was steered out).
            await t1_task
            print(f"[turn 1] terminal: response.{r1_terminal}")
            assert r1_terminal == "completed", (
                f"Turn 1 should reach completed when steered, got {r1_terminal!r}.\n"
                "  None or 'failed' → the cancellation terminal fix may be missing."
            )

            # Poll turn 2 until terminal.
            for _ in range(120):
                await asyncio.sleep(0.5)
                s2 = (await http.get(f"/responses/{r2_id}")).json()["status"]
                print(f"[turn 2] polled: {s2}")
                if s2 in ("completed", "failed", "cancelled"):
                    break
            else:
                raise AssertionError("Turn 2 never reached a terminal state within the timeout")

            assert s2 == "completed", f"Expected turn 2 to complete, got {s2!r}"

    finally:
        shutdown_event.set()
        await asyncio.sleep(1.5)

    print("PASS: steering flow completed successfully")


if __name__ == "__main__":
    try:
        asyncio.run(run_steering_test())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
