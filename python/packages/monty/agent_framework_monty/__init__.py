# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import importlib.metadata

from ._execute_code_tool import MontyExecuteCodeTool
from ._provider import MontyCodeActProvider
from ._types import FileMount, FileMountInput, MountMode

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "FileMount",
    "FileMountInput",
    "MontyCodeActProvider",
    "MontyExecuteCodeTool",
    "MountMode",
    "__version__",
]
