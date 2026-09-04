# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
from collections.abc import MutableMapping
from enum import IntEnum
from typing import Protocol
from urllib.parse import urlsplit

from agent_framework._telemetry import USER_AGENT_KEY, apply_feature_token, remove_feature_token
from openai import DefaultAsyncHttpxClient


class FeatureIndex(IntEnum):
    """OpenAI-owned feature-usage indexes."""

    OPENAI = 56


_AZURE_OPENAI_ORIGIN_SUFFIXES = (
    "cognitiveservices.azure.com",
    "openai.azure.com",
    "services.ai.azure.com",
)


class _HttpRequest(Protocol):
    @property
    def headers(self) -> MutableMapping[str, str]: ...

    @property
    def url(self) -> object: ...


class _FeatureUsageAsyncHttpxClient(DefaultAsyncHttpxClient):
    """OpenAI-default HTTP client that preserves the SDK's GC cleanup behavior."""

    def __del__(self) -> None:
        if self.is_closed:
            return
        with contextlib.suppress(Exception):
            asyncio.get_running_loop().create_task(self.aclose())


def _is_approved_origin(url: str, suffixes: tuple[str, ...]) -> bool:
    parsed_url = urlsplit(url)
    host = (parsed_url.hostname or "").rstrip(".").lower()
    return parsed_url.scheme == "https" and any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)


def create_feature_usage_http_client(
    *,
    approved_origin_suffixes: tuple[str, ...] = _AZURE_OPENAI_ORIGIN_SUFFIXES,
) -> DefaultAsyncHttpxClient:
    """Create the OpenAI SDK default client with destination-aware feature stamping."""

    async def stamp_feature_usage(request: _HttpRequest) -> None:  # ruff:ignore[unused-async]
        user_agent = request.headers.get(USER_AGENT_KEY, "")
        request.headers[USER_AGENT_KEY] = (
            apply_feature_token(user_agent)
            if _is_approved_origin(str(request.url), approved_origin_suffixes)
            else remove_feature_token(user_agent)
        )

    return _FeatureUsageAsyncHttpxClient(event_hooks={"request": [stamp_feature_usage]})
