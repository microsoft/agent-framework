# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for run_tasks_in_changed_packages."""

from pathlib import Path

from scripts.run_tasks_in_changed_packages import get_changed_packages


def test_get_changed_packages_recognizes_repo_relative_paths() -> None:
    workspace_root = Path("/repo/python")
    projects = [Path("packages/core"), Path("packages/redis")]

    # POSIX spelling with repo prefix
    changed, core_changed = get_changed_packages(
        projects,
        ["python/packages/core/agent_framework/_types.py"],
        workspace_root,
    )
    assert changed == {Path("packages/core")}
    assert core_changed is True

    # Windows native backslash spelling with repo prefix
    changed, core_changed = get_changed_packages(
        projects,
        [r"python\packages\core\agent_framework\_types.py"],
        workspace_root,
    )
    assert changed == {Path("packages/core")}
    assert core_changed is True


def test_get_changed_packages_recognizes_workspace_relative_paths() -> None:
    workspace_root = Path("/repo/python")
    projects = [Path("packages/core"), Path("packages/redis")]

    # Forward slash workspace relative
    changed, core_changed = get_changed_packages(
        projects,
        ["packages/core/agent_framework/_types.py"],
        workspace_root,
    )
    assert changed == {Path("packages/core")}
    assert core_changed is True

    # Windows native backslash workspace relative
    changed, core_changed = get_changed_packages(
        projects,
        [r"packages\core\agent_framework\_types.py"],
        workspace_root,
    )
    assert changed == {Path("packages/core")}
    assert core_changed is True


def test_get_changed_packages_recognizes_dot_prefixed_paths() -> None:
    workspace_root = Path("/repo/python")
    projects = [Path("packages/core")]

    changed, core_changed = get_changed_packages(
        projects,
        ["./python/packages/core/agent_framework/_types.py"],
        workspace_root,
    )
    assert changed == {Path("packages/core")}
    assert core_changed is True

    changed, core_changed = get_changed_packages(
        projects,
        [r".\python\packages\core\agent_framework\_types.py"],
        workspace_root,
    )
    assert changed == {Path("packages/core")}
    assert core_changed is True


def test_get_changed_packages_non_core_package_flag() -> None:
    workspace_root = Path("/repo/python")
    projects = [Path("packages/core"), Path("packages/redis")]

    changed, core_changed = get_changed_packages(
        projects,
        [r"python\packages\redis\agent_framework_redis\_store.py"],
        workspace_root,
    )
    assert changed == {Path("packages/redis")}
    assert core_changed is False


def test_get_changed_packages_absolute_paths(tmp_path: Path) -> None:
    workspace_root = tmp_path / "python"
    project_core = Path("packages/core")
    projects = [project_core]

    file_abs = workspace_root / project_core / "agent_framework" / "_types.py"
    changed, core_changed = get_changed_packages(
        projects,
        [str(file_abs)],
        workspace_root,
    )
    assert changed == {project_core}
    assert core_changed is True


def test_get_changed_packages_ignores_unrelated_files() -> None:
    workspace_root = Path("/repo/python")
    projects = [Path("packages/core"), Path("packages/redis")]

    # Files outside workspace packages
    unrelated = [
        "README.md",
        "python/README.md",
        r"python\pyproject.toml",
        ".github/workflows/ci.yml",
        r"dotnet\packages\Microsoft.Agents.Core\Agent.cs",
    ]
    changed, core_changed = get_changed_packages(
        projects,
        unrelated,
        workspace_root,
    )
    assert changed == set()
    assert core_changed is False


def test_get_changed_packages_multiple_files_and_deduplication() -> None:
    workspace_root = Path("/repo/python")
    projects = [Path("packages/core"), Path("packages/redis")]

    files = [
        "python/packages/core/agent_framework/_types.py",
        r"python\packages\core\agent_framework\__init__.py",
        r"python\packages\redis\agent_framework_redis\_store.py",
        "README.md",
    ]
    changed, core_changed = get_changed_packages(
        projects,
        files,
        workspace_root,
    )
    assert changed == {Path("packages/core"), Path("packages/redis")}
    assert core_changed is True
