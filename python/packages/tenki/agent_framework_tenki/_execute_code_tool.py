# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from typing import Any, ClassVar, cast

from agent_framework import Content, FunctionTool
from agent_framework._tools import ApprovalMode
from tenki_sandbox import CommandResult, Sandbox

logger = logging.getLogger(__name__)


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

_DEFAULT_SANDBOX_NAME_PREFIX = "agent-framework"

# Server-side duration cap applied when the caller does not pass an explicit
# ``max_duration_seconds``. Without it, a crashed process or cancelled task
# would leave the sandbox running until Tenki's workspace policies stop it.
# On expiry Tenki pauses project/workspace-scoped sandboxes (compute stops,
# disk state is retained) and terminates unscoped ones.
_DEFAULT_MAX_DURATION_SECONDS = 60 * 15

# Poll-until-RUNNING budget for the reconcile loop (resume + transitional
# states). Sized for the slowest observed path: a ``USER_SHUTDOWN`` resume
# must first wait out the server's async rootfs capture (resume is rejected
# with "session has no pause snapshot" / "pause snapshot is not ready" until
# it completes — ~60s measured live), then cold-boot from that snapshot.
_RESUME_POLL_TIMEOUT_SECONDS = 120.0
_RESUME_POLL_INTERVAL_SECONDS = 0.5

# Pause-snapshot retention applied to run-scoped tools minted by
# ``create_run_tool`` when the caller does not set ``pause_retention_seconds``.
# A run-scoped sandbox that outlives its run only exists because run cleanup
# failed (crash, cancellation, abandoned stream), and nothing will ever resume
# it — a short retention lets Tenki's GC delete its pause snapshot (which bills
# storage while retained) after an hour instead of the server default (7 days).
_DEFAULT_RUN_SCOPED_PAUSE_RETENTION_SECONDS = 60 * 60

# State groupings (SDK returns strings). ``PAUSED`` and ``USER_SHUTDOWN`` are
# both stopped-but-resumable server-side: filesystem state is retained and
# ``resume()`` is a legal transition. Only ``TERMINATED`` is truly terminal;
# ``TERMINATING`` can no longer be resumed, so both are grouped for re-provision.
_RUNNABLE_STATE = "RUNNING"
_RESUMABLE_STATES = frozenset({"PAUSED", "USER_SHUTDOWN"})
_TERMINAL_STATES = frozenset({"TERMINATING", "TERMINATED"})


def _generate_sandbox_name(prefix: str) -> str:
    """Return ``<prefix>-<8-hex>``. Used by both standalone and run-scoped tools."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class _SandboxPreparationError(RuntimeError):
    """The sandbox could not be provisioned, resumed, or reconciled before exec.

    Distinguishes preparation failures from ``sandbox.exec`` failures now that
    both run inside the same worker-thread call (`_execute_sync`), so
    `_run_code` can keep reporting them under separate error headlines.
    """


class TenkiExecuteCodeTool(FunctionTool):
    r"""Execute Python code inside a `Tenki <https://tenki.cloud>`_ managed microVM sandbox.

    Requires the ``tenki-sandbox`` Python SDK (installed as a dependency of
    ``agent-framework-tenki``) and a Tenki API key. Follow the
    `Tenki Sandbox quick start <https://tenki.cloud/docs/sandbox/quick-start-sandbox>`_
    to create a workspace and generate a key, then export it as ``TENKI_API_KEY``.

    Lifecycle when used standalone: the tool lazily provisions a sandbox on the first
    ``execute_code`` invocation and reuses the same sandbox for every subsequent call.
    Before each call the tool reconciles remote sandbox state — a sandbox stopped in
    ``PAUSED`` or ``USER_SHUTDOWN`` (both resumable, filesystem retained) is
    transparently resumed and polled until ``RUNNING``; a sandbox in ``TERMINATING``
    or ``TERMINATED`` is replaced by a fresh provision. A transient ``refresh()``
    failure surfaces as a ``RuntimeError`` without dropping the handle, so the next
    call retries the same sandbox rather than leaking it. Each call runs
    ``python3 -c <code>`` inside the sandbox, so the sandbox filesystem and installed
    packages persist across calls but the Python interpreter state does not —
    variables defined in one call are not reachable in the next. Persist intermediate
    state through files or environment variables when a later call needs it. Call
    `close` (or use the tool via ``async with``) to terminate the sandbox and release
    the underlying microVM.

    Lifecycle when used through `TenkiCodeActProvider`: the provider mints a
    fresh run-scoped tool per agent run via `create_run_tool`, and the run tool
    provisions its own sandbox that is terminated by ``after_run``. Agent runs never
    share filesystem/secret state through this tool.

    Args:
        approval_mode (ApprovalMode | None): Approval policy passed through to
            `agent_framework.FunctionTool`. Defaults to ``"never_require"``.
        api_key (str | None): Optional Tenki API key. When ``None`` the SDK reads
            `TENKI_API_KEY` from the environment.
        sandbox_name (str | None): Optional literal sandbox identifier. Tenki does
            not enforce name uniqueness — names are display labels. When ``None``
            the tool generates ``agent-framework-<8-hex>`` and refreshes the suffix
            on every re-provision so successive sandboxes stay distinguishable in
            the Tenki dashboard. When set, the literal name is used as-is.
        image (str | None): Optional Tenki base-image identifier. When ``None`` the
            Tenki service picks its default sandbox image (which ships ``python3``).
        project_id (str | None): Optional Tenki project ID scoping the sandbox.
            Required when the API key has access to more than one project.
        workspace_id (str | None): Optional Tenki workspace ID.
        cpu_cores (int | None): Optional CPU-core count. When ``None`` the Tenki
            service default applies.
        memory_mb (int | None): Optional memory (MB). ``None`` uses the service default.
        disk_size_gb (int | None): Optional ephemeral disk (GB). ``None`` uses the
            service default.
        max_duration_seconds (int | None): Server-side duration cap enforced by
            Tenki. Defaults to 900 (15 minutes) so a crashed process or cancelled
            task cannot leave a sandbox running indefinitely. On expiry Tenki
            pauses project/workspace-scoped sandboxes (compute stops, disk state
            retained) and terminates unscoped ones. Pass an explicit value for
            longer evals; pass ``None`` to explicitly opt out (not recommended in
            production).
        pause_retention_seconds (int | None): How long Tenki retains the pause
            snapshot of a stopped sandbox (``PAUSED`` / ``USER_SHUTDOWN``) before
            the server's retention GC deletes it — snapshot storage bills until
            then. ``None`` (the default) uses the Tenki server default (7 days).
            Run-scoped tools minted by `create_run_tool` default to 1 hour
            instead, so a sandbox orphaned by a crashed run does not bill
            storage for a week; note that once the snapshot is GC'd the sandbox
            can no longer be resumed.
        exec_timeout_seconds (int): Per-``execute_code`` timeout in seconds. Defaults to 60.
        extra_create_kwargs (dict[str, Any] | None): Optional keyword arguments passed
            straight to `tenki_sandbox.Sandbox.create` — for advanced knobs not
            surfaced individually (e.g. ``snapshot_id``, ``allow_inbound``,
            ``allow_outbound``).

    Notes:
        * In-sandbox tool callbacks are not supported — code executing inside the sandbox
          cannot invoke host-side `agent_framework.FunctionTool` instances (the
          Tenki SDK does not expose a callback bridge).
        * File mounts and outbound network allow-lists are not surfaced as first-class
          kwargs; pass them through ``extra_create_kwargs``.
        * Cancellation latency: ``execute_code`` runs the reconcile and
          ``sandbox.exec`` inside ``asyncio.to_thread`` under the sandbox lock.
          Python cannot cancel an in-flight thread, so a cancel raised during
          exec propagates to the awaiter immediately but the underlying sandbox
          call keeps running server-side until it completes or hits
          ``exec_timeout_seconds`` — and a subsequent `close` blocks on the same
          lock until then. Worst-case wall time from cancel to full quiescence
          is therefore ``exec_timeout_seconds``.
    """

    SUPPORTED_LANGUAGES: ClassVar[list[str]] = ["python"]

    def __init__(
        self,
        *,
        approval_mode: ApprovalMode | None = None,
        api_key: str | None = None,
        sandbox_name: str | None = None,
        image: str | None = None,
        project_id: str | None = None,
        workspace_id: str | None = None,
        cpu_cores: int | None = None,
        memory_mb: int | None = None,
        disk_size_gb: int | None = None,
        max_duration_seconds: int | None = _DEFAULT_MAX_DURATION_SECONDS,
        pause_retention_seconds: int | None = None,
        exec_timeout_seconds: int = 60,
        extra_create_kwargs: dict[str, Any] | None = None,
        _sandbox_name_prefix: str | None = None,
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
        # Two naming modes (names are display labels; Tenki does not enforce uniqueness):
        # (1) explicit literal — ``sandbox_name="my-agent"`` on standalone use, passed
        #     verbatim and preserved across re-provision.
        # (2) prefix-with-suffix — ``_sandbox_name_prefix`` set by `create_run_tool`
        #     (or the default prefix): every provision mints ``<prefix>-<8-hex>`` so
        #     sandboxes stay distinguishable in the Tenki dashboard.
        self._explicit_sandbox_name: str | None = sandbox_name if _sandbox_name_prefix is None else None
        self._sandbox_name_prefix: str = _sandbox_name_prefix or _DEFAULT_SANDBOX_NAME_PREFIX
        if self._explicit_sandbox_name is not None:
            self._sandbox_name = self._explicit_sandbox_name
        else:
            self._sandbox_name = _generate_sandbox_name(self._sandbox_name_prefix)

        self._image = image
        self._project_id = project_id
        self._workspace_id = workspace_id
        self._cpu_cores = cpu_cores
        self._memory_mb = memory_mb
        self._disk_size_gb = disk_size_gb
        self._max_duration_seconds = max_duration_seconds
        self._pause_retention_seconds = pause_retention_seconds
        self._exec_timeout_seconds = exec_timeout_seconds
        self._extra_create_kwargs: dict[str, Any] = dict(extra_create_kwargs) if extra_create_kwargs else {}

        # A single sandbox is created lazily on first use and reused across calls.
        # A lock guards the create/close race between concurrent ``execute_code`` invocations.
        self._sandbox_lock = threading.Lock()
        self._sandbox: Sandbox | None = None

    @property
    def sandbox_name(self) -> str:
        """The name of the current or next-provisioned Tenki sandbox."""
        return self._sandbox_name

    @property
    def exec_timeout_seconds(self) -> int:
        """Per-invocation execution timeout in seconds."""
        return self._exec_timeout_seconds

    def create_run_tool(self) -> TenkiExecuteCodeTool:
        """Return a fresh, run-scoped ``TenkiExecuteCodeTool`` with the same config.

        Called by `TenkiCodeActProvider.before_run` to create a per-agent-run
        tool. The returned tool has a unique ``<prefix>-<8-hex>`` sandbox name derived
        from the user's explicit ``sandbox_name`` (used as prefix) or the default
        ``agent-framework`` prefix. ``pause_retention_seconds`` defaults to 1 hour
        when not set explicitly (run-scoped sandboxes that outlive their run are
        orphans of a failed cleanup; see `_DEFAULT_RUN_SCOPED_PAUSE_RETENTION_SECONDS`).
        All other kwargs are copied verbatim.
        """
        prefix = self._explicit_sandbox_name if self._explicit_sandbox_name is not None else self._sandbox_name_prefix
        pause_retention_seconds = self._pause_retention_seconds
        if pause_retention_seconds is None:
            pause_retention_seconds = _DEFAULT_RUN_SCOPED_PAUSE_RETENTION_SECONDS
        # ``FunctionTool.__init__`` stores ``approval_mode`` after applying its own
        # ``or "never_require"`` fallback, so the runtime value is always a valid
        # ``ApprovalMode``. Cast so the constructor's stricter ``ApprovalMode | None``
        # type annotation stays satisfied.
        return TenkiExecuteCodeTool(
            approval_mode=cast("ApprovalMode | None", self.approval_mode),
            api_key=self._api_key,
            image=self._image,
            project_id=self._project_id,
            workspace_id=self._workspace_id,
            cpu_cores=self._cpu_cores,
            memory_mb=self._memory_mb,
            disk_size_gb=self._disk_size_gb,
            max_duration_seconds=self._max_duration_seconds,
            pause_retention_seconds=pause_retention_seconds,
            exec_timeout_seconds=self._exec_timeout_seconds,
            extra_create_kwargs=dict(self._extra_create_kwargs),
            _sandbox_name_prefix=prefix,
        )

    def _build_create_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"name": self._sandbox_name}
        # Only forward optional values the caller explicitly set; the Tenki SDK applies
        # its own defaults when we omit a field, and it may reject ``field=None``.
        # ``is not None`` (rather than ``or``) so that an explicit empty string on the
        # constructor still wins over the env var — the contract is "explicit args
        # override env vars when provided", not "truthy args override env vars".
        #
        # Env-var ownership: ``TENKI_API_KEY`` is also read by the SDK
        # (``resolve_auth_token``); the duplicate read here preserves the
        # explicit-arg-wins semantics above. ``TENKI_PROJECT_ID`` and
        # ``TENKI_WORKSPACE_ID`` are **not** read by the SDK — this module
        # owns them.
        api_key = self._api_key if self._api_key is not None else os.environ.get("TENKI_API_KEY")
        if api_key is not None:
            kwargs["auth_token"] = api_key
        if self._image is not None:
            kwargs["image"] = self._image
        project_id = self._project_id if self._project_id is not None else os.environ.get("TENKI_PROJECT_ID")
        if project_id is not None:
            kwargs["project_id"] = project_id
        workspace_id = self._workspace_id if self._workspace_id is not None else os.environ.get("TENKI_WORKSPACE_ID")
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
        if self._pause_retention_seconds is not None:
            kwargs["pause_retention"] = self._pause_retention_seconds
        # Caller-supplied extras win last so they can override anything above.
        kwargs.update(self._extra_create_kwargs)
        return kwargs

    def _execute_sync(self, code: str) -> CommandResult:
        """Reconcile sandbox state and execute the code under a single lock hold.

        Called inside ``asyncio.to_thread``. Holding ``_sandbox_lock`` across
        both the reconcile and ``sandbox.exec`` means `close` (which takes the
        same lock) cannot terminate the sandbox or close its gRPC client while
        an exec is still in flight — it blocks until the exec finishes, bounded
        by ``exec_timeout_seconds``. Concurrent ``execute_code`` calls serialize
        on the lock; the sandbox is a single microVM either way.
        """
        with self._sandbox_lock:
            sandbox = self._ensure_sandbox_locked()
            return sandbox.exec("python3", "-c", code, timeout=self._exec_timeout_seconds)

    def _ensure_sandbox_locked(self) -> Sandbox:
        """Return a runnable sandbox — provision on first use, resume if stopped, re-provision if gone.

        ``_sandbox_lock`` must be held by the caller. Reconciles remote state on
        every call:

        - ``TERMINATING`` / ``TERMINATED`` → drop the handle, provision a fresh
          sandbox (auto-generated names refresh their suffix; explicit names are
          preserved).
        - any other non-``RUNNING`` state → `_wait_for_running_locked`, which
          resumes stopped-but-resumable sandboxes (``PAUSED`` / ``USER_SHUTDOWN``)
          and polls transitional states (``PAUSING`` / ``RESUMING`` / ``CREATING``)
          until ``RUNNING``.
        - ``refresh()`` raising → surface as `_SandboxPreparationError` without
          dropping the handle. Next call retries the same sandbox rather than
          leaking it.
        """
        sandbox = self._sandbox
        if sandbox is None:
            return self._create_sandbox_locked()

        try:
            sandbox.refresh()
        except Exception as exc:
            # Do not drop the handle — the sandbox may still be alive.
            # Surface the error so the next call retries the same session
            # rather than provisioning a duplicate.
            raise _SandboxPreparationError(f"Failed to refresh Tenki sandbox state: {exc}") from exc

        if sandbox.state in _TERMINAL_STATES:
            logger.debug("Tenki sandbox reached remote state=%s; re-provisioning", sandbox.state)
            # The session can no longer be resumed or terminated again, but the
            # SDK-owned control-plane channel is still open on our side.
            self._close_owning_client_sync(sandbox)
            self._sandbox = None
            self._refresh_autogenerated_name_locked()
            return self._create_sandbox_locked()
        return self._wait_for_running_locked(sandbox)

    def _wait_for_running_locked(self, sandbox: Sandbox) -> Sandbox:
        """Poll until the sandbox reaches ``RUNNING``, resuming it if stopped. Lock must be held.

        Resume attempts are retried within the poll budget. Two failure shapes
        require this — both observed live: ``USER_SHUTDOWN`` links its pause
        snapshot asynchronously (the rootfs capture runs *after* the state
        flips), so the server rejects resume with FAILED_PRECONDITION ("session
        has no pause snapshot" / "pause snapshot is not ready") until the
        capture completes; and a dispatched resume that fails on the node is
        reverted server-side to the source state (``RESUMING`` →
        ``USER_SHUTDOWN``/``PAUSED``), which the loop sees as the sandbox
        settling back and simply retries. Unknown states are treated as
        transitional so an SDK upgrade that adds new states doesn't fail
        closed. Raises `_SandboxPreparationError` on timeout so the caller sees
        a clear error rather than a "sandbox is not RUNNING" exec failure.

        Concurrency: the sandbox lock is held for the full poll window (up to
        `_RESUME_POLL_TIMEOUT_SECONDS`); concurrent ``execute_code`` calls block
        on the lock rather than racing the resume.
        """
        deadline = time.monotonic() + _RESUME_POLL_TIMEOUT_SECONDS
        while True:
            state = sandbox.state
            if state == _RUNNABLE_STATE:
                return sandbox
            if state in _TERMINAL_STATES:
                raise _SandboxPreparationError(f"Tenki sandbox reached state={state} while waiting for RUNNING.")
            if state in _RESUMABLE_STATES:
                try:
                    sandbox.resume()
                except Exception as exc:
                    if time.monotonic() >= deadline:
                        raise _SandboxPreparationError(
                            f"Failed to resume Tenki sandbox from state={state}: {exc}"
                        ) from exc
                    logger.debug("Tenki sandbox resume from state=%s failed; retrying: %s", state, exc)
                else:
                    # Local state is now RESUMING; fall through to poll. If the
                    # server reverts the resume, the next refresh shows the
                    # resumable state again and the loop retries.
                    continue
            if time.monotonic() >= deadline:
                raise _SandboxPreparationError(
                    f"Tenki sandbox did not reach RUNNING within {_RESUME_POLL_TIMEOUT_SECONDS}s (last state={state})."
                )
            time.sleep(_RESUME_POLL_INTERVAL_SECONDS)
            try:
                sandbox.refresh()
            except Exception as exc:
                raise _SandboxPreparationError(f"Failed to refresh Tenki sandbox state while polling: {exc}") from exc

    def _refresh_autogenerated_name_locked(self) -> None:
        """Mint a fresh suffix on re-provision for auto-generated names.

        Tenki does not enforce name uniqueness; the fresh suffix keeps
        successive sandboxes distinguishable in the Tenki dashboard and logs.
        An explicit user-supplied literal name is preserved as-is.
        """
        if self._explicit_sandbox_name is None:
            self._sandbox_name = _generate_sandbox_name(self._sandbox_name_prefix)

    def _create_sandbox_locked(self) -> Sandbox:
        """Provision a fresh sandbox. The sandbox lock must be held by the caller."""
        create_kwargs = self._build_create_kwargs()
        try:
            sandbox = Sandbox.create(**create_kwargs)  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            raise _SandboxPreparationError(f"Failed to create Tenki sandbox: {exc}") from exc
        self._sandbox = sandbox
        return sandbox

    async def _run_code(self, *, code: str) -> list[Content]:
        """Execute a single block of Python code inside the sandbox."""
        try:
            result = await asyncio.to_thread(self._execute_sync, code)
        except asyncio.CancelledError:
            # Cancellation must propagate so higher-level workflows can stop promptly.
            raise
        except _SandboxPreparationError as exc:
            return [Content.from_error(message="Failed to prepare Tenki sandbox", error_details=str(exc))]
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

    def _build_contents(self, result: CommandResult) -> list[Content]:
        """Convert a Tenki ``CommandResult`` into a list of `Content` values.

        ``result.ok`` accounts for the process being killed by a signal
        (SIGKILL, SIGTERM, …), which ``exit_code`` alone misses. ``signal``,
        ``reason``, and ``errno`` are surfaced in the error message so operators
        can distinguish timeouts, OOM kills, and spawn failures.
        """
        stdout = result.stdout_text
        stderr = result.stderr_text

        contents: list[Content] = []
        if stdout:
            contents.append(Content.from_text(stdout))
        if not result.ok:
            # Inline a truncated stderr into the message so LLM consumers see the
            # traceback in the primary field, not just in error_details.
            stderr_snippet = stderr.strip()[: self._ERROR_MESSAGE_STDERR_LIMIT]
            failure_bits: list[str] = [f"status {result.exit_code}"]
            if result.signal:
                failure_bits.append(f"signal {result.signal}")
            if result.reason:
                failure_bits.append(f"reason {result.reason}")
            if result.errno is not None:
                failure_bits.append(f"errno {result.errno}")
            message = f"Code exited with {', '.join(failure_bits)}"
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
        """Terminate the underlying Tenki sandbox and its owning SDK client.

        Safe to call multiple times; a no-op if the sandbox was never created.
        On terminate failure the handle is **preserved** so the caller can retry
        — a swallowed failure would otherwise leak the microVM. The SDK-owned
        `tenki_sandbox.Client` created by ``Sandbox.create`` (when
        ``_owns_client=True``) is closed after a successful terminate to release
        the gRPC channel.
        """
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        """Sync body of `close`, run inside ``asyncio.to_thread``.

        Holds ``_sandbox_lock`` for the whole terminate so it never races
        `_execute_sync` — an in-flight reconcile or exec finishes before the
        terminate starts — and, like all lock acquisitions in this class, only
        ever blocks a worker thread, never the event loop (a reconcile can hold
        the lock for up to the resume-poll budget; an exec for up to
        ``exec_timeout_seconds``).
        """
        with self._sandbox_lock:
            sandbox = self._sandbox
            if sandbox is None:
                return

            # Terminate first. If it fails, the raised error propagates and the
            # handle is kept so the caller can retry — dropping it here would
            # leak the sandbox.
            sandbox.close_if_open()

            self._sandbox = None
            # Close the owning Client (see `_close_owning_client_sync`).
            self._close_owning_client_sync(sandbox)

    def _close_owning_client_sync(self, sandbox: Sandbox) -> None:
        """Close the SDK-owned control-plane `tenki_sandbox.Client`.

        Called both after a successful ``close_if_open`` and from the
        terminal-state re-provision branch in `_ensure_sandbox_locked`. The
        SDK's own ``Sandbox.close()`` only closes the data-plane RPC, so
        without this the gRPC control channel would stay open until the
        process exits — a real leak under long-lived standalone tools that
        re-provision on ``TERMINATED``.

        ``_owns_client`` / ``_client`` are private SDK attributes read via
        ``getattr``; if Tenki renames them we log loudly rather than silently
        leak. A public ``sandbox.close_client()`` would let us drop this.
        Errors are logged and suppressed — callers must not block on channel
        cleanup.
        """
        if not getattr(sandbox, "_owns_client", False):
            return
        client = getattr(sandbox, "_client", None)
        client_close = getattr(client, "close", None) if client is not None else None
        if not callable(client_close):
            logger.warning(
                "Tenki sandbox %s reports _owns_client=True but no closable Client is "
                "accessible; gRPC channel may leak. Tenki SDK internals may have changed.",
                sandbox.id,
            )
            return
        try:
            client_close()
        except Exception as exc:
            logger.debug("Ignoring error closing Tenki Client: %s", exc)

    async def __aenter__(self) -> TenkiExecuteCodeTool:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()
