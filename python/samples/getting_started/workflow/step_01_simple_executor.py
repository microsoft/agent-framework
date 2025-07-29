# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys

from agent_framework.workflow import Executor, ExecutorContext

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


class SimpleExecutor(Executor[str]):
    """A simple executor that processes string messages."""

    @override
    async def _execute(self, data: str, ctx: ExecutorContext) -> str:
        """Execute the task by converting the input string to uppercase."""
        return data.upper()


async def main():
    """Main function to run the SimpleExecutor."""
    executor = SimpleExecutor()
    result = await executor.execute("hello world")
    print(result)  # Output: HELLO WORLD


if __name__ == "__main__":
    asyncio.run(main())
