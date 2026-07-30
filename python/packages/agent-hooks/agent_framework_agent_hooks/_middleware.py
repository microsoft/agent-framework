# Copyright (c) Microsoft. All rights reserved.
"""AGENT-HOOKS-0.1 middleware for Agent Framework.

Implements the agent-hooks control contract
(https://github.com/responsibleai/agent-hooks) on the framework's
middleware pipeline. One agent run is one agent-hooks session:
``agent_startup`` and ``agent_shutdown`` bracket the run, agent-level
middleware emits ``input``/``output``, chat middleware emits the model
bracket, and function middleware emits the tool bracket. Block verdicts
terminate the run via ``MiddlewareTermination``; transforms write back
through the middleware context so execution uses exactly the value the
interceptors approved. See MAPPING.md for the seam-by-seam rationale
and known gaps.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from agent_framework import (
    AgentContext,
    AgentMiddleware,
    ChatContext,
    ChatMiddleware,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareTermination,
)
from agent_hooks import (
    AgentContextBuilder,
    ApprovalResolver,
    CompositionConfig,
    EnforcementMode,
    IdentityProvider,
    InterceptionBlocked,
    InterceptionEmitter,
    InterceptionRecord,
    Interceptor,
)

_FRAMEWORK = "agent-framework"

# Carries the per-run emitter/builder from the agent middleware to the
# inner chat/function pipelines (their contexts do not share metadata).
_RUN: ContextVar["_RunState | None"] = ContextVar("agent_hooks_run", default=None)


@dataclass(slots=True)
class _RunState:
    emitter: InterceptionEmitter
    builder: AgentContextBuilder


def _terminate(exc: InterceptionBlocked) -> MiddlewareTermination:
    verdict = exc.result.verdict
    reason = getattr(verdict, "reason", None) or "blocked"
    point = exc.result.interception_point
    return MiddlewareTermination(f"agent-hooks {getattr(point, 'value', point)}: {reason}")


def _message_to_wire(message: Any) -> dict[str, Any]:
    """Best-effort projection of a framework Message to a wire dict."""
    role = getattr(message, "role", None)
    role = getattr(role, "value", role) or "user"
    text = getattr(message, "text", None)
    if text is None:
        contents = getattr(message, "contents", None)
        text = "" if contents is None else str(contents)
    return {"role": str(role), "content": text}


def _messages_to_wire(messages: Sequence[Any] | None) -> list[dict[str, Any]]:
    return [_message_to_wire(m) for m in (messages or [])]


def _result_content(result: Any) -> Any:
    for attr in ("text", "content"):
        value = getattr(result, attr, None)
        if value is not None:
            return value
    return None if result is None else str(result)


def _result_tool_calls(result: Any) -> list[dict[str, Any]]:
    """Best-effort extraction of tool calls from a chat result (MAPPING.md gap 3)."""
    calls: list[dict[str, Any]] = []
    for message in getattr(result, "messages", None) or []:
        for content in getattr(message, "contents", None) or []:
            call_id = getattr(content, "call_id", None)
            name = getattr(content, "name", None)
            if call_id is not None and name is not None:
                arguments = getattr(content, "arguments", None)
                if not isinstance(arguments, Mapping):
                    arguments = {}
                calls.append({"id": str(call_id), "name": str(name), "args": dict(arguments)})
    return calls


def _finish_reason(result: Any) -> str:
    reason = getattr(result, "finish_reason", None)
    return str(getattr(reason, "value", reason) or "stop")


def _arguments_to_dict(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, Mapping):
        return dict(arguments)
    dump = getattr(arguments, "model_dump", None)
    if callable(dump):
        return dict(dump())
    return {"value": str(arguments)}


def _result_to_wire(value: Any) -> Any:
    """Best-effort JSON projection of a tool result for post_tool_call."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _result_to_wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_result_to_wire(v) for v in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        with contextlib.suppress(Exception):
            return dump()
    return str(value)


class AgentHooksAgentMiddleware(AgentMiddleware):
    """Run bracket: ``agent_startup``, ``input``, ``output``, ``agent_shutdown``."""

    def __init__(
        self,
        interceptors: Sequence[Interceptor],
        *,
        resolver: ApprovalResolver | None = None,
        mode: EnforcementMode = EnforcementMode.ENFORCE,
        composition: CompositionConfig | None = None,
        identity_provider: str | IdentityProvider | None = "jcs-sha256",
        timeout: float | None = 5.0,
        record_sink: Callable[[InterceptionRecord], None] | None = None,
    ) -> None:
        self._interceptors = list(interceptors)
        self._resolver = resolver
        self._mode = mode
        self._composition = composition
        self._identity_provider = identity_provider
        self._timeout = timeout
        self._record_sink = record_sink

    def _new_emitter(self) -> InterceptionEmitter:
        emitter = InterceptionEmitter(
            mode=self._mode,
            resolver=self._resolver,
            timeout=self._timeout,
            composition=self._composition,
            identity_provider=self._identity_provider,
        )
        for interceptor in self._interceptors:
            emitter.register(interceptor)
        if self._record_sink is not None:
            emitter.set_record_sink(self._record_sink)
        return emitter

    async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        agent = getattr(context, "agent", None)
        agent_id = str(getattr(agent, "name", None) or getattr(agent, "id", None) or "agent")
        builder = AgentContextBuilder(agent_id=agent_id, framework=_FRAMEWORK, session_id=uuid.uuid4().hex)
        emitter = self._new_emitter()
        state = _RunState(emitter=emitter, builder=builder)
        token = _RUN.set(state)
        shutdown_reason = "completed"
        try:
            tools = [str(getattr(t, "name", t)) for t in (getattr(context, "tools", None) or [])]
            try:
                await emitter.emit(builder.agent_startup(tools_registered=tools))
                await emitter.emit(builder.input(content=_messages_to_wire(context.messages)))
            except InterceptionBlocked as exc:
                shutdown_reason = "error"
                raise _terminate(exc) from exc

            try:
                await call_next()
            except BaseException:
                shutdown_reason = "error"
                raise

            if not context.stream:
                try:
                    await emitter.emit(builder.output(content=_result_content(context.result)))
                except InterceptionBlocked as exc:
                    context.result = None
                    shutdown_reason = "error"
                    raise _terminate(exc) from exc
            # Streaming: pre-action points are enforced; output content is
            # not available until the stream is consumed (MAPPING.md gap 1).
        finally:
            # Shutdown blocks are record-only per the spec; nothing to halt.
            with contextlib.suppress(InterceptionBlocked):
                await emitter.emit(builder.agent_shutdown(reason=shutdown_reason))
            _RUN.reset(token)


class AgentHooksChatMiddleware(ChatMiddleware):
    """Model bracket: ``pre_model_call`` and ``post_model_call``."""

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        state = _RUN.get()
        if state is None:
            await call_next()
            return
        options = context.options or {}
        model_id = str(options.get("model") or type(getattr(context, "client", None)).__name__)
        try:
            await state.emitter.emit(
                state.builder.pre_model_call(model_id=model_id, messages=_messages_to_wire(context.messages))
            )
        except InterceptionBlocked as exc:
            raise _terminate(exc) from exc

        await call_next()

        if context.stream:
            return  # MAPPING.md gap 1: finalized content unavailable here.
        result = context.result
        try:
            await state.emitter.emit(
                state.builder.post_model_call(
                    model_id=model_id,
                    content=_result_content(result),
                    tool_calls=_result_tool_calls(result),
                    finish_reason=_finish_reason(result),
                )
            )
        except InterceptionBlocked as exc:
            context.result = None
            raise _terminate(exc) from exc


class AgentHooksFunctionMiddleware(FunctionMiddleware):
    """Tool bracket: ``pre_tool_call`` and ``post_tool_call``."""

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        state = _RUN.get()
        if state is None:
            await call_next()
            return
        call_id = uuid.uuid4().hex
        name = str(getattr(context.function, "name", context.function))
        args = _arguments_to_dict(context.arguments)
        try:
            outcome = await state.emitter.emit(state.builder.pre_tool_call(call_id=call_id, name=name, args=args))
        except InterceptionBlocked as exc:
            raise _terminate(exc) from exc
        effective = outcome.target
        if isinstance(effective, Mapping) and dict(effective) != args:
            # A transform rewrote the arguments: execute the approved value.
            args = dict(effective)
            context.arguments = args

        try:
            await call_next()
        except MiddlewareTermination:
            raise
        except BaseException as exc:
            # The invocation completed with an error: the contract still
            # brackets it with post_tool_call (tool_result.is_error = true).
            with contextlib.suppress(InterceptionBlocked):
                await state.emitter.emit(
                    state.builder.post_tool_call(
                        call_id=call_id, name=name, args=args, value=type(exc).__name__, is_error=True
                    )
                )
            raise

        try:
            await state.emitter.emit(
                state.builder.post_tool_call(
                    call_id=call_id, name=name, args=args, value=_result_to_wire(context.result)
                )
            )
        except InterceptionBlocked as exc:
            context.result = None
            raise _terminate(exc) from exc


def agent_hooks_middleware(
    interceptors: Sequence[Interceptor],
    *,
    resolver: ApprovalResolver | None = None,
    mode: EnforcementMode = EnforcementMode.ENFORCE,
    composition: CompositionConfig | None = None,
    identity_provider: str | IdentityProvider | None = "jcs-sha256",
    timeout: float | None = 5.0,
    record_sink: Callable[[InterceptionRecord], None] | None = None,
) -> list[AgentMiddleware | ChatMiddleware | FunctionMiddleware]:
    """Build the middleware trio that emits AGENT-HOOKS-0.1 interception points.

    Args:
        interceptors: agent-hooks interceptors, dispatched per the composition
            profile (default ``sequential/first_deny`` with ``on_approval: stop``).
        resolver: Optional approval resolver for liftable denies.
        mode: ``ENFORCE`` honours verdicts; ``EVALUATE_ONLY`` records them.
        composition: Composition profile and knobs; ``None`` uses the default.
        identity_provider: ``"jcs-sha256"`` (default), a custom provider, or
            ``None`` for identity-unbound records.
        timeout: Per-interceptor timeout in seconds (spec RECOMMENDED 5.0).
        record_sink: Optional callable receiving every interception record.

    Returns:
        Middleware instances to pass to ``Agent(middleware=[...])``.

    Example:
        .. code-block:: python

            from agent_framework import Agent
            from agent_framework_agent_hooks import agent_hooks_middleware

            agent = Agent(
                client=client,
                name="assistant",
                middleware=agent_hooks_middleware([EgressGuard()]),
            )
    """
    return [
        AgentHooksAgentMiddleware(
            interceptors,
            resolver=resolver,
            mode=mode,
            composition=composition,
            identity_provider=identity_provider,
            timeout=timeout,
            record_sink=record_sink,
        ),
        AgentHooksChatMiddleware(),
        AgentHooksFunctionMiddleware(),
    ]
