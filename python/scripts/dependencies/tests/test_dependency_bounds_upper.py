# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path
from subprocess import CompletedProcess

from packaging.version import Version

from scripts.dependencies._dependency_bounds_upper_impl import (
    _build_internal_graph,
    _build_workspace_package_map,
    _resolve_internal_editables,
    _run_tasks,
)


def test_upper_bound_probe_is_independent_from_parent_workspace(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[dependency-groups]\ndev = []\n")
    project_dir = tmp_path / "packages" / "provider"
    project_dir.mkdir(parents=True)
    (project_dir / "pyproject.toml").write_text(
        """
[project]
name = "agent-framework-provider"
version = "1.0.0"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=9"]
feature = ["httpx>=0.28"]

[dependency-groups]
test = ["pytest-cov>=7"]
"""
    )
    internal_editable = tmp_path / "packages" / "core"
    captured_commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs) -> CompletedProcess[str]:
        captured_commands.append(command)
        return CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("scripts.dependencies._dependency_bounds_upper_impl.subprocess.run", fake_run)

    success, error = _run_tasks(
        project_dir,
        workspace_root=tmp_path,
        tasks=["pyright"],
        internal_editables=[internal_editable],
        resolution="highest",
        dependency_pin=("fastapi", Version("0.139.2")),
        dependency_groups=["test"],
        include_dev_extra=True,
        optional_extras=["feature"],
        timeout_seconds=60,
    )

    assert success
    assert error is None
    assert len(captured_commands) == 1
    command = captured_commands[0]
    assert "--isolated" in command
    assert "--no-project" not in command
    assert command[command.index("--package") + 1] == "agent-framework-provider"
    assert command[command.index("--group") + 1] == "test"
    assert command.count("--extra") == 2
    assert "dev" in command
    assert "feature" in command
    assert str(internal_editable) in command
    assert "fastapi==0.139.2" in command


def test_internal_editables_exclude_unselected_all_extra(tmp_path: Path) -> None:
    packages_dir = tmp_path / "packages"
    project_files = {
        "target": """
[project]
name = "agent-framework-target"
version = "1.0.0"
dependencies = ["agent-framework-core"]

[project.optional-dependencies]
dev = ["agent-framework-helper"]
""",
        "core": """
[project]
name = "agent-framework-core"
version = "1.0.0"
dependencies = []

[project.optional-dependencies]
all = ["agent-framework-unrelated"]
""",
        "helper": """
[project]
name = "agent-framework-helper"
version = "1.0.0"
dependencies = ["agent-framework-core"]
""",
        "unrelated": """
[project]
name = "agent-framework-unrelated"
version = "1.0.0"
dependencies = []
""",
    }
    for package_path, content in project_files.items():
        project_dir = packages_dir / package_path
        project_dir.mkdir(parents=True)
        (project_dir / "pyproject.toml").write_text(content)

    package_map = _build_workspace_package_map(tmp_path)
    graph = _build_internal_graph(tmp_path, package_map)
    editables = _resolve_internal_editables("agent-framework-target", package_map, graph)

    assert packages_dir / "core" in editables
    assert packages_dir / "helper" in editables
    assert packages_dir / "unrelated" not in editables
