# Copyright (c) Microsoft. All rights reserved.

import logging
import sys
from collections.abc import Callable, Sequence
from typing import Any

from .._agents import AgentProtocol
from ..observability import OtelAttr, capture_exception, create_workflow_span
from ._agent_executor import AgentExecutor
from ._checkpoint import CheckpointStorage
from ._const import DEFAULT_MAX_ITERATIONS
from ._edge import (
    Case,
    Default,
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
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


logger = logging.getLogger(__name__)


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
                .add_edge(UpperCaseExecutor(id="upper"), ReverseExecutor(id="reverse"))
                .set_start_executor("upper")
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
        # Maps underlying AgentProtocol object id -> wrapped Executor so we reuse the same wrapper
        # across set_start_executor / add_edge calls. Without this, unnamed agents (which receive
        # random UUID based executor ids) end up wrapped multiple times, giving different ids for
        # the start node vs edge nodes and triggering a GraphConnectivityError during validation.
        self._agent_wrappers: dict[int, Executor] = {}

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

    def _maybe_wrap_agent(
        self,
        candidate: Executor | AgentProtocol,
        agent_thread: Any | None = None,
        output_response: bool = False,
        executor_id: str | None = None,
    ) -> Executor:
        """If the provided object implements AgentProtocol, wrap it in an AgentExecutor.

        This allows fluent builder APIs to directly accept agents instead of
        requiring callers to manually instantiate AgentExecutor.

        Args:
            candidate: The executor or agent to wrap.
            agent_thread: The thread to use for running the agent. If None, a new thread will be created.
            output_response: Whether to yield an AgentRunResponse as a workflow output when the agent completes.
            executor_id: A unique identifier for the executor. If None, the agent's name will be used if available.
        """
        try:  # Local import to avoid hard dependency at import time
            from agent_framework import AgentProtocol  # type: ignore
        except Exception:  # pragma: no cover - defensive
            AgentProtocol = object  # type: ignore

        if isinstance(candidate, Executor):  # Already an executor
            return candidate
        if isinstance(candidate, AgentProtocol):  # type: ignore[arg-type]
            # Reuse existing wrapper for the same agent instance if present
            agent_instance_id = id(candidate)
            existing = self._agent_wrappers.get(agent_instance_id)
            if existing is not None:
                return existing
            # Use agent name if available and unique among current executors
            name = getattr(candidate, "name", None)
            proposed_id: str | None = executor_id
            if proposed_id is None and name:
                proposed_id = str(name)
                if proposed_id in self._executors:
                    raise ValueError(
                        f"Duplicate executor ID '{proposed_id}' from agent name. "
                        "Agent names must be unique within a workflow."
                    )
            wrapper = AgentExecutor(
                candidate,
                agent_thread=agent_thread,
                output_response=output_response,
                id=proposed_id,
            )
            self._agent_wrappers[agent_instance_id] = wrapper
            return wrapper
        raise TypeError(
            f"WorkflowBuilder expected an Executor or AgentProtocol instance; got {type(candidate).__name__}."
        )

    def add_agent(
        self,
        agent: AgentProtocol,
        agent_thread: Any | None = None,
        output_response: bool = False,
        id: str | None = None,
    ) -> Self:
        """Add an agent to the workflow by wrapping it in an AgentExecutor.

        This method creates an AgentExecutor that wraps the agent with the given parameters
        and ensures that subsequent uses of the same agent instance in other builder methods
        (like add_edge, set_start_executor, etc.) will reuse the same wrapped executor.

        Note: Agents adapt their behavior based on how the workflow is executed:
        - run_stream(): Agents emit incremental AgentRunUpdateEvent events as tokens are produced
        - run(): Agents emit a single AgentRunEvent containing the complete response

        Args:
            agent: The agent to add to the workflow.
            agent_thread: The thread to use for running the agent. If None, a new thread will be created.
            output_response: Whether to yield an AgentRunResponse as a workflow output when the agent completes.
            id: A unique identifier for the executor. If None, the agent's name will be used if available.

        Returns:
            Self: The WorkflowBuilder instance for method chaining.

        Raises:
            ValueError: If the provided id or agent name conflicts with an existing executor.

        Example:
            .. code-block:: python

                from agent_framework import WorkflowBuilder
                from agent_framework_anthropic import AnthropicAgent

                # Create an agent
                agent = AnthropicAgent(name="writer", model="claude-3-5-sonnet-20241022")

                # Add the agent to a workflow
                workflow = WorkflowBuilder().add_agent(agent, output_response=True).set_start_executor(agent).build()
        """
        executor = self._maybe_wrap_agent(
            agent, agent_thread=agent_thread, output_response=output_response, executor_id=id
        )
        self._add_executor(executor)
        return self

    def add_edge(
        self,
        source: Executor | AgentProtocol,
        target: Executor | AgentProtocol,
        condition: Callable[[Any], bool] | None = None,
    ) -> Self:
        """Add a directed edge between two executors.

        The output types of the source and the input types of the target must be compatible.
        Messages sent by the source executor will be routed to the target executor.

        Args:
            source: The source executor of the edge.
            target: The target executor of the edge.
            condition: An optional condition function that determines whether the edge
                       should be traversed based on the message type.

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
                    WorkflowBuilder().add_edge(ProcessorA(id="a"), ProcessorB(id="b")).set_start_executor("a").build()
                )


                # With a condition
                def only_large_numbers(msg: int) -> bool:
                    return msg > 100


                workflow = (
                    WorkflowBuilder()
                    .add_edge(ProcessorA(id="a"), ProcessorB(id="b"), condition=only_large_numbers)
                    .set_start_executor("a")
                    .build()
                )
        """
        # TODO(@taochen): Support executor factories for lazy initialization
        source_exec = self._maybe_wrap_agent(source)
        target_exec = self._maybe_wrap_agent(target)
        source_id = self._add_executor(source_exec)
        target_id = self._add_executor(target_exec)
        self._edge_groups.append(SingleEdgeGroup(source_id, target_id, condition))  # type: ignore[call-arg]
        return self

    def add_fan_out_edges(
        self,
        source: Executor | AgentProtocol,
        targets: Sequence[Executor | AgentProtocol],
    ) -> Self:
        """Add multiple edges to the workflow where messages from the source will be sent to all targets.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source will be broadcast to all target executors concurrently.

        Args:
            source: The source executor of the edges.
            targets: A list of target executors for the edges.

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


                # Broadcast to multiple validators
                workflow = (
                    WorkflowBuilder()
                    .add_fan_out_edges(DataSource(id="source"), [ValidatorA(id="val_a"), ValidatorB(id="val_b")])
                    .set_start_executor("source")
                    .build()
                )
        """
        source_exec = self._maybe_wrap_agent(source)
        target_execs = [self._maybe_wrap_agent(t) for t in targets]
        source_id = self._add_executor(source_exec)
        target_ids = [self._add_executor(t) for t in target_execs]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids))  # type: ignore[call-arg]

        return self

    def add_switch_case_edge_group(
        self,
        source: Executor | AgentProtocol,
        cases: Sequence[Case | Default],
    ) -> Self:
        """Add an edge group that represents a switch-case statement.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source executor will be sent to one of the target executors based on
        the provided conditions.

        Think of this as a switch statement where each target executor corresponds to a case.
        Each condition function will be evaluated in order, and the first one that returns True
        will determine which target executor receives the message.

        The last case (the default case) will receive messages that fall through all conditions
        (i.e., no condition matched).

        Args:
            source: The source executor of the edges.
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


                # Route based on score value
                workflow = (
                    WorkflowBuilder()
                    .add_switch_case_edge_group(
                        Evaluator(id="eval"),
                        [
                            Case(condition=lambda r: r.score > 10, target=HighScoreHandler(id="high")),
                            Default(target=LowScoreHandler(id="low")),
                        ],
                    )
                    .set_start_executor("eval")
                    .build()
                )
        """
        source_exec = self._maybe_wrap_agent(source)
        source_id = self._add_executor(source_exec)
        # Convert case data types to internal types that only uses target_id.
        internal_cases: list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault] = []
        for case in cases:
            # Allow case targets to be agents
            case.target = self._maybe_wrap_agent(case.target)  # type: ignore[attr-defined]
            self._add_executor(case.target)
            if isinstance(case, Default):
                internal_cases.append(SwitchCaseEdgeGroupDefault(target_id=case.target.id))
            else:
                internal_cases.append(SwitchCaseEdgeGroupCase(condition=case.condition, target_id=case.target.id))
        self._edge_groups.append(SwitchCaseEdgeGroup(source_id, internal_cases))  # type: ignore[call-arg]

        return self

    def add_multi_selection_edge_group(
        self,
        source: Executor | AgentProtocol,
        targets: Sequence[Executor | AgentProtocol],
        selection_func: Callable[[Any, list[str]], list[str]],
    ) -> Self:
        """Add an edge group that represents a multi-selection execution model.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source executor will be sent to multiple target executors based on
        the provided selection function.

        The selection function should take a message and a list of target executor IDs,
        and return a list of executor IDs indicating which target executors should receive the message.

        Args:
            source: The source executor of the edges.
            targets: A list of target executors for the edges.
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


                # Select workers based on task priority
                def select_workers(task: Task, executor_ids: list[str]) -> list[str]:
                    if task.priority == "high":
                        return executor_ids  # Send to all workers
                    return [executor_ids[0]]  # Send to first worker only


                workflow = (
                    WorkflowBuilder()
                    .add_multi_selection_edge_group(
                        TaskDispatcher(id="dispatcher"),
                        [WorkerA(id="worker_a"), WorkerB(id="worker_b")],
                        selection_func=select_workers,
                    )
                    .set_start_executor("dispatcher")
                    .build()
                )
        """
        source_exec = self._maybe_wrap_agent(source)
        target_execs = [self._maybe_wrap_agent(t) for t in targets]
        source_id = self._add_executor(source_exec)
        target_ids = [self._add_executor(t) for t in target_execs]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids, selection_func))  # type: ignore[call-arg]

        return self

    def add_fan_in_edges(
        self,
        sources: Sequence[Executor | AgentProtocol],
        target: Executor | AgentProtocol,
    ) -> Self:
        """Add multiple edges from sources to a single target executor.

        The edges will be grouped together for synchronized processing, meaning
        the target executor will only be executed once all source executors have completed.

        The target executor will receive a list of messages aggregated from all source executors.
        Thus the input types of the target executor must be compatible with a list of the output
        types of the source executors.

        Args:
            sources: A list of source executors for the edges.
            target: The target executor for the edges.

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


                # Collect results from multiple producers
                workflow = (
                    WorkflowBuilder()
                    .add_fan_in_edges([Producer(id="prod_1"), Producer(id="prod_2")], Aggregator(id="agg"))
                    .set_start_executor("prod_1")
                    .build()
                )
        """
        source_execs = [self._maybe_wrap_agent(s) for s in sources]
        target_exec = self._maybe_wrap_agent(target)
        source_ids = [self._add_executor(s) for s in source_execs]
        target_id = self._add_executor(target_exec)
        self._edge_groups.append(FanInEdgeGroup(source_ids, target_id))  # type: ignore[call-arg]

        return self

    def add_chain(self, executors: Sequence[Executor | AgentProtocol]) -> Self:
        """Add a chain of executors to the workflow.

        The output of each executor in the chain will be sent to the next executor in the chain.
        The input types of each executor must be compatible with the output types of the previous executor.

        Circles in the chain are not allowed, meaning the chain cannot have two executors with the same ID.

        Args:
            executors: A list of executors to be added to the chain.

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


                # Chain executors in sequence
                workflow = (
                    WorkflowBuilder()
                    .add_chain([Step1(id="step1"), Step2(id="step2"), Step3(id="step3")])
                    .set_start_executor("step1")
                    .build()
                )
        """
        # Wrap each candidate first to ensure stable IDs before adding edges
        wrapped: list[Executor] = [self._maybe_wrap_agent(e) for e in executors]
        for i in range(len(wrapped) - 1):
            self.add_edge(wrapped[i], wrapped[i + 1])
        return self

    def set_start_executor(self, executor: Executor | AgentProtocol | str) -> Self:
        """Set the starting executor for the workflow.

        The start executor is the entry point for the workflow. When the workflow is executed,
        the initial message will be sent to this executor.

        Args:
            executor: The starting executor, which can be an Executor instance, AgentProtocol instance,
                or the string ID of an executor previously added to the workflow.

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


                # Set by executor instance
                entry = EntryPoint(id="entry")
                workflow = WorkflowBuilder().add_edge(entry, Processor(id="proc")).set_start_executor(entry).build()

                # Set by executor ID string
                workflow = (
                    WorkflowBuilder()
                    .add_edge(EntryPoint(id="entry"), Processor(id="proc"))
                    .set_start_executor("entry")
                    .build()
                )
        """
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
                    .add_edge(StepA(id="step_a"), StepB(id="step_b"))
                    .add_edge(StepB(id="step_b"), StepA(id="step_a"))  # Cycle
                    .set_start_executor("step_a")
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
                    .add_edge(ProcessorA(id="proc_a"), ProcessorB(id="proc_b"))
                    .set_start_executor("proc_a")
                    .with_checkpointing(storage)
                    .build()
                )

                # Run with checkpoint saving
                events = await workflow.run("input")
        """
        self._checkpoint_storage = checkpoint_storage
        return self

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
                workflow = WorkflowBuilder().set_start_executor(MyExecutor(id="executor")).build()

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

                if not self._start_executor:
                    raise ValueError(
                        "Starting executor must be set using set_start_executor before building the workflow."
                    )

                # Perform validation before creating the workflow
                validate_workflow_graph(
                    self._edge_groups,
                    self._executors,
                    self._start_executor,
                )

                # Add validation completed event
                span.add_event(OtelAttr.BUILD_VALIDATION_COMPLETED)

                context = InProcRunnerContext(self._checkpoint_storage)

                # Create workflow instance after validation
                workflow = Workflow(
                    self._edge_groups,
                    self._executors,
                    self._start_executor,
                    context,
                    self._max_iterations,
                    name=self._name,
                    description=self._description,
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

            except Exception as exc:
                attributes = {
                    OtelAttr.BUILD_ERROR_MESSAGE: str(exc),
                    OtelAttr.BUILD_ERROR_TYPE: type(exc).__name__,
                }
                span.add_event(OtelAttr.BUILD_ERROR, attributes)  # type: ignore[reportArgumentType, arg-type]
                capture_exception(span, exc)
                raise
