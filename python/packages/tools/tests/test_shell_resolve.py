# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework_tools.shell import ShellExecutionError
from agent_framework_tools.shell._resolve import resolve_shell


def test_empty_string_shell_override_rejected() -> None:
    with pytest.raises(ShellExecutionError, match="must not be empty"):
        resolve_shell("", interactive=True)


def test_whitespace_string_shell_override_rejected() -> None:
    with pytest.raises(ShellExecutionError, match="must not be empty"):
        resolve_shell("   ", interactive=False)


def test_empty_sequence_shell_override_rejected() -> None:
    with pytest.raises(ShellExecutionError, match="must not be empty"):
        resolve_shell([], interactive=True)
