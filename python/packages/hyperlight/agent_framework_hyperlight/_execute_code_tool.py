# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import mimetypes
import shutil
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from copy import copy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any, Protocol, TypeGuard, TypeVar, cast
from urllib.parse import urlparse

from agent_framework import Content, FunctionTool
from agent_framework._tools import ApprovalMode, normalize_tools

from ._drop_diagnostic import is_enabled as _drop_diag_enabled
from ._drop_diagnostic import track as _drop_diag_track
from ._instructions import build_codeact_instructions, build_execute_code_description
from ._types import AllowedDomain, AllowedDomainInput, FileMount, FileMountHostPath, FileMountInput

DEFAULT_HYPERLIGHT_BACKEND = "wasm"
DEFAULT_HYPERLIGHT_MODULE = "python_guest.path"
EXECUTE_CODE_TOOL_DESCRIPTION = "Execute Python in an isolated Hyperlight sandbox."
OUTPUT_FILE_RETRY_ATTEMPTS = 10
OUTPUT_FILE_RETRY_DELAY_SECONDS = 0.1

EXECUTE_CODE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "_ExecuteCodeInput",
    "properties": {
        "code": {
            "type": "string",
            "title": "Code",
            "description": "Python code to execute in an isolated Hyperlight sandbox.",
        },
    },
    "required": ["code"],
}


@dataclass(frozen=True, slots=True)
class _NormalizedFileMount:
    host_path: Path
    mount_path: str
    path_signature: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True, slots=True)
class _RunConfig:
    backend: str
    module: str | None
    module_path: str | None
    approval_mode: ApprovalMode
    tools: tuple[FunctionTool, ...]
    workspace_root: Path | None
    workspace_signature: tuple[tuple[str, int, int], ...]
    file_mounts: tuple[_NormalizedFileMount, ...]
    allowed_domains: tuple[AllowedDomain, ...]

    @property
    def mounted_paths(self) -> tuple[str, ...]:
        return tuple(_display_mount_path(mount.mount_path) for mount in self.file_mounts)

    @property
    def filesystem_enabled(self) -> bool:
        return self.workspace_root is not None or bool(self.file_mounts)

    def cache_key(self) -> tuple[Any, ...]:
        return (
            self.backend,
            self.module,
            self.module_path,
            self.approval_mode,
            tuple((tool_obj.name, id(tool_obj)) for tool_obj in self.tools),
            str(self.workspace_root) if self.workspace_root is not None else None,
            self.workspace_signature,
            tuple((mount.mount_path, str(mount.host_path), mount.path_signature) for mount in self.file_mounts),
            tuple((allowed_domain.target, allowed_domain.methods) for allowed_domain in self.allowed_domains),
        )


class SandboxRuntime(Protocol):
    def execute(self, *, config: _RunConfig, code: str) -> list[Content]: ...


_T = TypeVar("_T")


class _SandboxWorker:
    """Thread-confined actor that owns a sandbox + snapshot.

    The Hyperlight ``WasmSandbox`` is declared ``unsendable`` in PyO3: it can only be
    accessed *and dropped* from the OS thread that created it. Touching or
    releasing it on any other thread triggers a Rust panic
    (``"_native_wasm::WasmSandbox is unsendable, but is being dropped on another thread"``)
    that cannot be caught from Python.

    To make this guarantee airtight, this class is an actor: the underlying
    sandbox and snapshot are stored ONLY as worker-local state and are never
    exposed to or returned to other threads. Public methods submit closures to
    the dedicated single-thread executor and return only sendable results.
    Because no caller can ever obtain a strong reference to the unsendable
    objects, no caller can ever cause them to be dropped on the wrong thread.

    Exception isolation: exceptions raised inside worker closures carry a
    ``__traceback__`` whose frames retain references to local variables --
    including PyO3 unsendable sandbox/native_result objects. Letting such an
    exception propagate to the calling thread would defeat the actor model:
    when the calling thread GCs the exception, the traceback's frame locals
    are dropped on the wrong thread and PyO3 panics. To prevent this, every
    exception raised inside a worker closure is caught on the worker, the
    traceback is dropped while still on the worker thread, and a sanitized
    copy (preserving message and exception type) is re-raised on the caller.
    """

    __slots__ = ("_executor", "_initialized", "_sandbox", "_snapshot")

    def __init__(self, *, name: str = "hl-sandbox") -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=name)
        # _sandbox/_snapshot are accessed/mutated ONLY from worker-side closures.
        self._sandbox: Any = None
        self._snapshot: Any = None
        self._initialized = False

    def _run_on_worker(self, fn: Callable[[], _T]) -> _T:
        """Run ``fn`` on the worker thread; sanitize any exception's traceback there.

        If ``fn`` raises, the exception's ``__traceback__`` is dropped on the worker
        thread (so any PyO3 unsendable locals captured in frame locals are released
        on the owner thread) and a fresh exception of the same type is raised on
        the caller's thread carrying only the original message.
        """

        def _wrapped() -> tuple[bool, Any]:
            try:
                return True, fn()
            except BaseException as exc:
                exc_type = type(exc)
                exc_message = str(exc)
                # Drop the traceback on the worker thread so frame locals (which
                # may include PyO3 unsendable objects) are released here, not on
                # the caller thread that will receive the wrapped exception.
                exc.__traceback__ = None
                del exc
                return False, (exc_type, exc_message)

        ok, payload = self._executor.submit(_wrapped).result()
        if ok:
            return cast(_T, payload)
        exc_type, exc_message = cast(tuple[type[BaseException], str], payload)
        # Re-raise a fresh instance with no chained traceback frames from the worker.
        raise exc_type(exc_message)

    def initialize(self, build_fn: Callable[[], tuple[Any, Any]]) -> None:
        """Build and install the sandbox+snapshot on the worker thread.

        ``build_fn`` is invoked with no arguments on the worker thread. It must
        return ``(sandbox, snapshot)``. Both references are retained as worker-
        local attributes; they do not escape this thread.
        """

        def _init_on_worker() -> None:
            sandbox, snapshot = build_fn()
            self._sandbox = sandbox
            self._snapshot = snapshot
            self._initialized = True
            if _drop_diag_enabled():
                _drop_diag_track(sandbox, "sandbox")
                _drop_diag_track(snapshot, "snapshot")
            # Locals fall out of scope on the worker thread; the worker-local
            # attributes hold the only strong refs from now on.

        self._run_on_worker(_init_on_worker)

    def execute(
        self,
        *,
        code: str,
        output_dir: TemporaryDirectory[str] | None,
        build_contents: Callable[..., list[Content]],
    ) -> list[Content]:
        """Restore + run + build sendable contents — all on the worker thread.

        Returns a plain ``list[Content]`` whose elements never carry strong
        references to the underlying sandbox or snapshot.
        """

        def _on_worker() -> list[Content]:
            sandbox = self._sandbox
            snapshot = self._snapshot
            sandbox.restore(snapshot)
            _clear_directory(output_dir)
            result = sandbox.run(code=code)
            if _drop_diag_enabled():
                _drop_diag_track(result, "execution-result")
            try:
                return build_contents(
                    result=result,
                    sandbox=sandbox,
                    output_dir=output_dir,
                    code=code,
                )
            finally:
                # ``result`` may carry a back-reference to the sandbox. Force its
                # final dec_ref on this thread so Drop runs here, not on whatever
                # thread later GCs the ``Content`` list.
                del result

        return self._run_on_worker(_on_worker)

    def dispose(self) -> None:
        """Release the sandbox+snapshot on the owner worker thread, then shut down.

        Safe to call multiple times. After ``dispose`` returns, the sandbox/
        snapshot are guaranteed to have been released on the worker thread; any
        remaining references held elsewhere have already been impossible (they
        never leaked out of this object).
        """

        def _dispose_on_worker() -> None:
            sandbox = self._sandbox
            snapshot = self._snapshot
            self._sandbox = None
            self._snapshot = None
            close_hook = (
                (getattr(sandbox, "close", None) or getattr(sandbox, "shutdown", None)) if sandbox is not None else None
            )
            if callable(close_hook):
                with suppress(Exception):
                    close_hook()
            # ``sandbox`` and ``snapshot`` are local on the worker thread and
            # will be dec_ref'd here when this frame returns -> Drop on worker.
            del sandbox, snapshot

        if self._initialized:
            try:
                # Use the bare executor here -- _dispose_on_worker swallows its
                # own errors and never raises, so traceback sanitization is not
                # needed and we want dispose to remain robust during teardown.
                self._executor.submit(_dispose_on_worker).result()
            except RuntimeError:
                # Worker already shut down; sandbox/snapshot will leak rather
                # than panic on the wrong thread. This is the safest fallback.
                pass
            finally:
                self._initialized = False
        # Do not block on shutdown; stop accepting new tasks, but allow any
        # already-queued task (including the dispose closure above) to finish.
        self._executor.shutdown(wait=False, cancel_futures=False)


@dataclass
class _SandboxEntry:
    """Per-config cached sandbox handle.

    The unsendable sandbox/snapshot live inside ``worker`` and never appear as
    Python attributes on this object. Anything stored here is sendable and
    safe to GC on any thread.
    """

    worker: _SandboxWorker
    input_dir: TemporaryDirectory[str] | None
    output_dir: TemporaryDirectory[str] | None

    def dispose(self) -> None:
        """Release the sandbox+snapshot on the worker thread and clean up temp dirs."""
        self.worker.dispose()
        for tmp_dir in (self.input_dir, self.output_dir):
            if tmp_dir is not None:
                with suppress(Exception):
                    tmp_dir.cleanup()
        self.input_dir = None
        self.output_dir = None


def _load_sandbox_class() -> type[Any]:
    try:
        from hyperlight_sandbox import Sandbox
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Hyperlight support requires `hyperlight-sandbox`, `hyperlight-sandbox-python-guest`, "
            "and a compatible backend package such as `hyperlight-sandbox-backend-wasm`."
        ) from exc

    return Sandbox


def _collect_tools(*tool_groups: Any) -> list[FunctionTool]:
    tools_by_name: dict[str, FunctionTool] = {}

    for tool_group in tool_groups:
        normalized_group = normalize_tools(tool_group)
        for tool_obj in normalized_group:
            if not isinstance(tool_obj, FunctionTool):
                continue
            if tool_obj.name == "execute_code":
                continue
            tools_by_name.pop(tool_obj.name, None)
            tools_by_name[tool_obj.name] = tool_obj

    return list(tools_by_name.values())


def _resolve_execute_code_approval_mode(
    *,
    base_approval_mode: ApprovalMode,
    tools: Sequence[FunctionTool],
) -> ApprovalMode:
    if base_approval_mode == "always_require":
        return "always_require"

    if any(tool_obj.approval_mode == "always_require" for tool_obj in tools):
        return "always_require"

    return "never_require"


def _resolve_existing_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=True)


def _resolve_workspace_root(value: str | Path | None) -> Path | None:
    if value is None:
        return None

    resolved_path = _resolve_existing_path(value)
    if not resolved_path.is_dir():
        raise ValueError("workspace_root must point to an existing directory.")
    return resolved_path


def _is_file_mount_pair(value: Any) -> TypeGuard[FileMount | tuple[FileMountHostPath, str]]:
    if not isinstance(value, tuple):
        return False

    value_tuple = cast(tuple[object, ...], value)
    if len(value_tuple) != 2:
        return False

    host_path, mount_path = value_tuple
    return isinstance(host_path, (str, Path)) and isinstance(mount_path, str)


def _normalize_file_mount_input(file_mount: FileMountInput) -> FileMount:
    host_path: FileMountHostPath
    mount_path: str
    if isinstance(file_mount, str):
        host_path = file_mount
        mount_path = file_mount
    else:
        host_path = file_mount[0]
        mount_path = file_mount[1]

    return FileMount(
        host_path=_resolve_existing_path(host_path),
        mount_path=_normalize_mount_path(mount_path),
    )


def _normalize_domain(target: str) -> str:
    candidate = target.strip()
    if not candidate:
        raise ValueError("Allowed domain entries must not be empty.")

    parsed = urlparse(candidate if "://" in candidate else f"//{candidate}")
    normalized = (parsed.netloc or parsed.path).strip().rstrip("/")
    if not normalized:
        raise ValueError(f"Could not normalize allowed domain entry: {target!r}.")
    return normalized.lower()


def _normalize_http_method(method: str) -> str:
    normalized = method.strip().upper()
    if not normalized:
        raise ValueError("HTTP method entries must not be empty.")
    return normalized


def _normalize_http_methods(methods: str | Sequence[str] | None) -> tuple[str, ...] | None:
    if methods is None:
        return None

    normalized_methods = (
        {_normalize_http_method(methods)}
        if isinstance(methods, str)
        else {_normalize_http_method(method) for method in methods}
    )
    if not normalized_methods:
        raise ValueError("Allowed domain methods must not be empty when provided.")
    return tuple(sorted(normalized_methods))


def _is_allowed_domain_pair(value: Any) -> TypeGuard[tuple[str, str | Sequence[str]]]:
    if not isinstance(value, tuple) or isinstance(value, AllowedDomain):
        return False

    value_tuple = cast(tuple[object, ...], value)
    if len(value_tuple) != 2:
        return False

    target, methods = value_tuple
    if not isinstance(target, str):
        return False
    if isinstance(methods, str):
        return True
    return isinstance(methods, Sequence)


def _normalize_allowed_domain_input(allowed_domain: AllowedDomainInput) -> AllowedDomain:
    if isinstance(allowed_domain, str):
        return AllowedDomain(target=_normalize_domain(allowed_domain), methods=None)

    if isinstance(allowed_domain, AllowedDomain):
        return AllowedDomain(
            target=_normalize_domain(allowed_domain.target),
            methods=_normalize_http_methods(allowed_domain.methods),
        )

    target, methods = allowed_domain
    return AllowedDomain(
        target=_normalize_domain(target),
        methods=_normalize_http_methods(methods),
    )


def _allowed_domain_registration_targets(*, target: str, expand_missing_scheme: bool) -> tuple[str, ...]:
    if not expand_missing_scheme or "://" in target:
        return (target,)
    return (f"http://{target}", f"https://{target}")


def _should_retry_allowed_domain_registration(
    *,
    error: RuntimeError,
    allowed_domains: Sequence[AllowedDomain],
) -> bool:
    message = str(error).lower()
    return "invalid url for network permission" in message and any(
        "://" not in domain.target for domain in allowed_domains
    )


def _normalize_mount_path(mount_path: str) -> str:
    raw_path = mount_path.strip().replace("\\", "/")
    if not raw_path:
        raise ValueError("mount_path must not be empty.")

    pure_path = PurePosixPath(raw_path)
    parts = [part for part in pure_path.parts if part not in {"", "/", "."}]
    if parts and parts[0] == "input":
        parts = parts[1:]
    if any(part == ".." for part in parts):
        raise ValueError("mount_path must stay within /input.")
    if not parts:
        raise ValueError("mount_path must point to a concrete path under /input.")
    return "/".join(parts)


def _display_mount_path(mount_path: str) -> str:
    return f"/input/{mount_path}"


def _path_tree_signature(path: Path) -> tuple[tuple[str, int, int], ...]:
    if path.is_file():
        stat = path.stat()
        return ((path.name, int(stat.st_size), int(stat.st_mtime_ns)),)

    entries: list[tuple[str, int, int]] = []
    for candidate in sorted(path.rglob("*"), key=lambda value: value.as_posix()):
        try:
            stat = candidate.stat()
        except FileNotFoundError:
            continue
        relative_path = candidate.relative_to(path).as_posix()
        size = int(stat.st_size) if candidate.is_file() else 0
        entries.append((relative_path, size, int(stat.st_mtime_ns)))
    return tuple(entries)


def _copy_path(source: Path, destination: Path) -> None:
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir(), key=lambda value: value.name):
            _copy_path(child, destination / child.name)
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _populate_input_dir(*, config: _RunConfig, input_root: Path) -> None:
    if config.workspace_root is not None:
        for child in sorted(config.workspace_root.iterdir(), key=lambda value: value.name):
            _copy_path(child, input_root / child.name)

    for mount in config.file_mounts:
        _copy_path(mount.host_path, input_root / mount.mount_path)


def _create_file_content(file_path: Path, *, relative_path: str) -> Content:
    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return Content.from_data(
        data=file_path.read_bytes(),
        media_type=media_type,
        additional_properties={"path": f"/output/{relative_path}"},
    )


def _normalize_output_relative_path(*, output_file: object, root: Path) -> str | None:
    candidate_path = Path(str(output_file))
    if candidate_path.is_absolute():
        try:
            return candidate_path.relative_to(root).as_posix()
        except ValueError:
            return None

    raw_path = str(output_file).replace("\\", "/")
    pure_path = PurePosixPath(raw_path)
    parts = [part for part in pure_path.parts if part not in {"", "/", "."}]
    if parts and parts[0] == "output":
        parts = parts[1:]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _collect_output_relative_paths(*, sandbox: Any, root: Path) -> set[str]:
    relative_paths: set[str] = set()

    if hasattr(sandbox, "get_output_files"):
        try:
            output_files = cast(Sequence[object], sandbox.get_output_files())
        except Exception:
            output_files = ()

        for output_file in output_files:
            if (relative_path := _normalize_output_relative_path(output_file=output_file, root=root)) is not None:
                relative_paths.add(relative_path)

    for host_path in root.rglob("*"):
        if host_path.is_file():
            relative_paths.add(host_path.relative_to(root).as_posix())

    return relative_paths


def _parse_output_files(
    *,
    sandbox: Any,
    output_dir: TemporaryDirectory[str] | None,
    expect_output_files: bool,
) -> list[Content]:
    if output_dir is None:
        return []

    root = Path(output_dir.name)

    for attempt in range(OUTPUT_FILE_RETRY_ATTEMPTS):
        relative_paths = _collect_output_relative_paths(sandbox=sandbox, root=root)
        missing_files = expect_output_files and not relative_paths
        contents: list[Content] = []

        for relative_path in sorted(relative_paths):
            host_path = root.joinpath(*PurePosixPath(relative_path).parts)
            if not host_path.is_file():
                missing_files = True
                continue
            try:
                contents.append(_create_file_content(host_path, relative_path=relative_path))
            except PermissionError:
                missing_files = True

        if not missing_files or attempt == OUTPUT_FILE_RETRY_ATTEMPTS - 1:
            return contents

        time.sleep(OUTPUT_FILE_RETRY_DELAY_SECONDS)

    return []


def _result_snapshot(result: Any) -> dict[str, Any]:
    """Return a sendable plain-dict snapshot of a sandbox.run() result.

    The Hyperlight ``WasmSandbox.run()`` return value is a PyO3 ``unsendable`` object that
    can carry a back-reference to the sandbox itself. Storing it on
    ``Content.raw_representation`` lets it ride out of the owner thread and be garbage
    collected elsewhere, which trips the PyO3 ``Drop`` panic. Build a thread-safe summary
    of the fields we actually surface and forward that instead, so the original result can
    be released on the worker thread that produced it.
    """
    return {
        "success": bool(getattr(result, "success", False)),
        "stdout": str(getattr(result, "stdout", "") or ""),
        "stderr": str(getattr(result, "stderr", "") or ""),
    }


def _build_execution_contents(
    *,
    result: Any,
    sandbox: Any,
    output_dir: TemporaryDirectory[str] | None,
    code: str,
) -> list[Content]:
    success = bool(getattr(result, "success", False))
    stdout = str(getattr(result, "stdout", "") or "").replace("\r\n", "\n") or None
    stderr = str(getattr(result, "stderr", "") or "").replace("\r\n", "\n") or None
    snapshot = _result_snapshot(result)
    outputs: list[Content] = []

    if stdout is not None:
        outputs.append(Content.from_text(stdout, raw_representation=snapshot))

    outputs.extend(
        _parse_output_files(
            sandbox=sandbox,
            output_dir=output_dir,
            expect_output_files="/output" in code,
        )
    )

    if success:
        if stderr is not None:
            outputs.append(Content.from_text(stderr, raw_representation=snapshot))
        if not outputs:
            outputs.append(Content.from_text("Code executed successfully without output."))
        return outputs

    error_details = stderr or "Unknown sandbox error"
    outputs.append(
        Content.from_error(
            message="Execution error",
            error_details=error_details,
            raw_representation=snapshot,
        )
    )
    return outputs


def _make_sandbox_callback(tool_obj: FunctionTool) -> Callable[..., Any]:
    sandbox_tool = copy(tool_obj)

    def _callback(**kwargs: Any) -> Any:
        async def _invoke() -> Any:
            return await sandbox_tool.invoke(arguments=kwargs, skip_parsing=True)

        # FunctionTool.invoke() is async. The real Hyperlight backend invokes
        # registered callbacks synchronously via FFI, so this must be a sync function.
        # We run the async call on a dedicated thread to avoid conflicts with any
        # event loop that may be running on the current thread.
        result_box: list[Any] = [None]
        error_box: list[BaseException] = []

        def _run() -> None:
            try:
                result_box[0] = asyncio.run(_invoke())
            except BaseException as exc:
                error_box.append(exc)

        worker = threading.Thread(target=_run)
        worker.start()
        worker.join()
        if error_box:
            raise error_box[0]
        # Return the raw value. The Hyperlight FFI marshals primitives (dict, list,
        # str, int, float, bool, None) natively into the guest, and falls back to
        # repr()/str() for unsupported types — so the guest receives real Python
        # objects without a lossy host-side serialization round-trip.
        return result_box[0]

    return _callback


def _clear_directory(output_dir: TemporaryDirectory[str] | None) -> None:
    """Remove all contents of the output directory without deleting the directory itself."""
    if output_dir is None:
        return
    root = Path(output_dir.name)
    for child in root.iterdir():
        try:
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
        except (FileNotFoundError, PermissionError):
            pass


class _SandboxRegistry(SandboxRuntime):
    def __init__(self) -> None:
        self._entries: dict[tuple[Any, ...], _SandboxEntry] = {}
        self._entries_lock = threading.RLock()

    def execute(self, *, config: _RunConfig, code: str) -> list[Content]:
        """Execute code in a cached sandbox matching the given config.

        Entries are keyed by ``config.cache_key()``. All operations against the underlying
        sandbox object are routed through the entry's dedicated single-threaded worker, which
        both serializes concurrent callers and satisfies the PyO3 ``unsendable`` invariant
        that the sandbox can only be touched from the thread that created it. The unsendable
        objects never escape the worker; this method returns only sendable plain Python data.
        """
        entry = self._get_or_create_entry(config)
        return entry.worker.execute(
            code=code,
            output_dir=entry.output_dir,
            build_contents=_build_execution_contents,
        )

    def _get_or_create_entry(self, config: _RunConfig) -> _SandboxEntry:
        cache_key = config.cache_key()
        with self._entries_lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                entry = self._create_entry(config)
                self._entries[cache_key] = entry
            return entry

    def close(self) -> None:
        """Shut down all per-entry worker threads and release per-entry resources.

        Safe to call multiple times. Each entry's sandbox/snapshot is disposed on the
        worker thread that created it to honor the PyO3 ``unsendable`` invariant.
        """
        with self._entries_lock:
            entries = list(self._entries.values())
            self._entries.clear()
        try:
            for entry in entries:
                entry.dispose()
        finally:
            # Drop our local strong references; entries' own refs to sandbox/snapshot
            # were already moved into the per-worker disposal closure inside dispose().
            del entries

    def _create_entry(self, config: _RunConfig) -> _SandboxEntry:
        input_dir_handle = TemporaryDirectory() if config.filesystem_enabled else None
        output_dir_handle = TemporaryDirectory() if config.filesystem_enabled else None

        if input_dir_handle is not None:
            _populate_input_dir(config=config, input_root=Path(input_dir_handle.name))

        sandbox_cls = _load_sandbox_class()

        def _create_sandbox() -> Any:
            try:
                return sandbox_cls(
                    backend=config.backend,
                    module=config.module,
                    module_path=config.module_path,
                    input_dir=input_dir_handle.name if input_dir_handle is not None else None,
                    output_dir=output_dir_handle.name if output_dir_handle is not None else None,
                )
            except ImportError as exc:
                raise RuntimeError(
                    "The selected Hyperlight backend is not installed or not supported on this platform. "
                    "Install a compatible backend package, such as `hyperlight-sandbox-backend-wasm`."
                ) from exc

        def _configure_sandbox(*, sandbox: Any, expand_missing_scheme: bool) -> None:
            for tool_obj in config.tools:
                sandbox.register_tool(tool_obj.name, _make_sandbox_callback(tool_obj))

            for allowed_domain in config.allowed_domains:
                for target in _allowed_domain_registration_targets(
                    target=allowed_domain.target,
                    expand_missing_scheme=expand_missing_scheme,
                ):
                    sandbox.allow_domain(
                        target,
                        methods=list(allowed_domain.methods) if allowed_domain.methods is not None else None,
                    )

        def _build_sandbox() -> tuple[Any, Any]:
            sandbox = _create_sandbox()
            _configure_sandbox(sandbox=sandbox, expand_missing_scheme=False)

            try:
                sandbox.run("None")
            except RuntimeError as exc:
                if not _should_retry_allowed_domain_registration(error=exc, allowed_domains=config.allowed_domains):
                    raise

                sandbox = _create_sandbox()
                _configure_sandbox(sandbox=sandbox, expand_missing_scheme=True)
                sandbox.run("None")

            snapshot = sandbox.snapshot()
            return sandbox, snapshot

        worker = _SandboxWorker()
        try:
            worker.initialize(_build_sandbox)
        except BaseException:
            worker.dispose()
            raise

        return _SandboxEntry(
            worker=worker,
            input_dir=input_dir_handle,
            output_dir=output_dir_handle,
        )


class HyperlightExecuteCodeTool(FunctionTool):
    """Execute Python code inside a Hyperlight sandbox."""

    def __init__(
        self,
        *,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        approval_mode: ApprovalMode | None = None,
        workspace_root: str | Path | None = None,
        file_mounts: FileMountInput | Sequence[FileMountInput] | None = None,
        allowed_domains: AllowedDomainInput | Sequence[AllowedDomainInput] | None = None,
        backend: str = DEFAULT_HYPERLIGHT_BACKEND,
        module: str | None = DEFAULT_HYPERLIGHT_MODULE,
        module_path: str | None = None,
        _registry: SandboxRuntime | None = None,
    ) -> None:
        super().__init__(
            name="execute_code",
            description=EXECUTE_CODE_TOOL_DESCRIPTION,
            approval_mode="never_require",
            func=self._run_code,
            input_model=EXECUTE_CODE_INPUT_SCHEMA,
        )
        self._state_lock = threading.RLock()
        self._registry = _registry or _SandboxRegistry()
        self._default_approval_mode: ApprovalMode = approval_mode or "never_require"
        self._workspace_root = _resolve_workspace_root(workspace_root)
        self._backend: str = backend
        self._module: str | None = module
        self._module_path: str | None = module_path
        self._managed_tools: list[FunctionTool] = []
        self._file_mounts: dict[str, FileMount] = {}
        self._allowed_domains: dict[str, AllowedDomain] = {}

        if tools is not None:
            self.add_tools(tools)
        if file_mounts is not None:
            self.add_file_mounts(file_mounts)
        if allowed_domains is not None:
            self.add_allowed_domains(allowed_domains)

        self._refresh_approval_mode()

    @property
    def description(self) -> str:
        state_lock = getattr(self, "_state_lock", None)
        if state_lock is None:
            return str(self.__dict__.get("description", EXECUTE_CODE_TOOL_DESCRIPTION))

        with state_lock:
            allowed_domains = sorted(self._allowed_domains.values(), key=lambda value: value.target)
            return build_execute_code_description(
                tools=self._managed_tools,
                filesystem_enabled=self._workspace_root is not None or bool(self._file_mounts),
                workspace_enabled=self._workspace_root is not None,
                mounted_paths=[_display_mount_path(mount.mount_path) for mount in self._file_mounts.values()],
                allowed_domains=allowed_domains,
            )

    @description.setter
    def description(self, value: str) -> None:
        self.__dict__["description"] = value

    def add_tools(
        self,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]],
    ) -> None:
        """Add sandbox-managed tools to this execute_code surface."""
        with self._state_lock:
            combined_tools = _collect_tools(self._managed_tools, tools)
            self._managed_tools = combined_tools
            self._refresh_approval_mode()

    def get_tools(self) -> list[FunctionTool]:
        """Return the currently managed sandbox tools."""
        with self._state_lock:
            return list(self._managed_tools)

    def remove_tool(self, name: str) -> None:
        """Remove one managed sandbox tool by name."""
        with self._state_lock:
            remaining_tools = [tool_obj for tool_obj in self._managed_tools if tool_obj.name != name]
            if len(remaining_tools) == len(self._managed_tools):
                raise KeyError(f"No managed tool named {name!r} is registered.")
            self._managed_tools = remaining_tools
            self._refresh_approval_mode()

    def clear_tools(self) -> None:
        """Remove all managed sandbox tools."""
        with self._state_lock:
            self._managed_tools = []
            self._refresh_approval_mode()

    def add_file_mounts(self, file_mounts: FileMountInput | Sequence[FileMountInput]) -> None:
        """Add one or more file mounts under `/input`.

        A single string uses the same relative path on the host and in the sandbox.
        Use a two-string tuple or `FileMount` when those paths differ.
        """
        if isinstance(file_mounts, str) or _is_file_mount_pair(file_mounts):
            normalized_mounts = [_normalize_file_mount_input(file_mounts)]
        else:
            normalized_mounts = [
                _normalize_file_mount_input(mount) for mount in cast(Sequence[FileMountInput], file_mounts)
            ]

        with self._state_lock:
            for mount in normalized_mounts:
                self._file_mounts[mount.mount_path] = mount

    def get_file_mounts(self) -> list[FileMount]:
        """Return the configured file mounts."""
        with self._state_lock:
            return [
                FileMount(host_path=mount.host_path, mount_path=_display_mount_path(mount.mount_path))
                for mount in self._file_mounts.values()
            ]

    def remove_file_mount(self, mount_path: str) -> None:
        """Remove one file mount by its sandbox path."""
        normalized_mount_path = _normalize_mount_path(mount_path)
        with self._state_lock:
            if normalized_mount_path not in self._file_mounts:
                raise KeyError(f"No file mount exists for {mount_path!r}.")
            del self._file_mounts[normalized_mount_path]

    def clear_file_mounts(self) -> None:
        """Remove all configured file mounts."""
        with self._state_lock:
            self._file_mounts.clear()

    def add_allowed_domains(self, domains: AllowedDomainInput | Sequence[AllowedDomainInput]) -> None:
        """Add one or more outbound allow-list entries."""
        if isinstance(domains, (str, AllowedDomain)) or _is_allowed_domain_pair(domains):
            normalized_domains = [_normalize_allowed_domain_input(domains)]
        else:
            normalized_domains = [
                _normalize_allowed_domain_input(domain) for domain in cast(Sequence[AllowedDomainInput], domains)
            ]

        with self._state_lock:
            for normalized_domain in normalized_domains:
                self._allowed_domains[normalized_domain.target] = normalized_domain

    def get_allowed_domains(self) -> list[AllowedDomain]:
        """Return the configured outbound allow-list entries."""
        with self._state_lock:
            return sorted(self._allowed_domains.values(), key=lambda value: value.target)

    def remove_allowed_domain(self, domain: str) -> None:
        """Remove one outbound allow-list entry."""
        normalized_domain = _normalize_domain(domain)
        with self._state_lock:
            if normalized_domain not in self._allowed_domains:
                raise KeyError(f"No allowed domain exists for {domain!r}.")
            del self._allowed_domains[normalized_domain]

    def clear_allowed_domains(self) -> None:
        """Remove all outbound allow-list entries."""
        with self._state_lock:
            self._allowed_domains.clear()

    def build_instructions(self, *, tools_visible_to_model: bool) -> str:
        """Build the current CodeAct instructions for this execute_code surface."""
        config = self._build_run_config()
        return build_codeact_instructions(
            tools=config.tools,
            tools_visible_to_model=tools_visible_to_model,
            filesystem_enabled=config.filesystem_enabled,
        )

    def create_run_tool(self) -> HyperlightExecuteCodeTool:
        """Create a run-scoped snapshot of this execute_code surface."""
        file_mounts = self.get_file_mounts()
        allowed_domains = self.get_allowed_domains()

        return HyperlightExecuteCodeTool(
            tools=self.get_tools(),
            approval_mode=self._default_approval_mode,
            workspace_root=self._workspace_root,
            file_mounts=file_mounts or None,
            allowed_domains=allowed_domains or None,
            backend=self._backend,
            module=self._module,
            module_path=self._module_path,
            _registry=self._registry,
        )

    def build_serializable_state(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the effective run state."""
        config = self._build_run_config()
        return {
            "backend": config.backend,
            "module": config.module,
            "module_path": config.module_path,
            "approval_mode": config.approval_mode,
            "tool_names": [tool_obj.name for tool_obj in config.tools],
            "filesystem_enabled": config.filesystem_enabled,
            "workspace_root": str(config.workspace_root) if config.workspace_root is not None else None,
            "file_mounts": [
                {
                    "host_path": str(mount.host_path),
                    "mount_path": _display_mount_path(mount.mount_path),
                }
                for mount in config.file_mounts
            ],
            "network_enabled": bool(config.allowed_domains),
            "allowed_domains": [
                {
                    "target": allowed_domain.target,
                    "methods": list(allowed_domain.methods) if allowed_domain.methods is not None else None,
                }
                for allowed_domain in config.allowed_domains
            ],
        }

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        self.__dict__["description"] = self.description
        return super().to_dict(exclude=exclude, exclude_none=exclude_none)

    def _refresh_approval_mode(self) -> None:
        self.approval_mode = _resolve_execute_code_approval_mode(
            base_approval_mode=self._default_approval_mode,
            tools=self._managed_tools,
        )

    def _build_run_config(self) -> _RunConfig:
        with self._state_lock:
            managed_tools = tuple(self._managed_tools)
            workspace_root = self._workspace_root
            stored_mounts = tuple(self._file_mounts.values())
            allowed_domains = tuple(sorted(self._allowed_domains.values(), key=lambda value: value.target))
            approval_mode = _resolve_execute_code_approval_mode(
                base_approval_mode=self._default_approval_mode,
                tools=managed_tools,
            )

        workspace_signature = _path_tree_signature(workspace_root) if workspace_root is not None else ()
        normalized_mounts = tuple(
            _NormalizedFileMount(
                host_path=Path(mount.host_path),
                mount_path=mount.mount_path,
                path_signature=_path_tree_signature(Path(mount.host_path)),
            )
            for mount in stored_mounts
        )

        return _RunConfig(
            backend=self._backend,
            module=self._module,
            module_path=self._module_path,
            approval_mode=approval_mode,
            tools=managed_tools,
            workspace_root=workspace_root,
            workspace_signature=workspace_signature,
            file_mounts=normalized_mounts,
            allowed_domains=allowed_domains,
        )

    async def _run_code(self, *, code: str) -> list[Content]:
        config = self._build_run_config()
        return await asyncio.to_thread(self._registry.execute, config=config, code=code)
