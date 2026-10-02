# Copyright (c) Microsoft. All rights reserved.
"""Opt-in local-filesystem coordination for hosted file-memory lifecycle management."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, TypeVar, cast

from filelock import AsyncFileLock, Timeout

from .._feature_stage import ExperimentalFeature, experimental
from .._filesystem import _is_link_or_reparse_point  # pyright: ignore[reportPrivateUsage]
from ._file_access import AgentFileStore, FileSearchResult, FileStoreEntry, FileSystemAgentFileStore
from ._file_store_limits import _FileStoreLimits, _FileStoreQuotaError  # pyright: ignore[reportPrivateUsage]

logger = logging.getLogger(__name__)
_ResultT = TypeVar("_ResultT")


class _FileMemoryCommitError(ValueError):
    """An operation changed content but did not commit its lifecycle metadata."""


async def _complete(work: Awaitable[_ResultT]) -> _ResultT:
    """Finish filesystem work before releasing its lock, including on cancellation."""
    task = asyncio.ensure_future(work)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if not task.cancelled():
            task.exception()
        raise


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileMemoryRetentionManager:
    """Coordinate quotas and sliding expiry for cooperating local file-memory stores.

    Store roots must be direct children of directory. Control files live outside
    those roots. Existing unregistered files remain readable and count toward capacity.
    All participating writers must use this manager on the same host/local filesystem.
    Construction performs no writes. Use the async context for periodic GC and
    FileMemoryProvider.protect() throughout request/stream lifetime.
    """

    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        retention_seconds: int | None = None,
        max_total_bytes: int | None = None,
        max_files: int | None = None,
        sweep_interval_seconds: int = 300,
    ) -> None:
        """Configure a host-owned memory area.

        Args:
            directory: Common parent of participating store roots.

        Keyword Args:
            retention_seconds: Initial idle lifetime for a new directory. Existing policy is preserved;
                use set_retention() for explicit configuration changes. None initially disables expiry.
            max_total_bytes: Shared file bytes, including control metadata and an atomic-copy reserve.
            max_files: Shared regular-file count, including control files and one staging slot.
            sweep_interval_seconds: Interval between server-driven sweeps.

        Raises:
            ValueError: If a limit is invalid or the managed directory is empty.
        """
        _FileStoreLimits.create(retention_seconds, sweep_interval_seconds, None)
        if not os.fspath(directory).strip():
            raise ValueError("The managed memory directory must not be empty.")
        self.directory = Path(directory).absolute()
        self._control = self.directory / ".retention"
        self.retention_seconds = retention_seconds
        self._initial_retention = retention_seconds
        self._policy: dict[str, Any] = {}
        self._capacity = _FileStoreLimits.create(None, max_files, max_total_bytes)
        self.sweep_interval_seconds = sweep_interval_seconds
        self._now: Callable[[], float] = time.time
        self._sweeper: asyncio.Task[None] | None = None

    def _validate_store(self, store: AgentFileStore) -> FileSystemAgentFileStore:
        """Require an explicitly supported store without creating directories."""
        if not isinstance(store, FileSystemAgentFileStore) or type(store) is not FileSystemAgentFileStore:
            raise ValueError("File-memory retention requires FileSystemAgentFileStore without backend overrides.")
        if store.root_path.parent != self.directory.resolve() or store.root_path.name == ".retention":
            raise ValueError("The memory store must be a direct child of the managed directory.")
        return store

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(os.path.normcase(value).replace("\\", "/").encode("utf-8")).hexdigest()

    def _scope(self, store: FileSystemAgentFileStore) -> str:
        return self._digest(store.root_path.name)

    def _key(self, store: FileSystemAgentFileStore, path: Path) -> str:
        return self._digest(path.relative_to(store.root_path).as_posix())

    def _manifest_path(self, store: FileSystemAgentFileStore) -> Path:
        return self._control / f"{self._scope(store)}.json"

    @staticmethod
    def _safe(path: Path) -> None:
        if os.path.lexists(path) and _is_link_or_reparse_point(path):
            raise ValueError("Memory lifecycle paths must not contain links or reparse points.")

    def _prepare_control(self) -> None:
        self._safe(self.directory)
        if self.directory.resolve() != self.directory:
            raise ValueError("The managed memory directory must not resolve through a link.")
        self.directory.mkdir(parents=True, exist_ok=True)
        self._safe(self._control)
        self._control.mkdir(exist_ok=True)
        lock_path = self._control / "manager.lock"
        self._safe(lock_path)
        if lock_path.exists() and lock_path.stat().st_size:
            raise ValueError("Existing data conflicts with the lifecycle control lock.")
        staging = self._control / "staging"
        self._safe(staging)
        staging.mkdir(exist_ok=True)

    @asynccontextmanager
    async def _locked(self, *, load_policy: bool = True) -> AsyncGenerator[None]:
        self._prepare_control()
        # Keep the coordination pathname stable, including on Windows. Native OS
        # locks release after process death; a soft-file fallback cannot promise that.
        # https://py-filelock.readthedocs.io/en/latest/changelog.html
        lock = AsyncFileLock(
            self._control / "manager.lock", timeout=10, preserve_lock_file=True, fallback_to_soft=False
        )
        try:
            async with lock:
                for path in (self._control / "staging").iterdir():
                    self._safe(path)
                    if path.is_file() and path.name.endswith(".tmp"):
                        path.unlink()
                if load_policy:
                    self._load_policy()
                yield
        except Timeout as exc:
            raise TimeoutError("Timed out acquiring the file-memory management lock.") from exc

    def _load_policy(self) -> None:
        path = self._control / "policy.json"
        self._safe(path)
        if not path.exists():
            self._policy = {
                "schema_version": 1,
                "retention_seconds": self._initial_retention,
                "generation": 0,
                "resumed_expires_at": None,
            }
            self._save_policy()
        else:
            if path.stat().st_size > 16384:
                raise ValueError("The file-memory policy exceeds its supported size.")
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("The file-memory policy is invalid; management is paused.") from exc
            if (
                not isinstance(raw, dict)
                or cast(dict[str, Any], raw).get("schema_version") != 1
                or isinstance(cast(dict[str, Any], raw).get("schema_version"), bool)
            ):
                raise ValueError("Unsupported file-memory policy version; management is paused.")
            raw = cast(dict[str, Any], raw)
            if not {"retention_seconds", "generation", "resumed_expires_at"}.issubset(raw):
                raise ValueError("The file-memory policy is missing required fields.")
            _FileStoreLimits.create(raw["retention_seconds"], None, None)
            generation, deadline = raw.get("generation"), raw.get("resumed_expires_at")
            if (
                type(generation) is not int
                or generation < 0
                or (
                    deadline is not None
                    and (
                        isinstance(deadline, bool)
                        or not isinstance(deadline, (int, float))
                        or not math.isfinite(deadline)
                    )
                )
                or (generation > 0 and deadline is None)
            ):
                raise ValueError("The file-memory policy has invalid recovery metadata.")
            self._policy = raw
        self.retention_seconds = self._policy["retention_seconds"]

    def _save_policy(self) -> None:
        path = self._control / "policy.json"
        payload = json.dumps(self._policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) > 16384:
            raise ValueError("The file-memory policy exceeds its supported size.")
        self._check_growth(path, len(payload))
        self._atomic(path, payload)

    async def set_retention(self, retention_seconds: int | None) -> None:
        """Explicitly enable, disable or change the shared idle lifetime.

        Args:
            retention_seconds: Positive lifetime in seconds, or None to disable TTL.

        Disabling retains deadlines and permits ordinary reads without renewal.
        Reenabling grants every retained ready record a complete new lifetime.
        Same-value calls are no-ops. Changing one positive value to another only
        changes subsequent successful writes/uses. Construction/restart reads an
        existing policy without changing it; the constructor value initializes a
        new managed directory only.
        """
        _FileStoreLimits.create(retention_seconds, None, None)

        async def work() -> None:
            async with self._locked():
                previous = self.retention_seconds
                if previous == retention_seconds:
                    return
                policy = self._policy.copy()
                policy["retention_seconds"] = retention_seconds
                if previous is None and retention_seconds is not None:
                    policy["generation"] += 1
                    policy["resumed_expires_at"] = self._now() + retention_seconds
                self._policy = policy
                self._save_policy()
                self.retention_seconds = retention_seconds

        await _complete(work())

    def _deadline(self, record: dict[str, Any]) -> float | None:
        if record.get("generation", 0) < self._policy["generation"]:
            return self._policy["resumed_expires_at"]
        return record["expires_at"]

    def _load(self, store: FileSystemAgentFileStore) -> dict[str, Any]:
        path = self._manifest_path(store)
        self._safe(path)
        if not path.exists():
            return {"schema_version": 1, "entries": {}}
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("The file-memory manifest exceeds its supported size.")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("The file-memory manifest is invalid; lifecycle operations are paused.") from exc
        if (
            not isinstance(raw, dict)
            or cast(dict[str, Any], raw).get("schema_version") != 1
            or isinstance(cast(dict[str, Any], raw).get("schema_version"), bool)
        ):
            raise ValueError("Unsupported file-memory manifest version; lifecycle operations are paused.")
        state = cast(dict[str, Any], raw)
        entries = state.get("entries")
        if not isinstance(entries, dict):
            raise ValueError("The file-memory manifest has invalid entries.")
        for key, value in cast(dict[str, Any], entries).items():
            if len(key) != 64 or any(c not in "0123456789abcdef" for c in key) or not isinstance(value, dict):
                raise ValueError("The file-memory manifest contains an unsupported record.")
            record = cast(dict[str, Any], value)
            if record.get("state") not in ("ready", "updating", "deleting"):
                raise ValueError("The file-memory manifest contains an unsupported state.")
            for name in ("folder", "description"):
                digest = record.get(name)
                if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError("The file-memory manifest contains an unsupported reference.")
            if key in (record["folder"], record["description"]) or record["folder"] == record["description"]:
                raise ValueError("The file-memory record contains inconsistent references.")
            generation = record.get("generation", 0)
            if type(generation) is not int or generation < 0 or generation > self._policy["generation"]:
                raise ValueError("The file-memory record has an unsupported recovery generation.")
            if "expires_at" not in record:
                raise ValueError("The file-memory record is missing its expiry field.")
            deadline = record["expires_at"]
            if (
                deadline is None
                and record["state"] == "ready"
                and self.retention_seconds is not None
                and generation == self._policy["generation"]
            ):
                raise ValueError("An active ready record must have an expiry time.")
            if deadline is not None and (
                isinstance(deadline, bool) or not isinstance(deadline, (float, int)) or not math.isfinite(deadline)
            ):
                raise ValueError("The file-memory manifest has an invalid expiry time.")
        self._stored_limits(state)
        return state

    def _usage(self) -> tuple[int, int, int]:
        count = total = largest = 0
        directories = [self.directory]
        while directories:
            directory = directories.pop()
            if not directory.exists():
                continue
            for path in directory.iterdir():
                self._safe(path)
                if path.is_dir():
                    if path != self._control / "staging":
                        directories.append(path)
                elif path.is_file():
                    count += 1
                    size = path.stat().st_size
                    total += size
                    largest = max(largest, size)
        return count, total, largest

    def _check_growth(self, path: Path, size: int) -> None:
        self._check_combined_growth([(path, size)])

    def _check_combined_growth(self, changes: list[tuple[Path, int]]) -> None:
        if self._capacity is None:
            return
        count, total, largest = self._usage()
        resulting_count, resulting_bytes, reserve = count, total, largest
        for path, size in changes:
            exists = path.is_file()
            resulting_count += int(not exists)
            resulting_bytes += size - (path.stat().st_size if exists else 0)
            reserve = max(reserve, size)
        # Serialized mutations reserve room for one complete atomic-copy file.
        if self._capacity.max_files is not None and resulting_count + 1 > max(count + 1, self._capacity.max_files):
            raise _FileStoreQuotaError("shared_max_files", self._capacity.max_files, resulting_count + 1)
        if self._capacity.max_total_bytes is not None and (
            resulting_bytes + reserve > max(total + largest, self._capacity.max_total_bytes)
        ):
            raise _FileStoreQuotaError(
                "shared_max_total_bytes", self._capacity.max_total_bytes, resulting_bytes + largest
            )

    @staticmethod
    def _stored_limits(state: dict[str, Any]) -> _FileStoreLimits | None:
        raw = state.get("store_limits")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError("Invalid stored file-memory capacity configuration.")
        limits = cast(dict[str, Any], raw)
        return _FileStoreLimits.create(
            limits.get("max_file_bytes"), limits.get("max_files"), limits.get("max_total_bytes")
        )

    def _check_store_growth(self, store: FileSystemAgentFileStore, path: Path, size: int) -> None:
        limits = store._limits  # pyright: ignore[reportPrivateUsage]
        if limits is not None:
            limits.check_read(size)
            count, total = store._quota_usage() if store.root_path.exists() else (0, 0)  # pyright: ignore[reportPrivateUsage]
            limits.check_usage(
                count + int(not path.exists()), total - (path.stat().st_size if path.exists() else 0) + size
            )

    async def _write_index(self, store: FileSystemAgentFileStore, view: _RetainedFileStore, folder: Path) -> None:
        path = folder / "memories.md"
        payload = (await view.index_text(folder.relative_to(store.root_path).as_posix())).encode("utf-8")
        self._check_store_growth(store, path, len(payload))
        self._check_growth(path, len(payload))
        self._atomic(path, payload)

    def _atomic(self, path: Path, payload: bytes, *, overwrite: bool = True) -> None:
        temporary = self._control / "staging" / f"{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._safe(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if overwrite:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _save(self, store: FileSystemAgentFileStore, state: dict[str, Any], *, reclaim: bool = False) -> None:
        path = self._manifest_path(store)
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) > 16 * 1024 * 1024:
            raise ValueError("The file-memory manifest exceeds its supported size.")
        if not reclaim:
            self._check_growth(path, len(payload))
        self._atomic(path, payload)

    @staticmethod
    def _files(root: Path) -> list[Path]:
        files: list[Path] = []
        directories = [root]
        while directories:
            directory = directories.pop()
            if not directory.exists():
                continue
            FileMemoryRetentionManager._safe(directory)
            for path in directory.iterdir():
                FileMemoryRetentionManager._safe(path)
                if path.is_dir():
                    directories.append(path)
                elif path.is_file() and path != root / ".agent-framework-quota.lock":
                    files.append(path)
        return files

    async def _run(
        self,
        store: AgentFileStore,
        action: Callable[[AgentFileStore], Awaitable[_ResultT]],
        *,
        started_at: float | None = None,
        purpose: str = "",
    ) -> _ResultT:
        """Run a provider operation under shared capacity and lifecycle coordination."""
        backing = self._validate_store(store)

        async def work() -> _ResultT:
            async with self._locked():
                self._safe(backing.root_path)
                state = self._load(backing)
                view = _RetainedFileStore(self, backing, state, started_at, purpose)
                result = await action(view)
                if view.changed:
                    if not view.failed:
                        for key in view.deleted:
                            state["entries"].pop(key, None)
                        for key in view.pending:
                            record = state["entries"][key]
                            record["state"] = "ready"
                            record["generation"] = self._policy["generation"]
                            record["expires_at"] = (
                                self._now() + self.retention_seconds if self.retention_seconds is not None else None
                            )
                    try:
                        self._save(backing, state)
                    except (ValueError, OSError) as exc:
                        if view.pending or view.deleted:
                            raise _FileMemoryCommitError(
                                "Memory content may have changed, but lifecycle metadata was not committed. "
                                "The interrupted operation is protected from expiry; host repair is required."
                            ) from exc
                        raise
                return result

        return await _complete(work())

    @asynccontextmanager
    async def _protect_store(self, store: AgentFileStore) -> AsyncGenerator[float]:
        """Hold an OS-backed request token until the host closes the request/stream."""
        backing = self._validate_store(store)
        token_lock: AsyncFileLock | None = None
        token_path: Path | None = None
        try:
            async with self._locked():
                self._load(backing)
                tokens = self._control / "active" / self._scope(backing)
                self._safe(self._control / "active")
                self._safe(tokens)
                tokens.mkdir(parents=True, exist_ok=True)
                token_path = tokens / f"{uuid.uuid4().hex}.lock"
                self._check_growth(token_path, 0)
                token_lock = AsyncFileLock(token_path, timeout=0, preserve_lock_file=True, fallback_to_soft=False)
                await token_lock.acquire()
                started_at = self._now()
            yield started_at  # ruff: ignore[unnecessary-assign-before-yield] - capture visibility while registration holds the lock
        finally:
            if token_lock is not None:

                async def release() -> None:
                    try:
                        async with self._locked(load_policy=False):
                            await token_lock.release()
                            if token_path is not None:
                                token_path.unlink(missing_ok=True)
                                if token_path.parent.exists() and not any(token_path.parent.iterdir()):
                                    token_path.parent.rmdir()
                    finally:
                        # A broken policy/control directory must not pin an OS lease.
                        await token_lock.release()

                await _complete(release())

    async def _active(self, store: FileSystemAgentFileStore) -> bool:
        return await self._tokens_active(self._scope(store))

    async def _tokens_active(self, scope: str) -> bool:
        tokens = self._control / "active" / scope
        self._safe(tokens)
        if not tokens.exists():
            return False
        active = False
        for path in tokens.iterdir():
            self._safe(path)
            if (
                not path.is_file()
                or path.suffix != ".lock"
                or len(path.stem) != 32
                or any(c not in "0123456789abcdef" for c in path.stem)
                or path.stat().st_size
            ):
                raise ValueError("Unexpected file in the request protection directory.")
            probe = AsyncFileLock(path, timeout=0, preserve_lock_file=True, fallback_to_soft=False)
            try:
                await probe.acquire()
            except Timeout:
                active = True
            else:
                await probe.release()
                path.unlink(missing_ok=True)
        if not active:
            tokens.rmdir()
        return active

    async def collect(self) -> int:
        """Delete registered expired memories, retaining active or uncertain scopes."""

        async def work() -> int:
            async with self._locked():
                return await self._collect_locked()

        return await _complete(work())

    async def _collect_locked(self) -> int:
        removed = 0
        active_scopes: set[str] = set()
        active = self._control / "active"
        self._safe(active)
        if active.exists():
            for tokens in active.iterdir():
                self._safe(tokens)
                if (
                    not tokens.is_dir()
                    or len(tokens.name) != 64
                    or any(c not in "0123456789abcdef" for c in tokens.name)
                ):
                    raise ValueError("Unexpected request protection metadata.")
                if await self._tokens_active(tokens.name):
                    active_scopes.add(tokens.name)
        if self.retention_seconds is None:
            return 0
        for root in list(self.directory.iterdir()):
            if root == self._control or not root.is_dir():
                continue
            try:
                self._safe(root)
                backing = FileSystemAgentFileStore(root)
                state = self._load(backing)
                limits = self._stored_limits(state)
                if limits is not None:
                    backing = FileSystemAgentFileStore(
                        root,
                        max_file_bytes=limits.max_file_bytes,
                        max_files=limits.max_files,
                        max_total_bytes=limits.max_total_bytes,
                    )
                if self._scope(backing) in active_scopes:
                    continue
                view = _RetainedFileStore(self, backing, state, None, "gc")
                files = self._files(root)
                paths = {self._key(backing, p): p for p in files}
                folders = {self._key(backing, p.parent): p.parent for p in files}
                for key, record in list(state["entries"].items()):
                    deadline = self._deadline(record)
                    if record["state"] == "updating":
                        logger.warning("Retaining interrupted memory update; explicit repair is required.")
                        continue
                    if record["state"] != "deleting" and (deadline is None or deadline > self._now()):
                        continue
                    body, folder = paths.get(key), folders.get(record["folder"])
                    if body is not None and (
                        view.internal(body.name)
                        or record["folder"] != self._key(backing, body.parent)
                        or record["description"] != self._key(backing, body.with_name(view._description(body.name)))  # pyright: ignore[reportPrivateUsage]
                    ):
                        raise ValueError("Inconsistent file-memory lifecycle references.")
                    record["state"] = "deleting"
                    self._save(backing, state, reclaim=True)
                    if body is not None:
                        body.unlink(missing_ok=True)
                    description = paths.get(record["description"])
                    if description is not None:
                        from ._file_memory import _description_file_name  # pyright: ignore[reportPrivateUsage]

                        referenced = any(
                            p.exists()
                            and not view.internal(p.name)
                            and p.parent == description.parent
                            and os.path.normcase(_description_file_name(p.name)) == os.path.normcase(description.name)
                            for p in files
                        )
                        if not referenced:
                            description.unlink(missing_ok=True)
                    del state["entries"][key]
                    if folder is not None and folder.exists():
                        index = folder / "memories.md"
                        if any(not view.internal(p.name) for p in folder.iterdir() if p.is_file()):
                            try:
                                await self._write_index(backing, view, folder)
                            except _FileStoreQuotaError:
                                # The index is a projection; insufficient space must not
                                # leave an already-deleted body permanently tombstoned.
                                index.unlink(missing_ok=True)
                                logger.warning("Deferred memory index rebuild due to capacity; stale index removed.")
                        else:
                            index.unlink(missing_ok=True)
                            if not any(folder.iterdir()):
                                folder.rmdir()
                    self._save(backing, state, reclaim=True)
                    removed += 1
                directories: list[Path] = []
                pending = [root]
                while pending:
                    directory = pending.pop()
                    self._safe(directory)
                    directories.append(directory)
                    pending.extend(path for path in directory.iterdir() if path.is_dir())
                for directory in reversed(directories[1:]):
                    if not any(directory.iterdir()):
                        directory.rmdir()
                if not state["entries"] and not self._files(root):
                    self._manifest_path(backing).unlink(missing_ok=True)
                    if not any(root.iterdir()):
                        root.rmdir()
            except (ValueError, OSError) as exc:
                logger.warning("Skipped file-memory cleanup (%s).", type(exc).__name__)
        return removed

    async def repair(self, store: AgentFileStore) -> int:
        """Confirm retained interrupted updates after the operator inspects their content.

        Args:
            store: Supported filesystem store belonging to this manager.

        Returns:
            Number of interrupted updates confirmed or removed if the body is absent.

        This is an explicit confirmation, not proof that a multi-file write completed.
        Present bodies are accepted as their current content, indexes are rebuilt, and
        a fresh lifetime begins. Pending deletions remain deletions. Active scopes
        cannot be repaired.
        """
        backing = self._validate_store(store)

        async def work() -> int:
            async with self._locked():
                if await self._active(backing):
                    raise ValueError("Cannot repair a memory scope while a request is active.")
                state = self._load(backing)
                files = self._files(backing.root_path)
                paths = {self._key(backing, path): path for path in files}
                folders = {self._key(backing, path.parent): path.parent for path in files}
                view = _RetainedFileStore(self, backing, state, None, "repair")
                affected: set[Path] = set()
                repaired = 0
                for key, record in list(state["entries"].items()):
                    if record["state"] != "updating":
                        continue
                    body, folder = paths.get(key), folders.get(record["folder"])
                    if body is None:
                        state["entries"].pop(key)
                    else:
                        record["state"] = "ready"
                        record["generation"] = self._policy["generation"]
                        record["expires_at"] = (
                            self._now() + self.retention_seconds if self.retention_seconds is not None else None
                        )
                    if folder is not None:
                        affected.add(folder)
                    repaired += 1
                for folder in affected:
                    await self._write_index(backing, view, folder)
                if repaired:
                    self._save(backing, state)
                return repaired

        return await _complete(work())

    async def __aenter__(self) -> FileMemoryRetentionManager:
        """Start one server-owned sweeper; each sweep uses current on-disk state."""
        if self._sweeper is not None:
            raise RuntimeError("The file-memory retention manager is already running.")

        async with self._locked():
            pass

        async def sweep() -> None:
            while True:
                await asyncio.sleep(self.sweep_interval_seconds)
                try:
                    await self.collect()
                except (ValueError, OSError) as exc:
                    logger.warning("File-memory sweep failed (%s).", type(exc).__name__)

        self._sweeper = asyncio.create_task(sweep())
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Stop GC; task shutdown does not itself select a retention-resume policy."""
        if self._sweeper is not None:
            self._sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await self._sweeper
            self._sweeper = None


class _RetainedFileStore(AgentFileStore):
    """Request-local view; all operations hold the manager lock."""

    def __init__(
        self,
        manager: FileMemoryRetentionManager,
        backing: FileSystemAgentFileStore,
        state: dict[str, Any],
        started_at: float | None,
        purpose: str,
    ) -> None:
        self.manager, self.backing, self.state = manager, backing, state
        self.started_at, self.purpose = started_at, purpose
        self.pending: set[str] = set()
        self.deleted: set[str] = set()
        self.changed = self.failed = False

    @staticmethod
    def internal(name: str) -> bool:
        return name.lower() == "memories.md" or name.lower().endswith("_description.md")

    def _path(self, path: str) -> Path:
        return self.backing._resolve_safe_path(path)  # pyright: ignore[reportPrivateUsage]

    def _visible(self, path: str) -> bool:
        record = self.state["entries"].get(self.manager._key(self.backing, self._path(path)))  # pyright: ignore[reportPrivateUsage]
        if record is None:
            return True
        if record["state"] == "deleting":
            return False
        if record["state"] == "updating" or self.manager.retention_seconds is None:
            return True
        deadline = self.manager._deadline(record)  # pyright: ignore[reportPrivateUsage]
        cutoff = self.started_at if self.started_at is not None else self.manager._now()  # pyright: ignore[reportPrivateUsage]
        return deadline is None or deadline > cutoff

    def _touch(self, path: str) -> None:
        record = self.state["entries"].get(self.manager._key(self.backing, self._path(path)))  # pyright: ignore[reportPrivateUsage]
        if record is not None and record["state"] == "ready" and self.manager.retention_seconds is not None:
            record["expires_at"] = self.manager._now() + self.manager.retention_seconds  # pyright: ignore[reportPrivateUsage]
            record["generation"] = self.manager._policy["generation"]  # pyright: ignore[reportPrivateUsage]
            self.changed = True

    async def write(self, path: str, content: str, *, overwrite: bool = True) -> None:
        target = self._path(path)
        try:
            limits = self.backing._limits  # pyright: ignore[reportPrivateUsage]
            sizing = limits or _FileStoreLimits(
                None,
                None,
                self.manager._capacity.max_total_bytes if self.manager._capacity else None,  # pyright: ignore[reportPrivateUsage]
            )
            if not overwrite and target.exists():
                raise FileExistsError("The memory file already exists.")
            size = sizing.content_size(content)

            def check() -> None:
                self.manager._check_store_growth(self.backing, target, size)  # pyright: ignore[reportPrivateUsage]
                if self.internal(target.name):
                    self.manager._check_growth(target, size)  # pyright: ignore[reportPrivateUsage]
                    return
                key = self.manager._key(self.backing, target)  # pyright: ignore[reportPrivateUsage]
                previous = self.state["entries"].get(key)
                record: dict[str, Any] = {
                    **(previous or {}),
                    "state": "ready",
                    "expires_at": self.manager._now() + self.manager.retention_seconds  # pyright: ignore[reportPrivateUsage]
                    if self.manager.retention_seconds is not None
                    else None,
                    "generation": self.manager._policy["generation"],  # pyright: ignore[reportPrivateUsage]
                    "folder": self.manager._key(self.backing, target.parent),  # pyright: ignore[reportPrivateUsage]
                    "description": self.manager._key(self.backing, target.with_name(self._description(target.name))),  # pyright: ignore[reportPrivateUsage]
                }
                self.state["entries"][key] = record
                config: dict[str, Any] = {
                    **(self.state.get("store_limits") or {}),
                    "max_file_bytes": limits.max_file_bytes if limits else None,
                    "max_files": limits.max_files if limits else None,
                    "max_total_bytes": limits.max_total_bytes if limits else None,
                }
                self.state["store_limits"] = config
                payload_size = len(json.dumps(self.state, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                # A finite float's JSON representation is shorter than 32 bytes;
                # reserve its maximum field width before touching the body.
                if record["expires_at"] is not None:
                    payload_size += max(0, 32 - len(json.dumps(record["expires_at"])))
                if previous is None:
                    self.state["entries"].pop(key)
                else:
                    self.state["entries"][key] = previous
                self.manager._check_combined_growth(  # pyright: ignore[reportPrivateUsage]
                    [(target, size), (self.manager._manifest_path(self.backing), payload_size)]  # pyright: ignore[reportPrivateUsage]
                )

            try:
                check()
            except _FileStoreQuotaError:
                await self.manager._collect_locked()  # pyright: ignore[reportPrivateUsage]
                loaded = self.manager._load(self.backing)  # pyright: ignore[reportPrivateUsage]
                self.state.clear()
                self.state.update(loaded)
                check()
            if not self.internal(target.name):
                key = self.manager._key(self.backing, target)  # pyright: ignore[reportPrivateUsage]
                record = self.state["entries"].get(key)
                if record is not None and record["state"] == "deleting":
                    raise ValueError("This memory has a pending deletion; host cleanup must finish first.")
                self.state["entries"][key] = {
                    **(record or {}),
                    "state": "updating",
                    "expires_at": None,
                    "generation": self.manager._policy["generation"],  # pyright: ignore[reportPrivateUsage]
                    "folder": self.manager._key(self.backing, target.parent),  # pyright: ignore[reportPrivateUsage]
                    "description": self.manager._key(self.backing, target.with_name(self._description(target.name))),  # pyright: ignore[reportPrivateUsage]
                }
                self.manager._save(self.backing, self.state)  # pyright: ignore[reportPrivateUsage]
                try:
                    self.manager._check_growth(target, size)  # pyright: ignore[reportPrivateUsage]
                except _FileStoreQuotaError:
                    if record is None:
                        self.state["entries"].pop(key, None)
                    else:
                        self.state["entries"][key] = record
                    self.manager._save(self.backing, self.state, reclaim=True)  # pyright: ignore[reportPrivateUsage]
                    raise
                self.pending.add(key)
                self.changed = True
            self.manager._check_growth(target, size)  # pyright: ignore[reportPrivateUsage]
            await asyncio.to_thread(self.manager._atomic, target, content.encode("utf-8"), overwrite=overwrite)  # pyright: ignore[reportPrivateUsage]
        except BaseException:
            self.failed = True
            raise

    @staticmethod
    def _description(name: str) -> str:
        from ._file_memory import _description_file_name  # pyright: ignore[reportPrivateUsage]

        return _description_file_name(name)

    async def read(self, path: str) -> str | None:
        if Path(path).name.lower() == "memories.md":
            directory = Path(path).parent.as_posix()
            content = await self.index_text("" if directory == "." else directory)
            return content if content.strip() != "# Memory Index" else None
        if not self.internal(Path(path).name) and not self._visible(path):
            return None
        target = self._path(path)
        if target.name.lower().endswith("_description.md") and target.parent.exists():
            references = [
                body
                for body in target.parent.iterdir()
                if body.is_file()
                and not self.internal(body.name)
                and os.path.normcase(self._description(body.name)) == os.path.normcase(target.name)
            ]
            key = self.manager._key(self.backing, target)  # pyright: ignore[reportPrivateUsage]
            registered = any(record["description"] == key for record in self.state["entries"].values())
            if (references or registered) and not any(
                self._visible(body.relative_to(self.backing.root_path).as_posix()) for body in references
            ):
                return None
        try:
            content = await self.backing.read(path)
        except ValueError:
            self.failed = self.failed or bool(self.pending or self.deleted)
            raise
        if content is not None and not self.internal(Path(path).name) and self.purpose == "read":
            self._touch(path)
        return content

    async def delete(self, path: str) -> bool:
        target = self._path(path)
        if not self.internal(target.name):
            key = self.manager._key(self.backing, target)  # pyright: ignore[reportPrivateUsage]
            record = self.state["entries"].get(key)
            if record is not None:
                record["state"] = "deleting"
                self.manager._save(self.backing, self.state, reclaim=True)  # pyright: ignore[reportPrivateUsage]
                self.deleted.add(key)
                self.changed = True
        elif target.name.lower().endswith("_description.md") and target.parent.exists():
            if any(
                p.is_file()
                and not self.internal(p.name)
                and os.path.normcase(self._description(p.name)) == os.path.normcase(target.name)
                for p in target.parent.iterdir()
            ):
                return False
        try:
            return await asyncio.to_thread(self.backing._delete_file_sync, target)  # pyright: ignore[reportPrivateUsage]
        except BaseException:
            self.failed = True
            raise

    async def list_children(self, directory: str = "") -> list[FileStoreEntry]:
        entries = await self.backing.list_children(directory)
        return [
            entry
            for entry in entries
            if entry.type != FileStoreEntry.FILE
            or self.internal(entry.name)
            or self._visible(f"{directory}/{entry.name}" if directory else entry.name)
        ]

    async def file_exists(self, path: str) -> bool:
        return self._visible(path) and await self.backing.file_exists(path)

    async def create_directory(self, path: str) -> None:
        await self.backing.create_directory(path)

    async def search(
        self, directory: str, regex_pattern: str, glob_pattern: str | None = None, *, recursive: bool = False
    ) -> list[FileSearchResult]:
        results = await super().search(directory, regex_pattern, glob_pattern, recursive=recursive)
        for result in results:
            if not self.internal(Path(result.file_name).name):
                self._touch(f"{directory}/{result.file_name}" if directory else result.file_name)
        return results

    async def index_text(self, directory: str) -> str:
        from ._file_memory import _MAX_INDEX_ENTRIES  # pyright: ignore[reportPrivateUsage]

        entries = await self.list_children(directory)
        names = sorted(
            (entry.name for entry in entries if entry.type == FileStoreEntry.FILE and not self.internal(entry.name)),
            key=str.lower,
        )
        lines = ["# Memory Index", ""]
        for name in names[:_MAX_INDEX_ENTRIES]:
            path = f"{directory}/{self._description(name)}" if directory else self._description(name)
            description = await self.backing.read(path)
            lines.append(
                f"- **{name}**: {description.strip()}" if description and description.strip() else f"- **{name}**"
            )
        content = "\n".join(lines) + "\n"
        limits = self.backing._limits  # pyright: ignore[reportPrivateUsage]
        if limits is not None:
            limits.content_size(content)
        return content
