# Copyright (c) Microsoft. All rights reserved.

"""The ``execute_code`` FunctionTool implementation.

Each call ships the LLM-emitted Python to a long-lived agent-sandbox pod and
runs it as a fresh ``python3`` process. The pod is claimed lazily on the first
invocation and reused for the lifetime of the tool instance, so filesystem
state and any ``pip install``-ed packages persist across calls while each
call still gets a clean interpreter.

The integration is async-native: it uses the agent-sandbox SDK's
``AsyncSandboxClient`` / ``AsyncSandbox`` directly, so no thread offloading is
needed inside Agent Framework's async run loop. ``AsyncSandboxClient`` requires
an explicit ``connection_config`` (``SandboxDirectConnectionConfig``,
``SandboxGatewayConnectionConfig``, or ``SandboxInClusterConnectionConfig``);
the synchronous ``kubectl port-forward`` tunnel mode is not supported by the
async client.

The runtime image used by the reference ``python-sandbox-template`` runs the
request command via ``shlex.split`` + ``subprocess.run`` without a shell, which
makes ``python3 -c '<code>'`` brittle for non-trivial programs (quoting,
multi-line strings, embedded shell metacharacters). Writing the code to a file
via the sandbox's files API and running ``python3 -u <file>`` avoids all of
that and gives the model real tracebacks with file/line info.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_framework import Content, FunctionTool
from agent_framework._tools import ApprovalMode
from k8s_agent_sandbox import AsyncSandboxClient
from k8s_agent_sandbox.async_sandbox import AsyncSandbox
from k8s_agent_sandbox.models import SandboxConnectionConfig, SandboxTracerConfig

from ._instructions import build_codeact_instructions, build_execute_code_description

logger = logging.getLogger(__name__)

EXECUTE_CODE_TOOL_NAME = "execute_code"
DEFAULT_CODE_FILENAME = "_agent_sandbox_exec.py"
DEFAULT_PYTHON_COMMAND = "python3 -u"
DEFAULT_EXEC_TIMEOUT_SECONDS = 120
DEFAULT_SANDBOX_READY_TIMEOUT_SECONDS = 180

EXECUTE_CODE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "_ExecuteCodeInput",
    "properties": {
        "code": {
            "type": "string",
            "title": "Code",
            "description": (
                "Python source to execute in an isolated agent-sandbox pod. End with `print(...)` to surface results."
            ),
        },
    },
    "required": ["code"],
}


class AgentSandboxExecuteCodeTool(FunctionTool):
    """``execute_code`` tool backed by a Kubernetes agent-sandbox Pod.

    One sandbox is created lazily on the first call and reused for every
    subsequent invocation on this tool instance. State (working directory,
    installed packages, long-lived files) persists across calls; Python
    module-level globals do not, because each call is a fresh ``python3``
    process.

    Always call :meth:`close` (or use the parent provider as an async context
    manager) when finished — the sandbox claim and its underlying Pod will
    keep running on the cluster until then.
    """

    def __init__(
        self,
        *,
        warmpool: str,
        namespace: str = "default",
        connection_config: SandboxConnectionConfig | None = None,
        tracer_config: SandboxTracerConfig | None = None,
        sandbox_ready_timeout: int = DEFAULT_SANDBOX_READY_TIMEOUT_SECONDS,
        shutdown_after_seconds: int | None = None,
        labels: dict[str, str] | None = None,
        approval_mode: ApprovalMode | None = None,
        python_command: str = DEFAULT_PYTHON_COMMAND,
        exec_timeout: int = DEFAULT_EXEC_TIMEOUT_SECONDS,
        code_filename: str = DEFAULT_CODE_FILENAME,
        _client: AsyncSandboxClient[Any] | None = None,
    ) -> None:
        """Initialize the tool.

        Keyword Args:
            warmpool: Name of the ``SandboxWarmPool`` the Pod is claimed from.
                Required. The warm pool references a ``SandboxTemplate`` and may
                pre-warm pods (``replicas > 0``) to remove cold-start latency,
                or act as a plain on-demand pool (``replicas: 0``).
            namespace: Kubernetes namespace that holds the warm pool and where
                the Pod will run.
            connection_config: How the SDK reaches the Pod. Required — the
                async client supports ``SandboxDirectConnectionConfig``,
                ``SandboxGatewayConnectionConfig``, and
                ``SandboxInClusterConnectionConfig`` (not the synchronous
                ``kubectl port-forward`` tunnel mode).
            tracer_config: OpenTelemetry tracing config forwarded to the SDK.
            sandbox_ready_timeout: Seconds to wait for the Pod to become Ready
                after the claim is created.
            shutdown_after_seconds: If set, the controller will auto-delete
                the sandbox after this many seconds. Safety net so forgotten
                tools do not leak Pods.
            labels: Optional Kubernetes labels to attach to the claim.
            approval_mode: Whether or not approval is required to run this
                tool. Defaults to ``"never_require"``.
            python_command: How to invoke the interpreter inside the Pod.
                Default ``"python3 -u"`` keeps stdout unbuffered.
            exec_timeout: Per-call timeout for the ``python3`` subprocess
                inside the Pod, in seconds.
            code_filename: Scratch file name (under ``/app/``) used to ship the
                model's source to the Pod. The file is overwritten on each
                call.
            _client: Internal hook for tests and shared-client scenarios. When
                provided, the tool does not own the client and will not delete
                it on close.

        Raises:
            ValueError: If ``warmpool`` is empty.
        """
        if not warmpool:
            raise ValueError("warmpool is required.")

        super().__init__(
            name=EXECUTE_CODE_TOOL_NAME,
            description=build_execute_code_description(
                warmpool=warmpool,
                namespace=namespace,
            ),
            approval_mode=approval_mode or "never_require",
            func=self._run_code,
            input_model=EXECUTE_CODE_INPUT_SCHEMA,
        )

        self._warmpool = warmpool
        self._namespace = namespace
        self._connection_config = connection_config
        self._tracer_config = tracer_config
        self._sandbox_ready_timeout = sandbox_ready_timeout
        self._shutdown_after_seconds = shutdown_after_seconds
        self._labels = labels
        self._python_command = python_command
        self._exec_timeout = exec_timeout
        self._code_filename = code_filename

        # Track whether the client was injected by a caller (e.g. shared across
        # providers) or owned by this tool. Only owned clients get cleaned up.
        self._client: AsyncSandboxClient[Any] | None = _client
        self._owns_client = _client is None
        self._sandbox: AsyncSandbox | None = None
        self._sandbox_lock = asyncio.Lock()
        self._closed = False

    @property
    def warmpool(self) -> str:
        """Name of the ``SandboxWarmPool`` this tool claims sandboxes from."""
        return self._warmpool

    @property
    def namespace(self) -> str:
        """Kubernetes namespace where claims are created."""
        return self._namespace

    def build_instructions(self) -> str:
        """Return the CodeAct system-prompt fragment for this tool."""
        return build_codeact_instructions()

    async def _ensure_sandbox(self) -> AsyncSandbox:
        """Lazily claim and return the underlying sandbox, idempotently."""
        # Fast path outside the lock; the authoritative check is inside it.
        sandbox = self._sandbox
        if not self._closed and sandbox is not None and sandbox.is_active:
            return sandbox

        async with self._sandbox_lock:
            # Re-check under the lock so a concurrent close() cannot slip in
            # between the check and the create and leave the new sandbox
            # orphaned (close() flips _closed while holding this same lock).
            if self._closed:
                raise RuntimeError(
                    "AgentSandboxExecuteCodeTool has been closed; create a new tool or provider instance.",
                )
            sandbox = self._sandbox
            if sandbox is not None and sandbox.is_active:
                return sandbox

            if self._client is None:
                # AsyncSandboxClient validates connection_config in __init__ and
                # raises a descriptive ValueError if it is None or a tunnel
                # config, so no extra guard is needed here.
                self._client = AsyncSandboxClient(
                    connection_config=self._connection_config,
                    tracer_config=self._tracer_config,
                )
            # ``k8s-agent-sandbox`` ships no type information, so its generic
            # ``create_sandbox`` return is opaque to the type checker. Treat the
            # client as untyped at this boundary (as the in-tree hyperlight
            # package does for its sandbox) and annotate the concrete handle.
            client: Any = self._client
            new_sandbox: AsyncSandbox = await client.create_sandbox(
                warmpool=self._warmpool,
                namespace=self._namespace,
                sandbox_ready_timeout=self._sandbox_ready_timeout,
                labels=self._labels,
                shutdown_after_seconds=self._shutdown_after_seconds,
            )
            self._sandbox = new_sandbox
            logger.info(
                "agent-sandbox '%s' claimed from warm pool '%s' in namespace '%s'.",
                new_sandbox.sandbox_id,
                self._warmpool,
                self._namespace,
            )
            return new_sandbox

    async def _run_code(self, *, code: str) -> list[Content]:
        """Execute ``code`` inside the sandbox Pod and return tool ``Content``."""
        sandbox = await self._ensure_sandbox()

        # Write the source to a file inside the sandbox, then exec it.
        # Two HTTP round-trips, but it sidesteps shell quoting entirely and
        # the model gets a real path in its tracebacks. The filename is
        # reused so we do not accumulate cruft in /app over a long session.
        files = sandbox.files
        commands = sandbox.commands
        if files is None or commands is None:
            raise RuntimeError("Sandbox connection is not active.")

        await files.write(self._code_filename, code)
        result = await commands.run(
            f"{self._python_command} {self._code_filename}",
            self._exec_timeout,
        )
        return _build_execution_contents(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
        )

    async def close(self) -> None:
        """Terminate the sandbox Pod and clean up the client (if owned).

        Safe to call multiple times. After ``close`` returns, the tool can no
        longer execute code — construct a new instance if needed.
        """
        # Flip _closed and detach the sandbox/client references under the same
        # lock _ensure_sandbox() uses. If a claim is in flight, this blocks
        # until it finishes and then picks up the freshly created sandbox, so
        # nothing is orphaned; if creation has not started, _ensure_sandbox()
        # sees _closed under the lock and refuses to create.
        async with self._sandbox_lock:
            if self._closed:
                return
            self._closed = True
            sandbox = self._sandbox
            self._sandbox = None
            client = self._client
            self._client = None
            owns_client = self._owns_client

        # Terminate outside the lock — these are network round-trips and the
        # references are already detached.
        if sandbox is not None:
            try:
                # terminate() closes the connection and deletes the SandboxClaim.
                await sandbox.terminate()
            except Exception:
                logger.exception(
                    "Failed to terminate sandbox '%s'.",
                    sandbox.sandbox_id,
                )

        if owns_client and client is not None:
            try:
                # close() shuts down any remaining sandbox connections and the
                # underlying async k8s API client (httpx / kubernetes_asyncio).
                await client.close()
            except Exception:
                logger.exception("Failed to clean up AsyncSandboxClient on close.")


def _build_execution_contents(
    *,
    stdout: str,
    stderr: str,
    exit_code: int,
) -> list[Content]:
    """Convert an ``ExecutionResult`` into the framework's ``Content`` list shape."""
    normalized_stdout = (stdout or "").replace("\r\n", "\n").rstrip("\n")
    normalized_stderr = (stderr or "").replace("\r\n", "\n").rstrip("\n")

    outputs: list[Content] = []
    if normalized_stdout:
        outputs.append(Content.from_text(normalized_stdout))

    if exit_code == 0:
        if normalized_stderr:
            outputs.append(Content.from_text(normalized_stderr))
        if not outputs:
            outputs.append(
                Content.from_text("Code executed successfully without output."),
            )
        return outputs

    # Non-zero exit: surface as a structured error so the model can decide to
    # retry / adjust rather than treating it as plain output.
    error_details = normalized_stderr or f"Process exited with code {exit_code}."
    outputs.append(
        Content.from_error(
            message="Execution error",
            error_details=error_details,
        ),
    )
    return outputs
