# Copyright (c) Microsoft. All rights reserved.

"""Demonstrate that a long-running workflow survives host interruptions.

The demo submits one background request to a four-stage pipeline, stops the
host twice while work is in progress, and starts a replacement host each time.
It then verifies that:

- the original request still completes,
- completed stages are not repeated,
- interrupted work continues automatically, and
- intermediate progress and final response output are preserved.

Server and telemetry output is written to an isolated diagnostic log instead
of the console. The temporary state is removed after a successful run.

Usage:
    uv run python demo.py

Prerequisites: none. No external services, model deployments, or credentials
are required -- the whole pipeline is local and deterministic.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

_BASE = "http://localhost:8088"
_MAIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
_SERVER_LOG = "server.log"

_STAGES = ("ingest", "transform", "validate", "finalize")

# Allow the host to durably record a completed stage before interrupting the
# following stage.
_KILL_GRACE_SECONDS = 2.0


async def _wait_for_server(base_url: str, timeout: float = 30) -> bool:
    """Poll /readiness until the server responds or the timeout expires."""
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as probe:
        while time.monotonic() < deadline:
            try:
                r = await probe.get(f"{base_url}/readiness", timeout=1.0)
                if r.status_code == 200:
                    return True
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.3)
    return False


async def _wait_for_marker(markers_dir: Path, stage: str, timeout: float = 60) -> None:
    """Poll the filesystem until <stage>.json appears under markers_dir."""
    marker = markers_dir / f"{stage}.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists():
            return
        await asyncio.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for stage marker: {marker}")


def _start_server(state_dir: Path, stage_delay_seconds: float) -> subprocess.Popen[bytes]:
    """Start main.py with isolated durable state and captured diagnostics."""
    env = dict(os.environ)
    env["HOME"] = str(state_dir)
    env["USERPROFILE"] = str(state_dir)
    env["WORKFLOW_STATE_DIR"] = str(state_dir)
    env["WORKFLOW_STAGE_DELAY_SECONDS"] = str(stage_delay_seconds)
    with (state_dir / _SERVER_LOG).open("ab") as server_log:
        server_log.write(b"\n--- starting host instance ---\n")
        server_log.flush()
        return subprocess.Popen(
            [sys.executable, _MAIN],
            cwd=str(state_dir),
            env=env,
            stdout=server_log,
            stderr=subprocess.STDOUT,
        )


def _interrupt(server: subprocess.Popen[bytes], running_stage: str) -> None:
    print(f"[INTERRUPT] Stopping the host while '{running_stage}' is running...")
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=10)
    print("[INTERRUPT] Host stopped unexpectedly.\n")


def _print_log_tail(state_dir: Path, line_count: int = 40) -> None:
    log_path = state_dir / _SERVER_LOG
    if not log_path.exists():
        return
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\nLast server diagnostic lines:")
    for line in lines[-line_count:]:
        print(f"  {line}")


def _read_audit(state_dir: Path) -> list[dict[str, Any]]:
    audit_path = state_dir / "audit.jsonl"
    if not audit_path.exists():
        return []
    with audit_path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def demo() -> None:
    """Run the customer-facing durability demonstration."""
    state_dir = Path(tempfile.mkdtemp(prefix="workflow_resilience_demo_"))
    markers_dir = state_dir / "markers"
    stage_delay_seconds = 4.0
    succeeded = False
    print("Durable workflow recovery demo")
    print("==============================")
    print("Pipeline: ingest -> transform -> validate -> finalize")
    print("The host will be interrupted twice while one request is running.\n")

    server: subprocess.Popen[bytes] | None = None
    try:
        print("[START] Starting the first host instance...")
        server = _start_server(state_dir, stage_delay_seconds)
        if not await _wait_for_server(_BASE):
            _interrupt(server, "startup")
            raise RuntimeError("Server did not start within 30 seconds.")
        print("[OK] Host is ready.\n")

        async with httpx.AsyncClient(base_url=_BASE, timeout=60) as client:
            print("[REQUEST] Starting one background workflow request...")
            r = await client.post(
                "/responses",
                json={
                    "model": "n/a",  # ignored: WorkflowAgent doesn't use runtime model options
                    "input": "run the resilient pipeline",
                    "background": True,
                    "store": True,
                },
            )
            assert r.status_code == 200, f"POST failed: {r.status_code} {r.text}"
            body: dict[str, Any] = r.json()
            resp_id: str = body["id"]
            print(f"[OK] Request accepted: {resp_id}")
            print(f"[OK] Initial status: {body['status']}\n")

        print("[WORKFLOW] Waiting for the first stage to complete...")
        await _wait_for_marker(markers_dir, "ingest")
        print("[OK] 'ingest' completed and its progress was saved.")
        await asyncio.sleep(_KILL_GRACE_SECONDS)
        _interrupt(server, "transform")

        print("[RECOVER] Starting a replacement host...")
        server = _start_server(state_dir, stage_delay_seconds)
        if not await _wait_for_server(_BASE):
            _interrupt(server, "recovery startup")
            raise RuntimeError("Replacement host did not start within 30 seconds.")
        print("[OK] The existing request was recovered automatically.\n")

        print("[WORKFLOW] Waiting for two more stages to complete...")
        await _wait_for_marker(markers_dir, "validate")
        print("[OK] 'transform' and 'validate' completed; saved progress was preserved.")
        await asyncio.sleep(_KILL_GRACE_SECONDS)
        _interrupt(server, "finalize")

        print("[RECOVER] Starting another replacement host...")
        server = _start_server(state_dir, stage_delay_seconds)
        if not await _wait_for_server(_BASE):
            _interrupt(server, "recovery startup")
            raise RuntimeError("Replacement host did not start within 30 seconds.")
        print("[OK] The same request was recovered again.\n")

        print("[REQUEST] Waiting for the original request to finish...")
        async with httpx.AsyncClient(base_url=_BASE, timeout=60) as client:
            status = "unknown"
            for _ in range(150):
                await asyncio.sleep(0.5)
                poll = (await client.get(f"/responses/{resp_id}")).json()
                status = poll.get("status", "unknown")
                if status in ("completed", "failed", "cancelled"):
                    break
            assert status == "completed", f"Response did not complete: status={status!r}"

            output_texts = [
                "".join(part.get("text", "") or part.get("content", "") for part in item.get("content", []))
                for item in poll.get("output", [])
                if item.get("type") == "message"
            ]
            expected_outputs = [
                "[ingest] received request: 'run the resilient pipeline'",
                "[transform] normalized request: 'run the resilient pipeline'",
                "[validate] validated request: 'run the resilient pipeline'",
                (
                    "Pipeline complete for 'run the resilient pipeline'. "
                    "Stages executed: ingest, transform, validate, finalize."
                ),
            ]
            assert output_texts == expected_outputs, (
                f"Recovered response did not preserve the expected workflow outputs: {output_texts!r}"
            )
            final_output = output_texts[-1]

        for stage in _STAGES:
            marker = markers_dir / f"{stage}.json"
            assert marker.exists(), f"Missing stage marker: {marker}"

        audit = _read_audit(state_dir)
        counts = {stage: sum(1 for entry in audit if entry["stage"] == stage) for stage in _STAGES}
        for stage, count in counts.items():
            assert count == 1, (
                f"Stage {stage!r} appears {count} times in audit.jsonl; expected exactly once. "
                "A count > 1 means a completed stage replayed; a count of 0 means it never ran."
            )

        print("\nResult")
        print("------")
        print("[OK] The original request completed after two host interruptions.")
        print("[OK] Progress output from every completed stage was preserved.")
        print(f"[OK] Final output: {final_output}")
        print("[OK] Every completed stage ran exactly once:")
        for stage in _STAGES:
            print(f"     {stage}: {counts[stage]}")
        print("\nPASS: Durable progress and response output survived both interruptions.")
        succeeded = True

    except Exception:
        print("\nFAIL: The durability demonstration did not complete.")
        _print_log_tail(state_dir)
        raise

    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        if succeeded:
            shutil.rmtree(state_dir, ignore_errors=True)
        else:
            print(f"\nDiagnostic state retained at: {state_dir}")


if __name__ == "__main__":
    asyncio.run(demo())
