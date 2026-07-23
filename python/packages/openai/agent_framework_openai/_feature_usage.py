# Copyright (c) Microsoft. All rights reserved.

from enum import IntEnum

import httpx
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


def _is_approved_origin(url: httpx.URL | str, suffixes: tuple[str, ...]) -> bool:
    if isinstance(url, str):
        url = httpx.URL(url)
    host = (url.host or "").rstrip(".").lower()
    return url.scheme == "https" and any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)


def create_feature_usage_http_client(
    *,
    approved_origin_suffixes: tuple[str, ...] = _AZURE_OPENAI_ORIGIN_SUFFIXES,
) -> DefaultAsyncHttpxClient:
    """Create the OpenAI SDK default client with destination-aware feature stamping."""

    async def stamp_feature_usage(request: httpx.Request) -> None:  # ruff:ignore[unused-async]
        user_agent = request.headers.get(USER_AGENT_KEY, "")
        request.headers[USER_AGENT_KEY] = (
            apply_feature_token(user_agent)
            if _is_approved_origin(request.url, approved_origin_suffixes)
            else remove_feature_token(user_agent)
        )

    return DefaultAsyncHttpxClient(event_hooks={"request": [stamp_feature_usage]})
