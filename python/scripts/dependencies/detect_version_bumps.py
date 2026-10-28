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


def changed_package_versions(repo_root: Path, base_ref: str) -> list[str]:
    """Return new workspace manifests and those whose declared version differs from the base."""
    if not base_ref.strip():
        raise ValueError("An explicit PR or merge-group base commit is required")
    base_sha = _git(repo_root, "rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}").strip()
    workspace = tomllib.loads(_git(repo_root, "show", "HEAD:python/pyproject.toml"))["tool"]["uv"]["workspace"]
    changed = _git(
        repo_root,
        "diff",
        "--name-status",
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
    entries = changed.split("\0")[:-1]
    for status, manifest in zip(entries[::2], entries[1::2], strict=True):
        if manifest != "python/pyproject.toml":
            relative = Path(manifest).relative_to("python")
            if len(relative.parts) != 3:
                continue
            project_path = relative.parent.as_posix()
            if not any(fnmatch.fnmatchcase(project_path, pattern) for pattern in workspace["members"]):
                continue
            if any(fnmatch.fnmatchcase(project_path, pattern) for pattern in workspace.get("exclude", [])):
                continue
        current = _version(_git(repo_root, "show", f"HEAD:{manifest}"), manifest)
        # A downgrade also runs validation; it must not provide a way to bypass the gate.
        if status == "A" or current != _version(_git(repo_root, "show", f"{base_sha}:{manifest}"), manifest):
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
