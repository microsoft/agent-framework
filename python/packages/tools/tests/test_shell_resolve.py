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


def test_stateless_appends_dash_c_for_posix_shell_without_flag() -> None:
    argv = resolve_shell("/bin/bash", interactive=False)
    assert argv == ["/bin/bash", "-c"]


def test_stateless_appends_dash_c_for_pwsh_without_flag() -> None:
    argv = resolve_shell("/usr/bin/pwsh -NoProfile", interactive=False)
    assert argv[-1] == "-Command"
    assert "pwsh" in argv[0]


def test_stateless_preserves_existing_dash_c_flag() -> None:
    argv = resolve_shell("/bin/bash -c", interactive=False)
    assert argv == ["/bin/bash", "-c"]


def test_stateless_preserves_existing_pwsh_command_flag() -> None:
    argv = resolve_shell("pwsh -NoProfile -Command", interactive=False)
    assert argv[-1] == "-Command"
    # No second -Command appended.
    assert argv.count("-Command") == 1


def test_interactive_does_not_append_command_flag() -> None:
    argv = resolve_shell("/bin/bash --noprofile", interactive=True)
    assert "-c" not in argv
