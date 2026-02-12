# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from ._checkpoint import CheckpointID, CheckpointStorage, WorkflowCheckpoint
from ._const import EXECUTOR_STATE_KEY
from ._edge import EdgeGroup
from ._edge_runner import EdgeRunner, create_edge_runner
from ._events import WorkflowEvent
from ._exceptions import (
    WorkflowCheckpointException,
    WorkflowConvergenceException,
    WorkflowRunnerException,
)
from ._executor import Executor
from ._runner_context import (
    RunnerContext,
    WorkflowMessage,
)
from ._state import State

logger = logging.getLogger(__name__)

RequestHandler = Callable[[Any], Awaitable[Any]]
RequestHandlerMap = Mapping[type[Any], RequestHandler]


class Runner:
    """A class to run a workflow in Pregel supersteps."""

    def __init__(
        self,
        edge_groups: Sequence[EdgeGroup],
        executors: dict[str, Executor],
        state: State,
        ctx: RunnerContext,
        workflow_name: str,
        graph_signature_hash: str,
        max_iterations: int = 100,
    ) -> None:
        """Initialize the runner with edges, state, and context.

        Args:
            edge_groups: The edge groups of the workflow.
            executors: Map of executor IDs to executor instances.
            state: The state for the workflow.
            ctx: The runner context for the workflow.
            workflow_name: The name of the workflow, used for checkpoint labeling.
            graph_signature_hash: A hash representing the workflow graph topology for checkpoint validation.
            max_iterations: The maximum number of iterations to run.
        """
        # Workflow instance related attributes
        self._executors = executors
        self._edge_runners = [create_edge_runner(group, executors) for group in edge_groups]
        self._edge_runner_map = self._parse_edge_runners(self._edge_runners)
        self._ctx = ctx
        self._workflow_name = workflow_name
        self._graph_signature_hash = graph_signature_hash

        # Runner state related attributes
        self._iteration = 0
        self._max_iterations = max_iterations
        self._state = state
        self._running = False
        self._resumed_from_checkpoint = False  # Track whether we resumed

    @property
    def context(self) -> RunnerContext:
        """Get the workflow context."""
        return self._ctx

    def reset_iteration_count(self) -> None:
        """Reset the iteration count to zero."""
        self._iteration = 0

    @staticmethod
    def _type_name(t: type[Any]) -> str:
        """Return a human-readable type name, handling union/generic aliases."""
        return getattr(t, "__name__", str(t))

    async def _invoke_request_handler(
        self,
        handler_fn: RequestHandler,
        request_id: str,
        request_data: Any,
    ) -> None:
        """Invoke an async request handler and submit the response to the context."""
        try:
            response = await handler_fn(request_data)
        except Exception:
            logger.exception(f"Response handler failed for request {request_id} (type={type(request_data).__name__})")
            return

        try:
            await self._ctx.send_request_info_response(request_id, response)
        except Exception:
            logger.exception(
                f"Failed to submit response for request {request_id} "
                f"(type={type(request_data).__name__}). "
                f"Handler succeeded but response could not be delivered."
            )

    def _dispatch_request_handler(
        self,
        event: WorkflowEvent[Any],
        request_handlers: RequestHandlerMap | None,
        outstanding_handler_tasks: set[asyncio.Task[None]] | None,
    ) -> None:
        """Schedule a request handler task for request_info events when configured."""
        if event.type != "request_info" or request_handlers is None or outstanding_handler_tasks is None:
            return

        request_data: Any = event.data
        request_data_type: type[Any] = cast(type[Any], type(request_data))
        matched_handler = request_handlers.get(request_data_type)
        if matched_handler is None:
            registered_types = [self._type_name(t) for t in request_handlers]
            logger.warning(
                f"No response handler registered for request type "
                f"{self._type_name(request_data_type)} (request_id={event.request_id}). "
                f"Registered types: {registered_types}"
            )
            return

        task = asyncio.create_task(self._invoke_request_handler(matched_handler, event.request_id, request_data))
        outstanding_handler_tasks.add(task)
        task.add_done_callback(outstanding_handler_tasks.discard)

    async def _cancel_outstanding_handler_tasks(
        self,
        outstanding_handler_tasks: set[asyncio.Task[None]] | None,
    ) -> None:
        """Cancel and await outstanding handler tasks."""
        if not outstanding_handler_tasks:
            return

        for task in outstanding_handler_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*outstanding_handler_tasks, return_exceptions=True)

    async def run_until_convergence(
        self,
        request_handlers: RequestHandlerMap | None = None,
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """Run the workflow until no more messages are sent.

        Args:
            request_handlers: Optional mapping of request data types to async handler
                functions. When provided, request_info events are dispatched inline and
                handler responses are submitted back through the runner context.
        """
        if self._running:
            raise WorkflowRunnerException("Runner is already running.")

        outstanding_handler_tasks: set[asyncio.Task[None]] | None = set() if request_handlers else None

        self._running = True
        previous_checkpoint_id: CheckpointID | None = None
        try:
            # Emit any events already produced prior to entering loop
            if await self._ctx.has_events():
                logger.info("Yielding pre-loop events")
                for event in await self._ctx.drain_events():
                    self._dispatch_request_handler(event, request_handlers, outstanding_handler_tasks)
                    yield event

            # Create the first checkpoint. Checkpoints are usually considered to be created at the end of an iteration,
            # we can think of the first checkpoint as being created at the end of a "superstep 0" which captures the
            # states after which the start executor has run.  Note that we execute the start executor outside of the
            # main iteration loop.
            if await self._ctx.has_messages() and not self._resumed_from_checkpoint:
                previous_checkpoint_id = await self._create_checkpoint_if_enabled(previous_checkpoint_id)

            while self._iteration < self._max_iterations:
                logger.info(f"Starting superstep {self._iteration + 1}")
                yield WorkflowEvent.superstep_started(iteration=self._iteration + 1)

                # Run iteration concurrently with live event streaming: we poll
                # for new events while the iteration coroutine progresses.
                iteration_task = asyncio.create_task(self._run_iteration())
                try:
                    while not iteration_task.done():
                        try:
                            # Wait briefly for any new event; timeout allows progress checks
                            event = await asyncio.wait_for(self._ctx.next_event(), timeout=0.05)
                            self._dispatch_request_handler(event, request_handlers, outstanding_handler_tasks)
                            yield event
                        except asyncio.TimeoutError:
                            # Periodically continue to let iteration advance
                            continue
                except asyncio.CancelledError:
                    # Propagate cancellation to the iteration task to avoid orphaned work
                    iteration_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await iteration_task
                    raise

                # Propagate errors from iteration, but first surface any pending events
                try:
                    await iteration_task
                except Exception:
                    # Make sure failure-related events (like ExecutorFailedEvent) are surfaced
                    if await self._ctx.has_events():
                        for event in await self._ctx.drain_events():
                            self._dispatch_request_handler(event, request_handlers, outstanding_handler_tasks)
                            yield event
                    raise
                self._iteration += 1

                # Drain any straggler events emitted at tail end
                if await self._ctx.has_events():
                    for event in await self._ctx.drain_events():
                        self._dispatch_request_handler(event, request_handlers, outstanding_handler_tasks)
                        yield event

                logger.info(f"Completed superstep {self._iteration}")

                # Commit pending state changes at superstep boundary
                self._state.commit()

                # Create checkpoint after each superstep iteration
                previous_checkpoint_id = await self._create_checkpoint_if_enabled(previous_checkpoint_id)

                yield WorkflowEvent.superstep_completed(iteration=self._iteration)

                # Check for convergence: no more messages to process
                if not await self._ctx.has_messages():
                    if outstanding_handler_tasks is not None:
                        # Wait for in-flight request handlers before declaring idle.
                        # A completed handler may enqueue a response message that should
                        # be processed in another superstep within this same run.
                        still_running: set[asyncio.Task[None]] = {
                            task for task in outstanding_handler_tasks if not task.done()
                        }
                        while still_running:
                            wait_result: tuple[set[asyncio.Task[None]], set[asyncio.Task[None]]] = await asyncio.wait(
                                still_running,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            still_running = wait_result[1]
                            if await self._ctx.has_messages():
                                break
                        if await self._ctx.has_messages():
                            continue
                    break

            if self._iteration >= self._max_iterations and await self._ctx.has_messages():
                raise WorkflowConvergenceException(f"Runner did not converge after {self._max_iterations} iterations.")

            logger.info(f"Workflow completed after {self._iteration} supersteps")
            self._resumed_from_checkpoint = False  # Reset resume flag for next run
        finally:
            await self._cancel_outstanding_handler_tasks(outstanding_handler_tasks)
            self._running = False

    async def _run_iteration(self) -> None:
        async def _deliver_messages(source_executor_id: str, messages: list[WorkflowMessage]) -> None:
            """Outer loop to concurrently deliver messages from all sources to their targets."""

            async def _deliver_message_inner(edge_runner: EdgeRunner, message: WorkflowMessage) -> bool:
                """Inner loop to deliver a single message through an edge runner."""
                return await edge_runner.send_message(message, self._state, self._ctx)

            # Route all messages through normal workflow edges
            associated_edge_runners = self._edge_runner_map.get(source_executor_id, [])
            if not associated_edge_runners:
                # This is expected for terminal nodes (e.g., EndWorkflow, last action in workflow)
                logger.debug(f"No outgoing edges found for executor {source_executor_id}; dropping messages.")
                return

            for message in messages:
                # Deliver a message through all edge runners associated with the source executor concurrently.
                tasks = [_deliver_message_inner(edge_runner, message) for edge_runner in associated_edge_runners]
                await asyncio.gather(*tasks)

        messages = await self._ctx.drain_messages()
        tasks = [_deliver_messages(source_executor_id, messages) for source_executor_id, messages in messages.items()]
        await asyncio.gather(*tasks)

    async def _create_checkpoint_if_enabled(self, previous_checkpoint_id: CheckpointID | None) -> CheckpointID | None:
        """Create a checkpoint if checkpointing is enabled and attach a label and metadata."""
        if not self._ctx.has_checkpointing():
            return None

        try:
            # Save executor states into the shared state before creating the checkpoint,
            # so that they are included in the checkpoint payload.
            await self._save_executor_states()

            checkpoint_id = await self._ctx.create_checkpoint(
                self._workflow_name,
                self._graph_signature_hash,
                self._state,
                previous_checkpoint_id,
                self._iteration,
            )

            logger.info(f"Created checkpoint: {checkpoint_id}")
            return checkpoint_id
        except Exception as e:
            logger.warning(f"Failed to create checkpoint: {e}")
            return None

    async def restore_from_checkpoint(
        self,
        checkpoint_id: CheckpointID,
        checkpoint_storage: CheckpointStorage | None = None,
    ) -> None:
        """Restore workflow state from a checkpoint.

        Args:
            checkpoint_id: The ID of the checkpoint to restore from
            checkpoint_storage: Optional storage to load checkpoints from when the
                runner context itself is not configured with checkpointing.

        Returns:
            None on success.

        Raises:
            WorkflowCheckpointException on failure.
        """
        try:
            # Load the checkpoint
            checkpoint: WorkflowCheckpoint | None
            if self._ctx.has_checkpointing():
                checkpoint = await self._ctx.load_checkpoint(checkpoint_id)
            elif checkpoint_storage is not None:
                checkpoint = await checkpoint_storage.load(checkpoint_id)
            else:
                raise WorkflowCheckpointException(
                    "Cannot load checkpoint: no checkpointing configured in context or external storage provided."
                )

            if not checkpoint:
                logger.error(f"Checkpoint {checkpoint_id} not found")
                raise WorkflowCheckpointException(f"Checkpoint {checkpoint_id} not found")

            # Validate the loaded checkpoint against the workflow
            if self._graph_signature_hash != checkpoint.graph_signature_hash:
                raise WorkflowCheckpointException(
                    "Workflow graph has changed since the checkpoint was created. "
                    "Please rebuild the original workflow before resuming."
                )

            # Restore state
            self._state.import_state(checkpoint.state)
            # Restore executor states using the restored state
            await self._restore_executor_states()
            # Apply the checkpoint to the context
            await self._ctx.apply_checkpoint(checkpoint)
            # Mark the runner as resumed
            self._mark_resumed(checkpoint.iteration_count)

            logger.info(f"Successfully restored workflow from checkpoint: {checkpoint_id}")
        except WorkflowCheckpointException:
            raise
        except Exception as e:
            logger.error(f"Failed to restore from checkpoint {checkpoint_id}: {e}")
            raise WorkflowCheckpointException(f"Failed to restore from checkpoint {checkpoint_id}") from e

    async def _save_executor_states(self) -> None:
        """Populate executor state by calling checkpoint hooks on executors."""
        for exec_id, executor in self._executors.items():
            # Try the updated behavior only if backward compatibility did not yield state
            try:
                state_dict = await executor.on_checkpoint_save()
                await self._set_executor_state(exec_id, state_dict)
            except WorkflowCheckpointException:
                raise
            except Exception as ex:  # pragma: no cover
                raise WorkflowCheckpointException(f"Executor {exec_id} on_checkpoint_save failed") from ex

    async def _restore_executor_states(self) -> None:
        """Restore executor state by calling restore hooks on executors."""
        has_executor_states = self._state.has(EXECUTOR_STATE_KEY)
        if not has_executor_states:
            return

        executor_states = self._state.get(EXECUTOR_STATE_KEY)
        if not isinstance(executor_states, dict):
            raise WorkflowCheckpointException("Executor states in shared state is not a dictionary. Unable to restore.")

        for executor_id, state in executor_states.items():  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(executor_id, str):
                raise WorkflowCheckpointException("Executor ID in executor states is not a string. Unable to restore.")
            if not isinstance(state, dict) or not all(isinstance(k, str) for k in state):  # pyright: ignore[reportUnknownVariableType]
                raise WorkflowCheckpointException(
                    f"Executor state for {executor_id} is not a dict[str, Any]. Unable to restore."
                )

            executor = self._executors.get(executor_id)
            if not executor:
                raise WorkflowCheckpointException(f"Executor {executor_id} not found during state restoration.")

            # Try the updated behavior only if backward compatibility did not restore
            try:
                await executor.on_checkpoint_restore(state)  # pyright: ignore[reportUnknownArgumentType]
            except Exception as ex:  # pragma: no cover - defensive
                raise WorkflowCheckpointException(f"Executor {executor_id} on_checkpoint_restore failed") from ex

    def _parse_edge_runners(self, edge_runners: list[EdgeRunner]) -> dict[str, list[EdgeRunner]]:
        """Parse the edge runners of the workflow into a mapping where each source executor ID maps to its edge runners.

        Args:
            edge_runners: A list of edge runners in the workflow.

        Returns:
            A dictionary mapping each source executor ID to a list of edge runners.
        """
        parsed: defaultdict[str, list[EdgeRunner]] = defaultdict(list)
        for runner in edge_runners:
            # Accessing protected attribute (_edge_group) intentionally for internal wiring.
            for source_executor_id in runner._edge_group.source_executor_ids:  # type: ignore[attr-defined]
                parsed[source_executor_id].append(runner)

        return parsed

    def _mark_resumed(self, iteration: int) -> None:
        """Mark the runner as having resumed from a checkpoint.

        Optionally set the current iteration and max iterations.
        """
        self._resumed_from_checkpoint = True
        self._iteration = iteration

    async def _set_executor_state(self, executor_id: str, state: dict[str, Any]) -> None:
        """Store executor state in state under a reserved key.

        Executors call this with a JSON-serializable dict capturing the minimal
        state needed to resume. It replaces any previously stored state.
        """
        existing_states = self._state.get(EXECUTOR_STATE_KEY, {})

        if not isinstance(existing_states, dict):
            raise WorkflowCheckpointException("Existing executor states in state is not a dictionary.")

        existing_states[executor_id] = state
        self._state.set(EXECUTOR_STATE_KEY, existing_states)
