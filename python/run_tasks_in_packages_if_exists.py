# Copyright (c) Microsoft. All rights reserved.

import argparse
import glob
import sys
from pathlib import Path

import tomli
from poethepoet.app import PoeThePoet
from rich import print


def discover_projects(workspace_pyproject_file: Path, additional_exclude: list[str] | None = None) -> list[Path]:
    with workspace_pyproject_file.open("rb") as f:
        data = tomli.load(f)

    projects = data["tool"]["uv"]["workspace"]["members"]
    exclude = data["tool"]["uv"]["workspace"].get("exclude", [])

    # Add additional excludes from command line
    if additional_exclude:
        exclude.extend(additional_exclude)

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tasks in packages if they exist")
    parser.add_argument("task", help="Task name to run")
    parser.add_argument("--exclude", action="append", help="Additional packages to exclude (can be used multiple times)")

    args, unknown_args = parser.parse_known_args()

    pyproject_file = Path(__file__).parent / "pyproject.toml"
    projects = discover_projects(pyproject_file, args.exclude)

    task_name = args.task
    for project in projects:
        tasks = extract_poe_tasks(project / "pyproject.toml")
        if task_name in tasks:
            print(f"Running task {task_name} in {project}")
            app = PoeThePoet(cwd=project)
            # Pass task name and all unknown args to poe
            poe_args = [task_name] + unknown_args

            result = app(cli_args=poe_args)
            if result:
                sys.exit(result)
        else:
            print(f"Task {task_name} not found in {project}")


if __name__ == "__main__":
    main()
