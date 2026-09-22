"""Isolated verification for explicit, trusted Python and .NET repair targets."""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import tarfile
import uuid
from pathlib import Path, PurePosixPath

from . import python_verify as container_tools


def _archive(repo_path: Path, sha: str) -> bytes:
    code, data = container_tools._run(
        ["git", "-C", str(repo_path), "archive", "--format=tar", sha],
        timeout=120,
        limit=container_tools.MAX_ARCHIVE,
        binary=True,
    )
    if code:
        raise ValueError("Unable to archive revision")
    container_tools._validate_archive(data)
    return data


def _dotnet_verify(
    repo_path, head_sha, replacements, projects, trusted_sha, image=None
):
    name = f"devflow-repair-{uuid.uuid4().hex}"
    created = False
    result = {
        "passed": False,
        "commands": [],
        "results": [],
        "checks_started": False,
        "checks_completed": False,
        "source_unchanged": False,
        "image_id": None,
        "output": "",
    }
    output = bytearray()

    def run(command, *, data=None, timeout=600):
        code, captured = container_tools._run(command, data=data, timeout=timeout)
        output.extend(captured)
        del output[: -container_tools.MAX_OUTPUT]
        if code:
            raise RuntimeError("Verification setup failed")
        return captured

    try:
        for sha in (head_sha, trusted_sha):
            if not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise ValueError("Invalid frozen revision")
        if not projects or len(projects) > 6 or len(set(projects)) != len(projects):
            raise ValueError("Invalid project selection")
        for project in projects:
            if (
                container_tools._safe_path(project) != project
                or not re.fullmatch(
                    r"dotnet/(src|tests)/[A-Za-z0-9_./-]+\.csproj", project
                )
                or (
                    project.startswith("dotnet/tests/")
                    and not project.endswith("UnitTests.csproj")
                )
            ):
                raise ValueError("Unsupported project")
        trusted = _archive(repo_path, trusted_sha)
        source = _archive(repo_path, head_sha)
        paths = container_tools._validate_archive(source)
        trusted_paths = container_tools._validate_archive(trusted)
        if not all(project in paths & trusted_paths for project in projects):
            raise ValueError("Project missing in frozen revisions")
        with tarfile.open(fileobj=io.BytesIO(trusted)) as archive:
            sdk = json.load(archive.extractfile("dotnet/global.json"))
        version = sdk.get("sdk", {}).get("version", "")
        if not re.fullmatch(r"10\.0\.[0-9]+", version):
            raise ValueError("Unsupported trusted SDK")
        if sdk.get("test", {}).get("runner") != "Microsoft.Testing.Platform":
            raise ValueError("Unsupported test runner")
        container_tools._validate_image(image)
        expected = container_tools._source_hashes(source)
        container_tools._validate_source_replacements(replacements, expected)
        for path, content in replacements.items():
            expected[path] = hashlib.sha256(content.encode()).hexdigest()
        run(["docker", "pull", image], timeout=180)
        image_id = (
            run(["docker", "image", "inspect", "--format={{.Id}}", image], timeout=30)
            .decode()
            .strip()
        )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise ValueError("Unable to pin SDK image")
        result["image_id"] = image_id
        run(
            [
                "docker",
                "create",
                "--name",
                name,
                *container_tools._container_limits(),
                "--network=bridge",
                "--workdir=/work",
                "--env=DOTNET_CLI_TELEMETRY_OPTOUT=1",
                "--env=DOTNET_NOLOGO=1",
                "--env=GITHUB_ACTIONS=true",
                "--env=CI=true",
                "--env=NUGET_PACKAGES=/work/nuget",
                image_id,
                "sleep",
                "7200",
            ],
            timeout=120,
        )
        created = True
        run(["docker", "start", name], timeout=30)
        run(["docker", "exec", name, "mkdir", "-p", "/work/source"])
        container_tools._copy_in(name, "/work/source", trusted, run)
        execute = ["docker", "exec", "--workdir=/work/source/dotnet", name]
        relative = [p.removeprefix("dotnet/") for p in projects]
        artifacts = ["-p:UseArtifactsOutput=true", "-p:ArtifactsPath=/work/artifacts"]
        for project in relative:
            run(
                [
                    *execute,
                    "dotnet",
                    "restore",
                    project,
                    "-p:TargetFramework=net10.0",
                    *artifacts,
                ],
                timeout=900,
            )
        run(["docker", "network", "disconnect", "bridge", name], timeout=30)
        run(["docker", "exec", name, "rm", "-rf", "/work/source", "/work/artifacts"])
        run(["docker", "exec", name, "mkdir", "-p", "/work/source"])
        container_tools._copy_in(name, "/work/source", source, run)
        if replacements:
            container_tools._copy_in(
                name, "/work/source", container_tools._overlay(replacements), run
            )

        def confirm_source():
            actual = {}
            groups = {str(PurePosixPath(*PurePosixPath(p).parts[:2])) for p in expected}
            for group in sorted(groups):
                code, data = container_tools._copy_out(name, group)
                if code:
                    raise ValueError("Unable to inspect verified source")
                for path, digest in container_tools._source_hashes(data).items():
                    actual[path] = digest
            if actual != expected:
                raise ValueError("Verification modified source")

        # Restoring the frozen head uses cached trusted dependencies only: the
        # container has no network and receives no host filesystem mounts.
        for project in relative:
            run(
                [
                    *execute,
                    "dotnet",
                    "restore",
                    project,
                    "--ignore-failed-sources",
                    "-p:TargetFramework=net10.0",
                    *artifacts,
                ],
                timeout=600,
            )
        confirm_source()
        checks = []
        for project in relative:
            checks.append(
                (
                    "quality",
                    [
                        "dotnet",
                        "build",
                        project,
                        "--no-restore",
                        "--configuration",
                        "Release",
                        "--framework",
                        "net10.0",
                        "--warnaserror",
                        *artifacts,
                    ],
                )
            )
            if project.endswith("UnitTests.csproj"):
                checks.append(
                    (
                        "tests",
                        [
                            "dotnet",
                            "test",
                            "--project",
                            project,
                            "--configuration",
                            "Release",
                            "--framework",
                            "net10.0",
                            "--no-build",
                            "--no-restore",
                            "--filter-not-trait",
                            "Category=Integration",
                            "--filter-not-trait",
                            "Category=Manual",
                            *artifacts,
                            "--",
                            "--minimum-expected-tests",
                            "1",
                        ],
                    )
                )
        result["commands"] = [command for _, command in checks]
        result["checks_started"] = True
        try:
            for kind, command in checks:
                code, captured = container_tools._run([*execute, *command], timeout=600)
                output.extend(captured)
                del output[: -container_tools.MAX_OUTPUT]
                result["results"].append(
                    {
                        "kind": kind,
                        "command": command,
                        "passed": code == 0,
                        "output": captured.decode("utf-8", errors="replace"),
                    }
                )
        finally:
            confirm_source()
            result["source_unchanged"] = True
        result["checks_completed"] = True
        result["passed"] = all(item["passed"] for item in result["results"])
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        tarfile.TarError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        output.extend(
            f"\n{type(exc).__name__}: verification did not complete.".encode()
        )
    finally:
        if created:
            try:
                container_tools._run(["docker", "rm", "--force", name], timeout=30)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
    result["output"] = output[-container_tools.MAX_OUTPUT :].decode(
        "utf-8", errors="replace"
    )
    return result


def verify_requested_revision(
    repo_path: Path,
    head_sha: str,
    replacements: dict[str, str],
    *,
    trusted_sha: str,
    targets: dict[str, list[str]],
    images: dict[str, str] | None = None,
) -> dict:
    """Verify explicit targets; pass returned images to subsequent comparisons."""
    if not targets or set(targets) - {"python", "dotnet"} or not any(targets.values()):
        raise ValueError("Explicit verification targets required")
    if any(
        not isinstance(items, list) or any(not isinstance(p, str) for p in items)
        for items in targets.values()
    ):
        raise ValueError("Invalid verification targets")
    if any(not path.startswith(("python/", "dotnet/")) for path in replacements):
        raise ValueError("Unsupported replacement")
    if any(not targets.get(path.split("/", 1)[0]) for path in replacements):
        raise ValueError("Replacement has no verification target")
    images = images or {}
    for key in ("python", "dotnet"):
        container_tools._validate_image(images.get(key))
    runs = {}
    for language, selected in targets.items():
        if not selected:
            continue
        changes = {
            p: text for p, text in replacements.items() if p.startswith(language + "/")
        }
        if language == "python":
            runs[language] = container_tools.verify_revision(
                repo_path,
                head_sha,
                changes,
                selected,
                trusted_sha=trusted_sha,
                collect_all=True,
                companion_replacements={
                    p: text for p, text in replacements.items() if p not in changes
                },
                image=images[language],
            )
        else:
            runs[language] = _dotnet_verify(
                repo_path,
                head_sha,
                replacements,
                selected,
                trusted_sha,
                images.get(language),
            )
    return {
        "passed": all(run["passed"] for run in runs.values()),
        "checks_started": all(run["checks_started"] for run in runs.values()),
        "checks_completed": all(run["checks_completed"] for run in runs.values()),
        "source_unchanged": all(run["source_unchanged"] for run in runs.values()),
        "commands": [cmd for run in runs.values() for cmd in run["commands"]],
        "results": [
            dict(item, language=language)
            for language, run in runs.items()
            for item in run["results"]
        ],
        "images": {language: run["image_id"] for language, run in runs.items()},
        "output": "\n".join(run["output"] for run in runs.values())[
            -container_tools.MAX_OUTPUT :
        ],
    }
