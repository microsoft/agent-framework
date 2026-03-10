# Copyright (c) Microsoft. All rights reserved.

"""Subprocess-based skill script runner.

Provides a sample :class:`~agent_framework.SkillScriptRunner` callback for
:class:`~agent_framework.SkillsProvider` that executes skill scripts as
**local Python subprocesses** via :func:`subprocess.run`.

Usage::

    from subprocess_script_runner import subprocess_script_runner

    provider = SkillsProvider(
        skill_paths="./skills",
        script_runner=subprocess_script_runner,
    )

The runner resolves the script's absolute path from the owning skill directory,
converts the ``args`` dict to CLI flags (e.g. ``{"length": 24}`` → ``--length 24``),
and captures stdout/stderr as the result returned to the LLM.

.. note:: Sample Code Only

    This runner is provided for **demonstration purposes only**. For
    production use, consider adding:

    * Sandboxing (e.g. containers, ``seccomp``, or ``firejail``)
    * Resource limits (CPU, memory, wall-clock timeout)
    * Input validation and allow-listing of executable scripts
    * Structured logging and audit trails
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from agent_framework import Skill, SkillScript


def subprocess_script_runner(skill: Skill, script: SkillScript, args: dict[str, Any] | None = None) -> str:
    """Run a skill script as a local Python subprocess.

    .. warning:: This runner is provided for **demonstration purposes only**.
        For production use, implement proper sandboxing, resource limits,
        input validation, and structured logging.

    Resolves the script's absolute path by joining ``skill.path`` (the skill
    directory) with ``script.path`` (relative path declared in ``SKILL.md``).
    The ``args`` dictionary is converted to CLI flags following these rules:

    * **Boolean** values produce a bare flag when ``True`` (e.g.
      ``{"verbose": True}`` → ``--verbose``), and are omitted when ``False``.
    * **Other** values produce a flag–value pair (e.g. ``{"length": 24}``
      → ``--length 24``).  ``None`` values are skipped.

    The script runs with a **30-second timeout** and its working directory
    set to the script's parent folder so that relative imports and file
    references inside the script work as expected.

    Args:
        skill: The skill that owns the script.  Must have a non-``None``
            :attr:`~Skill.path` pointing to the skill directory.
        script: The script to run.  Must have a non-``None``
            :attr:`~SkillScript.path` relative to the skill directory.
        args: Optional keyword arguments forwarded to the script as CLI
            flags.  Defaults to ``None`` (no extra flags).

    Returns:
        The combined stdout and stderr output from the subprocess, or a
        human-readable error message if the script could not be found,
        timed out, or failed to launch.
    """
    if not skill.path:
        return f"Error: Skill '{skill.name}' has no directory path."

    if not script.path:
        return f"Error: Script '{script.name}' has no file path. Only file-based scripts can be executed locally."

    script_path = Path(skill.path) / script.path
    if not script_path.is_file():
        return f"Error: Script file not found: {script_path}"

    cmd = [sys.executable, str(script_path)]

    # Convert args dict to CLI flags
    if args:
        for key, value in args.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            elif value is not None:
                cmd.append(f"--{key}")
                cmd.append(str(value))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(script_path.parent),
        )

        output = result.stdout
        if result.stderr:
            output += f"\nStderr:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\nScript exited with code {result.returncode}"

        return output.strip() or "(no output)"

    except subprocess.TimeoutExpired:
        return f"Error: Script '{script.name}' timed out after 30 seconds."
    except OSError as e:
        return f"Error: Failed to execute script '{script.name}': {e}"
