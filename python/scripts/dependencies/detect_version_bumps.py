# Copyright (c) Microsoft. All rights reserved.

"""Detect new packages and release version changes without installing the Python workspace (Python 3.11+)."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import tomllib
from pathlib import Path


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo_root, check=False, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"Git comparison failed: {result.stderr.strip()}")
    return result.stdout


def _version(content: str, manifest: str) -> str:
    version = tomllib.loads(content).get("project", {}).get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"{manifest} must declare a non-empty project.version")
    return version


def _workspace_manifests(repo_root: Path, ref: str) -> set[str]:
    workspace = tomllib.loads(_git(repo_root, "show", f"{ref}:python/pyproject.toml"))["tool"]["uv"]["workspace"]
    manifests = {"python/pyproject.toml"}
    tracked = _git(repo_root, "ls-tree", "-r", "--name-only", "-z", ref, "--", "python/packages")
    for manifest in filter(None, tracked.split("\0")):
        relative = Path(manifest).relative_to("python")
        if len(relative.parts) != 3 or relative.name != "pyproject.toml":
            continue
        project_path = relative.parent.as_posix()
        if not any(fnmatch.fnmatchcase(project_path, pattern) for pattern in workspace["members"]):
            continue
        if any(fnmatch.fnmatchcase(project_path, pattern) for pattern in workspace.get("exclude", [])):
            continue
        manifests.add(manifest)
    return manifests


def changed_package_versions(repo_root: Path, base_ref: str) -> list[str]:
    """Return newly included workspace manifests and those with changed versions."""
    if not base_ref.strip():
        raise ValueError("An explicit PR or merge-group base commit is required")
    base_sha = _git(repo_root, "rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}").strip()
    base_manifests = _workspace_manifests(repo_root, base_sha)
    head_manifests = _workspace_manifests(repo_root, "HEAD")
    newly_included = head_manifests - base_manifests
    changed = _git(
        repo_root,
        "diff",
        "--name-only",
        "-z",
        "--no-renames",
        "--diff-filter=AM",
        base_sha,
        "HEAD",
        "--",
        "python/pyproject.toml",
        "python/packages/*/pyproject.toml",
    )
    bumps: list[str] = []
    candidates = (set(changed.split("\0")) & head_manifests) | newly_included
    for manifest in sorted(candidates):
        current = _version(_git(repo_root, "show", f"HEAD:{manifest}"), manifest)
        # A downgrade also runs validation; it must not provide a way to bypass the gate.
        if manifest in newly_included or current != _version(_git(repo_root, "show", f"{base_sha}:{manifest}"), manifest):
            bumps.append(manifest)
    return sorted(bumps)


def main() -> None:
    """Write the gate decision as a GitHub Actions step output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    bumps = changed_package_versions(Path(__file__).resolve().parents[3], args.base_ref)
    with args.github_output.open("a") as output:
        output.write(f"required={'true' if bumps else 'false'}\n")
    if bumps:
        print("New packages or package version changes require dependency-bounds tests:\n" + "\n".join(bumps))
    else:
        print("No new workspace packages or package version changes; dependency-bounds tests are not required.")


if __name__ == "__main__":
    main()
