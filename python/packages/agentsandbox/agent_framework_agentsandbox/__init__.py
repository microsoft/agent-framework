# Copyright (c) Microsoft. All rights reserved.

"""agent-sandbox CodeAct integration for Microsoft Agent Framework.

This package exposes two classes that plug into the Agent Framework's
``ContextProvider`` / ``FunctionTool`` extension points:

* :class:`AgentSandboxCodeActProvider` — drop into ``Agent(context_providers=[...])``
  to auto-inject the ``execute_code`` tool and CodeAct system instructions on
  every run.
* :class:`AgentSandboxExecuteCodeTool` — the underlying ``FunctionTool`` for
  callers that want to add the tool directly without a provider.

Each invocation of ``execute_code`` runs LLM-emitted Python inside a Kubernetes
Pod managed by the `kubernetes-sigs/agent-sandbox
<https://github.com/kubernetes-sigs/agent-sandbox>`_ controller. State persists
for the lifetime of the provider: the Pod's filesystem and any
``pip install``-ed packages are available across calls, even though each call
runs as a fresh ``python3`` process. Call ``await provider.close()`` (or use
the provider as an async context manager) to terminate the Pod when done.
"""

import importlib.metadata

from ._execute_code_tool import AgentSandboxExecuteCodeTool
from ._provider import AgentSandboxCodeActProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AgentSandboxCodeActProvider",
    "AgentSandboxExecuteCodeTool",
    "__version__",
]
