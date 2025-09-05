# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


async def retry(
    func: Callable[[], Awaitable[Any]],
    retries: int = 3,
    reset: Callable[[], None] | None = None,
    name: str | None = None,
) -> None:
    """Retry function with reset capability and proper logging.

    Args:
        func: The function to retry.
        retries: Number of retries.
        reset: Function to reset the state of any variables used in the function.
        name: Optional name for logging purposes.
    """
    func_name = name or func.__module__
    logger.info(f"Running {retries} retries with func: {func_name}")

    for i in range(retries):
        logger.info(f"   Try {i + 1} for {func_name}")
        try:
            if reset:
                reset()
            await func()
            return
        except Exception as e:
            logger.warning(f"   On try {i + 1} got this error: {e}")
            if i == retries - 1:  # Last retry
                raise

            # Binary exponential backoff like Semantic Kernel
            backoff = 2**i
            logger.info(f"   Sleeping for {backoff} seconds before retrying")
            await asyncio.sleep(backoff)
