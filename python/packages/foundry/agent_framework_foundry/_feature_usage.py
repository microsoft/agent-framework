# Copyright (c) Microsoft. All rights reserved.

from enum import IntEnum
from typing import Any

from agent_framework._telemetry import (
    USER_AGENT_KEY,
    apply_feature_token,
    remove_feature_token,
)
from agent_framework_openai._feature_usage import (
    _is_approved_origin,  # pyright: ignore[reportPrivateUsage]
    create_feature_usage_http_client,
)
from azure.core.pipeline.policies import SansIOHTTPPolicy
from openai import DefaultAsyncHttpxClient


class FeatureIndex(IntEnum):
    """Foundry-owned feature-usage indexes."""

    FOUNDRY_CHAT_CLIENT = 48
    FOUNDRY_AGENT = 49
    FOUNDRY_MEMORY = 50
    FOUNDRY_EMBEDDING = 51
    FOUNDRY_EVALS = 52


_FOUNDRY_ORIGIN_SUFFIXES = (
    "inference.ai.azure.com",
    "services.ai.azure.com",
)


def create_foundry_feature_usage_http_client() -> DefaultAsyncHttpxClient:
    """Create an OpenAI SDK client for approved Foundry origins."""
    return create_feature_usage_http_client(approved_origin_suffixes=_FOUNDRY_ORIGIN_SUFFIXES)


def create_feature_usage_policy() -> "FeatureUsagePolicy":
    """Create the destination-aware policy that stamps each actual request hop."""
    return FeatureUsagePolicy()


class FeatureUsagePolicy(SansIOHTTPPolicy[Any, Any]):
    """Refresh or remove the feature token based on the actual Azure request origin."""

    def on_request(self, request: Any) -> None:
        """Apply destination-aware feature stamping to the current request hop."""
        headers = request.http_request.headers
        user_agent = headers.get(USER_AGENT_KEY)
        if not isinstance(user_agent, str):
            return
        headers[USER_AGENT_KEY] = (
            apply_feature_token(user_agent)
            if _is_approved_origin(request.http_request.url, _FOUNDRY_ORIGIN_SUFFIXES)
            else remove_feature_token(user_agent)
        )
