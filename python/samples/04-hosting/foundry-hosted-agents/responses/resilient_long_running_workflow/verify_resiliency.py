# Copyright (c) Microsoft. All rights reserved.

"""End-to-end crash-recovery test for the resilient countdown workflow sample.

Starts the server, kicks off a background countdown, force-kills the server mid-countdown to
simulate a real crash, clears the stale Windows stream lock file, restarts the server, and
verifies the countdown resumes and completes with the exact expected output (no loss, no
duplication). Requires the same environment (.env) as running main.py directly.

Usage:
    python verify_resiliency.py [--target N] [--crash-after-count N]
"""

import argparse
import json
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
LOG_PATH = SAMPLE_DIR / "verify_resiliency.log"


def _http_get(path: str, timeout: float = 5.0) -> tuple[int, dict[str, Any]]:
    with urllib.request.urlopen(urllib.request.Request(f"{BASE_URL}{path}"), timeout=timeout) as resp:
        return resp.status, json.loads(resp.read())


def _start_server(log_file: IO[str]) -> subprocess.Popen:  # type: ignore
    return subprocess.Popen([sys.executable, "main.py"], cwd=SAMPLE_DIR, stdout=log_file, stderr=subprocess.STDOUT)


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
    # Popen.kill() maps to TerminateProcess on Windows -- an ungraceful hard kill, just like a real crash.
    if server.poll() is None:
        server.kill()
        server.wait(timeout=10)


def _clear_stale_stream_lock(response_id: str) -> None:
    # On Windows, the local stream store falls back to a plain lock *file* (no `fcntl`), which isn't
    # cleaned up when the process is force-killed. If restart fails with `another process holds the
    # lock-file on ...jsonl`, delete the stale `<response-id>.jsonl.lock` file under
    lock_path = Path.home() / ".agentserver" / "streams" / f"{response_id}.jsonl.lock"
    if not lock_path.exists():
        return
    # Windows may not release the killed process's file handle immediately; retry briefly.
    for attempt in range(10):
        try:
            lock_path.unlink()
            print(f"      removed stale lock file: {lock_path}")
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.5)


def _create_streaming_background_response(payload: dict[str, Any], progress: dict[str, Any]) -> None:
    """POST a streaming background create-response request and track its progress.

    Background responses only expose incremental output over SSE when the *creation*
    request itself sets ``stream=true`` (``ResponseExecution.replay_enabled`` requires it);
    a plain (non-streaming) GET only ever reflects the initial (empty output) or terminal
    (full output) snapshot, never anything in between. So the create call itself must be
    the streaming one, and its own response body is read here as the progress feed.
    """
    data = json.dumps({**payload, "stream": True}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/responses", data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request) as resp:
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
                elif current_event == "response.output_item.done":
                    progress["count"] += 1
                    for part in data_obj.get("item", {}).get("content", []):
                        if part.get("type") == "output_text":
                            print(f"      output item {progress['count']}: {part['text']!r}")
    except urllib.error.HTTPError as exc:
        progress["error"] = f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}"
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        progress["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        progress["ready"].set()  # Unblock a waiter even if response.created never arrived.


def _watch_recovery_progress(response_id: str, progress: dict[str, Any]) -> None:
    """Replay the response's SSE stream after recovery and print each item as it arrives.

    ``starting_after`` is omitted, so the replay starts from the beginning of the retained
    history -- pre-crash items are reprinted, then live items follow as the recovered
    workflow produces them.
    """
    url = f"{BASE_URL}/responses/{response_id}?stream=true"
    try:
        with urllib.request.urlopen(url) as resp:
            current_event: str | None = None
            for raw_line in resp:
                line = raw_line.decode("utf-8").rstrip("\n")
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data_obj = json.loads(line[len("data:") :].strip())
                if current_event == "response.output_item.done":
                    progress["count"] += 1
                    for part in data_obj.get("item", {}).get("content", []):
                        if part.get("type") == "output_text":
                            print(f"      output item {progress['count']}: {part['text']!r}")
                elif current_event in ("response.completed", "response.failed", "response.incomplete"):
                    progress["done"].set()
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        pass  # Connection drops when the server crashes or exits; the caller already knows.
    finally:
        progress["done"].set()


def _extract_message_texts(output_items: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for item in output_items:
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                texts.append(part["text"])
    return texts


def _clear_stale_state() -> None:
    """Wipe ~/.agentserver so a prior run's incomplete response is never auto-recovered
    on startup and left competing with this run's request for the event loop.
    """
    state_root = Path.home() / ".agentserver"
    if state_root.exists():
        shutil.rmtree(state_root, ignore_errors=True)
        print(f"      cleared stale state: {state_root}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=20, help="Countdown starting value.")
    args = parser.parse_args()

    crash_after_count = args.target // 2
    expected_texts = [str(n) for n in range(args.target, 0, -1)] + ["Countdown complete."]

    _clear_stale_state()

    log_file = LOG_PATH.open("w", encoding="utf-8")
    print(f"Server logs (DEBUG level) are redirected to {LOG_PATH}.")

    print(f"[1/6] Starting server (target={args.target})...")
    server = _start_server(log_file)  # type: ignore
    print(f"      PID: {server.pid}")
    try:
        _wait_for_ready()

        print("[2/6] Starting background countdown...")
        progress: dict[str, Any] = {"count": 0, "ready": threading.Event()}
        watcher = threading.Thread(
            target=_create_streaming_background_response,
            args=({"input": f"Count down from {args.target}", "store": True, "background": True}, progress),
            daemon=True,
        )
        watcher.start()
        if not progress["ready"].wait(timeout=60):
            raise SystemExit("FAIL: did not receive response.created in time.")
        if "id" not in progress:
            raise SystemExit(f"FAIL: streaming create request failed: {progress.get('error', 'unknown error')}")
        response_id = progress["id"]
        print(f"      response id: {response_id}, status: {progress['status']}")

        print(f"[3/6] Waiting for the countdown to reach {crash_after_count} completed item(s)...")
        while progress["count"] < crash_after_count:
            time.sleep(0.5)
        print(f"      output items observed via SSE before crash: {progress['count']}")

        print("[4/6] Force-killing the server (simulated crash)...")
    finally:
        _kill(server)

    _clear_stale_stream_lock(response_id)

    print("[5/6] Restarting the server...")
    server = _start_server(log_file)  # type: ignore
    print(f"      PID: {server.pid}")
    try:
        _wait_for_ready()

        print("[6/6] Waiting for the recovered countdown to complete...")
        recovery: dict[str, Any] = {"count": 0, "done": threading.Event()}
        recovery_watcher = threading.Thread(target=_watch_recovery_progress, args=(response_id, recovery), daemon=True)
        recovery_watcher.start()
        recovery["done"].wait(timeout=args.target * 2 + 30)
        final = _http_get(f"/responses/{response_id}")[1]
    finally:
        _kill(server)
        log_file.close()

    if final["status"] != "completed":
        raise SystemExit(
            f"FAIL: response did not complete in time; last status: {final['status']}. See {LOG_PATH} for server logs."
        )

    texts = _extract_message_texts(final.get("output", []))
    print(f"      final status: {final['status']}, output items: {len(final['output'])}")
    if texts != expected_texts:
        raise SystemExit(
            f"FAIL: recovered output mismatch.\n  expected: {expected_texts}\n  got:      {texts}\n"
            f"See {LOG_PATH} for server logs."
        )

    print("PASS: countdown crashed mid-flight and recovered with no lost or duplicated output.")


if __name__ == "__main__":
    main()
