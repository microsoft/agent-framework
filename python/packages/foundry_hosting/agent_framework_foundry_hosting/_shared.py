# Copyright (c) Microsoft. All rights reserved.

"""Share request contracts, options, and request-owned agent and workflow factories across Foundry hosts."""

from __future__ import annotations

import inspect
import warnings
import weakref
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Generic, Literal, Protocol, TypeAlias, TypeGuard, cast

from agent_framework import (
    SKIP_PARSING,
    Agent,
    AgentContext,
    AgentExecutor,
    AgentMiddleware,
    AgentResponse,
    AgentRunInputs,
    Content,
    FunctionTool,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    RawAgent,
    SupportsAgentRun,
    Workflow,
    WorkflowAgent,
    WorkflowCheckpoint,
    WorkflowExecutor,
    WorkflowInvocationKwargs,
    WorkflowRunState,
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


def build_response_server_options(
    *,
    is_workflow: bool,
    history_source: Literal["host_managed", "agent_managed", "inference_service"] = "host_managed",
    background_source: Literal["host_managed", "inference_service"] = "host_managed",
    max_history_items: int | None = None,
    sse_keep_alive_interval_seconds: int | None = None,
    shutdown_grace_period_seconds: int = 10,
    enable_background_recovery: bool = False,
) -> ResponsesServerOptions:
    """Validate supported settings and build SDK options without host initialization.

    Omit an unset history limit so the installed SDK supplies its own default.
    Leave heartbeat environment resolution to the SDK: an explicit positive
    interval wins over a positive ``SSE_KEEPALIVE_INTERVAL``, otherwise disabled.
    Neither SDK ``from_env`` history overrides nor host model defaults are loaded.
    """
    validate_sse_keep_alive_interval(sse_keep_alive_interval_seconds)
    if isinstance(shutdown_grace_period_seconds, bool) or not isinstance(shutdown_grace_period_seconds, int):
        raise TypeError("shutdown_grace_period_seconds must be an integer.")
    if shutdown_grace_period_seconds <= 0:
        raise ValueError("shutdown_grace_period_seconds must be positive.")
    if not isinstance(enable_background_recovery, bool):
        raise TypeError("enable_background_recovery must be a boolean.")
    if history_source not in ("host_managed", "agent_managed", "inference_service"):
        raise ValueError("history_source must be 'host_managed', 'agent_managed', or 'inference_service'.")
    if background_source not in ("host_managed", "inference_service"):
        raise ValueError("background_source must be 'host_managed' or 'inference_service'.")
    if background_source == "inference_service" and (is_workflow or history_source != "inference_service"):
        raise ValueError(
            "Inference-service background requires a regular agent with history_source='inference_service'."
        )
    if enable_background_recovery and not is_workflow and background_source != "inference_service":
        raise ValueError(
            "enable_background_recovery=True requires history_source='inference_service' and "
            "background_source='inference_service' for regular agents."
        )
    kwargs: dict[str, Any] = {}
    if max_history_items is not None:
        if isinstance(max_history_items, bool) or not isinstance(max_history_items, int):
            raise TypeError("max_history_items must be an integer or None.")
        if max_history_items <= 0:
            raise ValueError("max_history_items must be positive when supplied.")
        if is_workflow or history_source != "host_managed":
            warnings.warn(
                "max_history_items is ignored unless used with a regular agent and history_source='host_managed'.",
                UserWarning,
                stacklevel=2,
            )
        else:
            kwargs["default_fetch_history_count"] = max_history_items
    return ResponsesServerOptions(
        sse_keep_alive_interval_seconds=sse_keep_alive_interval_seconds,
        shutdown_grace_period_seconds=shutdown_grace_period_seconds,
        resilient_background=enable_background_recovery,
        steerable_conversations=False,
        **kwargs,
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

_RUN_CONTROLLED_FIELDS = frozenset({
    "additional_function_arguments",
    "client_kwargs",
    "compaction_strategy",
    "function_invocation_kwargs",
    "messages",
    "middleware",
    "session",
    "tokenizer",
})


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
            if reserved := _HOST_CONTROLLED_FIELDS.intersection(cast(Mapping[str, Any], value)):
                raise ValueError(f"extra_body cannot set host-controlled fields: {', '.join(sorted(reserved))}.")
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
        **nested_extra,
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
    """Apply a sync/async option selection hook without changing agent defaults.

    Caller options are omitted when no hook is configured. The host validates the
    hook's replacement mapping before dispatch.
    """
    if hook is None:
        request.set_options({})
        return
    result = hook(request, deepcopy(dict(request.options)))
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, Mapping) or any(not isinstance(key, str) for key in result):
        raise TypeError("prepare_options must return a mapping of MAF run options.")
    request.set_options(deepcopy(dict(result)))


async def response_input_messages(request: ResponsesRequest) -> list[Message]:
    """Convert only this Responses turn's input items to the legacy workflow message contract.

    This explicit migration helper does not load outer history, restore checkpoints,
    or decode pending native workflow replies. Native workflows should prefer typed
    application inputs and use ``request.get_workflow_responses()`` for resumable pauses.
    """
    from ._responses_shared import _items_to_messages  # pyright: ignore[reportPrivateUsage]

    return await _items_to_messages(await request.get_input_items(), approval_storage=None)


def validate_request_options(options: Mapping[str, Any], *, allow_background: bool = False) -> None:
    """Keep hosting identity, storage decisions, and private continuation out of model options.

    With ``allow_background``, a ``background`` value set by the application's
    options hook is passed to the agent unchanged; the application owns that choice.
    """
    if not isinstance(options, Mapping) or any(not isinstance(key, str) for key in options):
        raise TypeError("Run options must be a mapping with string keys.")
    reserved = set((_HOST_CONTROLLED_FIELDS | _RUN_CONTROLLED_FIELDS).intersection(options))
    if allow_background:
        reserved.discard("background")
    if reserved:
        raise ValueError(f"prepare_options cannot set host-controlled fields: {', '.join(sorted(reserved))}.")


def validate_agent_background_options(agent: SupportsAgentRun, *, provider_background: bool) -> None:
    """Reject hidden provider background in hosting-visible agent defaults without mutating them.

    A selected regular-agent provider-background request may use a top-level
    boolean default. A transport ``extra_body`` override is never supported.
    Clients hard-wired internally to provider background are unsupported.
    This does not select execution mode or validate client/storage capabilities.
    """
    defaults = getattr(agent, "default_options", {})
    if not isinstance(defaults, Mapping):
        raise TypeError("Agent default_options must be a mapping.")
    validate_provider_background_options(cast(Mapping[str, Any], defaults), provider_background=provider_background)


def validate_provider_background_options(options: Mapping[str, Any], *, provider_background: bool) -> None:
    """Validate visible provider-background options without changing the execution mode.

    Permit a boolean top-level default only when compatible with the selected
    mode. Reject transport-body overrides even when false. This pure check does
    not inspect client internals or produce protocol responses.
    """
    background = options.get("background")
    if background is not None and not isinstance(background, bool):
        raise TypeError("Provider background must be a boolean.")
    if background is True and not provider_background:
        raise ValueError(
            "Provider background=True requires an outer background request with "
            "history_source='inference_service' and background_source='inference_service'."
        )
    extra_body = options.get("extra_body")
    if isinstance(extra_body, Mapping) and "background" in extra_body:
        raise ValueError("Provider extra_body cannot set host-controlled fields: background.")


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
        raise NotImplementedError


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
        if (_CLIENT_CONTROLS - {"store", "instructions", "tools", "extra_body"}).intersection(effective):
            raise ValueError("Native workflow model options cannot override hosting or transport controls.")
        if (_CLIENT_CONTROLS - {"additional_function_arguments", "middleware"}).intersection(context.client_kwargs):
            raise ValueError("Native workflow client kwargs cannot override hosting or transport controls.")
        validate_default_transport_options(effective, allow_agent_store=False)
        validate_agent_background_options(context.agent, provider_background=False)
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


def _is_stateless_function_tool(value: object) -> bool:
    if type(value) is not FunctionTool:
        return False
    return (
        inspect.isfunction(value.func)
        and value.func.__closure__ is None
        and value._instance is None  # pyright: ignore[reportPrivateUsage]
        and value.max_invocations is None
        and value.max_invocation_exceptions is None
        and (
            value.result_parser is None
            or value.result_parser is SKIP_PARSING
            or (inspect.isfunction(value.result_parser) and value.result_parser.__closure__ is None)
        )
    )


class WorkflowResolver(Generic[RequestT]):
    """Reject reuse of mutable graphs and known request-bound resources.

    This is an ownership guard, not a clone operation or a proof that arbitrary
    application globals, function attributes, or default arguments are stateless.
    Plain function tools without bound instances, closures, or lifetime limits may
    be shared. Applications must keep those functions stateless. Factories must
    allocate mutable resources without performing workflow or tool side effects.
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
                    for tool in cast(Sequence[object], tools):
                        if isinstance(tool, Mapping) or _is_stateless_function_tool(tool):
                            continue
                        resources.append(tool)
                        if isinstance(tool, FunctionTool) and tool._instance is not None:  # pyright: ignore[reportPrivateUsage]
                            resources.append(tool._instance)  # pyright: ignore[reportPrivateUsage]
        unique_resources = {id(resource): resource for resource in resources}
        for identifier, resource in unique_resources.items():
            previous = self._owned.get(id(resource))
            if (previous is not None and previous() is resource) or self._strong_owned.get(identifier) is resource:
                raise RuntimeError(
                    "Native workflow requests cannot share workflows, executors, agents, clients, providers, "
                    "or mutable tools. "
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
