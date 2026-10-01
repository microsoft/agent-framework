# Copyright (c) Microsoft. All rights reserved.

"""Built, request-owned workflow sources shared by the Foundry protocol hosts."""

from __future__ import annotations

import inspect
import weakref
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from typing import Any, Generic, TypeAlias, TypeVar, cast

from agent_framework import (
    AgentExecutor,
    HistoryProvider,
    InMemoryHistoryProvider,
    RawAgent,
    Workflow,
    WorkflowExecutor,
    WorkflowInvocationKwargs,
    WorkflowRunState,
)

from ._request import WorkflowTurn, validate_default_transport_options
from ._scope import FoundryRequestScope

RequestT = TypeVar("RequestT")
WorkflowSource: TypeAlias = Workflow | Callable[[RequestT], Workflow | Awaitable[Workflow]]
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


def prepare_workflow_kwargs(
    workflow: Workflow,
    turn: WorkflowTurn[Any],
    scope: FoundryRequestScope,
    *,
    options: Mapping[str, Any] | None = None,
    stored: bool = True,
) -> tuple[WorkflowInvocationKwargs, WorkflowInvocationKwargs]:
    """Separate model options, explicit tool kwargs, and trusted current-call context.

    Agent executors use MAF checkpoint history, not downstream service storage.
    Applications keep tool context in ``function_invocation_kwargs``; generation
    options cannot become workflow, agent lifecycle, or storage controls.
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
    agents = list(workflow_executors(workflow))
    for executor in agents:
        agent_value = executor.agent
        if not isinstance(agent_value, RawAgent):
            raise TypeError("Native workflow agent executors require RawAgent to enforce inner storage.")
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
        values = specific_client.setdefault(executor.id, {})
        effective = {**global_client.get("options", {}), **values.get("options", {}), **model_options}
        if stores:
            effective["store"] = False
        values["options"] = effective
        values["additional_function_arguments"] = identity
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
                elif isinstance(executor, AgentExecutor):
                    agent_value = executor.agent
                    resources.append(agent_value)
                    if isinstance(agent_value, RawAgent):
                        agent = cast(RawAgent[Any], agent_value)
                        resources.append(agent.client)
                        resources.extend(agent.context_providers)
                        resources.extend(agent.mcp_tools)
                        tools = agent.default_options.get("tools", ())
                        if isinstance(tools, Sequence):
                            resources.extend(
                                tool for tool in cast(Sequence[object], tools) if not isinstance(tool, Mapping)
                            )

        collect(workflow)
        for resource in resources:
            previous = self._owned.get(id(resource))
            if previous is not None and previous() is resource:
                raise RuntimeError(
                    "Native workflow requests cannot share workflows, executors, agents, clients, or providers. "
                    "Use a request-aware factory that creates fresh instances."
                )
        for resource in resources:
            identifier = id(resource)
            self._owned[identifier] = weakref.ref(resource, lambda ref, key=identifier: self._forget(key, ref))
        return workflow

    def _forget(self, key: int, reference: weakref.ReferenceType[Any]) -> None:
        if self._owned.get(key) is reference:
            del self._owned[key]
