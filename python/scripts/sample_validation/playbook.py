# Copyright (c) Microsoft. All rights reserved.

"""Cached validation playbooks.

A *playbook* is a small JSON recipe that captures exactly how a sample was
successfully validated so future runs can replay it deterministically without
invoking an LLM agent. The agent produces a playbook the first time it
validates a sample; subsequent runs replay it directly and only fall back to
the agent when the playbook is missing, stale (the sample changed), or the
replay fails.

The playbook payload is an agent-authored **Python validation script**. Replaying
a playbook writes that script to a temporary file and runs it with the active
interpreter, treating a zero exit code as success. A single script can validate
any sample shape: a plain sample that runs to completion, or a long-lived server
sample (e.g. a hosted agent) that must be started in the background, exercised
over HTTP, asserted, and then torn down.

The script is a cache-only artifact (it is never committed to the repository), so
it is exempt from the repository's Python style/type rules; the harness treats it
as an opaque, self-contained program. Any paths the script references should be
relative to the Python root (the ``python/`` directory), which is the working
directory used at replay time, so playbooks stay portable across machines and CI
runners.
"""

import asyncio
import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from sample_validation.models import RunResult, RunStatus, SampleInfo

logger = logging.getLogger(__name__)

# Bump when the on-disk playbook format changes in an incompatible way.
# v2: the payload is an agent-authored Python script (replaces the v1 RunSpec).
SCHEMA_VERSION = 2

# Hard cap on how long a replayed sample may run, regardless of the value the
# agent recorded, to protect the CI job from a runaway process.
MAX_REPLAY_TIMEOUT = 600


@dataclass
class Playbook:
    """A cached, replayable recipe for validating a single sample.

    The recipe is an agent-authored Python ``script`` that reproduces a
    successful validation without any AI assistance. Replaying runs the script
    with the active interpreter from the Python root and maps a zero exit code to
    success. The script is self-contained: it launches/exercises the sample,
    performs its own assertions, bakes in any edits it needs, and (for a server
    sample) starts and tears down the server itself.
    """

    sample: str
    sample_hash: str
    script: str
    timeout: int = 120
    env: dict[str, str] = field(default_factory=dict) # type: ignore
    expected_status: str = RunStatus.SUCCESS.value
    schema_version: int = SCHEMA_VERSION
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Playbook":
        """Deserialize from a dict, tolerating unknown/missing optional keys.

        Tolerant of older schema versions (which lack ``script``) so
        ``PlaybookStore.load`` can read them and then reject them on the schema
        version check rather than raising.
        """
        return cls(
            sample=str(data["sample"]),
            sample_hash=str(data["sample_hash"]),
            script=str(data.get("script") or ""),
            timeout=int(data.get("timeout") or 120),  # type: ignore[arg-type]
            env={str(k): str(v) for k, v in (data.get("env") or {}).items()},  # type: ignore[union-attr]
            expected_status=str(data.get("expected_status") or RunStatus.SUCCESS.value),
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),  # type: ignore[arg-type]
            generated_at=str(data.get("generated_at") or datetime.now().isoformat()),
        )


def sample_files(sample: SampleInfo) -> list[Path]:
    """Return the files that make up a sample.

    For a single-file sample this is just that file. For a directory sample
    (``main.py``/``app.py`` entrypoint) it is every ``.py`` file in the tree.
    """
    path = sample.path
    if path.is_dir():
        return sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
    return [path]


def compute_sample_hash(sample: SampleInfo) -> str:
    """Compute a stable content hash for a sample.

    For a single-file sample the hash covers that file. For a directory sample
    (``main.py``/``app.py`` entrypoint) it covers every ``.py`` file in the
    directory tree so any change to the sample invalidates the cached playbook.
    """
    hasher = hashlib.sha256()
    path = sample.path
    for file in sample_files(sample):
        try:
            hasher.update(file.relative_to(path.parent).as_posix().encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(file.read_bytes())
            hasher.update(b"\0")
        except OSError as ex:  # pragma: no cover - defensive
            logger.warning(f"Could not hash {file}: {ex}")

    return f"sha256:{hasher.hexdigest()}"


class PlaybookStore:
    """Loads and saves per-sample playbooks under a directory.

    Each sample gets one JSON file whose name is derived from the sample's
    relative path (path separators replaced so it stays flat and filesystem
    safe).
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @staticmethod
    def _slug(relative_path: str) -> str:
        return relative_path.replace("\\", "/").replace("/", "__") + ".json"

    def _path_for(self, relative_path: str) -> Path:
        return self.directory / self._slug(relative_path)

    def load(self, sample: SampleInfo) -> Playbook | None:
        """Return the stored playbook for a sample, or ``None`` if absent/invalid."""
        path = self._path_for(sample.relative_path)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            playbook = Playbook.from_dict(data)
        except (OSError, ValueError, KeyError) as ex:
            logger.warning(f"Ignoring unreadable playbook {path}: {ex}")
            return None
        if playbook.schema_version != SCHEMA_VERSION:
            logger.info(f"Ignoring playbook with schema {playbook.schema_version} for {sample.relative_path}")
            return None
        return playbook

    def save(self, playbook: Playbook) -> Path:
        """Persist a playbook to disk and return its path."""
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path_for(playbook.sample)
        path.write_text(json.dumps(playbook.to_dict(), indent=2), encoding="utf-8")
        return path

    def is_valid_for(self, sample: SampleInfo) -> Playbook | None:
        """Return the stored playbook only if it matches the sample's current hash."""
        playbook = self.load(sample)
        if playbook is None:
            return None
        current_hash = compute_sample_hash(sample)
        if playbook.sample_hash != current_hash:
            logger.info(f"Playbook for {sample.relative_path} is stale (sample changed); will re-validate.")
            return None
        return playbook


def _new_process_group_kwargs() -> dict[str, object]:
    """Return subprocess kwargs that launch the child in its own process group.

    Isolating the replay in a new group/session lets us tear down the whole tree
    (for example a background server the script spawned) even if the script exits
    without cleaning up after itself.
    """
    if os.name == "posix":
        return {"start_new_session": True}
    # Windows: a new process group so the whole tree can be terminated together.
    return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}


def _terminate_process_tree(proc: "asyncio.subprocess.Process", pgid: int | None) -> None:
    """Best-effort kill of a replay process and any descendants it leaked.

    This always runs, even when the script itself already exited cleanly, because
    the whole point of the backstop is to reap a background server the script may
    have started but failed to tear down. On POSIX we signal the saved process
    group id (captured at spawn time, since the leader may already be reaped);
    on Windows we kill the process tree by PID.
    """
    try:
        if os.name == "posix":
            if pgid is not None:
                os.killpg(pgid, signal.SIGKILL)
            elif proc.returncode is None:
                proc.kill()
        else:
            # Kill by PID (not image name) including the whole child tree.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
    except (ProcessLookupError, OSError) as ex:  # pragma: no cover - defensive
        logger.debug(f"Could not terminate replay process tree {proc.pid}: {ex}")


async def replay_playbook(playbook: Playbook, python_root: Path) -> RunResult:
    """Deterministically replay a playbook and return a ``RunResult``.

    Writes the recorded Python script to a temporary file and runs it with the
    active interpreter, using the Python root as the working directory. A zero
    exit code maps to ``SUCCESS``; anything else yields a ``FAILURE`` so the
    caller falls back to the agent.

    Sample files are snapshotted and restored so a replay never leaves the
    repository dirty (the script may edit the sample to make it run), and the
    replay process is launched in its own process group so a background server it
    starts is always torn down afterwards, even if the script fails to clean up.
    """
    sample_path = playbook.sample
    sample_info = SampleInfo(path=python_root / sample_path, relative_path=sample_path)

    if not playbook.script.strip():
        return RunResult(
            sample=sample_info,
            status=RunStatus.FAILURE,
            output="",
            error="Playbook has an empty validation script.",
        )

    # Snapshot every file that makes up the sample so we can restore it byte-exact
    # no matter how we exit (the script is allowed to edit the sample in place).
    snapshot: dict[Path, bytes] = {}
    for file in sample_files(sample_info):
        try:
            snapshot[file] = file.read_bytes()
        except OSError:
            pass

    script_file = tempfile.NamedTemporaryFile(  # noqa: SIM115 - closed explicitly below
        prefix="playbook_", suffix=".py", delete=False
    )
    script_path = Path(script_file.name)
    proc: asyncio.subprocess.Process | None = None
    pgid: int | None = None
    try:
        script_file.write(playbook.script.encode("utf-8"))
        script_file.close()

        env = {**os.environ, **playbook.env}
        timeout = min(max(1, playbook.timeout), MAX_REPLAY_TIMEOUT)

        start = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script_path),
                cwd=str(python_root),
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                **_new_process_group_kwargs(),  # type: ignore[arg-type]
            )
        except OSError as ex:
            return RunResult(
                sample=sample_info,
                status=RunStatus.FAILURE,
                output="",
                error=f"Replay could not start the script: {ex}",
            )

        # Capture the process-group id now (== proc.pid, since we start a new
        # session/group) so teardown can kill leaked descendants even after the
        # leader process has exited and been reaped.
        if os.name == "posix":
            try:
                pgid = os.getpgid(proc.pid)
            except OSError:  # pragma: no cover - defensive
                pgid = None

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError):
            return RunResult(
                sample=sample_info,
                status=RunStatus.FAILURE,
                output="",
                error=f"Replay timed out after {timeout}s.",
            )

        duration = time.perf_counter() - start
        output_text = stdout.decode("utf-8", errors="replace") if stdout else ""

        if proc.returncode == 0:
            return RunResult(
                sample=sample_info,
                status=RunStatus.SUCCESS,
                output=f"Replayed cached playbook successfully in {duration:.1f}s.",
                error="",
            )

        # Non-zero exit: surface a truncated tail to aid debugging; caller retries with the agent.
        tail = output_text[-1000:]
        return RunResult(
            sample=sample_info,
            status=RunStatus.FAILURE,
            output="",
            error=f"Replay exited with code {proc.returncode}. Output tail: {tail}",
        )
    finally:
        # Always tear down the process group (even if the script exited cleanly)
        # so a background server it leaked is killed, then reap the leader.
        if proc is not None:
            _terminate_process_tree(proc, pgid)
            try:
                await proc.wait()
            except Exception:  # pragma: no cover - defensive
                pass
        for target, original in snapshot.items():
            try:
                if target.read_bytes() != original:
                    target.write_bytes(original)
            except OSError as ex:  # pragma: no cover - defensive
                logger.warning(f"Could not restore {target} after replay: {ex}")
        try:
            script_path.unlink()
        except OSError:  # pragma: no cover - defensive
            pass
