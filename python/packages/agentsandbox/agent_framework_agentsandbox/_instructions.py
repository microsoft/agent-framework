# Copyright (c) Microsoft. All rights reserved.

"""CodeAct prompt and tool-description builders.

The wording is deliberately small. The goal is to teach the model two things and
nothing more: prefer ``execute_code`` for computation, and end the program with
``print(...)`` (the sandbox does not return the value of the last expression).

The persistent-state note matters because agent-sandbox differs from a
snapshot-and-restore sandbox: filesystem state and installed packages carry
over between calls, while Python module-level globals do not (each call is a
fresh interpreter process). Surfacing this lets the model use the filesystem
as a working store between steps without expecting in-memory continuity.
"""

from __future__ import annotations


def build_codeact_instructions(*, working_directory: str = "/app") -> str:
    """Return the CodeAct system-prompt fragment injected by the provider.

    Args:
        working_directory: Absolute path of the working directory inside the
            sandbox Pod. The agent-sandbox runtime image used by the sample
            ``python-sandbox-template`` runs commands from ``/app``, so that is
            the default.

    Returns:
        A short CodeAct instruction fragment suitable for
        :meth:`agent_framework.SessionContext.extend_instructions`.
    """
    return (
        "You have one primary tool: execute_code.\n"
        "\n"
        "Prefer a single execute_code call per user turn when possible. "
        "To surface results, end the code with `print(...)`; the sandbox does "
        "not return the value of the last expression.\n"
        "\n"
        f"The working directory inside the sandbox is `{working_directory}/`. "
        "Files written there persist across calls, and any packages you "
        "`pip install` remain installed for the lifetime of the session. "
        "Module-level Python globals do not persist between calls — each "
        "execute_code invocation is a fresh `python3` process.\n"
    )


def build_execute_code_description(*, warmpool: str, namespace: str) -> str:
    """Return the description shown to the model on the ``execute_code`` tool.

    Args:
        warmpool: The name of the ``SandboxWarmPool`` the pod is claimed from.
            Surfaced to the model so reasoning traces can mention which sandbox
            backed the call.
        namespace: Kubernetes namespace that holds the warm pool.

    Returns:
        Tool description suitable for :class:`agent_framework.FunctionTool`.
    """
    return (
        "Execute a Python program inside an isolated Kubernetes sandbox pod "
        f"(agent-sandbox warm pool `{warmpool}`, namespace `{namespace}`). "
        "Returns stdout, plus stderr or a structured error on non-zero exit. "
        "Use `print(...)` to surface results; the working directory is `/app/` "
        "and persists across calls."
    )
