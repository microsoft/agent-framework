"""Verify frozen public source in a disposable, credential-free Docker container."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import selectors
import signal
import subprocess
import tarfile
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath

MAX_ARCHIVE = 100 * 1024 * 1024
MAX_FILE = 10 * 1024 * 1024
MAX_OUTPUT = 16000
# Deliberately exclude HOME, Docker contexts, proxy credentials and GitHub tokens.
PROCESS_ENV = {
    "PATH": os.defpath + ":/usr/local/bin:/opt/homebrew/bin",
    "LANG": "C.UTF-8",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}


def _run(
    command: list[str],
    *,
    data: bytes | None = None,
    timeout: int = 600,
    limit: int = MAX_OUTPUT,
    binary: bool = False,
) -> tuple[int, bytes]:
    # Bounded input is spooled; output is drained through a bounded memory buffer.
    with tempfile.TemporaryFile() as source:
        if data:
            source.write(data)
        source.seek(0)
        process = subprocess.Popen(
            command,
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=PROCESS_ENV,
            start_new_session=True,
        )
        captured = bytearray()
        total = 0
        deadline = time.monotonic() + timeout
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, timeout)
                    for key, _ in selector.select(min(remaining, 1)):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            break
                        total += len(chunk)
                        if total > (limit if binary else 8 * 1024 * 1024):
                            raise ValueError("Subprocess output exceeds size limit")
                        captured.extend(chunk)
                        if not binary:
                            del captured[:-limit]
                code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
                return code, bytes(captured)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            process.stdout.close()


def _safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or ".git" in path.parts
        or "\\" in value
    ):
        raise ValueError("Unsafe archive path")
    if any(ord(char) < 32 for char in value):
        raise ValueError("Unsafe archive path")
    return str(path)


def _validate_archive(data: bytes) -> set[str]:
    if len(data) > MAX_ARCHIVE:
        raise ValueError("Source archive exceeds size limit")
    paths: set[str] = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive:
            path = _safe_path(member.name)
            if not (member.isfile() or member.isdir()) or member.size > MAX_FILE:
                raise ValueError("Unsupported archive entry")
            total += member.size
            if total > MAX_ARCHIVE or path in paths:
                raise ValueError("Oversized or duplicate archive entries")
            paths.add(path)
    return paths


def _overlay(files: dict[str, str]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for path, content in files.items():
            path = _safe_path(path)
            data = content.encode("utf-8")
            if len(data) > MAX_FILE:
                raise ValueError("Replacement exceeds size limit")
            member = tarfile.TarInfo(path)
            member.size = len(data)
            member.mode = 0o644
            member.uid = member.gid = 65532
            archive.addfile(member, io.BytesIO(data))
            if stream.tell() > MAX_ARCHIVE:
                raise ValueError("Overlay exceeds size limit")
    return stream.getvalue()


def _validate_image(image: str) -> None:
    if not isinstance(image, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9./_-]*@sha256:[0-9a-f]{64}", image
    ):
        raise ValueError("Verifier requires an immutable repository image digest")


def _container_limits() -> list[str]:
    return [
        "--user=65532:65532",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=256",
        "--memory=4g",
        "--cpus=2",
        "--ulimit=fsize=536870912:536870912",
        "--ulimit=nofile=1024:1024",
        "--tmpfs",
        "/work:rw,exec,nosuid,nodev,size=3g,nr_inodes=65536,uid=65532,gid=65532,mode=0755",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,nodev,size=512m,nr_inodes=16384,mode=1777",
        "--env=HOME=/work/home",
        "--env=DOTNET_CLI_HOME=/work/home",
        "--env=UV_CACHE_DIR=/work/uv-cache",
        "--env=UV_PYTHON_INSTALL_DIR=/work/python",
        "--env=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    ]


def _owned_archive(data: bytes) -> bytes:
    """Validate and reset uploaded file ownership for the non-root worker."""
    _validate_archive(data)
    stream = io.BytesIO()
    with (
        tarfile.open(fileobj=io.BytesIO(data)) as source,
        tarfile.open(fileobj=stream, mode="w") as target,
    ):
        for member in source:
            content = source.extractfile(member) if member.isfile() else None
            member.uid = member.gid = 65532
            member.uname = member.gname = ""
            member.mode = 0o755 if member.isdir() or member.mode & 0o111 else 0o644
            member.pax_headers = {}
            target.addfile(member, content)
    return stream.getvalue()


def _copy_in(container: str, destination: str, data: bytes, run) -> None:
    """Extract into bounded tmpfs using the immutable image's fixed tar binary."""
    if destination != "/work/source":
        raise ValueError("Invalid source destination")
    run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "/usr/bin/env",
            "-i",
            "PATH=/usr/bin:/bin",
            "LANG=C",
            "/bin/tar",
            "-xf",
            "-",
            "--no-same-owner",
            "--no-same-permissions",
            "-C",
            destination,
        ],
        data=_owned_archive(data),
    )


def _copy_out(container: str, group: str) -> tuple[int, bytes]:
    """Export source through read-only image tooling, without inherited options."""
    if _safe_path(group) != group:
        raise ValueError("Invalid source group")
    return _run(
        [
            "docker",
            "exec",
            container,
            "/usr/bin/env",
            "-i",
            "PATH=/usr/bin:/bin",
            "LANG=C",
            "/bin/tar",
            "-cf",
            "-",
            "-C",
            "/work/source",
            "--",
            group,
        ],
        timeout=120,
        limit=MAX_ARCHIVE,
        binary=True,
    )


def _source_hashes(data: bytes, *, prefix: str = "") -> dict[str, str]:
    _validate_archive(data)
    result = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for item in archive:
            name = item.name.removeprefix(prefix)
            if item.isfile() and name.endswith((".py", ".cs")):
                result[name] = hashlib.sha256(
                    archive.extractfile(item).read()
                ).hexdigest()
    return result


def _validate_source_replacements(
    files: dict[str, str], expected: dict[str, str]
) -> None:
    """Require canonical existing regular source files, never project controls."""
    for path in files:
        supported = (path.startswith("python/packages/") and path.endswith(".py")) or (
            path.startswith(("dotnet/src/", "dotnet/tests/")) and path.endswith(".cs")
        )
        if _safe_path(path) != path or path not in expected or not supported:
            raise ValueError("Replacement is outside existing supported source files")


# Runs before checks solely to reject unsupported or empty package selections.
PREFLIGHT = """import json, pathlib, sys, tomllib
from packaging.specifiers import SpecifierSet
version = '.'.join(map(str, sys.version_info[:3]))
for package in json.loads(sys.argv[1]):
    root = pathlib.Path('packages') / package
    metadata = tomllib.loads((root / 'pyproject.toml').read_text())
    requirement = metadata.get('project', {}).get('requires-python', '')
    if requirement and version not in SpecifierSet(requirement):
        raise SystemExit('Requested package does not support verifier Python')
    if not (root / 'tests').is_dir():
        raise SystemExit('Requested package has no test directory')
"""


def verify_revision(
    repo_path: Path,
    head_sha: str,
    replacements: dict[str, str],
    packages: list[str],
    *,
    trusted_sha: str,
    image: str,
    collect_all: bool = False,
    companion_replacements: dict[str, str] | None = None,
) -> dict:
    """Install trusted dependencies online, then verify the PR offline."""
    commands: list[list[str]] = []
    output = bytearray()
    container = f"devflow-fix-ci-{uuid.uuid4().hex}"
    created = False
    checks_started = False
    checks_completed = False
    source_unchanged = False
    results: list[dict] = []
    image_id = None

    def run(
        command: list[str], *, data: bytes | None = None, timeout: int = 600
    ) -> bytes:
        code, captured = _run(command, data=data, timeout=timeout)
        output.extend(captured)
        del output[:-MAX_OUTPUT]
        if code:
            raise RuntimeError(f"Verification command exited with status {code}")
        return captured

    def archive_revision(sha: str) -> bytes:
        code, data = _run(
            ["git", "-C", str(repo_path), "archive", "--format=tar", sha],
            timeout=120,
            limit=MAX_ARCHIVE,
            binary=True,
        )
        if code:
            raise ValueError("Unable to archive frozen revision")
        _validate_archive(data)
        return data

    def confirm_source(expected: dict[str, str]) -> None:
        # Export only source-bearing subtrees (python/packages, python/scripts,
        # etc.), not repository-root caches created by typing and test tools.
        # Top-level Python files are copied individually. These groups cannot
        # overlap because each is either a file or a two-component directory.
        groups = {
            str(PurePosixPath(*PurePosixPath(path).parts[:2])) for path in expected
        }
        actual: dict[str, str] = {}
        for group in sorted(groups):
            code, data = _copy_out(container, group)
            if code:
                raise ValueError("Unable to inspect verified source")
            for path, digest in _source_hashes(data).items():
                full_path = path
                if full_path in actual:
                    raise ValueError("Duplicate verified source")
                actual[full_path] = digest
        if actual != expected:
            raise ValueError("Verification changed source")

    try:
        if any(
            not re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (head_sha, trusted_sha)
        ):
            raise ValueError("Invalid frozen revision")
        if not packages or any(
            not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", p) for p in packages
        ):
            raise ValueError("Invalid package selection")
        _validate_image(image)
        archive = archive_revision(head_sha)
        paths = _validate_archive(archive)
        expected = _source_hashes(archive)
        _validate_source_replacements(replacements, expected)
        for path in replacements:
            _safe_path(path)
            if (
                path not in paths
                or not path.startswith("python/packages/")
                or not path.endswith(".py")
            ):
                raise ValueError("Replacement is outside existing package Python files")
        companions = companion_replacements or {}
        if replacements.keys() & companions.keys():
            raise ValueError("Overlapping replacement sets")
        _validate_source_replacements(companions, expected)
        replacements = {**replacements, **companions}
        for package in packages:
            prefix = f"python/packages/{package}/"
            if prefix + "pyproject.toml" not in paths or not any(
                p.startswith(prefix + "tests/") for p in paths
            ):
                raise ValueError("Requested package or tests are missing")
            # Do not invoke the mutating package formatter through check-packages.
            # Each command matches the package configuration but only reports errors.
            prefix_command = ["uv", "run", "--frozen", "--offline", "--no-sync"]
            commands.extend(
                [
                    [
                        *prefix_command,
                        "ruff",
                        "format",
                        "--check",
                        f"packages/{package}",
                    ],
                    [*prefix_command, "ruff", "check", f"packages/{package}"],
                    [*prefix_command, "pyright", "--project", f"packages/{package}"],
                ]
            )
            for task in ("test-typing",):
                commands.append(
                    [
                        "uv",
                        "run",
                        "--frozen",
                        "--offline",
                        "--no-sync",
                        "python",
                        "scripts/workspace_poe_tasks.py",
                        task,
                        "-P",
                        package,
                    ]
                )
            commands.append(
                [
                    "uv",
                    "run",
                    "--frozen",
                    "--offline",
                    "--no-sync",
                    "pytest",
                    "-m",
                    "not integration",
                    f"packages/{package}/tests",
                    "-q",
                ]
            )
        trusted_archive = archive_revision(trusted_sha)
        expected = _source_hashes(archive)
        expected.update(
            {
                path: hashlib.sha256(content.encode()).hexdigest()
                for path, content in replacements.items()
            }
        )
        run(["docker", "pull", image], timeout=180)
        image_id = (
            run(["docker", "image", "inspect", "--format={{.Id}}", image], timeout=30)
            .decode()
            .strip()
        )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise ValueError("Unable to pin verifier image")
        run(
            [
                "docker",
                "create",
                "--name",
                container,
                *_container_limits(),
                "--network=bridge",
                "--workdir=/work",
                "--env=PYTHONUNBUFFERED=1",
                "--env=UV_PROJECT_ENVIRONMENT=/work/venv",
                image_id,
                "sleep",
                "3000",
            ],
            timeout=120,
        )
        created = True
        run(["docker", "start", container], timeout=30)
        run(["docker", "exec", container, "mkdir", "-p", "/work/source"])
        _copy_in(container, "/work/source", trusted_archive, run)
        execute = ["docker", "exec", "--workdir=/work/source/python", container]
        sync = [
            "uv",
            "sync",
            "--frozen",
            "--all-packages",
            "--all-extras",
            "--all-groups",
        ]
        run([*execute, *sync], timeout=900)
        # Pyright bootstraps its Node runtime on first use; do that only on trusted source.
        run(
            [*execute, "uv", "run", "--frozen", "--no-sync", "pyright", "--version"],
            timeout=180,
        )
        # No PR bytes enter the container until it has lost all network access.
        run(["docker", "network", "disconnect", "bridge", container], timeout=30)
        run(["docker", "exec", container, "rm", "-rf", "/work/source"])
        run(["docker", "exec", container, "mkdir", "-p", "/work/source"])
        _copy_in(container, "/work/source", archive, run)
        if replacements:
            _copy_in(container, "/work/source", _overlay(replacements), run)
        run([*execute, *sync, "--offline"], timeout=600)
        run(
            [
                *execute,
                "uv",
                "run",
                "--frozen",
                "--offline",
                "--no-sync",
                "python",
                "-I",
                "-c",
                PREFLIGHT,
                json.dumps(packages),
            ],
            timeout=30,
        )
        confirm_source(expected)
        checks_started = True
        try:
            for command in commands:
                code, captured = _run([*execute, *command], timeout=600)
                output.extend(captured)
                del output[:-MAX_OUTPUT]
                kind = (
                    "tests"
                    if "pytest" in command
                    else "typing"
                    if "test-typing" in command
                    else "quality"
                )
                results.append(
                    {
                        "command": command,
                        "passed": code == 0,
                        "output": captured.decode("utf-8", errors="replace"),
                        "kind": kind,
                    }
                )
                if code and not collect_all:
                    break
        finally:
            confirm_source(expected)
            source_unchanged = True
        checks_completed = len(results) == len(commands)
        return {
            "passed": checks_completed and all(item["passed"] for item in results),
            "output": output.decode("utf-8", errors="replace"),
            "commands": commands,
            "checks_started": checks_started,
            "checks_completed": checks_completed,
            "source_unchanged": source_unchanged,
            "results": results,
            "image_id": image_id,
        }
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as exc:
        message = (
            output.decode("utf-8", errors="replace")
            + f"\n{type(exc).__name__}: verification did not complete."
        )
        return {
            "passed": False,
            "output": message[-MAX_OUTPUT:],
            "commands": commands,
            "checks_started": checks_started,
            "checks_completed": checks_completed,
            "source_unchanged": source_unchanged,
            "results": results,
            "image_id": image_id,
        }
    finally:
        if created:
            try:
                _run(["docker", "rm", "--force", container], timeout=30)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
