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


def subprocess_script_runner(skill: FileSkill, script: FileSkillScript, args: dict[str, Any] | None = None) -> str:
    """Run a skill script as a local Python subprocess.
    Uses ``FileSkillScript.full_path`` as the script path, converts the
    ``args`` dict to CLI flags, and returns captured output.
    Args:
        skill: The file-based skill that owns the script.
        script: The file-based script to run.
        args: Optional arguments forwarded as CLI flags.
    Returns:
        The combined stdout/stderr output, or an error message.
    """
    script_path = Path(script.full_path)
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
