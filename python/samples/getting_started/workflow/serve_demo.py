# Copyright (c) Microsoft. All rights reserved.

"""Map-Reduce web UI demo.

This sample adapts step_06_map_reduce.py to the web UI server demo and inserts
random 1–2s delays in each executor to simulate work.
"""

import ast
import asyncio
import os
import random
from collections import defaultdict
from dataclasses import dataclass

import aiofiles
from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowViz,
    handler,
)

DIR = os.path.dirname(__file__)
TEMP_DIR = os.path.join(DIR, "tmp")
os.makedirs(TEMP_DIR, exist_ok=True)

SHARED_STATE_DATA_KEY = "data_to_be_processed"


class SplitCompleted:
    """Signal the completion of the Split executor."""

    ...


class Split(Executor):
    def __init__(self, map_executor_ids: list[str], id: str | None = None):
        super().__init__(id)
        self._map_executor_ids = map_executor_ids

    @handler(output_types=[SplitCompleted])
    async def split(self, data: str, ctx: WorkflowContext) -> None:
        # Simulate workload
        await asyncio.sleep(random.uniform(1, 2))

        word_list = self._preprocess(data)
        await ctx.set_shared_state(SHARED_STATE_DATA_KEY, word_list)

        map_executor_count = len(self._map_executor_ids)
        chunk_size = max(1, len(word_list) // map_executor_count) if map_executor_count else 1

        async def _process_chunk(i: int) -> None:
            await asyncio.sleep(random.uniform(1, 2))
            start_index = i * chunk_size
            end_index = start_index + chunk_size if i < map_executor_count - 1 else len(word_list)
            await ctx.set_shared_state(self._map_executor_ids[i], (start_index, end_index))
            await ctx.send_message(SplitCompleted(), self._map_executor_ids[i])

        tasks = [asyncio.create_task(_process_chunk(i)) for i in range(map_executor_count)]
        if tasks:
            await asyncio.gather(*tasks)

    def _preprocess(self, data: str) -> list[str]:
        line_list = [line.strip() for line in data.splitlines() if line.strip()]
        return [word for line in line_list for word in line.split() if word]


@dataclass
class MapCompleted:
    file_path: str


class Map(Executor):
    @handler(output_types=[MapCompleted])
    async def map(self, _: SplitCompleted, ctx: WorkflowContext) -> None:
        await asyncio.sleep(random.uniform(1, 2))
        data_to_be_processed: list[str] = await ctx.get_shared_state(SHARED_STATE_DATA_KEY)
        chunk_start, chunk_end = await ctx.get_shared_state(self.id)

        results = [(item, 1) for item in data_to_be_processed[chunk_start:chunk_end]]

        file_path = os.path.join(TEMP_DIR, f"map_results_{self.id}.txt")
        async with aiofiles.open(file_path, "w") as f:
            await f.writelines([f"{item}: {count}\n" for item, count in results])

        await ctx.send_message(MapCompleted(file_path))


@dataclass
class ShuffleCompleted:
    file_path: str
    reducer_id: str


class Shuffle(Executor):
    def __init__(self, reducer_ids: list[str], id: str | None = None):
        super().__init__(id)
        self._reducer_ids = reducer_ids

    @handler(output_types=[ShuffleCompleted])
    async def shuffle(self, data: list[MapCompleted], ctx: WorkflowContext) -> None:
        await asyncio.sleep(random.uniform(1, 2))
        chunks = await self._preprocess(data)

        async def _process_chunk(chunk: list[tuple[str, list[int]]], index: int) -> None:
            await asyncio.sleep(random.uniform(1, 2))
            file_path = os.path.join(TEMP_DIR, f"shuffle_results_{index}.txt")
            async with aiofiles.open(file_path, "w") as f:
                await f.writelines([f"{key}: {value}\n" for key, value in chunk])
            await ctx.send_message(ShuffleCompleted(file_path, self._reducer_ids[index]))

        tasks = [asyncio.create_task(_process_chunk(chunk, i)) for i, chunk in enumerate(chunks)]
        if tasks:
            await asyncio.gather(*tasks)

    async def _preprocess(self, data: list[MapCompleted]) -> list[list[tuple[str, list[int]]]]:
        map_results: list[tuple[str, int]] = []
        for result in data:
            async with aiofiles.open(result.file_path, "r") as f:
                map_results.extend([
                    (line.strip().split(": ")[0], int(line.strip().split(": ")[1])) for line in await f.readlines()
                ])

        intermediate_results: defaultdict[str, list[int]] = defaultdict(list[int])
        for item in map_results:
            key = item[0]
            value = item[1]
            intermediate_results[key].append(value)

        aggregated_results = [(key, values) for key, values in intermediate_results.items()]
        aggregated_results.sort(key=lambda x: x[0])

        reduce_executor_count = len(self._reducer_ids)
        if reduce_executor_count == 0:
            return []
        chunk_size = len(aggregated_results) // reduce_executor_count
        remaining = len(aggregated_results) % reduce_executor_count

        chunks = [
            aggregated_results[i : i + chunk_size] for i in range(0, len(aggregated_results) - remaining, chunk_size)
        ]
        if remaining > 0 and chunks:
            chunks[-1].extend(aggregated_results[-remaining:])

        return chunks


@dataclass
class ReduceCompleted:
    file_path: str


class Reduce(Executor):
    @handler(output_types=[ReduceCompleted])
    async def _execute(self, data: ShuffleCompleted, ctx: WorkflowContext) -> None:
        await asyncio.sleep(random.uniform(1, 2))
        if data.reducer_id != self.id:
            return

        async with aiofiles.open(data.file_path, "r") as f:
            lines = await f.readlines()

        reduced_results: dict[str, int] = defaultdict(int)
        for line in lines:
            key, value = line.split(": ")
            reduced_results[key] = sum(ast.literal_eval(value))

        file_path = os.path.join(TEMP_DIR, f"reduced_results_{self.id}.txt")
        async with aiofiles.open(file_path, "w") as f:
            await f.writelines([f"{key}: {value}\n" for key, value in reduced_results.items()])

        await ctx.send_message(ReduceCompleted(file_path))


class CompletionExecutor(Executor):
    @handler
    async def complete(self, data: list[ReduceCompleted], ctx: WorkflowContext) -> None:
        await asyncio.sleep(random.uniform(1, 2))
        await ctx.add_event(WorkflowCompletedEvent(data=[result.file_path for result in data]))


async def main():
    # Create executors
    map_operations = [Map(id=f"map_executor_{i}") for i in range(3)]
    split_operation = Split([m.id for m in map_operations], id="split_data_executor")
    reduce_operations = [Reduce(id=f"reduce_executor_{i}") for i in range(4)]
    shuffle_operation = Shuffle([r.id for r in reduce_operations], id="shuffle_executor")
    completion_executor = CompletionExecutor(id="completion_executor")

    # Build workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(split_operation)
        .add_fan_out_edges(split_operation, map_operations)
        .add_fan_in_edges(map_operations, shuffle_operation)
        .add_fan_out_edges(shuffle_operation, reduce_operations)
        .add_fan_in_edges(reduce_operations, completion_executor)
        .build()
    )

    viz = WorkflowViz(workflow)
    # Serve a minimal web UI on http://127.0.0.1:8765/
    await viz.serve(port=8765)


if __name__ == "__main__":
    asyncio.run(main())
