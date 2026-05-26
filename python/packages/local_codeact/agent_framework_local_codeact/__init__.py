# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import importlib.metadata

from ._execute_code_tool import LocalExecuteCodeTool
from ._provider import LocalCodeActProvider
from ._types import ExecutionMode, FileMount, FileMountInput, MountMode, ProcessExecutionLimits
from ._validator import CodeValidationError

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "CodeValidationError",
    "ExecutionMode",
    "FileMount",
    "FileMountInput",
    "LocalCodeActProvider",
    "LocalExecuteCodeTool",
    "MountMode",
    "ProcessExecutionLimits",
    "__version__",
]
