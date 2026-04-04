# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: INP001

"""Refresh dev dependency pins across the Python workspace."""

from __future__ import annotations

import logging
import argparse
from dataclasses import dataclass
from pathlib import Path

import tomli
from rich import print

from scripts.dependencies._dependency_bounds_upper_impl import (
    VersionCatalog,
    _apply_package_replacements,
    _collect_dev_pin_replacements,
    _load_lock_versions,
)
from scripts.task_runner import discover_projects

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class WorkspaceProject:
    """Workspace project metadata used for dev dependency pin refresh."""

    name: str
    project_path: str
    pyproject_path: str
    pyproject_file: Path


def _read_project_name(pyproject_file: Path) -> str:
    """Return the normalized project name declared in a pyproject file."""
    with pyproject_file.open("rb") as f:
        data = tomli.load(f)

    project = data.get("project", {}) or {}
    project_name = str(project.get("name", "")).strip()
    return project_name or pyproject_file.parent.name


def _discover_workspace_projects(workspace_root: Path) -> list[WorkspaceProject]:
    """Return the root project plus all package projects in the workspace."""
    workspace_pyproject = workspace_root / "pyproject.toml"
    projects = [
        WorkspaceProject(
            name=_read_project_name(workspace_pyproject),
            project_path=".",
            pyproject_path="pyproject.toml",
            pyproject_file=workspace_pyproject,
        )
    ]

    # The root project carries the repo-wide dev toolchain pins, while package pyprojects may
    # carry package-specific dev extras/groups. Refresh both surfaces in one pass so the
    # workspace stays internally consistent after a tooling bump.
    # Reuse the shared workspace discovery logic so this script stays aligned with the rest
    # of the repo-level task runners when packages are added or moved.
    for project in sorted(discover_projects(workspace_pyproject), key=lambda value: str(value)):
        pyproject_file = workspace_root / project / "pyproject.toml"
        if not pyproject_file.exists():
            continue

        projects.append(
            WorkspaceProject(
                name=_read_project_name(pyproject_file),
                project_path=str(project),
                pyproject_path=str(project / "pyproject.toml"),
                pyproject_file=pyproject_file,
            )
        )

    return projects


def _normalize_filter(value: str) -> str:
    """Normalize a package filter for matching project names and paths."""
    normalized = value.strip().strip("/").lower()
    return normalized or "."


def _select_projects(projects: list[WorkspaceProject], package_filters: list[str] | None) -> list[WorkspaceProject]:
    """Filter workspace projects by package name or workspace path if requested."""
    if not package_filters:
        return projects

    normalized_filters = {_normalize_filter(value) for value in package_filters if value.strip()}
    selected: list[WorkspaceProject] = []
    for project in projects:
        normalized_path = _normalize_filter(project.project_path)
        candidates = {project.name.lower(), normalized_path}
        if normalized_path != ".":
            candidates.add(f"./{normalized_path}")

        if candidates & normalized_filters:
            selected.append(project)

    return selected


def main() -> None:
    """Refresh exact dev dependency pins in workspace pyproject files."""
    parser = argparse.ArgumentParser(
        description=(
            "Refresh dev dependency pins across the workspace pyproject.toml files. "
            "By default, resolves versions from PyPI and falls back to uv.lock when network access is unavailable."
        )
    )
    parser.add_argument(
        "--packages",
        nargs="*",
        default=None,
        help="Optional project filters by workspace path (for example packages/core) or package name.",
    )
    parser.add_argument(
        "--version-source",
        choices=["pypi", "lock"],
        default="pypi",
        help="Version source for selecting the newest dev pin.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned replacements without updating files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show debug logging.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    workspace_root = Path(__file__).resolve().parents[2]
    lock_versions = _load_lock_versions(workspace_root)
    # Reuse the same version catalog as the bound-expansion tooling so dev pin refreshes choose
    # versions with the same PyPI-vs-lock fallback behavior as the dependency validators.
    catalog = VersionCatalog(lock_versions=lock_versions, source=args.version_source)

    selected_projects = _select_projects(
        _discover_workspace_projects(workspace_root),
        package_filters=args.packages,
    )
    logger.debug(f"Selected projects for dev dependency refresh: {[project.pyproject_path for project in selected_projects]}")
    if not selected_projects:
        filters = ", ".join(args.packages or [])
        raise SystemExit(f"No matching workspace projects found for: {filters}")

    updated_projects = 0
    updated_requirements = 0
    for project in selected_projects:
        # Keep the replacement logic centralized in the upper-bound helper so exact dev pins are
        # formatted consistently regardless of whether we update them directly here or while
        # widening runtime dependency bounds.
        replacements = _collect_dev_pin_replacements(project.pyproject_file, catalog=catalog)
        if not replacements:
            continue

        updated_projects += 1
        updated_requirements += len(replacements)
        if args.dry_run:
            print(f"[yellow]Planned updates for {project.pyproject_path}[/yellow]")
            for original, replacement in replacements.items():
                print(f"  - {original} -> {replacement}")
            continue

        _apply_package_replacements(project.pyproject_file, replacements)
        print(
            f"[green]Updated {project.pyproject_path}[/green] "
            f"({project.name}) with {len(replacements)} dev dependency pin refresh(es)."
        )

    if updated_projects == 0:
        print("[green]No dev dependency pin updates were needed.[/green]")
        return

    action = "Would update" if args.dry_run else "Updated"
    print(
        f"[green]{action} {updated_requirements} dev dependency pin(s) "
        f"across {updated_projects} workspace project(s).[/green]"
    )


if __name__ == "__main__":
    main()
