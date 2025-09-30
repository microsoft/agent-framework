# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Any, Final

from . import __version__ as version_info
from ._logging import get_logger

logger = get_logger()

__all__ = [
    "AGENT_FRAMEWORK_USER_AGENT",
    "APP_INFO",
    "USER_AGENT_KEY",
    "USER_AGENT_TELEMETRY_DISABLED_ENV_VAR",
    "prepend_agent_framework_to_user_agent",
]

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


def prepend_agent_framework_to_user_agent(headers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepend "agent-framework" to the User-Agent in the headers.

    When user agent telemetry is disabled, through the AZURE_TELEMETRY_DISABLED environment variable,
    the User-Agent header will not include the agent-framework information, it will be sent back as is,
    or as a empty dict when None is passed.

    Args:
        headers: The existing headers dictionary.

    Returns:
        A new dict with "User-Agent" set to "agent-framework-python/{version}" if headers is None.
        The modified headers dictionary with "agent-framework-python/{version}" prepended to the User-Agent.
    """
    if not IS_TELEMETRY_ENABLED:
        return headers or {}
    if not headers:
        return {USER_AGENT_KEY: AGENT_FRAMEWORK_USER_AGENT}
    headers[USER_AGENT_KEY] = (
        f"{AGENT_FRAMEWORK_USER_AGENT} {headers[USER_AGENT_KEY]}"
        if USER_AGENT_KEY in headers
        else AGENT_FRAMEWORK_USER_AGENT
    )

    return headers
