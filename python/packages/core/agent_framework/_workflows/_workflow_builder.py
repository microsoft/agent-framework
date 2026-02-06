# Copyright (c) Microsoft. All rights reserved.

import inspect
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace

from .._agents import SupportsAgentRun
from .._threads import AgentThread
from ..observability import OtelAttr, capture_exception, create_workflow_span
from ._agent_executor import AgentExecutor
from ._agent_utils import resolve_agent_id
from ._checkpoint import CheckpointStorage
from ._const import DEFAULT_MAX_ITERATIONS
from ._edge import (
    Case,
    Default,
    EdgeCondition,
    EdgeGroup,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    InternalEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
    SwitchCaseEdgeGroupCase,
    SwitchCaseEdgeGroupDefault,
)
from ._executor import Executor
from ._runner_context import InProcRunnerContext
from ._validation import validate_workflow_graph
from ._workflow import Workflow

if sys.version_info >= (3, 11):
    from typing import Self  # type: ignore # pragma: no cover
else:
    from typing_extensions import Self  # type: ignore # pragma: no cover


logger = logging.getLogger(__name__)


@dataclass
class _EdgeRegistration:
    """A data class representing an edge registration in the workflow builder.

    Args:
        source: The registered source name.
        target: The registered target name.
        condition: An optional condition function `(data) -> bool | Awaitable[bool]`.
    """

    source: str
    target: str
    condition: EdgeCondition | None = None


@dataclass
class _FanOutEdgeRegistration:
    """A data class representing a fan-out edge registration in the workflow builder.

    Args:
        source: The registered source name.
        targets: A list of registered target names.
    """

    source: str
    targets: list[str]


@dataclass
class _FanInEdgeRegistration:
    """A data class representing a fan-in edge registration in the workflow builder.

    Args:
        sources: A list of registered source names.
        target: The registered target name.
    """

    sources: list[str]
    target: str


@dataclass
class _SwitchCaseEdgeGroupRegistration:
    """A data class representing a switch-case edge group registration in the workflow builder.

    Args:
        source: The registered source name.
        cases: A list of case objects that determine the target executor for each message.
    """

    source: str
    cases: list[Case | Default]


@dataclass
class _MultiSelectionEdgeGroupRegistration:
    """A data class representing a multi-selection edge group registration in the workflow builder.

    Args:
        source: The registered source name.
        targets: A list of registered target names.
        selection_func: A function that selects target executors for messages.
            Takes (message, list[registered target names]) and returns list[registered target names].
    """

    source: str
    targets: list[str]
    selection_func: Callable[[Any, list[str]], list[str]]


class WorkflowBuilder:
    """A builder class for constructing workflows.

    This class provides a fluent API for defining workflow graphs by connecting executors
    with edges and configuring execution parameters. Call :meth:`build` to create an
    immutable :class:`Workflow` instance.

    Example:
        .. code-block:: python

            from typing_extensions import Never
            from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


            class UpperCaseExecutor(Executor):
                @handler
                async def process(self, text: str, ctx: WorkflowContext[str]) -> None:
                    await ctx.send_message(text.upper())


            class ReverseExecutor(Executor):
                @handler
                async def process(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
                    await ctx.yield_output(text[::-1])


            # Build a workflow
            workflow = (
                WorkflowBuilder()
                .register_executors({
                    "UpperCase": lambda: UpperCaseExecutor(id="upper"),
                    "Reverse": lambda: ReverseExecutor(id="reverse"),
                })
                .add_edge("UpperCase", "Reverse")
                .set_start_executor("UpperCase")
                .build()
            )

            # Run the workflow
            events = await workflow.run("hello")
            print(events.get_outputs())  # ['OLLEH']
    """

    def __init__(
        self,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        name: str | None = None,
        description: str | None = None,
    ):
        """Initialize the WorkflowBuilder with an empty list of edges and no starting executor.

        Args:
            max_iterations: Maximum number of iterations for workflow convergence. Default is 100.
            name: Optional human-readable name for the workflow.
            description: Optional description of what the workflow does.
        """
        self._edge_groups: list[EdgeGroup] = []
        self._executors: dict[str, Executor] = {}
        self._start_executor: Executor | str | None = None
        self._checkpoint_storage: CheckpointStorage | None = None
        self._max_iterations: int = max_iterations
        self._name: str | None = name
        self._description: str | None = description
        # Maps underlying SupportsAgentRun object id -> wrapped Executor so we reuse the same wrapper
        # across set_start_executor / add_edge calls. This avoids multiple AgentExecutor instances
        # being created for the same agent.
        self._agent_wrappers: dict[str, Executor] = {}

        # Registrations for lazy initialization of executors
        self._edge_registry: list[
            _EdgeRegistration
            | _FanOutEdgeRegistration
            | _SwitchCaseEdgeGroupRegistration
            | _MultiSelectionEdgeGroupRegistration
            | _FanInEdgeRegistration
        ] = []
        self._executor_registry: dict[str, Callable[[], Executor | Awaitable[Executor]]] = {}

        # Output executors filter; if set, only outputs from these executors are yielded
        self._output_executors: list[Executor | SupportsAgentRun | str] = []

    # Agents auto-wrapped by builder now always stream incremental updates.

    def _add_executor(self, executor: Executor) -> str:
        """Add an executor to the map and return its ID."""
        existing = self._executors.get(executor.id)
        if existing is not None:
            if existing is executor:
                # Already added
                return executor.id
            # ID conflict
            raise ValueError(f"Duplicate executor ID '{executor.id}' detected in workflow.")

        # New executor
        self._executors[executor.id] = executor
        # Add an internal edge group for each unique executor
        self._edge_groups.append(InternalEdgeGroup(executor.id))  # type: ignore[call-arg]

        return executor.id

    def _maybe_wrap_agent(self, candidate: Executor | SupportsAgentRun) -> Executor:
        """If the provided object implements SupportsAgentRun, wrap it in an AgentExecutor.

        This allows fluent builder APIs to directly accept agents instead of
        requiring callers to manually instantiate AgentExecutor.

        Args:
            candidate: The executor or agent to wrap.

        Returns:
            An Executor instance, wrapping the agent if necessary.
        """
        try:  # Local import to avoid hard dependency at import time
            from agent_framework import SupportsAgentRun  # type: ignore
        except Exception:  # pragma: no cover - defensive
            SupportsAgentRun = object  # type: ignore

        if isinstance(candidate, Executor):  # Already an executor
            return candidate
        if isinstance(candidate, SupportsAgentRun):  # type: ignore[arg-type]
            # Reuse existing wrapper for the same agent instance if present
            agent_instance_id = str(id(candidate))
            existing = self._agent_wrappers.get(agent_instance_id)
            if existing is not None:
                return existing
            executor_id = resolve_agent_id(candidate)
            if executor_id in self._executors:
                raise ValueError(
                    f"Duplicate executor ID '{executor_id}' from agent. "
                    "Agent IDs or names must be unique within a workflow."
                )
            wrapper = AgentExecutor(candidate, id=executor_id)
            self._agent_wrappers[agent_instance_id] = wrapper
            return wrapper

        raise TypeError(
            f"WorkflowBuilder expected an Executor or SupportsAgentRun instance; got {type(candidate).__name__}."
        )

    def register_executors(self, executor_factories: dict[str, Callable[[], Executor | Awaitable[Executor]]]) -> Self:
        """Register multiple executor factory functions for lazy initialization.

        This method allows you to register multiple factory functions at once. Each
        executor is instantiated only when the workflow is built, enabling deferred
        initialization and reducing builder boilerplate.

        Args:
            executor_factories: A mapping of executor names to factory callables that
                return Executor instances when called.

        Raises:
            ValueError: If executor_factories is empty or contains empty names, or if a name is already registered.
            TypeError: If an executor factory is not callable.

        Example:
            .. code-block:: python
                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


                class UpperCaseExecutor(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[str]) -> None:
                        await ctx.send_message(text.upper())


                class ReverseExecutor(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[str]) -> None:
                        await ctx.yield_output(text[::-1])


                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "UpperCase": lambda: UpperCaseExecutor(id="upper"),
                        "Reverse": lambda: ReverseExecutor(id="reverse"),
                    })
                    .set_start_executor("UpperCase")
                    .add_edge("UpperCase", "Reverse")
                    .build()
                )
        """
        if not executor_factories:
            raise ValueError("Executor factories cannot be empty.")

        for name, factory_function in executor_factories.items():
            if not name or not name.strip():
                raise ValueError("Executor factory name cannot be empty or whitespace-only")
            if not callable(factory_function):
                raise TypeError(f"Executor factory for '{name}' must be callable.")
            if name in self._executor_registry:
                raise ValueError(f"An executor factory with the name '{name}' is already registered.")

        for name, factory_function in executor_factories.items():
            self._executor_registry[name] = factory_function

        return self

    def register_agent(
        self,
        factory_func: Callable[[], SupportsAgentRun],
        name: str,
        agent_thread: AgentThread | None = None,
    ) -> Self:
        """Register an agent factory function for lazy initialization.

        This method allows you to register a factory function that creates an agent.
        The agent will be instantiated and wrapped in an AgentExecutor only when the workflow is built,
        enabling deferred initialization and potentially reducing startup time.

        Args:
            factory_func: A callable that returns an SupportsAgentRun instance when called.
            name: The name of the registered agent factory. This doesn't have to match
                  the agent's internal name. But it must be unique within the workflow.
            agent_thread: The thread to use for running the agent. If None, a new thread will be created when
                          the agent is instantiated.

        Example:
            .. code-block:: python

                from agent_framework import WorkflowBuilder
                from agent_framework_anthropic import AnthropicAgent


                # Build a workflow
                workflow = (
                    WorkflowBuilder()
                    .register_executors({"SomeOtherExecutor": lambda: ...})
                    .register_agent(
                        lambda: AnthropicAgent(name="writer", model="claude-3-5-sonnet-20241022"),
                        name="WriterAgent",
                        output_response=True,
                    )
                    .add_edge("SomeOtherExecutor", "WriterAgent")
                    .set_start_executor("SomeOtherExecutor")
                    .build()
                )
        """
        if name in self._executor_registry:
            raise ValueError(f"An agent factory with the name '{name}' is already registered.")

        def wrapped_factory() -> AgentExecutor:
            agent = factory_func()
            return AgentExecutor(
                agent,
                agent_thread=agent_thread,
            )

        self._executor_registry[name] = wrapped_factory

        return self

    def add_edge(
        self,
        source: Executor | SupportsAgentRun | str,
        target: Executor | SupportsAgentRun | str,
        condition: EdgeCondition | None = None,
    ) -> Self:
        """Add a directed edge between two executors.

        The output types of the source and the input types of the target must be compatible.
        Messages sent by the source executor will be routed to the target executor.

        Args:
            source: The source executor or registered name of the source factory for the edge.
            target: The target executor or registered name of the target factory for the edge.
            condition: An optional condition function `(data) -> bool | Awaitable[bool]`
                       that determines whether the edge should be traversed.
                       Example: `lambda data: data["ready"]`.

            Note: If instances are provided for both source and target, they will be shared across
                all workflow instances created from the built Workflow. To avoid this, consider
                registering the executors and agents using `register_executors` and `register_agent`
                and referencing them by factory name for lazy initialization instead.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Example:
            .. code-block:: python

                from typing_extensions import Never
                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


                class ProcessorA(Executor):
                    @handler
                    async def process(self, data: str, ctx: WorkflowContext[int]) -> None:
                        await ctx.send_message(len(data))


                class ProcessorB(Executor):
                    @handler
                    async def process(self, count: int, ctx: WorkflowContext[Never, str]) -> None:
                        await ctx.yield_output(f"Processed {count} characters")


                # Connect executors with an edge
                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "ProcessorA": lambda: ProcessorA(id="a"),
                        "ProcessorB": lambda: ProcessorB(id="b"),
                    })
                    .add_edge("ProcessorA", "ProcessorB")
                    .set_start_executor("ProcessorA")
                    .build()
                )

                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "ProcessorA": lambda: ProcessorA(id="a"),
                        "ProcessorB": lambda: ProcessorB(id="b"),
                    })
                    .add_edge("ProcessorA", "ProcessorB", condition=only_large_numbers)
                    .set_start_executor("ProcessorA")
                    .build()
                )
        """
        if (isinstance(source, str) and not isinstance(target, str)) or (
            not isinstance(source, str) and isinstance(target, str)
        ):
            raise ValueError(
                "Both source and target must be either registered factory names (str) or "
                "Executor/SupportsAgentRun instances."
            )

        if isinstance(source, str) and isinstance(target, str):
            # Both are names; defer resolution to build time
            self._edge_registry.append(_EdgeRegistration(source=source, target=target, condition=condition))
            return self

        # Both are Executor/SupportsAgentRun instances; wrap and add now
        source_exec = self._maybe_wrap_agent(source)  # type: ignore[arg-type]
        target_exec = self._maybe_wrap_agent(target)  # type: ignore[arg-type]
        source_id = self._add_executor(source_exec)
        target_id = self._add_executor(target_exec)
        self._edge_groups.append(SingleEdgeGroup(source_id, target_id, condition))
        return self

    def add_fan_out_edges(
        self,
        source: Executor | SupportsAgentRun | str,
        targets: Sequence[Executor | SupportsAgentRun | str],
    ) -> Self:
        """Add multiple edges to the workflow where messages from the source will be sent to all targets.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source will be broadcast to all target executors concurrently.

        Args:
            source: The source executor or registered name of the source factory for the edges.
            targets: A list of target executors or registered names of the target factories for the edges.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Note: If instances are provided for source and targets, they will be shared across
              all workflow instances created from the built Workflow. To avoid this, consider
              registering the executors and agents using `register_executors` and `register_agent`
              and referencing them by factory name for lazy initialization instead.

        Example:
            .. code-block:: python

                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


                class DataSource(Executor):
                    @handler
                    async def generate(self, count: int, ctx: WorkflowContext[str]) -> None:
                        for i in range(count):
                            await ctx.send_message(f"data_{i}")


                class ValidatorA(Executor):
                    @handler
                    async def validate(self, data: str, ctx: WorkflowContext) -> None:
                        print(f"ValidatorA: {data}")


                class ValidatorB(Executor):
                    @handler
                    async def validate(self, data: str, ctx: WorkflowContext) -> None:
                        print(f"ValidatorB: {data}")


                # Broadcast to multiple validators
                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "DataSource": lambda: DataSource(id="source"),
                        "ValidatorA": lambda: ValidatorA(id="val_a"),
                        "ValidatorB": lambda: ValidatorB(id="val_b"),
                    })
                    .add_fan_out_edges("DataSource", ["ValidatorA", "ValidatorB"])
                    .set_start_executor("DataSource")
                    .build()
                )
        """
        if (isinstance(source, str) and not all(isinstance(t, str) for t in targets)) or (
            not isinstance(source, str) and any(isinstance(t, str) for t in targets)
        ):
            raise ValueError(
                "Both source and targets must be either registered factory names (str) or "
                "Executor/SupportsAgentRun instances."
            )

        if isinstance(source, str) and all(isinstance(t, str) for t in targets):
            # Both are names; defer resolution to build time
            self._edge_registry.append(_FanOutEdgeRegistration(source=source, targets=list(targets)))  # type: ignore
            return self

        # Both are Executor/SupportsAgentRun instances; wrap and add now
        source_exec = self._maybe_wrap_agent(source)  # type: ignore[arg-type]
        target_execs = [self._maybe_wrap_agent(t) for t in targets]  # type: ignore[arg-type]
        source_id = self._add_executor(source_exec)
        target_ids = [self._add_executor(t) for t in target_execs]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids))  # type: ignore[call-arg]

        return self

    def add_switch_case_edge_group(
        self,
        source: Executor | SupportsAgentRun | str,
        cases: Sequence[Case | Default],
    ) -> Self:
        """Add an edge group that represents a switch-case statement.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source executor will be sent to one of the target executors based on
        the provided conditions.

        Think of this as a switch statement where each target executor corresponds to a case.
        Each condition function will be evaluated in order, and the first one that returns True
        will determine which target executor receives the message.

        The default case (if provided) will receive messages that fall through all conditions
        (i.e., no condition matched).

        Args:
            source: The source executor or registered name of the source factory for the edge group.
            cases: A list of case objects that determine the target executor for each message.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Note: If instances are provided for source and case targets, they will be shared across
              all workflow instances created from the built Workflow. To avoid this, consider
              registering the executors and agents using `register_executors` and `register_agent`
              and referencing them by factory name for lazy initialization instead.

        Example:
            .. code-block:: python

                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler, Case, Default
                from dataclasses import dataclass


                @dataclass
                class Result:
                    score: int


                class Evaluator(Executor):
                    @handler
                    async def evaluate(self, text: str, ctx: WorkflowContext[Result]) -> None:
                        await ctx.send_message(Result(score=len(text)))


                class HighScoreHandler(Executor):
                    @handler
                    async def handle(self, result: Result, ctx: WorkflowContext) -> None:
                        print(f"High score: {result.score}")


                class LowScoreHandler(Executor):
                    @handler
                    async def handle(self, result: Result, ctx: WorkflowContext) -> None:
                        print(f"Low score: {result.score}")


                # Route based on score value
                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "Evaluator": lambda: Evaluator(id="eval"),
                        "HighScoreHandler": lambda: HighScoreHandler(id="high"),
                        "LowScoreHandler": lambda: LowScoreHandler(id="low"),
                    })
                    .add_switch_case_edge_group(
                        "Evaluator",
                        [
                            Case(condition=lambda r: r.score > 10, target="HighScoreHandler"),
                            Default(target="LowScoreHandler"),
                        ],
                    )
                    .set_start_executor("Evaluator")
                    .build()
                )
        """
        if (isinstance(source, str) and not all(isinstance(case.target, str) for case in cases)) or (
            not isinstance(source, str) and any(isinstance(case.target, str) for case in cases)
        ):
            raise ValueError(
                "Both source and case targets must be either registered factory names (str) "
                "or Executor/SupportsAgentRun instances."
            )

        if isinstance(source, str) and all(isinstance(case.target, str) for case in cases):
            # Source is a name; defer resolution to build time
            self._edge_registry.append(_SwitchCaseEdgeGroupRegistration(source=source, cases=list(cases)))  # type: ignore
            return self

        # Source is an Executor/SupportsAgentRun instance; wrap and add now
        source_exec = self._maybe_wrap_agent(source)  # type: ignore[arg-type]
        source_id = self._add_executor(source_exec)
        # Convert case data types to internal types that only uses target_id.
        internal_cases: list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault] = []
        for case in cases:
            # Allow case targets to be agents
            case.target = self._maybe_wrap_agent(case.target)  # type: ignore[arg-type]
            self._add_executor(case.target)
            if isinstance(case, Default):
                internal_cases.append(SwitchCaseEdgeGroupDefault(target_id=case.target.id))
            else:
                internal_cases.append(SwitchCaseEdgeGroupCase(condition=case.condition, target_id=case.target.id))
        self._edge_groups.append(SwitchCaseEdgeGroup(source_id, internal_cases))  # type: ignore[call-arg]

        return self

    def add_multi_selection_edge_group(
        self,
        source: Executor | SupportsAgentRun | str,
        targets: Sequence[Executor | SupportsAgentRun | str],
        selection_func: Callable[[Any, list[str]], list[str]],
    ) -> Self:
        """Add an edge group that represents a multi-selection execution model.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source executor will be sent to multiple target executors based on
        the provided selection function.

        The selection function should take a message and a list of target executor IDs,
        and return a list of executor IDs indicating which target executors should receive the message.

        Args:
            source: The source executor or registered name of the source factory for the edge group.
            targets: A list of target executors or registered names of the target factories for the edges.
            selection_func: A function that selects target executors for messages.
                Takes (message, list[executor_id]) and returns list[executor_id].

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Note: If instances are provided for source and targets, they will be shared across
              all workflow instances created from the built Workflow. To avoid this, consider
              registering the executors and agents using `register_executors` and `register_agent`
              and referencing them by factory name for lazy initialization instead.

        Example:
            .. code-block:: python

                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
                from dataclasses import dataclass


                @dataclass
                class Task:
                    priority: str
                    data: str


                class TaskDispatcher(Executor):
                    @handler
                    async def dispatch(self, text: str, ctx: WorkflowContext[Task]) -> None:
                        priority = "high" if len(text) > 10 else "low"
                        await ctx.send_message(Task(priority=priority, data=text))


                class WorkerA(Executor):
                    @handler
                    async def process(self, task: Task, ctx: WorkflowContext) -> None:
                        print(f"WorkerA processing: {task.data}")


                class WorkerB(Executor):
                    @handler
                    async def process(self, task: Task, ctx: WorkflowContext) -> None:
                        print(f"WorkerB processing: {task.data}")


                # Select workers based on task priority
                def select_workers(task: Task, available: list[str]) -> list[str]:
                    if task.priority == "high":
                        return available  # Send to all workers
                    return [available[0]]  # Send to first worker only


                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "TaskDispatcher": lambda: TaskDispatcher(id="dispatcher"),
                        "WorkerA": lambda: WorkerA(id="worker_a"),
                        "WorkerB": lambda: WorkerB(id="worker_b"),
                    })
                    .add_multi_selection_edge_group(
                        "TaskDispatcher",
                        ["WorkerA", "WorkerB"],
                        selection_func=select_workers,
                    )
                    .set_start_executor("TaskDispatcher")
                    .build()
                )
        """
        if (isinstance(source, str) and not all(isinstance(t, str) for t in targets)) or (
            not isinstance(source, str) and any(isinstance(t, str) for t in targets)
        ):
            raise ValueError(
                "Both source and targets must be either registered factory names (str) or "
                "Executor/SupportsAgentRun instances."
            )

        if isinstance(source, str) and all(isinstance(t, str) for t in targets):
            # Both are names; defer resolution to build time
            self._edge_registry.append(
                _MultiSelectionEdgeGroupRegistration(
                    source=source,
                    targets=list(targets),  # type: ignore
                    selection_func=selection_func,
                )
            )
            return self

        # Both are Executor/SupportsAgentRun instances; wrap and add now
        source_exec = self._maybe_wrap_agent(source)  # type: ignore
        target_execs = [self._maybe_wrap_agent(t) for t in targets]  # type: ignore
        source_id = self._add_executor(source_exec)
        target_ids = [self._add_executor(t) for t in target_execs]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids, selection_func))  # type: ignore[call-arg]

        return self

    def add_fan_in_edges(
        self,
        sources: Sequence[Executor | SupportsAgentRun | str],
        target: Executor | SupportsAgentRun | str,
    ) -> Self:
        """Add multiple edges from sources to a single target executor.

        The edges will be grouped together for synchronized processing, meaning
        the target executor will only be executed once all source executors have completed.

        The target executor will receive a list of messages aggregated from all source executors.
        Thus the input types of the target executor must be compatible with a list of the output
        types of the source executors.

        Args:
            sources: A list of source executors or registered names of the source factories for the edges.
            target: The target executor or registered name of the target factory for the edges.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Note: If instances are provided for sources and target, they will be shared across
              all workflow instances created from the built Workflow. To avoid this, consider
              registering the executors and agents using `register_executors` and `register_agent`
              and referencing them by factory name for lazy initialization instead.

        Example:
            .. code-block:: python

                from typing_extensions import Never
                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


                class Producer(Executor):
                    @handler
                    async def produce(self, seed: int, ctx: WorkflowContext[str]) -> None:
                        await ctx.send_message(f"result_{seed}")


                class Aggregator(Executor):
                    @handler
                    async def aggregate(self, results: list[str], ctx: WorkflowContext[Never, str]) -> None:
                        combined = ", ".join(results)
                        await ctx.yield_output(f"Combined: {combined}")


                # Collect results from multiple producers
                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "Producer1": lambda: Producer(id="prod_1"),
                        "Producer2": lambda: Producer(id="prod_2"),
                        "Aggregator": lambda: Aggregator(id="agg"),
                    })
                    .add_fan_in_edges(["Producer1", "Producer2"], "Aggregator")
                    .set_start_executor("Producer1")
                    .build()
                )
        """
        if (all(isinstance(s, str) for s in sources) and not isinstance(target, str)) or (
            not all(isinstance(s, str) for s in sources) and isinstance(target, str)
        ):
            raise ValueError(
                "Both sources and target must be either registered factory names (str) or "
                "Executor/SupportsAgentRun instances."
            )

        if all(isinstance(s, str) for s in sources) and isinstance(target, str):
            # Both are names; defer resolution to build time
            self._edge_registry.append(_FanInEdgeRegistration(sources=list(sources), target=target))  # type: ignore
            return self

        # Both are Executor/SupportsAgentRun instances; wrap and add now
        source_execs = [self._maybe_wrap_agent(s) for s in sources]  # type: ignore
        target_exec = self._maybe_wrap_agent(target)  # type: ignore
        source_ids = [self._add_executor(s) for s in source_execs]
        target_id = self._add_executor(target_exec)
        self._edge_groups.append(FanInEdgeGroup(source_ids, target_id))  # type: ignore[call-arg]

        return self

    def add_chain(self, executors: Sequence[Executor | SupportsAgentRun | str]) -> Self:
        """Add a chain of executors to the workflow.

        The output of each executor in the chain will be sent to the next executor in the chain.
        The input types of each executor must be compatible with the output types of the previous executor.

        Cycles in the chain are not allowed, meaning an executor cannot appear more than once in the chain.

        Args:
            executors: A list of executors or registered names of the executor factories to chain together.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Note: If executor instances are provided, they will be shared across all workflow instances created
              from the built Workflow. To avoid this, consider registering the executors and agents using
              `register_executors` and `register_agent` and referencing them by factory name for lazy
              initialization instead.

        Example:
            .. code-block:: python

                from typing_extensions import Never
                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


                class Step1(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[str]) -> None:
                        await ctx.send_message(text.upper())


                class Step2(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[str]) -> None:
                        await ctx.send_message(text[::-1])


                class Step3(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
                        await ctx.yield_output(f"Final: {text}")


                # Chain executors in sequence
                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "step1": lambda: Step1(id="step1"),
                        "step2": lambda: Step2(id="step2"),
                        "step3": lambda: Step3(id="step3"),
                    })
                    .add_chain(["step1", "step2", "step3"])
                    .set_start_executor("step1")
                    .build()
                )
        """
        if len(executors) < 2:
            raise ValueError("At least two executors are required to form a chain.")

        if not all(isinstance(e, str) for e in executors) and any(isinstance(e, str) for e in executors):
            raise ValueError(
                "All executors in the chain must be either registered factory names (str) "
                "or Executor/SupportsAgentRun instances."
            )

        if all(isinstance(e, str) for e in executors):
            # All are names; defer resolution to build time
            for i in range(len(executors) - 1):
                self.add_edge(executors[i], executors[i + 1])
            return self

        # All are Executor/SupportsAgentRun instances; wrap and add now
        # Wrap each candidate first to ensure stable IDs before adding edges
        wrapped: list[Executor] = [self._maybe_wrap_agent(e) for e in executors]  # type: ignore[arg-type]
        for i in range(len(wrapped) - 1):
            self.add_edge(wrapped[i], wrapped[i + 1])
        return self

    def set_start_executor(self, executor: Executor | SupportsAgentRun | str) -> Self:
        """Set the starting executor for the workflow.

        The start executor is the entry point for the workflow. When the workflow is executed,
        the initial message will be sent to this executor.

        Args:
            executor: The starting executor, which can be an Executor instance, SupportsAgentRun instance,
                or the name of a registered executor factory.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Example:
            .. code-block:: python

                from typing_extensions import Never
                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


                class EntryPoint(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[str]) -> None:
                        await ctx.send_message(text.upper())


                class Processor(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
                        await ctx.yield_output(text)


                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "EntryPoint": lambda: EntryPoint(id="entry"),
                        "Processor": lambda: Processor(id="proc"),
                    })
                    .add_edge("EntryPoint", "Processor")
                    .set_start_executor("EntryPoint")
                    .build()
                )
        """
        if self._start_executor is not None:
            start_id = self._start_executor if isinstance(self._start_executor, str) else self._start_executor.id
            logger.warning(f"Overwriting existing start executor: {start_id} for the workflow.")

        if isinstance(executor, str):
            self._start_executor = executor
        else:
            wrapped = self._maybe_wrap_agent(executor)  # type: ignore[arg-type]
            self._start_executor = wrapped
            # Ensure the start executor is present in the executor map so validation succeeds
            # even if no edges are added yet, or before edges wrap the same agent again.
            existing = self._executors.get(wrapped.id)
            if existing is not wrapped:
                self._add_executor(wrapped)
        return self

    def set_max_iterations(self, max_iterations: int) -> Self:
        """Set the maximum number of iterations for the workflow.

        When a workflow contains cycles, this limit prevents infinite loops by capping
        the total number of executor invocations. The default is 100 iterations.

        Args:
            max_iterations: The maximum number of iterations the workflow will run for convergence.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Example:
            .. code-block:: python

                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


                class StepA(Executor):
                    @handler
                    async def process(self, count: int, ctx: WorkflowContext[int]) -> None:
                        if count < 10:
                            await ctx.send_message(count + 1)


                class StepB(Executor):
                    @handler
                    async def process(self, count: int, ctx: WorkflowContext[int]) -> None:
                        await ctx.send_message(count)


                # Set a custom iteration limit for workflow with cycles
                workflow = (
                    WorkflowBuilder()
                    .set_max_iterations(500)
                    .register_executors({
                        "StepA": lambda: StepA(id="step_a"),
                        "StepB": lambda: StepB(id="step_b"),
                    })
                    .add_edge("StepA", "StepB")
                    .add_edge("StepB", "StepA")  # Cycle
                    .set_start_executor("StepA")
                    .build()
                )
        """
        self._max_iterations = max_iterations
        return self

    # Removed explicit set_agent_streaming() API; agents always stream updates.

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> Self:
        """Enable checkpointing with the specified storage.

        Checkpointing allows workflows to save their state periodically, enabling
        pause/resume functionality and recovery from failures. The checkpoint storage
        implementation determines where checkpoints are persisted.

        Args:
            checkpoint_storage: The checkpoint storage implementation to use.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Example:
            .. code-block:: python

                from typing_extensions import Never
                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
                from agent_framework import FileCheckpointStorage


                class ProcessorA(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[str]) -> None:
                        await ctx.send_message(text.upper())


                class ProcessorB(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
                        await ctx.yield_output(text)


                # Enable checkpointing with file-based storage
                storage = FileCheckpointStorage("./checkpoints")
                workflow = (
                    WorkflowBuilder()
                    .register_executors({
                        "ProcessorA": lambda: ProcessorA(id="proc_a"),
                        "ProcessorB": lambda: ProcessorB(id="proc_b"),
                    })
                    .add_edge("ProcessorA", "ProcessorB")
                    .set_start_executor("ProcessorA")
                    .with_checkpointing(storage)
                    .build()
                )

                # Run with checkpoint saving
                events = await workflow.run("input")
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_output_from(self, executors: list[Executor | SupportsAgentRun | str]) -> Self:
        """Specify which executors' outputs should be collected as workflow outputs.

        By default, outputs from all executors are collected. This method allows
        filtering to only include outputs from specified executors.

        Args:
            executors: A list of executors or registered names of the executor factories
                       whose outputs should be collected.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.
        """
        self._output_executors = list(executors)
        return self

    def _resolve_edge_registrations(self, factory_name_to_instance: dict[str, Executor]) -> list[EdgeGroup]:
        """Process edge registrations into edge groups using resolved executor instances.

        Args:
            factory_name_to_instance: Mapping of registered factory names to executor instances.

        Returns:
            list[EdgeGroup]: A list of EdgeGroup instances for the registered edges.
        """

        def _get_executor(name: str) -> Executor:
            """Helper to get executor by the registered name.

            Args:
                name: The registered name of the executor to get.

            Returns:
                Executor: The Executor instance.

            Raises:
                ValueError: If the executor is not found.
            """
            if name not in factory_name_to_instance:
                raise ValueError(f"Factory '{name}' has not been registered.")
            return factory_name_to_instance[name]

        edge_groups: list[EdgeGroup] = []
        for registration in self._edge_registry:
            match registration:
                case _EdgeRegistration(source, target, condition):
                    source_exec: Executor = _get_executor(source)
                    target_exec: Executor = _get_executor(target)
                    edge_groups.append(SingleEdgeGroup(source_exec.id, target_exec.id, condition))  # type: ignore[call-arg]
                case _FanOutEdgeRegistration(source, targets):
                    source_exec = _get_executor(source)
                    target_execs = [_get_executor(t) for t in targets]
                    edge_groups.append(FanOutEdgeGroup(source_exec.id, [t.id for t in target_execs]))  # type: ignore[call-arg]
                case _SwitchCaseEdgeGroupRegistration(source, cases):
                    source_exec = _get_executor(source)
                    cases_converted: list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault] = []
                    for case in cases:
                        if not isinstance(case.target, str):
                            raise ValueError("Switch case target must be a registered factory name (str) if deferred.")
                        target_exec = _get_executor(case.target)
                        if isinstance(case, Default):
                            cases_converted.append(SwitchCaseEdgeGroupDefault(target_id=target_exec.id))
                        else:
                            cases_converted.append(
                                SwitchCaseEdgeGroupCase(condition=case.condition, target_id=target_exec.id)
                            )
                    edge_groups.append(SwitchCaseEdgeGroup(source_exec.id, cases_converted))  # type: ignore[call-arg]
                case _MultiSelectionEdgeGroupRegistration(source, targets, selection_func):
                    source_exec = _get_executor(source)
                    target_execs = [_get_executor(t) for t in targets]
                    edge_groups.append(
                        FanOutEdgeGroup(source_exec.id, [t.id for t in target_execs], selection_func)  # type: ignore[call-arg]
                    )
                case _FanInEdgeRegistration(sources, target):
                    source_execs = [_get_executor(s) for s in sources]
                    target_exec = _get_executor(target)
                    edge_groups.append(FanInEdgeGroup([s.id for s in source_execs], target_exec.id))  # type: ignore[call-arg]
        return edge_groups

    def _process_instantiated_executors(
        self,
        factory_name_to_instance: dict[str, Executor],
    ) -> tuple[Executor, dict[str, Executor], list[EdgeGroup]]:
        """Process instantiated executors: validate IDs, create edge groups, resolve edges.

        Args:
            factory_name_to_instance: Mapping of factory names to already-instantiated executors.

        Returns:
            tuple: A tuple containing:
                - The starting Executor instance.
                - The factory_name_to_instance mapping.
                - A list of EdgeGroup instances representing the workflow edges.

        Raises:
            ValueError: If start executor is not set, if duplicate executor IDs are found,
                or if start executor cannot be resolved.
        """
        if not self._start_executor:
            raise ValueError("Starting executor must be set using set_start_executor before building the workflow.")

        start_executor: Executor | None = None
        if isinstance(self._start_executor, Executor):
            start_executor = self._start_executor

        deferred_edge_groups: list[EdgeGroup] = []
        # Map of executor IDs to their factory names for error message clarity
        executor_id_to_factory_name: dict[str, str] = {}

        for name, instance in factory_name_to_instance.items():
            if instance.id in executor_id_to_factory_name:
                existing_factory = executor_id_to_factory_name[instance.id]
                raise ValueError(
                    f"Executor with ID '{instance.id}' from factory '{name}' "
                    f"conflicts with existing factory '{existing_factory}'."
                )
            if instance.id in self._executors:
                raise ValueError(f"Executor with ID '{instance.id}' has already been added to the workflow.")
            executor_id_to_factory_name[instance.id] = name

            if isinstance(self._start_executor, str) and name == self._start_executor:
                start_executor = instance

            # All executors will get their own internal edge group for receiving system messages
            deferred_edge_groups.append(InternalEdgeGroup(instance.id))  # type: ignore[call-arg]

        # Process edge registrations using shared helper
        deferred_edge_groups.extend(self._resolve_edge_registrations(factory_name_to_instance))

        if start_executor is None:
            raise ValueError("Failed to resolve starting executor from registered factories.")

        return (start_executor, factory_name_to_instance, deferred_edge_groups)

    def _resolve_edge_registry(self) -> tuple[Executor, dict[str, Executor], list[EdgeGroup]]:
        """Resolve deferred edge registrations into executors and edge groups.

        Factory functions are called synchronously to instantiate executors. If any factory
        returns an awaitable, an error is raised directing the caller to use :meth:`build_async`
        instead.

        Returns:
            tuple: A tuple containing:
                - The starting Executor instance.
                - A dictionary mapping registered factory names to resolved Executor instances.
                - A list of EdgeGroup instances representing the workflow edges composed of resolved executors.

        Raises:
            ValueError: If an async executor factory is detected.

        Notes:
            Non-factory executors (i.e., those added directly) are not included in the returned list,
            as they are already part of the workflow builder's internal state.
        """
        factory_name_to_instance: dict[str, Executor] = {}
        for name, executor_factory in self._executor_registry.items():
            instance = executor_factory()
            if inspect.isawaitable(instance):
                # Close un-awaited coroutines to avoid runtime warnings or memory leaks
                try:
                    if hasattr(instance, "close"):
                        instance.close()  # type: ignore[reportGeneralTypeIssues]
                finally:
                    raise ValueError("Async executor factories were detected. Use build_async() instead.")

            if not isinstance(instance, Executor):
                raise TypeError(f"Factory '{name}' returned {type(instance).__name__} instead of an Executor.")

            factory_name_to_instance[name] = instance

        return self._process_instantiated_executors(factory_name_to_instance)

    async def _resolve_edge_registry_async(self) -> tuple[Executor, dict[str, Executor], list[EdgeGroup]]:
        """Resolve deferred edge registrations with support for async executor factories.

        This async variant of :meth:`_resolve_edge_registry` allows executor factories to
        return awaitables. Factory functions are called and any awaitable results are awaited
        before processing. All other logic (validation, edge resolution) is identical to the
        sync version.

        Returns:
            tuple: A tuple containing:
                - The starting Executor instance.
                - A dictionary mapping registered factory names to resolved Executor instances.
                - A list of EdgeGroup instances representing the workflow edges composed of resolved executors.

        Notes:
            Non-factory executors (i.e., those added directly) are not included in the returned list,
            as they are already part of the workflow builder's internal state.

        See Also:
            :meth:`_resolve_edge_registry`: Synchronous version that raises an error on async factories.
        """
        factory_name_to_instance: dict[str, Executor] = {}
        for name, executor_factory in self._executor_registry.items():
            instance = executor_factory()
            if inspect.isawaitable(instance):
                # Handle maybe awaitable executor instances
                instance = await instance

            if not isinstance(instance, Executor):
                raise TypeError(f"Factory '{name}' returned {type(instance).__name__} instead of an Executor.")

            factory_name_to_instance[name] = instance

        return self._process_instantiated_executors(factory_name_to_instance)

    def _create_workflow_from_resolved_registry(
        self,
        span: trace.Span,
        start_executor: Executor,
        deferred_executors: dict[str, Executor],
        deferred_edge_groups: list[EdgeGroup],
    ) -> Workflow:
        """Create and validate a Workflow instance from resolved executor registry data.

        This is a shared helper used by both :meth:`build` and :meth:`build_async` to avoid
        code duplication in the workflow creation and validation logic.

        Args:
            span: The OpenTelemetry span for tracking the build process.
            start_executor: The resolved starting executor instance.
            deferred_executors: Mapping of factory names to instantiated executors.
            deferred_edge_groups: List of edge groups from resolved registrations.

        Returns:
            Workflow: A fully constructed and validated Workflow instance.

        Raises:
            WorkflowValidationError: If workflow validation fails.
        """
        executors = self._executors | {exe.id: exe for exe in deferred_executors.values()}
        edge_groups = self._edge_groups + deferred_edge_groups
        output_executors = (
            [
                deferred_executors[factory_name].id
                for factory_name in self._output_executors
                if isinstance(factory_name, str)
            ]
            + [ex.id for ex in self._output_executors if isinstance(ex, Executor)]
            + [resolve_agent_id(agent) for agent in self._output_executors if isinstance(agent, SupportsAgentRun)]
        )

        # Perform validation before creating the workflow
        validate_workflow_graph(
            edge_groups,
            executors,
            start_executor,
            output_executors,
        )

        # Add validation completed event
        span.add_event(OtelAttr.BUILD_VALIDATION_COMPLETED)

        context = InProcRunnerContext(self._checkpoint_storage)

        # Create workflow instance after validation
        workflow = Workflow(
            edge_groups,
            executors,
            start_executor,
            context,
            self._max_iterations,
            name=self._name,
            description=self._description,
            output_executors=output_executors,
        )
        build_attributes: dict[str, Any] = {
            OtelAttr.WORKFLOW_ID: workflow.id,
            OtelAttr.WORKFLOW_DEFINITION: workflow.to_json(),
        }
        if workflow.name:
            build_attributes[OtelAttr.WORKFLOW_NAME] = workflow.name
        if workflow.description:
            build_attributes[OtelAttr.WORKFLOW_DESCRIPTION] = workflow.description
        span.set_attributes(build_attributes)

        # Add workflow build completed event
        span.add_event(OtelAttr.BUILD_COMPLETED)

        return workflow

    def build(self) -> Workflow:
        """Build and return the constructed workflow.

        This method performs validation before building the workflow to ensure:
        - A starting executor has been set
        - All edges connect valid executors
        - The graph is properly connected
        - Type compatibility between connected executors

        Returns:
            Workflow: An immutable Workflow instance ready for execution.

        Raises:
            ValueError: If starting executor is not set.
            WorkflowValidationError: If workflow validation fails (includes EdgeDuplicationError,
                TypeCompatibilityError, and GraphConnectivityError subclasses).

        Example:
            .. code-block:: python

                from typing_extensions import Never
                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


                class MyExecutor(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
                        await ctx.yield_output(text.upper())


                # Build and execute a workflow
                workflow = (
                    WorkflowBuilder()
                    .register_executors({"MyExecutor": lambda: MyExecutor(id="executor")})
                    .set_start_executor("MyExecutor")
                    .build()
                )

                # The workflow is now immutable and ready to run
                events = await workflow.run("hello")
                print(events.get_outputs())  # ['HELLO']

                # Workflows can be reused multiple times
                events2 = await workflow.run("world")
                print(events2.get_outputs())  # ['WORLD']
        """
        # Create workflow build span that includes validation and workflow creation
        with create_workflow_span(OtelAttr.WORKFLOW_BUILD_SPAN) as span:
            try:
                # Add workflow build started event
                span.add_event(OtelAttr.BUILD_STARTED)

                # Resolve lazy edge registrations
                start_executor, deferred_executors, deferred_edge_groups = self._resolve_edge_registry()

                # Create and validate workflow
                return self._create_workflow_from_resolved_registry(
                    span, start_executor, deferred_executors, deferred_edge_groups
                )
            except Exception as exc:
                attributes = {
                    OtelAttr.BUILD_ERROR_MESSAGE: str(exc),
                    OtelAttr.BUILD_ERROR_TYPE: type(exc).__name__,
                }
                span.add_event(OtelAttr.BUILD_ERROR, attributes)  # type: ignore[reportArgumentType, arg-type]
                capture_exception(span, exc)
                raise

    async def build_async(self) -> Workflow:
        """Build and return the constructed workflow with async executor factory support.

        This async version of :meth:`build` supports executor factories that return
        awaitables (coroutines). Use this method when any of your registered executor
        factories are async functions.

        This method performs validation before building the workflow to ensure:
        - A starting executor has been set
        - All edges connect valid executors
        - The graph is properly connected
        - Type compatibility between connected executors

        Returns:
            Workflow: An immutable Workflow instance ready for execution.

        Raises:
            ValueError: If starting executor is not set.
            WorkflowValidationError: If workflow validation fails (includes EdgeDuplicationError,
                TypeCompatibilityError, and GraphConnectivityError subclasses).

        Example:
            .. code-block:: python

                from typing_extensions import Never
                from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


                class MyExecutor(Executor):
                    @handler
                    async def process(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
                        await ctx.yield_output(text.upper())


                async def create_executor() -> MyExecutor:
                    # Async initialization (e.g., fetching config, establishing connections)
                    return MyExecutor(id="executor")


                # Build with async executor factories
                workflow = await (
                    WorkflowBuilder()
                    .register_executors({"MyExecutor": create_executor})
                    .set_start_executor("MyExecutor")
                    .build_async()
                )

                # The workflow is now immutable and ready to run
                events = await workflow.run("hello")
                print(events.get_outputs())  # ['HELLO']
        """
        # Create workflow build span that includes validation and workflow creation
        with create_workflow_span(OtelAttr.WORKFLOW_BUILD_SPAN) as span:
            try:
                # Add workflow build started event
                span.add_event(OtelAttr.BUILD_STARTED)

                # Resolve lazy edge registrations with support for async executor factories
                start_executor, deferred_executors, deferred_edge_groups = await self._resolve_edge_registry_async()

                # Create and validate workflow
                return self._create_workflow_from_resolved_registry(
                    span, start_executor, deferred_executors, deferred_edge_groups
                )
            except Exception as exc:
                attributes = {
                    OtelAttr.BUILD_ERROR_MESSAGE: str(exc),
                    OtelAttr.BUILD_ERROR_TYPE: type(exc).__name__,
                }
                span.add_event(OtelAttr.BUILD_ERROR, attributes)  # type: ignore[reportArgumentType, arg-type]
                capture_exception(span, exc)
                raise
