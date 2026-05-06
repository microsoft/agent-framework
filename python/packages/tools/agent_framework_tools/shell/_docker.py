# Copyright (c) Microsoft. All rights reserved.

"""Sandboxed shell tool backed by a Docker (or compatible) container runtime.

``DockerShellTool`` exposes the same public surface as
:class:`LocalShellTool` but executes commands inside a container. The
container is intended to be the security boundary; effective isolation
depends on the host runtime configuration, image contents, and the flags
passed at launch.

Default flags applied at launch:

- ``--network none``: no host or external network access.
- ``--user 65534:65534``: runs as ``nobody:nogroup``.
- ``--read-only`` root filesystem; only the optional ``host_workdir``
  mount is writable when ``mount_readonly=False``.
- ``--memory``, ``--pids-limit`` set to bounded values.
- ``--cap-drop=ALL`` and ``--security-opt=no-new-privileges``.
- ``--tmpfs /tmp`` so commands that need scratch space have somewhere to
  write that doesn't escape the container.

Persistent mode reuses :class:`ShellSession` by launching
``docker exec -i <container> bash`` as the long-lived shell — the
sentinel protocol works unchanged because the session is still talking
to a bash REPL over pipes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import shutil
import subprocess  # noqa: S404
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from agent_framework import FunctionTool, tool
from agent_framework._tools import SHELL_TOOL_KIND_VALUE

from ._policy import ShellPolicy, ShellRequest
from ._session import ShellSession
from ._truncate import truncate_head_tail as _truncate_bytes
from ._types import ShellCommandError, ShellMode, ShellResult

logger = logging.getLogger(__name__)


DEFAULT_IMAGE = "mcr.microsoft.com/azurelinux/base/core:3.0"
DEFAULT_CONTAINER_USER = "65534:65534"  # nobody:nogroup on most distros
DEFAULT_NETWORK = "none"
DEFAULT_MEMORY = "512m"
DEFAULT_PIDS_LIMIT = 256
DEFAULT_WORKDIR = "/workspace"


class DockerNotAvailableError(RuntimeError):
    """Raised when the configured docker binary cannot be reached."""


def is_docker_available(binary: str = "docker") -> bool:
    """Return ``True`` if ``binary`` is on PATH and the daemon responds."""
    if shutil.which(binary) is None:
        return False
    try:
        out = subprocess.run(  # noqa: S603
            [binary, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and bool(out.stdout.strip())


# ---------------------------------------------------------------------------
# Pure argv builders. Kept side-effect-free so unit tests don't need Docker.
# ---------------------------------------------------------------------------


def build_run_argv(
    *,
    binary: str,
    image: str,
    container_name: str,
    user: str,
    network: str,
    memory: str,
    pids_limit: int,
    workdir: str,
    host_workdir: str | None,
    mount_readonly: bool,
    read_only_root: bool,
    extra_env: Mapping[str, str] | None,
    extra_args: Sequence[str] | None,
) -> list[str]:
    """Build the ``docker run -d`` argv that starts the long-lived container.

    The container runs ``sleep infinity`` so it stays alive while the
    session uses ``docker exec`` for individual commands.
    """
    argv: list[str] = [
        binary,
        "run",
        "-d",
        "--rm",
        "--name",
        container_name,
        "--user",
        user,
        "--network",
        network,
        "--memory",
        memory,
        "--pids-limit",
        str(pids_limit),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=64m",  # noqa: S108,
        "--workdir",
        workdir,
    ]
    if read_only_root:
        argv.append("--read-only")
    if host_workdir is not None:
        ro = "ro" if mount_readonly else "rw"
        argv.extend(["-v", f"{host_workdir}:{workdir}:{ro}"])
    if extra_env:
        for k, v in extra_env.items():
            argv.extend(["-e", f"{k}={v}"])
    if extra_args:
        argv.extend(extra_args)
    argv.extend([image, "sleep", "infinity"])
    return argv


def build_exec_argv(
    *,
    binary: str,
    container_name: str,
    interactive: bool,
    shell: str = "bash",
) -> list[str]:
    """Build the ``docker exec -i <container> <shell>`` argv.

    For persistent mode this is the long-lived shell that
    :class:`ShellSession` reads/writes via stdin/stdout pipes.
    """
    argv = [binary, "exec", "-i", container_name, shell]
    if not interactive:
        # Stateless: ``docker exec`` is run per-command; <shell> -c <cmd> is
        # appended later by run_stateless.
        argv.extend(["-c"])  # caller appends the command
    elif shell == "bash":
        argv.extend(["--noprofile", "--norc"])
    return argv


# ---------------------------------------------------------------------------
# DockerShellTool
# ---------------------------------------------------------------------------


_DEFAULT_DESCRIPTION = (
    "Execute a single shell command inside an isolated Docker container "
    "and return its stdout, stderr, and exit code. Commands run in a "
    "persistent session so `cd` and environment variables from previous "
    "calls are preserved within the container."
)


class DockerShellTool:
    """Shell tool that runs commands inside a Docker (or compatible) container.

    Args:
        image: OCI image to run. Defaults to a small Microsoft-maintained
            base image. Override with anything that includes ``bash`` and
            (for persistent mode) ``sleep``.
        container_name: Optional explicit name. When ``None`` a unique
            name is generated per instance.
        mode: ``"persistent"`` (default) keeps a single long-lived
            container with `cd`/`export` carrying across calls.
            ``"stateless"`` runs each command in a fresh ``docker run --rm``.
        host_workdir: Optional host directory to mount into the container
            at ``workdir``. Mounted read-only by default; pass
            ``mount_readonly=False`` to allow writes.
        workdir: Path inside the container. Default ``/workspace``.
        mount_readonly: When ``True`` (default), mount ``host_workdir`` ro.
        network: Docker network mode. Default ``"none"`` for no network.
        memory: Container memory limit (e.g. ``"512m"``, ``"2g"``).
        pids_limit: Max processes inside the container.
        user: ``UID:GID`` to run as. Default ``65534:65534`` (nobody).
        read_only_root: Mount the root filesystem read-only. Default ``True``.
        extra_run_args: Additional args appended to ``docker run``.
        env: Environment variables to set inside the container. These are
            passed via ``-e`` and apply to every command.
        policy: Optional :class:`ShellPolicy`. Less critical than for
            ``LocalShellTool`` since the container is the intended
            isolation layer, but useful as a guardrail (and for audit
            logging).
        timeout: Per-command timeout in seconds.
        max_output_bytes: Combined stdout/stderr byte cap before truncation.
        approval_mode: Controls the FunctionTool approval gate. Unlike
            ``LocalShellTool``, ``"never_require"`` is permitted without
            ``acknowledge_unsafe`` because the container — when launched
            with the default isolation flags and a trusted runtime — is
            the intended boundary rather than approval.
        on_command: Audit hook fired for every allowed command.
        docker_binary: Override (e.g. ``"podman"``).
        shell: Shell binary to invoke inside the container. Defaults to
            ``"bash"``; pass ``"sh"`` for minimal images such as Alpine
            that don't ship bash. Anything else must be present on
            ``$PATH`` inside the image.
    """

    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        container_name: str | None = None,
        mode: ShellMode = "persistent",
        host_workdir: str | os.PathLike[str] | None = None,
        workdir: str = DEFAULT_WORKDIR,
        mount_readonly: bool = True,
        network: str = DEFAULT_NETWORK,
        memory: str = DEFAULT_MEMORY,
        pids_limit: int = DEFAULT_PIDS_LIMIT,
        user: str = DEFAULT_CONTAINER_USER,
        read_only_root: bool = True,
        extra_run_args: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        policy: ShellPolicy | None = None,
        timeout: float | None = 30.0,
        max_output_bytes: int = 64 * 1024,
        approval_mode: Literal["always_require", "never_require"] = "always_require",
        on_command: Callable[[str], None] | None = None,
        docker_binary: str = "docker",
        shell: str = "bash",
    ) -> None:
        if mode not in ("persistent", "stateless"):
            raise ValueError(f"mode must be 'persistent' or 'stateless', got {mode!r}")
        self._image = image
        self._container_name = container_name or f"af-shell-{secrets.token_hex(6)}"
        self._mode: ShellMode = mode
        self._host_workdir: str | None = (
            os.fspath(host_workdir) if host_workdir is not None else None
        )
        self._workdir = workdir
        self._mount_readonly = mount_readonly
        self._network = network
        self._memory = memory
        self._pids_limit = pids_limit
        self._user = user
        self._read_only_root = read_only_root
        self._extra_run_args = tuple(extra_run_args or ())
        self._env = dict(env or {})
        self._policy = policy or ShellPolicy()
        self._timeout = timeout
        self._max_output_bytes = max_output_bytes
        self._approval_mode = approval_mode
        self._on_command = on_command
        self._binary = docker_binary
        self._shell = shell

        self._session: ShellSession | None = None
        self._container_started = False
        self._lifecycle_lock: asyncio.Lock | None = None

    def _get_lifecycle_lock(self) -> asyncio.Lock:
        if self._lifecycle_lock is None:
            self._lifecycle_lock = asyncio.Lock()
        return self._lifecycle_lock

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Pull/start the container and (if persistent) the inner shell session."""
        # Stateless mode never uses the long-lived container — every call goes
        # through ``docker run --rm`` — so start()/close() are no-ops.
        if self._mode == "stateless":
            return
        async with self._get_lifecycle_lock():
            if self._container_started:
                if self._session is not None:
                    await self._session.start()
                return
            await self._start_container()
            self._container_started = True
            argv = build_exec_argv(
                binary=self._binary,
                container_name=self._container_name,
                interactive=True,
                shell=self._shell,
            )
            self._session = ShellSession(
                argv,
                workdir=None,  # workdir is set on the container itself
                env=None,
                max_output_bytes=self._max_output_bytes,
            )
            await self._session.start()

    async def close(self) -> None:
        """Stop the inner shell session and tear down the container."""
        if self._mode == "stateless":
            return
        async with self._get_lifecycle_lock():
            if self._session is not None:
                try:
                    await self._session.close()
                finally:
                    self._session = None
            if self._container_started:
                await self._stop_container()
                self._container_started = False

    async def __aenter__(self) -> "DockerShellTool":
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------ execution

    async def run(self, command: str) -> ShellResult:
        """Execute ``command`` inside the container and return its result."""
        request = ShellRequest(command=command, workdir=self._workdir)
        decision = self._policy.evaluate(request)
        if decision.decision == "deny":
            raise ShellCommandError(f"Command rejected by policy: {decision.reason}")
        if self._on_command is not None:
            try:
                self._on_command(command)
            except Exception:
                logger.exception("on_command hook raised")

        if self._mode == "persistent":
            if self._session is None:
                await self.start()
            assert self._session is not None
            return await self._session.run(command, timeout=self._timeout)

        return await self._run_stateless(command)

    # ------------------------------------------------------------------ stateless

    async def _run_stateless(self, command: str) -> ShellResult:
        """Run a single command in a fresh ``docker run --rm`` container."""
        per_call_name = f"af-shell-{secrets.token_hex(6)}"
        argv = [
            self._binary,
            "run",
            "--rm",
            "-i",
            "--name",
            per_call_name,
            "--user",
            self._user,
            "--network",
            self._network,
            "--memory",
            self._memory,
            "--pids-limit",
            str(self._pids_limit),
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m",  # noqa: S108,
            "--workdir",
            self._workdir,
        ]
        if self._read_only_root:
            argv.append("--read-only")
        if self._host_workdir is not None:
            ro = "ro" if self._mount_readonly else "rw"
            argv.extend(["-v", f"{self._host_workdir}:{self._workdir}:{ro}"])
        for k, v in self._env.items():
            argv.extend(["-e", f"{k}={v}"])
        argv.extend(self._extra_run_args)
        argv.extend([self._image, self._shell, "-c", command])

        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            timed_out = True
            # Kill the container by name; --rm reaps it.
            killer = await asyncio.create_subprocess_exec(
                self._binary,
                "kill",
                "--signal",
                "KILL",
                per_call_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(killer.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                killer.kill()
            try:
                stdout_bytes, stderr_bytes = await proc.communicate()
            except Exception:
                stdout_bytes, stderr_bytes = b"", b""

        duration_ms = int((time.monotonic() - started) * 1000)
        stdout_str, stdout_truncated = _truncate_bytes(
            stdout_bytes or b"", self._max_output_bytes
        )
        stderr_str, stderr_truncated = _truncate_bytes(
            stderr_bytes or b"", self._max_output_bytes
        )
        return ShellResult(
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_ms=duration_ms,
            truncated=stdout_truncated or stderr_truncated,
            timed_out=timed_out,
        )

    # ------------------------------------------------------------------ container ops

    async def _start_container(self) -> None:
        argv = build_run_argv(
            binary=self._binary,
            image=self._image,
            container_name=self._container_name,
            user=self._user,
            network=self._network,
            memory=self._memory,
            pids_limit=self._pids_limit,
            workdir=self._workdir,
            host_workdir=self._host_workdir,
            mount_readonly=self._mount_readonly,
            read_only_root=self._read_only_root,
            extra_env=self._env,
            extra_args=self._extra_run_args,
        )
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise DockerNotAvailableError(
                f"Failed to start container ({proc.returncode}): "
                f"{err.decode('utf-8', errors='replace').strip()}"
            )
        logger.info(
            "started docker container %s (id=%s)",
            self._container_name,
            out.decode("utf-8", errors="replace").strip()[:12],
        )

    async def _stop_container(self) -> None:
        # Use docker rm -f for a hard shutdown. With --rm on the run
        # command, this also reaps the container.
        proc = await asyncio.create_subprocess_exec(
            self._binary,
            "rm",
            "-f",
            self._container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            proc.kill()

    # ------------------------------------------------------------------ AF wiring

    def as_function(
        self,
        *,
        name: str = "run_shell",
        description: str | None = None,
    ) -> FunctionTool:
        """Return a :class:`~agent_framework.FunctionTool` bound to this instance."""

        async def _run_shell(command: str) -> str:
            try:
                result = await self.run(command)
            except ShellCommandError as exc:
                return f"Command blocked by policy: {exc}"
            return result.format_for_model()

        _run_shell.__doc__ = description or _DEFAULT_DESCRIPTION
        return tool(
            func=_run_shell,
            name=name,
            description=description or _DEFAULT_DESCRIPTION,
            approval_mode=self._approval_mode,
            kind=SHELL_TOOL_KIND_VALUE,
        )
