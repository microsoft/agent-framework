# Copyright (c) Microsoft. All rights reserved.

"""``MontyExecuteCodeTool`` - a ``FunctionTool`` that runs Python in Monty.

Mirrors the public API of ``HyperlightExecuteCodeTool`` for the subset that
applies to a pure-Python interpreter (no backends to choose from). By default
the Monty sandbox rejects OS / filesystem / network calls with
``PermissionError``; pass ``workspace_root`` or ``file_mounts`` to expose
scoped host directories, and the tool will capture files written under
``read-write`` mounts as ``Content`` items within per-execution capture limits.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import stat
from collections.abc import Callable, Iterator, Sequence
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any, cast

from agent_framework import Content, FunctionTool
from agent_framework._filesystem import _is_link_or_reparse_point  # pyright: ignore[reportPrivateUsage]
from agent_framework._tools import (
    ApprovalMode,
    _normalize_tool_description_format,  # pyright: ignore[reportPrivateUsage]
    _NormalizedToolDescriptionFormat,  # pyright: ignore[reportPrivateUsage]
    _ToolDescriptionFormat,  # pyright: ignore[reportPrivateUsage]
    normalize_tools,
)

from ._instructions import build_codeact_instructions, build_execute_code_description
from ._monty_bridge import InlineCodeBridge, generate_type_stubs
from ._types import FileMount, FileMountInput

logger = logging.getLogger("agent_framework")

EXECUTE_CODE_TOOL_NAME = "execute_code"
EXECUTE_CODE_TOOL_DESCRIPTION = "Execute Python in a Monty interpreter."

_FIDES_TOOL_PROPERTY_KEYS = frozenset({
    "source_integrity",
    "confidentiality",
    "max_allowed_confidentiality",
    "accepts_untrusted",
    "standing_guidance",
    "agent_framework.security.principals",
    "_agent_framework_internal_security_tool",
    "_mcp_trust_server_ifc",
})

#: Virtual path that the optional ``workspace_root`` directory is mounted at,
#: matching the Hyperlight default. Use ``file_mounts`` for any other path.
WORKSPACE_MOUNT_PATH = "/input"

#: Maximum bytes per captured output file. Oversized files are skipped and
#: reported in one omission summary per execution.
MAX_CAPTURED_FILE_BYTES = 5 * 1024 * 1024  # 5 MiB

#: Maximum captured files across all read-write mounts in one execution.
MAX_CAPTURED_FILES = 20

#: Maximum raw captured bytes across all read-write mounts in one execution.
MAX_CAPTURED_TOTAL_BYTES = 20 * 1024 * 1024  # 20 MiB

_CAPTURE_OMISSION_MESSAGE = "[files omitted: capture file-count or byte limits exceeded]"

EXECUTE_CODE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "_ExecuteCodeInput",
    "properties": {
        "code": {
            "type": "string",
            "title": "Code",
            "description": "Python code to execute in a Monty interpreter.",
        },
    },
    "required": ["code"],
}


def _collect_tools(*tool_groups: Any) -> list[FunctionTool]:
    """Merge tool groups, dropping any ``execute_code`` entries and deduping by name."""
    tools_by_name: dict[str, FunctionTool] = {}

    for tool_group in tool_groups:
        normalized_group = normalize_tools(tool_group)
        for tool_obj in normalized_group:
            if not isinstance(tool_obj, FunctionTool):
                continue
            if tool_obj.name == EXECUTE_CODE_TOOL_NAME:
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


def _normalize_mount_path(mount_path: str) -> str:
    """Normalize a virtual mount path to a clean POSIX absolute path."""
    raw = mount_path.strip().replace("\\", "/")
    if not raw:
        raise ValueError("mount_path must not be empty.")
    pure = PurePosixPath(raw)
    parts = [part for part in pure.parts if part not in {"", "/", "."}]
    if any(part == ".." for part in parts):
        raise ValueError("mount_path must not contain '..' segments.")
    if not parts:
        raise ValueError("mount_path must point to a concrete absolute path.")
    return "/" + "/".join(parts)


def _resolve_existing_directory(value: str | Path) -> Path:
    resolved = Path(value).expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"Path {value!r} must point to an existing directory.")
    return resolved


def _is_file_mount_pair(value: Any) -> bool:
    if not isinstance(value, tuple) or isinstance(value, FileMount):
        return False
    items = cast("tuple[object, ...]", value)
    if len(items) != 2:
        return False
    host_path, mount_path = items
    return isinstance(host_path, (str, Path)) and isinstance(mount_path, str)


def _normalize_file_mount(file_mount: FileMountInput) -> FileMount:
    if isinstance(file_mount, FileMount):
        host_path = file_mount.host_path
        mount_path = file_mount.mount_path
        mode = file_mount.mode
        write_limit = file_mount.write_bytes_limit
    elif isinstance(file_mount, str):
        host_path = file_mount
        mount_path = file_mount
        mode = "overlay"
        write_limit = None
    else:
        host_path, mount_path = file_mount
        mode = "overlay"
        write_limit = None

    return FileMount(
        host_path=_resolve_existing_directory(host_path),
        mount_path=_normalize_mount_path(mount_path),
        mode=mode,
        write_bytes_limit=write_limit,
    )


def _to_monty_mount(file_mount: FileMount) -> Any:
    """Convert a public :class:`FileMount` to Monty's ``MountDir``.

    Imports lazily through the bridge's loader so missing-dependency errors
    surface as the same actionable ``RuntimeError`` the rest of the package
    raises, rather than a bare ``ImportError`` from a top-level import.
    """
    from ._monty_bridge import load_monty  # avoid top-level pydantic_monty import

    monty_module = load_monty()
    return monty_module.MountDir(
        virtual_path=file_mount.mount_path,
        host_path=str(file_mount.host_path),
        mode=file_mount.mode,
        write_bytes_limit=file_mount.write_bytes_limit,
    )


def _make_tool_callback(tool_obj: FunctionTool) -> Callable[..., Any]:
    """Return an async callable that invokes ``tool_obj`` with the bridge's kwargs.

    Returns the raw native value (no ``Content`` wrapping) so the Monty interpreter
    receives real Python objects. ``FunctionTool.invoke`` accepts direct keyword
    arguments and handles both sync and async underlying functions internally.
    """
    return partial(tool_obj.invoke, skip_parsing=True)


def _fides_metadata_snapshot(tool_obj: FunctionTool) -> dict[str, str]:
    """Capture FIDES metadata for compatibility-warning deduplication."""
    properties = tool_obj.additional_properties or {}
    return {key: repr(value) for key, value in properties.items() if key in _FIDES_TOOL_PROPERTY_KEYS}


def _warn_unsupported_fides_tools(
    tools: Sequence[FunctionTool],
    warned_metadata: list[tuple[FunctionTool, dict[str, str]]],
) -> None:
    """Warn when newly registered or changed FIDES metadata is observed."""
    for tool_obj in tools:
        snapshot = _fides_metadata_snapshot(tool_obj)
        previous = next(
            (metadata for registered, metadata in warned_metadata if registered is tool_obj),
            None,
        )

        if snapshot and snapshot != previous:
            logger.warning(
                "FIDES is not supported with CodeAct providers. Metadata on tool '%s' will not be enforced "
                "through function middleware for calls made inside generated code. "
                "Keep FIDES-dependent tools as direct agent tools.",
                tool_obj.name,
            )

        warned_metadata[:] = [
            (registered, metadata) for registered, metadata in warned_metadata if registered is not tool_obj
        ]

        if snapshot:
            warned_metadata.append((tool_obj, snapshot))


class MontyExecuteCodeTool(FunctionTool):
    """Execute Python code inside a Monty interpreter.

    Tools registered on this object are available inside the interpreter as
    typed async functions (e.g. ``await tool_name(...)``). Argument types are
    validated by the [ty](https://docs.astral.sh/ty/) type checker before any
    host tool runs.

    Optional filesystem access is exposed via:

    - ``workspace_root`` — auto-mounts a host directory at ``/input`` (matching
      Hyperlight's default).
    - ``file_mounts`` — extra :class:`FileMount` entries for fine-grained
      control (mount path, read-only / read-write / overlay mode, write
      byte caps).

    Files written by sandboxed code to any **read-write** mount are scanned
    after execution and returned as ``Content.from_data`` items, mirroring
    Hyperlight's ``/output`` flow.

    ``resource_limits`` is forwarded to Monty's ``ResourceLimits`` to cap CPU
    time, memory, output size, recursion depth, and GC frequency.

    ``tool_description_format`` controls parameter documentation in both the
    description and instructions: ``"compact"`` (default) or ``"json"`` globally,
    or a mapping of exact, case-sensitive tool names to either format. Missing
    names use compact; rich schemas fall back to full JSON Schema. Mappings
    are copied and retain entries for tools registered later.

    All mutators (``add_tools``, ``add_file_mounts`` etc.) must be called from
    the same task/thread that owns the tool. Monty itself runs on the event
    loop, so no internal locking is needed.
    """

    def __init__(
        self,
        *,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        approval_mode: ApprovalMode | None = None,
        workspace_root: str | Path | None = None,
        file_mounts: FileMountInput | Sequence[FileMountInput] | None = None,
        resource_limits: dict[str, Any] | None = None,
        tool_description_format: _ToolDescriptionFormat = "compact",
        _fides_warned_metadata: list[tuple[FunctionTool, dict[str, str]]] | None = None,
    ) -> None:
        super().__init__(
            name=EXECUTE_CODE_TOOL_NAME,
            description=EXECUTE_CODE_TOOL_DESCRIPTION,
            approval_mode="never_require",
            func=self._run_code,
            input_model=EXECUTE_CODE_INPUT_SCHEMA,
        )
        self._default_approval_mode: ApprovalMode = approval_mode or "never_require"
        self._tool_description_format: _NormalizedToolDescriptionFormat = _normalize_tool_description_format(
            tool_description_format
        )
        self._managed_tools: list[FunctionTool] = []
        self._fides_warned_metadata: list[tuple[FunctionTool, dict[str, str]]] = list(_fides_warned_metadata or [])
        self._workspace_root: Path | None = (
            _resolve_existing_directory(workspace_root) if workspace_root is not None else None
        )
        self._file_mounts: dict[str, FileMount] = {}
        self._resource_limits: dict[str, Any] | None = dict(resource_limits) if resource_limits else None

        if tools is not None:
            self.add_tools(tools)
        if file_mounts is not None:
            self.add_file_mounts(file_mounts)

        self._refresh_approval_mode()

    @property
    def description(self) -> str:
        # During FunctionTool.__init__, ``_managed_tools`` is not yet set.
        if not hasattr(self, "_managed_tools"):
            return str(self.__dict__.get("description", EXECUTE_CODE_TOOL_DESCRIPTION))
        return build_execute_code_description(
            tools=self._managed_tools,
            mounts=self._effective_mounts(),
            tool_description_format=self._tool_description_format,
        )

    @description.setter
    def description(self, value: str) -> None:
        self.__dict__["description"] = value

    def add_tools(
        self,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]],
    ) -> None:
        """Add Monty-side tools to this execute_code surface."""
        new_tools = _collect_tools(tools)
        self._managed_tools = _collect_tools(self._managed_tools, new_tools)
        self._fides_warned_metadata[:] = [
            (registered, metadata)
            for registered, metadata in self._fides_warned_metadata
            if any(registered is current for current in self._managed_tools)
        ]
        _warn_unsupported_fides_tools(new_tools, self._fides_warned_metadata)
        self._refresh_approval_mode()

    def get_tools(self) -> list[FunctionTool]:
        """Return the currently managed Monty tools."""
        return list(self._managed_tools)

    def remove_tool(self, name: str) -> None:
        """Remove one managed Monty tool by name."""
        remaining_tools = [tool_obj for tool_obj in self._managed_tools if tool_obj.name != name]
        if len(remaining_tools) == len(self._managed_tools):
            raise KeyError(f"No managed tool named {name!r} is registered.")
        self._managed_tools = remaining_tools
        self._fides_warned_metadata[:] = [
            (registered, metadata)
            for registered, metadata in self._fides_warned_metadata
            if any(registered is current for current in remaining_tools)
        ]
        self._refresh_approval_mode()

    def clear_tools(self) -> None:
        """Remove all managed Monty tools."""
        self._managed_tools = []
        self._fides_warned_metadata.clear()
        self._refresh_approval_mode()

    def add_file_mounts(self, file_mounts: FileMountInput | Sequence[FileMountInput]) -> None:
        """Add one or more file mounts.

        A single string mounts the same path on both sides. Use a
        ``(host_path, mount_path)`` tuple or :class:`FileMount` when the paths
        differ or when you need to set the mount mode / write limit.
        """
        if isinstance(file_mounts, (str, FileMount)) or _is_file_mount_pair(file_mounts):
            normalized = [_normalize_file_mount(cast("FileMountInput", file_mounts))]
        else:
            normalized = [_normalize_file_mount(item) for item in cast("Sequence[FileMountInput]", file_mounts)]

        for mount in normalized:
            self._file_mounts[mount.mount_path] = mount

    def get_file_mounts(self) -> list[FileMount]:
        """Return the configured file mounts (excluding ``workspace_root``)."""
        return list(self._file_mounts.values())

    def remove_file_mount(self, mount_path: str) -> None:
        """Remove one file mount by its sandbox path."""
        normalized = _normalize_mount_path(mount_path)
        if normalized not in self._file_mounts:
            raise KeyError(f"No file mount exists for {mount_path!r}.")
        del self._file_mounts[normalized]

    def clear_file_mounts(self) -> None:
        """Remove all configured file mounts."""
        self._file_mounts.clear()

    @property
    def workspace_root(self) -> Path | None:
        """Return the configured workspace root, if any."""
        return self._workspace_root

    @property
    def resource_limits(self) -> dict[str, Any] | None:
        """Return the configured Monty :class:`pydantic_monty.ResourceLimits`, if any."""
        return dict(self._resource_limits) if self._resource_limits else None

    def build_instructions(self, *, tools_visible_to_model: bool) -> str:
        """Build the current CodeAct instructions for this execute_code surface."""
        return build_codeact_instructions(
            tools=list(self._managed_tools),
            tools_visible_to_model=tools_visible_to_model,
            mounts=self._effective_mounts(),
            tool_description_format=self._tool_description_format,
        )

    def create_run_tool(self) -> MontyExecuteCodeTool:
        """Create a run-scoped snapshot of this execute_code surface."""
        tools = self.get_tools()
        _warn_unsupported_fides_tools(tools, self._fides_warned_metadata)
        return MontyExecuteCodeTool(
            _fides_warned_metadata=self._fides_warned_metadata,
            tools=tools,
            approval_mode=self._default_approval_mode,
            workspace_root=self._workspace_root,
            file_mounts=list(self._file_mounts.values()) or None,
            resource_limits=self._resource_limits,
            tool_description_format=self._tool_description_format,
        )

    def build_serializable_state(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the effective run state."""
        approval_mode = _resolve_execute_code_approval_mode(
            base_approval_mode=self._default_approval_mode,
            tools=self._managed_tools,
        )
        mounts = self._effective_mounts()
        return {
            "runtime": "monty",
            "approval_mode": approval_mode,
            "tool_names": [tool_obj.name for tool_obj in self._managed_tools],
            "tool_description_format": (
                dict(self._tool_description_format)
                if isinstance(self._tool_description_format, dict)
                else self._tool_description_format
            ),
            "workspace_root": str(self._workspace_root) if self._workspace_root is not None else None,
            "file_mounts": [
                {
                    "host_path": str(mount.host_path),
                    "mount_path": mount.mount_path,
                    "mode": mount.mode,
                    "write_bytes_limit": mount.write_bytes_limit,
                }
                for mount in mounts
            ],
            "resource_limits": dict(self._resource_limits) if self._resource_limits else None,
        }

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        # Materialize the dynamic description so the dump captures the current tool list.
        self.__dict__["description"] = self.description
        return super().to_dict(exclude=exclude, exclude_none=exclude_none)

    def _refresh_approval_mode(self) -> None:
        self.approval_mode = _resolve_execute_code_approval_mode(
            base_approval_mode=self._default_approval_mode,
            tools=self._managed_tools,
        )

    def _build_tool_map(self, tools: Sequence[FunctionTool]) -> dict[str, Callable[..., Any]]:
        return {tool_obj.name: _make_tool_callback(tool_obj) for tool_obj in tools}

    def _build_type_stub_map(self, tools: Sequence[FunctionTool]) -> dict[str, Callable[..., Any]]:
        """Return a name -> underlying-Python-callable map for type stub generation.

        The raw Python function attached to the ``FunctionTool`` carries the
        author's actual ``Annotated`` parameter types, which are what we want
        ``ty`` to validate against. Tools without an attached function (e.g.
        ``declaration_only`` tools) are skipped.
        """
        stub_map: dict[str, Callable[..., Any]] = {}
        for tool_obj in tools:
            func = getattr(tool_obj, "func", None)
            if callable(func):
                stub_map[tool_obj.name] = func
        return stub_map

    def _effective_mounts(self) -> list[FileMount]:
        """Combine ``workspace_root`` (if set) with the explicit ``file_mounts``."""
        mounts: list[FileMount] = []
        if self._workspace_root is not None and WORKSPACE_MOUNT_PATH not in self._file_mounts:
            mounts.append(
                FileMount(
                    host_path=self._workspace_root,
                    mount_path=WORKSPACE_MOUNT_PATH,
                    mode="read-write",
                    write_bytes_limit=None,
                )
            )
        mounts.extend(self._file_mounts.values())
        return mounts

    async def _run_code(self, *, code: str) -> list[Content]:
        tools = list(self._managed_tools)
        mounts = self._effective_mounts()

        tool_map = self._build_tool_map(tools)
        stub_map = self._build_type_stub_map(tools)
        type_stubs = generate_type_stubs(stub_map) if stub_map else None

        # Snapshot mtimes of host files in read-write mounts so we can later
        # identify which files the sandbox actually touched.
        pre_state = _snapshot_writable_mounts(mounts)

        bridge = InlineCodeBridge(
            tool_map,
            type_stubs=type_stubs,
            mounts=[_to_monty_mount(mount) for mount in mounts] or None,
            resource_limits=self._resource_limits,
        )

        try:
            result = await bridge.run(code)
        except Exception as exc:
            return [
                Content.from_error(
                    message="Execution error",
                    error_details=f"{type(exc).__name__}: {exc}",
                ),
            ]

        contents = _build_execution_contents(result=result)
        contents.extend(_capture_written_files(mounts, pre_state))
        return contents


def _build_execution_contents(*, result: dict[str, Any]) -> list[Content]:
    stdout = str(result.get("stdout") or "").replace("\r\n", "\n")
    output_value = result.get("output")
    truncated = bool(result.get("truncated"))

    outputs: list[Content] = []
    if stdout:
        text = stdout
        if truncated:
            text = f"{text}\n\n[stdout truncated]"
        outputs.append(Content.from_text(text))
    elif truncated:
        outputs.append(Content.from_text("[stdout truncated]"))

    if output_value is not None:
        try:
            serialized_output = json.dumps(output_value, ensure_ascii=False)
        except (TypeError, ValueError):
            serialized_output = repr(output_value)
        outputs.append(Content.from_text(serialized_output))

    if not outputs:
        outputs.append(Content.from_text("Code executed successfully without output."))

    return outputs


def _iter_real_files(root: Path) -> Iterator[Path]:
    """Walk ``root`` recursively, yielding only real regular files.

    ``Path.rglob`` follows directory symlinks by default, which combined with
    ``Path.is_file()`` / ``Path.read_bytes()`` (both follow symlinks) would let
    an attacker who controls the workspace pre-place a symlink to a host file
    or directory and have our post-execution capture surface it. Skip symlinks,
    Windows junctions, and other reparse points at every directory level.
    """
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            if _is_link_or_reparse_point(current):
                continue
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if _is_link_or_reparse_point(entry):
                    continue
                entry_stat = entry.lstat()
                if stat.S_ISDIR(entry_stat.st_mode):
                    stack.append(entry)
                elif stat.S_ISREG(entry_stat.st_mode):
                    yield entry
            except OSError:
                continue


def _safe_capture_file_stat(*, root: Path, entry: Path) -> os.stat_result | None:
    """Return the verified stat for a real regular file beneath ``root``."""
    try:
        relative = entry.relative_to(root)
    except ValueError:
        return None

    current = root
    try:
        if _is_link_or_reparse_point(current):
            return None
        for part in relative.parts:
            current /= part
            if _is_link_or_reparse_point(current):
                return None
        entry_stat = current.lstat()
    except OSError:
        return None
    return entry_stat if stat.S_ISREG(entry_stat.st_mode) else None


class _CaptureSizeLimitError(ValueError):
    """A file exceeded its remaining capture byte allowance."""


def _read_validated_file(
    *,
    root: Path,
    entry: Path,
    expected: os.stat_result,
    max_bytes: int,
) -> bytes | None:
    """Read ``entry`` through one descriptor that is checked against the validated file.

    ``Path.read_bytes()`` reopens the path, so a component swapped for a link or junction after
    validation would be followed. Opening first, comparing the descriptor with the validated ``lstat``
    identity, and revalidating the path afterwards rejects such a swap. Windows has no no-follow open,
    so the check is not atomic there, but an undetected swap would have to be applied, reverted, and
    applied again around the checks. Returns ``None`` when the file identity changed or cannot be read
    safely. Raises ``_CaptureSizeLimitError`` if the file exceeds ``max_bytes``.
    """
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(entry, flags)
    except OSError:
        return None
    try:
        opened = os.fstat(fd)
        identity = (opened.st_dev, opened.st_ino)
        if not stat.S_ISREG(opened.st_mode) or identity != (expected.st_dev, expected.st_ino):
            return None
        rechecked = _safe_capture_file_stat(root=root, entry=entry)
        if rechecked is None or (rechecked.st_dev, rechecked.st_ino) != identity:
            return None
        if opened.st_size > max_bytes:
            raise _CaptureSizeLimitError("File exceeds the capture byte limit.")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise _CaptureSizeLimitError("File grew beyond the capture byte limit.")
        return data
    except OSError:
        return None
    finally:
        os.close(fd)


def _snapshot_writable_mounts(mounts: Sequence[FileMount]) -> dict[str, dict[str, tuple[int, int]]]:
    """Capture (size, mtime_ns) for every real host file under read-write mounts.

    Returns ``{mount_path: {relative_posix_path: (size, mtime_ns)}}``. Used by
    :func:`_capture_written_files` to detect new or modified files after the run.
    Read-only and overlay mounts are skipped because their writes do not
    propagate to the host. Links and reparse points are deliberately skipped so
    an attacker cannot escape the mount through a host path outside the workspace.
    """
    snapshot: dict[str, dict[str, tuple[int, int]]] = {}
    for mount in mounts:
        if mount.mode != "read-write":
            continue
        host_root = Path(mount.host_path)
        per_mount: dict[str, tuple[int, int]] = {}
        for entry in _iter_real_files(host_root):
            try:
                entry_stat = entry.lstat()  # lstat: never follow symlinks (defensive)
            except OSError:
                continue
            relative = entry.relative_to(host_root).as_posix()
            per_mount[relative] = (int(entry_stat.st_size), int(entry_stat.st_mtime_ns))
        snapshot[mount.mount_path] = per_mount
    return snapshot


def _capture_written_files(
    mounts: Sequence[FileMount],
    pre_state: dict[str, dict[str, tuple[int, int]]],
) -> list[Content]:
    """Return :class:`Content` items for files the sandbox wrote during the run.

    New or modified real regular files under read-write mounts are surfaced as
    ``Content.from_data`` with a ``path`` annotation in ``additional_properties``.
    File-count and raw-byte budgets apply across all mounts, with one summary
    for files omitted by capture limits. Links and reparse points are skipped at
    every directory level, and bounded reads use descriptors verified against
    the validated paths.
    """
    captured: list[Content] = []
    total_bytes = 0
    omitted = False
    for mount in mounts:
        if mount.mode != "read-write":
            continue
        host_root = Path(mount.host_path)
        before = pre_state.get(mount.mount_path, {})
        for entry in sorted(_iter_real_files(host_root)):
            entry_stat = _safe_capture_file_stat(root=host_root, entry=entry)
            if entry_stat is None:
                continue
            relative = entry.relative_to(host_root).as_posix()
            current = (int(entry_stat.st_size), int(entry_stat.st_mtime_ns))
            if before.get(relative) == current:
                continue  # Unchanged.
            if len(captured) >= MAX_CAPTURED_FILES:
                captured.append(Content.from_text(_CAPTURE_OMISSION_MESSAGE))
                return captured
            sandbox_path = f"{mount.mount_path.rstrip('/')}/{relative}"
            max_bytes = min(MAX_CAPTURED_FILE_BYTES, MAX_CAPTURED_TOTAL_BYTES - total_bytes)
            if entry_stat.st_size > max_bytes:
                omitted = True
                continue
            try:
                data = _read_validated_file(root=host_root, entry=entry, expected=entry_stat, max_bytes=max_bytes)
            except _CaptureSizeLimitError:
                omitted = True
                continue
            if data is None:
                continue
            media_type = mimetypes.guess_type(entry.name)[0] or "application/octet-stream"
            captured.append(
                Content.from_data(
                    data=data,
                    media_type=media_type,
                    additional_properties={"path": sandbox_path},
                )
            )
            total_bytes += len(data)
    if omitted:
        captured.append(Content.from_text(_CAPTURE_OMISSION_MESSAGE))
    return captured
