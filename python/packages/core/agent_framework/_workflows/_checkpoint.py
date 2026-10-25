# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import logging
import os
import stat
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, TypeAlias

from ..exceptions import WorkflowCheckpointException

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ._events import WorkflowEvent
    from ._runner_context import WorkflowMessage

# Type alias for checkpoint IDs in case we want to change the
# underlying type in the future (e.g., to UUID or a custom class)
CheckpointID: TypeAlias = str
_MAX_GET_LATEST_ATTEMPTS = 3
_GET_LATEST_RETRY_DELAY_SECONDS = 0.05


class _CheckpointScanInvalidated(WorkflowCheckpointException):
    """Internal signal that an optimistic scan was invalidated by concurrent changes.

    Raised only inside the worker thread used by ``get_latest`` and always consumed
    by its retry loop. Callers see a plain :class:`WorkflowCheckpointException`
    only when every attempt is invalidated.
    """


@dataclass(slots=True)
class WorkflowCheckpoint:
    """Represents a complete checkpoint of workflow state.

    Checkpoints capture the full execution state of a workflow at a specific point,
    enabling workflows to be paused and resumed.

    Note that a checkpoint is not tied to a specific workflow instance, but rather to
    a workflow definition (identified by workflow_name and graph_signature_hash). Thus,
    the ID of the workflow instance that created the checkpoint is not included in the
    checkpoint data. This allows checkpoints to be shared and restored across different
    workflow instances of the same workflow definition.

    Attributes:
        workflow_name: Name of the workflow this checkpoint belongs to. This acts as a
            logical grouping for checkpoints and can be used to filter checkpoints by
            workflow. Workflows with the same name are expected to have compatible graph
            structures for checkpointing.
        graph_signature_hash: Hash of the workflow graph topology to validate checkpoint
            compatibility during restore
        checkpoint_id: Unique identifier for this checkpoint
        previous_checkpoint_id: ID of the previous checkpoint in the chain, if any. This
            allows chaining checkpoints together to form a history of workflow states.
        timestamp: ISO 8601 timestamp when checkpoint was created
        messages: Messages exchanged between executors
        state: Committed workflow state including user data, executor states, and
            edge runner delivery state. This contains only committed state; pending
            state changes are not included in checkpoints. Executor states are stored
            under the reserved key '_executor_state', and edge runner state, such as
            partially filled fan-in buffers, under '_edge_state'.
        pending_request_info_events: Any pending request info events that have not
            yet been processed at the time of checkpointing. This allows the workflow
            to resume with the correct pending events after a restore.
        iteration_count: Current iteration number when checkpoint was created.
            Note: iteration_count is not guaranteed to be unique across a workflow's
            lifecycle. It marks the superstep boundary the checkpoint sits on, and the
            same boundary can carry more than one checkpoint. For example, a run that
            pauses at ``IDLE_WITH_PENDING_REQUESTS`` records a checkpoint after superstep
            K; when responses are later delivered, a response-entry checkpoint is recorded
            at the same iteration K (responses in-flight, before superstep K+1 runs).
            Both share iteration K but are distinct checkpoints. Checkpoint ordering is
            defined by the ``previous_checkpoint_id`` lineage chain (and ``timestamp``),
            not by ``iteration_count``; do not use ``iteration_count`` to identify the
            latest checkpoint in human-in-the-loop flows.
        metadata: Additional metadata (e.g., superstep info, graph signature)
        version: Checkpoint format version

    Note:
        The state dict may contain reserved keys managed by the framework.
        See State class documentation for details on reserved keys.
    """

    workflow_name: str
    graph_signature_hash: str

    checkpoint_id: CheckpointID = field(default_factory=lambda: str(uuid.uuid4()))
    previous_checkpoint_id: CheckpointID | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Core workflow state
    messages: dict[str, list[WorkflowMessage]] = field(default_factory=dict)  # type: ignore[misc]
    state: dict[str, Any] = field(default_factory=dict)  # type: ignore[misc]
    pending_request_info_events: dict[str, WorkflowEvent[Any]] = field(default_factory=dict)  # type: ignore[misc]

    # Runtime state
    iteration_count: int = 0

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)  # type: ignore[misc]
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """Convert the WorkflowCheckpoint to a dictionary.

        Notes:
            1. This method does not recursively convert nested dataclasses to dicts.
            2. This is a shallow conversion. The resulting dict will contain the same
               references to nested objects as the original dataclass.
        """
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkflowCheckpoint:
        """Create a WorkflowCheckpoint from a dictionary.

        Args:
            data: Dictionary containing checkpoint fields.

        Returns:
            A new WorkflowCheckpoint instance.

        Raises:
            WorkflowCheckpointException: If required fields are missing.
        """
        try:
            return cls(**data)
        except Exception as ex:
            raise WorkflowCheckpointException(f"Failed to create WorkflowCheckpoint from dict: {ex}") from ex


class CheckpointStorage(Protocol):
    """Protocol for checkpoint storage backends."""

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Create a copy of the given checkpoint and store it, returning its ID.

        Args:
            checkpoint: The WorkflowCheckpoint object to save.

        Returns:
            The unique ID of the saved checkpoint.
        """
        ...

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a checkpoint by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to load.

        Returns:
            A copy of the WorkflowCheckpoint object corresponding to the given ID.

        Raises:
            WorkflowCheckpointException: If no checkpoint with the given ID exists.
        """
        ...

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List checkpoint objects for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoints for.

        Returns:
            A list of copies of WorkflowCheckpoint objects for the specified workflow name.
        """
        ...

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        """Delete a checkpoint by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to delete.

        Returns:
            True if the checkpoint was successfully deleted, False if no checkpoint with the given ID exists.
        """
        ...

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Get the latest checkpoint for a given workflow name.

        Args:
            workflow_name: The name of the workflow to get the latest checkpoint for.

        Returns:
            A copy of the latest WorkflowCheckpoint object for the specified workflow name,
            or None if no checkpoints exist.
        """
        ...

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        """List checkpoint IDs for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoint IDs for.

        Returns:
            A list of checkpoint IDs for the specified workflow name.
        """
        ...


class InMemoryCheckpointStorage:
    """In-memory checkpoint storage for testing and development."""

    def __init__(self) -> None:
        """Initialize the memory storage."""
        self._checkpoints: dict[CheckpointID, WorkflowCheckpoint] = {}

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Create a copy of the given checkpoint and store it, returning its ID."""
        self._checkpoints[checkpoint.checkpoint_id] = copy.deepcopy(checkpoint)
        logger.debug(f"Saved checkpoint {checkpoint.checkpoint_id} to memory")
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a checkpoint by ID."""
        checkpoint = self._checkpoints.get(checkpoint_id)
        if checkpoint:
            logger.debug(f"Loaded checkpoint {checkpoint_id} from memory")
            return copy.deepcopy(checkpoint)
        raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id}")

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List checkpoint objects for a given workflow name."""
        return [copy.deepcopy(cp) for cp in self._checkpoints.values() if cp.workflow_name == workflow_name]

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        """Delete a checkpoint by ID."""
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
            logger.debug(f"Deleted checkpoint {checkpoint_id} from memory")
            return True
        return False

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Get the latest checkpoint for a given workflow name."""
        checkpoints = [cp for cp in self._checkpoints.values() if cp.workflow_name == workflow_name]
        if not checkpoints:
            return None
        latest_checkpoint = max(checkpoints, key=lambda cp: datetime.fromisoformat(cp.timestamp))
        logger.debug(f"Latest checkpoint for workflow {workflow_name} is {latest_checkpoint.checkpoint_id}")
        return copy.deepcopy(latest_checkpoint)

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        """List checkpoint IDs. If workflow_id is provided, filter by that workflow."""
        return [cp.checkpoint_id for cp in self._checkpoints.values() if cp.workflow_name == workflow_name]


# Process-wide serialization of writes per destination file.
#
# asyncio.Lock is loop-bound, so a per-(loop, checkpoint-id) registry cannot
# serialize two FileCheckpointStorage instances pointed at the same directory, nor one
# instance driven from two event loops. Ownership is therefore handed out by a
# process-wide queue keyed by the canonical destination path, and taken *before* the
# write is submitted to a worker thread rather than inside it.
#
# Hand-off runs over ``concurrent.futures.Future`` signals, which are not bound to a
# loop, so a single chain orders writers regardless of which loop enqueued them, and
# waiters suspend on the event loop instead of occupying an ``asyncio.to_thread``
# worker. Blocking on a ``threading.Lock`` inside the worker instead -- the original
# design -- let a burst of same-path saves fill the default executor and stall unrelated
# ``to_thread`` work, including checkpoint loads, and could deadlock once the write that
# had to finish first was queued behind those waiters.
#
# Those signals are awaited through ``_wait_for_signal``, never ``asyncio.wrap_future``.
# Cancellation is the reason: ``wrap_future`` chains it into the future it wraps, so one
# cancelled waiter would cancel the signal an earlier writer still has to resolve, and
# the ``asyncio`` task wrapping a submitted write reports ``done()`` while its function
# is still running on the executor thread. Both let a later save start its ``os.replace``
# beside an earlier one, after which the earlier write can land last and overwrite the
# newer checkpoint.
#
# Entries are reference-counted by queued-or-running operations and dropped when the
# last one releases, so a process that saves many distinct checkpoint IDs -- the
# default, since ``WorkflowCheckpoint`` generates a fresh UUID -- does not retain an
# entry per ID for its lifetime.
#
# The scope really is one process. Several replicas sharing a checkpoint directory -- a
# mounted volume, a network share -- get no serialization from this, because there is no
# shared state between them to coordinate through. Concurrent saves of the same
# checkpoint ID from different processes still rely on ``os.replace`` being atomic on
# the underlying filesystem for the file not to be seen half-written; which write
# survives is undefined.
_destination_queues: dict[Path, _DestinationQueue] = {}
# A completed predecessor invokes callbacks synchronously. If cancellation lands while
# a save is entering the queue, its deferred release can therefore run re-entrantly on
# the same thread before the enqueue frame has left this guard. A plain Lock deadlocks
# that release (and permanently wedges every later save), while an RLock still excludes
# all other threads and lets the owning thread finish the hand-off.
_destination_queues_guard = threading.RLock()


@dataclass
class _DestinationQueue:
    """FIFO ownership hand-off for one destination path."""

    #: Completion signal of the most recently enqueued operation, awaited by the next.
    tail: Future[None] | None = None
    #: Operations queued or running for this path; the entry is dropped at zero.
    pending: int = 0


@dataclass
class _WriteTicket:
    """One operation's place in a destination's queue."""

    path: Path
    #: Signal to await before taking ownership; ``None`` when the queue was empty.
    predecessor: Future[None] | None
    #: Signal this operation resolves to hand ownership to its successor.
    completion: Future[None]
    #: Set by whichever of the worker thread or the coroutine releases first.
    released: bool = False
    #: Failure raised by the write, recorded on the worker thread. A cancelled caller
    #: never sees it, and a cancelled task hides its own exception, so the ticket is the
    #: only place it survives.
    error: BaseException | None = None


def _enqueue_write(file_path: Path) -> _WriteTicket:
    """Take a place in *file_path*'s queue without waiting for it."""
    completion: Future[None] = Future()
    with _destination_queues_guard:
        queue = _destination_queues.get(file_path)
        if queue is None:
            queue = _DestinationQueue()
            _destination_queues[file_path] = queue
        predecessor = queue.tail
        queue.tail = completion
        queue.pending += 1
    return _WriteTicket(path=file_path, predecessor=predecessor, completion=completion)


def _wait_for_signal(
    source: Future[None],
    *,
    on_abandoned: Callable[[], None] | None = None,
) -> asyncio.Future[None]:
    """Return a fresh awaitable that completes when *source* does.

    Deliberately not ``asyncio.wrap_future``: that chains cancellation into the future it
    wraps, so a waiter cancelled here would cancel the hand-off signal an earlier writer
    still has to resolve, and every later writer keyed to it. A per-wait future fed by a
    done-callback leaves *source* untouched no matter what happens to the waiter.
    """
    loop = asyncio.get_running_loop()
    waiter: asyncio.Future[None] = loop.create_future()

    def _resolve(_completed: Future[None]) -> None:
        def _set() -> None:
            if not waiter.done():
                waiter.set_result(None)

        try:
            loop.call_soon_threadsafe(_set)
        except RuntimeError:
            # The waiter's loop has closed, so the coroutine suspended here will never
            # resume and cannot do anything on its way out. Whatever it owed -- releasing
            # its place in the queue, above all -- has to happen here instead, on the
            # thread that resolved the signal.
            #
            # This catches a loop that is already closed when the signal resolves. It
            # cannot catch one that closes in the window after `call_soon_threadsafe`
            # succeeded but before the callback runs, nor one abandoned without being
            # closed at all: both leave a queued ticket unreleased. Reaching either needs
            # a loop closed with tasks still pending, which asyncio already reports as an
            # error, and a graceful shutdown is unaffected -- `asyncio.run` cancels
            # pending tasks first, which drives the queued save through its cancellation
            # path and defers the hand-off onto the predecessor.
            if on_abandoned is not None:
                on_abandoned()

    source.add_done_callback(_resolve)
    return waiter


async def _await_signal_through_cancellation(source: Future[None]) -> None:
    """Wait until *source* resolves, absorbing cancellations delivered meanwhile.

    Used to wait out a write this coroutine still owns. Waiting on the ``asyncio`` task
    wrapping the write is not equivalent: a cancelled task reports ``done()`` while its
    function is still running on the executor thread, so ownership would be released
    with the write still in flight. Only the signal the worker thread resolves tracks
    the write itself, and cancellation cannot mark it done.

    The done-callback is registered once and points at whichever waiter is current,
    rather than one callback per wait. Each cancellation would otherwise leave another
    callback on the signal, so a caller cancelling in a loop would grow that list in
    step with it and pay for the whole list when the write finally lands.
    """
    if source.done():
        # Purely to avoid registering a callback that would fire straight back; the loop
        # condition below already short-circuits, so this is not load-bearing.
        return

    loop = asyncio.get_running_loop()
    current: dict[str, asyncio.Future[None] | None] = {"waiter": None}

    def _resolve(_completed: Future[None]) -> None:
        def _set() -> None:
            waiter = current["waiter"]
            if waiter is not None and not waiter.done():
                waiter.set_result(None)

        # Safe to swallow here, unlike the queued wait in `_wait_for_signal`. By the
        # time anything drains, the write has been submitted, so the worker thread and
        # the submitted future's callback both release the ticket without needing this
        # loop; a closed loop only means there is nobody left to wake.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(_set)

    source.add_done_callback(_resolve)
    while not source.done():
        waiter: asyncio.Future[None] = loop.create_future()
        current["waiter"] = waiter
        try:
            await waiter
        except asyncio.CancelledError:
            # Re-delivered cancellation. The signal may have resolved against the waiter
            # we just abandoned, so the loop condition is what decides whether to stop.
            continue


def _release_write_after(ticket: _WriteTicket, predecessor: Future[None]) -> None:
    """Hand *ticket*'s ownership on only once *predecessor* has actually finished.

    A ticket cancelled while still queued must not resolve its own signal immediately:
    an earlier writer still owns the destination, and the next waiter would start its
    write alongside that one. Deferring keeps the queue in order while still guaranteeing
    the hand-off happens, so nothing waits forever behind a cancelled save.
    """
    predecessor.add_done_callback(lambda _completed: _release_write(ticket))


class _ReleaseTrampoline(threading.local):
    """Releases waiting for the one currently unwinding on this thread.

    Resolving one ticket's signal runs the next ticket's deferred-release callback
    synchronously, so a run of cancelled queued saves would otherwise nest one stack
    frame per link and raise ``RecursionError`` on the worker thread partway through --
    leaving the destination owned for good. Collecting them here and draining in a loop
    keeps the depth flat however long the run is.
    """

    queued: list[_WriteTicket] | None = None


_release_trampoline = _ReleaseTrampoline()


def _release_write(ticket: _WriteTicket) -> None:
    """Hand ownership to the next waiter and drop the entry once nothing is queued.

    Called from three places, whichever gets there first, and idempotent so all can:

    * the worker thread, as the last act of the write itself. This is what keeps a
      destination usable if the event loop that submitted the write goes away before the
      coroutine can resume -- the thread finishes and releases regardless.
    * a done-callback on the submitted write, which fires on success, failure and
      cancellation alike, so the executor dropping the work still releases.
    * the coroutine, when the write was never submitted at all.

    Resolving the completion signal is what keeps the chain moving, so an operation that
    is cancelled or fails must still release rather than stall every later writer.
    """
    queued = _release_trampoline.queued
    if queued is not None:
        # A release is already unwinding on this thread; let it drain this one.
        queued.append(ticket)
        return

    draining: list[_WriteTicket] = []
    _release_trampoline.queued = draining
    try:
        _release_one_write(ticket)
        while draining:
            _release_one_write(draining.pop(0))
    finally:
        _release_trampoline.queued = None


def _release_one_write(ticket: _WriteTicket) -> None:
    """Release exactly one ticket. Only ``_release_write`` should call this."""
    with _destination_queues_guard:
        if ticket.released:
            return
        ticket.released = True
        queue = _destination_queues.get(ticket.path)
        if queue is not None:
            queue.pending -= 1
            if queue.pending <= 0:
                del _destination_queues[ticket.path]
    # Outside the guard: waking the successor must not happen while holding the lock its
    # own release will need.
    if not ticket.completion.done():
        ticket.completion.set_result(None)


class FileCheckpointStorage:
    """File-based checkpoint storage for persistence.

    This storage implements a hybrid approach where the checkpoint metadata and structure are
    stored in JSON format, while the actual state data (which may contain complex Python objects)
    is serialized using pickle and embedded as base64-encoded strings within the JSON. This allows
    for human-readable checkpoint files while preserving the ability to store complex Python objects.

    By default, checkpoint deserialization is restricted to a built-in set of safe Python types
    (primitives, datetime, uuid, ...), all ``agent_framework`` and ``agent_framework_orchestrations``
    internal types, and OpenAI SDK types (``openai.types``). To allow additional application-specific
    types, register them with ``agent_framework.register_checkpoint_type`` or pass them via the
    ``allowed_checkpoint_types`` parameter using ``"module:qualname"`` format.

    Example::

        storage = FileCheckpointStorage(
            "/tmp/checkpoints",
            allowed_checkpoint_types=[
                "my_app.models:MyState",
            ],
        )
    """

    _DELETE_LOCK_STRIPE_COUNT: ClassVar[int] = 64
    _DELETE_LOCKS: ClassVar[tuple[threading.Lock, ...]] = tuple(
        threading.Lock() for _ in range(_DELETE_LOCK_STRIPE_COUNT)
    )

    def __init__(
        self,
        storage_path: str | Path,
        *,
        allowed_checkpoint_types: list[str] | None = None,
    ) -> None:
        """Initialize the file storage.

        Args:
            storage_path: Directory path where checkpoint files will be stored.
            allowed_checkpoint_types: Additional types (beyond the built-in safe set
                and framework types) that are permitted during checkpoint
                deserialization.  Each entry should be a ``"module:qualname"``
                string (e.g., ``"my_app.models:MyState"``).
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._allowed_types: frozenset[str] = frozenset(allowed_checkpoint_types or [])
        logger.info(f"Initialized file checkpoint storage at {self.storage_path}")

    def _validate_file_path(self, checkpoint_id: CheckpointID) -> Path:
        """Validate that a checkpoint ID resolves to a path within the storage directory.

        This can prevent someone from crafting a checkpoint ID that points to an arbitrary
        file on the filesystem.

        Args:
            checkpoint_id: The checkpoint ID to validate.

        Returns:
            The validated file path.

        Raises:
            WorkflowCheckpointException: If the checkpoint ID would resolve outside the storage directory.
        """
        file_path = (self.storage_path / f"{checkpoint_id}.json").resolve()
        if not file_path.is_relative_to(self.storage_path.resolve()):
            raise WorkflowCheckpointException(f"Invalid checkpoint ID: {checkpoint_id}")
        return file_path

    @classmethod
    def _delete_lock(cls, file_path: Path) -> threading.Lock:
        """Return the process-local deletion lock for a checkpoint file."""
        return cls._DELETE_LOCKS[hash(file_path) % cls._DELETE_LOCK_STRIPE_COUNT]

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Save a checkpoint and return its ID.

        Args:
            checkpoint: The WorkflowCheckpoint object to save.

        Returns:
            The unique ID of the saved checkpoint.

        Raises:
            WorkflowCheckpointException: If the checkpoint cannot be encoded or would
                fail to decode under this storage's ``allowed_checkpoint_types``.
        """
        from ._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value

        file_path = self._validate_file_path(checkpoint.checkpoint_id)
        checkpoint_dict = checkpoint.to_dict()
        # Fail at save time if encoding or restore validation fails (#8181).
        try:
            encoded_checkpoint = encode_checkpoint_value(checkpoint_dict)
            decode_checkpoint_value(encoded_checkpoint, allowed_types=self._allowed_types)
        except WorkflowCheckpointException:
            raise
        except Exception as ex:
            raise WorkflowCheckpointException(
                f"Checkpoint {checkpoint.checkpoint_id} cannot be encoded or restored under "
                "this storage's allowed types; refusing to save."
            ) from ex

        def _replace_with_retry(tmp_path: Path) -> None:
            # On Windows, os.replace can transiently fail with PermissionError when a
            # background indexer or AV scan briefly holds a handle to the destination
            # file. The destination queue serializes concurrent save() calls to the same
            # path, but the OS callback is still external to the process and can trip a
            # transient error even when only one replace is in flight. Retry briefly to
            # absorb it.
            for attempt in range(5):
                try:
                    os.replace(tmp_path, file_path)
                    return
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.001 * (2**attempt))

        def _write_atomic() -> None:
            # No lock here: ownership of the destination is already held by the caller
            # of this function, taken from the process-wide queue before the write was
            # submitted. Acquiring it on the worker instead is what let same-path saves
            # pile up inside the executor.
            #
            # Use a unique temp file per save in the destination directory so
            # concurrent saves of distinct checkpoint IDs never contend on a
            # shared temporary path, and os.replace remains atomic (same
            # filesystem). A short, ID-independent name keeps every destination
            # name accepted by _validate_file_path saveable regardless of
            # checkpoint-ID length or filesystem limits.
            tmp_path: Path | None = None
            try:
                # O_CREAT | O_EXCL | O_WRONLY with an explicit 0o666 mode, so the
                # file is created with the process umask exactly like the previous
                # open(..., "w") path was (NamedTemporaryFile would hard-code 0o600
                # and downgrade modes on POSIX after an os.replace over an existing
                # checkpoint).
                tmp_name = f".maf-ckpt-{uuid.uuid4().hex}.tmp"
                tmp_path = file_path.parent / tmp_name
                fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
                # UTF-8 explicitly, carried over from #8214: `json.dump(..., ensure_ascii=False)`
                # writes non-ASCII raw, and the platform default is cp1252 on Windows, so a
                # checkpoint containing CJK text or emoji raised UnicodeEncodeError. The read
                # sides are UTF-8 too; fixing only one would trade a loud write error for silent
                # read corruption.
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(encoded_checkpoint, f, indent=2, ensure_ascii=False)
                _replace_with_retry(tmp_path)
                tmp_path = None
            finally:
                if tmp_path is not None and tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        # Best-effort cleanup only; leaking a temp file is harmless
                        # compared to masking the original exception.
                        logger.debug(f"Failed to remove checkpoint temp file {tmp_path}", exc_info=True)

        def _write_atomic_and_release(ticket: _WriteTicket) -> None:
            # Release on the worker thread, as the write's last act. The coroutine's
            # `finally` would otherwise be the only releaser, and it never runs if the
            # loop that submitted this write is gone -- leaving the destination owned
            # forever and hanging every later save to it.
            try:
                _write_atomic()
            except BaseException as exc:
                ticket.error = exc
                raise
            finally:
                _release_write(ticket)

        ticket = _enqueue_write(file_path)
        if ticket.predecessor is not None:
            # Suspends on the event loop, not on an executor worker, and orders this save
            # behind every earlier one for the same destination even when they were
            # enqueued from a different loop.
            try:
                await _wait_for_signal(
                    ticket.predecessor,
                    # If this loop dies while we are queued, nothing else would release
                    # this ticket: the write was never submitted, so there is no worker
                    # thread to fall back on, and every later save for the destination
                    # would wait on a signal nobody resolves.
                    on_abandoned=lambda: _release_write(ticket),
                )
            except BaseException:
                # Nothing was submitted and nothing written, but the hand-off cannot
                # happen yet: an earlier writer still owns the destination, and resolving
                # this ticket's signal now would let the next save run its os.replace
                # alongside that one -- after which the earlier write can land last and
                # overwrite the newer checkpoint. Defer the hand-off until the
                # predecessor has actually finished.
                _release_write_after(ticket, ticket.predecessor)
                raise

        # Ownership held from here. Submit through `run_in_executor` rather than
        # `ensure_future(asyncio.to_thread(...))`: the latter creates a Task, and loop
        # shutdown cancels every task, so the write could be cancelled before it ever
        # reached the executor -- leaving nobody to release the destination and this
        # coroutine waiting on a signal that could never be resolved. `run_in_executor`
        # returns a plain Future that `asyncio.all_tasks()` does not include, and it
        # submits synchronously, so returning from it means the write really is queued.
        loop = asyncio.get_running_loop()
        try:
            write_future = loop.run_in_executor(None, _write_atomic_and_release, ticket)
        except BaseException:
            # Never reached the executor, so no worker will release on our behalf.
            _release_write(ticket)
            raise
        # The callback fires on success, failure and cancellation alike, so the
        # destination is released even if the executor drops the work before the function
        # runs. Idempotent with the worker thread's own release, which means no flag is
        # needed to decide which of the two owns it.
        write_future.add_done_callback(lambda _completed: _release_write(ticket))

        try:
            # Shield so a cancellation arriving mid-write cannot leave the write running
            # past this frame: its os.replace would otherwise land after the caller
            # returned, overwriting whatever a later save had published.
            await asyncio.shield(write_future)
        except asyncio.CancelledError:
            # Wait out the write itself rather than the task wrapping it. A cancelled
            # task reports done() while its function is still running on the executor
            # thread, so waiting on `worker` would return with the replace still in
            # flight and ownership about to be released.
            await _await_signal_through_cancellation(ticket.completion)
            if ticket.error is not None:
                # The caller is receiving CancelledError and will never see this, and a
                # cancelled task hides its own exception, so the log is the only place a
                # write that failed while draining can surface.
                logger.warning(
                    f"Checkpoint write to {file_path} failed while draining after cancellation: {ticket.error!r}"
                )
            raise
        except BaseException:
            # The write failed. The worker already released in its own `finally`; this is
            # idempotent cover for a submission that never got that far.
            _release_write(ticket)
            raise

        logger.info(f"Saved checkpoint {checkpoint.checkpoint_id} to {file_path}")
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a checkpoint by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to load.

        Returns:
            The WorkflowCheckpoint object corresponding to the given ID.

        Raises:
            WorkflowCheckpointException: If no checkpoint with the given ID exists,
                or if checkpoint decoding fails.
        """
        file_path = self._validate_file_path(checkpoint_id)

        if not file_path.exists():
            raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id}")

        def _read() -> dict[str, Any]:
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)

        try:
            encoded_checkpoint = await asyncio.to_thread(_read)
        except UnicodeDecodeError as ex:
            raise WorkflowCheckpointException(
                f"Checkpoint file for {checkpoint_id} is not valid UTF-8 and cannot be loaded."
            ) from ex
        except json.JSONDecodeError as ex:
            raise WorkflowCheckpointException(
                f"Checkpoint file for {checkpoint_id} is not valid JSON and cannot be loaded."
            ) from ex

        checkpoint = self._decode_checkpoint(encoded_checkpoint)
        logger.info(f"Loaded checkpoint {checkpoint_id} from {file_path}")
        return checkpoint

    def _decode_checkpoint(self, encoded_checkpoint: dict[str, Any]) -> WorkflowCheckpoint:
        """Decode an already-read checkpoint using this reader's deserialization policy.

        Shared by :meth:`load` and :meth:`get_latest` so both apply the same
        ``allowed_checkpoint_types`` policy. Callers must have already validated the
        on-disk state if snapshot consistency matters; this method only handles
        deserialization.
        """
        from ._checkpoint_encoding import decode_checkpoint_value

        decoded = decode_checkpoint_value(encoded_checkpoint, allowed_types=self._allowed_types)
        return WorkflowCheckpoint.from_dict(decoded)

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List checkpoint objects for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoints for.

        Returns:
            A list of WorkflowCheckpoint objects for the specified workflow name.
        """

        def _list_checkpoints() -> list[WorkflowCheckpoint]:
            checkpoints: list[WorkflowCheckpoint] = []
            for file_path in self.storage_path.glob("*.json"):
                try:
                    with open(file_path, encoding="utf-8") as f:
                        encoded_checkpoint = json.load(f)
                        from ._checkpoint_encoding import decode_checkpoint_value

                        decoded_checkpoint_dict = decode_checkpoint_value(
                            encoded_checkpoint, allowed_types=self._allowed_types
                        )
                        checkpoint = WorkflowCheckpoint.from_dict(decoded_checkpoint_dict)
                    if checkpoint.workflow_name == workflow_name:
                        checkpoints.append(checkpoint)
                except Exception as e:
                    logger.warning(f"Failed to read checkpoint file {file_path}: {e}")
            return checkpoints

        return await asyncio.to_thread(_list_checkpoints)

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        """Delete a checkpoint by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to delete.

        Returns:
            True if the checkpoint was successfully deleted, False if no checkpoint with the given ID exists.
        """
        file_path = self._validate_file_path(checkpoint_id)
        file_lock = self._delete_lock(file_path)

        def _delete() -> bool:
            with file_lock:
                try:
                    file_path.unlink()
                except FileNotFoundError:
                    return False
            logger.info(f"Deleted checkpoint {checkpoint_id} from {file_path}")
            return True

        return await asyncio.to_thread(_delete)

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Get the latest checkpoint for a given workflow name.

        Select from stored metadata and decode only the selected checkpoint, using the same
        data that was read during selection. Files whose owning workflow cannot be
        identified (unparseable JSON, a missing or non-string ``workflow_name``, or
        duplicate ``workflow_name`` keys) are quarantined: they are skipped with a
        warning so a single malformed or legacy file cannot permanently break recovery
        for every workflow sharing this storage root. Invalid content in a file that IS
        identified as belonging to the requested workflow still raises, and invalid
        metadata for a known different workflow is ignored.
        File versions and directory membership are checked before accepting the scan.
        Concurrent changes under the storage root, including an atomic save for a
        different workflow, invalidate the optimistic scan; the scan is retried
        internally a bounded number of times before raising, so ordinary concurrent
        checkpointing does not fail unrelated recovery. Writes after validation belong
        to a subsequent snapshot. This relies on the filesystem reporting file changes
        and writers using atomic replacement, as ``save`` does.
        Checkpoints with equal timestamps retain directory iteration order.
        Nested directories are included, with in-tree directory aliases visited only once.
        Reading and decoding run in a worker thread so decoding does not block the event
        loop.

        Args:
            workflow_name: The name of the workflow to get the latest checkpoint for.

        Returns:
            The latest WorkflowCheckpoint from the validated scan, or None if no matching
            checkpoints exist.

        Raises:
            WorkflowCheckpointException: If a checkpoint owned by ``workflow_name`` cannot
                be read or decoded, the directory cannot be read, matching metadata is
                invalid, or the scan changes on every retry attempt.
        """

        def _version(info: os.stat_result) -> tuple[int, int, int]:
            # On Windows, Path.stat() and os.fstat() use different Win32 APIs and can
            # return different values for st_dev (volume serial number) and st_ino
            # (file ID). Only st_size + st_mtime_ns + st_ctime_ns are reliable across
            # both APIs, which is sufficient to detect both content changes (mtime,
            # size) and file replacement (ctime on Windows is creation time, which
            # updates on os.replace). Symlink escapes are caught separately by
            # _validate_file_path and the is_relative_to(root) check in _checkpoint_paths.
            return info.st_size, info.st_mtime_ns, info.st_ctime_ns

        def _checkpoint_paths(root: Path) -> tuple[list[Path], dict[Path, tuple[int, int, int]]]:
            paths: list[Path] = []
            directories: dict[Path, tuple[int, int, int]] = {}
            pending = [root]
            while pending:
                directory = pending.pop().resolve()
                if not directory.is_relative_to(root):
                    raise WorkflowCheckpointException(
                        f"Checkpoint directory {directory} is outside storage root {root}"
                    )
                if directory in directories:
                    continue
                directories[directory] = _version(directory.stat())
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if entry.is_dir():
                            pending.append(Path(entry.path))
                        elif os.path.normcase(entry.name).endswith(".json"):
                            paths.append(Path(entry.path))
            return paths, directories

        def _make_duplicate_capturing_hook() -> tuple[
            Callable[[list[tuple[str, Any]]], dict[str, Any]],
            list[str],
        ]:
            """Return a JSON ``object_pairs_hook`` that records duplicate keys instead of raising.

            The hook is paired with a list that collects duplicate key names as they are
            encountered during parsing. The caller decides when to raise based on workflow
            ownership, so a foreign-workflow file with duplicate keys does not block
            recovery of healthy checkpoints for the requested workflow (per the documented
            policy that invalid metadata for a known different workflow is ignored).
            """
            duplicate_keys: list[str] = []

            def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, value in pairs:
                    if key in result:
                        duplicate_keys.append(key)
                    else:
                        result[key] = value
                return result

            return hook, duplicate_keys

        def _read_latest() -> WorkflowCheckpoint | None:
            root = self.storage_path.resolve()
            paths, directories = _checkpoint_paths(root)
            versions: dict[Path, tuple[int, int, int]] = {}
            latest: tuple[datetime, dict[str, Any]] | None = None
            for file_path in paths:
                try:
                    self._validate_file_path(str(file_path.relative_to(root))[:-5])
                    info = file_path.stat()
                    if not stat.S_ISREG(info.st_mode):
                        raise ValueError("checkpoint path is not a regular file")
                    version = _version(info)
                    hook, duplicate_keys = _make_duplicate_capturing_hook()
                    with open(file_path, encoding="utf-8") as f:
                        stored: dict[str, Any] = json.load(f, object_pairs_hook=hook)
                    versions[file_path] = version
                    owner: str | None = None
                    if (
                        isinstance(stored, dict)
                        and "workflow_name" not in duplicate_keys
                        and isinstance(stored.get("workflow_name"), str)
                    ):
                        owner = stored["workflow_name"]
                    if owner is None:
                        logger.warning(
                            "Quarantining unidentifiable checkpoint file %s while finding "
                            "the latest checkpoint for workflow '%s'",
                            file_path,
                            workflow_name,
                        )
                        continue
                    if owner != workflow_name:
                        continue
                    if "__pickled__" in stored or "__type__" in stored:
                        raise ValueError("Top-level pickle markers are not checkpoint metadata")
                    if duplicate_keys:
                        raise ValueError(f"Duplicate checkpoint JSON key: {duplicate_keys[0]}")
                    timestamp = datetime.fromisoformat(stored["timestamp"])
                    checkpoint_id = stored["checkpoint_id"]
                    if not isinstance(checkpoint_id, str):
                        raise ValueError("checkpoint_id must be a string")
                    if self._validate_file_path(checkpoint_id) != file_path.resolve():
                        raise ValueError("checkpoint_id does not match its checkpoint file")
                    if latest is None or timestamp > latest[0]:
                        latest = (timestamp, stored)
                except (json.JSONDecodeError, UnicodeDecodeError) as ex:
                    logger.warning(
                        "Quarantining checkpoint file %s that is not valid JSON while "
                        "finding the latest checkpoint for workflow '%s': %s",
                        file_path,
                        workflow_name,
                        ex,
                    )
                    continue
                except Exception as e:
                    raise WorkflowCheckpointException(
                        f"Failed to read checkpoint metadata for workflow {workflow_name} from {file_path}: {e}"
                    ) from e
            for file_path, version in versions.items():
                try:
                    current = _version(file_path.stat())
                except FileNotFoundError as ex:
                    raise _CheckpointScanInvalidated(
                        f"Checkpoint {file_path} was removed during the scan; retry get_latest"
                    ) from ex
                if current != version:
                    raise _CheckpointScanInvalidated(
                        f"Checkpoint {file_path} changed during the scan; retry get_latest"
                    )
            current_paths, current_directories = _checkpoint_paths(root)
            if (
                set(current_paths) != set(paths)
                or current_directories != directories
                or any(_version(path.stat()) != version for path, version in directories.items())
                or self.storage_path.resolve() != root
            ):
                raise _CheckpointScanInvalidated(
                    f"Checkpoint directory {self.storage_path} changed during the scan; retry get_latest"
                )
            return self._decode_checkpoint(latest[1]) if latest else None

        attempt = 0
        while True:
            attempt += 1
            try:
                checkpoint = await asyncio.to_thread(_read_latest)
            except _CheckpointScanInvalidated as exc:
                if attempt >= _MAX_GET_LATEST_ATTEMPTS:
                    raise WorkflowCheckpointException(
                        f"Checkpoint directory {self.storage_path} kept changing during "
                        f"get_latest for workflow '{workflow_name}' after "
                        f"{_MAX_GET_LATEST_ATTEMPTS} attempts; retry once concurrent "
                        "checkpoint writes settle"
                    ) from exc
                logger.debug(
                    "Checkpoint directory changed while finding the latest checkpoint for "
                    "workflow '%s' (attempt %d of %d); retrying",
                    workflow_name,
                    attempt,
                    _MAX_GET_LATEST_ATTEMPTS,
                )
                await asyncio.sleep(_GET_LATEST_RETRY_DELAY_SECONDS * attempt)
                continue
            except WorkflowCheckpointException:
                raise
            except Exception as e:
                raise WorkflowCheckpointException(
                    f"Failed to get latest checkpoint for workflow {workflow_name} from {self.storage_path}: {e}"
                ) from e
            if checkpoint is None:
                return None
            logger.debug(f"Latest checkpoint for workflow {workflow_name} is {checkpoint.checkpoint_id}")
            return checkpoint

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        """List checkpoint IDs for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoint IDs for.

        Returns:
            A list of checkpoint IDs for the specified workflow name.
            Only includes checkpoints that can be decoded under this storage's
            allowed types (aligned with :meth:`list_checkpoints`, #8181).
        """
        checkpoints = await self.list_checkpoints(workflow_name=workflow_name)
        return [checkpoint.checkpoint_id for checkpoint in checkpoints]
