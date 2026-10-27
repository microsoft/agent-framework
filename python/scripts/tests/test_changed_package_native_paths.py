# Copyright (c) Microsoft. All rights reserved.

"""Exercise native changed-package paths and task routing."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import run_tasks_in_changed_packages as runner

PROJECTS = [Path("packages/core"), Path("packages/redis")]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "python"
    root.mkdir()
    return root


@pytest.mark.parametrize("package", ["core", "redis"])
@pytest.mark.parametrize("spelling", ["repo-forward", "repo-native", "dot-forward", "dot-native"])
def test_repository_relative_path_selects_package(workspace: Path, package: str, spelling: str) -> None:
    relative = Path("python") / "packages" / package / "example.py"
    paths = {
        "repo-forward": relative.as_posix(),
        "repo-native": str(relative),
        "dot-forward": "./" + relative.as_posix(),
        "dot-native": "." + os.sep + str(relative),
    }

    assert runner.get_changed_packages(PROJECTS, [paths[spelling]], workspace) == (
        {Path("packages") / package},
        package == "core",
    )


@pytest.mark.parametrize("spelling", ["workspace-forward", "workspace-native", "absolute"])
def test_existing_path_forms_keep_selecting_core(workspace: Path, spelling: str) -> None:
    relative = Path("packages/core/example.py")
    paths = {
        "workspace-forward": relative.as_posix(),
        "workspace-native": str(relative),
        "absolute": str(workspace / relative),
    }

    assert runner.get_changed_packages(PROJECTS, [paths[spelling]], workspace) == ({PROJECTS[0]}, True)


def test_unrelated_path_stays_unselected(workspace: Path) -> None:
    assert runner.get_changed_packages(PROJECTS, ["dotnet/example.cs"], workspace) == (set(), False)


@pytest.mark.skipif(os.name == "nt", reason="Backslash is a filename character on POSIX.")
def test_literal_backslash_package_keeps_its_identity(workspace: Path) -> None:
    literal_package = Path(r"packages/core\notes")
    projects = [*PROJECTS, literal_package]
    file_path = workspace / literal_package / "example.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("", encoding="utf-8")

    assert runner.get_changed_packages(projects, [str(file_path)], workspace) == ({literal_package}, False)
    assert runner.get_changed_packages(projects, [str(Path("python") / literal_package / "example.py")], workspace) == (
        {literal_package},
        False,
    )


@pytest.mark.skipif(os.name != "nt", reason="UNC paths use native Windows semantics.")
def test_absolute_unc_path_keeps_selecting_core() -> None:
    workspace = Path(r"\\server\share\repo\python")
    file_path = workspace / PROJECTS[0] / "example.py"

    assert runner.get_changed_packages(PROJECTS, [str(file_path)], workspace) == ({PROJECTS[0]}, True)


@pytest.mark.parametrize("package", ["core", "redis"])
def test_cli_native_path_routes_local_and_type_tasks(
    workspace: Path, package: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (workspace / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/core", "packages/redis"]\n', encoding="utf-8"
    )
    for project in PROJECTS:
        directory = workspace / project
        directory.mkdir(parents=True)
        (directory / "pyproject.toml").write_text(
            '[tool.poe.tasks]\nlint = "echo unused"\npyright = "echo unused"\n', encoding="utf-8"
        )
    monkeypatch.chdir(workspace)
    monkeypatch.setattr(runner, "__file__", str(workspace / "scripts/run_tasks_in_changed_packages.py"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_tasks_in_changed_packages.py",
            "lint",
            "pyright",
            "--files",
            "." + os.sep + str(Path("python/packages") / package / "example.py"),
            "--seq",
        ],
    )
    run_tasks = Mock()
    monkeypatch.setattr(runner, "run_tasks", run_tasks)

    runner.main()

    selected = Path("packages") / package
    typed = PROJECTS if package == "core" else [selected]
    run_tasks.assert_called_once_with(
        [(selected, "lint"), *((project, "pyright") for project in typed)], workspace, sequential=True
    )
