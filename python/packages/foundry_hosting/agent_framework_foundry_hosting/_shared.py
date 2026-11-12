# Copyright (c) Microsoft. All rights reserved.

"""Share request contracts, options, factories, and native-state storage across Foundry hosts."""

from __future__ import annotations

import hashlib
import inspect
import json
import weakref
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Generic, Literal, Protocol, TypeAlias, TypeGuard, cast

from agent_framework import (
    Agent,
    AgentContext,
    AgentExecutor,
    AgentMiddleware,
    AgentResponse,
    AgentRunInputs,
    AgentSession,
    CheckpointID,
    CheckpointStorage,
    Content,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    RawAgent,
    SessionStore,
    SupportsAgentRun,
    Workflow,
    WorkflowAgent,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
    WorkflowExecutor,
    WorkflowInvocationKwargs,
    WorkflowRunState,
)
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.ai.agentserver.core.storage import (
    FoundryStateStore,
    FoundryStorageConflictError,
    FoundryStoragePreconditionError,
)
from azure.ai.agentserver.responses import ResponseContext, ResponsesServerOptions
from azure.ai.agentserver.responses.models import CreateResponse, Item
from typing_extensions import TypeVar

from ._scope import FoundryRequestScope

UnsupportedOptions: TypeAlias = Literal["ignore", "warn", "error"]


def validate_sse_keep_alive_interval(value: int | None) -> None:
    """Validate an explicit heartbeat interval without replacing SDK environment resolution."""
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("sse_keep_alive_interval_seconds must be an integer or None.")
        if value <= 0:
            raise ValueError("sse_keep_alive_interval_seconds must be positive when supplied.")


def _build_response_server_options(  # pyright: ignore[reportUnusedFunction]
    *,
    max_history_items: int | None = None,
    sse_keep_alive_interval_seconds: int | None = None,
    shutdown_grace_period_seconds: int = 10,
    resilient_background: bool = False,
) -> ResponsesServerOptions:
    """Build supported SDK settings, leaving an omitted history limit at its SDK default."""
    validate_sse_keep_alive_interval(sse_keep_alive_interval_seconds)
    if isinstance(shutdown_grace_period_seconds, bool) or not isinstance(shutdown_grace_period_seconds, int):
        raise TypeError("shutdown_grace_period_seconds must be an integer.")
    if shutdown_grace_period_seconds <= 0:
        raise ValueError("shutdown_grace_period_seconds must be positive.")
    if not isinstance(resilient_background, bool):
        raise TypeError("resilient_background must be a boolean.")
    history_options: dict[str, Any] = {}
    if max_history_items is not None:
        if isinstance(max_history_items, bool) or not isinstance(max_history_items, int):
            raise TypeError("max_history_items must be an integer or None.")
        if max_history_items <= 0:
            raise ValueError("max_history_items must be positive when supplied.")
        history_options["default_fetch_history_count"] = max_history_items
    return ResponsesServerOptions(
        sse_keep_alive_interval_seconds=sse_keep_alive_interval_seconds,
        shutdown_grace_period_seconds=shutdown_grace_period_seconds,
        resilient_background=resilient_background,
        steerable_conversations=False,
        **history_options,
    )


InputT = TypeVar("InputT", default=Any)


@dataclass(frozen=True)
class WorkflowTurn(Generic[InputT]):
    """A typed workflow start input or a complete batch of pending replies.

    Args:
        input: Application input accepted by the start executor. ``None`` is not a start input.
        responses: Replies keyed by the exact pending workflow request IDs. The host validates
            the batch against its scoped checkpoint before consuming any reply authority.
        client_kwargs: Existing workflow kwargs forwarded to agent clients, not raw workflow run arguments.
        function_invocation_kwargs: Existing workflow kwargs forwarded to tools. Trusted hosting
            identity is supplied separately and cannot be overridden.
        stream: Application streaming intent for protocols with a custom request parser.
            Responses continues to use its native request's ``stream`` flag.
    """

    input: InputT | None = None
    responses: Mapping[str, Any] | None = None
    client_kwargs: WorkflowInvocationKwargs | Mapping[str, Any] | None = None
    function_invocation_kwargs: WorkflowInvocationKwargs | Mapping[str, Any] | None = None
    stream: bool = False

    def __post_init__(self) -> None:
        if (self.input is None and self.responses is None) or (self.input is not None and self.responses is not None):
            raise ValueError("WorkflowTurn requires exactly one of input or non-empty responses.")
        if self.responses is not None:
            if (
                not isinstance(self.responses, Mapping)
                or not self.responses
                or any(not isinstance(key, str) or not key for key in self.responses)
            ):
                raise ValueError("WorkflowTurn.responses must be a non-empty mapping of request IDs to replies.")
            object.__setattr__(self, "responses", MappingProxyType(dict(self.responses)))
        for name in ("client_kwargs", "function_invocation_kwargs"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, (Mapping, WorkflowInvocationKwargs)):
                raise TypeError(f"WorkflowTurn.{name} must be a mapping or WorkflowInvocationKwargs.")
        if not isinstance(self.stream, bool):
            raise TypeError("WorkflowTurn.stream must be a boolean.")


@dataclass(frozen=True)
class InvocationRun:
    """Messages, per-turn options, and streaming intent parsed from an Invocations request.

    Args:
        messages: MAF message input for this turn, including typed `Message` or `Content` values.
        options: Caller generation options for this turn, separate from agent defaults.
        stream: Whether to stream framed SSE events rather than return a JSON response.

    Raises:
        TypeError: If the messages, options, or streaming intent have invalid types.
    """

    messages: AgentRunInputs
    options: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any]())
    stream: bool = False

    def __post_init__(self) -> None:
        if not (
            isinstance(self.messages, (str, Content, Message))
            or (
                isinstance(self.messages, Sequence)
                and all(isinstance(message, (str, Content, Message)) for message in self.messages)
            )
        ):
            raise TypeError("InvocationRun.messages must be a string, Content, Message, or a sequence of them.")
        if not isinstance(self.options, Mapping) or any(not isinstance(key, str) for key in self.options):
            raise TypeError("InvocationRun.options must be a mapping with string keys.")
        if not isinstance(self.stream, bool):
            raise TypeError("InvocationRun.stream must be a boolean.")


_HOST_CONTROLLED_FIELDS = frozenset({
    "agent",
    "agent_reference",
    "agent_session_id",
    "background",
    "call_id",
    "continuation_token",
    "conversation",
    "conversation_id",
    "extra_body",
    "input",
    "previous_response_id",
    "response_id",
    "service_session_id",
    "session_id",
    "store",
    "stream",
    "user",
    "user_id",
})


_OPTION_NAMES = {"max_output_tokens": "max_tokens", "parallel_tool_calls": "allow_multiple_tool_calls"}


_NATIVE_FIELDS = frozenset(CreateResponse.__annotations__)


def response_run_options(request: CreateResponse) -> dict[str, Any]:
    """Translate native generation fields, with flattened extra-body values winning collisions."""
    native: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    nested_extra: dict[str, Any] = {}
    for name, value in request.items():
        if value is None or (name == "model" and value == ""):
            continue
        if name == "extra_body":
            if not isinstance(value, Mapping) or any(
                not isinstance(key, str) for key in cast(Mapping[object, object], value)
            ):
                raise TypeError("extra_body must be a mapping of model options.")
            if "extra_body" in value:
                raise ValueError("Nested extra_body is not supported; flatten provider options instead.")
            nested_extra.update(cast(Mapping[str, Any], value))
        elif name in _HOST_CONTROLLED_FIELDS:
            continue
        elif name in _NATIVE_FIELDS:
            native[_OPTION_NAMES.get(name, name)] = value
        else:
            extra[name] = value
    return {
        **native,
        **{name: value for name, value in extra.items() if name not in _HOST_CONTROLLED_FIELDS},
        **{name: value for name, value in nested_extra.items() if name not in _HOST_CONTROLLED_FIELDS},
    }


class ResponsesRequest:
    """Expose a copied request, trusted scope, and this turn's input to factories, parsers, and option hooks."""

    def __init__(
        self,
        request: CreateResponse,
        context: ResponseContext,
        scope: FoundryRequestScope,
        options: Mapping[str, Any],
    ) -> None:
        self.request: Mapping[str, Any] = MappingProxyType(deepcopy(dict(request)))
        self.scope = scope
        self.response_id = context.response_id
        self.conversation_id = context.conversation_id
        self._context = context
        self._options: Mapping[str, Any] = MappingProxyType(dict(options))
        self._workflow_responses: Callable[[], Awaitable[dict[str, Any]]] | None = None

    @property
    def options(self) -> Mapping[str, Any]:
        """Return this turn's effective caller options after the hook."""
        return self._options

    def set_options(self, options: Mapping[str, Any]) -> None:
        """Replace the caller options without changing the agent's defaults."""
        self._options = MappingProxyType(dict(options))

    async def get_input_items(self) -> list[Item]:
        """Read only this turn's input items, not earlier conversation history."""
        return list(await self._context.get_input_items())

    async def get_input_text(self) -> str | None:
        """Read this turn's text input, if present."""
        return await self._context.get_input_text()

    async def get_workflow_responses(self) -> dict[str, Any]:
        """Decode replies against this turn's exact scoped workflow checkpoint.

        Use this explicitly in ``parse_input`` to resume a native workflow.
        Unknown, duplicate, stale, and incomplete reply batches are rejected before
        the host claims the workflow or executes any response handler.
        """
        if self._workflow_responses is None:
            raise RuntimeError("Workflow replies require a native workflow host and a pending stored checkpoint.")
        return await self._workflow_responses()

    def _set_workflow_responses(self, loader: Callable[[], Awaitable[dict[str, Any]]]) -> None:
        self._workflow_responses = loader


OptionsHook: TypeAlias = Callable[
    [ResponsesRequest, dict[str, Any]],
    Mapping[str, Any] | Awaitable[Mapping[str, Any]],
]


async def prepare_response_options(request: ResponsesRequest, hook: OptionsHook | None) -> None:
    """Apply a synchronous or asynchronous developer hook to a copy of caller options."""
    if hook is None:
        return
    result = hook(request, dict(request.options))
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, Mapping):
        raise TypeError("prepare_options must return a mapping of MAF run options.")
    request.set_options(result)


async def response_input_messages(request: ResponsesRequest) -> list[Message]:
    """Convert only this Responses turn's input items to the legacy workflow message contract.

    This explicit migration helper does not load outer history, restore checkpoints,
    or decode pending native workflow replies. Native workflows should prefer typed
    application inputs and use ``request.get_workflow_responses()`` for resumable pauses.
    """
    from ._responses_shared import _items_to_messages  # pyright: ignore[reportPrivateUsage]

    return await _items_to_messages(await request.get_input_items())


def validate_request_options(options: Mapping[str, Any]) -> None:
    """Keep hosting identity, storage decisions, and private continuation out of model options."""
    reserved = _HOST_CONTROLLED_FIELDS.intersection(options)
    if reserved:
        raise ValueError(f"prepare_options cannot set host-controlled fields: {', '.join(sorted(reserved))}.")


def validate_default_transport_options(defaults: Mapping[str, Any], *, allow_agent_store: bool) -> None:
    """Reject transport overrides that would bypass the host's inner storage and identity decisions."""
    extra_body = defaults.get("extra_body")
    if extra_body is None:
        return
    if not isinstance(extra_body, Mapping) or any(
        not isinstance(key, str) for key in cast(Mapping[object, object], extra_body)
    ):
        raise TypeError("Agent default extra_body must be a mapping of model options.")
    reserved = _HOST_CONTROLLED_FIELDS.intersection(cast(Mapping[str, Any], extra_body))
    if allow_agent_store:
        reserved -= {"store"}
    if reserved:
        raise ValueError(
            "Agent default extra_body cannot set host-controlled fields: "
            f"{', '.join(sorted(reserved))}. Use explicit agent defaults or history_source='inference_service'."
        )


def validate_unsupported_options(mode: str) -> UnsupportedOptions:
    """Reject misspelled unsupported-options policies at host construction."""
    if mode not in ("ignore", "warn", "error"):
        raise ValueError("unsupported_options must be 'ignore', 'warn', or 'error'.")
    return mode


RequestT = TypeVar("RequestT")
AgentRequestT = TypeVar("AgentRequestT", contravariant=True)


class AgentFactory(Protocol[AgentRequestT]):
    """Create a request-owned agent from the protocol's request context."""

    def __call__(self, *, request: AgentRequestT) -> SupportsAgentRun | Awaitable[SupportsAgentRun]:
        """Create an agent, optionally using the current request."""
        ...


AgentSource: TypeAlias = SupportsAgentRun | AgentFactory[RequestT]


def is_agent(value: object) -> TypeGuard[SupportsAgentRun]:
    return not inspect.isclass(value) and isinstance(value, SupportsAgentRun)


def validate_agent_source(source: object) -> None:
    if is_agent(source):
        _validate_agent_type(source)
        return
    if not callable(source):
        raise TypeError("agent must be an agent instance or a callable that creates one.")
    _validate_agent_factory(source)


def _validate_agent_type(agent: SupportsAgentRun) -> None:
    if isinstance(agent, WorkflowAgent):
        raise TypeError(
            "Agent hosts do not support WorkflowAgent. Use ResponsesWorkflowHostServer or "
            "InvocationsWorkflowHostServer with a factory returning a native Workflow."
        )


def _validate_agent_factory(factory: Callable[..., object]) -> None:
    message = (
        "agent factory must declare a required named 'request' parameter and accept "
        "request=request with no other required arguments."
    )
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError) as exc:
        raise TypeError(message) from exc
    parameter = signature.parameters.get("request")
    if (
        parameter is None
        or parameter.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        or parameter.default is not inspect.Parameter.empty
    ):
        raise TypeError(message)
    try:
        signature.bind(request=object())
    except TypeError as exc:
        raise TypeError(message) from exc


async def resolve_agent(source: AgentSource[RequestT], request: RequestT) -> SupportsAgentRun:
    """Resolve an agent instance or request-scoped agent factory."""
    if is_agent(source):
        _validate_agent_type(source)
        return source

    factory = cast(AgentFactory[RequestT], source)
    result = factory(request=request)
    agent = await result if inspect.isawaitable(result) else result
    if not is_agent(agent):
        raise TypeError("The agent factory must return an object implementing SupportsAgentRun.")
    _validate_agent_type(agent)
    return agent


WorkflowSource: TypeAlias = Callable[[RequestT], Workflow | Awaitable[Workflow]]


_MAX_STRONG_RESOURCE_IDENTITIES = 1024


_CLIENT_CONTROLS = frozenset({
    "additional_function_arguments",
    "agent",
    "background",
    "call_id",
    "checkpoint_id",
    "checkpoint_storage",
    "client_kwargs",
    "continuation_token",
    "conversation",
    "conversation_id",
    "extra_body",
    "function_invocation_kwargs",
    "fresh_factory",
    "input",
    "instructions",
    "messages",
    "middleware",
    "previous_response_id",
    "response_id",
    "responses",
    "service_session_id",
    "session",
    "session_id",
    "agent_session_id",
    "store",
    "stream",
    "tokenizer",
    "tools",
    "user",
    "user_id",
})


class _NativeAgentOptions(AgentMiddleware):
    """Apply native workflow options at the existing agent boundary, not as client **kwargs."""

    def __init__(self, scope: FoundryRequestScope) -> None:
        self.scope = scope

    async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        options = context.client_kwargs.pop("options", {})
        if not isinstance(options, Mapping):
            raise TypeError("Native workflow model options must be a mapping.")
        options = cast(Mapping[str, Any], options)
        if (_CLIENT_CONTROLS - {"store"}).intersection(options):
            raise ValueError("Native workflow model options cannot override hosting or transport controls.")
        if context.session is not None and context.session.service_session_id is not None:
            raise RuntimeError("Native workflow checkpoints cannot resume a private downstream service session.")
        effective = {**(context.options or {}), **options}
        client = getattr(context.agent, "client", None)
        if getattr(client, "STORES_BY_DEFAULT", None) is True:
            effective["store"] = False
        else:
            if effective.pop("store", None) is True:
                raise RuntimeError("The native workflow client cannot safely override a storing runtime option.")
        context.options = effective
        context.client_kwargs["additional_function_arguments"] = {
            "session_id": self.scope.session_id,
            "user_id": self.scope.user_id,
            "call_id": self.scope.call_id,
        }

        def check_result(result: AgentResponse[Any]) -> None:
            if context.session is not None and context.session.service_session_id is not None:
                raise RuntimeError("The native workflow client stored a service session despite store=False.")
            if result.continuation_token is not None:
                raise RuntimeError("Native workflows cannot checkpoint an unfinished provider background response.")

        if context.stream:
            context.stream_result_hooks.append(check_result)
        await call_next()
        if not context.stream and isinstance(context.result, AgentResponse):
            check_result(context.result)


def prepare_workflow_kwargs(
    workflow: Workflow,
    turn: WorkflowTurn[Any],
    scope: FoundryRequestScope,
    *,
    options: Mapping[str, Any] | None = None,
    stored: bool = True,
    fresh_factory: bool = False,
) -> tuple[WorkflowInvocationKwargs, WorkflowInvocationKwargs]:
    """Separate model options, explicit tool kwargs, and trusted current-call context.

    Agent executors use MAF checkpoint history, not downstream service storage.
    Applications keep tool context in ``function_invocation_kwargs``; generation
    options cannot become workflow, agent lifecycle, or storage controls.
    ``Agent`` uses its existing middleware boundary without changing defaults.
    Bare ``RawAgent`` requires ``fresh_factory`` from a validated resolver,
    explicit non-storing defaults, and pre-materialized matching model overrides.
    No nested options keyword is forwarded to a bare client's ``**kwargs``.
    """
    client, _ = workflow._resolve_invocation_kwargs(  # pyright: ignore[reportPrivateUsage]
        turn.client_kwargs or {}, "client_kwargs"
    )
    functions, _ = workflow._resolve_invocation_kwargs(  # pyright: ignore[reportPrivateUsage]
        turn.function_invocation_kwargs or {}, "function_invocation_kwargs"
    )

    def validate_values(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in cast(Mapping[object, Any], value)):
            raise TypeError("Workflow kwargs must have string-keyed mappings for global and executor values.")
        return dict(cast(Mapping[str, Any], value))

    global_client = validate_values(client.get("global_kwargs", {}))
    specific_client = {
        key: validate_values(value) for key, value in cast(dict[str, Any], client.get("executor_kwargs", {})).items()
    }
    for values in (global_client, *specific_client.values()):
        if _CLIENT_CONTROLS.intersection(values):
            raise ValueError("Workflow client kwargs cannot override hosting, agent, or transport controls.")
        if "options" in values:
            values["options"] = validate_values(values["options"])
            if _CLIENT_CONTROLS.intersection(values["options"]):
                raise ValueError("Workflow model options cannot override hosting, agent, or transport controls.")
    model_options = validate_values(options or {})
    if _CLIENT_CONTROLS.intersection(model_options):
        raise ValueError("Workflow model options cannot override hosting, agent, or transport controls.")

    identity = {"session_id": scope.session_id, "user_id": scope.user_id, "call_id": scope.call_id}
    global_client["additional_function_arguments"] = identity
    global_model_options = global_client.pop("options", {})
    agents = list(workflow_agent_targets(workflow))
    for executor_id, agent_value in agents:
        if not isinstance(agent_value, RawAgent):
            raise TypeError(
                "Native workflow custom agents must expose a verifiable client/storage contract. "
                "Use Agent or a validated fresh RawAgent factory."
            )
        agent = cast(RawAgent[Any], agent_value)
        validate_default_transport_options(agent.default_options, allow_agent_store=False)
        if any(
            agent.default_options.get(name) is not None
            for name in _CLIENT_CONTROLS - {"store", "instructions", "tools"}
        ):
            raise ValueError("Native workflow agents cannot have downstream continuation or hosting identity defaults.")
        stores = getattr(agent.client, "STORES_BY_DEFAULT", None)
        if not isinstance(stores, bool) or (not stores and agent.default_options.get("store") is True):
            raise TypeError(
                "Native workflow clients must declare storage support so hosting can disable inner storage."
            )
        if not stored and any(
            isinstance(provider, HistoryProvider)
            and not isinstance(provider, InMemoryHistoryProvider)
            and (provider.store_inputs or provider.store_outputs or provider.store_context_messages)
            for provider in agent.context_providers
        ):
            raise ValueError("store=false cannot disable an external workflow HistoryProvider.")
        values = specific_client.setdefault(executor_id, {})
        effective = {**global_model_options, **values.get("options", {}), **model_options}
        values["additional_function_arguments"] = identity
        if isinstance(agent_value, Agent):
            if stores:
                effective["store"] = False
            values["options"] = effective
            policies = [
                middleware for middleware in agent_value.middleware or () if isinstance(middleware, _NativeAgentOptions)
            ]
            if policies:
                if len(policies) != 1 or policies[0].scope != scope:
                    raise RuntimeError("Native workflow option policy cannot be shared across request scopes.")
            else:
                agent_value.middleware = [*(agent_value.middleware or ()), _NativeAgentOptions(scope)]
        else:
            if not fresh_factory:
                raise TypeError("Native RawAgent workflows require a validated request-aware fresh factory.")
            if stores and agent.default_options.get("store") is not False:
                raise ValueError("A storing native RawAgent client requires explicit factory default store=False.")
            if any(agent.default_options.get(key) != value for key, value in effective.items()):
                raise ValueError(
                    "RawAgent workflow generation overrides must be materialized in the fresh factory defaults."
                )
            values.pop("options", None)
    global_functions = validate_values(functions.get("global_kwargs", {}))
    specific_functions = {
        key: validate_values(value) for key, value in cast(dict[str, Any], functions.get("executor_kwargs", {})).items()
    }
    return (
        WorkflowInvocationKwargs(global_client, specific_client),
        WorkflowInvocationKwargs(global_functions, specific_functions),
    )


def workflow_executors(workflow: Workflow) -> Iterator[AgentExecutor]:
    """Walk agent executors, including those in built subworkflows."""
    for executor in workflow.get_executors_list():
        if isinstance(executor, AgentExecutor):
            yield executor
        elif isinstance(executor, WorkflowExecutor):
            yield from workflow_executors(executor.workflow)


def workflow_agent_targets(workflow: Workflow) -> Iterator[tuple[str, SupportsAgentRun]]:
    """Walk core and registry-backed executor agents with their run-kwargs routing IDs."""
    seen: set[tuple[str, int]] = set()
    for graph in _workflow_graphs(workflow):
        for executor in graph.get_executors_list():
            values: list[object] = []
            if isinstance(executor, AgentExecutor):
                values.append(executor.agent)
            registry = getattr(executor, "_agents", None)
            if isinstance(registry, Mapping):
                values.extend(cast(Mapping[object, object], registry).values())
            for value in values:
                agent = value.agent if isinstance(value, AgentExecutor) else value
                if not isinstance(agent, SupportsAgentRun):
                    raise TypeError("A workflow agent registry contains an unsupported agent value.")
                key = (executor.id, id(agent))
                if key in seen:
                    continue
                seen.add(key)
                yield executor.id, agent


def workflow_agents(workflow: Workflow) -> Iterator[SupportsAgentRun]:
    """Walk every unique agent owned by core or registry-backed executors."""
    seen: set[int] = set()
    for _, agent in workflow_agent_targets(workflow):
        if id(agent) in seen:
            continue
        seen.add(id(agent))
        yield agent


def _workflow_graphs(workflow: Workflow) -> Iterator[Workflow]:
    yield workflow
    for executor in workflow.get_executors_list():
        if isinstance(executor, WorkflowExecutor):
            yield from _workflow_graphs(executor.workflow)


def validate_workflow_provider_state(workflow: Workflow, checkpoint: WorkflowCheckpoint | None = None) -> None:
    """Refuse unexpected private service continuation before pairing or publishing native output."""
    if checkpoint is None:
        for executor in workflow_executors(workflow):
            if executor._session.service_session_id is not None:  # pyright: ignore[reportPrivateUsage]
                raise RuntimeError("The native workflow client stored a service session despite store=False.")
        return
    states = checkpoint.state.get("_executor_state", {})
    if not isinstance(states, Mapping):
        raise ValueError("Invalid native workflow executor checkpoint state.")
    states = cast(Mapping[str, Any], states)
    for executor in workflow.get_executors_list():
        state = states.get(executor.id, {})
        if not isinstance(state, Mapping):
            raise ValueError("Invalid native workflow executor checkpoint state.")
        state = cast(Mapping[str, Any], state)
        if isinstance(executor, AgentExecutor):
            session = state.get("agent_session", {})
            if not isinstance(session, Mapping):
                raise ValueError("Invalid native workflow agent checkpoint state.")
            session = cast(Mapping[str, Any], session)
            if session.get("service_session_id") is not None:
                raise RuntimeError("The native workflow checkpoint contains unexpected private service continuation.")
        elif isinstance(executor, WorkflowExecutor):
            child = state.get("sub_workflow_checkpoint")
            if child is not None:
                if not isinstance(child, WorkflowCheckpoint):
                    raise ValueError("Invalid native subworkflow checkpoint state.")
                validate_workflow_provider_state(executor.workflow, child)


def validate_workflow_source(source: object) -> None:
    """Require a factory accepting the protocol's request object."""
    if isinstance(source, (Workflow, SupportsAgentRun)) or not callable(source) or inspect.isclass(source):
        raise TypeError("workflow must be a request-aware factory returning a freshly built Workflow.")
    try:
        inspect.signature(source).bind(object())
    except (TypeError, ValueError) as exc:
        raise TypeError("A workflow factory must accept one request argument.") from exc


class WorkflowResolver(Generic[RequestT]):
    """Reject reuse of mutable graphs and known request-bound resources.

    This is an ownership guard, not a clone operation or a proof that arbitrary
    application globals are stateless. Factories must allocate their resources
    without performing workflow or tool side effects.
    """

    def __init__(self, source: WorkflowSource[RequestT]) -> None:
        validate_workflow_source(source)
        self.source = source
        self._owned: dict[int, weakref.ReferenceType[Any]] = {}
        self._strong_owned: OrderedDict[int, object] = OrderedDict()

    async def resolve(self, request: RequestT) -> Workflow:
        """Resolve one fresh built graph without sharing executors, agents, clients, or providers."""
        result = self.source(request)
        workflow = await result if inspect.isawaitable(result) else result
        if not isinstance(workflow, Workflow):
            raise TypeError(
                "The workflow factory must return a built Workflow, not an agent, WorkflowAgent, or WorkflowBuilder."
            )
        resources: list[object] = []

        def collect(graph: Workflow) -> None:
            if (
                graph.status != WorkflowRunState.IDLE
                or graph.get_last_checkpoint_id() is not None
                or graph._runner.state.export_state()  # pyright: ignore[reportPrivateUsage]
                or graph._is_run_active()  # pyright: ignore[reportPrivateUsage]
            ):
                raise RuntimeError("Native hosting requires a freshly built, unrun workflow.")
            if graph._runner_context.has_checkpointing():  # pyright: ignore[reportPrivateUsage]
                raise RuntimeError("Native hosting owns checkpoint storage; build the workflow without a store.")
            resources.extend((graph, graph._runner_context))  # pyright: ignore[reportPrivateUsage]
            for executor in graph.get_executors_list():
                resources.append(executor)
                if isinstance(executor, WorkflowExecutor):
                    collect(executor.workflow)

        collect(workflow)
        for agent_value in workflow_agents(workflow):
            resources.append(agent_value)
            if isinstance(agent_value, RawAgent):
                agent = cast(RawAgent[Any], agent_value)
                resources.append(agent.client)
                resources.extend(agent.context_providers)
                resources.extend(agent.mcp_tools)
                tools = agent.default_options.get("tools", ())
                if isinstance(tools, Sequence):
                    resources.extend(tool for tool in cast(Sequence[object], tools) if not isinstance(tool, Mapping))
        unique_resources = {id(resource): resource for resource in resources}
        for identifier, resource in unique_resources.items():
            previous = self._owned.get(id(resource))
            if (previous is not None and previous() is resource) or self._strong_owned.get(identifier) is resource:
                raise RuntimeError(
                    "Native workflow requests cannot share workflows, executors, agents, clients, or providers. "
                    "Use a request-aware factory that creates fresh instances."
                )
        for identifier, resource in unique_resources.items():
            try:
                self._owned[identifier] = weakref.ref(resource, lambda ref, key=identifier: self._forget(key, ref))
            except TypeError:
                # Some valid slotted protocol implementations omit __weakref__.
                # Keep a bounded exact-identity fallback rather than rejecting them
                # or retaining unbounded request resources for the host lifetime.
                self._strong_owned[identifier] = resource
                self._strong_owned.move_to_end(identifier)
                while len(self._strong_owned) > _MAX_STRONG_RESOURCE_IDENTITIES:
                    self._strong_owned.popitem(last=False)
        return workflow

    def _forget(self, key: int, reference: weakref.ReferenceType[Any]) -> None:
        if self._owned.get(key) is reference:
            del self._owned[key]


StoreT = TypeVar("StoreT")


def _encoded_checkpoint_hash(value: Any) -> str:
    """Hash the exact JSON-compatible representation acknowledged by storage."""
    payload = json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _select_latest_checkpoint(checkpoints: list[WorkflowCheckpoint]) -> WorkflowCheckpoint:
    """Return the latest checkpoint, resolving timestamp ties through the lineage chain.

    Mirrors the tie-breaker used by the core checkpoint storages. Checkpoints taken at the
    same superstep boundary can share a timestamp. Among the checkpoints with the newest
    timestamp, one that another of them names as its ``previous_checkpoint_id`` is
    superseded, so the result does not depend on the order the store lists keys in.
    If several unsuperseded candidates remain, the one with the greatest ``checkpoint_id``
    is returned, so the choice among them is stable too.
    """
    newest_timestamp = max(datetime.fromisoformat(cp.timestamp) for cp in checkpoints)
    candidates = [cp for cp in checkpoints if datetime.fromisoformat(cp.timestamp) == newest_timestamp]
    superseded_ids = {cp.previous_checkpoint_id for cp in candidates}
    leaves = [cp for cp in candidates if cp.checkpoint_id not in superseded_ids]
    return max(leaves or candidates, key=lambda cp: cp.checkpoint_id)


def _store_scope(config: AgentConfig, platform_context: FoundryAgentRequestContext) -> FoundryRequestScope | None:
    if not config.is_hosted:
        return None
    return FoundryRequestScope.from_context(config, platform_context)


def _store_name(root: str, scope: FoundryRequestScope | None, context_id: str | None = None) -> str:
    if scope is None:
        return f"{root}/{context_id}" if context_id is not None else root
    name = f"{root}/v2/{scope.storage_key}"
    if context_id is not None:
        name += f"/{hashlib.sha256(context_id.encode('utf-8')).hexdigest()[:24]}"
    return name


class StoreProvider(ABC, Generic[StoreT]):
    """Provide store for a hosting environment."""

    @abstractmethod
    def get_store(self, *, config: AgentConfig, platform_context: FoundryAgentRequestContext) -> StoreT:
        """Get store for a hosting environment.

        Args:
            config: The resolved agent server configuration.
            platform_context: The request-scoped platform context for the current request.

        Returns:
            The store instance for the given hosting environment.
        """


class ContextScopedStoreProvider(ABC, Generic[StoreT]):
    """Provide a context-scoped store for a hosting environment.

    Use this when state must be queried or managed as a collection belonging to
    one context, rather than accessed only by an individual item ID. The context
    can be a conversation ID or another identifier that groups related state.
    """

    @abstractmethod
    def get_store(
        self,
        *,
        config: AgentConfig,
        context_id: str,
        platform_context: FoundryAgentRequestContext,
    ) -> StoreT:
        """Get a context-scoped store for a hosting environment.

        Args:
            config: The resolved agent server configuration.
            context_id: A string that uniquely identifies the context for which the store is scoped.
            platform_context: The request-scoped platform context for the current request.

        Returns:
            The store instance for the given hosting environment and context ID.
        """


# region Checkpoint persistence


class FoundryCheckpointStore:
    """Checkpoint store backed by the `FoundryStateStore`."""

    DEFAULT_ROOT_SCOPE = "checkpoints"

    def __init__(
        self,
        context_id: str,
        platform_context: FoundryAgentRequestContext,
        *,
        allowed_checkpoint_types: list[str] | None = None,
        scope: FoundryRequestScope | None = None,
    ) -> None:
        """Initialize a Foundry-scoped checkpoint store for the given context ID.

        Args:
            context_id: A string that uniquely identifies the context for which the checkpoint store is scoped.
                        This can be used to isolate checkpoints for different workflow runs.
            platform_context: The request-scoped platform context for the current request.
            allowed_checkpoint_types: Additional types (beyond the built-in safe set
                and framework types) that are permitted during checkpoint
                deserialization.  Each entry should be a ``"module:qualname"``
                string (e.g., ``"my_app.models:MyState"``).
            scope: Trusted request scope for hosted sandbox isolation.
        """
        if not context_id:
            raise ValueError("context_id must be provided to initialize a FoundryCheckpointStore.")

        self.context_id = context_id
        self.platform_context = platform_context
        self._allowed_types: frozenset[str] = frozenset(allowed_checkpoint_types or [])
        self._scope = scope

    async def _get_store(self) -> FoundryStateStore:
        return await FoundryStateStore.get_or_create(
            _store_name(self.DEFAULT_ROOT_SCOPE, self._scope, self.context_id),
            user_isolation=True,
        )

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Save a workflow checkpoint to the store.

        Args:
            checkpoint: The workflow checkpoint to save.

        The checkpoint will be serialized to a dictionary and then encoded before being stored.

        Returns:
            The ID of the saved checkpoint.
        """
        from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value

        encoded_checkpoint = encode_checkpoint_value(checkpoint.to_dict())

        store = await self._get_store()
        async with store:
            await store.set_item(checkpoint.checkpoint_id, encoded_checkpoint, call_id=self.platform_context.call_id)
            return checkpoint.checkpoint_id

    async def _load_encoded(self, checkpoint_id: CheckpointID) -> Any:
        store = await self._get_store()
        async with store:
            item = await store.get_item(checkpoint_id, call_id=self.platform_context.call_id)
        if item is None:
            raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id}")
        return item.value

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a workflow checkpoint from the store.

        Args:
            checkpoint_id: The ID of the checkpoint to load.

        Returns:
            The loaded workflow checkpoint.

        Raises:
            WorkflowCheckpointException: If no checkpoint is found with the given ID.
        """
        from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value

        encoded = await self._load_encoded(checkpoint_id)
        return WorkflowCheckpoint.from_dict(decode_checkpoint_value(encoded, allowed_types=self._allowed_types))

    async def load_with_hash(self, checkpoint_id: CheckpointID) -> tuple[WorkflowCheckpoint, str]:
        """Load a checkpoint and hash its exact persisted encoding.

        Pickle is not a canonical serialization across Python versions or repeated
        encodes. Hashing the acknowledged storage value preserves exact tamper
        detection without rejecting an unchanged checkpoint after deserialization.
        """
        from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value

        encoded = await self._load_encoded(checkpoint_id)
        checkpoint = WorkflowCheckpoint.from_dict(decode_checkpoint_value(encoded, allowed_types=self._allowed_types))
        return checkpoint, _encoded_checkpoint_hash(encoded)

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List all workflow checkpoints for a given workflow name."""
        from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value

        store = await self._get_store()
        checkpoints: list[WorkflowCheckpoint] = []
        after: str | None = None
        async with store:
            while True:
                page = await store.list_keys(after=after, call_id=self.platform_context.call_id)
                for item_key in page.keys:
                    item = await store.get_item(item_key.key, call_id=self.platform_context.call_id)
                    if item is None:
                        continue
                    checkpoint = WorkflowCheckpoint.from_dict(
                        decode_checkpoint_value(item.value, allowed_types=self._allowed_types)
                    )
                    if checkpoint.workflow_name == workflow_name:
                        checkpoints.append(checkpoint)
                if not page.has_more or page.last_id is None:
                    break
                after = page.last_id
        return checkpoints

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        store = await self._get_store()
        async with store:
            deleted_item = await store.delete_item(checkpoint_id, call_id=self.platform_context.call_id)
        return deleted_item.id is not None

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        checkpoints = await self.list_checkpoints(workflow_name=workflow_name)
        if not checkpoints:
            return None
        return _select_latest_checkpoint(checkpoints)

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        checkpoints = await self.list_checkpoints(workflow_name=workflow_name)
        return [checkpoint.checkpoint_id for checkpoint in checkpoints]


class CheckpointStoreProvider(ContextScopedStoreProvider[CheckpointStorage]):
    """Provide workflow checkpoint store scoped to a context.

    A workflow context can contain multiple checkpoints. Scoping establishes the
    collection boundary used to list checkpoints, restore the latest checkpoint,
    and clean up older checkpoints without affecting another workflow context.

    This defaults to using the `FoundryCheckpointStore` in all environments.
    """

    def __init__(self, *, allowed_checkpoint_types: list[str] | None = None) -> None:
        """Initialize the provider.

        Args:
            allowed_checkpoint_types: Additional types (beyond the built-in safe set
                and framework types) that are permitted during checkpoint
                deserialization, forwarded to every store this provider creates.
                Each entry should be a ``"module:qualname"`` string
                (e.g., ``"my_app.models:MyState"``).
        """
        self._allowed_checkpoint_types = allowed_checkpoint_types

    def validate_checkpoint_value(self, value: object) -> None:
        """Verify a value can round-trip through this provider's restricted decoder.

        Native hosts use this before claiming a stored typed workflow turn so an
        omitted application allowlist fails before executors or tools run.
        """
        from agent_framework._workflows._checkpoint_encoding import (
            decode_checkpoint_value,
            encode_checkpoint_value,
        )

        decode_checkpoint_value(
            encode_checkpoint_value(value),
            allowed_types=frozenset(self._allowed_checkpoint_types or ()),
        )

    def get_store(
        self,
        *,
        config: AgentConfig,
        context_id: str,
        platform_context: FoundryAgentRequestContext,
    ) -> CheckpointStorage:
        """Get checkpoint store for the requested hosting environment."""
        if not context_id:
            raise ValueError("context_id must be provided to get a checkpoint store.")

        return self.get_store_for_scope(
            context_id=context_id,
            platform_context=platform_context,
            scope=_store_scope(config, platform_context),
        )

    def get_store_for_scope(
        self,
        *,
        scope: FoundryRequestScope | None,
        context_id: str,
        platform_context: FoundryAgentRequestContext,
    ) -> CheckpointStorage:
        """Create a checkpoint store using a host's already validated scope.

        Native hosts use this after protocol-specific identity resolution.
        ``get_store`` retains its strict configuration-based scope validation.

        Args:
            scope: Trusted user and sandbox scope resolved by the protocol host.
            context_id: Native workflow lineage's checkpoint collection.
            platform_context: The current request's storage authorization context.
        """
        return FoundryCheckpointStore(
            context_id,
            platform_context,
            allowed_checkpoint_types=self._allowed_checkpoint_types,
            scope=scope,
        )


# endregion Checkpoint persistence

# region Agent session persistence


class FoundryAgentSessionStore(SessionStore):
    """Agent session store backed by the `FoundryStateStore`."""

    DEFAULT_ROOT_SCOPE = "agent_sessions"

    def __init__(
        self,
        platform_context: FoundryAgentRequestContext,
        *,
        store_name: str | None = None,
        scope: FoundryRequestScope | None = None,
    ) -> None:
        """Initialize session storage.

        Args:
            platform_context: The request-scoped platform context.
            store_name: Logical state-store name. Defaults to `agent_sessions`.
            scope: Trusted Foundry request scope for sandbox-specific storage.
        """
        if store_name is not None and (not isinstance(store_name, str) or not store_name.strip()):
            raise ValueError("store_name must be a non-empty string")
        self.platform_context = platform_context
        self._store_name = self.DEFAULT_ROOT_SCOPE if store_name is None else store_name
        self._scope = scope
        self._etags: dict[str, str | None] = {}

    async def _get_store(self) -> FoundryStateStore:
        return await FoundryStateStore.get_or_create(
            _store_name(self._store_name, self._scope),
            user_isolation=True,
        )

    async def get(self, session_id: str) -> AgentSession | None:
        store = await self._get_store()
        async with store:
            item = await store.get_item(session_id, call_id=self.platform_context.call_id)
        if item is None:
            self._etags[session_id] = None
            return None
        if not item.etag:
            raise RuntimeError("Foundry agent session storage returned a loaded session without an ETag.")
        self._etags[session_id] = item.etag
        return AgentSession.from_dict(item.value)

    async def set(self, session_id: str, session: AgentSession) -> None:
        store = await self._get_store()
        async with store:
            try:
                etag = self._etags.get(session_id)
                if etag is not None:
                    result = await store.set_item(
                        session_id, session.to_dict(), if_match=etag, call_id=self.platform_context.call_id
                    )
                elif self._scope is not None or session_id in self._etags:
                    result = await store.create_item(
                        session_id, session.to_dict(), call_id=self.platform_context.call_id
                    )
                else:
                    result = await store.set_item(session_id, session.to_dict(), call_id=self.platform_context.call_id)
            except (FoundryStorageConflictError, FoundryStoragePreconditionError) as exc:
                raise RuntimeError("Another request advanced this agent session; reload before writing.") from exc
        if not result.etag:
            raise RuntimeError("Foundry agent session storage did not return an ETag after saving.")
        self._etags[session_id] = result.etag

    async def delete(self, session_id: str) -> None:
        store = await self._get_store()
        async with store:
            await store.delete_item(session_id, call_id=self.platform_context.call_id)
        self._etags.pop(session_id, None)


class AgentSessionStoreProvider(StoreProvider[SessionStore]):
    """Provide agent session store for the active hosting environment.

    This defaults to using the `FoundryAgentSessionStore` in all environments.
    """

    def __init__(self, *, store_name: str | None = None) -> None:
        """Initialize the provider.

        Args:
            store_name: Logical state-store name. Defaults to `agent_sessions`.
        """
        if store_name is not None and (not isinstance(store_name, str) or not store_name.strip()):
            raise ValueError("store_name must be a non-empty string")
        self._store_name = store_name

    def _get_scoped_store(
        self, platform_context: FoundryAgentRequestContext, scope: FoundryRequestScope | None
    ) -> SessionStore:
        return FoundryAgentSessionStore(
            platform_context,
            store_name=self._store_name,
            scope=scope,
        )

    def get_store(self, *, config: AgentConfig, platform_context: FoundryAgentRequestContext) -> SessionStore:
        """Get agent session store for the requested hosting environment."""
        return self._get_scoped_store(platform_context, _store_scope(config, platform_context))


# endregion Agent session persistence
