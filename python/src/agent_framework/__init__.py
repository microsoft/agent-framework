# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._guard_rails import InputGuardrail, OutputGuardrail
from ._tool import AITool

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__ALL__ = [
    "__version__",
] + [
    export.__name__
    for export in [
        InputGuardrail,
        OutputGuardrail,
        AITool,
    ]
]
