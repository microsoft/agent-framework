# Copyright (c) Microsoft. All rights reserved.

"""Run a task only in packages that have changed files."""

import argparse
import glob
import sys
from pathlib import Path

import tomli
from poethepoet.app import PoeThePoet
from rich import print


def discover_projects(workspace_pyproject_file: Path) -> list[Path]:
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


def get_changed_packages(projects: list[Path], changed_files: list[str], workspace_root: Path) -> set[Path]:
    """Determine which packages have changed files."""
    changed_packages: set[Path] = set()
    core_package_changed = False

    for file_path in changed_files:
        # Strip 'python/' prefix if present (when git diff is run from repo root)
        file_path_str = str(file_path)
        if file_path_str.startswith("python/"):
            file_path_str = file_path_str[7:]  # Remove 'python/' prefix

        # Convert to absolute path if relative
        abs_path = Path(file_path_str)
        if not abs_path.is_absolute():
            abs_path = workspace_root / file_path_str

        # Check which package this file belongs to
        for project in projects:
            project_abs = workspace_root / project
            try:
                # Check if the file is within this project directory
                abs_path.relative_to(project_abs)
                changed_packages.add(project)
                # Check if the core package was changed
                if project == Path("packages/core"):
                    core_package_changed = True
                break
            except ValueError:
                # File is not in this project
                continue

    # If core package changed, check all packages
    if core_package_changed:
        print("[yellow]Core package changed - checking all packages[/yellow]")
        return set(projects)

    return changed_packages


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a task only in packages with changed files.")
    parser.add_argument("task", help="The task name to run")
    parser.add_argument("files", nargs="*", help="Changed files to determine which packages to run")
    args = parser.parse_args()

    pyproject_file = Path(__file__).parent / "pyproject.toml"
    workspace_root = pyproject_file.parent
    projects = discover_projects(pyproject_file)

    # If no files specified, run in all packages (default behavior)
    if not args.files or args.files == ["."]:
        print(f"[yellow]No specific files provided, running {args.task} in all packages[/yellow]")
        changed_packages = set(projects)
    else:
        changed_packages = get_changed_packages(projects, args.files, workspace_root)
        if changed_packages:
            print(f"[cyan]Detected changes in packages: {', '.join(str(p) for p in sorted(changed_packages))}[/cyan]")
        else:
            print(f"[yellow]No changes detected in any package, skipping {args.task}[/yellow]")
            return

    # Run the task in changed packages
    for project in sorted(changed_packages):
        tasks = extract_poe_tasks(project / "pyproject.toml")
        if args.task in tasks:
            print(f"Running task {args.task} in {project}")
            app = PoeThePoet(cwd=project)
            result = app(cli_args=[args.task])
            if result:
                sys.exit(result)
        else:
            print(f"Task {args.task} not found in {project}")


if __name__ == "__main__":
    main()
