# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Microsoft Agent Framework for Python.

This is the main agent-framework package that provides a convenient way to install
all the core and optional packages of the Microsoft Agent Framework.
"""

import contextlib

__version__ = "1.0.0-b251001"

# Re-export commonly used components from core package
with contextlib.suppress(ImportError):
    from agent_framework_core import *  # noqa: F403

# Make optional packages available for discovery
__all__ = ["__version__"]