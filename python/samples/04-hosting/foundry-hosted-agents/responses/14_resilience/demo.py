# Copyright (c) Microsoft. All rights reserved.

"""Automated crash-recovery demonstration.

Starts main.py as a subprocess, sends a background request, kills the server
to simulate a crash, restarts it, and watches the response recover and
complete — all without any manual timing.

Usage:
    uv run python demo.py

Prerequisites: fill in .env with FOUNDRY_PROJECT_ENDPOINT and
AZURE_AI_MODEL_DEPLOYMENT_NAME, then run 'az login'.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

_BASE = "http://localhost:8088"
_MODEL = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")

# A prompt that reliably produces a substantive multi-paragraph response
# so the handler is definitely still running when we kill the server.
_PROMPT = (
    "Write a detailed technical explanation of how the internet works. "
    "Cover TCP/IP, DNS, HTTP, TLS, routing, and CDNs. "
    "Explain each topic with examples. Be thorough."
)


async def _wait_for_server(timeout: float = 30) -> bool:
    """Poll /readiness until the server responds or the timeout expires."""
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as probe:
        while time.monotonic() < deadline:
            try:
                r = await probe.get(f"{_BASE}/readiness", timeout=1.0)
                if r.status_code == 200:
                    return True
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.3)
    return False


def _start_server() -> subprocess.Popen[bytes]:
    """Start main.py as a subprocess, suppressing its output."""
    return subprocess.Popen(
        [sys.executable, "main.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def demo() -> None:
    """Run the full crash-recovery demonstration."""
    # ------------------------------------------------------------------
    # 1. Start the server
    # ------------------------------------------------------------------
    print("Step 1/5  Starting server...")
    server = _start_server()
    if not await _wait_for_server():
        server.terminate()
        print("ERROR: Server did not start within 30 s")
        sys.exit(1)
    print(f"          Server ready (pid={server.pid})\n")

    try:
        async with httpx.AsyncClient(base_url=_BASE, timeout=60) as client:
            # ----------------------------------------------------------
            # 2. Send a background request — returns immediately with
            #    status=in_progress while the handler runs in a task.
            # ----------------------------------------------------------
            print("Step 2/5  Sending background request...")
            r = await client.post(
                "/responses",
                json={
                    "model": _MODEL,
                    "input": _PROMPT,
                    "background": True,
                    "store": True,
                },
            )
            assert r.status_code == 200, f"POST failed: {r.status_code} {r.text}"
            body: dict[str, Any] = r.json()
            resp_id: str = body["id"]
            print(f"          Response ID : {resp_id}")
            print(f"          Status      : {body['status']}  (handler is running)\n")

        # Allow the handler a moment to start before we kill.
        await asyncio.sleep(2)

        # ----------------------------------------------------------
        # 3. Kill the server — simulates a process crash.
        # ----------------------------------------------------------
        print("Step 3/5  Simulating crash (terminating server)...")
        server.terminate()
        server.wait(timeout=10)
        print(f"          Server killed (exit code: {server.returncode})\n")
        await asyncio.sleep(1)  # allow OS to release the port

        # ----------------------------------------------------------
        # 4. Restart — the recovery scanner runs on startup and
        #    re-invokes the handler for any in-progress resilient task.
        # ----------------------------------------------------------
        print("Step 4/5  Restarting server (recovery scanner will fire)...")
        server = _start_server()
        if not await _wait_for_server():
            server.terminate()
            print("ERROR: Server did not restart within 30 s")
            sys.exit(1)
        print(f"          Server restarted (pid={server.pid})\n")

        # ----------------------------------------------------------
        # 5. Poll until the response completes.
        # ----------------------------------------------------------
        print("Step 5/5  Polling response (watching recovery)...")
        async with httpx.AsyncClient(base_url=_BASE, timeout=120) as client:
            for _ in range(120):
                await asyncio.sleep(1)
                poll = (await client.get(f"/responses/{resp_id}")).json()
                status = poll.get("status", "unknown")
                print(f"          status: {status}")
                if status in ("completed", "failed", "cancelled"):
                    if status == "completed":
                        output_text = "".join(
                            part.get("text", "") or part.get("content", "")
                            for item in poll.get("output", [])
                            for part in item.get("content", [])
                        )
                        preview = output_text[:400] + ("..." if len(output_text) > 400 else "")
                        print(f"\nRecovered response ({len(output_text)} chars):\n{preview}")
                    else:
                        print(f"\nResponse ended with status={status!r}")
                    break
            else:
                print("Response did not complete within the timeout")

    finally:
        server.terminate()

    print("\nDEMO COMPLETE")


if __name__ == "__main__":
    asyncio.run(demo())
