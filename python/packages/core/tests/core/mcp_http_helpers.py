# Copyright (c) Microsoft. All rights reserved.

"""Deterministic request barriers for MCP HTTP concurrency tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any

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


class MCPPaginatedHTTPServer:
    """Serve distinct catalogs and cursors for each initialized connection."""

    def __init__(self, *, reject_old_cursor: bool = False) -> None:
        self.generation = 0
        self.reject_old_cursor = reject_old_cursor
        self.pages: list[tuple[str, int, str | None]] = []

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(405)
        if request.method == "DELETE":
            return httpx.Response(200)
        body = json.loads(request.content)
        method = body.get("method")
        if "id" not in body:
            return httpx.Response(202)
        result: dict[str, Any] = {}
        headers: dict[str, str] = {}
        if method == "initialize":
            self.generation += 1
            headers["mcp-session-id"] = f"session-{self.generation}"
            result = {
                "protocolVersion": body["params"]["protocolVersion"],
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": "paginated-test", "version": "1"},
            }
        elif method in {"tools/list", "prompts/list"}:
            cursor = body.get("params", {}).get("cursor")
            self.pages.append((method, self.generation, cursor))
            if cursor == "old-cursor" and self.generation > 1 and self.reject_old_cursor:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "error": {"code": -32602, "message": "Cursor belongs to an old session"},
                    },
                )
            suffix = "tail" if cursor else "head"
            kind = "tool" if method == "tools/list" else "prompt"
            item: dict[str, Any] = {"name": f"session_{self.generation}_{kind}_{suffix}"}
            if kind == "tool":
                item.update(
                    inputSchema={"type": "object", "properties": {f"arg{self.generation}": {"type": "string"}}},
                    _meta={"catalog": self.generation},
                )
            else:
                item["arguments"] = [{"name": f"arg{self.generation}"}]
            result = {"tools" if kind == "tool" else "prompts": [item]}
            if cursor is None:
                result["nextCursor"] = "old-cursor" if self.generation == 1 else f"cursor-{self.generation}"
        elif method == "tools/call":
            result = {"content": [{"type": "text", "text": "ok"}]}
        return httpx.Response(
            200,
            headers=headers,
            json={"jsonrpc": "2.0", "id": body["id"], "result": result},
        )
