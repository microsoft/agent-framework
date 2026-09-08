# Copyright (c) Microsoft. All rights reserved.

from typing import Any

import httpx


class AsyncClientUsingConfiguredTimeout:
    """Let an injected HTTPX client retain its configured per-phase timeouts."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    def build_request(self, *args: Any, **kwargs: Any) -> httpx.Request:
        kwargs["timeout"] = httpx.USE_CLIENT_DEFAULT
        return self.client.build_request(*args, **kwargs)

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        return await self.client.send(request, **kwargs)

    async def aclose(self) -> None:
        # The caller owns the injected client.
        return
