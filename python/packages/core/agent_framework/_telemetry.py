# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import os
from typing import Any, Final

from . import __version__ as version_info

logger = logging.getLogger("agent_framework")


# Note that if this environment variable does not exist, user agent telemetry is enabled.
USER_AGENT_TELEMETRY_DISABLED_ENV_VAR = "AGENT_FRAMEWORK_USER_AGENT_DISABLED"
IS_TELEMETRY_ENABLED = os.environ.get(USER_AGENT_TELEMETRY_DISABLED_ENV_VAR, "false").lower() not in ["true", "1"]

APP_INFO = (
    {
        "agent-framework-version": f"python/{version_info}",  # type: ignore[has-type]
    }
    if IS_TELEMETRY_ENABLED
    else None
)
USER_AGENT_KEY: Final[str] = "User-Agent"
HTTP_USER_AGENT: Final[str] = "agent-framework-python"
AGENT_FRAMEWORK_USER_AGENT = f"{HTTP_USER_AGENT}/{version_info}"  # type: ignore[has-type]

_user_agent_prefixes: list[str] = []


def append_to_user_agent(prefix: str) -> None:
    """Prepend a prefix to the agent framework user agent string.

    This is useful for hosting layers that want to identify themselves in telemetry.
    Duplicate prefixes are ignored.

    Args:
        prefix: The prefix to prepend (e.g. "foundry-hosting-responses").
    """
    if prefix and prefix not in _user_agent_prefixes:
        _user_agent_prefixes.append(prefix)


def _get_user_agent() -> str:
    """Return the full user agent string including any prepended prefixes."""
    if not _user_agent_prefixes:
        return AGENT_FRAMEWORK_USER_AGENT
    return f"{'/'.join(_user_agent_prefixes)}/{AGENT_FRAMEWORK_USER_AGENT}"


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
    user_agent = _get_user_agent()
    if not headers:
        return {USER_AGENT_KEY: user_agent}
    headers[USER_AGENT_KEY] = f"{user_agent} {headers[USER_AGENT_KEY]}" if USER_AGENT_KEY in headers else user_agent

    return headers
