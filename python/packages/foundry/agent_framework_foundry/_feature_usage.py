# Copyright (c) Microsoft. All rights reserved.

from enum import IntEnum
from typing import Any

from agent_framework._telemetry import (
    IS_TELEMETRY_ENABLED,
    USER_AGENT_KEY,
    apply_feature_token,
    get_user_agent,
    remove_feature_token,
)
from agent_framework_openai._feature_usage import (
    _is_approved_origin,  # pyright: ignore[reportPrivateUsage]
    create_feature_usage_http_client,
)
from azure.core.pipeline.policies import UserAgentPolicy
from openai import DefaultAsyncHttpxClient


class FeatureIndex(IntEnum):
    """Foundry-owned feature-usage indexes."""

    CHAT_CLIENT = 48
    AGENT = 49
    MEMORY = 50
    EMBEDDING = 51
    EVALS = 52
    TOOLBOX = 53


_FOUNDRY_ORIGIN_SUFFIXES = (
    "inference.ai.azure.com",
    "services.ai.azure.com",
)


def create_foundry_feature_usage_http_client() -> DefaultAsyncHttpxClient:
    """Create an OpenAI SDK client for approved Foundry origins."""
    return create_feature_usage_http_client(approved_origin_suffixes=_FOUNDRY_ORIGIN_SUFFIXES)


def create_feature_usage_user_agent_policy() -> "FeatureUsageUserAgentPolicy":
    """Create the Azure policy with the Agent Framework base User-Agent when enabled."""
    if IS_TELEMETRY_ENABLED:
        return FeatureUsageUserAgentPolicy(user_agent=get_user_agent())
    return FeatureUsageUserAgentPolicy()


class FeatureUsageUserAgentPolicy(UserAgentPolicy):
    """Refresh or remove the feature token based on the actual Azure request origin."""

    def on_request(self, request: Any) -> None:
        """Apply normal Azure User-Agent behavior, then destination-aware feature stamping."""
        super().on_request(request)
        headers = request.http_request.headers
        user_agent = headers.get(USER_AGENT_KEY)
        base_user_agent = user_agent if isinstance(user_agent, str) else get_user_agent()
        headers[USER_AGENT_KEY] = (
            apply_feature_token(base_user_agent)
            if _is_approved_origin(request.http_request.url, _FOUNDRY_ORIGIN_SUFFIXES)
            else remove_feature_token(base_user_agent)
        )
