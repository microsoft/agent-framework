# Copyright (c) Microsoft. All rights reserved.

"""Sample subprocess-based skill script runner.
Executes file-based skill scripts as local Python subprocesses.
This is provided for demonstration purposes only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from agent_framework import Skill, SkillScript


def subprocess_script_runner(skill: Skill, script: SkillScript, args: dict[str, Any] | None = None) -> str:
    """Run a skill script as a local Python subprocess.
    Resolves the script's absolute path from the skill directory, converts
    the ``args`` dict to CLI flags, and returns captured output.
    Args:
        skill: The skill that owns the script.
        script: The script to run.
        args: Optional arguments forwarded as CLI flags.
    Returns:
        The combined stdout/stderr output, or an error message.
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
