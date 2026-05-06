# Copyright (c) Microsoft. All rights reserved.

"""Cross-platform local shell tool for the Microsoft Agent Framework."""

from __future__ import annotations

from ._docker import (
    DEFAULT_IMAGE as DOCKER_DEFAULT_IMAGE,
)
from ._docker import (
    DockerNotAvailableError,
    DockerShellTool,
    is_docker_available,
)
from ._environment import (
    ShellEnvironmentProvider,
    ShellEnvironmentProviderOptions,
    ShellEnvironmentSnapshot,
    ShellFamily,
    default_instructions_formatter,
)
from ._executor_base import ShellExecutor
from ._policy import DEFAULT_DENYLIST, ShellDecision, ShellPolicy, ShellRequest
from ._tool import LocalShellTool
from ._types import (
    ShellCommandError,
    ShellExecutionError,
    ShellMode,
    ShellResult,
    ShellTimeoutError,
)

__all__ = [
    "DEFAULT_DENYLIST",
    "DOCKER_DEFAULT_IMAGE",
    "DockerNotAvailableError",
    "DockerShellTool",
    "LocalShellTool",
    "ShellCommandError",
    "ShellDecision",
    "ShellEnvironmentProvider",
    "ShellEnvironmentProviderOptions",
    "ShellEnvironmentSnapshot",
    "ShellExecutionError",
    "ShellExecutor",
    "ShellFamily",
    "ShellMode",
    "ShellPolicy",
    "ShellRequest",
    "ShellResult",
    "ShellTimeoutError",
    "default_instructions_formatter",
    "is_docker_available",
]
