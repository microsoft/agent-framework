# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.util
import inspect
import json
import sys
import threading
import time
from collections.abc import Awaitable, Callable, Iterator, Mapping, MutableSequence
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from agent_framework import (
    Agent,
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
    tool,
)

from agent_framework_hyperlight import AllowedDomain, FileMount, HyperlightCodeActProvider, HyperlightExecuteCodeTool
from agent_framework_hyperlight import _execute_code_tool as execute_code_module


def _hyperlight_integration_static_skip_reason() -> str | None:
    if sys.version_info >= (3, 14):
        return (
            "Hyperlight integration tests require Python < 3.14 because hyperlight-sandbox-backend-wasm is unsupported."
        )

    if sys.platform not in {"linux", "win32"}:
        return "Hyperlight integration tests require Linux or Windows runners."

    if importlib.util.find_spec("hyperlight_sandbox") is None:
        return "hyperlight-sandbox is not installed."

    if importlib.util.find_spec("python_guest") is None:
        return "hyperlight-sandbox-python-guest is not installed."

    try:
        importlib.metadata.version("hyperlight-sandbox-backend-wasm")
    except importlib.metadata.PackageNotFoundError:
        return "hyperlight-sandbox-backend-wasm is not installed."

    return None


def _hyperlight_integration_runtime_skip_reason() -> str | None:
    if (reason := _hyperlight_integration_static_skip_reason()) is not None:
        return reason

    try:
        sandbox_cls = execute_code_module._load_sandbox_class()
        sandbox = sandbox_cls(
            backend=execute_code_module.DEFAULT_HYPERLIGHT_BACKEND,
            module=execute_code_module.DEFAULT_HYPERLIGHT_MODULE,
        )
        sandbox.run("None")
    except RuntimeError as exc:
        message = str(exc)
        if "no hypervisor was found for sandbox" in message.lower():
            return "Hyperlight integration tests require a runner with a working Hyperlight hypervisor."

    return None


def _skip_if_hyperlight_integration_runtime_disabled() -> None:
    if (reason := _hyperlight_integration_runtime_skip_reason()) is not None:
        pytest.skip(reason)


skip_if_hyperlight_integration_tests_disabled = pytest.mark.skipif(
    (reason := _hyperlight_integration_static_skip_reason()) is not None,
    reason=reason or "Hyperlight integration tests are disabled.",
)


@tool(approval_mode="never_require")
def compute(a: int, b: int) -> int:
    return a + b


@tool(approval_mode="always_require")
def dangerous_compute(a: int, b: int) -> int:
    return a * b


@tool(name="compute", approval_mode="always_require")
def replacement_compute(a: int, b: int) -> int:
    return a - b


@dataclass(slots=True)
class _FakeResult:
    success: bool
    stdout: str = ""
    stderr: str = ""


def _run_in_thread(callback: Callable[[], Any]) -> Any:
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = callback()
        except BaseException as exc:
            error["value"] = exc

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]

    return result.get("value")


class _FakeSandbox:
    instances: list[_FakeSandbox] = []

    def __init__(
        self,
        *,
        input_dir: str | None = None,
        output_dir: str | None = None,
        temp_output: bool = False,
        backend: str = "wasm",
        module: str | None = None,
        module_path: str | None = None,
        heap_size: str | None = None,
        stack_size: str | None = None,
    ) -> None:
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.registered_tools: dict[str, Any] = {}
        self.allowed_domains: list[tuple[str, list[str] | None]] = []
        self.restore_calls: list[Any] = []
        self.output_files: list[str] = []
        _FakeSandbox.instances.append(self)

    def register_tool(self, name_or_tool: Any, callback: Any | None = None) -> None:
        if callback is None:
            raise AssertionError("Expected callback registration for sandbox tools.")
        self.registered_tools[str(name_or_tool)] = callback

    def allow_domain(self, target: str, methods: list[str] | None = None) -> None:
        self.allowed_domains.append((target, methods))

    def _invoke_tool(self, name: str, **kwargs: Any) -> Any:
        callback = self.registered_tools[name]
        if inspect.iscoroutinefunction(callback):
            return _run_in_thread(lambda: asyncio.run(callback(**kwargs)))

        result = callback(**kwargs)
        if inspect.isawaitable(result):
            return _run_in_thread(lambda: asyncio.run(result))
        return result

    def run(self, code: str) -> _FakeResult:
        if code == "None":
            return _FakeResult(success=True)
        if code == "create-output":
            if self.output_dir is None:
                raise AssertionError("Expected output directory for create-output test.")
            Path(self.output_dir, "report.txt").write_text("artifact", encoding="utf-8")
            self.output_files = ["report.txt"]
            return _FakeResult(success=True, stdout="done\n")
        if 'call_tool("compute", a=20, b=22)' in code:
            total = self._invoke_tool("compute", a=20, b=22)
            return _FakeResult(success=True, stdout=f"{total}\n")
        return _FakeResult(success=False, stderr="sandbox boom")

    def snapshot(self) -> str:
        return "snapshot"

    def restore(self, snapshot: Any) -> None:
        self.restore_calls.append(snapshot)

    def get_output_files(self) -> list[str]:
        return list(self.output_files)


class _FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, str]] = []

    def execute(self, *, config: Any, code: str) -> list[Content]:
        self.calls.append((config, code))
        return [Content.from_text("ok")]


class _FakeSandboxWithoutOutputListing(_FakeSandbox):
    def get_output_files(self) -> list[str]:
        return []


class _FakeSandboxWithDelayedUnlistedOutput(_FakeSandboxWithoutOutputListing):
    writer_threads: list[threading.Thread] = []

    def run(self, code: str) -> _FakeResult:
        if 'Path("/output/report.txt").write_text("artifact", encoding="utf-8")' in code:
            if self.output_dir is None:
                raise AssertionError("Expected output directory for delayed output test.")

            def _write_file() -> None:
                time.sleep(0.15)
                Path(self.output_dir, "report.txt").write_text("artifact", encoding="utf-8")

            writer_thread = threading.Thread(target=_write_file)
            writer_thread.start()
            self.writer_threads.append(writer_thread)
            return _FakeResult(success=True)

        return super().run(code)


class _FakeSessionContext:
    def __init__(self, *, tools: list[Any] | None = None) -> None:
        self.options: dict[str, Any] = {}
        if tools is not None:
            self.options["tools"] = tools
        self.instructions: list[tuple[str, str]] = []
        self.tools: list[tuple[str, list[Any]]] = []

    def extend_instructions(self, source_id: str, instructions: str) -> None:
        self.instructions.append((source_id, instructions))

    def extend_tools(self, source_id: str, tools: list[Any]) -> None:
        self.tools.append((source_id, tools))


def _extract_execute_code_result(function_result: Content) -> Content:
    assert function_result.type == "function_result"
    assert function_result.exception is None, (
        f"execute_code raised {function_result.exception!r} with items={function_result.items!r}"
    )

    code_result = next(
        (item for item in function_result.items or [] if item.type == "code_interpreter_tool_result"),
        None,
    )
    if code_result is not None:
        return code_result

    text_outputs = [item for item in function_result.items or [] if item.type == "text"]
    if text_outputs:
        return Content.from_code_interpreter_tool_result(outputs=text_outputs)

    if function_result.result:
        return Content.from_code_interpreter_tool_result(outputs=[Content.from_text(function_result.result)])

    raise AssertionError(f"execute_code returned no usable outputs: {function_result.items!r}")


def _extract_text_output(result_content: Content) -> str:
    code_result = _extract_execute_code_result(result_content)
    text_output = next(
        (item for item in code_result.outputs or [] if item.type == "text" and item.text is not None), None
    )
    assert text_output is not None and text_output.text is not None, (
        f"Expected text output from execute_code, got {code_result.outputs!r}"
    )
    return text_output.text


@contextmanager
def _serve_http_text_response(body: bytes) -> Iterator[tuple[str, list[str]]]:
    requests: list[str] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            requests.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class _FakeCodeActChatClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    def __init__(self) -> None:
        FunctionInvocationLayer.__init__(self)
        BaseChatClient.__init__(self)
        self.call_count = 0

    def _inner_get_response(
        self,
        *,
        messages: MutableSequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        if stream:
            raise AssertionError("Streaming is not used in this integration test.")

        async def _get_response() -> ChatResponse:
            self.call_count += 1

            if self.call_count == 1:
                return ChatResponse(
                    messages=Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="execute_code_call",
                                name="execute_code",
                                arguments={
                                    "code": 'total = call_tool("compute", a=20, b=22)\nprint(total)',
                                },
                            )
                        ],
                    )
                )

            function_results = [
                content for message in messages for content in message.contents if content.type == "function_result"
            ]
            assert len(function_results) == 1

            result_content = function_results[0]
            assert result_content.call_id == "execute_code_call"
            assert _extract_text_output(result_content) == "42\n"

            return ChatResponse(messages=Message(role="assistant", contents=["The sandbox returned 42."]))

        return _get_response()


def test_execute_code_tool_updates_approval_with_managed_tools() -> None:
    execute_code = HyperlightExecuteCodeTool(tools=[compute], _registry=_FakeRuntime())
    assert execute_code.approval_mode == "never_require"

    execute_code.add_tools([dangerous_compute])
    assert execute_code.approval_mode == "always_require"


def test_execute_code_tool_replaces_tools_with_the_same_name() -> None:
    execute_code = HyperlightExecuteCodeTool(tools=[compute], _registry=_FakeRuntime())

    execute_code.add_tools(replacement_compute)

    tools = execute_code.get_tools()
    assert len(tools) == 1
    assert tools[0] is replacement_compute
    assert execute_code.approval_mode == "always_require"


def test_execute_code_tool_accepts_string_and_tuple_file_mounts_without_mode_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shorthand_file = tmp_path / "notes.txt"
    shorthand_file.write_text("hello", encoding="utf-8")
    explicit_file = tmp_path / "data.json"
    explicit_file.write_text('{"hello": "world"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    execute_code = HyperlightExecuteCodeTool(_registry=_FakeRuntime())
    execute_code.add_file_mounts("notes.txt")
    execute_code.add_file_mounts((explicit_file, "data/data.json"))

    assert execute_code.get_file_mounts() == [
        FileMount(shorthand_file.resolve(), "/input/notes.txt"),
        FileMount(explicit_file.resolve(), "/input/data/data.json"),
    ]


def test_execute_code_tool_allowed_domains_use_structured_entries_and_replace_by_target() -> None:
    execute_code = HyperlightExecuteCodeTool(_registry=_FakeRuntime())

    execute_code.add_allowed_domains(["https://api.example.com/v1", ("github.com", "get")])
    execute_code.add_allowed_domains([
        AllowedDomain("api.example.com", ("post", "get")),
        ("github.com", ["head", "get"]),
    ])

    assert execute_code.get_allowed_domains() == [
        AllowedDomain("api.example.com", ("GET", "POST")),
        AllowedDomain("github.com", ("GET", "HEAD")),
    ]


def test_execute_code_tool_description_contains_call_tool_guidance(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "notes.txt").write_text("hello", encoding="utf-8")
    mount_file = tmp_path / "data.json"
    mount_file.write_text('{"hello": "world"}', encoding="utf-8")

    execute_code = HyperlightExecuteCodeTool(
        tools=[compute],
        workspace_root=workspace_root,
        file_mounts=[FileMount(str(mount_file), "data/data.json")],
        allowed_domains=[AllowedDomain("https://api.example.com/v1", ("get", "post")), "github.com"],
        _registry=_FakeRuntime(),
    )

    description = execute_code.description

    assert "call_tool(name, **kwargs)" in description
    assert "compute" in description
    assert "/input/data/data.json" in description
    assert "/output" in description
    assert "api.example.com" in description
    assert "GET, POST" in description
    assert "github.com" in description


async def test_execute_code_tool_executes_with_structured_content(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeSandbox.instances.clear()
    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: _FakeSandbox)

    execute_code = HyperlightExecuteCodeTool(
        tools=[compute],
        file_mounts=[FileMount(Path(__file__), "fixtures/source.py")],
        allowed_domains=[("api.example.com", "get")],
    )

    result = await execute_code.invoke(arguments={"code": "create-output"})

    assert result[0].type == "code_interpreter_tool_result"
    assert result[0].outputs is not None
    assert result[0].outputs[0].type == "text"
    assert result[0].outputs[0].text == "done\n"
    assert any(item.type == "data" for item in result[0].outputs)
    assert _FakeSandbox.instances[0].allowed_domains == [("api.example.com", ["GET"])]
    assert "compute" in _FakeSandbox.instances[0].registered_tools


async def test_execute_code_tool_collects_output_files_without_backend_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: _FakeSandboxWithoutOutputListing)

    execute_code = HyperlightExecuteCodeTool(
        file_mounts=[FileMount(Path(__file__), "fixtures/source.py")],
    )
    result = await execute_code.invoke(arguments={"code": "create-output"})

    assert result[0].type == "code_interpreter_tool_result"
    assert result[0].outputs is not None
    assert any(
        item.type == "data" and item.additional_properties["path"] == "/output/report.txt" for item in result[0].outputs
    )


async def test_execute_code_tool_waits_for_unlisted_output_files_to_appear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeSandboxWithDelayedUnlistedOutput.writer_threads.clear()
    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: _FakeSandboxWithDelayedUnlistedOutput)

    execute_code = HyperlightExecuteCodeTool(
        file_mounts=[FileMount(Path(__file__), "fixtures/source.py")],
    )
    result = await execute_code.invoke(
        arguments={"code": 'Path("/output/report.txt").write_text("artifact", encoding="utf-8")'}
    )

    for writer_thread in _FakeSandboxWithDelayedUnlistedOutput.writer_threads:
        writer_thread.join()

    assert result[0].type == "code_interpreter_tool_result"
    assert result[0].outputs is not None
    assert any(
        item.type == "data" and item.additional_properties["path"] == "/output/report.txt" for item in result[0].outputs
    )


async def test_execute_code_tool_failure_returns_error_content(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeSandbox.instances.clear()
    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: _FakeSandbox)

    execute_code = HyperlightExecuteCodeTool()
    result = await execute_code.invoke(arguments={"code": "fail"})

    assert result[0].type == "code_interpreter_tool_result"
    assert result[0].outputs is not None
    assert result[0].outputs[0].type == "error"
    assert result[0].outputs[0].error_details == "sandbox boom"


async def test_execute_code_tool_retries_allowed_domains_with_urls_when_backend_rejects_host_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStrictNetworkSandbox:
        instances: list[_FakeStrictNetworkSandbox] = []

        def __init__(
            self,
            *,
            input_dir: str | None = None,
            output_dir: str | None = None,
            backend: str = "wasm",
            module: str | None = None,
            module_path: str | None = None,
        ) -> None:
            del input_dir, output_dir, backend, module, module_path
            self.allowed_domains: list[tuple[str, list[str] | None]] = []
            _FakeStrictNetworkSandbox.instances.append(self)

        def register_tool(self, name_or_tool: Any, callback: Any | None = None) -> None:
            del name_or_tool, callback

        def allow_domain(self, target: str, methods: list[str] | None = None) -> None:
            self.allowed_domains.append((target, methods))

        def run(self, code: str) -> _FakeResult:
            if code == "None" and any("://" not in target for target, _ in self.allowed_domains):
                raise RuntimeError("invalid URL for network permission: ")
            return _FakeResult(success=True)

        def snapshot(self) -> str:
            return "snapshot"

        def restore(self, snapshot: Any) -> None:
            del snapshot

    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: _FakeStrictNetworkSandbox)

    execute_code = HyperlightExecuteCodeTool(allowed_domains=[("127.0.0.1:8080", "get")])
    result = await execute_code.invoke(arguments={"code": "None"})

    assert result[0].type == "code_interpreter_tool_result"
    assert len(_FakeStrictNetworkSandbox.instances) == 2
    assert _FakeStrictNetworkSandbox.instances[0].allowed_domains == [("127.0.0.1:8080", ["GET"])]
    assert _FakeStrictNetworkSandbox.instances[1].allowed_domains == [
        ("http://127.0.0.1:8080", ["GET"]),
        ("https://127.0.0.1:8080", ["GET"]),
    ]


def test_hyperlight_integration_runtime_skip_reason_reports_missing_hypervisor(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeNoHypervisorSandbox:
        def __init__(
            self,
            *,
            input_dir: str | None = None,
            output_dir: str | None = None,
            backend: str = "wasm",
            module: str | None = None,
            module_path: str | None = None,
        ) -> None:
            del input_dir, output_dir, backend, module, module_path

        def run(self, code: str) -> _FakeResult:
            del code
            raise RuntimeError("failed to build ProtoWasmSandbox: No Hypervisor was found for Sandbox")

    original_find_spec = importlib.util.find_spec

    def _fake_find_spec(name: str) -> object | None:
        if name in {"hyperlight_sandbox", "python_guest"}:
            return object()
        return original_find_spec(name)

    monkeypatch.setattr(sys, "version_info", (3, 13, 0))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "0.0.0")
    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: _FakeNoHypervisorSandbox)

    assert _hyperlight_integration_runtime_skip_reason() == (
        "Hyperlight integration tests require a runner with a working Hyperlight hypervisor."
    )


async def test_provider_injects_run_scoped_execute_code_tool() -> None:
    runtime = _FakeRuntime()
    provider = HyperlightCodeActProvider(tools=[compute], _registry=runtime)
    context = _FakeSessionContext(tools=[dangerous_compute])
    state: dict[str, Any] = {}

    await provider.before_run(agent=object(), session=None, context=context, state=state)

    assert context.options["tools"] == [dangerous_compute]
    assert len(context.instructions) == 1
    assert len(context.tools) == 1

    run_tool = context.tools[0][1][0]
    assert isinstance(run_tool, HyperlightExecuteCodeTool)
    assert run_tool.approval_mode == "never_require"
    assert [tool_obj.name for tool_obj in run_tool.get_tools()] == ["compute"]
    assert "dangerous_compute" not in context.instructions[0][1]
    assert "compute" not in context.instructions[0][1]
    assert "Filesystem capabilities:" not in context.instructions[0][1]
    assert state[provider.source_id]["tool_names"] == ["compute"]
    assert state[provider.source_id]["approval_mode"] == "never_require"
    json.dumps(state)

    provider.remove_tool("compute")
    assert [tool_obj.name for tool_obj in run_tool.get_tools()] == ["compute"]


async def test_agent_runs_hyperlight_codeact_end_to_end_with_fake_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeSandbox.instances.clear()
    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: _FakeSandbox)

    client = _FakeCodeActChatClient()
    provider = HyperlightCodeActProvider(tools=[compute])
    agent = Agent(client=client, context_providers=[provider])

    response = await agent.run("Use the sandbox to add 20 and 22.")

    assert response.text == "The sandbox returned 42."
    assert client.call_count == 2
    assert len(_FakeSandbox.instances) == 1
    assert "compute" in _FakeSandbox.instances[0].registered_tools


@skip_if_hyperlight_integration_tests_disabled
async def test_agent_runs_hyperlight_codeact_end_to_end_with_real_sandbox() -> None:
    _skip_if_hyperlight_integration_runtime_disabled()

    client = _FakeCodeActChatClient()
    provider = HyperlightCodeActProvider(tools=[compute])
    agent = Agent(client=client, context_providers=[provider])

    response = await agent.run("Use the sandbox to add 20 and 22.")

    assert response.text == "The sandbox returned 42."
    assert client.call_count == 2


@skip_if_hyperlight_integration_tests_disabled
async def test_provider_run_tool_reads_writes_files_and_accesses_allowed_url_with_real_sandbox(
    tmp_path: Path,
) -> None:
    _skip_if_hyperlight_integration_runtime_disabled()

    mounted_file = tmp_path / "mounted.txt"
    mounted_file.write_text("hello from mount", encoding="utf-8")

    with _serve_http_text_response(b"network ok") as (allowed_host, requests):
        provider = HyperlightCodeActProvider()
        provider.add_file_mounts((mounted_file, "data/input.txt"))
        provider.add_allowed_domains((allowed_host, "GET"))

        context = _FakeSessionContext()
        state: dict[str, Any] = {}
        await provider.before_run(agent=object(), session=None, context=context, state=state)

        run_tool = context.tools[0][1][0]
        assert isinstance(run_tool, HyperlightExecuteCodeTool)

        # The packaged guest on Windows 3.10 exposes a reduced stdlib, and some
        # backends surface mounted files relative to the guest cwd instead of
        # under `/input`, so keep this probe minimal and path-tolerant.
        result = await run_tool.invoke(
            arguments={
                "code": (
                    "import os\n"
                    "import _socket\n\n"
                    "input_text = None\n"
                    "input_path = None\n"
                    'for candidate_input_path in ("/input/data/input.txt", "input/data/input.txt", "data/input.txt"):\n'
                    "    input_path = candidate_input_path\n"
                    "    if not os.path.exists(candidate_input_path):\n"
                    "        continue\n"
                    '    with open(candidate_input_path, encoding="utf-8") as input_file:\n'
                    "        input_text = input_file.read()\n"
                    "    break\n"
                    "if input_text is None:\n"
                    '    for search_root in (".", "input", "/input"):\n'
                    "        if not os.path.exists(search_root):\n"
                    "            continue\n"
                    "        try:\n"
                    "            for root, _, files in os.walk(search_root):\n"
                    '                if "input.txt" not in files:\n'
                    "                    continue\n"
                    '                input_path = os.path.join(root, "input.txt")\n'
                    '                with open(input_path, encoding="utf-8") as input_file:\n'
                    "                    input_text = input_file.read()\n"
                    "                break\n"
                    "        except OSError:\n"
                    "            continue\n"
                    "        if input_text is not None:\n"
                    "            break\n"
                    'assert input_text is not None, "input file not found"\n'
                    "output_path = None\n"
                    'for candidate_output_path in ("/output/result.txt", "output/result.txt", "result.txt"):\n'
                    "    candidate_parent = os.path.dirname(candidate_output_path)\n"
                    "    if candidate_parent:\n"
                    "        try:\n"
                    "            os.makedirs(candidate_parent, exist_ok=True)\n"
                    "        except OSError:\n"
                    "            pass\n"
                    "    try:\n"
                    '        with open(candidate_output_path, "w", encoding="utf-8") as output_file:\n'
                    "            output_file.write(input_text.upper())\n"
                    "    except OSError:\n"
                    "        continue\n"
                    "    output_path = candidate_output_path\n"
                    "    break\n"
                    'assert output_path is not None, "output path unavailable"\n'
                    f'host, port_text = "{allowed_host}".rsplit(":", 1)\n'
                    "response_bytes = b''\n"
                    "request = ("
                    'b"GET /allowed HTTP/1.1\\r\\n" '
                    f'b"Host: {allowed_host}\\r\\n" '
                    'b"Connection: close\\r\\n\\r\\n")\n'
                    "connection = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)\n"
                    "try:\n"
                    "    connection.settimeout(10)\n"
                    "    connection.connect((host, int(port_text)))\n"
                    "    connection.sendall(request)\n"
                    "    while True:\n"
                    "        chunk = connection.recv(4096)\n"
                    "        if not chunk:\n"
                    "            break\n"
                    "        response_bytes += chunk\n"
                    "finally:\n"
                    "    connection.close()\n"
                    'header_end = response_bytes.find(b"\\r\\n\\r\\n")\n'
                    "assert header_end != -1\n"
                    'network_text = response_bytes[header_end + 4 :].decode("utf-8")\n'
                    'assert input_text == "hello from mount"\n'
                    'assert network_text == "network ok"\n'
                    'assert os.path.exists(output_path), "output file was not written"\n'
                    'print("validated")\n'
                )
            }
        )

    assert result[0].type == "code_interpreter_tool_result"
    outputs = result[0].outputs or []
    error_outputs = [
        f"{item.message}: {item.error_details}"
        for item in outputs
        if item.type == "error" and item.error_details is not None
    ]
    assert not error_outputs, error_outputs

    text_output = next((item for item in outputs if item.type == "text" and item.text is not None), None)
    if text_output is not None:
        assert text_output.text == "validated\n"

    file_output = next((item for item in outputs if item.type == "data"), None)
    if file_output is not None:
        assert file_output.data == b"HELLO FROM MOUNT"
        assert file_output.additional_properties["path"] in {"/output/result.txt", "/output/output/result.txt"}
    assert requests == ["/allowed"]
