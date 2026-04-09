# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import ast
import copy
import mimetypes
import shutil
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Protocol
from urllib.parse import urlparse

from agent_framework import Content, FunctionTool
from agent_framework._tools import ApprovalMode, normalize_tools
from pydantic import BaseModel, Field

from ._instructions import build_codeact_instructions, build_execute_code_description
from ._types import FileMount, FilesystemMode, NetworkMode

DEFAULT_HYPERLIGHT_BACKEND = "wasm"
DEFAULT_HYPERLIGHT_MODULE = "python_guest.path"
EXECUTE_CODE_INPUT_DESCRIPTION = "Python code to execute in an isolated Hyperlight sandbox."


class _ExecuteCodeInput(BaseModel):
    code: Annotated[str, Field(description=EXECUTE_CODE_INPUT_DESCRIPTION)]


@dataclass(frozen=True, slots=True)
class _StoredFileMount:
    host_path: Path
    mount_path: str


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
    filesystem_mode: FilesystemMode
    workspace_root: Path | None
    workspace_signature: tuple[tuple[str, int, int], ...]
    file_mounts: tuple[_NormalizedFileMount, ...]
    network_mode: NetworkMode
    allowed_domains: tuple[str, ...]
    allowed_http_methods: tuple[str, ...]

    @property
    def mounted_paths(self) -> tuple[str, ...]:
        return tuple(_display_mount_path(mount.mount_path) for mount in self.file_mounts)

    def cache_key(self) -> tuple[Any, ...]:
        return (
            self.backend,
            self.module,
            self.module_path,
            self.approval_mode,
            tuple((tool_obj.name, id(tool_obj)) for tool_obj in self.tools),
            self.filesystem_mode,
            str(self.workspace_root) if self.workspace_root is not None else None,
            self.workspace_signature,
            tuple((mount.mount_path, str(mount.host_path), mount.path_signature) for mount in self.file_mounts),
            self.network_mode,
            self.allowed_domains,
            self.allowed_http_methods,
        )


class SandboxRuntime(Protocol):
    def execute(self, *, config: _RunConfig, code: str) -> list[Content]: ...


@dataclass
class _SandboxEntry:
    sandbox: Any
    snapshot: Any
    input_dir: TemporaryDirectory[str] | None
    output_dir: TemporaryDirectory[str] | None
    lock: threading.RLock


def _load_sandbox_class() -> type[Any]:
    try:
        from hyperlight_sandbox import Sandbox
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Hyperlight support requires `hyperlight-sandbox`, `hyperlight-sandbox-python-guest`, "
            "and a compatible backend package such as `hyperlight-sandbox-backend-wasm`."
        ) from exc

    return Sandbox


def _passthrough_result_parser(result: Any) -> str:
    return repr(result)


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


def _normalize_domain(target: str) -> str:
    candidate = target.strip()
    if not candidate:
        raise ValueError("Domain entries must not be empty.")

    parsed = urlparse(candidate if "://" in candidate else f"//{candidate}")
    normalized = (parsed.netloc or parsed.path).strip().rstrip("/")
    if not normalized:
        raise ValueError(f"Could not normalize domain entry: {target!r}.")
    return normalized.lower()


def _normalize_http_method(method: str) -> str:
    normalized = method.strip().upper()
    if not normalized:
        raise ValueError("HTTP method entries must not be empty.")
    return normalized


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


def _parse_output_files(*, sandbox: Any, output_dir: TemporaryDirectory[str] | None) -> list[Content]:
    if output_dir is None or not hasattr(sandbox, "get_output_files"):
        return []

    try:
        output_files = sandbox.get_output_files()
    except Exception:
        return []

    contents: list[Content] = []
    root = Path(output_dir.name)

    for output_file in output_files:
        raw_path = str(output_file).replace("\\", "/")
        pure_path = PurePosixPath(raw_path)
        parts = [part for part in pure_path.parts if part not in {"", "/", "."}]
        if parts and parts[0] == "output":
            parts = parts[1:]
        if not parts or any(part == ".." for part in parts):
            continue

        relative_path = "/".join(parts)
        host_path = root.joinpath(*parts)
        if host_path.is_file():
            contents.append(_create_file_content(host_path, relative_path=relative_path))

    return contents


def _build_execution_contents(
    *,
    result: Any,
    sandbox: Any,
    output_dir: TemporaryDirectory[str] | None,
) -> list[Content]:
    success = bool(getattr(result, "success", False))
    stdout = str(getattr(result, "stdout", "") or "").replace("\r\n", "\n") or None
    stderr = str(getattr(result, "stderr", "") or "").replace("\r\n", "\n") or None
    outputs: list[Content] = []

    if stdout is not None:
        outputs.append(Content.from_text(stdout, raw_representation=result))

    outputs.extend(_parse_output_files(sandbox=sandbox, output_dir=output_dir))

    if success:
        if stderr is not None:
            outputs.append(Content.from_text(stderr, raw_representation=result))
        if not outputs:
            outputs.append(Content.from_text("Code executed successfully without output."))
        return [Content.from_code_interpreter_tool_result(outputs=outputs, raw_representation=result)]

    error_details = stderr or "Unknown sandbox error"
    outputs.append(
        Content.from_error(
            message="Execution error",
            error_details=error_details,
            raw_representation=result,
        )
    )
    return [Content.from_code_interpreter_tool_result(outputs=outputs, raw_representation=result)]


def _make_sandbox_callback(tool_obj: FunctionTool) -> Callable[..., Any]:
    sandbox_tool = copy.copy(tool_obj)
    sandbox_tool.result_parser = _passthrough_result_parser

    async def _callback(**kwargs: Any) -> Any:
        contents = await sandbox_tool.invoke(arguments=kwargs)

        values: list[Any] = []
        for content in contents:
            if content.type == "text" and content.text is not None:
                try:
                    values.append(ast.literal_eval(content.text))
                except (SyntaxError, ValueError):
                    values.append(content.text)
                continue

            values.append(content.to_dict())

        if len(values) == 1:
            return values[0]
        return values

    return _callback


class _SandboxRegistry:
    def __init__(self) -> None:
        self._entries: dict[tuple[Any, ...], _SandboxEntry] = {}
        self._entries_lock = threading.RLock()

    def execute(self, *, config: _RunConfig, code: str) -> list[Content]:
        cache_key = config.cache_key()
        with self._entries_lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                entry = self._create_entry(config)
                self._entries[cache_key] = entry

        with entry.lock:
            entry.sandbox.restore(entry.snapshot)
            result = entry.sandbox.run(code=code)
            return _build_execution_contents(result=result, sandbox=entry.sandbox, output_dir=entry.output_dir)

    def _create_entry(self, config: _RunConfig) -> _SandboxEntry:
        input_dir_handle = TemporaryDirectory() if config.filesystem_mode != "none" else None
        output_dir_handle = TemporaryDirectory() if config.filesystem_mode == "read_write" else None

        if input_dir_handle is not None:
            _populate_input_dir(config=config, input_root=Path(input_dir_handle.name))

        sandbox_cls = _load_sandbox_class()
        try:
            sandbox = sandbox_cls(
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

        for tool_obj in config.tools:
            sandbox.register_tool(tool_obj.name, _make_sandbox_callback(tool_obj))

        if config.network_mode == "allow_list":
            methods = list(config.allowed_http_methods) or None
            for domain in config.allowed_domains:
                sandbox.allow_domain(domain, methods=methods)

        sandbox.run("None")
        snapshot = sandbox.snapshot()
        return _SandboxEntry(
            sandbox=sandbox,
            snapshot=snapshot,
            input_dir=input_dir_handle,
            output_dir=output_dir_handle,
            lock=threading.RLock(),
        )


class HyperlightExecuteCodeTool(FunctionTool):
    """Execute Python code inside a Hyperlight sandbox."""

    def __init__(
        self,
        *,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        approval_mode: ApprovalMode | None = None,
        filesystem_mode: FilesystemMode = "none",
        workspace_root: str | Path | None = None,
        file_mounts: FileMount | Sequence[FileMount] | None = None,
        network_mode: NetworkMode = "none",
        allowed_domains: str | Sequence[str] | None = None,
        allowed_http_methods: str | Sequence[str] | None = None,
        backend: str = DEFAULT_HYPERLIGHT_BACKEND,
        module: str | None = DEFAULT_HYPERLIGHT_MODULE,
        module_path: str | None = None,
        _registry: SandboxRuntime | None = None,
    ) -> None:
        super().__init__(
            name="execute_code",
            description=EXECUTE_CODE_INPUT_DESCRIPTION,
            approval_mode="never_require",
            func=self._run_code,
            input_model=_ExecuteCodeInput,
        )
        self._state_lock = threading.RLock()
        self._registry = _registry or _SandboxRegistry()
        self._default_approval_mode: ApprovalMode = approval_mode or "never_require"
        self._filesystem_mode: FilesystemMode = filesystem_mode
        self._workspace_root = _resolve_workspace_root(workspace_root)
        if self._filesystem_mode == "none" and self._workspace_root is not None:
            raise ValueError("workspace_root requires filesystem_mode to be 'read_only' or 'read_write'.")
        self._network_mode: NetworkMode = network_mode
        self._backend: str = backend
        self._module: str | None = module
        self._module_path: str | None = module_path
        self._managed_tools: list[FunctionTool] = []
        self._file_mounts: dict[str, _StoredFileMount] = {}
        self._allowed_domains: set[str] = set()
        self._allowed_http_methods: set[str] = set()

        if tools is not None:
            self.add_tools(tools)
        if file_mounts is not None:
            self.add_file_mounts(file_mounts)
        if allowed_http_methods is not None:
            self.add_allowed_http_methods(allowed_http_methods)
        if allowed_domains is not None:
            self.add_allowed_domains(allowed_domains)

        self._refresh_approval_mode()

    @property
    def description(self) -> str:
        state_lock = getattr(self, "_state_lock", None)
        if state_lock is None:
            return str(self.__dict__.get("description", EXECUTE_CODE_INPUT_DESCRIPTION))

        with state_lock:
            return build_execute_code_description(
                tools=self._managed_tools,
                filesystem_mode=self._filesystem_mode,
                workspace_enabled=self._workspace_root is not None,
                mounted_paths=[_display_mount_path(mount.mount_path) for mount in self._file_mounts.values()],
                network_mode=self._network_mode,
                allowed_domains=sorted(self._allowed_domains),
                allowed_http_methods=sorted(self._allowed_http_methods),
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

    def add_file_mounts(self, file_mounts: FileMount | Sequence[FileMount]) -> None:
        """Add one or more file mounts under `/input`."""
        if self._filesystem_mode == "none":
            raise ValueError("File mounts require filesystem_mode to be 'read_only' or 'read_write'.")

        mounts = [file_mounts] if isinstance(file_mounts, FileMount) else list(file_mounts)
        normalized_mounts = [
            _StoredFileMount(
                host_path=_resolve_existing_path(mount.host_path),
                mount_path=_normalize_mount_path(mount.mount_path),
            )
            for mount in mounts
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

    def add_allowed_domains(self, domains: str | Sequence[str]) -> None:
        """Add one or more outbound allow-list domains."""
        if self._network_mode == "none":
            raise ValueError("Allowed domains require network_mode='allow_list'.")

        normalized_domains = (
            {_normalize_domain(domains)}
            if isinstance(domains, str)
            else {_normalize_domain(domain) for domain in domains}
        )
        with self._state_lock:
            self._allowed_domains.update(normalized_domains)

    def get_allowed_domains(self) -> list[str]:
        """Return the configured outbound allow-list domains."""
        with self._state_lock:
            return sorted(self._allowed_domains)

    def remove_allowed_domain(self, domain: str) -> None:
        """Remove one outbound allow-list domain."""
        normalized_domain = _normalize_domain(domain)
        with self._state_lock:
            if normalized_domain not in self._allowed_domains:
                raise KeyError(f"No allowed domain exists for {domain!r}.")
            self._allowed_domains.remove(normalized_domain)

    def clear_allowed_domains(self) -> None:
        """Remove all outbound allow-list domains."""
        with self._state_lock:
            self._allowed_domains.clear()

    def add_allowed_http_methods(self, methods: str | Sequence[str]) -> None:
        """Add one or more outbound HTTP methods for the allow-list policy."""
        if self._network_mode == "none":
            raise ValueError("Allowed HTTP methods require network_mode='allow_list'.")

        normalized_methods = (
            {_normalize_http_method(methods)}
            if isinstance(methods, str)
            else {_normalize_http_method(method) for method in methods}
        )
        with self._state_lock:
            self._allowed_http_methods.update(normalized_methods)

    def get_allowed_http_methods(self) -> list[str]:
        """Return the configured outbound allow-list HTTP methods."""
        with self._state_lock:
            return sorted(self._allowed_http_methods)

    def remove_allowed_http_method(self, method: str) -> None:
        """Remove one outbound allow-list HTTP method."""
        normalized_method = _normalize_http_method(method)
        with self._state_lock:
            if normalized_method not in self._allowed_http_methods:
                raise KeyError(f"No allowed HTTP method exists for {method!r}.")
            self._allowed_http_methods.remove(normalized_method)

    def clear_allowed_http_methods(self) -> None:
        """Remove all outbound allow-list HTTP methods."""
        with self._state_lock:
            self._allowed_http_methods.clear()

    def build_instructions(self, *, tools_visible_to_model: bool) -> str:
        """Build the current CodeAct instructions for this execute_code surface."""
        config = self._build_run_config()
        return build_codeact_instructions(
            tools=config.tools,
            tools_visible_to_model=tools_visible_to_model,
            filesystem_mode=config.filesystem_mode,
            workspace_enabled=config.workspace_root is not None,
            mounted_paths=config.mounted_paths,
            network_mode=config.network_mode,
            allowed_domains=config.allowed_domains,
            allowed_http_methods=config.allowed_http_methods,
        )

    def create_run_tool(self) -> HyperlightExecuteCodeTool:
        """Create a run-scoped snapshot of this execute_code surface."""
        file_mounts = self.get_file_mounts()
        allowed_domains = self.get_allowed_domains()
        allowed_http_methods = self.get_allowed_http_methods()

        return HyperlightExecuteCodeTool(
            tools=self.get_tools(),
            approval_mode=self._default_approval_mode,
            filesystem_mode=self._filesystem_mode,
            workspace_root=self._workspace_root,
            file_mounts=file_mounts or None,
            network_mode=self._network_mode,
            allowed_domains=allowed_domains or None,
            allowed_http_methods=allowed_http_methods or None,
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
            "filesystem_mode": config.filesystem_mode,
            "workspace_root": str(config.workspace_root) if config.workspace_root is not None else None,
            "file_mounts": [
                {
                    "host_path": str(mount.host_path),
                    "mount_path": _display_mount_path(mount.mount_path),
                }
                for mount in config.file_mounts
            ],
            "network_mode": config.network_mode,
            "allowed_domains": list(config.allowed_domains),
            "allowed_http_methods": list(config.allowed_http_methods),
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
            allowed_domains = tuple(sorted(self._allowed_domains))
            allowed_http_methods = tuple(sorted(self._allowed_http_methods))
            approval_mode = _resolve_execute_code_approval_mode(
                base_approval_mode=self._default_approval_mode,
                tools=managed_tools,
            )

        workspace_signature = _path_tree_signature(workspace_root) if workspace_root is not None else ()
        normalized_mounts = tuple(
            _NormalizedFileMount(
                host_path=mount.host_path,
                mount_path=mount.mount_path,
                path_signature=_path_tree_signature(mount.host_path),
            )
            for mount in stored_mounts
        )

        return _RunConfig(
            backend=self._backend,
            module=self._module,
            module_path=self._module_path,
            approval_mode=approval_mode,
            tools=managed_tools,
            filesystem_mode=self._filesystem_mode,
            workspace_root=workspace_root,
            workspace_signature=workspace_signature,
            file_mounts=normalized_mounts,
            network_mode=self._network_mode,
            allowed_domains=allowed_domains,
            allowed_http_methods=allowed_http_methods,
        )

    def _run_code(self, *, code: str) -> list[Content]:
        config = self._build_run_config()
        return self._registry.execute(config=config, code=code)
