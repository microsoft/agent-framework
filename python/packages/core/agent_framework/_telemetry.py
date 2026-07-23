# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import contextlib
import logging
import os
import re
import threading
from enum import IntEnum
from typing import Any, Final

from . import __version__ as version_info

logger = logging.getLogger("agent_framework")


# Note that if this environment variable does not exist, user agent telemetry is enabled.
USER_AGENT_TELEMETRY_DISABLED_ENV_VAR = "AGENT_FRAMEWORK_USER_AGENT_DISABLED"
IS_TELEMETRY_ENABLED = os.environ.get(USER_AGENT_TELEMETRY_DISABLED_ENV_VAR, "false").lower() not in ["true", "1"]
FEATURE_MASK_DISABLED_ENV_VAR = "AGENT_FRAMEWORK_FEATURE_MASK_DISABLED"
FEATURE_REGISTRY_VERSION = 1

APP_INFO = (
    {
        "agent-framework-version": f"python/{version_info}",
    }
    if IS_TELEMETRY_ENABLED
    else None
)
USER_AGENT_KEY: Final[str] = "User-Agent"
HTTP_USER_AGENT: Final[str] = "agent-framework-python"
AGENT_FRAMEWORK_USER_AGENT = f"{HTTP_USER_AGENT}/{version_info}"


class FeatureIndex(IntEnum):
    """Core-owned indexes in the Python feature-usage registry."""

    CORE_AGENT = 0
    CORE_HARNESS_AGENT = 1
    CORE_WORKFLOW = 2
    CORE_MCP = 3
    CORE_TOOL_APPROVAL = 4
    CORE_MEMORY_PROVIDER = 5
    CORE_SKILLS_PROVIDER = 6
    CORE_FILE_ACCESS_PROVIDER = 7
    CORE_COMPACTION_PROVIDER = 8
    CORE_TODO_PROVIDER = 9
    CORE_AGENT_MODE_PROVIDER = 10
    CORE_BACKGROUND_AGENTS_PROVIDER = 11
    CORE_IN_MEMORY_HISTORY_PROVIDER = 12
    CORE_FILE_HISTORY_PROVIDER = 13
    CORE_FILE_SKILLS_SOURCE = 14
    CORE_IN_MEMORY_SKILLS_SOURCE = 15
    CORE_MCP_SKILLS_SOURCE = 16


# This environment variable is reserved by the Foundry hosting environment to
# indicate that the agent is running in a hosted environment.
_FOUNDRY_HOSTING_ENV_VAR = "FOUNDRY_HOSTING_ENVIRONMENT"
# This prefix is added to the user agent string when the agent is running in a hosted environment.
_HOSTED_USER_AGENT_PREFIX = "foundry-hosting"

_user_agent_prefixes: set[str] = set()
_hosted_env_detected: bool = False
_feature_mask = 0
_feature_mask_lock = threading.Lock()
_feature_comment_pattern = re.compile(r"\s+\(feat=v\d+\.[0-9a-fA-F]+\)")


def _add_user_agent_prefix(prefix: str) -> None:
    """Permanently add a prefix to the user agent string.

    This is used by hosting layers to identify themselves in telemetry.
    Once added, the prefix applies to all subsequent user agent strings.

    Args:
        prefix: The prefix to add (e.g. "foundry-hosting").
    """
    if prefix:
        _user_agent_prefixes.add(prefix)


def _detect_hosted_environment() -> None:
    """Detect if running in a hosted environment and add the user agent prefix.

    Checks the ``FOUNDRY_HOSTING_ENVIRONMENT`` env var first, then falls back
    to checking whether the agent server SDK is installed (via
    ``importlib.util.find_spec``) before importing it, to avoid unnecessary
    import overhead for non-hosted scenarios.
    """
    global _hosted_env_detected
    if _hosted_env_detected:
        return

    if (env_value := os.environ.get(_FOUNDRY_HOSTING_ENV_VAR)) is not None:
        # Env var exists — trust its value and skip the fallback.
        if env_value:
            _add_user_agent_prefix(_HOSTED_USER_AGENT_PREFIX)
            _hosted_env_detected = True
        return

    # Env var not set — fall back to AgentConfig as a second layer of defense.
    # Use find_spec to avoid the cost of a full import when the SDK is not installed.
    import importlib.util

    try:
        if importlib.util.find_spec("azure.ai.agentserver.core") is None:
            return
    except (ImportError, ValueError):
        return
    with contextlib.suppress(ImportError, AttributeError):
        from azure.ai.agentserver.core import (
            AgentConfig,
        )

        if AgentConfig.from_env().is_hosted:
            _add_user_agent_prefix(_HOSTED_USER_AGENT_PREFIX)
            _hosted_env_detected = True


def get_user_agent() -> str:
    """Return the full user agent string including any registered prefixes."""
    _detect_hosted_environment()
    if not _user_agent_prefixes:
        return AGENT_FRAMEWORK_USER_AGENT
    return f"{'/'.join(sorted(_user_agent_prefixes))}/{AGENT_FRAMEWORK_USER_AGENT}"


def _feature_mask_enabled() -> bool:
    """Return whether feature-usage marking and emission are enabled."""
    return IS_TELEMETRY_ENABLED and os.environ.get(FEATURE_MASK_DISABLED_ENV_VAR, "false").lower() not in ("true", "1")


def mark_feature_used(index: IntEnum | int) -> None:
    """Mark a feature as used in the process-global feature mask."""
    if not _feature_mask_enabled():
        return

    feature_index = int(index)
    if not 0 <= feature_index < 128:
        raise ValueError(f"Feature index must be in range 0..127, got {feature_index}")

    global _feature_mask
    with _feature_mask_lock:
        _feature_mask |= 1 << feature_index


def get_feature_token() -> str | None:
    """Return the current versioned feature token, or None when empty or disabled."""
    if not _feature_mask_enabled():
        return None

    with _feature_mask_lock:
        feature_mask = _feature_mask
    if feature_mask == 0:
        return None
    return f"v{FEATURE_REGISTRY_VERSION}.{feature_mask:x}"


def apply_feature_token(user_agent: str) -> str:
    """Append or refresh the live feature token in a User-Agent value."""
    base_user_agent = remove_feature_token(user_agent)
    token = get_feature_token()
    if token is None:
        return base_user_agent
    if not base_user_agent:
        return f"(feat={token})"
    return f"{base_user_agent} (feat={token})"


def remove_feature_token(user_agent: str) -> str:
    """Remove the Agent Framework feature token from a User-Agent value."""
    return _feature_comment_pattern.sub("", user_agent).strip()


def prepend_agent_framework_to_user_agent(headers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepend "agent-framework" to the User-Agent in the headers.

    When user agent telemetry is disabled through the ``AGENT_FRAMEWORK_USER_AGENT_DISABLED``
    environment variable, the User-Agent header will not include the agent-framework information.
    It will be sent back as is, or as an empty dict when None is passed.

    Args:
        headers: The existing headers dictionary.

    Returns:
        A new dict with "User-Agent" set to "agent-framework-python/{version}" if headers is None.
        The modified headers dictionary with "agent-framework-python/{version}" prepended to the User-Agent.

    Examples:
        .. code-block:: python

            from agent_framework import prepend_agent_framework_to_user_agent

            # Add agent-framework to new headers
            headers = prepend_agent_framework_to_user_agent()
            print(headers["User-Agent"])  # "agent-framework-python/0.1.0"

            # Prepend to existing headers
            existing = {"User-Agent": "my-app/1.0"}
            headers = prepend_agent_framework_to_user_agent(existing)
            print(headers["User-Agent"])  # "agent-framework-python/0.1.0 my-app/1.0"
    """
    if not IS_TELEMETRY_ENABLED:
        return headers or {}
    user_agent = get_user_agent()
    if not headers:
        return {USER_AGENT_KEY: user_agent}
    headers[USER_AGENT_KEY] = f"{user_agent} {headers[USER_AGENT_KEY]}" if USER_AGENT_KEY in headers else user_agent

    return headers
