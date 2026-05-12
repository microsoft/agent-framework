# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._agent import GitHubCopilotAgent, GitHubCopilotOptions, GitHubCopilotSettings, RawGitHubCopilotAgent
from ._model_client import (
    COPILOT_BASE_URL,
    GitHubCopilotModelClient,
    build_copilot_headers,
    device_code_login,
    exchange_token,
    fetch_copilot_model_catalog,
    resolve_github_token,
    validate_token,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "COPILOT_BASE_URL",
    "GitHubCopilotAgent",
    "GitHubCopilotModelClient",
    "GitHubCopilotOptions",
    "GitHubCopilotSettings",
    "RawGitHubCopilotAgent",
    "__version__",
    "build_copilot_headers",
    "device_code_login",
    "exchange_token",
    "fetch_copilot_model_catalog",
    "resolve_github_token",
    "validate_token",
]
