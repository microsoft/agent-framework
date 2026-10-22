# Copyright (c) Microsoft. All rights reserved.

"""Browser-based regression test for DevUI streaming memory growth."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import http.client
import io
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    Message,
    ResponseStream,
)
from websockets.asyncio.client import connect as websocket_connect

from agent_framework_devui import DevServer

_BROWSER_COMMANDS = (
    "chrome",
    "chrome.exe",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "msedge",
    "msedge.exe",
)
_BROWSER_ENV_VARS = ("DEVUI_TEST_BROWSER", "CHROME_BIN", "BROWSER_BIN")
_WINDOWS_PROCESS_QUERY = """
$rows = @(
    Get-CimInstance Win32_Process | ForEach-Object {
        if (-not $_.CommandLine) {
            return
        }

        try {
            $process = Get-Process -Id $_.ProcessId -ErrorAction Stop
            [PSCustomObject]@{
                pid = [int]$_.ProcessId
                parent_pid = [int]$_.ParentProcessId
                rss_kb = [int][Math]::Round($process.WorkingSet64 / 1KB)
                command = [string]$_.CommandLine
            }
        }
        catch {
        }
    }
)

$rows | ConvertTo-Json -Compress
""".strip()

_STREAM_CHUNK_COUNT = 12_000
_STREAM_CHUNK_SIZE = 128
_POST_SEND_DELAY_S = 1.0
_SAMPLE_INTERVAL_S = 0.5
_SAMPLE_WINDOW_S = 12.0
_MAX_RENDERER_GROWTH_MB = 500.0
_MAX_STREAMING_STATE_STORAGE_BYTES = 64 * 1024
_MAX_DEBUG_EVENT_DOM_ITEMS = 1000


@dataclass(frozen=True)
class _BrowserProcessRow:
    pid: int
    parent_pid: int
    rss_kb: int
    command: str


@dataclass(frozen=True)
class _BrowserMemoryProbe:
    streaming_state_storage_bytes: int
    debug_event_dom_items: int
    js_heap_bytes: int | None


class MemoryStressAgent(BaseAgent):
    """Agent that emits many small streaming chunks."""

    def __init__(self, *, chunk_count: int, chunk_size: int, delay_ms: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._chunk_count = chunk_count
        self._chunk_size = max(chunk_size, 24)
        self._delay_s = max(delay_ms, 0.0) / 1000.0

    def run(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        del messages, session, kwargs
        if stream:
            return self._run_stream()
        return self._run()

    async def _run(self) -> AgentResponse:
        text = "".join(self._make_chunk(index) for index in range(self._chunk_count))
        return AgentResponse(messages=[Message("assistant", [Content.from_text(text=text)])])

    def _run_stream(self) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        async def _iter() -> AsyncIterable[AgentResponseUpdate]:
            for index in range(self._chunk_count):
                yield AgentResponseUpdate(
                    contents=[Content.from_text(text=self._make_chunk(index))],
                    role="assistant",
                )
                if self._delay_s:
                    await asyncio.sleep(self._delay_s)

        return ResponseStream(_iter(), finalizer=AgentResponse.from_updates)

    def _make_chunk(self, index: int) -> str:
        prefix = f"[{index:06d}] "
        payload_size = max(self._chunk_size - len(prefix), 1)
        payload = ("x" * (payload_size - 1)) + ("\n" if index % 8 == 7 else " ")
        return prefix + payload


class _CDPClient:
    """Minimal Chrome DevTools Protocol client for a single attached page."""

    def __init__(self, websocket: Any) -> None:
        self._websocket = websocket
        self._next_id = 0

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self._next_id += 1
        command_id = self._next_id
        payload: dict[str, Any] = {"id": command_id, "method": method}
        if params is not None:
            payload["params"] = params
        if session_id is not None:
            payload["sessionId"] = session_id

        await self._websocket.send(json.dumps(payload))

        while True:
            raw_message = await self._websocket.recv()
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")

            message = json.loads(raw_message)
            if message.get("id") != command_id:
                continue

            error = message.get("error")
            if isinstance(error, dict):
                raise RuntimeError(f"CDP command {method} failed: {error}")

            result = message.get("result")
            return result if isinstance(result, dict) else {}

    async def evaluate(self, expression: str, *, session_id: str) -> Any:
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
            session_id=session_id,
        )
        remote_result = result.get("result")
        if isinstance(remote_result, dict):
            return remote_result.get("value")
        return None


def _get_browser_candidates() -> tuple[Path, ...]:
    if sys.platform == "darwin":
        return (
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        )

    if sys.platform == "win32":
        windows_bases: list[Path] = []
        for env_var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            raw_value = os.environ.get(env_var)
            if raw_value:
                windows_bases.append(Path(raw_value))

        return tuple(
            dict.fromkeys(
                [base / "Microsoft/Edge/Application/msedge.exe" for base in windows_bases]
                + [base / "Google/Chrome/Application/chrome.exe" for base in windows_bases]
                + [base / "Chromium/Application/chrome.exe" for base in windows_bases]
            )
        )

    return (
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/usr/bin/microsoft-edge"),
        Path("/opt/google/chrome/chrome"),
        Path("/opt/microsoft/msedge/msedge"),
        Path("/snap/bin/chromium"),
    )


def _find_browser_executable() -> Path | None:
    for env_var in _BROWSER_ENV_VARS:
        configured_path = os.environ.get(env_var)
        if not configured_path:
            continue

        candidate = Path(configured_path).expanduser()
        if candidate.exists():
            return candidate

    for candidate in _get_browser_candidates():
        if candidate.exists():
            return candidate

    for command in _BROWSER_COMMANDS:
        resolved = shutil.which(command)
        if resolved is not None:
            return Path(resolved)

    return None


def _find_available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _get_json_response(*, host: str, port: int, path: str) -> dict[str, Any]:
    connection = http.client.HTTPConnection(host, port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"Request to {path} failed with status {response.status}")
        payload = response.read().decode("utf-8")
    finally:
        connection.close()

    data = json.loads(payload)
    if isinstance(data, dict):
        return data
    raise RuntimeError(f"Expected JSON object from {path}, got: {type(data).__name__}")


async def _get_devtools_websocket_url(port: int) -> str:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        with contextlib.suppress(Exception):
            version_data = _get_json_response(host="127.0.0.1", port=port, path="/json/version")
            websocket_url = version_data.get("webSocketDebuggerUrl")
            if isinstance(websocket_url, str) and websocket_url:
                return websocket_url
        await asyncio.sleep(0.1)

    raise RuntimeError(f"Timed out waiting for DevTools on port {port}")


def _wait_for_server_details(server_instance: uvicorn.Server) -> tuple[int, str]:
    deadline = time.monotonic() + 10.0
    actual_port: int | None = None

    while time.monotonic() < deadline:
        if hasattr(server_instance, "servers") and server_instance.servers:
            for uvicorn_server in server_instance.servers:
                sockets = getattr(uvicorn_server, "sockets", None)
                if not sockets:
                    continue
                actual_port = int(sockets[0].getsockname()[1])
                break

        if actual_port is not None:
            with contextlib.suppress(Exception):
                health = _get_json_response(host="127.0.0.1", port=actual_port, path="/health")
                if health.get("status") == "healthy":
                    entities = _get_json_response(host="127.0.0.1", port=actual_port, path="/v1/entities")
                    entity_list = entities.get("entities")
                    if isinstance(entity_list, list) and entity_list:
                        entity = entity_list[0]
                        if isinstance(entity, dict) and isinstance(entity.get("id"), str):
                            return actual_port, entity["id"]
        time.sleep(0.1)

    raise RuntimeError("Timed out waiting for DevUI server startup")


def _parse_posix_process_rows(output: str) -> list[_BrowserProcessRow]:
    rows: list[_BrowserProcessRow] = []
    for line in output.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) != 4:
            continue

        pid_text, parent_pid_text, rss_text, command = parts
        with contextlib.suppress(ValueError):
            rows.append(
                _BrowserProcessRow(
                    pid=int(pid_text),
                    parent_pid=int(parent_pid_text),
                    rss_kb=int(rss_text),
                    command=command,
                )
            )

    return rows


def _parse_windows_process_rows(output: str) -> list[_BrowserProcessRow]:
    text = output.strip()
    if not text:
        return []

    payload = json.loads(text)
    items = payload if isinstance(payload, list) else [payload]

    rows: list[_BrowserProcessRow] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        pid = item.get("pid")
        parent_pid = item.get("parent_pid")
        rss_kb = item.get("rss_kb")
        command = item.get("command")
        if not isinstance(pid, int) or not isinstance(parent_pid, int) or not isinstance(rss_kb, int):
            continue
        if not isinstance(command, str):
            continue

        rows.append(
            _BrowserProcessRow(
                pid=pid,
                parent_pid=parent_pid,
                rss_kb=rss_kb,
                command=command,
            )
        )

    return rows


def _read_process_rows() -> list[_BrowserProcessRow]:
    if sys.platform == "win32":
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _WINDOWS_PROCESS_QUERY],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        return _parse_windows_process_rows(result.stdout)

    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,rss=,command="],
        capture_output=True,
        text=True,
        check=True,
    )
    return _parse_posix_process_rows(result.stdout)


def _collect_process_tree(root_pids: set[int], process_rows: list[_BrowserProcessRow]) -> list[_BrowserProcessRow]:
    process_by_pid = {row.pid: row for row in process_rows}
    child_pids_by_parent: dict[int, list[int]] = {}
    for row in process_rows:
        child_pids_by_parent.setdefault(row.parent_pid, []).append(row.pid)

    collected_rows: list[_BrowserProcessRow] = []
    seen_pids: set[int] = set()
    pending_pids = list(root_pids)

    while pending_pids:
        pid = pending_pids.pop()
        if pid in seen_pids:
            continue

        seen_pids.add(pid)
        process_row = process_by_pid.get(pid)
        if process_row is None:
            continue

        collected_rows.append(process_row)
        pending_pids.extend(child_pids_by_parent.get(pid, []))

    return collected_rows


def _collect_browser_process_rows(root_pid: int, profile_dir: str) -> list[_BrowserProcessRow]:
    process_rows = _read_process_rows()
    normalized_profile_dir = profile_dir.casefold()
    matched_root_pids = {row.pid for row in process_rows if normalized_profile_dir in row.command.casefold()}
    matched_root_pids.add(root_pid)
    return _collect_process_tree(matched_root_pids, process_rows)


def _sample_peak_renderer_rss_mb(root_pid: int, profile_dir: str) -> float:
    renderer_rss_kb = [
        row.rss_kb
        for row in _collect_browser_process_rows(root_pid, profile_dir)
        if "--type=renderer" in row.command.casefold()
    ]
    return round((max(renderer_rss_kb, default=0)) / 1024, 2)


async def _sample_browser_memory_probe(client: _CDPClient, *, session_id: str) -> _BrowserMemoryProbe:
    value = await client.evaluate(
        """
        (() => {
          const storagePrefix = "devui_streaming_state_";
          const textEncoder = new TextEncoder();
          let streamingStateStorageBytes = 0;
          for (let index = 0; index < localStorage.length; index += 1) {
            const key = localStorage.key(index);
            if (!key || !key.startsWith(storagePrefix)) {
              continue;
            }

            const item = localStorage.getItem(key) || "";
            streamingStateStorageBytes += textEncoder.encode(key).length + textEncoder.encode(item).length;
          }

          return {
            streamingStateStorageBytes,
            debugEventDomItems: document.querySelectorAll("[data-devui-debug-event]").length,
            jsHeapBytes: performance.memory ? performance.memory.usedJSHeapSize : null,
          };
        })()
        """,
        session_id=session_id,
    )
    if not isinstance(value, dict):
        raise AssertionError(f"Expected browser memory probe object, got: {type(value).__name__}")

    streaming_state_storage_bytes = value.get("streamingStateStorageBytes")
    debug_event_dom_items = value.get("debugEventDomItems")
    js_heap_bytes = value.get("jsHeapBytes")
    if not isinstance(streaming_state_storage_bytes, int):
        raise AssertionError("Browser memory probe did not return streamingStateStorageBytes")
    if not isinstance(debug_event_dom_items, int):
        raise AssertionError("Browser memory probe did not return debugEventDomItems")
    if js_heap_bytes is not None and not isinstance(js_heap_bytes, int):
        raise AssertionError("Browser memory probe returned invalid jsHeapBytes")

    return _BrowserMemoryProbe(
        streaming_state_storage_bytes=streaming_state_storage_bytes,
        debug_event_dom_items=debug_event_dom_items,
        js_heap_bytes=js_heap_bytes,
    )


def _terminate_browser_processes(root_pid: int, profile_dir: str) -> None:
    browser_rows = _collect_browser_process_rows(root_pid, profile_dir)
    browser_pids = sorted({row.pid for row in browser_rows} | {root_pid}, reverse=True)

    if sys.platform == "win32":
        for pid in browser_pids:
            with contextlib.suppress(subprocess.CalledProcessError):
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
        return

    for pid in browser_pids:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)


def _launch_browser_process(*, browser_path: Path, debug_port: int, profile_dir: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            str(browser_path),
            "--headless=new",
            f"--remote-debugging-port={debug_port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-renderer-backgrounding",
            "--hide-scrollbars",
            "--mute-audio",
            "--enable-precise-memory-info",
            "--no-sandbox",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _shutdown_browser_process(browser_process: subprocess.Popen[str], *, profile_dir: str) -> None:
    with contextlib.suppress(Exception):
        browser_process.terminate()
        browser_process.wait(timeout=5)
    _terminate_browser_processes(browser_process.pid, profile_dir)


def test_parse_posix_process_rows() -> None:
    output = """
      101 1 2048 /usr/bin/google-chrome --user-data-dir=/tmp/devui-memory
      202 101 4096 /usr/bin/google-chrome --type=renderer --lang=en-US
    """.strip()

    assert _parse_posix_process_rows(output) == [
        _BrowserProcessRow(
            pid=101,
            parent_pid=1,
            rss_kb=2048,
            command="/usr/bin/google-chrome --user-data-dir=/tmp/devui-memory",
        ),
        _BrowserProcessRow(
            pid=202,
            parent_pid=101,
            rss_kb=4096,
            command="/usr/bin/google-chrome --type=renderer --lang=en-US",
        ),
    ]


def test_parse_windows_process_rows() -> None:
    output = json.dumps([
        {
            "pid": 301,
            "parent_pid": 1,
            "rss_kb": 2048,
            "command": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        },
        {
            "pid": 302,
            "parent_pid": 301,
            "rss_kb": 6144,
            "command": r"C:\Program Files\Google\Chrome\Application\chrome.exe --type=renderer",
        },
    ])

    assert _parse_windows_process_rows(output) == [
        _BrowserProcessRow(
            pid=301,
            parent_pid=1,
            rss_kb=2048,
            command=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ),
        _BrowserProcessRow(
            pid=302,
            parent_pid=301,
            rss_kb=6144,
            command=r"C:\Program Files\Google\Chrome\Application\chrome.exe --type=renderer",
        ),
    ]


def test_sample_peak_renderer_rss_mb_uses_browser_process_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_dir = "/tmp/devui-memory-browser"
    process_rows = [
        _BrowserProcessRow(
            pid=101,
            parent_pid=1,
            rss_kb=1024,
            command="/usr/bin/google-chrome",
        ),
        _BrowserProcessRow(
            pid=102,
            parent_pid=101,
            rss_kb=4096,
            command="/usr/bin/google-chrome --type=renderer",
        ),
        _BrowserProcessRow(
            pid=201,
            parent_pid=1,
            rss_kb=2048,
            command=f"/usr/bin/google-chrome --user-data-dir={profile_dir}",
        ),
        _BrowserProcessRow(
            pid=202,
            parent_pid=201,
            rss_kb=8192,
            command="/usr/bin/google-chrome --type=renderer",
        ),
        _BrowserProcessRow(
            pid=999,
            parent_pid=1,
            rss_kb=32768,
            command="/usr/bin/google-chrome --type=renderer",
        ),
    ]

    monkeypatch.setattr(sys.modules[__name__], "_read_process_rows", lambda: process_rows)

    assert _sample_peak_renderer_rss_mb(101, profile_dir) == 8.0


@pytest.fixture
def memory_regression_server() -> Generator[tuple[str, str]]:
    """Start DevUI with a synthetic streaming agent and yield the base URL plus entity ID."""

    server = DevServer(host="127.0.0.1", port=0, auth_enabled=False)
    server.register_entities([
        MemoryStressAgent(
            id="memory-stream-agent",
            name="MemoryStreamAgent",
            description="Streams many small chunks for UI memory profiling.",
            chunk_count=_STREAM_CHUNK_COUNT,
            chunk_size=_STREAM_CHUNK_SIZE,
            delay_ms=1.0,
        )
    ])

    app = server.get_app()
    server_config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=0,
        log_level="error",
        ws="none",
    )
    server_instance = uvicorn.Server(server_config)

    def run_server() -> None:
        asyncio.run(server_instance.serve())

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    actual_port, entity_id = _wait_for_server_details(server_instance)
    yield f"http://127.0.0.1:{actual_port}", entity_id

    with contextlib.suppress(Exception):
        server_instance.should_exit = True
    server_thread.join(timeout=5)


async def _wait_for_expression(
    client: _CDPClient,
    *,
    session_id: str,
    expression: str,
    timeout_s: float,
) -> Any:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = await client.evaluate(expression, session_id=session_id)
        if value:
            return value
        await asyncio.sleep(0.1)

    raise AssertionError(f"Timed out waiting for expression: {expression}")


@pytest.fixture
async def audio_browser(memory_regression_server: tuple[str, str]) -> AsyncGenerator[tuple[_CDPClient, str]]:
    """Open the bundled chat UI with mocked microphone hardware and HTTP responses."""
    browser_path = _find_browser_executable()
    if browser_path is None:
        pytest.skip("No Chromium-based browser found for DevUI audio tests")
    base_url, entity_id = memory_regression_server
    debug_port = _find_available_port()
    with tempfile.TemporaryDirectory(prefix="devui-audio-browser-") as profile_dir:
        process = _launch_browser_process(browser_path=browser_path, debug_port=debug_port, profile_dir=profile_dir)
        try:
            websocket_url = await _get_devtools_websocket_url(debug_port)
            async with websocket_connect(websocket_url, max_size=None) as websocket:
                client = _CDPClient(websocket)
                target = await client.send("Target.createTarget", {"url": "about:blank"})
                attached = await client.send("Target.attachToTarget", {"targetId": target["targetId"], "flatten": True})
                session_id = attached["sessionId"]
                await client.send("Page.enable", session_id=session_id)
                await client.send(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {
                        "source": """
                        localStorage.setItem("devui-storage", JSON.stringify({
                          state: { audioInput: { enabled: true, autoPlayAgentAudio: false } }, version: 0,
                        }));
                        """
                    },
                    session_id=session_id,
                )
                await client.send("Page.navigate", {"url": f"{base_url}/?entity_id={entity_id}"}, session_id=session_id)
                await _wait_for_expression(
                    client,
                    session_id=session_id,
                    expression="""!!document.querySelector(
                      'button[aria-label="Record audio"], button[aria-label^="Click to record"]'
                    )""",
                    timeout_s=30,
                )
                await client.evaluate(
                    """
                  window.audioProbe = { stopped: 0, urls: 0, revoked: 0, requests: [] };
                  const probe = window.audioProbe;
                  const NativeRecorder = window.MediaRecorder;
                  const NativeContext = window.AudioContext;
                  probe.useNative = async () => {
                    window.MediaRecorder = NativeRecorder;
                    window.AudioContext = NativeContext;
                    const context = new NativeContext();
                    const oscillator = context.createOscillator();
                    const destination = context.createMediaStreamDestination();
                    oscillator.frequency.value = 440;
                    oscillator.connect(destination);
                    oscillator.start();
                    await context.resume();
                    for (const track of destination.stream.getTracks()) {
                      const stop = track.stop.bind(track);
                      track.stop = () => { probe.stopped++; stop(); void context.close(); };
                    }
                    navigator.mediaDevices.getUserMedia = async () => destination.stream;
                  };
                  const stream = { getTracks: () => [{ stop: () => probe.stopped++ }] };
                  navigator.mediaDevices.getUserMedia = () => probe.mode === "permission"
                    ? new Promise(resolve => { probe.allow = () => resolve(stream); })
                    : Promise.resolve(stream);
                  window.MediaRecorder = class {
                    static isTypeSupported() { return true; }
                    constructor() {
                      if (probe.mode === "constructor") throw new Error("Recorder unavailable");
                      this.state = "inactive";
                    }
                    start() { this.state = "recording"; }
                    stop() {
                      this.state = "inactive";
                      this.ondataavailable({ data: new Blob(["recorded audio"]) });
                      this.onstop();
                    }
                  };
                  window.AudioContext = class {
                    createMediaStreamSource() { return { connect() {} }; }
                    createAnalyser() {
                      return { fftSize: 256, getByteTimeDomainData: data => data.fill(probe.quiet ? 128 : 180) };
                    }
                    decodeAudioData() {
                      const audio = new AudioBuffer({ length: 16000, sampleRate: 16000, numberOfChannels: 1 });
                      audio.getChannelData(0).fill(0.5);
                      return probe.mode === "processing"
                        ? new Promise(resolve => { probe.decode = () => resolve(audio); })
                        : Promise.resolve(audio);
                    }
                    close() { return Promise.resolve(); }
                  };
                  const createURL = URL.createObjectURL.bind(URL);
                  URL.createObjectURL = blob => { probe.urls++; return createURL(blob); };
                  const revokeURL = URL.revokeObjectURL.bind(URL);
                  URL.revokeObjectURL = url => { probe.revoked++; revokeURL(url); };
                  const fetchOriginal = window.fetch.bind(window);
                  window.fetch = (url, options) => {
                    if (String(url).endsWith("/v1/responses") && options?.method === "POST") {
                      probe.requests.push(JSON.parse(options.body));
                      const audio = probe.requests.at(-1).input[0].content.find(c => c.type === "input_audio");
                      const audioUrl = audio ? `data:audio/wav;base64,${audio.input_audio.data}` : undefined;
                      const output = audio ? [
                        {
                          id: "audio-reply-text", type: "message", role: "assistant", status: "completed",
                          content: [{
                            type: "output_text", annotations: [],
                            text: "This is a spoken response with accompanying text " +
                              "that should share the same left edge as its audio player.",
                          }],
                        },
                        {
                          id: "audio-reply", type: "output_file", filename: "reply.wav",
                          mime_type: "audio/wav",
                          file_url: ["base64", "data-uri"].includes(probe.replySource)
                            ? "/expired-audio.wav" : audioUrl,
                          file_data: probe.replySource === "base64" ? audio.input_audio.data
                            : probe.replySource === "data-uri" ? audioUrl : undefined,
                        },
                      ] : [];
                      const event = { type: "response.completed", response: { id: "audio-test", output } };
                      const events = audio ? [{
                        type: "response.output_text.delta", item_id: "audio-reply-text",
                        output_index: 0, content_index: 0, sequence_number: 1, delta: output[0].content[0].text,
                      }, event] : [event];
                      const body = events.map(value => `data: ${JSON.stringify(value)}\\n\\n`).join("");
                      return Promise.resolve(new Response(`${body}data: [DONE]\\n\\n`,
                        { headers: { "Content-Type": "text/event-stream" } }));
                    }
                    return fetchOriginal(url, options);
                  };
                """,
                    session_id=session_id,
                )
                yield client, session_id
        finally:
            _shutdown_browser_process(process, profile_dir=profile_dir)


@pytest.mark.parametrize(
    ("scenario", "reply_source"),
    [
        ("constructor", "url-only"),
        ("permission", "url-only"),
        ("processing", "url-only"),
        ("success", "url-only"),
        ("native", "url-only"),
        ("uploads", "url-only"),
        ("success", "base64"),
        ("success", "data-uri"),
    ],
)
async def test_audio_input_lifecycle_and_uploads(
    audio_browser: tuple[_CDPClient, str], scenario: str, reply_source: str
) -> None:
    """Microphone failures/cancellation release resources, while recordings and generic uploads keep their contracts."""
    client, session_id = audio_browser

    async def evaluate(expression: str) -> Any:
        return await client.evaluate(expression, session_id=session_id)

    async def wait(expression: str) -> Any:
        return await _wait_for_expression(client, session_id=session_id, expression=expression, timeout_s=10)

    await evaluate(
        f"window.audioProbe.mode = {json.dumps(scenario)}; window.audioProbe.replySource = {json.dumps(reply_source)}"
    )
    if scenario == "native":
        await client.send(
            "Runtime.evaluate",
            {"expression": "window.audioProbe.useNative()", "awaitPromise": True, "userGesture": True},
            session_id=session_id,
        )
    if scenario == "uploads":
        await evaluate("""
          const transfer = new DataTransfer();
          transfer.items.add(new File(["m4a"], "first.m4a", { type: "audio/mp4" }));
          transfer.items.add(new File(["ogg"], "second.ogg", { type: "audio/ogg" }));
          const input = document.querySelector('input[type="file"]');
          input.files = transfer.files;
          input.dispatchEvent(new Event("change", { bubbles: true }));
        """)
        await wait('document.body.textContent.includes("second.ogg")')
    else:
        await evaluate("""
          document.querySelector(
            'button[aria-label="Record audio"], button[aria-label^="Click to record"]'
          ).click()
        """)
        if scenario == "constructor":
            await wait('document.querySelector(\'[role="alert"]\')?.textContent.includes("Recorder unavailable")')
        elif scenario == "permission":
            await wait('document.body.textContent.includes("Preparing microphone")')
            await evaluate("""
              const textarea = document.querySelector("textarea");
              Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(textarea, "Wait");
              textarea.dispatchEvent(new Event("input", { bubbles: true }));
            """)
            await wait('document.querySelector("textarea").value === "Wait"')
            await evaluate("""
              document.querySelector("textarea").dispatchEvent(new KeyboardEvent("keydown", {
                key: "Enter", bubbles: true, cancelable: true,
              }));
              [...document.querySelectorAll("button")].find(b => b.textContent === "Cancel recording").click();
              window.audioProbe.allow();
            """)
        else:
            await wait("!!document.querySelector('button[aria-label=\"Stop recording\"]')")
            if scenario == "native":
                await wait('document.querySelector(\'[aria-label="Recording duration"]\')?.textContent === "0:01"')
            presentation = await evaluate("""
              (() => {
                const stop = document.querySelector('button[aria-label="Stop recording"]');
                const canvas = document.createElement("canvas");
                const context = canvas.getContext("2d");
                context.fillStyle = getComputedStyle(stop).backgroundColor;
                context.fillRect(0, 0, 1, 1);
                const [red, green, blue] = context.getImageData(0, 0, 1, 1).data;
                return { violet: red > green && blue > green,
                  rounded: parseFloat(getComputedStyle(stop.parentElement).borderRadius) > 20 };
              })()
            """)
            assert presentation == {"violet": True, "rounded": True}
            await evaluate("document.querySelector('button[aria-label=\"Stop recording\"]').click()")
            if scenario == "processing":
                await wait('typeof window.audioProbe.decode === "function"')
                await evaluate("""
                  [...document.querySelectorAll("button")].find(b => b.textContent === "Cancel recording").click();
                  window.audioProbe.decode();
                """)
            else:
                await wait("!!document.querySelector('audio[aria-label=\"Voice recording preview\"]')")
                assert await evaluate("!!document.querySelector('input[aria-label=\"Audio playback position\"]')")
                assert await evaluate("!!document.querySelector('button[aria-label=\"Play recording preview\"]')")
                header = await evaluate("""
                  (async () => {
                    const blob = await (await fetch(document.querySelector("audio").src)).arrayBuffer();
                    const view = new DataView(blob);
                    return [new TextDecoder().decode(blob.slice(0, 4)), view.getUint16(22, true),
                      view.getUint32(24, true), view.getInt16(44, true)];
                  })()
                """)
                assert header[:3] == ["RIFF", 1, 16000]
                if scenario == "success":
                    assert header[3] == 16383

        await wait("window.audioProbe.stopped === 1")
        if scenario not in {"success", "native"}:
            await evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            assert await evaluate("window.audioProbe.urls") == 0
            assert await evaluate("window.audioProbe.requests.length") == 0
            assert not await evaluate("!!document.querySelector('audio[aria-label=\"Voice recording preview\"]')")
            return

    await wait("!document.querySelector('button[aria-label=\"Send message\"]').disabled")
    if scenario == "native":
        await evaluate("""
          window.AudioContext = class {
            constructor() { throw new Error("Waveform decoding unavailable"); }
          };
        """)
    await evaluate("document.querySelector('button[aria-label=\"Send message\"]').click()")
    request = await wait("window.audioProbe.requests[0]")
    content = request["input"][0]["content"]
    assert [part["type"] for part in content] == (
        ["input_file", "input_file"] if scenario == "uploads" else ["input_audio"]
    )
    if scenario == "uploads":
        assert [part["filename"] for part in content] == ["first.m4a", "second.ogg"]
    else:
        assert content[0]["input_audio"]["format"] == "wav"
        if scenario == "native":
            wav_bytes = base64.b64decode(content[0]["input_audio"]["data"])
            with wave.open(io.BytesIO(wav_bytes), "rb") as recording:
                assert recording.getnchannels() == 1
                assert recording.getframerate() == 16000
                assert recording.getnframes() > 8000
                samples = recording.readframes(recording.getnframes())
            assert max(abs(sample[0]) for sample in struct.iter_unpack("<h", samples)) > 1000

        await wait('document.body.textContent.includes("reply.wav")')
        player = "document.querySelector('audio[aria-label=\"reply.wav\"]').parentElement"
        expected_audio_url = f"data:audio/wav;base64,{content[0]['input_audio']['data']}"
        assert await evaluate(f"{player}.querySelector('audio').src") == expected_audio_url
        assert await evaluate(f"{player}.querySelector('a[aria-label=\"Download audio\"]').href") == expected_audio_url
        await wait("document.querySelector('audio[aria-label=\"reply.wav\"]')?.readyState >= 1")
        await client.send(
            "Runtime.evaluate",
            {
                "expression": f"{player}.querySelector('button[aria-label=\"Play recording preview\"]').click()",
                "userGesture": True,
            },
            session_id=session_id,
        )
        await wait(f"!!{player}.querySelector('button[aria-label=\"Pause recording preview\"]')")
        await evaluate(f"{player}.querySelector('button[aria-label=\"Pause recording preview\"]').click()")
        await evaluate(f"{player}.querySelector('input[aria-label=\"Audio playback position\"]').focus()")
        await client.send(
            "Input.dispatchKeyEvent",
            {"type": "keyDown", "key": "End", "code": "End", "windowsVirtualKeyCode": 35},
            session_id=session_id,
        )
        await wait("document.querySelector('audio[aria-label=\"reply.wav\"]').currentTime > 0")


@pytest.mark.parametrize("theme", ["light", "dark"])
async def test_audio_preview_preserves_original_presentation(audio_browser: tuple[_CDPClient, str], theme: str) -> None:
    """The original audio presentation stays readable before and after sending in both themes."""
    client, session_id = audio_browser

    async def assert_text_contrast() -> list[str]:
        players = await client.evaluate(
            """
            (() => {
              const context = document.createElement("canvas").getContext("2d");
              const luminance = color => {
                context.fillStyle = color;
                context.fillRect(0, 0, 1, 1);
                const channels = [...context.getImageData(0, 0, 1, 1).data].slice(0, 3).map(value => {
                  const component = value / 255;
                  return component <= 0.04045 ? component / 12.92 : ((component + 0.055) / 1.055) ** 2.4;
                });
                return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
              };
              return [...document.querySelectorAll("audio")].map(audio => {
                const pill = audio.parentElement;
                const background = luminance(getComputedStyle(pill).backgroundColor);
                const texts = [...pill.querySelectorAll("div, span")]
                  .filter(element => !element.children.length && element.textContent.trim());
                return {
                  label: audio.getAttribute("aria-label"),
                  contrasts: texts.map(element => {
                    const foreground = luminance(getComputedStyle(element).color);
                    return (Math.max(background, foreground) + 0.05) / (Math.min(background, foreground) + 0.05);
                  }),
                };
              });
            })()
            """,
            session_id=session_id,
        )
        for player in players:
            assert len(player["contrasts"]) == 2
            assert min(player["contrasts"]) >= 4.5, f"Unreadable audio label/duration in {theme}: {player}"
        return [player["label"] for player in players]

    await client.send(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
        session_id=session_id,
    )
    await client.evaluate(
        f"""
        document.documentElement.classList.toggle("dark", {str(theme == "dark").lower()});
        document.querySelector('button[aria-label="Record audio"], button[aria-label^="Click to record"]').click();
        """,
        session_id=session_id,
    )
    await _wait_for_expression(
        client,
        session_id=session_id,
        expression="!!document.querySelector('button[aria-label=\"Stop recording\"]')",
        timeout_s=10,
    )
    animation = await client.evaluate(
        """
        (() => {
          const bar = document.querySelector('button[aria-label="Stop recording"]').parentElement
            .querySelector('[aria-hidden="true"] span');
          return { name: getComputedStyle(bar).animationName, duration: getComputedStyle(bar).animationDuration };
        })()
        """,
        session_id=session_id,
    )
    assert animation["name"] != "none"
    assert animation["duration"] == "0.9s"
    await client.evaluate(
        "document.querySelector('button[aria-label=\"Stop recording\"]').click()", session_id=session_id
    )
    await _wait_for_expression(
        client,
        session_id=session_id,
        expression="!!document.querySelector('audio[aria-label=\"Voice recording preview\"]')",
        timeout_s=10,
    )
    presentation = await client.evaluate(
        """
        (() => {
          const audio = document.querySelector('audio[aria-label="Voice recording preview"]');
          const pill = audio.parentElement;
          const container = pill.parentElement;
          const bounds = pill.getBoundingClientRect();
          const outer = container.getBoundingClientRect();
          const bar = pill.querySelector('[aria-hidden="true"] span');
          const scrubber = pill.querySelector('input[aria-label="Audio playback position"]');
          const overlay = scrubber.parentElement.querySelector('[aria-hidden="true"]:last-of-type');
          return {
            label: pill.textContent,
            width: bounds.width,
            centered: Math.abs((bounds.left + bounds.right) / 2 - (outer.left + outer.right) / 2) < 1,
            thinWaveform: parseFloat(getComputedStyle(bar).width) === 2,
            widthTransition: getComputedStyle(pill).transitionProperty.includes("width"),
            scrubberTransition: getComputedStyle(overlay).transitionProperty.includes("opacity"),
          };
        })()
        """,
        session_id=session_id,
    )
    assert "Voice recording · 31 KB · WAV" in presentation["label"]
    assert presentation["width"] >= 420
    assert presentation["centered"]
    assert presentation["thinWaveform"]
    assert presentation["widthTransition"]
    assert presentation["scrubberTransition"]
    assert await assert_text_contrast() == ["Voice recording preview"]
    await client.evaluate(
        "document.querySelector('button[aria-label=\"Send message\"]').click()", session_id=session_id
    )
    await _wait_for_expression(
        client,
        session_id=session_id,
        expression="""document.querySelectorAll("audio").length === 2 &&
          !!document.querySelector('audio[aria-label="reply.wav"]') &&
          [...document.querySelectorAll("p")].some(element =>
            element.textContent.startsWith("This is a spoken response"))""",
        timeout_s=10,
    )
    assert await assert_text_contrast() == ["Voice message (WAV)", "reply.wav"]
    alignment = await client.evaluate(
        """
        (() => {
          const text = [...document.querySelectorAll("p")]
            .find(element => element.textContent.startsWith("This is a spoken response"));
          const player = document.querySelector('audio[aria-label="reply.wav"]').parentElement;
          return {
            textLeft: text.getBoundingClientRect().left,
            audioLeft: player.getBoundingClientRect().left,
            textWidth: text.getBoundingClientRect().width,
            audioWidth: player.getBoundingClientRect().width,
          };
        })()
        """,
        session_id=session_id,
    )
    assert abs(alignment["audioLeft"] - alignment["textLeft"]) < 1
    assert alignment["audioWidth"] < alignment["textWidth"]


@pytest.mark.parametrize("scenario", ["hold", "silence", "permission"])
async def test_audio_recording_gestures_and_settings(audio_browser: tuple[_CDPClient, str], scenario: str) -> None:
    """Hold-to-record, silence detection, and capture/preview settings preserve their original behavior."""
    client, session_id = audio_browser

    async def evaluate(expression: str) -> Any:
        return await client.evaluate(expression, session_id=session_id)

    async def wait(expression: str) -> Any:
        return await _wait_for_expression(client, session_id=session_id, expression=expression, timeout_s=10)

    async def open_options() -> None:
        await evaluate("document.querySelector('header svg.lucide-settings').closest('button').click()")
        await wait('[...document.querySelectorAll("summary")].some(s => s.textContent.trim() === "Audio options")')
        await evaluate("""
          [...document.querySelectorAll("summary")].find(s => s.textContent.trim() === "Audio options").click()
        """)

    async def close_options() -> None:
        for event in ("mousePressed", "mouseReleased"):
            await client.send(
                "Input.dispatchMouseEvent",
                {"type": event, "x": 2, "y": 2, "button": "left", "clickCount": 1},
                session_id=session_id,
            )
        await wait('!document.querySelector("#audio-sample-rate")')

    await evaluate(f"window.audioProbe.mode = {json.dumps(scenario)}")
    if scenario != "permission":
        await open_options()
        assert await evaluate('document.querySelector("#audio-sample-rate").value') == "16000"
        await evaluate("""
          document.querySelector('[aria-label="Auto-stop on silence"]').click();
        """)
        await wait('!!document.querySelector("#audio-silence-duration")')
        await evaluate("""
          for (const [id, value] of [
            ["audio-silence-duration", "250"], ["audio-min-recording", "0"], ["audio-sample-rate", "8000"]
          ]) {
            const input = document.getElementById(id);
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, value);
            input.dispatchEvent(new Event("input", { bubbles: true }));
          }
          window.audioProbe.quiet = true;
        """)
        await close_options()

    microphone = await evaluate("""
      (() => {
        const bounds = document.querySelector('button[aria-label^="Click to record"]').getBoundingClientRect();
        return { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
      })()
    """)
    if scenario == "silence":
        await evaluate("document.querySelector('button[aria-label^=\"Click to record\"]').click()")
    else:
        await client.send(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", **microphone, "button": "left", "buttons": 1, "clickCount": 1},
            session_id=session_id,
        )
        if scenario == "permission":
            await wait('document.body.textContent.includes("Preparing microphone")')
        else:
            await wait('document.querySelector(\'[aria-label="Recording duration"]\')?.textContent === "0:01"')
        await client.send(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": 2, "y": 2, "button": "left", "clickCount": 1},
            session_id=session_id,
        )

    if scenario == "permission":
        await wait('!document.body.textContent.includes("Preparing microphone")')
        await evaluate("window.audioProbe.allow()")
        await wait("window.audioProbe.stopped === 1")
        assert await evaluate("window.audioProbe.urls") == 0
        assert await evaluate("window.audioProbe.requests.length") == 0
        return

    await wait("!!document.querySelector('audio[aria-label=\"Voice recording preview\"]')")
    assert await evaluate("window.audioProbe.stopped") == 1
    assert await evaluate("window.audioProbe.requests.length") == 0
    sample_rate = await evaluate("""
      (async () => {
        const data = await (await fetch(document.querySelector('audio[aria-label="Voice recording preview"]').src))
          .arrayBuffer();
        return new DataView(data).getUint32(24, true);
      })()
    """)
    assert sample_rate == 8000

    await open_options()
    await evaluate('document.querySelector("#audio-preview").click()')
    await close_options()
    preview = "document.querySelector('audio[aria-label=\"Voice recording preview\"]').parentElement"
    assert not await evaluate(f"!!{preview}.querySelector('button[aria-label=\"Play recording preview\"]')")
    assert not await evaluate(f"!!{preview}.querySelector('input[aria-label=\"Audio playback position\"]')")
    await evaluate("document.querySelector('button[aria-label=\"Remove recording\"]').click()")
    await wait("!document.querySelector('audio[aria-label=\"Voice recording preview\"]')")
    assert await evaluate("window.audioProbe.revoked") == 1
    assert await evaluate("document.querySelector('button[aria-label=\"Send message\"]').disabled")


async def test_devui_streaming_renderer_memory_is_bounded(
    memory_regression_server: tuple[str, str],
) -> None:
    """Fail when frontend renderer memory grows unbounded during streaming."""

    browser_path = _find_browser_executable()
    if browser_path is None:
        pytest.skip("No Chromium-based browser found for DevUI memory regression test")

    base_url, entity_id = memory_regression_server
    debug_port = _find_available_port()

    with tempfile.TemporaryDirectory(prefix="devui-memory-browser-") as profile_dir:
        browser_process = _launch_browser_process(
            browser_path=browser_path,
            debug_port=debug_port,
            profile_dir=profile_dir,
        )

        try:
            try:
                websocket_url = await _get_devtools_websocket_url(debug_port)
            except RuntimeError as exc:
                return_code = browser_process.poll()
                if return_code is not None:
                    pytest.skip(f"Chromium exited before DevTools became available (code {return_code}).")
                pytest.skip(str(exc))

            async with websocket_connect(websocket_url, max_size=None) as websocket:
                client = _CDPClient(websocket)

                target = await client.send("Target.createTarget", {"url": "about:blank"})
                target_id = target["targetId"]
                attached = await client.send(
                    "Target.attachToTarget",
                    {"targetId": target_id, "flatten": True},
                )
                session_id = attached["sessionId"]

                await client.send("Page.enable", session_id=session_id)
                await client.send("Runtime.enable", session_id=session_id)
                await client.send(
                    "Page.navigate",
                    {"url": f"{base_url}/?entity_id={entity_id}"},
                    session_id=session_id,
                )

                await _wait_for_expression(
                    client,
                    session_id=session_id,
                    expression=(
                        "Boolean("
                        "document.querySelector('textarea') && "
                        "document.querySelector('button[aria-label=\"Send message\"]')"
                        ")"
                    ),
                    timeout_s=30.0,
                )

                start_renderer_rss_mb = _sample_peak_renderer_rss_mb(
                    browser_process.pid,
                    profile_dir,
                )

                await client.evaluate(
                    """
                    (() => {
                      const textarea = document.querySelector("textarea");
                      const valueSetter = Object.getOwnPropertyDescriptor(
                        HTMLTextAreaElement.prototype,
                        "value"
                      ).set;
                      valueSetter.call(textarea, "Stream a very long answer.");
                      textarea.dispatchEvent(new Event("input", { bubbles: true }));
                      document.querySelector('button[aria-label="Send message"]').click();
                      return true;
                    })()
                    """,
                    session_id=session_id,
                )

                await _wait_for_expression(
                    client,
                    session_id=session_id,
                    expression="Boolean(document.querySelector('button[aria-label=\"Stop generating response\"]'))",
                    timeout_s=10.0,
                )

                await asyncio.sleep(_POST_SEND_DELAY_S)

                peak_renderer_rss_mb = start_renderer_rss_mb
                samples: list[tuple[float, float]] = [(0.0, start_renderer_rss_mb)]
                probe_samples: list[tuple[float, _BrowserMemoryProbe]] = []
                start_time = time.monotonic()

                while time.monotonic() - start_time < _SAMPLE_WINDOW_S:
                    current_sample = _sample_peak_renderer_rss_mb(
                        browser_process.pid,
                        profile_dir,
                    )
                    elapsed_s = round(time.monotonic() - start_time, 2)
                    samples.append((elapsed_s, current_sample))
                    peak_renderer_rss_mb = max(peak_renderer_rss_mb, current_sample)
                    probe_samples.append((
                        elapsed_s,
                        await _sample_browser_memory_probe(client, session_id=session_id),
                    ))

                    if peak_renderer_rss_mb - start_renderer_rss_mb > _MAX_RENDERER_GROWTH_MB:
                        break

                    await asyncio.sleep(_SAMPLE_INTERVAL_S)

                renderer_growth_mb = round(peak_renderer_rss_mb - start_renderer_rss_mb, 2)
                max_streaming_state_storage_bytes = max(
                    (probe.streaming_state_storage_bytes for _, probe in probe_samples),
                    default=0,
                )
                max_debug_event_dom_items = max(
                    (probe.debug_event_dom_items for _, probe in probe_samples),
                    default=0,
                )
                assert renderer_growth_mb <= _MAX_RENDERER_GROWTH_MB, (
                    "DevUI renderer memory grew too much during a ~1.5 MB streaming response. "
                    f"start={start_renderer_rss_mb:.2f}MB "
                    f"peak={peak_renderer_rss_mb:.2f}MB "
                    f"growth={renderer_growth_mb:.2f}MB "
                    f"budget={_MAX_RENDERER_GROWTH_MB:.2f}MB "
                    f"samples={samples} "
                    f"probe_samples={probe_samples}"
                )
                assert max_streaming_state_storage_bytes <= _MAX_STREAMING_STATE_STORAGE_BYTES, (
                    "DevUI streaming resume state retained too much text in browser storage. "
                    f"peak={max_streaming_state_storage_bytes} bytes "
                    f"budget={_MAX_STREAMING_STATE_STORAGE_BYTES} bytes "
                    f"probe_samples={probe_samples}"
                )
                assert max_streaming_state_storage_bytes > 0, (
                    "DevUI streaming state storage was never written during the stress run "
                    "(cap assertion would be vacuous). "
                    f"probe_samples={probe_samples}"
                )
                assert max_debug_event_dom_items <= _MAX_DEBUG_EVENT_DOM_ITEMS, (
                    "DevUI debug panel rendered too many retained streaming events. "
                    f"peak={max_debug_event_dom_items} "
                    f"budget={_MAX_DEBUG_EVENT_DOM_ITEMS} "
                    f"probe_samples={probe_samples}"
                )
                assert max_debug_event_dom_items > 0, (
                    "DevUI debug panel rendered zero events during the stress run "
                    "(cap assertion would be vacuous). "
                    f"probe_samples={probe_samples}"
                )
        finally:
            _shutdown_browser_process(browser_process, profile_dir=profile_dir)
