# Copyright (c) Microsoft. All rights reserved.

"""End-to-end steering test for the steerable single-agent countdown sample.

Starts the server, kicks off a background streaming countdown, then -- while the model is still
generating -- sends a second turn on the same conversation with a new target. Verifies the second
turn is accepted immediately as "queued", that the first turn is cancelled and completes early
(fewer tokens than a full run), and that the second (steered) turn completes with a countdown for
its own target. Because this sample uses a real model (no deterministic per-tick pacing),
assertions here are necessarily looser than an exact output match. Requires the
same environment (.env) as running main.py directly.

Usage:
    python verify_steering.py [--first-target N] [--second-target N] [--min-deltas-before-steering N]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import IO, Any

HOST = "127.0.0.1"
PORT = 8088
BASE_URL = f"http://{HOST}:{PORT}"
SAMPLE_DIR = Path(__file__).parent
LOG_PATH = SAMPLE_DIR / "verify_steering.log"


def _http_get(path: str, timeout: float = 5.0) -> tuple[int, dict[str, Any]]:
    with urllib.request.urlopen(urllib.request.Request(f"{BASE_URL}{path}"), timeout=timeout) as resp:
        return resp.status, json.loads(resp.read())


def _http_post(path: str, payload: dict[str, Any], timeout: float = 30.0) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _poll_until_terminal(response_id: str, timeout: float) -> dict[str, Any]:
    """Poll ``GET /responses/{id}`` until the response reaches a terminal status.

    A ``stream=false`` create only guarantees a fast initial ack (e.g. ``"queued"``); this polls
    for the actual outcome instead of trying to replay it live (a ``?stream=true`` GET replay is
    only valid for a response that was itself created with ``stream=true``).
    """
    deadline = time.monotonic() + timeout
    snapshot: dict[str, Any] = {}
    while time.monotonic() < deadline:
        snapshot = _http_get(f"/responses/{response_id}")[1]
        if snapshot.get("status") in ("completed", "failed", "incomplete", "cancelled"):
            return snapshot
        time.sleep(0.5)
    return snapshot


def _start_server(log_file: IO[str]) -> subprocess.Popen:  # type: ignore
    return subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=SAMPLE_DIR,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


def _wait_for_ready(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, _ = _http_get("/readiness", timeout=2.0)
            if status == 200:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Server did not become ready in time.")


def _kill(server: subprocess.Popen) -> None:  # type: ignore
    if server.poll() is None:
        server.kill()
        server.wait(timeout=10)


def _watch_sse(request: "urllib.request.Request | str", progress: dict[str, Any]) -> None:
    """Read an SSE stream from a streaming create POST and track its progress.

    Tracks the response id (on ``response.created``), a running count of text delta events (a
    single-agent response streams as one message, not discrete output items), and signals
    ``progress["done"]`` on any terminal event.
    """
    try:
        with urllib.request.urlopen(request) as resp:
            # Without an explicit conversation_id, the session id (which scopes the conversation
            # chain id used to attach a steered turn to the same task) must be forwarded by the
            # caller on later turns -- otherwise each turn derives a different session id locally.
            session_id = resp.headers.get("x-agent-session-id")
            if session_id:
                progress["session_id"] = session_id
            current_event: str | None = None
            for raw_line in resp:
                line = raw_line.decode("utf-8").rstrip("\n")
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data_obj = json.loads(line[len("data:") :].strip())
                if current_event == "response.created" and "id" not in progress:
                    progress["id"] = data_obj["response"]["id"]
                    progress["status"] = data_obj["response"]["status"]
                    progress["ready"].set()
                elif current_event == "response.output_text.delta":
                    progress["delta_count"] += 1
                elif current_event in ("response.completed", "response.failed", "response.incomplete"):
                    progress["done"].set()
    except urllib.error.HTTPError as exc:
        progress["error"] = f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}"
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        progress["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        progress["ready"].set()
        progress["done"].set()


def _extract_output_text(output_items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in output_items:
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                parts.append(part["text"])
    return "".join(parts)


def _clear_stale_state() -> None:
    """Wipe ~/.agentserver so a prior run's task/queue state never leaks into this run."""
    state_root = Path.home() / ".agentserver"
    if state_root.exists():
        shutil.rmtree(state_root, ignore_errors=True)
        print(f"      cleared stale state: {state_root}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-target", type=int, default=30, help="First turn's countdown starting value.")
    parser.add_argument("--second-target", type=int, default=3, help="Steered turn's countdown starting value.")
    parser.add_argument(
        "--min-deltas-before-steering",
        type=int,
        default=15,
        help="Minimum text delta events to observe on turn 1 before sending the steering turn.",
    )
    args = parser.parse_args()

    _clear_stale_state()

    log_file = LOG_PATH.open("w", encoding="utf-8")
    print(f"Server logs (DEBUG level) are redirected to {LOG_PATH}.")

    print(f"[1/5] Starting server (first target={args.first_target}, second target={args.second_target})...")
    server = _start_server(log_file)  # type: ignore
    print(f"      PID: {server.pid}")
    try:
        _wait_for_ready()

        print("[2/5] Starting the first turn's background streaming countdown...")
        first_progress: dict[str, Any] = {
            "delta_count": 0,
            "ready": threading.Event(),
            "done": threading.Event(),
        }
        first_payload = {
            "input": f"Count down from {args.first_target}, slowly and with commentary.",
            "store": True,
            "background": True,
            "stream": True,
        }
        first_data = json.dumps(first_payload).encode("utf-8")
        first_request = urllib.request.Request(
            f"{BASE_URL}/responses", data=first_data, headers={"Content-Type": "application/json"}, method="POST"
        )
        first_watcher = threading.Thread(target=_watch_sse, args=(first_request, first_progress), daemon=True)
        first_watcher.start()
        if not first_progress["ready"].wait(timeout=60):
            raise SystemExit("FAIL: did not receive response.created for turn 1 in time.")
        if "id" not in first_progress:
            raise SystemExit(f"FAIL: turn 1 create request failed: {first_progress.get('error', 'unknown error')}")
        first_id = first_progress["id"]
        print(f"      turn 1 response id: {first_id}, status: {first_progress['status']}")

        print(f"[3/5] Waiting for turn 1 to stream at least {args.min_deltas_before_steering} tokens...")
        deadline = time.monotonic() + 60
        while first_progress["delta_count"] < args.min_deltas_before_steering:
            if first_progress["done"].is_set() or time.monotonic() > deadline:
                raise SystemExit(
                    "FAIL: turn 1 finished or timed out before enough tokens streamed to steer reliably; "
                    f"observed {first_progress['delta_count']} delta(s). See {LOG_PATH} for server logs."
                )
            time.sleep(0.1)
        count_at_steer_time = first_progress["delta_count"]
        print(f"      turn 1 text deltas observed before steering: {count_at_steer_time}")

        print(f"[4/5] Sending the steering turn (new target={args.second_target})...")
        second_payload = {
            "input": f"Actually, count down from {args.second_target} instead.",
            "store": True,
            "background": True,
            "stream": False,
            "previous_response_id": first_id,
        }
        # Forward the session id turn 1 was assigned so this turn resolves to the same
        # conversation chain and is queued as a steer instead of starting a fresh task.
        if "session_id" in first_progress:
            second_payload["agent_session_id"] = first_progress["session_id"]
        status, body = _http_post("/responses", second_payload)
        if status != 200 or body.get("status") != "queued":
            raise SystemExit(f"FAIL: expected an immediate queued response for the steering turn, got: {body}")
        second_id = body["id"]
        print(f"      steering turn accepted immediately as queued; response id: {second_id}")

        print("[5/5] Watching turn 1 end early and the steered turn complete...")
        first_progress["done"].wait(timeout=120)
        first_final = _http_get(f"/responses/{first_id}")[1]
        second_final = _poll_until_terminal(second_id, timeout=60)
    finally:
        _kill(server)
        log_file.close()

    first_text = _extract_output_text(first_final.get("output", []))
    second_text = _extract_output_text(second_final.get("output", []))

    print(f"      turn 1 final status: {first_final['status']}, {len(first_text)} character(s): {first_text}")
    print(f"      turn 2 final status: {second_final['status']}, {len(second_text)} character(s): {second_text}")

    if "Serving steered turn" in LOG_PATH.read_text(encoding="utf-8"):
        print("      confirmed 'Serving steered turn' in the server log.")

    if first_final["status"] != "completed":
        raise SystemExit(
            f"FAIL: turn 1 did not complete; last status: {first_final['status']}. See {LOG_PATH} for server logs."
        )
    # Loose bound: a steered turn 1 should have generated only a bit more than what we observed
    # right before steering, not a whole additional full run's worth of tokens.
    if first_progress["delta_count"] > count_at_steer_time * 3 + 20:
        raise SystemExit(
            "FAIL: turn 1 kept streaming long after the steering turn was sent -- steering did not "
            f"cancel it in time. See {LOG_PATH} for server logs."
        )

    if second_final["status"] != "completed":
        raise SystemExit(
            f"FAIL: turn 2 did not complete; last status: {second_final['status']}. See {LOG_PATH} for server logs."
        )
    # Weak ordering check: each number from the new target down to 1 must appear, in order.
    search_from = 0
    for n in range(args.second_target, 0, -1):
        idx = second_text.find(str(n), search_from)
        if idx == -1:
            raise SystemExit(
                f"FAIL: steered turn output is missing '{n}' in order.\n  got: {second_text!r}\n"
                f"See {LOG_PATH} for server logs."
            )
        search_from = idx + 1

    print("PASS: the steering turn cancelled the in-progress countdown early and completed its own countdown.")


if __name__ == "__main__":
    main()
