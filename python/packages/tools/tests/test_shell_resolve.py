# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework_tools.shell import ShellExecutionError
from agent_framework_tools.shell._resolve import _ensure_command_flag, is_powershell, resolve_shell


def test_empty_string_shell_override_rejected() -> None:
    with pytest.raises(ShellExecutionError, match="must not be empty"):
        resolve_shell("", interactive=True)


def test_whitespace_string_shell_override_rejected() -> None:
    with pytest.raises(ShellExecutionError, match="must not be empty"):
        resolve_shell("   ", interactive=False)


def test_empty_sequence_shell_override_rejected() -> None:
    with pytest.raises(ShellExecutionError, match="must not be empty"):
        resolve_shell([], interactive=True)


def test_resolve_shell_prefers_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_FRAMEWORK_SHELL", "/custom/pwsh -NoProfile")

    assert resolve_shell(None, interactive=False) == ["/custom/pwsh", "-NoProfile", "-Command"]


def test_resolve_shell_windows_defaults_and_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "win32")
    monkeypatch.setattr(resolve_module.shutil, "which", lambda name: "C:/pwsh.exe" if name == "pwsh" else None)
    assert resolve_shell(None, interactive=True) == [
        "C:/pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "-",
    ]

    monkeypatch.setattr(resolve_module.shutil, "which", lambda name: None)
    with pytest.raises(ShellExecutionError, match="Neither 'pwsh' nor 'powershell'"):
        resolve_shell(None, interactive=False)


def test_resolve_shell_posix_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "darwin")
    monkeypatch.setattr(resolve_module.os.path, "exists", lambda candidate: candidate == "/bin/sh")
    assert resolve_shell(None, interactive=False) == ["/bin/sh", "-c"]

    monkeypatch.setattr(resolve_module.os.path, "exists", lambda candidate: False)
    monkeypatch.setattr(resolve_module.shutil, "which", lambda name: "/usr/local/bin/sh" if name == "sh" else None)
    assert resolve_shell(None, interactive=True) == ["/usr/local/bin/sh"]

    monkeypatch.setattr(resolve_module.shutil, "which", lambda name: None)
    with pytest.raises(ShellExecutionError, match="No POSIX shell found"):
        resolve_shell(None, interactive=False)


def test_is_powershell_and_command_flag_helpers() -> None:
    assert is_powershell([]) is False
    assert _ensure_command_flag([]) == []


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


def test_win32_shell_override_keeps_backslashes(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "win32")
    path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    assert resolve_shell(path, interactive=False) == [path, "-Command"]


def test_win32_env_shell_override_keeps_backslashes(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "win32")
    path = r"C:\msys64\usr\bin\bash.exe"
    monkeypatch.setenv("AGENT_FRAMEWORK_SHELL", path)
    assert resolve_shell(None, interactive=False) == [path, "-c"]


def test_win32_quoted_shell_override_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "win32")
    argv = resolve_shell(r'"C:\Program Files\PowerShell\7\pwsh.exe" -NoProfile', interactive=False)
    assert argv[0] == r"C:\Program Files\PowerShell\7\pwsh.exe"
    assert "-NoProfile" in argv
    assert argv[-1] == "-Command"


def test_win32_adjacent_quoted_unquoted_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "win32")
    argv = resolve_shell('"C:/Program Files"/PowerShell/7/pwsh.exe -NoProfile', interactive=False)
    assert argv[0] == "C:/Program Files/PowerShell/7/pwsh.exe"
    assert "-NoProfile" in argv
    assert argv[-1] == "-Command"


def test_win32_equals_quoted_value_stays_one_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "win32")
    argv = resolve_shell(r'C:\msys64\usr\bin\bash.exe --rcfile="C:/Program Files/bash.rc"', interactive=True)
    assert argv[0] == r"C:\msys64\usr\bin\bash.exe"
    assert argv[1] == "--rcfile=C:/Program Files/bash.rc"
