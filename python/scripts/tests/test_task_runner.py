# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path

from scripts.task_runner import discover_projects


def test_discover_projects_ignores_glob_matches_without_pyproject(tmp_path: Path) -> None:
    workspace_pyproject = tmp_path / "pyproject.toml"
    workspace_pyproject.write_text('[tool.uv.workspace]\nmembers = ["packages/*"]\n')

    valid_project = tmp_path / "packages" / "valid"
    valid_project.mkdir(parents=True)
    (valid_project / "pyproject.toml").write_text('[project]\nname = "valid"\nversion = "1.0.0"\n')
    (tmp_path / "packages" / "stale").mkdir()

    assert discover_projects(workspace_pyproject) == [Path("packages/valid")]
