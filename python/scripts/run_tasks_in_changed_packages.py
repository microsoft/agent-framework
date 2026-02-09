# Copyright (c) Microsoft. All rights reserved.

"""Run task(s) only in packages that have changed files, in parallel by default."""

import argparse
from pathlib import Path

from rich import print
from task_runner import build_work_items, discover_projects, run_tasks


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
    parser = argparse.ArgumentParser(description="Run task(s) in changed packages, in parallel by default.")
    parser.add_argument("tasks", nargs="+", help="Task name(s) to run")
    parser.add_argument("--files", nargs="*", default=None, help="Changed files to determine which packages to run")
    parser.add_argument("--seq", action="store_true", help="Run sequentially instead of in parallel")
    args = parser.parse_args()

    pyproject_file = Path(__file__).parent.parent / "pyproject.toml"
    workspace_root = pyproject_file.parent
    projects = discover_projects(pyproject_file)

    # Determine which packages to check
    if not args.files or args.files == ["."]:
        task_list = ", ".join(args.tasks)
        print(f"[yellow]No specific files provided, running {task_list} in all packages[/yellow]")
        target_packages = sorted(set(projects))
    else:
        changed_packages = get_changed_packages(projects, args.files, workspace_root)
        if changed_packages:
            print(f"[cyan]Detected changes in packages: {', '.join(str(p) for p in sorted(changed_packages))}[/cyan]")
        else:
            print(f"[yellow]No changes detected in any package, skipping[/yellow]")
            return
        target_packages = sorted(changed_packages)

    work_items = build_work_items(target_packages, args.tasks)
    run_tasks(work_items, workspace_root, sequential=args.seq)


if __name__ == "__main__":
    main()
