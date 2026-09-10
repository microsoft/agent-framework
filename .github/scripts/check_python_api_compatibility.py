# Copyright (c) Microsoft. All rights reserved.

"""Check Python API compatibility against a pull request's base commit."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from griffe import (
    Alias,
    AliasResolutionError,
    ExplanationStyle,
    Object,
    find_breaking_changes,
    load,
)

_EXPERIMENTAL_DECORATOR = "agent_framework._feature_stage.experimental"
_GRIFFE_VERSION = version("griffe")
_PACKAGE_STATUS_ROW = re.compile(
    r"^\| `(?P<name>[^`]+)` \| `(?P<path>python/packages/[^`]+)` \| `(?P<state>[^`]+)` \|$"
)


@dataclass(frozen=True, order=True)
class ModuleSpec:
    """A top-level import package and its owning distribution."""

    module: str
    search_path: Path


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


@contextmanager
def _base_source(repo: Path, base_sha: str) -> Iterator[Path]:
    archive = subprocess.run(
        ["git", "archive", base_sha, "python"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="python-api-base-") as directory:
        subprocess.run(
            ["tar", "-xf", "-", "-C", directory],
            input=archive,
            check=True,
        )
        yield Path(directory)


def _package_states(repo: Path, base_sha: str) -> dict[Path, str]:
    status_document = _git(repo, "show", f"{base_sha}:python/PACKAGE_STATUS.md")
    states: dict[Path, str] = {}

    for line in status_document.splitlines():
        match = _PACKAGE_STATUS_ROW.match(line)
        if match:
            states[Path(match["path"])] = match["state"]

    if not states:
        raise RuntimeError(
            "No package lifecycle states were found in python/PACKAGE_STATUS.md"
        )

    return states


def _module_specs(
    repo: Path, base_sha: str, package_states: dict[Path, str]
) -> list[ModuleSpec]:
    tracked_files = _git(
        repo, "ls-tree", "-r", "--name-only", base_sha, "--", "python/packages"
    )
    specs: set[ModuleSpec] = set()

    for file_name in tracked_files.splitlines():
        parts = Path(file_name).parts
        if (
            len(parts) != 5
            or parts[:2] != ("python", "packages")
            or parts[4] != "__init__.py"
            or parts[3] in {"build", "tests"}
        ):
            continue

        package_path = Path(*parts[:3])
        if package_path.name == "lab":
            continue
        if package_path not in package_states:
            raise RuntimeError(
                f"{package_path} is missing from python/PACKAGE_STATUS.md"
            )
        if package_states[package_path] != "released":
            continue

        specs.add(ModuleSpec(module=parts[3], search_path=package_path))

    return sorted(specs)


def _resolved(obj: Object | Alias) -> Object | None:
    try:
        return obj.final_target if isinstance(obj, Alias) else obj
    except AliasResolutionError:
        return None


def _experimental_owner(obj: Object | Alias) -> str | None:
    current = _resolved(obj)
    while current is not None:
        decorators = getattr(current, "decorators", ())
        if any(
            decorator.callable_path == _EXPERIMENTAL_DECORATOR
            for decorator in decorators
        ):
            return str(current.path)
        current = current.parent
    return None


def _write_summary(
    *,
    checked: int,
    breakages: int,
    acknowledged: bool,
) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = [
        "## Python public API compatibility",
        "",
        f"Compared {checked} released import packages with the PR base using Griffe {_GRIFFE_VERSION}.",
        "",
        f"- Published API breakages: {breakages}",
    ]
    if breakages and acknowledged:
        lines.extend(
            [
                "",
                "Published API breakages were acknowledged by the `breaking change` label.",
            ]
        )
    elif breakages:
        lines.extend(
            [
                "",
                "Restore compatibility or acknowledge the intentional break with the `breaking change` label.",
            ]
        )

    with Path(summary_path).open("a") as summary:
        summary.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-sha", required=True, help="Trusted pull request base commit"
    )
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="Pull request checkout"
    )
    parser.add_argument("--acknowledge-breaking-changes", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    os.chdir(repo)
    package_states = _package_states(repo, args.base_sha)
    specs = _module_specs(repo, args.base_sha, package_states)
    breakage_count = 0

    with _base_source(repo, args.base_sha) as base_source:
        for spec in specs:
            print(f"::group::{spec.module}")
            old_package = load(
                spec.module,
                search_paths=[base_source / spec.search_path],
                allow_inspection=False,
                resolve_aliases=True,
            )
            new_package = load(
                spec.module,
                search_paths=[spec.search_path],
                allow_inspection=False,
                resolve_aliases=True,
            )

            for breakage in find_breaking_changes(old_package, new_package):
                try:
                    old_breakage_obj = old_package.modules_collection.get_member(
                        breakage.obj.path
                    )
                except KeyError:
                    old_breakage_obj = breakage.obj
                experimental_owner = _experimental_owner(old_breakage_obj)

                if experimental_owner is None:
                    breakage_count += 1
                    print(breakage.explain(style=ExplanationStyle.GITHUB))

            print("::endgroup::")

    _write_summary(
        checked=len(specs),
        breakages=breakage_count,
        acknowledged=args.acknowledge_breaking_changes,
    )

    if breakage_count and not args.acknowledge_breaking_changes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
