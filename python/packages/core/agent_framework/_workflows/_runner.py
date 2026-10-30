# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import copy
import logging
import warnings
from collections import defaultdict
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from ..exceptions import (
    WorkflowCheckpointException,
    WorkflowConvergenceException,
)
from ._checkpoint import CheckpointID, CheckpointStorage, WorkflowCheckpoint
from ._const import EDGE_STATE_KEY, EXECUTOR_STATE_KEY, WORKFLOW_RESPONSE_SCOPE_KEY
from ._edge import EdgeGroup
from ._edge_runner import EdgeRunner, create_edge_runner, gather_cancelling_siblings_on_error
from ._events import WorkflowEvent
from ._executor import Executor
from ._request_context import get_response_scopes, request_context_state_key, validate_request_contexts
from ._runner_context import (
    RunnerContext,
    WorkflowMessage,
    _get_queued_response_info_events,  # pyright: ignore[reportPrivateUsage]
    _SupportsQueuedMessages,  # pyright: ignore[reportPrivateUsage]
)
from ._state import State

logger = logging.getLogger(__name__)


def warn_runner_deprecated() -> None:
    """Emit a deprecation warning when ``Runner`` is accessed from the public API.

    ``Runner`` remains importable from ``agent_framework`` for backward
    compatibility, but it is intended for internal use only and will be removed
    from the public API in a future version.
    """
    warnings.warn(
        "`Runner` is deprecated and will be removed from the public API in a future version. "
        "It is intended for internal use only.",
        DeprecationWarning,
        stacklevel=3,
    )


class RunnerImpl:
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
        # Keyed by topology rather than EdgeGroup.id, which is a random UUID: a checkpoint has to
        # restore onto a rebuilt instance of the same workflow definition.
        self._edge_runner_state_keys = [runner.state_key for runner in self._edge_runners]
        self._ctx = ctx
        self._workflow_name = workflow_name
        self._graph_signature_hash = graph_signature_hash

        # Runner state related attributes
        self._iteration = 0
        self._max_iterations = max_iterations
        self._state = state

        # Checkpointing related attributes
        self._previous_checkpoint_id: CheckpointID | None = None
        self._response_batch_validator: Callable[[Sequence[WorkflowEvent]], None] | None = None
        self._queued_response_validator: Callable[[set[str]], Awaitable[None]] | None = None
        self._wrapped_response_validator: (
            Callable[[Mapping[str, Sequence[WorkflowEvent]], set[str]], Awaitable[None]] | None
        ) = None

    @property
    def context(self) -> RunnerContext:
        """Get the runner context for message, event, and checkpoint handling."""
        return self._ctx

    @property
    def state(self) -> State:
        """Get the shared state for the workflow."""
        return self._state

    def reset_iteration_count(self) -> None:
        """Reset the iteration count to zero.

        This is useful when the workflow resumes from a new set of messages.

        Note:
            When a workflow is resumed from a response (for a request_info_event)
            or a checkpoint, the iteration count is normally NOT reset.
        """
        self._iteration = 0

    async def run_until_convergence(self) -> AsyncGenerator[WorkflowEvent]:
        """Run the workflow until no more messages are sent.

        The runner's checkpoint responsibility is intentionally narrow: it creates a
        checkpoint at the end of each superstep. The entry checkpoint that captures the
        run's initial input (before any executor runs) is created by ``Workflow`` prior
        to entering this loop, since only the workflow knows how the run was started
        (fresh input vs. checkpoint resume vs. responses).
        """
        # Emit any events already produced prior to entering loop
        if await self._ctx.has_events():
            logger.info("Yielding pre-loop events")
            for event in await self._ctx.drain_events():
                yield event

        while self._iteration < self._max_iterations:
            logger.info(f"Starting superstep {self._iteration + 1}")
            yield WorkflowEvent.superstep_started(iteration=self._iteration + 1)

            committed = False
            try:
                # Wake on either a live event or iteration completion, including silent supersteps.
                iteration_task = asyncio.create_task(self._run_iteration())
                event_task: asyncio.Task[WorkflowEvent] | None = None
                try:
                    while not iteration_task.done():
                        event_task = asyncio.create_task(self._ctx.next_event())
                        done, _ = await asyncio.wait((iteration_task, event_task), return_when=asyncio.FIRST_COMPLETED)
                        if event_task in done:
                            yield event_task.result()
                finally:
                    # Cancellation and generator closure must not leave an event waiter or executor running.
                    tasks: list[asyncio.Task[Any]] = (
                        [iteration_task] if event_task is None else [iteration_task, event_task]
                    )
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Propagate errors from iteration, but first surface any pending events
                try:
                    await iteration_task
                except (Exception, asyncio.CancelledError):
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

                # Idle checkpoints must allow a later response run to select a different origin.
                if not await self._ctx.has_messages() and self._state.has(WORKFLOW_RESPONSE_SCOPE_KEY):
                    self._state.delete(WORKFLOW_RESPONSE_SCOPE_KEY)
                # Commit pending state changes at superstep boundary
                self._state.commit()
                committed = True
            finally:
                if not committed:
                    self._state.discard()

            # Create checkpoint after each superstep iteration
            await self.create_checkpoint_if_enabled()

            yield WorkflowEvent.superstep_completed(iteration=self._iteration)

            # Check for convergence: no more messages to process
            if not await self._ctx.has_messages():
                break

        logger.info(f"Workflow completed after {self._iteration} supersteps")

        if self._iteration >= self._max_iterations and await self._ctx.has_messages():
            raise WorkflowConvergenceException(f"Runner did not converge after {self._max_iterations} iterations.")

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
        - Wrapped replies wait for preceding messages only on compatible edge runners, then select and
          validate all targets before delivery. Unrelated edge runners remain concurrent.
        """
        from ._workflow_executor import SubWorkflowResponseMessage

        scopes = get_response_scopes(self._state)
        next_message: dict[str, int] = {}

        async def _deliver_messages(source_executor_id: str, source_messages: list[WorkflowMessage]) -> None:
            """Outer loop to concurrently deliver messages from all sources to their targets."""
            # Route all messages through normal workflow edges
            associated_edge_runners = self._edge_runner_map.get(source_executor_id, [])
            if not associated_edge_runners:
                # This is expected for terminal nodes (e.g., EndWorkflow, last action in workflow)
                logger.debug(f"No outgoing edges found for executor {source_executor_id}; dropping messages.")
                next_message[source_executor_id] = len(source_messages)
                return

            selections: dict[int, dict[EdgeRunner, asyncio.Future[tuple[bool, list[str]]]]] = {}
            validated: dict[int, asyncio.Event] = {}
            for index, message in enumerate(source_messages):
                if isinstance(message.data, SubWorkflowResponseMessage):
                    selections[index] = {
                        runner: asyncio.get_running_loop().create_future()
                        for runner in associated_edge_runners
                        if runner._has_compatible_target(message)  # pyright: ignore[reportPrivateUsage]
                    }
                    validated[index] = asyncio.Event()

            async def _deliver_messages_for_edge_runner(edge_runner: EdgeRunner) -> None:
                for index, message in enumerate(source_messages):
                    if index not in selections or edge_runner not in selections[index]:
                        await edge_runner.send_message(message, self._state, self._ctx)
                        continue
                    # Select routes after this edge's earlier handlers, not unrelated outgoing handlers.
                    delivery = await edge_runner._select_targets(message)  # pyright: ignore[reportPrivateUsage]
                    selections[index][edge_runner].set_result(delivery)
                    await validated[index].wait()
                    await edge_runner._send_selected_message(  # pyright: ignore[reportPrivateUsage]
                        message, self._state, self._ctx, delivery
                    )

            async def _validate_reply(index: int) -> None:
                targets: set[str] = set()
                for selection in selections[index].values():
                    _, target_ids = await selection
                    targets.update(target_ids)
                message = source_messages[index]
                if self._wrapped_response_validator is not None:
                    await self._wrapped_response_validator(
                        {target: [message.data.source_event] for target in targets}, scopes
                    )
                validated[index].set()
                # Independent paths may validate out of order; retain the earliest unvalidated reply on failure.
                while next_message[source_executor_id] < len(source_messages):
                    pending_index = next_message[source_executor_id]
                    if pending_index in validated and not validated[pending_index].is_set():
                        break
                    next_message[source_executor_id] += 1

            next_message[source_executor_id] = next(iter(selections), len(source_messages))
            await gather_cancelling_siblings_on_error(
                *(_validate_reply(index) for index in selections),
                *(_deliver_messages_for_edge_runner(runner) for runner in associated_edge_runners),
            )

        if self._queued_response_validator is not None:
            await self._queued_response_validator(scopes)
        message_batches = await self._ctx.drain_messages()
        try:
            await gather_cancelling_siblings_on_error(
                *(
                    _deliver_messages(source_executor_id, source_messages)
                    for source_executor_id, source_messages in message_batches.items()
                )
            )
        except BaseException:
            remaining = [
                message
                for source_id, messages in message_batches.items()
                for message in messages[next_message.get(source_id, 0) :]
            ]
            if remaining:
                # Siblings have stopped; retain undelivered replies ahead of newly emitted messages.
                queued = await self._ctx.drain_messages()
                for message in remaining:
                    await self._ctx.send_message(message)
                for messages in queued.values():
                    for message in messages:
                        await self._ctx.send_message(message)
            raise

    async def _get_queued_messages(self) -> Mapping[str, Sequence[WorkflowMessage]]:
        if isinstance(self._ctx, _SupportsQueuedMessages):
            return await self._ctx.get_queued_messages()
        # Legacy contexts expose their queues through non-persisting checkpoint snapshots.
        checkpoint = await self._ctx.build_checkpoint(
            self._workflow_name, self._graph_signature_hash, self._state, None, self._iteration
        )
        return checkpoint.messages

    async def _prepare_checkpoint_state(self) -> None:
        """Persist executor snapshots into committed shared state.

        This is used by checkpoint capture paths that need a complete, restorable
        state payload without necessarily writing to a checkpoint storage backend.
        """
        await self._save_executor_states()
        self._save_edge_runner_states()
        self._state.commit()

    async def create_checkpoint_if_enabled(self) -> None:
        """Create a checkpoint and save the checkpoint to the configured storage if one is configured.

        Note:
            1. This method has no effect if checkpointing is not enabled in the context.
        """
        if not self._ctx.has_checkpointing():
            return

        try:
            # Save executor states into committed state before creating the checkpoint.
            await self._prepare_checkpoint_state()

            checkpoint_id = await self._ctx.create_checkpoint(
                self._workflow_name,
                self._graph_signature_hash,
                self._state,
                self._previous_checkpoint_id,
                self._iteration,
            )

            logger.info(
                "Created checkpoint: %s with parent checkpoint at iteration %d: %s",
                checkpoint_id,
                self._iteration,
                self._previous_checkpoint_id,
            )
            self._previous_checkpoint_id = checkpoint_id
        except Exception as e:
            logger.warning(
                "Failed to create checkpoint at iteration %d: %s. "
                "Note that this does not fail the workflow run. "
                "The next successfully-created checkpoint will be parented to the last successful checkpoint: %s",
                self._iteration,
                e,
                self._previous_checkpoint_id,
            )

    async def restore_from_checkpoint(
        self,
        checkpoint_id: CheckpointID,
        checkpoint_storage: CheckpointStorage | None = None,
    ) -> None:
        """Restore the runner from a checkpoint.

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

            checkpoint = copy.deepcopy(checkpoint)
            await self._validate_checkpoint_tree(checkpoint)

            # Restore state. Clear first so import_state (which merges) does
            # not leak stale keys from a prior run on this Workflow instance.
            # This matters more now that Workflow.run() no longer wipes state
            # per call - the only reset point for shared state on a reused
            # instance is at restore time.
            self._state.clear()
            self._state.import_state(checkpoint.state)
            # Restore executor states using the restored state
            await self._restore_executor_states()
            # Restore edge runner states, resetting any left over from an interrupted run
            self._restore_edge_runner_states()
            # Apply the checkpoint to the context
            await self._ctx.apply_checkpoint(checkpoint)
            # Mark the runner as resumed
            self._mark_resumed(checkpoint)

            logger.info(f"Successfully restored workflow from checkpoint: {checkpoint_id}")
        except WorkflowCheckpointException:
            raise
        except Exception as e:
            logger.error(f"Failed to restore from checkpoint {checkpoint_id}: {e}")
            raise WorkflowCheckpointException(f"Failed to restore from checkpoint {checkpoint_id}") from e

    async def build_checkpoint(self) -> WorkflowCheckpoint:
        """Create a checkpoint object.

        Returns:
            A ``WorkflowCheckpoint``.
        """
        # Persist executor snapshots into committed shared state before exporting it.
        await self._prepare_checkpoint_state()
        return await self._ctx.build_checkpoint(
            self._workflow_name,
            self._graph_signature_hash,
            self._state,
            None,
            self._iteration,
        )

    async def restore_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        """Restore runner state from an in-memory ``WorkflowCheckpoint`` object.

        Unlike :meth:`restore_from_checkpoint`, this does not load from a storage
        backend; it applies a checkpoint the caller already holds - for example, a
        child workflow checkpoint embedded in a parent ``WorkflowExecutor``'s state.

        Restores shared state, executor snapshots, in-flight messages, and pending
        request_info events, then marks the runner as resumed.

        Args:
            checkpoint: The checkpoint whose state should be restored.

        Raises:
            WorkflowCheckpointException: If the checkpoint's graph signature does not
                match this runner's workflow, or if restoration otherwise fails.
        """
        try:
            checkpoint = copy.deepcopy(checkpoint)
            await self._validate_checkpoint_tree(checkpoint)

            # Clear first so import_state (which merges) does not leak stale keys from a
            # prior run on this Workflow instance.
            self._state.clear()
            self._state.import_state(checkpoint.state)
            await self._restore_executor_states()
            self._restore_edge_runner_states()
            await self._ctx.apply_checkpoint(checkpoint)
            self._mark_resumed(checkpoint)
        except WorkflowCheckpointException:
            raise
        except Exception as e:
            logger.error(f"Failed to restore from checkpoint {checkpoint.checkpoint_id}: {e}")
            raise WorkflowCheckpointException(f"Failed to restore from checkpoint {checkpoint.checkpoint_id}") from e

    async def _validate_checkpoint_tree(
        self, checkpoint: WorkflowCheckpoint, delegated_requests: Sequence[WorkflowEvent] = ()
    ) -> None:
        from ._const import WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY

        if self._graph_signature_hash != checkpoint.graph_signature_hash:
            raise WorkflowCheckpointException(
                "Workflow graph has changed since the checkpoint was created. "
                "Please rebuild the original workflow before resuming."
            )
        requests = [
            *_get_queued_response_info_events(checkpoint.messages),
            *(
                checkpoint.pending_request_info_events[request.request_id]
                for request in delegated_requests
                if request.request_id in checkpoint.pending_request_info_events
            ),
        ]
        if requests and self._response_batch_validator is not None:
            self._response_batch_validator(requests)
        parent_contexts = checkpoint.state.get(WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY, {})
        validate_request_contexts(
            parent_contexts,
            requests,
            previous_scopes=get_response_scopes(checkpoint.state),
            boundary_contexts=[
                (
                    checkpoint.state.get(request_context_state_key(executor_id), parent_contexts),
                    (),
                )
                for executor_id in self._executors
                if request_context_state_key(executor_id) in checkpoint.state
            ],
        )
        if EXECUTOR_STATE_KEY in checkpoint.state:
            delegated_by_executor: defaultdict[str, list[WorkflowEvent]] = defaultdict(list)
            for request in requests:
                delegated_by_executor[request.source_executor_id].append(request)
            for _, executor, state in self._get_executor_states(checkpoint.state[EXECUTOR_STATE_KEY]):
                await executor._validate_checkpoint_restore(  # pyright: ignore[reportPrivateUsage]
                    state, delegated_by_executor[executor.id]
                )

    async def _save_executor_states(self) -> None:
        """Populate executor state by calling checkpoint hooks on executors."""
        for exec_id, executor in self._executors.items():
            # Try the updated behavior only if backward compatibility did not yield state
            try:
                state_dict = await executor.on_checkpoint_save()
                # Validate at save time so restore cannot fail later on a non-dict payload (#8183).
                if not isinstance(state_dict, dict) or not all(isinstance(k, str) for k in state_dict):
                    raise WorkflowCheckpointException(
                        f"Executor state for {exec_id} is not a dict[str, Any]. Unable to save."
                    )
                await self._set_executor_state(exec_id, state_dict)
            except WorkflowCheckpointException:
                raise
            except Exception as ex:  # pragma: no cover
                raise WorkflowCheckpointException(f"Executor {exec_id} on_checkpoint_save failed") from ex

    async def _restore_executor_states(self) -> None:
        """Restore executor state by calling restore hooks on executors."""
        if not self._state.has(EXECUTOR_STATE_KEY):
            return

        for executor_id, executor, state in self._get_executor_states(self._state.get(EXECUTOR_STATE_KEY)):
            try:
                await executor.on_checkpoint_restore(state)
            except Exception as ex:  # pragma: no cover - defensive
                raise WorkflowCheckpointException(f"Executor {executor_id} on_checkpoint_restore failed") from ex

    def _get_executor_states(self, executor_states: Any) -> list[tuple[str, Executor, dict[str, Any]]]:
        if not isinstance(executor_states, dict):
            raise WorkflowCheckpointException("Executor states in shared state is not a dictionary. Unable to restore.")

        snapshots: list[tuple[str, Executor, dict[str, Any]]] = []
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
            snapshots.append((executor_id, executor, cast(dict[str, Any], state)))
        return snapshots

    def _save_edge_runner_states(self) -> None:
        """Store edge runner delivery state, such as partially filled fan-in buffers, in state.

        A fan-in buffers messages until every source has produced one, and the runner context has
        already drained those messages, so a checkpoint that omits them loses them on restore.
        """
        edge_states: dict[str, dict[str, Any]] = {}
        for key, runner in zip(self._edge_runner_state_keys, self._edge_runners, strict=True):
            snapshot = runner.snapshot_state()
            if snapshot is not None:
                edge_states[key] = snapshot

        if edge_states:
            self._state.set(EDGE_STATE_KEY, edge_states)
        elif self._state.has(EDGE_STATE_KEY):
            self._state.delete(EDGE_STATE_KEY)

    def _restore_edge_runner_states(self) -> None:
        """Reset every edge runner and reapply the delivery state held by the restored checkpoint.

        Every runner is reset, including runners the checkpoint has no entry for, so that state
        left behind by an interrupted run cannot survive into the restored run.
        """
        stored: Any = self._state.get(EDGE_STATE_KEY, {})
        if not isinstance(stored, dict):
            raise WorkflowCheckpointException("Edge states in shared state is not a dictionary. Unable to restore.")
        edge_states = cast(dict[Any, Any], stored)

        for key, runner in zip(self._edge_runner_state_keys, self._edge_runners, strict=True):
            state: Any = edge_states.get(key)
            if state is not None and not isinstance(state, dict):
                raise WorkflowCheckpointException(f"Edge state for {key} is not a dictionary. Unable to restore.")
            runner.restore_state(cast("dict[str, Any] | None", state))

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

    def _mark_resumed(self, checkpoint: WorkflowCheckpoint) -> None:
        """Restore per-run checkpoint bookkeeping from a resumed checkpoint.

        Sets the iteration counter and previous-checkpoint pointer so that
        checkpoints created after the resume continue the restored lineage.
        """
        self._iteration = checkpoint.iteration_count
        self._previous_checkpoint_id = checkpoint.checkpoint_id

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


if TYPE_CHECKING:
    Runner = RunnerImpl


def __getattr__(name: str) -> Any:
    """Lazily expose deprecated module-level public names."""
    if name == "Runner":
        warn_runner_deprecated()
        return RunnerImpl
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
