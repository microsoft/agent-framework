# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterable
from typing import Any, cast

from ._edge import Edge
from ._events import WorkflowEvent
from ._runner_context import CheckpointableRunnerContext, Message, RunnerContext
from ._shared_state import SharedState

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 100


class Runner:
    """A class to run a workflow in Pregel supersteps."""

    def __init__(
        self,
        edges: list[Edge],
        shared_state: SharedState,
        ctx: RunnerContext | CheckpointableRunnerContext,
        max_iterations: int = 100,
        workflow_id: str | None = None,
    ):
        """Initialize the runner with edges, shared state, and context.

        Args:
            edges: The edges of the workflow.
            shared_state: The shared state for the workflow.
            ctx: The runner context for the workflow.
            max_iterations: The maximum number of iterations to run.
            workflow_id: The workflow ID for checkpointing.
        """
        self._edge_map = self._parse_edges(edges)
        self._ctx = ctx
        self._iteration = 0
        self._max_iterations = max_iterations
        self._shared_state = shared_state
        self._workflow_id = workflow_id
        self._running = False

        # Set workflow ID in context if it's checkpointable
        if isinstance(ctx, CheckpointableRunnerContext) and workflow_id:
            ctx.set_workflow_id(workflow_id)

    @property
    def context(self) -> RunnerContext | CheckpointableRunnerContext:
        """Get the workflow context."""
        return self._ctx

    async def run_until_convergence(self) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow until no more messages are sent."""
        if self._running:
            raise RuntimeError("Runner is already running.")

        self._running = True
        try:
            # Process any events from initial execution before checkpointing
            if await self._ctx.has_events():
                logger.info("Processing events from initial execution")
                events = await self._ctx.drain_events()
                for event in events:
                    logger.info(f"Yielding initial event: {event}")
                    yield event

            # Create first checkpoint if there are messages from initial execution
            if await self._ctx.has_messages():
                logger.info("Creating checkpoint after initial execution")
                await self._create_checkpoint_if_enabled("after_initial_execution")

            # Initialize context with starting iteration state
            await self._update_context_with_shared_state()

            while self._iteration < self._max_iterations:
                logger.info(f"Starting superstep {self._iteration + 1}")
                await self._run_iteration()
                self._iteration += 1

                # Update context with current iteration state immediately
                await self._update_context_with_shared_state()

                logger.info(f"Completed superstep {self._iteration}")

                # Check what state we have before checkpointing
                has_messages_before = await self._ctx.has_messages()
                has_events_before = await self._ctx.has_events()
                logger.debug(f"Before checkpoint: messages={has_messages_before}, events={has_events_before}")

                # Process events first before any checkpointing
                if await self._ctx.has_events():
                    logger.info("Processing events before checkpointing")
                    events = await self._ctx.drain_events()
                    for event in events:
                        logger.debug(f"Yielding event: {event}")
                        yield event

                has_messages = await self._ctx.has_messages()
                has_events = await self._ctx.has_events()
                logger.debug(f"Has messages after superstep {self._iteration}: {has_messages}")
                logger.debug(f"Has events after superstep {self._iteration}: {has_events}")

                # Create checkpoint after each superstep iteration
                await self._create_checkpoint_if_enabled(f"superstep_{self._iteration}")

                # Check if we should continue processing
                if has_messages:
                    logger.debug("More messages to process, continuing")
                else:
                    # No more messages - workflow has converged
                    logger.debug("No more messages, workflow converged")
                    break

            # Check if we reached max iterations without convergence
            if self._iteration >= self._max_iterations:
                has_messages = await self._ctx.has_messages()
                if has_messages:
                    raise RuntimeError(f"Runner did not converge after {self._max_iterations} iterations.")

            logger.info(f"Workflow completed after {self._iteration} supersteps")
            self._iteration = 0
        finally:
            self._running = False

    async def _run_iteration(self):
        """Run a superstep of the workflow execution."""

        async def _deliver_messages(source_executor_id: str, messages: list[Message]) -> None:
            """Deliver messages to the executors.

            Outer loop to concurrently deliver messages from all sources to their targets.
            """

            async def _deliver_messages_inner(
                edge: Edge,
                messages: list[Message],
            ) -> None:
                """Deliver messages to a specific target executor.

                Inner loop to deliver messages to a specific target executor.
                """
                for message in messages:
                    if message.target_id is not None and message.target_id != edge.target_id:
                        continue

                    if not edge.can_handle(message.data):
                        continue

                    await edge.send_message(message, self._shared_state, self._ctx)

            associated_edges = self._edge_map.get(source_executor_id, [])
            tasks = [asyncio.create_task(_deliver_messages_inner(edge, messages)) for edge in associated_edges]
            await asyncio.gather(*tasks)

        messages = await self._ctx.drain_messages()
        tasks = [
            asyncio.create_task(_deliver_messages(source_executor_id, messages))
            for source_executor_id, messages in messages.items()
        ]
        await asyncio.gather(*tasks)

    async def _create_checkpoint_if_enabled(self, checkpoint_type: str) -> str | None:
        """Create a checkpoint if the context supports it.

        Args:
            checkpoint_type: A descriptive name for the checkpoint (e.g., 'initial', 'iteration_5', 'final')
                Used for logging/debugging.

        Returns:
            Checkpoint ID if created, None otherwise
        """
        if not isinstance(self._ctx, CheckpointableRunnerContext):
            return None

        try:
            # Update shared state information without interfering with events
            await self._update_context_with_shared_state()

            # Create checkpoint with descriptive ID
            checkpoint_id = await self._ctx.create_checkpoint()
            logger.info(f"Created {checkpoint_type} checkpoint: {checkpoint_id}")
            return checkpoint_id
        except Exception as e:
            logger.warning(f"Failed to create {checkpoint_type} checkpoint: {e}")
            return None

    async def _update_context_with_shared_state(self) -> None:
        """Update the context with current shared state for checkpointing."""
        if not isinstance(self._ctx, CheckpointableRunnerContext):
            return

        try:
            # Get current checkpoint state
            current_state = await self._ctx.get_checkpoint_state()

            # Add shared state and runtime info
            shared_state_data = {}
            async with self._shared_state.hold():
                # Extract the internal state (this is implementation-specific)
                if hasattr(self._shared_state, "_state"):
                    shared_state_data = dict(self._shared_state._state)  # type: ignore[attr-defined]

            # Update the state with current runtime information
            current_state["shared_state"] = shared_state_data
            current_state["iteration_count"] = self._iteration
            current_state["max_iterations"] = self._max_iterations

            # Set the updated state back
            await self._ctx.set_checkpoint_state(current_state)
        except Exception as e:
            logger.warning(f"Failed to update context with shared state: {e}")

    async def restore_from_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore workflow state from a checkpoint.

        Args:
            checkpoint_id: The ID of the checkpoint to restore from

        Returns:
            True if restoration was successful, False otherwise
        """
        if not isinstance(self._ctx, CheckpointableRunnerContext):
            logger.warning("Context does not support checkpointing")
            return False

        try:
            # Restore the context state
            success = await self._ctx.restore_from_checkpoint(checkpoint_id)
            if not success:
                return False

            # Restore shared state and runtime info
            await self._restore_shared_state_from_context()

            logger.info(f"Successfully restored workflow from checkpoint: {checkpoint_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore from checkpoint {checkpoint_id}: {e}")
            return False

    async def _restore_shared_state_from_context(self) -> None:
        """Restore shared state from the checkpointed context."""
        if not isinstance(self._ctx, CheckpointableRunnerContext):
            return

        try:
            # Get the restored state
            restored_state = await self._ctx.get_checkpoint_state()

            # Restore shared state
            shared_state_data = cast(dict[str, Any], restored_state.get("shared_state", {}))
            if shared_state_data and hasattr(self._shared_state, "_state"):
                async with self._shared_state.hold():
                    self._shared_state._state.clear()  # type: ignore[attr-defined]
                    self._shared_state._state.update(shared_state_data)  # type: ignore[attr-defined]

            # Restore runtime state
            self._iteration = cast(int, restored_state.get("iteration_count", 0))
            self._max_iterations = cast(int, restored_state.get("max_iterations", self._max_iterations))

        except Exception as e:
            logger.warning(f"Failed to restore shared state from context: {e}")

    def _parse_edges(self, edges: list[Edge]) -> dict[str, list[Edge]]:
        """Parse the edges of the workflow into a more convenient format.

        Args:
            edges: A list of edges in the workflow.

        Returns:
            A dictionary mapping each source executor ID to a list of target executor IDs.
        """
        parsed: defaultdict[str, list[Edge]] = defaultdict(list)
        for edge in edges:
            parsed[edge.source_id].append(edge)
        return parsed
