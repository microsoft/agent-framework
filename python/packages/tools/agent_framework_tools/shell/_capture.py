# Copyright (c) Microsoft. All rights reserved.

"""Bounded concurrent subprocess output capture."""

from __future__ import annotations

import asyncio
import logging
from typing import cast

from ._truncate import _OutputBuffer  # pyright: ignore[reportPrivateUsage] - shared shell capture

logger = logging.getLogger(__name__)

READ_CHUNK = 64 * 1024
_DRAIN_GRACE = 2.0


class _ProcessOutput:  # pyright: ignore[reportUnusedClass] - used by shell executors
    """Own pipe readers independently of a command's execution timeout."""

    def __init__(self, proc: asyncio.subprocess.Process, *, max_stdout_bytes: int, max_stderr_bytes: int) -> None:
        self._proc = proc
        self.stdout = _OutputBuffer(max_stdout_bytes)
        self.stderr = _OutputBuffer(max_stderr_bytes)
        self._readers = (
            asyncio.create_task(self._read(proc.stdout, self.stdout)),
            asyncio.create_task(self._read(proc.stderr, self.stderr)),
        )
        self._waiter = asyncio.create_task(proc.wait())
        self._completion = asyncio.create_task(self._wait())

    @staticmethod
    async def _read(stream: asyncio.StreamReader | None, output: _OutputBuffer) -> None:
        if stream is None:
            return
        while chunk := await stream.read(READ_CHUNK):
            output.append(chunk)

    async def _wait(self) -> None:
        await asyncio.gather(*self._readers, self._waiter)

    async def wait(self, timeout: float | None) -> None:
        await asyncio.wait_for(asyncio.shield(self._completion), timeout=timeout)

    async def finish(self) -> None:
        """Drain after termination without waiting forever for inherited pipes."""
        try:
            await self.wait(_DRAIN_GRACE)
        except asyncio.TimeoutError:
            logger.warning("subprocess output did not close after termination; stopping pipe readers")
        finally:
            await self.close()

    async def close(self) -> None:
        tasks = (*self._readers, self._waiter, self._completion)
        for task in tasks:
            if not task.done():
                task.cancel()
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Process has no public read-pipe close method. Use its transport
            # only to close owned output pipes, not to terminate the process.
            transport = cast(
                asyncio.SubprocessTransport,
                self._proc._transport,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType] - absent from typeshed
            )
            for fd in (1, 2):
                pipe = transport.get_pipe_transport(fd)
                if pipe is not None:
                    pipe.close()
