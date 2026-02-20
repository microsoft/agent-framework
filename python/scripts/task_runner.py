# Copyright (c) Microsoft. All rights reserved.

"""Shared utilities for running poe tasks across workspace packages in parallel."""

import concurrent.futures
import glob
import os
import subprocess
import sys
import time
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


def _run_task_subprocess(project: Path, task: str, workspace_root: Path) -> tuple[Path, str, int, str, str, float]:
    """Run a single poe task in a project directory via subprocess."""
    start = time.monotonic()
    cwd = workspace_root / project
    result = subprocess.run(
        ["uv", "run", "poe", task],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - start
    return (project, task, result.returncode, result.stdout, result.stderr, elapsed)


def _run_sequential(work_items: list[tuple[Path, str]]) -> None:
    """Run tasks sequentially using in-process PoeThePoet (streaming output)."""
    from poethepoet.app import PoeThePoet

    for project, task in work_items:
        print(f"Running task {task} in {project}")
        app = PoeThePoet(cwd=project)
        result = app(cli_args=[task])
        if result:
            sys.exit(result)


def _run_parallel(work_items: list[tuple[Path, str]], workspace_root: Path) -> None:
    """Run all (package × task) combinations in parallel via subprocesses."""
    max_workers = min(len(work_items), os.cpu_count() or 4)
    failures: list[tuple[Path, str, str, str]] = []
    completed = 0
    total = len(work_items)

    print(f"[cyan]Running {total} task(s) in parallel (max {max_workers} workers)...[/cyan]")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_task_subprocess, project, task, workspace_root): (project, task)
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
            print(f"\n[red]{'='*60}[/red]")
            print(f"[red]FAILED: {task} in {project}[/red]")
            if stdout.strip():
                print(stdout)
            if stderr.strip():
                sys.stderr.write(stderr)
        sys.exit(1)

    print(f"\n[green]All {total} task(s) passed ✓[/green]")


def run_tasks(work_items: list[tuple[Path, str]], workspace_root: Path, *, sequential: bool = False) -> None:
    """Run work items either in parallel or sequentially.

    Single items use in-process PoeThePoet for streaming output.
    Multiple items use parallel subprocesses by default.
    """
    if not work_items:
        print("[yellow]No matching tasks found in any package[/yellow]")
        return

    if sequential or len(work_items) == 1:
        _run_sequential(work_items)
    else:
        _run_parallel(work_items, workspace_root)
