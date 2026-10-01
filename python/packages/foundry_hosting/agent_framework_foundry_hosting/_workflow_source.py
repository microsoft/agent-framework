# Copyright (c) Microsoft. All rights reserved.

"""Built, request-owned workflow sources shared by the Foundry protocol hosts."""

from __future__ import annotations

import inspect
import weakref
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from typing import Any, Generic, TypeAlias, TypeVar, cast

from agent_framework import (
    Agent,
    AgentContext,
    AgentExecutor,
    AgentMiddleware,
    AgentResponse,
    HistoryProvider,
    InMemoryHistoryProvider,
    RawAgent,
    SupportsAgentRun,
    Workflow,
    WorkflowCheckpoint,
    WorkflowExecutor,
    WorkflowInvocationKwargs,
    WorkflowRunState,
)

from ._request import WorkflowTurn, validate_default_transport_options
from ._scope import FoundryRequestScope

RequestT = TypeVar("RequestT")
WorkflowSource: TypeAlias = Workflow | Callable[[RequestT], Workflow | Awaitable[Workflow]]
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
    """Require a built workflow or a factory accepting the protocol's request object."""
    if isinstance(source, Workflow):
        return
    if not callable(source) or inspect.isclass(source):
        raise TypeError("workflow must be a built Workflow or a request-aware factory returning a built Workflow.")
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

    @property
    def is_factory(self) -> bool:
        """Whether this source can produce a new graph for a later turn or recovery."""
        return not isinstance(self.source, Workflow)

    async def resolve(self, request: RequestT) -> Workflow:
        """Resolve one fresh built graph without sharing executors, agents, clients, or providers."""
        if isinstance(self.source, Workflow):
            workflow = self.source
        else:
            result = self.source(request)
            workflow = await result if inspect.isawaitable(result) else result
        if not isinstance(workflow, Workflow):
            raise TypeError(
                "The workflow factory must return a built Workflow, not a WorkflowBuilder or WorkflowAgent."
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
