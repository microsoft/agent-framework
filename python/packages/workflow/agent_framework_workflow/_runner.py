# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterable, Sequence

from ._edge import EdgeGroup
from ._events import WorkflowEvent
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 100


class Runner:
    """A class to run a workflow in Pregel supersteps."""

    def __init__(
        self,
        edge_groups: Sequence[EdgeGroup],
        shared_state: SharedState,
        ctx: RunnerContext,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> None:
        """Initialize the runner with edges, shared state, and context.

        Args:
            edge_groups: The edge groups of the workflow.
            shared_state: The shared state for the workflow.
            ctx: The runner context for the workflow.
            max_iterations: The maximum number of iterations to run.
        """
        self._edge_group_map = self._parse_edge_groups(edge_groups)
        self._ctx = ctx
        self._iteration = 0
        self._max_iterations = max_iterations
        self._shared_state = shared_state
        self._is_running = False

    @property
    def context(self) -> RunnerContext:
        """Get the workflow context."""
        return self._ctx

    async def run_until_convergence(self) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow until no more messages are sent."""
        try:
            if self._is_running:
                raise RuntimeError("Runner is already running.")
            self._is_running = True
            while self._iteration < self._max_iterations:
                await self._run_iteration()
                self._iteration += 1

                if await self._ctx.has_events():
                    events = await self._ctx.drain_events()
                    for event in events:
                        yield event

                if not await self._ctx.has_messages():
                    break
            else:
                raise RuntimeError(f"Runner did not converge after {self._max_iterations} iterations.")
        finally:
            self._is_running = False
            self._iteration = 0

    async def _run_iteration(self):
        """Run a superstep of the workflow execution."""

        async def _deliver_messages(source_executor_id: str, messages: list[Message]) -> None:
            """Outer loop to concurrently deliver messages from all sources to their targets."""

            async def _deliver_message_inner(edge_group: EdgeGroup, message: Message) -> bool:
                """Inner loop to deliver a single message through an edge group."""
                return await edge_group.send_message(message, self._shared_state, self._ctx)

            associated_edge_groups = self._edge_group_map.get(source_executor_id, [])
            for message in messages:
                # Deliver a message through all edge groups associated with the source executor concurrently.
                tasks = [_deliver_message_inner(edge_group, message) for edge_group in associated_edge_groups]
                results = await asyncio.gather(*tasks)
                if not any(results):
                    logger.warning(
                        f"Message {message} could not be delivered. "
                        "This may be due to type incompatibility or no matching targets."
                    )

        messages = await self._ctx.drain_messages()
        tasks = [_deliver_messages(source_executor_id, messages) for source_executor_id, messages in messages.items()]
        await asyncio.gather(*tasks)

    def _parse_edge_groups(self, edge_groups: Sequence[EdgeGroup]) -> dict[str, list[EdgeGroup]]:
        """Parse the edge groups of the workflow into a mapping where each source executor ID maps to its edge groups.

        Args:
            edge_groups: A list of edge groups in the workflow.

        Returns:
            A dictionary mapping each source executor ID to a list of edge groups.
        """
        parsed: defaultdict[str, list[EdgeGroup]] = defaultdict(list)
        for group in edge_groups:
            for source_executor in group.source_executors():
                parsed[source_executor.id].append(group)

        return parsed
