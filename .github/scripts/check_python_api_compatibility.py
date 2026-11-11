# Copyright (c) Microsoft. All rights reserved.

"""Check Python API compatibility against a pull request's base commit.

Compare public enum member value expressions statically, without importing packages.
Leave other attribute values to Griffe's compatibility policy.
"""

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
    Attribute,
    AttributeChangedValueBreakage,
    Breakage,
    Class,
    ExplanationStyle,
    ExprCall,
    Object,
    find_breaking_changes,
    load,
)

_UNRELEASED_DECORATORS = frozenset(
    {
        "agent_framework._feature_stage.experimental",
        "agent_framework._feature_stage.release_candidate",
    }
)
_GRIFFE_VERSION = version("griffe")
_PACKAGE_STATUS_ROW = re.compile(
    r"^\| `(?P<name>[^`]+)` \| `(?P<path>python/packages/[^`]+)` \| `(?P<state>[^`]+)` \|"
    r"(?: `[^`]+` \|)?$"
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


def _unreleased_owner(obj: Object | Alias) -> str | None:
    current = _resolved(obj)
    while current is not None:
        decorators = getattr(current, "decorators", ())
        if any(
            decorator.callable_path in _UNRELEASED_DECORATORS
            for decorator in decorators
        ):
            return str(current.path)
        current = current.parent
    return None


def _is_enum(cls: Class, seen: set[str] | None = None) -> bool:
    seen = set() if seen is None else seen
    if cls.path in seen:
        return False
    seen.add(cls.path)
    if any(
        (base if isinstance(base, str) else base.canonical_path)
        in {
            "enum.Enum",
            "enum.IntEnum",
            "enum.StrEnum",
            "enum.Flag",
            "enum.IntFlag",
            "enum.ReprEnum",
        }
        for base in cls.bases
    ):
        return True
    return any(
        _is_enum(base, seen) for base in cls.resolved_bases if isinstance(base, Class)
    )


def _enum_value_changes(
    old: Object | Alias,
    new: Object | Alias,
    seen: set[tuple[str, str]] | None = None,
) -> Iterator[tuple[Object, AttributeChangedValueBreakage]]:
    old_obj, new_obj = _resolved(old), _resolved(new)
    if (
        old_obj is None
        or new_obj is None
        or old_obj.kind != new_obj.kind
        or not (old_obj.is_module or old_obj.is_class)
    ):
        return
    seen = set() if seen is None else seen
    paths = (old_obj.path, new_obj.path)
    if paths in seen:
        return
    seen.add(paths)
    is_enum = isinstance(old_obj, Class) and _is_enum(old_obj)
    new_members = new_obj.all_members
    for name, old_member in old_obj.all_members.items():
        if not old_member.is_public or name not in new_members:
            continue
        new_member = new_members[name]
        old_attribute, new_attribute = _resolved(old_member), _resolved(new_member)
        if (
            is_enum
            and isinstance(old_attribute, Attribute)
            and isinstance(new_attribute, Attribute)
            and "class-attribute" in old_attribute.labels
            and old_attribute.value is not None
            and not (
                isinstance(old_attribute.value, ExprCall)
                and old_attribute.value.function.canonical_path == "enum.nonmember"
            )
            and str(old_attribute.value) != str(new_attribute.value)
        ):
            yield (
                old_attribute,
                AttributeChangedValueBreakage(
                    new_attribute, old_attribute.value, new_attribute.value
                ),
            )
        yield from _enum_value_changes(old_member, new_member, seen)


def _published_breaking_changes(old: Object, new: Object) -> Iterator[Breakage]:
    for breakage in find_breaking_changes(old, new):
        try:
            old_breakage_obj = old.modules_collection.get_member(breakage.obj.path)
        except KeyError:
            old_breakage_obj = breakage.obj
        if _unreleased_owner(old_breakage_obj) is None:
            yield breakage
    for old_member, breakage in _enum_value_changes(old, new):
        if _unreleased_owner(old_member) is None:
            yield breakage


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
        "--repo", type=Path, default=Path.cwd(), help="Trusted repository checkout"
    )
    parser.add_argument(
        "--current-source",
        type=Path,
        help="Extracted pull request source; defaults to the repository checkout",
    )
    parser.add_argument("--acknowledge-breaking-changes", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    current_source = (
        args.current_source.resolve() if args.current_source is not None else repo
    )
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
            try:
                new_package = load(
                    spec.module,
                    search_paths=[current_source / spec.search_path],
                    allow_inspection=False,
                    resolve_aliases=True,
                )
            except ModuleNotFoundError:
                breakage_count += 1
                print(
                    f"::warning title={spec.module}::"
                    "Released public import package was removed"
                )
                print("::endgroup::")
                continue

            for breakage in _published_breaking_changes(old_package, new_package):
                breakage_count += 1
                explanation = breakage.explain(style=ExplanationStyle.GITHUB)
                source_prefix = f"file={current_source.as_posix()}/"
                print(explanation.replace(source_prefix, "file=", 1))

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
