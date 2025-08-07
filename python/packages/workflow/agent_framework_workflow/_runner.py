# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterable

from ._edge import Edge
from ._events import WorkflowEvent
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 100


class Runner:
    """A class to run a workflow in Pregel supersteps."""

    def __init__(
        self,
        edges: list[Edge],
        shared_state: SharedState,
        ctx: RunnerContext,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> None:
        """Initialize the runner with edges, shared state, and context.

        Args:
            edges: The edges of the workflow.
            shared_state: The shared state for the workflow.
            ctx: The runner context for the workflow.
            max_iterations: The maximum number of iterations to run.
        """
        self._edge_map = self._parse_edges(edges)
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
