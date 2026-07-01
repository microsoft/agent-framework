# Copyright (c) Microsoft. All rights reserved.

"""Steerable conversations demo client.

Demonstrates steerable_conversations by sending two concurrent turns to a
running ResponsesHostServer.  Run this while main.py is running in a second
terminal to see steering in action.

Usage
-----
Terminal 1 — start the server:
    uv run python main.py

Terminal 2 — run this client:
    uv run python client.py [SERVER_URL]

SERVER_URL defaults to http://localhost:8088.
Set it to your deployed agent URL to test against a hosted instance.

What you will see
-----------------
Turn 1 starts streaming a long response (counting to 50).  Two seconds later,
turn 2 arrives on the same conversation with a different question.  Because the
server has steerable_conversations=True, turn 2 is accepted immediately with
status=queued rather than rejected with 409.  The server then cancels turn 1's
handler, which emits a partial response.completed event.  Once turn 1 finishes,
turn 2 runs and streams its answer.

Watch the server terminal to see the steering signal, cancellation, and drain
logged in real time.
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

_DEFAULT_BASE = "http://localhost:8088"
_MODEL = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")


def _parse_sse(chunk: str) -> dict[str, Any] | None:
    for line in chunk.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass
    return None


async def demo(base: str) -> None:
    """Run the steering demonstration against *base* URL."""
    import uuid

    conv_id = f"demo-{uuid.uuid4().hex[:8]}"
    turn1_text: list[str] = []
    turn1_terminal: str | None = None

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=5)
    async with httpx.AsyncClient(base_url=base, timeout=120, limits=limits) as client:
        print(f"\nConnected to {base}")
        print(f"Conversation ID: {conv_id}\n")

        # ------------------------------------------------------------------
        # Turn 1: ask the agent to count slowly.  Stream the response in
        # real-time so we can see the partial output before steering.
        # ------------------------------------------------------------------
        async def stream_turn1() -> None:
            nonlocal turn1_terminal
            print(">>> Turn 1: 'Count from 1 to 50, one number per line.'")
            async with client.stream(
                "POST",
                "/responses",
                json={
                    "model": _MODEL,
                    "input": "Count from 1 to 50, one number per line.",
                    "stream": True,
                    "store": True,
                    # "conversation" is the b8 field for a shared conversation ID.
                    # Both turns must carry the same value to share the same
                    # multi-turn steerable task.
                    "conversation": conv_id,
                },
            ) as resp:
                assert resp.status_code == 200, f"Turn 1 failed: {resp.status_code}"
                async for chunk in resp.aiter_text():
                    event = _parse_sse(chunk)
                    if event is None:
                        continue
                    et = event.get("type", "")
                    if et == "response.output_item.delta":
                        delta = (
                            event.get("delta", {}).get("text", "")
                            or event.get("delta", {}).get("content", "")
                            or ""
                        )
                        if delta:
                            print(delta, end="", flush=True)
                            turn1_text.append(delta)
                    elif et in ("response.completed", "response.failed", "response.cancelled"):
                        turn1_terminal = et.split(".")[-1]
                        break

        # ------------------------------------------------------------------
        # Turn 2: sent 2 s later while turn 1 is still streaming.
        # background=True returns status=queued immediately so we don't block.
        # ------------------------------------------------------------------
        async def send_turn2() -> dict[str, Any]:
            await asyncio.sleep(2)
            print("\n\n>>> Turn 2 (sent while turn 1 is still running): 'What is the capital of France?'")
            r2 = await client.post(
                "/responses",
                json={
                    "model": _MODEL,
                    "input": "What is the capital of France?",
                    "background": True,
                    "store": True,
                    "conversation": conv_id,
                },
            )
            assert r2.status_code == 200, f"Turn 2 failed: {r2.status_code} {r2.text}"
            return r2.json()  # type: ignore[no-any-return]

        t1 = asyncio.create_task(stream_turn1())
        r2 = await send_turn2()

        r2_id = r2["id"]
        r2_status = r2["status"]
        print(f"\n    Turn 2 response ID : {r2_id}")
        print(f"    Turn 2 status      : {r2_status}")

        if r2_status != "queued":
            print(
                f"\nUnexpected status {r2_status!r} — expected 'queued'.\n"
                "  If 'conflict': the server may not have steerable_conversations=True.\n"
                "  If 'in_progress': turn 1 completed before turn 2 arrived; "
                "the model may be responding too quickly for this prompt."
            )

        # Wait for turn 1 to drain
        await t1
        print(f"\n    Turn 1 terminated  : response.{turn1_terminal}")
        print(f"    Turn 1 text so far : {len(''.join(turn1_text))} chars")

        # Poll turn 2 until it completes, then print the agent's reply
        print("\n>>> Waiting for turn 2 to complete...")
        for _ in range(120):
            await asyncio.sleep(0.5)
            s2_resp = (await client.get(f"/responses/{r2_id}")).json()
            s2 = s2_resp["status"]
            print(f"    status: {s2}")
            if s2 in ("completed", "failed", "cancelled"):
                if s2 == "completed":
                    output_text = ""
                    for item in s2_resp.get("output", []):
                        for part in item.get("content", []):
                            output_text += part.get("text", "") or part.get("content", "")
                    print(f"\n>>> Turn 2 answer: {output_text.strip()}")
                break
        else:
            print("Turn 2 did not complete within the timeout.")


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_BASE
    asyncio.run(demo(base_url))
