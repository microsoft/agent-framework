# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._cancellation_token import CancellationToken
from ._guard_rails import InputGuardrail, OutputGuardrail

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__ALL__ = [
    "__version__",
] + [
    export.__name__ for export in [
        CancellationToken,
        InputGuardrail,
        OutputGuardrail,
    ]
]
