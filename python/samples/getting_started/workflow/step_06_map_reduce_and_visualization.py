# Copyright (c) Microsoft. All rights reserved.

import ast
import asyncio
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import aiofiles
from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowViz,
    handler,
)

"""
The following sample demonstrates a basic map reduce workflow that
processes a large text file by splitting it into smaller chunks,
mapping each word to a count, shuffling the results, and reducing them
to a final count per word.

Intermediate results are stored in a temporary directory, and the
final results are written to a file in the same directory.

This sample also shows how you can visualize a workflow using `WorkflowViz`.
"""

# Define the temporary directory for storing intermediate results
DIR = os.path.dirname(__file__)
TEMP_DIR = os.path.join(DIR, "tmp")
# Ensure the temporary directory exists
os.makedirs(TEMP_DIR, exist_ok=True)

# Define a key for the shared state to store the data to be processed
SHARED_STATE_DATA_KEY = "data_to_be_processed"


class SplitCompleted:
    """A class to signal the completion of the Split executor."""

    ...


class Split(Executor):
    """An executor that splits data into smaller chunks based on the number of nodes available."""

    def __init__(self, map_executor_ids: list[str], id: str | None = None):
        """Initialize the executor with the number of nodes."""
        super().__init__(id)
        self._map_executor_ids = map_executor_ids

    @handler
    async def split(self, data: str, ctx: WorkflowContext[SplitCompleted]) -> None:
        """Execute the task by splitting the data into chunks.

        Args:
            data: A string containing the text to be processed.
            ctx: The execution context containing the shared state and other information.
        """
        # Process data into a list of words and remove empty lines/words.
        word_list = self._preprocess(data)

        # Store the data to be processed state for later use.
        await ctx.set_shared_state(SHARED_STATE_DATA_KEY, word_list)

        # Split the word_list into chunks that are represented by the start and end indices.
        # The start and end indices tuples will be stored in the shared state.
        map_executor_count = len(self._map_executor_ids)
        chunk_size = len(word_list) // map_executor_count  # Assuming map_executor_count is not 0.

        async def _process_chunk(i: int) -> None:
            """Process each chunk and send a message to the executor."""
            start_index = i * chunk_size
            end_index = start_index + chunk_size if i < map_executor_count - 1 else len(word_list)

            # The start and end indices are stored in the shared state for the MapExecutor.
            # This allows the MapExecutor to know which part of the data it should process.
            await ctx.set_shared_state(self._map_executor_ids[i], (start_index, end_index))
            await ctx.send_message(SplitCompleted(), self._map_executor_ids[i])

        tasks = [asyncio.create_task(_process_chunk(i)) for i in range(map_executor_count)]
        await asyncio.gather(*tasks)

    def _preprocess(self, data: str) -> list[str]:
        """Preprocess the input data and return a list of words.

        Args:
            data: The input data to be processed.

        Returns:
            A list of words extracted from the input data.
        """
        line_list = [line.strip() for line in data.splitlines() if line.strip()]
        return [word for line in line_list for word in line.split() if word]


@dataclass
class MapCompleted:
    """A data class to hold the completed state of the MapExecutor."""

    file_path: str


class Map(Executor):
    """An executor that applies a function to each item in the data and save the result to a file."""

    @handler
    async def map(self, _: SplitCompleted, ctx: WorkflowContext[MapCompleted]) -> None:
        """Execute the task by applying a function to each item and same result to a file.

        Args:
            data: An instance of SplitCompleted signaling the map step can be started.
            ctx: The execution context containing the shared state and other information.
        """
        # Retrieve the data to be processed from the shared state.
        data_to_be_processed: list[str] = await ctx.get_shared_state(SHARED_STATE_DATA_KEY)
        chunk_start, chunk_end = await ctx.get_shared_state(self.id)

        results = [(item, 1) for item in data_to_be_processed[chunk_start:chunk_end]]

        file_path = os.path.join(TEMP_DIR, f"map_results_{self.id}.txt")
        async with aiofiles.open(file_path, "w") as f:
            await f.writelines([f"{item}: {count}\n" for item, count in results])

        await ctx.send_message(MapCompleted(file_path))


@dataclass
class ShuffleCompleted:
    """A data class to hold the completed state of the ShuffleExecutor."""

    file_path: str
    reducer_id: str


class Shuffle(Executor):
    """An executor that redistributes results from the map step to the reduce step."""

    def __init__(self, reducer_ids: list[str], id: str | None = None):
        """Initialize the executor with the number of nodes."""
        super().__init__(id)
        self._reducer_ids = reducer_ids

    @handler
    async def shuffle(self, data: list[MapCompleted], ctx: WorkflowContext[ShuffleCompleted]) -> None:
        """Execute the task by aggregating the results.

        Args:
            data: A list of MapCompleted instances containing the file paths of the map results.
            ctx: The execution context containing the shared state and other information.
        """
        chunks = await self._preprocess(data)

        async def _process_chunk(chunk: list[tuple[str, list[int]]], index: int) -> None:
            """Process each chunk and save it to a file."""
            file_path = os.path.join(TEMP_DIR, f"shuffle_results_{index}.txt")
            async with aiofiles.open(file_path, "w") as f:
                await f.writelines([f"{key}: {value}\n" for key, value in chunk])
            await ctx.send_message(ShuffleCompleted(file_path, self._reducer_ids[index]))

        tasks = [asyncio.create_task(_process_chunk(chunk, i)) for i, chunk in enumerate(chunks)]
        await asyncio.gather(*tasks)

    async def _preprocess(self, data: list[MapCompleted]) -> list[list[tuple[str, list[int]]]]:
        """Preprocess the input data and return a list of data to be processed by the reduce executors.

        Args:
            data: A list of MapCompleted instances containing the file paths of the map results.

        Returns:
            A list of lists, where each inner list contains tuples of (key, value) pairs to be processed
            by the reduce executors.
        """
        map_results: list[tuple[str, int]] = []
        for result in data:
            async with aiofiles.open(result.file_path, "r") as f:
                map_results.extend([
                    (line.strip().split(": ")[0], int(line.strip().split(": ")[1])) for line in await f.readlines()
                ])

        # Group values by the first element
        intermediate_results: defaultdict[str, list[int]] = defaultdict(list[int])
        for item in map_results:
            key = item[0]
            value = item[1]
            intermediate_results[key].append(value)

        # Convert defaultdict to a list
        aggregated_results = [(key, values) for key, values in intermediate_results.items()]

        # Sort by the first element
        aggregated_results.sort(key=lambda x: x[0])

        # Split the intermediate results into chunks for the reduce executors
        reduce_executor_count = len(self._reducer_ids)
        chunk_size = len(aggregated_results) // reduce_executor_count
        remaining = len(aggregated_results) % reduce_executor_count

        chunks = [
            aggregated_results[i : i + chunk_size] for i in range(0, len(aggregated_results) - remaining, chunk_size)
        ]
        # Append the remaining items to the last chunk
        if remaining > 0:
            chunks[-1].extend(aggregated_results[-remaining:])

        return chunks


@dataclass
class ReduceCompleted:
    """A data class to hold the completed state of the ReduceExecutor."""

    file_path: str


class Reduce(Executor):
    """An executor that reduces the results from the ShuffleExecutor."""

    @handler
    async def _execute(self, data: ShuffleCompleted, ctx: WorkflowContext[ReduceCompleted]) -> None:
        """Execute the task by reducing the results.

        Args:
            data: An instance of ShuffleCompleted containing the file path of the shuffle results.
            ctx: The execution context containing the shared state and other information.
        """
        if data.reducer_id != self.id:
            # If the reducer ID does not match, skip processing.
            return

        # Read the intermediate results from the file
        async with aiofiles.open(data.file_path, "r") as f:
            lines = await f.readlines()

        # Aggregate the results
        reduced_results: dict[str, int] = defaultdict(int)
        for line in lines:
            key, value = line.split(": ")
            reduced_results[key] = sum(ast.literal_eval(value))

        # Write the reduced results to a file
        file_path = os.path.join(TEMP_DIR, f"reduced_results_{self.id}.txt")
        async with aiofiles.open(file_path, "w") as f:
            await f.writelines([f"{key}: {value}\n" for key, value in reduced_results.items()])

        await ctx.send_message(ReduceCompleted(file_path))


class CompletionExecutor(Executor):
    """An executor that completes the workflow by aggregating the results from the ReduceExecutors."""

    @handler
    async def complete(self, data: list[ReduceCompleted], ctx: WorkflowContext[Any]) -> None:
        """Execute the task by aggregating the results.

        Args:
            data: A list of ReduceCompleted instances containing the file paths of the reduced results.
            ctx: The execution context containing the shared state and other information.
        """
        await ctx.add_event(WorkflowCompletedEvent(data=[result.file_path for result in data]))


async def main():
    """Main function to run the workflow."""
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

    # Step 2: Build the workflow.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(split_operation)
        .add_fan_out_edges(split_operation, map_operations)
        .add_fan_in_edges(map_operations, shuffle_operation)
        .add_fan_out_edges(shuffle_operation, reduce_operations)
        .add_fan_in_edges(reduce_operations, completion_executor)
        .build()
    )

    # Step 2.5: Visualize the workflow (optional)
    print("🎨 Generating workflow visualization...")
    viz = WorkflowViz(workflow)
    # Print out the mermaid string.
    print("🧜 Mermaid string: \n=======")
    print(viz.to_mermaid())
    print("=======")
    # Print out the DiGraph string.
    print("📊 DiGraph string: \n=======")
    print(viz.to_digraph())
    print("=======")
    try:
        # Export the DiGraph visualization as SVG.
        svg_file = viz.export(format="svg")
        print(f"🖼️  SVG file saved to: {svg_file}")
    except ImportError:
        print("💡 Tip: Install 'viz' extra to export workflow visualization: pip install agent-framework-workflow[viz]")

    # Step 3: Open the text file and read its content.
    async with aiofiles.open(os.path.join(DIR, "resources", "long_text.txt"), "r") as f:
        raw_text = await f.read()

    # Step 4: Run the workflow with the raw text as input.
    completion_event = None
    async for event in workflow.run_streaming(raw_text):
        print(f"Event: {event}")
        if isinstance(event, WorkflowCompletedEvent):
            completion_event = event

    if completion_event:
        print(f"Completion Event: {completion_event}")


if __name__ == "__main__":
    asyncio.run(main())
