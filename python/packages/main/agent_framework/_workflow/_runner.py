# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncGenerator, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._executor import RequestInfoExecutor

from ._edge import EdgeGroup
from ._edge_runner import EdgeRunner, create_edge_runner
from ._events import WorkflowEvent, WorkflowOutputEvent, _framework_event_origin
from ._executor import Executor
from ._runner_context import (
    _DATACLASS_MARKER,
    _PYDANTIC_MARKER,
    CheckpointState,
    Message,
    RunnerContext,
    _decode_checkpoint_value,
)
from ._shared_state import SharedState
from ._typing_utils import is_instance_of

logger = logging.getLogger(__name__)


class Runner:
    """A class to run a workflow in Pregel supersteps."""

    def __init__(
        self,
        edge_groups: Sequence[EdgeGroup],
        executors: dict[str, Executor],
        shared_state: SharedState,
        ctx: RunnerContext,
        max_iterations: int = 100,
        workflow_id: str | None = None,
    ) -> None:
        """Initialize the runner with edges, shared state, and context.

        Args:
            edge_groups: The edge groups of the workflow.
            executors: Map of executor IDs to executor instances.
            shared_state: The shared state for the workflow.
            ctx: The runner context for the workflow.
            max_iterations: The maximum number of iterations to run.
            workflow_id: The workflow ID for checkpointing.
        """
        self._executors = executors
        self._edge_runners = [create_edge_runner(group, executors) for group in edge_groups]
        self._edge_runner_map = self._parse_edge_runners(self._edge_runners)
        self._ctx = ctx
        self._iteration = 0
        self._max_iterations = max_iterations
        self._shared_state = shared_state
        self._workflow_id = workflow_id
        self._running = False
        self._resumed_from_checkpoint = False  # Track whether we resumed
        self.graph_signature_hash: str | None = None

        # Set workflow ID in context if provided
        if workflow_id:
            self._ctx.set_workflow_id(workflow_id)

    @property
    def context(self) -> RunnerContext:
        """Get the workflow context."""
        return self._ctx

    def mark_resumed(self, iteration: int | None = None, max_iterations: int | None = None) -> None:
        """Mark the runner as having resumed from a checkpoint.

        Optionally set the current iteration and max iterations.
        """
        self._resumed_from_checkpoint = True
        if iteration is not None:
            self._iteration = iteration
        if max_iterations is not None:
            self._max_iterations = max_iterations

    async def run_until_convergence(self) -> AsyncGenerator[WorkflowEvent, None]:
        """Run the workflow until no more messages are sent."""
        if self._running:
            raise RuntimeError("Runner is already running.")

        self._running = True
        try:
            # Emit any events already produced prior to entering loop
            if await self._ctx.has_events():
                logger.info("Yielding pre-loop events")
                for event in await self._ctx.drain_events():
                    yield event

            # Create first checkpoint if there are messages from initial execution
            if await self._ctx.has_messages() and self._ctx.has_checkpointing():
                if not self._resumed_from_checkpoint:
                    logger.info("Creating checkpoint after initial execution")
                    await self._create_checkpoint_if_enabled("after_initial_execution")
                else:
                    logger.info("Skipping 'after_initial_execution' checkpoint because we resumed from a checkpoint")

            # Initialize context with starting iteration state
            await self._update_context_with_shared_state()

            while self._iteration < self._max_iterations:
                logger.info(f"Starting superstep {self._iteration + 1}")

                # Run iteration concurrently with live event streaming: we poll
                # for new events while the iteration coroutine progresses.
                iteration_task = asyncio.create_task(self._run_iteration())
                while not iteration_task.done():
                    try:
                        # Wait briefly for any new event; timeout allows progress checks
                        event = await asyncio.wait_for(self._ctx.next_event(), timeout=0.05)
                        yield event
                    except asyncio.TimeoutError:
                        # Periodically continue to let iteration advance
                        continue

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

                # Update context with current iteration state immediately
                await self._update_context_with_shared_state()

                logger.info(f"Completed superstep {self._iteration}")

                # Create checkpoint after each superstep iteration
                await self._create_checkpoint_if_enabled(f"superstep_{self._iteration}")

                if not await self._ctx.has_messages():
                    break

            if self._iteration >= self._max_iterations and await self._ctx.has_messages():
                raise RuntimeError(f"Runner did not converge after {self._max_iterations} iterations.")

            logger.info(f"Workflow completed after {self._iteration} supersteps")
            self._iteration = 0
            self._resumed_from_checkpoint = False  # Reset resume flag for next run
        finally:
            self._running = False

    async def _run_iteration(self) -> None:
        async def _deliver_messages(source_executor_id: str, messages: list[Message]) -> None:
            """Outer loop to concurrently deliver messages from all sources to their targets."""

            # Special handling for SubWorkflowRequestInfo messages
            async def _deliver_sub_workflow_requests(messages: list[Message]) -> None:
                from ._executor import SubWorkflowRequestInfo

                # Handle SubWorkflowRequestInfo messages - only process those not already targeted
                sub_workflow_messages: list[Message] = []
                for msg in messages:
                    # Skip messages sent directly to RequestInfoExecutor - they are already forwarded
                    if self._is_message_to_request_info_executor(msg):
                        continue

                    if isinstance(msg.data, SubWorkflowRequestInfo):
                        sub_workflow_messages.append(msg)

                for message in sub_workflow_messages:
                    # message.data is guaranteed to be SubWorkflowRequestInfo via filtering above
                    sub_request = message.data  # type: ignore[assignment]

                    # Find executor that can intercept the wrapped type
                    interceptor_found = False
                    for executor in self._executors.values():
                        interceptors = getattr(executor, "_request_interceptors", [])
                        if interceptors and executor.id != message.source_id:
                            for registered_type in interceptors:  # type: ignore[assignment]
                                # Check type matching - handle both type and string cases
                                matched = False
                                if (
                                    isinstance(registered_type, type)
                                    and is_instance_of(sub_request.data, registered_type)
                                ) or (
                                    isinstance(registered_type, str)
                                    and hasattr(sub_request.data, "__class__")
                                    and sub_request.data.__class__.__name__ == registered_type
                                ):
                                    matched = True

                                if matched:
                                    # Send directly to the intercepting executor
                                    logger.info(
                                        f"Sending sub-workflow request of type '{sub_request.data.__class__.__name__}' "
                                        f"from sub-workflow '{sub_request.sub_workflow_id}' "
                                        f"to executor '{executor.id}' for interception."
                                    )
                                    await executor.execute(
                                        sub_request,
                                        [message.source_id],  # source_executor_ids
                                        self._shared_state,  # shared_state
                                        self._ctx,  # runner_context
                                        trace_contexts=[message.trace_context] if message.trace_context else None,
                                        source_span_ids=[message.source_span_id] if message.source_span_id else None,
                                    )
                                    interceptor_found = True
                                    break
                            if interceptor_found:
                                break

                    if not interceptor_found:
                        # No interceptor found - send directly to RequestInfoExecutor if available.

                        # Find the RequestInfoExecutor instance
                        request_info_executor = self._find_request_info_executor()

                        if request_info_executor:
                            logger.info(
                                f"Sending sub-workflow request of type '{sub_request.data.__class__.__name__}' "
                                f"from sub-workflow '{sub_request.sub_workflow_id}' to RequestInfoExecutor "
                                f"'{request_info_executor.id}'"
                            )
                            await request_info_executor.execute(
                                sub_request,
                                [message.source_id],  # source_executor_ids
                                self._shared_state,  # shared_state
                                self._ctx,  # runner_context
                                trace_contexts=[message.trace_context] if message.trace_context else None,
                                source_span_ids=[message.source_span_id] if message.source_span_id else None,
                            )
                        else:
                            logger.warning(
                                f"Sub-workflow request of type '{sub_request.data.__class__.__name__}' "
                                f"from sub-workflow '{sub_request.sub_workflow_id}' could not be handled: "
                                f"no RequestInfoExecutor found in the workflow. Add a RequestInfoExecutor "
                                f"to handle external requests or add an @intercepts_request handler."
                            )

            async def _deliver_message_inner(edge_runner: EdgeRunner, message: Message) -> bool:
                """Inner loop to deliver a single message through an edge runner."""
                return await edge_runner.send_message(message, self._shared_state, self._ctx)

            def _normalize_message_payload(message: Message) -> None:
                data = message.data
                if not isinstance(data, dict):
                    return
                if _PYDANTIC_MARKER not in data and _DATACLASS_MARKER not in data:
                    return
                try:
                    decoded = _decode_checkpoint_value(data)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("Failed to decode checkpoint payload during delivery: %s", exc)
                    return
                message.data = decoded

            # Handle SubWorkflowRequestInfo messages specially
            await _deliver_sub_workflow_requests(messages)

            # Filter out SubWorkflowRequestInfo messages from normal edge routing
            # since they were handled specially
            from ._executor import SubWorkflowRequestInfo

            non_sub_workflow_messages: list[Message] = []
            for msg in messages:
                # Keep messages sent directly to RequestInfoExecutor (forwarded messages)
                if self._is_message_to_request_info_executor(msg):
                    non_sub_workflow_messages.append(msg)
                    continue

                # Skip SubWorkflowRequestInfo messages (handled by special routing)
                if isinstance(msg.data, SubWorkflowRequestInfo):
                    continue

                non_sub_workflow_messages.append(msg)

            associated_edge_runners = self._edge_runner_map.get(source_executor_id, [])
            for message in non_sub_workflow_messages:
                _normalize_message_payload(message)
                # Deliver a message through all edge runners associated with the source executor concurrently.
                tasks = [_deliver_message_inner(edge_runner, message) for edge_runner in associated_edge_runners]
                if not tasks:
                    # No outgoing edges. If this is an AgentExecutorResponse, treat it as an
                    # intentional terminal emission and emit a WorkflowOutputEvent here.
                    # (Previously this relied on the executor to emit, but AgentExecutor only
                    # sends an AgentExecutorResponse message; centralized completion keeps the
                    # contract consistent with other executors.)
                    try:  # Local import to avoid circular dependencies at module import time.
                        from ._executor import AgentExecutorResponse  # type: ignore

                        if isinstance(message.data, AgentExecutorResponse):
                            final_messages = message.data.agent_run_response.messages
                            final_text = final_messages[-1].text if final_messages else "(no content)"
                            with _framework_event_origin():
                                # TODO(moonbox3): does user expect this event to contain the final text?
                                output_event = WorkflowOutputEvent(data=final_text, source_executor_id="<Runner>")
                            await self._ctx.add_event(output_event)
                            continue  # Terminal handled
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.debug("Suppressed exception during terminal message type check: %s", exc)
                    # Otherwise keep prior behavior (emit warning for unexpected undelivered message).
                    logger.warning(
                        f"Message {message} could not be delivered (no outgoing edges). "
                        "Add a downstream executor or remove the send if this is unexpected."
                    )
                    continue
                results = await asyncio.gather(*tasks)
                if not any(results):
                    # Outgoing edges exist but none accepted the message. If this is an
                    # AgentExecutorResponse, treat as natural terminal and emit completion.
                    try:
                        from ._executor import AgentExecutorResponse  # type: ignore

                        if isinstance(message.data, AgentExecutorResponse):
                            # Emit a single completion event with final text (best-effort extraction)
                            final_messages = message.data.agent_run_response.messages
                            final_text = final_messages[-1].text if final_messages else "(no content)"
                            with _framework_event_origin():
                                # TODO(moonbox3): does user expect this event to contain the final text?
                                output_event = WorkflowOutputEvent(data=final_text, source_executor_id="<Runner>")
                            await self._ctx.add_event(output_event)
                            continue
                    except Exception as exc:  # pragma: no cover
                        logger.debug("Terminal completion emission failed: %s", exc)
                    logger.warning(
                        f"Message {message} could not be delivered. "
                        "This may be due to type incompatibility or no matching targets."
                    )

        messages = await self._ctx.drain_messages()
        tasks = [_deliver_messages(source_executor_id, messages) for source_executor_id, messages in messages.items()]
        await asyncio.gather(*tasks)

    async def _create_checkpoint_if_enabled(self, checkpoint_type: str) -> str | None:
        """Create a checkpoint if checkpointing is enabled and attach a label and metadata."""
        if not self._ctx.has_checkpointing():
            return None

        try:
            # Auto-snapshot executor states
            await self._auto_snapshot_executor_states()
            await self._update_context_with_shared_state()
            checkpoint_category = "initial" if checkpoint_type == "after_initial_execution" else "superstep"
            metadata = {
                "superstep": self._iteration,
                "checkpoint_type": checkpoint_category,
            }
            if self.graph_signature_hash:
                metadata["graph_signature"] = self.graph_signature_hash
            checkpoint_id = await self._ctx.create_checkpoint(metadata=metadata)
            logger.info(f"Created {checkpoint_type} checkpoint: {checkpoint_id}")
            return checkpoint_id
        except Exception as e:
            logger.warning(f"Failed to create {checkpoint_type} checkpoint: {e}")
            return None

    async def _auto_snapshot_executor_states(self) -> None:
        """Populate executor state by calling snapshot hooks on executors if available.

        Convention:
          - If an executor defines an async or sync method `snapshot_state(self) -> dict`, use it.
          - Else if it has a plain attribute `state` that is a dict, use that.
        Only JSON-serializable dicts should be provided by executors.
        """
        for exec_id, executor in self._executors.items():
            state_dict: dict[str, Any] | None = None
            snapshot = getattr(executor, "snapshot_state", None)
            try:
                if callable(snapshot):
                    maybe = snapshot()
                    if asyncio.iscoroutine(maybe):  # type: ignore[arg-type]
                        maybe = await maybe  # type: ignore[assignment]
                    if isinstance(maybe, dict):
                        state_dict = maybe  # type: ignore[assignment]
                else:
                    state_attr = getattr(executor, "state", None)
                    if isinstance(state_attr, dict):
                        state_dict = state_attr  # type: ignore[assignment]
            except Exception as ex:  # pragma: no cover
                logger.debug(f"Executor {exec_id} snapshot_state failed: {ex}")
            if state_dict is not None:
                try:
                    await self._ctx.set_state(exec_id, state_dict)
                except Exception as ex:  # pragma: no cover
                    logger.debug(f"Failed to persist state for executor {exec_id}: {ex}")

    async def _update_context_with_shared_state(self) -> None:
        if not self._ctx.has_checkpointing():
            return

        try:
            current_state = await self._ctx.get_checkpoint_state()

            shared_state_data = {}
            async with self._shared_state.hold():
                if hasattr(self._shared_state, "_state"):
                    shared_state_data = dict(self._shared_state._state)  # type: ignore[attr-defined]

            current_state["shared_state"] = shared_state_data
            current_state["iteration_count"] = self._iteration
            current_state["max_iterations"] = self._max_iterations

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
        if not self._ctx.has_checkpointing():
            logger.warning("Context does not support checkpointing")
            return False

        try:
            checkpoint = await self._ctx.load_checkpoint(checkpoint_id)
            if not checkpoint:
                logger.error(f"Checkpoint {checkpoint_id} not found")
                return False

            graph_hash = getattr(self, "graph_signature_hash", None)
            checkpoint_hash = (checkpoint.metadata or {}).get("graph_signature")
            if graph_hash and checkpoint_hash and graph_hash != checkpoint_hash:
                raise ValueError(
                    "Workflow graph has changed since the checkpoint was created. "
                    "Please rebuild the original workflow before resuming."
                )
            if graph_hash and not checkpoint_hash:
                logger.warning(
                    "Checkpoint %s does not include graph signature metadata; skipping topology validation.",
                    checkpoint_id,
                )

            state: CheckpointState = {
                "messages": checkpoint.messages,
                "shared_state": checkpoint.shared_state,
                "executor_states": checkpoint.executor_states,
                "iteration_count": checkpoint.iteration_count,
                "max_iterations": checkpoint.max_iterations,
            }
            await self._ctx.set_checkpoint_state(state)
            if checkpoint.workflow_id:
                self._ctx.set_workflow_id(checkpoint.workflow_id)
            self._workflow_id = checkpoint.workflow_id

            await self._restore_shared_state_from_context()
            self.mark_resumed(
                iteration=checkpoint.iteration_count,
                max_iterations=checkpoint.max_iterations,
            )
            logger.info(f"Successfully restored workflow from checkpoint: {checkpoint_id}")
            return True
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to restore from checkpoint {checkpoint_id}: {e}")
            return False

    async def _restore_shared_state_from_context(self) -> None:
        if not self._ctx.has_checkpointing():
            return

        try:
            restored_state = await self._ctx.get_checkpoint_state()

            shared_state_data = restored_state.get("shared_state", {})
            if shared_state_data and hasattr(self._shared_state, "_state"):
                async with self._shared_state.hold():
                    self._shared_state._state.clear()  # type: ignore[attr-defined]
                    self._shared_state._state.update(shared_state_data)  # type: ignore[attr-defined]

            self._iteration = restored_state.get("iteration_count", 0)
            self._max_iterations = restored_state.get("max_iterations", self._max_iterations)

        except Exception as e:
            logger.warning(f"Failed to restore shared state from context: {e}")

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

    def _find_request_info_executor(self) -> "RequestInfoExecutor | None":
        """Find the RequestInfoExecutor instance in this workflow.

        Returns:
            The RequestInfoExecutor instance if found, None otherwise.
        """
        from ._executor import RequestInfoExecutor

        for executor in self._executors.values():
            if isinstance(executor, RequestInfoExecutor):
                return executor
        return None

    def _is_message_to_request_info_executor(self, msg: "Message") -> bool:
        """Check if message targets any RequestInfoExecutor in this workflow.

        Args:
            msg: The message to check.

        Returns:
            True if the message targets a RequestInfoExecutor, False otherwise.
        """
        from ._executor import RequestInfoExecutor

        if not msg.target_id:
            return False

        # Check all executors to see if target_id matches a RequestInfoExecutor
        for executor in self._executors.values():
            if executor.id == msg.target_id and isinstance(executor, RequestInfoExecutor):
                return True
        return False
