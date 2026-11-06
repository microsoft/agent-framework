# Copyright (c) Microsoft. All rights reserved.

"""Deterministic request barriers for MCP HTTP concurrency tests."""

import asyncio
import json

import httpx2 as httpx


class MCPHTTPBarrier:
    """Hold selected HTTP requests until a test explicitly releases their responses."""

    def __init__(self, *methods: str) -> None:
        self.methods = set(methods)
        self.arrivals: asyncio.Queue[httpx.Request] = asyncio.Queue()
        self.release = asyncio.Event()

    async def before_request(self, request: httpx.Request) -> None:
        if request.method == "POST" and json.loads(request.content).get("method") in self.methods:
            self.arrivals.put_nowait(request)
            await self.release.wait()

    async def next_request(self) -> httpx.Request:
        return await asyncio.wait_for(self.arrivals.get(), timeout=5)
