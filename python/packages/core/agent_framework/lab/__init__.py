# Copyright (c) Microsoft. All rights reserved.

"""Lab namespace package for experimental Agent Framework integrations.

This module extends the package path so experimental lab integrations can be
distributed in separate packages under the ``agent_framework.lab`` namespace.
"""

# This makes agent_framework.lab a namespace package
__path__ = __import__("pkgutil").extend_path(__path__, __name__)
