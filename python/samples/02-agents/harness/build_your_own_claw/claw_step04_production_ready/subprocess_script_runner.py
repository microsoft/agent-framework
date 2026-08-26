# Copyright (c) Microsoft. All rights reserved.

"""Sample subprocess-based skill script runner.
Executes file-based skill scripts as local Python subprocesses.
This is provided for demonstration purposes only.
"""

from __future__ import annotations

import subprocess
import sys

# Uncomment this filter to suppress the experimental Skills warning before
# using the sample's Skills APIs.
# import warnings
# warnings.filterwarnings("ignore", message=r"\[SKILLS\].*", category=FutureWarning)
from pathlib import Path
from typing import Any

from agent_framework import FileSkill, FileSkillScript


def subprocess_script_runner(
    skill: FileSkill, script: FileSkillScript, args: dict[str, Any] | list[str] | None = None
) -> str:
    """Run a skill script as a local Python subprocess.
    Uses ``FileSkillScript.full_path`` as the script path, converts the
    ``args`` to CLI arguments, and returns captured output.
    Args:
        skill: The file-based skill that owns the script.
        script: The file-based script to run.
        args: Optional arguments.  A ``list[str]`` is forwarded as
            positional CLI arguments.  Passing a ``dict`` or any other
            type raises :class:`TypeError` — file-based scripts expect
            positional arguments as a JSON array of strings.
    Returns:
        The combined stdout/stderr output, or an error message.
    Raises:
        TypeError: If ``args`` is not a ``list[str]`` or ``None``, or if
            any list element is not a string.
    """
    script_path = Path(script.full_path)
    if not script_path.is_file():
        return f"Error: Script file not found: {script_path}"
    cmd = [sys.executable, str(script_path)]
    if isinstance(args, list):
        for item in args:
            if not isinstance(item, str):
                raise TypeError(
                    f"File-based skill scripts only accept string CLI arguments "
                    f"but received a {type(item).__name__}. "
                    f"All array elements must be strings."
                )
        cmd.extend(args)
    elif args is not None:
        raise TypeError(
            f"Expected a list of CLI arguments but received {type(args).__name__}. "
            f"File-based skill scripts expect positional arguments as a list of strings."
        )
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
