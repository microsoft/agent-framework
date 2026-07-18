# Copyright (c) Microsoft. All rights reserved.

"""ContextProvider that wires the agent-sandbox CodeAct surface into an Agent.

The provider holds a single :class:`AgentSandboxExecuteCodeTool` and, on every
``before_run``, injects it together with a short CodeAct system-prompt fragment.
Because the tool owns one sandbox Pod for the lifetime of the provider, all
runs against the same agent share the same working directory and any
``pip install``-ed packages — which is what makes multi-step agent loops feel
natural without per-call setup cost.

Always close the provider when done (use it as an async context manager, or
call ``await provider.close()``) so the cluster-side Pod and SandboxClaim are
deleted.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

from agent_framework import AgentSession, ContextProvider, SessionContext, SupportsAgentRun
from agent_framework._tools import ApprovalMode
from k8s_agent_sandbox import AsyncSandboxClient
from k8s_agent_sandbox.models import SandboxConnectionConfig, SandboxTracerConfig

from ._execute_code_tool import (
    DEFAULT_EXEC_TIMEOUT_SECONDS,
    DEFAULT_SANDBOX_READY_TIMEOUT_SECONDS,
    AgentSandboxExecuteCodeTool,
)


class AgentSandboxCodeActProvider(ContextProvider):
    """Inject an agent-sandbox-backed ``execute_code`` tool into every agent run.

    Pass this to ``Agent(context_providers=[...])``. The provider creates one
    Kubernetes Sandbox Pod (lazily, on the first ``execute_code`` call) and
    reuses it across every run on the agent.
    """

    DEFAULT_SOURCE_ID = "agent_sandbox_codeact"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        warmpool: str,
        namespace: str = "default",
        connection_config: SandboxConnectionConfig | None = None,
        tracer_config: SandboxTracerConfig | None = None,
        sandbox_ready_timeout: int = DEFAULT_SANDBOX_READY_TIMEOUT_SECONDS,
        shutdown_after_seconds: int | None = None,
        labels: dict[str, str] | None = None,
        approval_mode: ApprovalMode | None = None,
        python_command: str | None = None,
        exec_timeout: int = DEFAULT_EXEC_TIMEOUT_SECONDS,
        _client: AsyncSandboxClient[Any] | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            source_id: Stable identifier used by Agent Framework to attribute
                the provider's contributions to a run. Override only if you
                register more than one CodeAct provider on the same agent.

        Keyword Args:
            warmpool: Name of the ``SandboxWarmPool`` to claim from. Required.
                The warm pool references a ``SandboxTemplate`` and may pre-warm
                pods (``replicas > 0``) to remove cold-start latency, or act as
                a plain on-demand pool (``replicas: 0``).
            namespace: Kubernetes namespace that holds the warm pool and where
                the sandbox Pod will run.
            connection_config: How the SDK reaches the Pod. Required — the async
                client supports ``SandboxDirectConnectionConfig``,
                ``SandboxGatewayConnectionConfig``, and
                ``SandboxInClusterConnectionConfig`` (not the synchronous
                ``kubectl port-forward`` tunnel mode).
            tracer_config: OpenTelemetry tracing config forwarded to the SDK.
            sandbox_ready_timeout: Seconds to wait for the Pod to become Ready
                after the claim is created.
            shutdown_after_seconds: If set, the controller will auto-delete
                the sandbox after this many seconds. Useful as a safety net so
                forgotten providers do not leak Pods.
            labels: Optional Kubernetes labels to attach to the claim.
            approval_mode: Mirrors the Hyperlight provider's parameter so an
                existing CodeAct agent definition can switch backends by
                changing the import.
            python_command: How to invoke the interpreter inside the Pod.
                Defaults to ``"python3 -u"`` when ``None``.
            exec_timeout: Per-call timeout for the ``python3`` subprocess
                inside the Pod, in seconds.
            _client: Internal hook for tests and advanced usage that want to
                inject a pre-built :class:`k8s_agent_sandbox.AsyncSandboxClient`.
                When provided, the provider does not own the client and will
                not delete it on close.
        """
        super().__init__(source_id)
        tool_kwargs: dict[str, Any] = {
            "warmpool": warmpool,
            "namespace": namespace,
            "connection_config": connection_config,
            "tracer_config": tracer_config,
            "sandbox_ready_timeout": sandbox_ready_timeout,
            "shutdown_after_seconds": shutdown_after_seconds,
            "labels": labels,
            "approval_mode": approval_mode,
            "exec_timeout": exec_timeout,
            "_client": _client,
        }
        # Only forward python_command if the caller explicitly set one, so the
        # tool keeps its own default.
        if python_command is not None:
            tool_kwargs["python_command"] = python_command

        self._execute_code_tool = AgentSandboxExecuteCodeTool(**tool_kwargs)

    @property
    def execute_code_tool(self) -> AgentSandboxExecuteCodeTool:
        """The underlying ``execute_code`` :class:`FunctionTool` instance."""
        return self._execute_code_tool

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject the CodeAct instructions and the execute_code tool for this run."""
        context.extend_instructions(
            self.source_id,
            self._execute_code_tool.build_instructions(),
        )
        context.extend_tools(self.source_id, [self._execute_code_tool])

    async def close(self) -> None:
        """Terminate the sandbox Pod owned by this provider. Idempotent."""
        await self._execute_code_tool.close()

    async def __aenter__(self) -> AgentSandboxCodeActProvider:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and terminate the sandbox."""
        await self.close()
