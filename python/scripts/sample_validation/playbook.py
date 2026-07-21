# Copyright (c) Microsoft. All rights reserved.

"""Cached validation playbooks.

A *playbook* is a small JSON recipe that captures exactly how a sample was
successfully validated so future runs can replay it deterministically without
invoking an LLM agent. The agent produces a playbook the first time it
validates a sample; subsequent runs replay it directly and only fall back to
the agent when the playbook is missing, stale (the sample changed), or the
replay fails.

All paths in a playbook are relative to the Python root (the ``python/``
directory) so playbooks are portable across machines and CI runners.
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from sample_validation.models import RunResult, RunStatus, SampleInfo

logger = logging.getLogger(__name__)

# Bump when the on-disk playbook format changes in an incompatible way.
SCHEMA_VERSION = 1

# Hard cap on how long a replayed sample may run, regardless of the value the
# agent recorded, to protect the CI job from a runaway process.
MAX_REPLAY_TIMEOUT = 600


@dataclass
class FileEdit:
    """An in-place text replacement applied to a file before running."""

    file: str
    find: str
    replace: str


@dataclass
class RunSpec:
    """How to execute the sample."""

    command: list[str]
    cwd: str | None = None
    stdin: list[str] = field(default_factory=list)
    timeout: int = 120
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Playbook:
    """A cached, replayable recipe for validating a single sample."""

    sample: str
    sample_hash: str
    run: RunSpec
    edits: list[FileEdit] = field(default_factory=list)
    expected_status: str = RunStatus.SUCCESS.value
    schema_version: int = SCHEMA_VERSION
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Playbook":
        """Deserialize from a dict, tolerating unknown/missing optional keys."""
        run_data = dict(data.get("run") or {})  # type: ignore[arg-type]
        run = RunSpec(
            command=list(run_data.get("command") or []),
            cwd=run_data.get("cwd"),
            stdin=list(run_data.get("stdin") or []),
            timeout=int(run_data.get("timeout") or 120),
            env={str(k): str(v) for k, v in (run_data.get("env") or {}).items()},
        )
        edits = [
            FileEdit(file=str(e["file"]), find=str(e["find"]), replace=str(e["replace"]))
            for e in (data.get("edits") or [])  # type: ignore[union-attr]
        ]
        return cls(
            sample=str(data["sample"]),
            sample_hash=str(data["sample_hash"]),
            run=run,
            edits=edits,
            expected_status=str(data.get("expected_status") or RunStatus.SUCCESS.value),
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
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


def normalize_newlines(text: str) -> str:
    """Normalize CRLF/CR line endings to LF so edits are portable across platforms."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


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


async def replay_playbook(playbook: Playbook, python_root: Path) -> RunResult:
    """Deterministically replay a playbook and return a ``RunResult``.

    Applies any recorded file edits in place, runs the recorded command feeding
    the recorded stdin, and maps a zero exit code to ``SUCCESS``. Any other
    outcome yields a ``FAILURE`` so the caller falls back to the agent. The
    working tree is always restored afterwards so a replay never leaves the
    repository dirty (and a failed replay does not poison a later agent run).
    """
    sample_path = playbook.sample
    sample_info = SampleInfo(path=python_root / sample_path, relative_path=sample_path)

    # Snapshot every file we may edit so we can restore it no matter how we exit.
    # Snapshot raw bytes so the restore is byte-exact (no CRLF/LF translation).
    snapshot: dict[Path, bytes] = {}
    for edit in playbook.edits:
        target = python_root / edit.file
        if target in snapshot:
            continue
        try:
            snapshot[target] = target.read_bytes()
        except OSError:
            pass

    try:
        # Apply edits in place. Mirrors what the agent does during validation.
        for edit in playbook.edits:
            target = python_root / edit.file
            try:
                text = target.read_text(encoding="utf-8")
            except OSError as ex:
                return RunResult(
                    sample=sample_info,
                    status=RunStatus.FAILURE,
                    output="",
                    error=f"Replay could not read edit target {edit.file}: {ex}",
                )
            if edit.find not in text:
                return RunResult(
                    sample=sample_info,
                    status=RunStatus.FAILURE,
                    output="",
                    error=f"Replay edit no longer applies to {edit.file}; playbook is stale.",
                )
            target.write_text(text.replace(edit.find, edit.replace, 1), encoding="utf-8")

        command = list(playbook.run.command)
        if not command:
            return RunResult(
                sample=sample_info,
                status=RunStatus.FAILURE,
                output="",
                error="Playbook has an empty run command.",
            )
        # Use the current interpreter so replay targets the same virtual environment.
        if command[0] in ("python", "python3"):
            command[0] = sys.executable

        cwd = python_root / (playbook.run.cwd or ".")
        env = {**os.environ, **playbook.run.env}
        stdin_bytes = "".join(line + "\n" for line in playbook.run.stdin).encode("utf-8")
        timeout = min(max(1, playbook.run.timeout), MAX_REPLAY_TIMEOUT)

        start = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as ex:
            return RunResult(
                sample=sample_info,
                status=RunStatus.FAILURE,
                output="",
                error=f"Replay could not start command {command!r}: {ex}",
            )

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(stdin_bytes), timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError):
            proc.kill()
            await proc.wait()
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
        tail = output_text[-500:]
        return RunResult(
            sample=sample_info,
            status=RunStatus.FAILURE,
            output="",
            error=f"Replay exited with code {proc.returncode}. Output tail: {tail}",
        )
    finally:
        for target, original in snapshot.items():
            try:
                if target.read_bytes() != original:
                    target.write_bytes(original)
            except OSError as ex:  # pragma: no cover - defensive
                logger.warning(f"Could not restore {target} after replay: {ex}")
