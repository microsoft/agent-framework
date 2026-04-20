# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import importlib.metadata

from ._execute_code_tool import HyperlightExecuteCodeTool
from ._provider import HyperlightCodeActProvider
from ._types import AllowedDomain, AllowedDomainInput, FileMount, FileMountInput

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AllowedDomain",
    "AllowedDomainInput",
    "FileMount",
    "FileMountInput",
    "HyperlightCodeActProvider",
    "HyperlightExecuteCodeTool",
    "__version__",
]
