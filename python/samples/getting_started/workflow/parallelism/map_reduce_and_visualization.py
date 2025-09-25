# Copyright (c) Microsoft. All rights reserved.

import ast
import asyncio
import os
from collections import defaultdict
from dataclasses import dataclass

import aiofiles
from typing_extensions import Never

from agent_framework import (
    Executor,  # Base class for custom workflow steps
    WorkflowBuilder,  # Fluent builder for executors and edges
    WorkflowContext,  # Per run context with shared state and messaging
    WorkflowOutputEvent,  # Event emitted when workflow yields output
    WorkflowViz,  # Utility to visualize a workflow graph
    handler,  # Decorator to expose an Executor method as a step
)

"""
Sample: Map reduce word count with fan out and fan in over file backed intermediate results

The workflow splits a large text into chunks, maps words to counts in parallel,
shuffles intermediate pairs to reducers, then reduces to per word totals.
It also demonstrates WorkflowViz for graph visualization.

Purpose:
Show how to:
- Partition input once and coordinate parallel mappers with shared state.
- Implement map, shuffle, and reduce executors that pass file paths instead of large payloads.
- Use fan out and fan in edges to express parallelism and joins.
- Persist intermediate results to disk to bound memory usage for large inputs.
- Visualize the workflow graph using WorkflowViz and export to SVG with the optional viz extra.

Prerequisites:
- Familiarity with WorkflowBuilder, executors, fan out and fan in edges, events, and streaming runs.
- aiofiles installed for async file I/O.
- Write access to a tmp directory next to this script.
- A source text at resources/long_text.txt.
- Optional for SVG export: install the viz extra for agent framework workflow.
"""

# Define the temporary directory for storing intermediate results
DIR = os.path.dirname(__file__)
TEMP_DIR = os.path.join(DIR, "tmp")
# Ensure the temporary directory exists
os.makedirs(TEMP_DIR, exist_ok=True)

# Define a key for the shared state to store the data to be processed
SHARED_STATE_DATA_KEY = "data_to_be_processed"


class SplitCompleted:
    """Marker type published when splitting finishes. Triggers map executors."""

    ...


class Split(Executor):
    """Splits data into roughly equal chunks based on the number of mapper nodes."""

    def __init__(self, map_executor_ids: list[str], id: str | None = None):
        """Store mapper ids so we can assign non overlapping ranges per mapper."""
        super().__init__(id=id or "split")
        self._map_executor_ids = map_executor_ids

    @handler
    async def split(self, data: str, ctx: WorkflowContext[SplitCompleted]) -> None:
        """Tokenize input and assign contiguous index ranges to each mapper via shared state.

        Args:
            data: The raw text to process.
            ctx: Workflow context to persist shared state and send messages.
        """
        # Process data into a list of words and remove empty lines or words.
        word_list = self._preprocess(data)

        # Store tokenized words once so all mappers can read by index.
        await ctx.set_shared_state(SHARED_STATE_DATA_KEY, word_list)

        # Divide indices into contiguous slices for each mapper.
        map_executor_count = len(self._map_executor_ids)
        chunk_size = len(word_list) // map_executor_count  # Assumes count > 0.

        async def _process_chunk(i: int) -> None:
            """Assign the slice for mapper i, then signal that splitting is done."""
            start_index = i * chunk_size
            end_index = start_index + chunk_size if i < map_executor_count - 1 else len(word_list)

            # The mapper reads its slice from shared state keyed by its own executor id.
            await ctx.set_shared_state(self._map_executor_ids[i], (start_index, end_index))
            await ctx.send_message(SplitCompleted(), self._map_executor_ids[i])

        tasks = [asyncio.create_task(_process_chunk(i)) for i in range(map_executor_count)]
        await asyncio.gather(*tasks)

    def _preprocess(self, data: str) -> list[str]:
        """Normalize lines and split on whitespace. Return a flat list of tokens."""
        line_list = [line.strip() for line in data.splitlines() if line.strip()]
        return [word for line in line_list for word in line.split() if word]


@dataclass
class MapCompleted:
    """Signal that a mapper wrote its intermediate pairs to file."""

    file_path: str


class Map(Executor):
    """Maps each token to a count of 1 and writes pairs to a per mapper file."""

    @handler
    async def map(self, _: SplitCompleted, ctx: WorkflowContext[MapCompleted]) -> None:
        """Read the assigned slice, emit (word, 1) pairs, and persist to disk.

        Args:
            _: SplitCompleted marker indicating maps can begin.
            ctx: Workflow context for shared state access and messaging.
        """
        # Retrieve tokens and our assigned slice.
        data_to_be_processed: list[str] = await ctx.get_shared_state(SHARED_STATE_DATA_KEY)
        chunk_start, chunk_end = await ctx.get_shared_state(self.id)

        results = [(item, 1) for item in data_to_be_processed[chunk_start:chunk_end]]

        # Write this mapper's results as simple text lines for easy debugging.
        file_path = os.path.join(TEMP_DIR, f"map_results_{self.id}.txt")
        async with aiofiles.open(file_path, "w") as f:
            await f.writelines([f"{item}: {count}\n" for item, count in results])

        await ctx.send_message(MapCompleted(file_path))


@dataclass
class ShuffleCompleted:
    """Signal that a shuffle partition file is ready for a specific reducer."""

    file_path: str
    reducer_id: str


class Shuffle(Executor):
    """Groups intermediate pairs by key and partitions them across reducers."""

    def __init__(self, reducer_ids: list[str], id: str | None = None):
        """Remember reducer ids so we can partition work deterministically."""
        super().__init__(id=id or "shuffle")
        self._reducer_ids = reducer_ids

    @handler
    async def shuffle(self, data: list[MapCompleted], ctx: WorkflowContext[ShuffleCompleted]) -> None:
        """Aggregate mapper outputs and write one partition file per reducer.

        Args:
            data: MapCompleted records with file paths for each mapper output.
            ctx: Workflow context to emit per reducer ShuffleCompleted messages.
        """
        chunks = await self._preprocess(data)

        async def _process_chunk(chunk: list[tuple[str, list[int]]], index: int) -> None:
            """Write one grouped partition for reducer index and notify that reducer."""
            file_path = os.path.join(TEMP_DIR, f"shuffle_results_{index}.txt")
            async with aiofiles.open(file_path, "w") as f:
                await f.writelines([f"{key}: {value}\n" for key, value in chunk])
            await ctx.send_message(ShuffleCompleted(file_path, self._reducer_ids[index]))

        tasks = [asyncio.create_task(_process_chunk(chunk, i)) for i, chunk in enumerate(chunks)]
        await asyncio.gather(*tasks)

    async def _preprocess(self, data: list[MapCompleted]) -> list[list[tuple[str, list[int]]]]:
        """Load all mapper files, group by key, sort keys, and partition for reducers.

        Returns:
            List of partitions. Each partition is a list of (key, [1, 1, ...]) tuples.
        """
        # Load all intermediate pairs.
        map_results: list[tuple[str, int]] = []
        for result in data:
            async with aiofiles.open(result.file_path, "r") as f:
                map_results.extend([
                    (line.strip().split(": ")[0], int(line.strip().split(": ")[1])) for line in await f.readlines()
                ])

        # Group values by token.
        intermediate_results: defaultdict[str, list[int]] = defaultdict(list[int])
        for key, value in map_results:
            intermediate_results[key].append(value)

        # Deterministic ordering helps with debugging and test stability.
        aggregated_results = [(key, values) for key, values in intermediate_results.items()]
        aggregated_results.sort(key=lambda x: x[0])

        # Partition keys across reducers as evenly as possible.
        reduce_executor_count = len(self._reducer_ids)
        chunk_size = len(aggregated_results) // reduce_executor_count
        remaining = len(aggregated_results) % reduce_executor_count

        chunks = [
            aggregated_results[i : i + chunk_size] for i in range(0, len(aggregated_results) - remaining, chunk_size)
        ]
        if remaining > 0:
            chunks[-1].extend(aggregated_results[-remaining:])

        return chunks


@dataclass
class ReduceCompleted:
    """Signal that a reducer wrote final counts for its partition."""

    file_path: str


class Reduce(Executor):
    """Sums grouped counts per key for its assigned partition."""

    @handler
    async def _execute(self, data: ShuffleCompleted, ctx: WorkflowContext[ReduceCompleted]) -> None:
        """Read one shuffle partition and reduce it to totals.

        Args:
            data: ShuffleCompleted with the partition file path and target reducer id.
            ctx: Workflow context used to emit ReduceCompleted with our output file path.
        """
        if data.reducer_id != self.id:
            # This partition belongs to a different reducer. Skip.
            return

        # Read grouped values from the shuffle output.
        async with aiofiles.open(data.file_path, "r") as f:
            lines = await f.readlines()

        # Sum values per key. Values are serialized Python lists like [1, 1, ...].
        reduced_results: dict[str, int] = defaultdict(int)
        for line in lines:
            key, value = line.split(": ")
            reduced_results[key] = sum(ast.literal_eval(value))

        # Persist our partition totals.
        file_path = os.path.join(TEMP_DIR, f"reduced_results_{self.id}.txt")
        async with aiofiles.open(file_path, "w") as f:
            await f.writelines([f"{key}: {value}\n" for key, value in reduced_results.items()])

        await ctx.send_message(ReduceCompleted(file_path))


class CompletionExecutor(Executor):
    """Joins all reducer outputs and yields the final output."""

    @handler
    async def complete(self, data: list[ReduceCompleted], ctx: WorkflowContext[Never, list[str]]) -> None:
        """Collect reducer output file paths and yield final output."""
        await ctx.yield_output([result.file_path for result in data])


async def main():
    """Construct the map reduce workflow, visualize it, then run it over a sample file."""
    # Step 1: Create the executors.
    map_operations = [Map(id=f"map_executor_{i}") for i in range(3)]
    split_operation = Split(
        [map_operation.id for map_operation in map_operations],
        id="split_data_executor",
    )
    reduce_operations = [Reduce(id=f"reduce_executor_{i}") for i in range(4)]
    shuffle_operation = Shuffle(
        [reduce_operation.id for reduce_operation in reduce_operations],
        id="shuffle_executor",
    )
    completion_executor = CompletionExecutor(id="completion_executor")

    # Step 2: Build the workflow graph using fan out and fan in edges.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(split_operation)
        .add_fan_out_edges(split_operation, map_operations)  # Split -> many mappers
        .add_fan_in_edges(map_operations, shuffle_operation)  # All mappers -> shuffle
        .add_fan_out_edges(shuffle_operation, reduce_operations)  # Shuffle -> many reducers
        .add_fan_in_edges(reduce_operations, completion_executor)  # All reducers -> completion
        .build()
    )

    # Step 2.5: Visualize the workflow (optional)
    print("Generating workflow visualization...")
    viz = WorkflowViz(workflow)
    # Print out the Mermaid string.
    print("Mermaid string: \n=======")
    print(viz.to_mermaid())
    print("=======")
    # Print out the DiGraph string.
    print("DiGraph string: \n=======")
    print(viz.to_digraph())
    print("=======")
    try:
        # Export the DiGraph visualization as SVG.
        svg_file = viz.export(format="svg")
        print(f"SVG file saved to: {svg_file}")
    except ImportError:
        print("Tip: Install 'viz' extra to export workflow visualization: pip install agent-framework[viz]")

    # Step 3: Open the text file and read its content.
    async with aiofiles.open(os.path.join(DIR, "resources", "long_text.txt"), "r") as f:
        raw_text = await f.read()

    # Step 4: Run the workflow with the raw text as input.
    async for event in workflow.run_stream(raw_text):
        print(f"Event: {event}")
        if isinstance(event, WorkflowOutputEvent):
            print(f"Final Output: {event.data}")


if __name__ == "__main__":
    asyncio.run(main())
