# Copyright (c) Microsoft. All rights reserved.

import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

from scripts.dependencies import add_dependency_to_project as add_dependency


def _mock_dependency_add(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    package = add_dependency.WorkspacePackage(
        short_name="core",
        project_path=Path("packages/core"),
        distribution_name="agent-framework-core",
    )
    resolve = Mock(return_value=package)
    run = Mock(return_value=CompletedProcess(args=[], returncode=0))
    monkeypatch.setattr(add_dependency, "_resolve_workspace_package", resolve)
    monkeypatch.setattr(add_dependency.subprocess, "run", run)
    return resolve, run


@pytest.mark.parametrize(
    ("selector_args", "expected_selector"),
    [
        (["-P", "core"], "core"),
        (["--package", "core"], "core"),
        (["--project", "core"], "core"),
        (["--package", "core", "--project", "openai"], "openai"),
        (["--project", "core", "--package", "openai"], "openai"),
    ],
)
def test_main_accepts_selector_spellings(
    monkeypatch: pytest.MonkeyPatch, selector_args: list[str], expected_selector: str
) -> None:
    resolve, run = _mock_dependency_add(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["add_dependency_to_project.py", *selector_args, "--dependency", "httpx"])

    add_dependency.main()

    workspace_root = Path(add_dependency.__file__).resolve().parents[2]
    resolve.assert_called_once_with(workspace_root, expected_selector)
    run.assert_called_once_with(
        ["uv", "add", "--package", "agent-framework-core", "httpx"],
        cwd=workspace_root,
        check=False,
    )


@pytest.mark.parametrize("arguments", [["--dependency", "httpx"], ["--package", "core"]])
def test_main_requires_selector_and_dependency(monkeypatch: pytest.MonkeyPatch, arguments: list[str]) -> None:
    resolve, run = _mock_dependency_add(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["add_dependency_to_project.py", *arguments])

    with pytest.raises(SystemExit) as error:
        add_dependency.main()

    assert error.value.code == 2
    resolve.assert_not_called()
    run.assert_not_called()


def test_help_keeps_legacy_selector_hidden(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    resolve, run = _mock_dependency_add(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["add_dependency_to_project.py", "--help"])

    with pytest.raises(SystemExit) as error:
        add_dependency.main()

    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert "--package" in help_text
    assert "--project" not in help_text
    resolve.assert_not_called()
    run.assert_not_called()
