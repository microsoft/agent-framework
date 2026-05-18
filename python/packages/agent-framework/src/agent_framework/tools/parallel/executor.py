import asyncio
from typing import List, Any, Callable

class ParallelToolExecutor:
    """
    Executor for parallel tool calls in agentic workflows.
    Significantly reduces latency for multi-tool operations.
    """
    def __init__(self, max_concurrency: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_parallel(self, tool_calls: List[Callable[[], Any]]) -> List[Any]:
        async def _run_tool(call):
            async with self.semaphore:
                return await asyncio.to_thread(call)
        
        return await asyncio.gather(*[_run_tool(call) for call in tool_calls])
