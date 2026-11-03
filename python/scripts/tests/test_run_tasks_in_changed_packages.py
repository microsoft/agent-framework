# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for changed-package path routing."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.run_tasks_in_changed_packages import get_changed_packages

PROJECTS = [Path("packages/core"), Path("packages/redis")]


@pytest.mark.parametrize("package", ["core", "redis"])
@pytest.mark.parametrize("spelling", ["forward", "native", "dot-forward", "dot-native"])
def test_repository_relative_paths_select_package(tmp_path: Path, package: str, spelling: str) -> None:
    workspace_root = tmp_path / "python"
    relative = Path("python") / "packages" / package / "example.py"
    paths = {
        "forward": f"python/packages/{package}/example.py",
        "native": str(relative),
        "dot-forward": f"./python/packages/{package}/example.py",
        "dot-native": f".{os.sep}{relative}",
    }

    assert get_changed_packages(PROJECTS, [paths[spelling]], workspace_root) == (
        {Path("packages") / package},
        package == "core",
    )


def test_existing_workspace_relative_and_absolute_paths_select_core(tmp_path: Path) -> None:
    workspace_root = tmp_path / "python"
    relative = Path("packages/core/example.py")
    paths = [
        relative.as_posix(),
        str(relative),
        f"./{relative.as_posix()}",
        f".{os.sep}{relative}",
        str(workspace_root / relative),
    ]

    for file_path in paths:
        assert get_changed_packages(PROJECTS, [file_path], workspace_root) == ({PROJECTS[0]}, True), file_path


@pytest.mark.skipif(os.name != "nt", reason="UNC paths use native Windows semantics.")
def test_unc_absolute_path_selects_core() -> None:
    workspace_root = Path(r"\\server\share\repo\python")
    file_path = workspace_root / PROJECTS[0] / "example.py"

    assert get_changed_packages(PROJECTS, [str(file_path)], workspace_root) == ({PROJECTS[0]}, True)


@pytest.mark.skipif(os.name == "nt", reason="Backslash is a path separator on Windows.")
def test_posix_literal_backslash_package_keeps_its_identity(tmp_path: Path) -> None:
    workspace_root = tmp_path / "python"
    literal_package = Path(r"packages/core\notes")
    file_path = Path("python") / literal_package / "example.py"

    assert get_changed_packages([*PROJECTS, literal_package], [str(file_path)], workspace_root) == (
        {literal_package},
        False,
    )
