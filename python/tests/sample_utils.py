# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


async def retry(func: Callable[[], Awaitable[Any]], retries: int = 3, reset: Callable[[], None] | None = None) -> None:
    """Retry function with reset capability."""
    for i in range(retries):
        try:
            await func()
            return
        except Exception as e:
            if i == retries - 1:
                raise e

            # Using print for test debugging - acceptable in test utilities
            print(f"Attempt {i + 1} failed: {e}")  # noqa: T201
            if reset:
                reset()
            await asyncio.sleep(1)
