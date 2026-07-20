# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
import uuid
from typing import Any, ClassVar, Optional

logger = logging.getLogger(__name__)

from agent_framework import Content, FunctionTool
from agent_framework._tools import ApprovalMode

try:
    from tenki_sandbox import Sandbox
except ImportError as _import_err:  # pragma: no cover - environment-dependent
    raise RuntimeError(
        "Missing dependencies for TenkiExecuteCodeTool. "
        "Install the Tenki SDK with `pip install tenki-sandbox` "
        "(or via `pip install agent-framework-tenki`)."
    ) from _import_err


EXECUTE_CODE_TOOL_DESCRIPTION = (
    "Execute Python in an isolated Tenki microVM sandbox. Each call runs the "
    "code as `python3 -c <code>`; only stdout and stderr are captured, so wrap "
    "any values you want to see in `print(...)` — bare expressions are not "
    "auto-printed like in a REPL."
)

EXECUTE_CODE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "_ExecuteCodeInput",
    "properties": {
        "code": {
            "type": "string",
            "title": "Code",
            "description": (
                "Python code to execute in an isolated Tenki sandbox. The code "
                "runs as `python3 -c <code>` — only stdout/stderr are captured, "
                "so use `print(...)` to return any values."
            ),
        },
    },
    "required": ["code"],
}


def _default_sandbox_name() -> str:
    """Return a unique, source-attributable sandbox name.

    The ``agent-framework-`` prefix lets operators inspecting the Tenki dashboard or the
    ``tenki sandbox list`` CLI attribute the sandbox back to Agent Framework — matching
    the client-attributable naming already used elsewhere in the workspace (for example
    ``WorkflowBuilder-<uuid>`` in ``agent-framework-durabletask``).
    """
    return f"agent-framework-{uuid.uuid4().hex[:8]}"


class TenkiExecuteCodeTool(FunctionTool):
    r"""Execute Python code inside a `Tenki <https://tenki.cloud>`_ managed microVM sandbox.

    Requires the ``tenki-sandbox`` Python SDK (installed as a dependency of
    ``agent-framework-tenki``) and a Tenki API key. Follow the
    `Tenki Sandbox quick start <https://tenki.cloud/docs/sandbox/quick-start-sandbox>`_
    to create a workspace and generate a key, then export it as ``TENKI_API_KEY``.

    Lifecycle: the tool lazily provisions a sandbox on the first ``_run_code`` invocation
    and reuses the same sandbox for every subsequent call within the tool's lifetime.
    Before each call the tool reconciles remote sandbox state — a sandbox that has
    transitioned to ``PAUSED`` (Tenki server-side idle policy, ``idle_timeout_minutes``
    from ``extra_create_kwargs``, or an external ``tenki sandbox pause``) is
    transparently resumed, and a sandbox that has transitioned to ``TERMINATING`` or
    ``TERMINATED`` (workspace timeout, ``max_duration_seconds``, or an external
    ``tenki sandbox terminate``) is replaced by a fresh provision. Callers therefore
    never have to track pause/terminate transitions manually. Each call runs
    ``python3 -c <code>`` inside the sandbox, so the sandbox filesystem and installed
    packages persist across calls but the Python interpreter state does not —
    variables defined in one call are not reachable in the next. Filesystem and
    installed packages are also lost when the sandbox is re-provisioned after a
    termination; use ``extra_create_kwargs={"snapshot_id": ...}`` on a new tool if you
    need to preserve state across that boundary. Persist intermediate state through
    files or environment variables when a later call needs it. Call :meth:`close` (or
    use the tool via ``async with``) to terminate the sandbox and release the
    underlying microVM. A new sandbox is created on the next call if the tool is
    reused after being closed.

    Args:
        approval_mode (Optional[ApprovalMode]): Approval policy passed through to
            :class:`agent_framework.FunctionTool`. Defaults to ``"never_require"``.
        api_key (Optional[str]): Optional Tenki API key. When ``None`` the SDK reads
            :envvar:`TENKI_API_KEY` from the environment.
        sandbox_name (Optional[str]): Optional sandbox identifier. When ``None`` the tool
            generates ``agent-framework-<8-hex>`` — matching the naming convention already
            used by other Agent Framework packages that create externally visible
            resources.
        image (Optional[str]): Optional Tenki base-image identifier. When ``None`` the
            Tenki service picks its default sandbox image (which ships ``python3``).
        project_id (Optional[str]): Optional Tenki project ID scoping the sandbox.
            Required when the API key has access to more than one project.
        workspace_id (Optional[str]): Optional Tenki workspace ID.
        cpu_cores (Optional[int]): Optional CPU-core count. When ``None`` the Tenki
            service default applies.
        memory_mb (Optional[int]): Optional memory (MB). ``None`` uses the service default.
        disk_size_gb (Optional[int]): Optional ephemeral disk (GB). ``None`` uses the
            service default.
        max_duration_seconds (Optional[int]): Optional cost-safety cap on sandbox
            lifetime, enforced server-side. When ``None`` the sandbox lives until
            explicitly terminated (or the workspace timeout applies). Recommended for
            production use to avoid runaway sandboxes in agent loops.
        exec_timeout_seconds (int): Per-``_run_code`` timeout in seconds. Defaults to 60.
        extra_create_kwargs (Optional[dict[str, Any]]): Optional keyword arguments passed
            straight to :meth:`tenki_sandbox.Sandbox.create` — for advanced knobs not
            surfaced individually (e.g. ``snapshot_id``, ``allow_inbound``,
            ``allow_outbound``).

    Notes:
        * In-sandbox tool callbacks are not supported — code executing inside the sandbox
          cannot invoke host-side :class:`~agent_framework.FunctionTool` instances (the
          Tenki SDK does not expose a callback bridge).
        * File mounts and outbound network allow-lists are not modeled by this package.
          Bake dependencies and files into a custom Tenki image, or configure them
          through ``extra_create_kwargs``.
        * The sandbox lifecycle is *reuse-per-tool*, not per-agent-run. If the tool is
          shared across many agent runs, filesystem state from run N is visible to run
          N+1 (same sandbox), though each individual ``execute_code`` invocation is a
          fresh Python process. Create a fresh :class:`TenkiExecuteCodeTool` per agent
          instance if isolation between agents matters.
    """

    SUPPORTED_LANGUAGES: ClassVar[list[str]] = ["python"]

    def __init__(
        self,
        *,
        approval_mode: Optional[ApprovalMode] = None,
        api_key: Optional[str] = None,
        sandbox_name: Optional[str] = None,
        image: Optional[str] = None,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        cpu_cores: Optional[int] = None,
        memory_mb: Optional[int] = None,
        disk_size_gb: Optional[int] = None,
        max_duration_seconds: Optional[int] = None,
        exec_timeout_seconds: int = 60,
        extra_create_kwargs: Optional[dict[str, Any]] = None,
    ) -> None:
        if exec_timeout_seconds < 1:
            raise ValueError("exec_timeout_seconds must be greater than or equal to 1.")

        super().__init__(
            name="execute_code",
            description=EXECUTE_CODE_TOOL_DESCRIPTION,
            approval_mode=approval_mode or "never_require",
            func=self._run_code,
            input_model=EXECUTE_CODE_INPUT_SCHEMA,
        )

        self._api_key = api_key
        self._sandbox_name = sandbox_name or _default_sandbox_name()
        self._image = image
        self._project_id = project_id
        self._workspace_id = workspace_id
        self._cpu_cores = cpu_cores
        self._memory_mb = memory_mb
        self._disk_size_gb = disk_size_gb
        self._max_duration_seconds = max_duration_seconds
        self._exec_timeout_seconds = exec_timeout_seconds
        self._extra_create_kwargs: dict[str, Any] = dict(extra_create_kwargs) if extra_create_kwargs else {}

        # A single sandbox is created lazily on first use and reused across calls.
        # A lock guards the create/close race between concurrent ``_run_code`` invocations.
        self._sandbox_lock = threading.Lock()
        self._sandbox: Optional[Sandbox] = None

    @property
    def sandbox_name(self) -> str:
        """The name of the underlying Tenki sandbox."""
        return self._sandbox_name

    @property
    def exec_timeout_seconds(self) -> int:
        """Per-invocation execution timeout in seconds."""
        return self._exec_timeout_seconds

    def _build_create_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"name": self._sandbox_name}
        # Only forward optional values the caller explicitly set; the Tenki SDK applies
        # its own defaults when we omit a field, and it may reject ``field=None``.
        api_key = self._api_key or os.environ.get("TENKI_API_KEY")
        if api_key is not None:
            kwargs["auth_token"] = api_key
        if self._image is not None:
            kwargs["image"] = self._image
        # Explicit constructor args take precedence over env vars, matching the
        # api_key path above and OpenAI/Anthropic sibling packages' behavior.
        project_id = self._project_id or os.environ.get("TENKI_PROJECT_ID")
        if project_id is not None:
            kwargs["project_id"] = project_id
        workspace_id = self._workspace_id or os.environ.get("TENKI_WORKSPACE_ID")
        if workspace_id is not None:
            kwargs["workspace_id"] = workspace_id
        if self._cpu_cores is not None:
            kwargs["cpu_cores"] = self._cpu_cores
        if self._memory_mb is not None:
            kwargs["memory_mb"] = self._memory_mb
        if self._disk_size_gb is not None:
            kwargs["disk_size_gb"] = self._disk_size_gb
        if self._max_duration_seconds is not None:
            kwargs["max_duration"] = self._max_duration_seconds
        # Caller-supplied extras win last so they can override anything above.
        kwargs.update(self._extra_create_kwargs)
        return kwargs

    def _ensure_sandbox_sync(self) -> Sandbox:
        """Return a usable sandbox — provision on first use, resume if paused, re-provision if gone.

        Tenki sandboxes can transition to ``PAUSED`` between calls (server-side idle
        policies, external ``tenki sandbox pause``) and to ``TERMINATED`` if the
        workspace timeout or ``max_duration`` elapsed. This method reconciles the
        remote state on every call so ``_run_code`` never hands the SDK a
        ``sandbox.exec`` that would fail with ``sandbox is not RUNNING``.

        Called inside ``asyncio.to_thread``.
        """
        with self._sandbox_lock:
            sandbox = self._sandbox
            if sandbox is None:
                return self._create_sandbox_locked()

            try:
                sandbox.refresh()
            except Exception as exc:
                # Remote state is unknowable — drop the stale handle and re-provision.
                logger.debug("Dropping Tenki sandbox handle after refresh failure: %s", exc)
                self._sandbox = None
                return self._create_sandbox_locked()

            state = getattr(sandbox, "state", None)
            if state == "PAUSED":
                try:
                    sandbox.resume()
                except Exception as exc:
                    raise RuntimeError(f"Failed to resume paused Tenki sandbox: {exc}") from exc
                return sandbox
            if state in {"TERMINATING", "TERMINATED"}:
                logger.debug("Dropping Tenki sandbox handle after remote state=%s", state)
                self._sandbox = None
                return self._create_sandbox_locked()
            return sandbox

    def _create_sandbox_locked(self) -> Sandbox:
        """Provision a fresh sandbox. The sandbox lock must be held by the caller."""
        create_kwargs = self._build_create_kwargs()
        try:
            sandbox = Sandbox.create(**create_kwargs)  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            raise RuntimeError(f"Failed to create Tenki sandbox: {exc}") from exc
        self._sandbox = sandbox
        return sandbox

    async def _run_code(self, *, code: str) -> list[Content]:
        """Execute a single block of Python code inside the sandbox."""
        try:
            sandbox = await asyncio.to_thread(self._ensure_sandbox_sync)
        except RuntimeError as exc:
            return [Content.from_error(message="Failed to provision Tenki sandbox", error_details=str(exc))]

        try:
            result = await asyncio.to_thread(sandbox.exec, "python3", "-c", code, timeout=self._exec_timeout_seconds)
        except asyncio.CancelledError:  # pragma: no cover - cancellation-dependent
            return [Content.from_error(message="Code execution was cancelled")]
        except Exception as exc:
            return [Content.from_error(message="Sandbox execution failed", error_details=str(exc))]

        return self._build_contents(result)

    _ERROR_MESSAGE_STDERR_LIMIT: ClassVar[int] = 500

    # Recovery hint appended when the sandbox reports a Python SyntaxError. Only
    # fires for that specific error class to keep the hint from misleading
    # stronger models on unrelated failures.
    _SYNTAX_ERROR_HINT: ClassVar[str] = (
        " [Common causes: (1) a compound statement (with/for/if/try/while) "
        "following a semicolon at the outer level; put it on its own line "
        "instead. (2) `\\n` literals in the JSON payload where actual newline "
        "characters were intended.]"
    )

    def _build_contents(self, result: Any) -> list[Content]:
        """Convert a Tenki exec result into a list of :class:`Content` values."""
        stdout = getattr(result, "stdout_text", "") or ""
        stderr = getattr(result, "stderr_text", "") or ""
        exit_code = int(getattr(result, "exit_code", 1))

        contents: list[Content] = []
        if stdout:
            contents.append(Content.from_text(stdout))
        if exit_code != 0:
            # Inline a truncated stderr into the message so downstream LLM
            # consumers see the traceback in the primary field, not just in
            # error_details — small models tend to under-weight secondary fields.
            stderr_snippet = stderr.strip()[: self._ERROR_MESSAGE_STDERR_LIMIT] if stderr else ""
            message = f"Code exited with status {exit_code}"
            if stderr_snippet:
                message = f"{message}. stderr: {stderr_snippet}"
            if stderr and "SyntaxError" in stderr:
                message = f"{message}{self._SYNTAX_ERROR_HINT}"
            contents.append(
                Content.from_error(
                    message=message,
                    error_details=stderr or None,
                )
            )
        elif stderr:
            # Non-fatal stderr (e.g. warnings) — surface it as ordinary text so the model
            # sees it, matching Hyperlight's behaviour.
            contents.append(Content.from_text(stderr))
        if not contents:
            contents.append(Content.from_text("Code executed successfully without output."))
        return contents

    async def close(self) -> None:
        """Terminate the underlying Tenki sandbox and release its resources.

        Safe to call multiple times; a no-op if the sandbox was never created. After
        close, a subsequent ``_run_code`` invocation lazily provisions a new sandbox.
        """
        with self._sandbox_lock:
            sandbox = self._sandbox
            self._sandbox = None
        if sandbox is None:
            return
        # SDK errors on shutdown are ignored — the sandbox is server-side managed and will
        # be reaped by Tenki's own idle timeout even if our terminate call fails.
        with contextlib.suppress(Exception):  # pragma: no cover - defensive
            await asyncio.to_thread(sandbox.close_if_open)

    async def __aenter__(self) -> TenkiExecuteCodeTool:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()
