#!/usr/bin/env python3
"""Run a digest-bound verification request without private code or credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from pr_repair_worker import python_verify, requested_verify

MAX_REQUEST = 2 * 1024 * 1024


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate request key")
        result[key] = value
    return result


def _load(data: bytes):
    if len(data) > MAX_REQUEST:
        raise ValueError("Request exceeds size bound")
    return json.loads(data, object_pairs_hook=_object)


def validate_request(data: bytes, digest: str, checkout: Path, repository: str) -> dict:
    if (
        not re.fullmatch(r"[0-9a-f]{64}", digest)
        or hashlib.sha256(data).hexdigest() != digest
    ):
        raise ValueError("Request digest mismatch")
    request = _load(data)
    required = {
        "schema_version",
        "repo",
        "automation_sha",
        "snapshot_sha256",
        "kind",
        "head_sha",
        "base_sha",
        "replacements",
        "toolchain",
    }
    if (
        not isinstance(request, dict)
        or not required <= request.keys()
        or request.keys() - required - {"packages", "targets", "request_id"}
    ):
        raise ValueError("Invalid request schema")
    if type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise ValueError("Unsupported request schema")
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or request["repo"] != repository
    ):
        raise ValueError("Repository binding mismatch")
    for key in ("automation_sha", "head_sha", "base_sha"):
        if not isinstance(request[key], str) or not re.fullmatch(
            r"[0-9a-f]{40}", request[key]
        ):
            raise ValueError("Invalid frozen revision")
    if not isinstance(request["snapshot_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", request["snapshot_sha256"]
    ):
        raise ValueError("Invalid snapshot digest")
    if "request_id" in request and (
        not isinstance(request["request_id"], str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", request["request_id"])
    ):
        raise ValueError("Invalid request ID")
    code, current = python_verify._run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], timeout=30
    )
    if code or current.decode().strip() != request["automation_sha"]:
        raise ValueError("Worker checkout does not match frozen automation")
    trusted_toolchain = _load(
        (checkout / ".github/pr-repair-toolchain.json").read_bytes()
    )
    if (
        not isinstance(request["toolchain"], dict)
        or set(request["toolchain"]) != {"python_image", "dotnet_image"}
        or request["toolchain"] != trusted_toolchain
    ):
        raise ValueError("Toolchain does not match trusted policy")
    for image in request["toolchain"].values():
        python_verify._validate_image(image)
    replacements = request["replacements"]
    if (
        not isinstance(replacements, dict)
        or len(replacements) > 12
        or any(not isinstance(value, str) for value in replacements.values())
    ):
        raise ValueError("Invalid replacements")
    python_verify._validate_source_replacements(
        replacements, {path: "" for path in replacements}
    )
    if request["kind"] == "python":
        packages = request.get("packages")
        if (
            "targets" in request
            or not isinstance(packages, list)
            or not 1 <= len(packages) <= 6
            or any(
                not isinstance(package, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", package)
                for package in packages
            )
        ):
            raise ValueError("Invalid package selection")
        if any(
            not path.startswith("python/packages/") or not path.endswith(".py")
            for path in replacements
        ):
            raise ValueError("Python request contains unsupported replacements")
    elif request["kind"] == "requested":
        targets = request.get("targets")
        if (
            "packages" in request
            or not isinstance(targets, dict)
            or set(targets) - {"python", "dotnet"}
            or not targets
            or not any(targets.values())
        ):
            raise ValueError("Invalid verification targets")
        if any(
            not isinstance(items, list)
            or len(items) > 6
            or any(not isinstance(item, str) for item in items)
            for items in targets.values()
        ):
            raise ValueError("Invalid verification targets")
    else:
        raise ValueError("Unknown verification kind")
    return request


def _public_objects(repository: str, revisions: list[str], destination: Path) -> None:
    commands = [["git", "init", "--bare", str(destination)]]
    for sha in dict.fromkeys(revisions):
        commands.append(
            [
                "git",
                "-C",
                str(destination),
                "-c",
                "credential.helper=",
                "fetch",
                "--no-tags",
                "--depth=1",
                "--",
                f"https://github.com/{repository}.git",
                sha,
            ]
        )
    for command in commands:
        code, _ = python_verify._run(command, timeout=180)
        if code:
            raise ValueError("Unable to fetch public frozen source")


def sanitize_result(result: dict, request: dict) -> dict:
    # This import is deliberately required, never an optional fallback to raw logs.
    from pr_repair_worker.diagnostics import extract_diagnostics

    clean = {
        key: result[key]
        for key in ("passed", "checks_started", "checks_completed", "source_unchanged")
    }
    if any(type(value) is not bool for value in clean.values()):
        raise ValueError("Invalid verifier result flags")
    clean["commands"] = result.get("commands", [])
    clean["output"] = extract_diagnostics(result.get("output", ""))
    toolchain = request["toolchain"]
    if request["kind"] == "python":
        clean["image_id"] = toolchain["python_image"]
    else:
        clean["images"] = {
            language: toolchain[language + "_image"]
            for language, targets in request["targets"].items()
            if targets
        }
    clean["results"] = []
    for item in result.get("results", []):
        if (
            item.get("kind") not in {"quality", "typing", "tests"}
            or type(item.get("passed")) is not bool
        ):
            raise ValueError("Invalid command result")
        diagnostics = extract_diagnostics(item.get("output", ""))
        clean["results"].append(
            {
                "command": item["command"],
                "kind": item["kind"],
                "passed": item["passed"],
                "language": item.get("language", "python"),
                "output": diagnostics,
            }
        )
    return clean


def run_request(data: bytes, digest: str, checkout: Path, repository: str) -> dict:
    request = validate_request(data, digest, checkout, repository)
    images = request["toolchain"]
    with tempfile.TemporaryDirectory(prefix="public-pr-verification-") as root:
        repo = Path(root) / "objects.git"
        _public_objects(repository, [request["base_sha"], request["head_sha"]], repo)
        if request["kind"] == "python":
            result = python_verify.verify_revision(
                repo,
                request["head_sha"],
                request["replacements"],
                request["packages"],
                trusted_sha=request["base_sha"],
                image=images["python_image"],
                collect_all=True,
            )
        else:
            result = requested_verify.verify_requested_revision(
                repo,
                request["head_sha"],
                request["replacements"],
                trusted_sha=request["base_sha"],
                targets=request["targets"],
                images={
                    "python": images["python_image"],
                    "dotnet": images["dotnet_image"],
                },
            )
    return {
        "schema_version": 1,
        "request_sha256": digest,
        "snapshot_sha256": request["snapshot_sha256"],
        "result": sanitize_result(result, request),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if (
            os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
        ):
            raise ValueError(
                "Verification requires an ephemeral GitHub-hosted worker job"
            )
        with args.request.open("rb") as source:
            data = source.read(MAX_REQUEST + 1)
        result = run_request(
            data,
            args.request_sha256,
            Path(__file__).resolve().parents[2],
            os.environ.get("GITHUB_REPOSITORY", ""),
        )
        encoded = json.dumps(result, sort_keys=True).encode()
        if len(encoded) > MAX_REQUEST:
            raise ValueError("Verification result exceeds size bound")
        args.output.write_bytes(encoded)
        return 0
    except Exception:  # noqa: BLE001 - the public CLI must never expose raw failure details
        # No source, raw logs, exception details, or request fields are printed.
        print("Verification request failed validation or setup.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
