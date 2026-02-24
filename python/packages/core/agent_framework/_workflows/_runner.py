# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import AsyncGenerator, Sequence
from typing import Any

from ..exceptions import (
    WorkflowCheckpointException,
    WorkflowConvergenceException,
    WorkflowRunnerException,
)
from ._checkpoint import CheckpointID, CheckpointStorage, WorkflowCheckpoint
from ._const import EXECUTOR_STATE_KEY
from ._edge import EdgeGroup
from ._edge_runner import EdgeRunner, create_edge_runner
from ._events import WorkflowEvent
from ._executor import Executor
from ._runner_context import (
    RunnerContext,
    WorkflowMessage,
)
from ._state import State

logger = logging.getLogger(__name__)


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

    async def run_until_convergence(self) -> AsyncGenerator[WorkflowEvent, None]:
        """Run the workflow until no more messages are sent."""
        if self._running:
            raise WorkflowRunnerException("Runner is already running.")

        self._running = True
        previous_checkpoint_id: CheckpointID | None = None
        try:
            # Emit any events already produced prior to entering loop
            if await self._ctx.has_events():
                logger.info("Yielding pre-loop events")
                for event in await self._ctx.drain_events():
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
                            yield event
                    raise
                self._iteration += 1

                # Drain any straggler events emitted at tail end
                if await self._ctx.has_events():
                    for event in await self._ctx.drain_events():
                        yield event

                logger.info(f"Completed superstep {self._iteration}")

                # Commit pending state changes at superstep boundary
                self._state.commit()

                # Create checkpoint after each superstep iteration
                previous_checkpoint_id = await self._create_checkpoint_if_enabled(previous_checkpoint_id)

                yield WorkflowEvent.superstep_completed(iteration=self._iteration)

                # Check for convergence: no more messages to process
                if not await self._ctx.has_messages():
                    break

            if self._iteration >= self._max_iterations and await self._ctx.has_messages():
                raise WorkflowConvergenceException(f"Runner did not converge after {self._max_iterations} iterations.")

            logger.info(f"Workflow completed after {self._iteration} supersteps")
            self._resumed_from_checkpoint = False  # Reset resume flag for next run
        finally:
            self._running = False

    async def _run_iteration(self) -> None:
        """Run a single iteration of the workflow.

        Messages are delivered through edge runners. A source executor may have multiple outgoing edge
        runners. All edge runners run concurrently, but messages sent through the same edge runner are
        delivered in the order they were sent to preserve message ordering guarantees per edge.

        What this means in practice:
        - A message from a source to multiple target is delivered to all targets concurrently.
        - Multiple messages from a source to the same target are delivered in the order they were sent.
        - Multiple messages from different sources to the same target can be delivered to the target one
          at a time in any order, because true parallelism is not realized in Python.
        - Multiple message from different sources to different targets are delivered concurrently to all
          targets, assuming each message is targeting a unique target, or it falls back to the previous
          rules if there are multiple messages targeting the same target.
        - Special case: if using a fan-out edge runner (or derived edge runner that replicates messages
          to multiple targets such as multi-selection or switch-case) to send messages to targets from
          a source by specifying the target, the messages will be delivered to the specified targets
          in the order they were sent. This is because all messages go through the same edge runner instance
          which preserves message order.
        """

        async def _deliver_messages(source_executor_id: str, source_messages: list[WorkflowMessage]) -> None:
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

            async def _deliver_messages_for_edge_runner(edge_runner: EdgeRunner) -> None:
                # Preserve message order per edge runner (and therefore per routed target path)
                # while still allowing parallelism across different edge runners.
                for message in source_messages:
                    await _deliver_message_inner(edge_runner, message)

            tasks = [_deliver_messages_for_edge_runner(edge_runner) for edge_runner in associated_edge_runners]
            await asyncio.gather(*tasks)

        message_batches = await self._ctx.drain_messages()
        tasks = [
            _deliver_messages(source_executor_id, source_messages)
            for source_executor_id, source_messages in message_batches.items()
        ]
        await asyncio.gather(*tasks)

    async def _create_checkpoint_if_enabled(self, previous_checkpoint_id: CheckpointID | None) -> CheckpointID | None:
        """Create a checkpoint if checkpointing is enabled and attach a label and metadata."""
        if not self._ctx.has_checkpointing():
            return None

        try:
            # Save executor states into the shared state before creating the checkpoint,
            # so that they are included in the checkpoint payload.
            await self._save_executor_states()
            # `on_checkpoint_save()` writes via State.set(), which stages values in the
            # pending buffer. Checkpoints serialize committed state only, so commit here
            # to ensure executor snapshots are captured in this checkpoint.
            self._state.commit()

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
