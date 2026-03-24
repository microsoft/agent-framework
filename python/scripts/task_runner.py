# Copyright (c) Microsoft. All rights reserved.

"""Shared utilities for running Poe tasks across workspace packages.

These helpers centralize workspace discovery, selector matching, and execution
mode so the root task dispatcher and dependency tooling interpret package
filters the same way.
"""

import concurrent.futures
import glob
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from fnmatch import fnmatch
from pathlib import Path

import tomli
from rich import print


def discover_projects(workspace_pyproject_file: Path) -> list[Path]:
    """Discover all workspace projects from pyproject.toml."""
    with workspace_pyproject_file.open("rb") as f:
        data = tomli.load(f)

    projects = data["tool"]["uv"]["workspace"]["members"]
    exclude = data["tool"]["uv"]["workspace"].get("exclude", [])

    all_projects: list[Path] = []
    for project in projects:
        if "*" in project:
            globbed = glob.glob(str(project), root_dir=workspace_pyproject_file.parent)
            globbed_paths = [Path(p) for p in globbed]
            all_projects.extend(globbed_paths)
        else:
            all_projects.append(Path(project))

    for project in exclude:
        if "*" in project:
            globbed = glob.glob(str(project), root_dir=workspace_pyproject_file.parent)
            globbed_paths = [Path(p) for p in globbed]
            all_projects = [p for p in all_projects if p not in globbed_paths]
        else:
            all_projects = [p for p in all_projects if p != Path(project)]

    return all_projects


def extract_poe_tasks(file: Path) -> set[str]:
    """Extract poe task names from a pyproject.toml file."""
    with file.open("rb") as f:
        data = tomli.load(f)

    tasks = set(data.get("tool", {}).get("poe", {}).get("tasks", {}).keys())

    # Check if there is an include too
    include: str | None = data.get("tool", {}).get("poe", {}).get("include", None)
    if include:
        include_file = file.parent / include
        if include_file.exists():
            tasks = tasks.union(extract_poe_tasks(include_file))

    return tasks


def build_work_items(projects: list[Path], task_names: list[str]) -> list[tuple[Path, str]]:
    """Build cross-product of (package, task) for packages that define the task."""
    work_items: list[tuple[Path, str]] = []
    for project in projects:
        available_tasks = extract_poe_tasks(project / "pyproject.toml")
        for task in task_names:
            if task in available_tasks:
                work_items.append((project, task))
    return work_items


def normalize_project_filter(value: str) -> str:
    """Normalize a user-supplied workspace selector.

    Strip presentation differences so short names, relative paths, and globs can
    be compared with one matcher.
    """
    normalized = value.strip().strip("/").replace("\\", "/")
    return normalized or "."


def build_project_filter_candidates(project: Path | str, aliases: Sequence[str] = ()) -> set[str]:
    """Return accepted selector values for one workspace project.

    We accept the workspace path, short package name, and any supplied aliases
    so user-facing ``--package core`` stays stable even when underlying tools
    still need paths or distribution names.
    """
    normalized_path = normalize_project_filter(str(project))
    candidates = {normalized_path}
    if normalized_path == ".":
        candidates.update({"./", "root"})
    else:
        # Accept bare short names like ``core`` alongside ``packages/core`` and
        # ``./packages/core`` so callers do not have to care which form a
        # downstream script prefers.
        path = Path(normalized_path)
        candidates.add(path.name)
        candidates.add(f"./{normalized_path}")

    for alias in aliases:
        normalized_alias = normalize_project_filter(alias)
        if normalized_alias and normalized_alias != ".":
            candidates.add(normalized_alias)

    return {candidate.lower() for candidate in candidates}


def project_filter_matches(project: Path | str, pattern: str, aliases: Sequence[str] = ()) -> bool:
    """Return whether a project matches a user-supplied selector or glob.

    Matching happens against the normalized candidate set so CLI callers can use
    the same selector vocabulary everywhere.
    """
    normalized_pattern = normalize_project_filter(pattern).lower()
    return any(
        fnmatch(candidate, normalized_pattern)
        for candidate in build_project_filter_candidates(project, aliases)
    )


def _run_task_subprocess(
    project: Path,
    task: str,
    workspace_root: Path,
    task_args: Sequence[str] = (),
) -> tuple[Path, str, int, str, str, float]:
    """Run a single poe task in a project directory via subprocess."""
    start = time.monotonic()
    cwd = workspace_root / project
    result = subprocess.run(
        ["uv", "run", "poe", task, *task_args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - start
    return (project, task, result.returncode, result.stdout, result.stderr, elapsed)


def _run_sequential(work_items: list[tuple[Path, str]], task_args: Sequence[str] = ()) -> None:
    """Run tasks sequentially using in-process PoeThePoet (streaming output)."""
    from poethepoet.app import PoeThePoet

    for project, task in work_items:
        print(f"Running task {task} in {project}")
        app = PoeThePoet(cwd=project)
        result = app(cli_args=[task, *task_args])
        if result:
            sys.exit(result)


def _run_parallel(work_items: list[tuple[Path, str]], workspace_root: Path, task_args: Sequence[str] = ()) -> None:
    """Run all (package x task) combinations in parallel via subprocesses."""
    max_workers = min(len(work_items), os.cpu_count() or 4)
    failures: list[tuple[Path, str, str, str]] = []
    completed = 0
    total = len(work_items)

    print(f"[cyan]Running {total} task(s) in parallel (max {max_workers} workers)...[/cyan]")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_task_subprocess, project, task, workspace_root, task_args): (project, task)
            for project, task in work_items
        }
        for future in concurrent.futures.as_completed(futures):
            project, task, returncode, stdout, stderr, elapsed = future.result()
            completed += 1
            progress = f"[{completed}/{total}]"
            if returncode == 0:
                print(f"  [green]✓[/green] {progress} {task} in {project} ({elapsed:.1f}s)")
            else:
                print(f"  [red]✗[/red] {progress} {task} in {project} ({elapsed:.1f}s)")
                failures.append((project, task, stdout, stderr))

    if failures:
        print(f"\n[red]{len(failures)} task(s) failed:[/red]")
        for project, task, stdout, stderr in failures:
            print(f"\n[red]{'=' * 60}[/red]")
            print(f"[red]FAILED: {task} in {project}[/red]")
            if stdout.strip():
                print(stdout)
            if stderr.strip():
                sys.stderr.write(stderr)
        sys.exit(1)

    print(f"\n[green]All {total} task(s) passed ✓[/green]")


def run_tasks(
    work_items: list[tuple[Path, str]],
    workspace_root: Path,
    *,
    sequential: bool = False,
    task_args: Sequence[str] = (),
) -> None:
    """Run work items either in parallel or sequentially.

    Single items use in-process PoeThePoet for streaming output.
    Multiple items use parallel subprocesses by default.
    """
    if not work_items:
        print("[yellow]No matching tasks found in any package[/yellow]")
        return

    if sequential or len(work_items) == 1:
        _run_sequential(work_items, task_args)
    else:
        _run_parallel(work_items, workspace_root, task_args)
