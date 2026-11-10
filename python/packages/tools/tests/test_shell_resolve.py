# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeAlias

import pytest

from agent_framework_tools.shell import ShellExecutionError
from agent_framework_tools.shell._resolve import (
    _ensure_command_flag,
    find_executable,
    is_powershell,
    resolve_executable,
    resolve_shell,
)

_FakeWindowsHost: TypeAlias = Callable[[str, Iterable[str]], None]

_TRUSTED_BIN = r"C:\Trusted\bin"
_POWERSHELL_7 = r"C:\Program Files\PowerShell\7"
_WINDOWS_POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0"


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


def test_resolve_shell_windows_defaults_and_missing_binary(
    fake_windows_host: _FakeWindowsHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_FRAMEWORK_SHELL", raising=False)
    fake_windows_host(_POWERSHELL_7, {rf"{_POWERSHELL_7}\pwsh.exe"})
    assert resolve_shell(None, interactive=True) == [
        rf"{_POWERSHELL_7}\pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "-",
    ]

    fake_windows_host(_POWERSHELL_7, set())
    with pytest.raises(ShellExecutionError, match="Neither 'pwsh' nor 'powershell'"):
        resolve_shell(None, interactive=False)


def test_resolve_shell_windows_default_ignores_executables_in_the_current_directory(
    fake_windows_host: _FakeWindowsHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_FRAMEWORK_SHELL", raising=False)
    fake_windows_host(
        rf".;{_WINDOWS_POWERSHELL}",
        {r".\pwsh.exe", r".\pwsh.cmd", r".\powershell.exe", rf"{_WINDOWS_POWERSHELL}\powershell.exe"},
    )

    assert resolve_shell(None, interactive=False)[0] == rf"{_WINDOWS_POWERSHELL}\powershell.exe"

    fake_windows_host(rf".;{_TRUSTED_BIN}", {r".\pwsh.exe", r".\powershell.cmd"})
    with pytest.raises(ShellExecutionError, match="Neither 'pwsh' nor 'powershell'"):
        resolve_shell(None, interactive=False)


def test_resolve_shell_windows_resolves_bare_overrides(
    fake_windows_host: _FakeWindowsHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_FRAMEWORK_SHELL", raising=False)
    fake_windows_host(f"{_POWERSHELL_7};{_TRUSTED_BIN}", {rf"{_POWERSHELL_7}\pwsh.exe", rf"{_TRUSTED_BIN}\bash.exe"})

    assert resolve_shell("pwsh -NoProfile", interactive=True) == [rf"{_POWERSHELL_7}\pwsh.exe", "-NoProfile"]
    assert resolve_shell(["bash", "--norc"], interactive=True) == [rf"{_TRUSTED_BIN}\bash.exe", "--norc"]
    monkeypatch.setenv("AGENT_FRAMEWORK_SHELL", "bash")
    assert resolve_shell(None, interactive=False) == [rf"{_TRUSTED_BIN}\bash.exe", "-c"]


def test_resolve_shell_windows_rejects_a_bare_override_found_only_in_the_current_directory(
    fake_windows_host: _FakeWindowsHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_FRAMEWORK_SHELL", raising=False)
    fake_windows_host(f".;{_TRUSTED_BIN}", {r".\bash.exe", "bash.exe"})

    with pytest.raises(ShellExecutionError, match="'bash'"):
        resolve_shell("bash", interactive=True)
    monkeypatch.setenv("AGENT_FRAMEWORK_SHELL", "bash")
    with pytest.raises(ShellExecutionError, match="'bash'"):
        resolve_shell(None, interactive=True)


@pytest.mark.parametrize(
    "shell",
    [
        [rf"{_POWERSHELL_7}\pwsh.exe", "-NoProfile"],
        [r".\pwsh.exe"],
        ["/opt/pwsh"],
    ],
)
def test_resolve_shell_windows_keeps_explicit_paths(fake_windows_host: _FakeWindowsHost, shell: list[str]) -> None:
    fake_windows_host(_TRUSTED_BIN, set())

    assert resolve_shell(shell, interactive=True) == shell


def test_find_executable_searches_only_fully_qualified_path_entries(fake_windows_host: _FakeWindowsHost) -> None:
    fake_windows_host(
        rf".;;bin;C:Tools;\rooted;{_TRUSTED_BIN}",
        {
            r".\docker.exe",
            r"bin\docker.exe",
            r"C:Tools\docker.exe",
            r"\rooted\docker.exe",
            rf"{_TRUSTED_BIN}\docker.exe",
        },
    )

    assert find_executable("docker") == rf"{_TRUSTED_BIN}\docker.exe"


def test_find_executable_returns_none_when_only_current_directory_dependent_entries_match(
    fake_windows_host: _FakeWindowsHost,
) -> None:
    fake_windows_host(
        rf".;;bin;C:Tools;\rooted;{_TRUSTED_BIN}",
        {r".\docker.exe", "docker.exe", r"bin\docker.exe", r"C:Tools\docker.exe", r"\rooted\docker.exe"},
    )

    assert find_executable("docker") is None


def test_find_executable_returns_the_first_match_in_path_order(fake_windows_host: _FakeWindowsHost) -> None:
    fake_windows_host(r"C:\First;C:\Second", {r"C:\First\docker.exe", r"C:\Second\docker.exe"})

    assert find_executable("docker") == r"C:\First\docker.exe"


@pytest.mark.parametrize(
    ("name", "expected"),
    [("pwsh", None), ("pwsh.exe", None), ("pwsh.cmd", rf"{_TRUSTED_BIN}\pwsh.cmd")],
)
def test_find_executable_adds_exe_only_to_names_without_an_extension(
    fake_windows_host: _FakeWindowsHost, name: str, expected: str | None
) -> None:
    fake_windows_host(_TRUSTED_BIN, {rf"{_TRUSTED_BIN}\pwsh.cmd"})

    assert find_executable(name) == expected


def test_find_executable_accepts_quoted_and_unc_path_entries(fake_windows_host: _FakeWindowsHost) -> None:
    fake_windows_host(
        r'"C:\Program Files\Docker";\\server\share\bin',
        {r"C:\Program Files\Docker\docker.exe", r"\\server\share\bin\podman.exe"},
    )

    assert find_executable("docker") == r"C:\Program Files\Docker\docker.exe"
    assert find_executable("podman") == r"\\server\share\bin\podman.exe"


@pytest.mark.parametrize(
    "name",
    [
        r"C:\tools\docker.exe",
        r"\\server\share\docker.exe",
        r".\docker.exe",
        r"bin\docker.exe",
        "C:docker.exe",
        r"\docker.exe",
        "/usr/bin/docker",
    ],
)
def test_resolve_executable_returns_names_with_a_directory_or_drive_unchanged(
    fake_windows_host: _FakeWindowsHost, name: str
) -> None:
    fake_windows_host(_TRUSTED_BIN, set())

    assert resolve_executable(name) == name


def test_resolve_executable_never_falls_back_to_the_bare_name_on_windows(fake_windows_host: _FakeWindowsHost) -> None:
    fake_windows_host(f".;{_TRUSTED_BIN}", {r".\docker.exe", "docker.exe"})

    with pytest.raises(FileNotFoundError, match="'docker'"):
        resolve_executable("docker")


def test_resolve_executable_returns_names_unchanged_on_other_platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("PATH", "")

    assert resolve_executable("docker") == "docker"


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
    argv = resolve_shell("/opt/pwsh -NoProfile -Command", interactive=False)
    assert argv[-1] == "-Command"
    # No second -Command appended.
    assert argv.count("-Command") == 1


def test_interactive_does_not_append_command_flag() -> None:
    argv = resolve_shell("/bin/bash --noprofile", interactive=True)
    assert "-c" not in argv


@pytest.mark.skipif(sys.platform != "win32", reason="Windows executable lookup")
def test_windows_lookup_ignores_executables_in_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The files are empty and never started: the lookup only inspects the file system.
    for name in ("pwsh.exe", "pwsh.cmd", "powershell.exe", "powershell.cmd", "docker.exe"):
        (tmp_path / name).write_text("")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_FRAMEWORK_SHELL", raising=False)

    shell = Path(resolve_shell(None, interactive=False)[0])
    runtime = find_executable("docker")

    assert shell.is_absolute()
    assert shell.parent != tmp_path
    assert runtime is None or Path(runtime).parent != tmp_path
