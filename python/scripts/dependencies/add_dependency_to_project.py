# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: S603

"""Add a dependency to one workspace package selected by short name or path.

``uv add --package`` expects the published workspace distribution name, while
the root Poe surface intentionally speaks in short repo package names such as
``core``. This wrapper keeps the user-facing selector stable and translates it
just before delegating to uv.
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

import tomli
from rich import print

from scripts.task_runner import discover_projects, project_filter_matches


@dataclass(frozen=True)
class WorkspacePackage:
    """Workspace package metadata needed for `uv add --package`."""

    short_name: str
    project_path: Path
    distribution_name: str


def _load_distribution_name(pyproject_file: Path) -> str:
    with pyproject_file.open("rb") as f:
        data = tomli.load(f)
    return str(data.get("project", {}).get("name", "")).strip()


def _discover_workspace_packages(workspace_root: Path) -> list[WorkspacePackage]:
    workspace_pyproject = workspace_root / "pyproject.toml"
    packages: list[WorkspacePackage] = []
    for project_path in sorted(discover_projects(workspace_pyproject), key=str):
        pyproject_file = workspace_root / project_path / "pyproject.toml"
        if not pyproject_file.exists():
            continue
        distribution_name = _load_distribution_name(pyproject_file)
        if not distribution_name:
            continue
        packages.append(
            WorkspacePackage(
                short_name=project_path.name,
                project_path=project_path,
                distribution_name=distribution_name,
            )
        )
    return packages


def _resolve_workspace_package(workspace_root: Path, project_filter: str) -> WorkspacePackage:
    """Resolve one workspace package from a user-facing selector.

    The wrapper accepts the same short-name/path/distribution-name vocabulary as
    the other root tasks, but errors on ambiguous matches so dependency edits
    never hit the wrong package.
    """
    matches = [
        package
        for package in _discover_workspace_packages(workspace_root)
        if project_filter_matches(package.project_path, project_filter, [package.short_name, package.distribution_name])
    ]
    if not matches:
        raise SystemExit(f"No workspace package matched selector '{project_filter}'.")
    if len(matches) > 1:
        names = ", ".join(sorted(package.short_name for package in matches))
        raise SystemExit(
            f"Package selector '{project_filter}' matched multiple workspace packages: {names}. "
            "Use a more specific short name or path."
        )
    return matches[0]


def main() -> None:
    """Resolve a workspace project selector, then delegate to `uv add`."""
    parser = argparse.ArgumentParser(
        description="Add a dependency to a single workspace package selected by short name, path, or package name."
    )
    parser.add_argument(
        "-P",
        "--package",
        dest="project",
        metavar="PACKAGE",
        required=True,
        help="Workspace package selector, such as `core`.",
    )
    # Keep the old long flag as a silent alias while downstream automation
    # finishes moving to the user-facing ``--package`` spelling.
    parser.add_argument("--project", dest="project", help=argparse.SUPPRESS)
    parser.add_argument("-D", "--dependency", required=True, help="Dependency specifier to add.")
    args = parser.parse_args()

    workspace_root = Path(__file__).resolve().parents[2]
    package = _resolve_workspace_package(workspace_root, args.project)
    print(
        f"[cyan]Adding {args.dependency} to {package.short_name} "
        f"({package.distribution_name})[/cyan]"
    )
    result = subprocess.run(
        ["uv", "add", "--package", package.distribution_name, args.dependency],
        cwd=workspace_root,
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
