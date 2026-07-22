# Copyright (c) Microsoft. All rights reserved.

import logging
import sys
import uuid
import warnings
from collections.abc import Callable, Sequence
from typing import Any, Literal

from .._agents import SupportsAgentRun
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
from ._validation import ValidationTypeEnum, WorkflowValidationError, validate_workflow_graph
from ._workflow import (
    _MISSING,  # pyright: ignore[reportPrivateUsage]
    Workflow,
    _coalesce_output_from_kwarg,  # pyright: ignore[reportPrivateUsage]
)

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


logger = logging.getLogger(__name__)

_ALL_OUTPUTS: Literal["all"] = "all"
_ALL_OTHER_OUTPUTS: Literal["all_other"] = "all_other"
_OutputSelection = list[Executor | SupportsAgentRun] | Literal["all"] | None
_IntermediateOutputSelection = list[Executor | SupportsAgentRun] | Literal["all", "all_other"] | None
_AnyOutputSelection = _OutputSelection | _IntermediateOutputSelection


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


            upper = UpperCaseExecutor(id="upper")
            reverse = ReverseExecutor(id="reverse")

            workflow = WorkflowBuilder(start_executor=upper).add_edge(upper, reverse).build()

            # Run the workflow
            events = await workflow.run("hello")
            print(events.get_outputs())  # ['OLLEH']
    """

    def __init__(
        self,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        name: str | None = None,
        description: str | None = None,
        *,
        start_executor: Executor | SupportsAgentRun,
        checkpoint_storage: CheckpointStorage | None = None,
        output_from: list[Executor | SupportsAgentRun] | Literal["all"] | None = _MISSING,
        intermediate_output_from: _IntermediateOutputSelection = _MISSING,
        output_executors: list[Executor | SupportsAgentRun] | None = _MISSING,
    ):
        """Initialize the WorkflowBuilder.

        Args:
            max_iterations: Maximum number of iterations for workflow convergence. Default is 100.
            name: A human-readable name for the workflow builder. This name will be the identifier
                for all workflow instances created from this builder. If not provided, a unique name
                will be generated. This will be useful for versioning, monitoring, checkpointing, and
                debugging workflows. Keeping this name unique across versions of your workflow definitions
                is recommended for better observability and management.
            description: Optional description of what the workflow does.
            start_executor: The starting executor for the workflow. Can be an Executor instance
                or SupportsAgentRun instance.
            checkpoint_storage: Optional checkpoint storage for enabling workflow state persistence.
            output_from: Designates which executors emit workflow output
                (``type='output'`` workflow events). Pass ``"all"`` to explicitly select every
                executor with declared workflow output types.
            intermediate_output_from: Designates which executors emit intermediate output
                (``type='intermediate'`` workflow events). Pass ``"all"`` to select every executor
                with declared workflow output types as intermediate (no executor emits ``output``).
                Pass ``"all_other"`` to select every executor with declared workflow output types
                that is not selected by ``output_from``.
                If neither ``output_from`` nor ``intermediate_output_from`` is provided,
                omitted-selection compatibility behavior applies and every ``yield_output`` produces
                ``type='output'``. If either is provided, explicit mode applies: listed
                workflow-output executors emit ``output``, listed intermediate executors emit
                ``intermediate``, and unlisted executor yields are hidden.

                Output selection behavior:
                - Omit both selections: every ``yield_output`` emits ``output`` for compatibility,
                  with a deprecation warning.
                - ``output_from="all"``: every output-capable executor emits ``output``.
                - ``output_from=[A]``: only A emits ``output``; other executor payloads are hidden.
                - ``output_from=[A], intermediate_output_from="all_other"``: A emits ``output``;
                  all other output-capable executors emit ``intermediate``.
                - ``intermediate_output_from="all_other"``: no executor emits ``output``; every
                  output-capable executor emits ``intermediate``.
                - ``output_from=[], intermediate_output_from="all_other"``: no executor emits
                  ``output``; every output-capable executor emits ``intermediate``.
                - ``output_from=[A], intermediate_output_from=[B, C]``: A emits ``output``; B and C
                  emit ``intermediate``; other executor payloads are hidden.
            output_executors: **Deprecated** alias for ``output_from``. Will be removed in a
                future version.
        """
        output_from = _coalesce_output_from_kwarg(output_from, output_executors)
        if intermediate_output_from is _MISSING:
            intermediate_output_from = None
        self._edge_groups: list[EdgeGroup] = []
        self._executors: dict[str, Executor] = {}
        self._start_executor: Executor | None = None
        self._checkpoint_storage: CheckpointStorage | None = checkpoint_storage
        self._max_iterations: int = max_iterations
        self._name: str = name or f"WorkflowBuilder-{uuid.uuid4()!s}"
        self._description: str | None = description
        # Maps underlying SupportsAgentRun object id -> wrapped Executor so we reuse the same wrapper
        # across start_executor / add_edge calls. This avoids multiple AgentExecutor instances
        # being created for the same agent.
        self._agent_wrappers: dict[str, Executor] = {}

        # ``None`` for both means omitted-selection compatibility behavior
        # (every yield_output produces type='output').
        # If either is provided, explicit mode applies and unlisted executor yields are hidden.
        self._output_from: _OutputSelection = self._coerce_output_from(output_from)
        self._intermediate_output_from: _IntermediateOutputSelection = self._coerce_intermediate_output_from(
            intermediate_output_from
        )

        # Set the start executor
        self._set_start_executor(start_executor)

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
        self._edge_groups.append(InternalEdgeGroup(executor.id))

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
            from agent_framework import SupportsAgentRun
        except Exception:  # pragma: no cover - defensive
            SupportsAgentRun = object

        if isinstance(candidate, Executor):  # Already an executor
            return candidate
        if isinstance(candidate, SupportsAgentRun):
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

    def add_edge(
        self,
        source: Executor | SupportsAgentRun,
        target: Executor | SupportsAgentRun,
        condition: EdgeCondition | None = None,
    ) -> Self:
        """Add a directed edge between two executors.

        The output types of the source and the input types of the target must be compatible.
        Messages sent by the source executor will be routed to the target executor.

        Args:
            source: The source executor or agent for the edge.
            target: The target executor or agent for the edge.
            condition: An optional condition function `(data) -> bool | Awaitable[bool]`
                       that determines whether the edge should be traversed.
                       Example: `lambda data: data["ready"]`.

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


                a = ProcessorA(id="a")
                b = ProcessorB(id="b")

                workflow = WorkflowBuilder(start_executor=a).add_edge(a, b).build()
        """
        source_exec = self._maybe_wrap_agent(source)
        target_exec = self._maybe_wrap_agent(target)
        source_id = self._add_executor(source_exec)
        target_id = self._add_executor(target_exec)
        self._edge_groups.append(SingleEdgeGroup(source_id, target_id, condition))
        return self

    def add_fan_out_edges(
        self,
        source: Executor | SupportsAgentRun,
        targets: Sequence[Executor | SupportsAgentRun],
    ) -> Self:
        """Add multiple edges to the workflow where messages from the source will be sent to all targets.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source will be broadcast to all target executors concurrently.

        Args:
            source: The source executor or agent for the edges.
            targets: A list of target executors or agents for the edges.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

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


                source = DataSource(id="source")
                val_a = ValidatorA(id="val_a")
                val_b = ValidatorB(id="val_b")

                workflow = WorkflowBuilder(start_executor=source).add_fan_out_edges(source, [val_a, val_b]).build()
        """
        source_exec = self._maybe_wrap_agent(source)
        target_execs = [self._maybe_wrap_agent(t) for t in targets]
        source_id = self._add_executor(source_exec)
        target_ids = [self._add_executor(t) for t in target_execs]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids))

        return self

    def add_switch_case_edge_group(
        self,
        source: Executor | SupportsAgentRun,
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
            source: The source executor or agent for the edge group.
            cases: A list of case objects that determine the target executor for each message.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

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


                evaluator = Evaluator(id="eval")
                high = HighScoreHandler(id="high")
                low = LowScoreHandler(id="low")

                workflow = (
                    WorkflowBuilder(start_executor=evaluator)
                    .add_switch_case_edge_group(
                        evaluator,
                        [
                            Case(condition=lambda r: r.score > 10, target=high),
                            Default(target=low),
                        ],
                    )
                    .build()
                )
        """
        source_exec = self._maybe_wrap_agent(source)
        source_id = self._add_executor(source_exec)
        # Convert case data types to internal types that only uses target_id.
        internal_cases: list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault] = []
        for case in cases:
            # Allow case targets to be agents
            case.target = self._maybe_wrap_agent(case.target)
            self._add_executor(case.target)
            if isinstance(case, Default):
                internal_cases.append(SwitchCaseEdgeGroupDefault(target_id=case.target.id))
            else:
                internal_cases.append(SwitchCaseEdgeGroupCase(condition=case.condition, target_id=case.target.id))
        self._edge_groups.append(SwitchCaseEdgeGroup(source_id, internal_cases))

        return self

    def add_multi_selection_edge_group(
        self,
        source: Executor | SupportsAgentRun,
        targets: Sequence[Executor | SupportsAgentRun],
        selection_func: Callable[[Any, list[str]], list[str]],
    ) -> Self:
        """Add an edge group that represents a multi-selection execution model.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source executor will be sent to multiple target executors based on
        the provided selection function.

        The selection function should take a message and a list of target executor IDs,
        and return a list of executor IDs indicating which target executors should receive the message.

        Args:
            source: The source executor or agent for the edge group.
            targets: A list of target executors or agents for the edges.
            selection_func: A function that selects target executors for messages.
                Takes (message, list[executor_id]) and returns list[executor_id].

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

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


                dispatcher = TaskDispatcher(id="dispatcher")
                worker_a = WorkerA(id="worker_a")
                worker_b = WorkerB(id="worker_b")


                # Select workers based on task priority
                def select_workers(task: Task, available: list[str]) -> list[str]:
                    if task.priority == "high":
                        return available  # Send to all workers
                    return [available[0]]  # Send to first worker only


                workflow = (
                    WorkflowBuilder(start_executor=dispatcher)
                    .add_multi_selection_edge_group(
                        dispatcher,
                        [worker_a, worker_b],
                        selection_func=select_workers,
                    )
                    .build()
                )
        """
        source_exec = self._maybe_wrap_agent(source)
        target_execs = [self._maybe_wrap_agent(t) for t in targets]
        source_id = self._add_executor(source_exec)
        target_ids = [self._add_executor(t) for t in target_execs]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids, selection_func))

        return self

    def add_fan_in_edges(
        self,
        sources: Sequence[Executor | SupportsAgentRun],
        target: Executor | SupportsAgentRun,
    ) -> Self:
        """Add multiple edges from sources to a single target executor.

        The edges will be grouped together for synchronized processing, meaning
        the target executor will only be executed once all source executors have completed.

        The target executor will receive a list of messages aggregated from all source executors.
        Thus the input types of the target executor must be compatible with a list of the output
        types of the source executors.

        Args:
            sources: A list of source executors or agents for the edges.
            target: The target executor or agent for the edges.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

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


                prod_1 = Producer(id="prod_1")
                prod_2 = Producer(id="prod_2")
                agg = Aggregator(id="agg")

                workflow = WorkflowBuilder(start_executor=prod_1).add_fan_in_edges([prod_1, prod_2], agg).build()
        """
        source_execs = [self._maybe_wrap_agent(s) for s in sources]
        target_exec = self._maybe_wrap_agent(target)
        source_ids = [self._add_executor(s) for s in source_execs]
        target_id = self._add_executor(target_exec)
        self._edge_groups.append(FanInEdgeGroup(source_ids, target_id))

        return self

    def add_chain(self, executors: Sequence[Executor | SupportsAgentRun]) -> Self:
        """Add a chain of executors to the workflow.

        The output of each executor in the chain will be sent to the next executor in the chain.
        The input types of each executor must be compatible with the output types of the previous executor.

        Cycles in the chain are not allowed, meaning an executor cannot appear more than once in the chain.

        Args:
            executors: A list of executors or agents to chain together.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

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


                step1 = Step1(id="step1")
                step2 = Step2(id="step2")
                step3 = Step3(id="step3")

                workflow = WorkflowBuilder(start_executor=step1).add_chain([step1, step2, step3]).build()
        """
        if len(executors) < 2:
            raise ValueError("At least two executors are required to form a chain.")

        # Wrap each candidate first to ensure stable IDs before adding edges
        wrapped: list[Executor] = [self._maybe_wrap_agent(e) for e in executors]
        for i in range(len(wrapped) - 1):
            self.add_edge(wrapped[i], wrapped[i + 1])
        return self

    def _set_start_executor(self, executor: Executor | SupportsAgentRun) -> None:
        """Set the starting executor for the workflow (internal method).

        Args:
            executor: The starting executor, which can be an Executor instance or SupportsAgentRun instance.
        """
        if self._start_executor is not None:
            logger.warning(f"Overwriting existing start executor: {self._start_executor.id} for the workflow.")

        wrapped = self._maybe_wrap_agent(executor)
        self._start_executor = wrapped
        # Ensure the start executor is present in the executor map so validation succeeds
        # even if no edges are added yet, or before edges wrap the same agent again.
        existing = self._executors.get(wrapped.id)
        if existing is not wrapped:
            self._add_executor(wrapped)

    def _coerce_output_from(self, output_from: Any) -> _OutputSelection:
        """Coerce workflow-output selection while preserving the explicit ``"all"`` literal."""
        if output_from is None:
            return None
        if output_from == _ALL_OUTPUTS:
            return _ALL_OUTPUTS
        if isinstance(output_from, str):
            raise ValueError(f"Unsupported output_from literal {output_from!r}; use 'all' or a list of executors.")
        return list(output_from)

    def _coerce_intermediate_output_from(self, intermediate_output_from: Any) -> _IntermediateOutputSelection:
        """Coerce intermediate-output selection and reject output-only literals."""
        if intermediate_output_from is None:
            return None
        if isinstance(intermediate_output_from, str):
            if intermediate_output_from == _ALL_OUTPUTS:
                return _ALL_OUTPUTS
            if intermediate_output_from == _ALL_OTHER_OUTPUTS:
                return _ALL_OTHER_OUTPUTS
            raise ValueError(
                f"Unsupported intermediate_output_from literal {intermediate_output_from!r}; "
                "use 'all', 'all_other', or a list of executors."
            )
        return list(intermediate_output_from)

    def _resolve_designated_executor_ids(
        self,
        designated: _AnyOutputSelection,
    ) -> list[str] | None:
        """Resolve an optional designation list into executor IDs without mutating the graph."""
        if designated is None:
            return None
        if designated == _ALL_OUTPUTS:
            return [executor_id for executor_id, executor in self._executors.items() if executor.workflow_output_types]
        if designated == _ALL_OTHER_OUTPUTS:
            raise ValueError("intermediate_output_from='all_other' must be expanded relative to output_from.")
        ids: list[str] = []
        for item in designated:
            if isinstance(item, Executor):
                ids.append(item.id)
            elif isinstance(item, SupportsAgentRun):
                ids.append(resolve_agent_id(item))
            else:
                raise TypeError(
                    "WorkflowBuilder expected designation entries to be Executor or SupportsAgentRun instances; "
                    f"got {type(item).__name__}."
                )
        return ids

    def _validate_designation_lists(
        self,
        output_executor_ids: list[str] | None,
        intermediate_executor_ids: list[str] | None,
    ) -> None:
        """Validate builder-level designation rules that need omitted-vs-explicit context."""
        explicit_mode = output_executor_ids is not None or intermediate_executor_ids is not None
        if not explicit_mode:
            return

        output_ids = output_executor_ids or []
        intermediate_ids = intermediate_executor_ids or []
        if not output_ids and not intermediate_ids:
            raise WorkflowValidationError(
                "Explicit workflow output designation must include at least one output or intermediate executor.",
                validation_type=ValidationTypeEnum.OUTPUT_VALIDATION,
            )

        duplicate_outputs = sorted({executor_id for executor_id in output_ids if output_ids.count(executor_id) > 1})
        if duplicate_outputs:
            raise WorkflowValidationError(
                f"Duplicate output executor designation(s): {duplicate_outputs}",
                validation_type=ValidationTypeEnum.OUTPUT_VALIDATION,
            )

        duplicate_intermediates = sorted({
            executor_id for executor_id in intermediate_ids if intermediate_ids.count(executor_id) > 1
        })
        if duplicate_intermediates:
            raise WorkflowValidationError(
                f"Duplicate intermediate executor designation(s): {duplicate_intermediates}",
                validation_type=ValidationTypeEnum.OUTPUT_VALIDATION,
            )

        overlap = sorted(set(output_ids).intersection(intermediate_ids))
        if overlap:
            raise WorkflowValidationError(
                f"Executors cannot be both output and intermediate designated: {overlap}",
                validation_type=ValidationTypeEnum.OUTPUT_VALIDATION,
            )

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


                executor = MyExecutor(id="executor")

                workflow = WorkflowBuilder(start_executor=executor).build()

                # The workflow is now immutable and ready to run
                events = await workflow.run("hello")
                print(events.get_outputs())  # ['HELLO']

                # Workflows can be reused multiple times
                events2 = await workflow.run("world")
                print(events2.get_outputs())  # ['WORLD']

                # Select one executor as Workflow Output.
                workflow = WorkflowBuilder(start_executor=executor, output_from=[executor]).build()
                events = await workflow.run("hello")
                print(events.get_outputs())  # ['HELLO']
                print(events.get_intermediate_outputs())  # []

                # Make one executor Workflow Output and every other output-capable executor Intermediate Output.
                workflow = (
                    WorkflowBuilder(
                        start_executor=planner,
                        output_from=[answerer],
                        intermediate_output_from="all_other",
                    )
                    .add_edge(planner, answerer)
                    .build()
                )
                events = await workflow.run("hello")
                print(events.get_outputs())  # outputs from answerer
                print(events.get_intermediate_outputs())  # outputs from planner

                # Build a progress-only workflow: no Workflow Output, all output-capable executors are intermediate.
                workflow = (
                    WorkflowBuilder(start_executor=planner, intermediate_output_from="all_other")
                    .add_edge(planner, answerer)
                    .build()
                )
                events = await workflow.run("hello")
                print(events.get_outputs())  # []
                print(events.get_intermediate_outputs())  # outputs from planner and answerer

                # Explicitly preserve all-output behavior without relying on omitted-selection compatibility.
                workflow = (
                    WorkflowBuilder(start_executor=planner, output_from="all").add_edge(planner, answerer).build()
                )
                events = await workflow.run("hello")
                print(events.get_outputs())  # outputs from planner and answerer
        """
        # Create workflow build span that includes validation and workflow creation
        with create_workflow_span(OtelAttr.WORKFLOW_BUILD_SPAN) as span:
            try:
                # Add workflow build started event
                span.add_event(OtelAttr.BUILD_STARTED)

                if not self._start_executor:
                    raise ValueError(
                        "Starting executor must be set via the start_executor constructor parameter before building."
                    )

                if self._output_from is None and self._intermediate_output_from is None:
                    warnings.warn(
                        "WorkflowBuilder built without explicit output_from or intermediate_output_from; "
                        "every yield_output produces type='output' for compatibility. Pass output_from='all', "
                        "output_from=[...], or intermediate_output_from=[...] to opt into explicit designation - "
                        "explicit designation will be required in a future version.",
                        DeprecationWarning,
                        stacklevel=2,
                    )

                start_executor = self._start_executor
                executors = self._executors
                edge_groups = self._edge_groups
                output_ids = self._resolve_designated_executor_ids(self._output_from)
                intermediate_output_ids: list[str] | None
                if self._intermediate_output_from == _ALL_OTHER_OUTPUTS:
                    output_ids_for_all_other = output_ids or []
                    intermediate_output_ids = [
                        executor_id
                        for executor_id, executor in self._executors.items()
                        if executor.workflow_output_types and executor_id not in output_ids_for_all_other
                    ]
                else:
                    intermediate_output_ids = self._resolve_designated_executor_ids(self._intermediate_output_from)
                self._validate_designation_lists(output_ids, intermediate_output_ids)

                explicit_mode = output_ids is not None or intermediate_output_ids is not None
                output_for_workflow: list[str] | None = output_ids if explicit_mode else None
                if explicit_mode and output_for_workflow is None:
                    output_for_workflow = []
                intermediate_output_for_workflow: list[str] | None = intermediate_output_ids if explicit_mode else None
                if explicit_mode and intermediate_output_for_workflow is None:
                    intermediate_output_for_workflow = []

                # Perform validation before creating the workflow
                validate_workflow_graph(
                    edge_groups,
                    executors,
                    start_executor,
                    output_for_workflow or [],
                    intermediate_output_for_workflow or [],
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
                    self._name,
                    description=self._description,
                    max_iterations=self._max_iterations,
                    output_from=output_for_workflow,
                    intermediate_output_from=intermediate_output_for_workflow,
                )
                build_attributes: dict[str, Any] = {
                    OtelAttr.WORKFLOW_BUILDER_NAME: self._name,
                    OtelAttr.WORKFLOW_ID: workflow.id,
                    OtelAttr.WORKFLOW_DEFINITION: workflow.to_json(),
                }
                if self._description:
                    build_attributes[OtelAttr.WORKFLOW_BUILDER_DESCRIPTION] = self._description
                span.set_attributes(build_attributes)

                # Add workflow build completed event
                span.add_event(OtelAttr.BUILD_COMPLETED)

                return workflow

            except Exception as exc:
                attributes = {
                    OtelAttr.BUILD_ERROR_MESSAGE: str(exc),
                    OtelAttr.BUILD_ERROR_TYPE: type(exc).__name__,
                }
                span.add_event(OtelAttr.BUILD_ERROR, attributes)  # type: ignore[reportArgumentType, arg-type]
                capture_exception(span, exc)
                raise
