# Copyright (c) Microsoft. All rights reserved.

import os
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Final

try:
    version_info = version("agent-framework")
except PackageNotFoundError:
    version_info = "dev"

# Note that if this environment variable does not exist, telemetry is enabled.
TELEMETRY_DISABLED_ENV_VAR = "AZURE_TELEMETRY_DISABLED"
IS_TELEMETRY_ENABLED = os.environ.get(TELEMETRY_DISABLED_ENV_VAR, "false").lower() not in ["true", "1"]

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


def prepend_agent_framework_to_user_agent(headers: dict[str, Any]) -> dict[str, Any]:
    """Prepend "agent-framework" to the User-Agent in the headers.

    Args:
        headers: The existing headers dictionary.

    Returns:
        The modified headers dictionary with "agent-framework-python/{version}" prepended to the User-Agent.
    """
    headers[USER_AGENT_KEY] = (
        f"{AGENT_FRAMEWORK_USER_AGENT} {headers[USER_AGENT_KEY]}"
        if USER_AGENT_KEY in headers
        else AGENT_FRAMEWORK_USER_AGENT
    )

    return headers


__all__ = ["AGENT_FRAMEWORK_USER_AGENT", "APP_INFO", "USER_AGENT_KEY", "prepend_agent_framework_to_user_agent"]
