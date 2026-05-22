# Copyright (c) Microsoft. All rights reserved.

"""In-process implementation of :class:`DurableTaskRunner`.

This is the default runner the host wires in when the operator does not
supply one. It runs tasks via :func:`asyncio.create_task` with a bounded
retry loop following the supplied :class:`RetryPolicy`.

Two modes:

* **In-memory** (``state_dir=None``, default) — pending tasks live as
  ``asyncio.Task`` references in process memory. In-flight tasks are
  lost on process death. Cheap, zero dependencies, suitable for unit
  tests and for long-running deployments where "the process dies,
  queued pushes are lost" is an acceptable failure mode.
* **Disk-persistent** (``state_dir=<path>``) — pending tasks are
  pickled into a :mod:`diskcache`-backed sqlite store before the
  ``asyncio.Task`` is created. On the next startup the host calls
  :meth:`InProcessTaskRunner.resume` which re-schedules every
  surviving ``"pending"`` record with its persisted attempt count.
  Graceful shutdown cancellations leave records in ``"pending"`` so
  they replay on the next boot. Suitable for ``runtime_mode="long_running"``
  deployments that survive container moves / OOMs.

For ``runtime_mode="ephemeral"`` deployments (Foundry Hosted Agent,
Azure Functions, Lambda) plug in a durable adapter package
(``agent-framework-hosting-durabletask`` for the gRPC TaskHub backend,
a future Foundry adapter, …) — they all implement the same
:class:`DurableTaskRunner` Protocol.

See ``docs/specs/002-python-hosting-channels.md`` § "Durable task runner".
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import pickle  # noqa: S403 # nosec B403 - used only to validate user payloads round-trip
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, cast

from ._persistence import (
    acquire_state_dir_lock,
    load_diskcache,
    release_state_dir_lock,
)
from ._types import (
    DurableTaskPayloadMode,
    DurableTaskRunner,
    PushPayloadNotPicklable,
    RetryPolicy,
    TaskHandle,
    TaskStatus,
)

logger = logging.getLogger(__name__)


# Keys used inside the per-task on-disk record. Kept as module constants
# so the schema is documented once and refactors are mechanical.
_REC_HANDLER_NAME = "handler_name"
_REC_PAYLOAD = "payload"
_REC_RETRY_POLICY = "retry_policy"
_REC_ATTEMPTS = "attempts_completed"
_REC_STATUS = "status"
_REC_CREATED_AT = "created_at"
_REC_TERMINAL_AT = "terminal_at"
_REC_NAME = "name"

# Deque key inside the cache holding terminal task ids in insertion order.
# Used for FIFO eviction of terminal records once the bounded cap is hit.
_TERMINAL_ORDER_KEY = "__terminal_order__"


class _PersistedPayloadDict(dict[str, Any]):
    """Drop-in :class:`dict` that mirrors mutations back to disk.

    Used by :class:`InProcessTaskRunner` when ``state_dir`` is set so
    handler-side cursors (``echo_done``) survive process restarts. The
    handler interacts with this object exactly as it would with a plain
    dict; the override on :meth:`__setitem__` is the only difference.

    Held weakly by the runner so handlers that capture the dict in
    long-lived closures don't keep the runner alive past its natural
    lifetime.
    """

    # Type annotation for the persist callback; the actual attribute is
    # assigned via the __slots__-aware ``object.__setattr__`` dance
    # below so PyPy doesn't reject the assignment on a ``dict`` subclass.
    _persist_cb: Callable[[Mapping[str, Any]], None]

    __slots__ = ("_persist_cb",)

    def __init__(
        self,
        data: Mapping[str, Any],
        persist_cb: Callable[[Mapping[str, Any]], None],
    ) -> None:
        super().__init__(data)
        # Use object.__setattr__ to bypass the __slots__ checker on
        # dict subclasses (CPython is liberal here but PyPy is strict).
        object.__setattr__(self, "_persist_cb", persist_cb)

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        # Re-serialise after each mutation. The cache stores opaque
        # pickled values, so partial-field updates aren't possible —
        # we send the whole payload mapping every time. Mutations on
        # the runner's hot path are rare (just the ``echo_done``
        # cursor today) so this is fine.
        self._persist_cb(dict(self))


class InProcessTaskRunner(DurableTaskRunner):
    """In-memory or disk-persistent :class:`DurableTaskRunner`.

    Schedules each task as an :func:`asyncio.create_task` coroutine and
    retries on exception up to ``RetryPolicy.max_attempts`` times with
    exponential backoff. Terminal status (``succeeded`` / ``failed`` /
    ``cancelled``) is reported via :meth:`get`.

    Re-registration of the same handler name after :meth:`schedule` has
    been called is rejected to avoid silent re-orderings of in-flight
    work; the host registers all handlers at startup, before serving
    traffic.

    Keyword Args:
        default_retry_policy: Per-runner default :class:`RetryPolicy`;
            overridable per-task at :meth:`schedule` call sites.
        terminal_cache_size: Maximum number of terminal task records to
            retain. Older entries are FIFO-evicted so a long-running
            host can't accumulate unbounded status entries.
        shutdown_grace_seconds: Window :meth:`shutdown` waits for
            in-flight tasks to drain before cancelling stragglers.
        state_dir: When set, the runner persists pending and terminal
            task records under this directory (a :mod:`diskcache`
            sqlite store at ``<state_dir>/cache.db`` and a single-owner
            lock at ``<state_dir>/.lock``). Persisted pending records
            survive process restarts and are replayed by :meth:`resume`.
            When ``None`` (default) the runner is purely in-memory and
            in-flight tasks are lost on process death. Requires the
            optional ``diskcache`` dependency — install with
            ``pip install 'agent-framework-hosting[disk]'``.
    """

    # Declared at class level so the ``DurableTaskRunner`` Protocol's
    # ``payload_mode`` attribute resolves on instances without needing
    # to assign it in ``__init__``.
    payload_mode: DurableTaskPayloadMode = DurableTaskPayloadMode.OBJECT

    def __init__(
        self,
        *,
        default_retry_policy: RetryPolicy | None = None,
        terminal_cache_size: int = 1024,
        shutdown_grace_seconds: float = 5.0,
        state_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        self._handlers: dict[str, Callable[[Mapping[str, Any]], Awaitable[None]]] = {}
        self._default_retry_policy = default_retry_policy or RetryPolicy()
        self._terminal_cache_size = terminal_cache_size
        # How long ``shutdown()`` waits for in-flight tasks to finish on
        # their own before cancelling them. Channels may legitimately
        # schedule a final push during their own shutdown callback
        # (goodbye message, telemetry flush), so the runner gives them
        # this window to complete before cancellation kicks in.
        self._shutdown_grace_seconds = shutdown_grace_seconds

        # Operational state. ``_pending`` holds asyncio tasks that are
        # scheduled or running. ``_terminal`` is an in-memory mirror of
        # the most recent terminal statuses (kept in-memory regardless of
        # ``state_dir`` so ``get`` is fast and works before/without the
        # cache being opened).
        self._pending: dict[str, asyncio.Task[None]] = {}
        self._terminal: dict[str, TaskStatus] = {}
        self._terminal_order: list[str] = []

        # Set to True on the first ``schedule``/``resume`` call so subsequent
        # ``register`` calls fail loudly rather than silently swapping a
        # handler out from under in-flight work.
        self._started = False

        # Set to True when ``shutdown()`` starts so the retry loop's
        # ``CancelledError`` handler distinguishes "the runner is going
        # down, leave my record in 'pending' for resume()" from "this
        # task was explicitly cancelled, mark it 'cancelled'".
        self._shutting_down = False

        # Disk persistence — opt-in via ``state_dir``. ``None`` keeps
        # the runner pure-memory (the default behaviour).
        self._state_dir: Path | None = Path(os.fspath(state_dir)) if state_dir is not None else None
        self._cache: Any = None
        self._terminal_deque: Any = None
        self._lock_handle: Any = None
        if self._state_dir is not None:
            self._open_cache()

    # ------------------------------------------------------------------ #
    # Cache lifecycle
    # ------------------------------------------------------------------ #

    def _open_cache(self) -> None:
        """Open the disk cache and acquire the single-owner lock.

        Called from ``__init__`` when ``state_dir`` is set. Splitting it
        out keeps the constructor body readable and gives tests a clean
        seam for monkeypatching.
        """
        if self._state_dir is None:  # pragma: no cover - guarded by caller
            raise RuntimeError("_open_cache called without state_dir")
        diskcache = load_diskcache()
        # Acquire the directory lock *before* opening the cache so two
        # runners pointed at the same dir don't both try to initialise
        # sqlite. The lock handle stays open for the runner's lifetime.
        self._lock_handle = acquire_state_dir_lock(self._state_dir)
        try:
            self._cache = diskcache.Cache(str(self._state_dir))
            # Re-hydrate the in-memory terminal mirror so ``get`` works
            # for task ids that completed in a prior process. Doing this
            # here (rather than lazily) means the mirror is consistent
            # the moment construction returns.
            order: Any = self._cache.get(_TERMINAL_ORDER_KEY, default=[])
            if not isinstance(order, list):
                # Defensive: a corrupted ordering list shouldn't take
                # the host down. Reset and continue — at worst we lose
                # ordering for FIFO eviction, not correctness.
                logger.warning(
                    "InProcessTaskRunner: terminal-order entry in %s is not a list; resetting", self._state_dir
                )
                order = []
                self._cache.set(_TERMINAL_ORDER_KEY, order)
            self._terminal_order = [str(x) for x in cast(list[Any], order)]
            for task_id in self._terminal_order:
                rec_obj: Any
                try:
                    rec_obj = self._cache.get(task_id)
                except Exception:  # pragma: no cover - exercised via corrupt-entry test
                    rec_obj = None
                if not isinstance(rec_obj, dict):
                    continue
                rec = cast(dict[str, Any], rec_obj)
                status = rec.get(_REC_STATUS)
                if status in {"succeeded", "failed", "cancelled"}:
                    self._terminal[task_id] = status
        except Exception:
            release_state_dir_lock(self._lock_handle)
            self._lock_handle = None
            raise

    # ------------------------------------------------------------------ #
    # DurableTaskRunner Protocol
    # ------------------------------------------------------------------ #

    def register(
        self,
        name: str,
        handler: Callable[[Mapping[str, Any]], Awaitable[None]],
    ) -> None:
        if self._started:
            raise RuntimeError(
                f"InProcessTaskRunner.register({name!r}) called after the "
                "runner started scheduling tasks — register all handlers at "
                "host startup, before serving traffic, to avoid silently "
                "reordering in-flight work."
            )
        if name in self._handlers:
            logger.warning("InProcessTaskRunner: replacing handler registered under %r", name)
        self._handlers[name] = handler

    async def schedule(
        self,
        name: str,
        payload: Mapping[str, Any],
        *,
        retry_policy: RetryPolicy | None = None,
    ) -> TaskHandle:
        if name not in self._handlers:
            raise KeyError(
                f"InProcessTaskRunner.schedule({name!r}): no handler "
                "registered under this name. Call register(name, handler) "
                "at host startup before scheduling."
            )

        self._started = True
        policy = retry_policy or self._default_retry_policy
        task_id = uuid.uuid4().hex
        handle = TaskHandle(task_id=task_id, name=name)

        # Persist the record (when state_dir is set) BEFORE we spawn the
        # asyncio task — if the persistence write fails we surface it as
        # a synchronous error from ``schedule`` rather than silently
        # downgrading to in-memory.
        if self._cache is not None:
            record = self._build_record(name, dict(payload), policy)
            self._validate_picklable(record)
            self._cache.set(task_id, record)

        # When persisted, wrap the payload so handler-side mutations
        # (e.g. ``payload["echo_done"] = True``) flow back to disk.
        runtime_payload: Mapping[str, Any]
        if self._cache is not None:
            captured_task_id = task_id

            def _persist_cb(new_payload: Mapping[str, Any]) -> None:
                self._update_record_payload(captured_task_id, new_payload)

            runtime_payload = _PersistedPayloadDict(payload, _persist_cb)
        else:
            runtime_payload = payload

        handler = self._handlers[name]
        task = asyncio.create_task(
            self._run_with_retry(handle, handler, runtime_payload, policy),
            name=f"hosting.task[{name}]:{task_id}",
        )
        self._pending[task_id] = task

        def _on_done(_t: asyncio.Task[None], tid: str = task_id) -> None:
            self._pending.pop(tid, None)

        task.add_done_callback(_on_done)
        return handle

    async def get(self, handle: TaskHandle) -> TaskStatus | None:
        if handle.task_id in self._pending:
            task = self._pending[handle.task_id]
            if task.cancelled():
                return "cancelled"
            return "running"
        # In-memory terminal mirror covers both pure-memory and
        # disk-persistent runs (we re-hydrate on cache open).
        if handle.task_id in self._terminal:
            return self._terminal[handle.task_id]
        # Disk fallback for very-aged task ids that left the in-memory
        # mirror but still have a record on disk (extremely unlikely
        # given that we re-hydrate all terminals at open, but defensive).
        if self._cache is not None:
            rec_obj: Any = self._cache.get(handle.task_id)
            if isinstance(rec_obj, dict):
                rec = cast(dict[str, Any], rec_obj)
                status = rec.get(_REC_STATUS)
                # Records on disk only live in one of four states:
                # ``pending`` (queued or in-flight — resume picks these
                # up) or one of the terminals. There is no transient
                # ``running`` status; the in-flight asyncio task is
                # observable via ``_pending`` only inside its own
                # process.
                if status in {"succeeded", "failed", "cancelled", "pending"}:
                    return cast(TaskStatus, status)
        return None

    # ------------------------------------------------------------------ #
    # Resume — replay persisted pending records on startup
    # ------------------------------------------------------------------ #

    async def resume(self) -> int:
        """Re-schedule pending tasks persisted by a previous process.

        Walks the cache for records in ``"pending"`` status, looks up
        their handler in :attr:`_handlers`, and re-creates an
        :class:`asyncio.Task` for each — preserving the persisted
        attempt count so retry budgets resume mid-way through their
        backoff schedule.

        Records whose handler is no longer registered are marked
        ``"failed"`` with a clear reason in the log; they will not be
        retried again. Records that fail to deserialise (corrupted
        sqlite row, schema drift, …) are quarantined: their entry is
        removed from the cache and the task id is logged. Both classes
        of error are non-fatal — the host should boot even when a
        small number of legacy records can't be replayed.

        Returns the number of records successfully re-scheduled.

        Called automatically from :class:`AgentFrameworkHost`'s lifespan
        startup hook when the runner is host-owned. Callers driving the
        runner directly (tests, bespoke ASGI setups) MUST call this
        once after registering handlers and before serving traffic.
        """
        if self._cache is None:
            return 0

        # Mark started so subsequent register() calls fail loudly — we
        # don't want handler swaps after replay begins.
        self._started = True

        replayed = 0
        # iterkeys returns a live view; we copy to a list because we may
        # delete entries inside the loop (quarantine / drop-on-missing-handler).
        task_ids: list[str] = [str(k) for k in self._cache.iterkeys() if k != _TERMINAL_ORDER_KEY]
        for task_id in task_ids:
            rec_obj: Any
            try:
                rec_obj = self._cache.get(task_id)
            except Exception:
                logger.exception("InProcessTaskRunner.resume: failed to read record %s; quarantining", task_id)
                with contextlib.suppress(KeyError):
                    del self._cache[task_id]
                continue
            if not isinstance(rec_obj, dict) or _REC_STATUS not in rec_obj:
                logger.warning("InProcessTaskRunner.resume: record %s is not a task dict; quarantining", task_id)
                with contextlib.suppress(KeyError):
                    del self._cache[task_id]
                continue
            rec = cast(dict[str, Any], rec_obj)
            status = rec[_REC_STATUS]
            if status != "pending":
                continue

            handler_name = rec.get(_REC_HANDLER_NAME)
            if not isinstance(handler_name, str) or handler_name not in self._handlers:
                logger.warning(
                    "InProcessTaskRunner.resume: no handler registered for record %s (handler=%r); marking failed",
                    task_id,
                    handler_name,
                )
                self._mark_terminal(task_id, "failed")
                continue
            handler = self._handlers[handler_name]

            policy_value = rec.get(_REC_RETRY_POLICY) or self._default_retry_policy
            if not isinstance(policy_value, RetryPolicy):
                # Legacy / corrupt entry — fall back to the default rather
                # than failing the whole resume.
                policy_value = self._default_retry_policy
            policy: RetryPolicy = policy_value
            payload_value: Any = rec.get(_REC_PAYLOAD) or {}
            payload: dict[str, Any]
            if isinstance(payload_value, dict):
                payload = cast(dict[str, Any], payload_value)
            elif hasattr(payload_value, "keys"):
                payload = dict(cast(Mapping[str, Any], payload_value))
            else:
                payload = {}

            name_value = rec.get(_REC_NAME, handler_name)
            handle = TaskHandle(task_id=task_id, name=str(name_value))
            attempts_value = rec.get(_REC_ATTEMPTS, 0)
            attempts_completed = int(attempts_value or 0)

            def _make_resume_persist_cb(tid: str) -> Callable[[Mapping[str, Any]], None]:
                def _cb(new_payload: Mapping[str, Any]) -> None:
                    self._update_record_payload(tid, new_payload)

                return _cb

            runtime_payload = _PersistedPayloadDict(payload, _make_resume_persist_cb(task_id))

            task = asyncio.create_task(
                self._run_with_retry(handle, handler, runtime_payload, policy, _resume_from_attempt=attempts_completed),
                name=f"hosting.task[{handle.name}]:{task_id}(resumed)",
            )
            self._pending[task_id] = task

            def _on_done(_t: asyncio.Task[None], tid: str = task_id) -> None:
                self._pending.pop(tid, None)

            task.add_done_callback(_on_done)
            replayed += 1

        if replayed:
            logger.info(
                "InProcessTaskRunner.resume: re-scheduled %d pending task(s) from %s", replayed, self._state_dir
            )
        return replayed

    # ------------------------------------------------------------------ #
    # Lifecycle helper (the host calls this from ``on_shutdown``)
    # ------------------------------------------------------------------ #

    async def shutdown(self, *, timeout: float | None = None) -> None:
        """Wait briefly for pending tasks to drain, then cancel anything still running.

        Called by the host on ``on_shutdown`` so a graceful shutdown does
        not orphan in-flight push retries. Channels may legitimately
        schedule a final push from their own shutdown callback (e.g. a
        goodbye message); the runner therefore *waits* up to
        ``timeout`` seconds (default: the runner's
        ``shutdown_grace_seconds`` configured at construction) for the
        in-flight set to finish on its own before cancelling stragglers.
        Tasks that don't honour cancellation within the same window are
        abandoned — the runner makes no synchronous durability claim,
        so cleanup is best-effort.

        When ``state_dir`` is set, tasks that didn't drain are left in
        ``"pending"`` status on disk so the next process replays them
        via :meth:`resume`. The disk cache is closed and the
        single-owner lock is released regardless of drain outcome.
        """
        self._shutting_down = True
        try:
            if self._pending:
                grace = timeout if timeout is not None else self._shutdown_grace_seconds
                tasks = list(self._pending.values())
                # Phase 1 — wait for natural completion within the grace window.
                if grace > 0:
                    await asyncio.wait(tasks, timeout=grace)
                # Phase 2 — cancel anything still pending, then wait briefly for
                # cancellation to propagate.
                still_pending = [t for t in tasks if not t.done()]
                if still_pending:
                    logger.info(
                        "InProcessTaskRunner.shutdown: %d task(s) still running after %.2fs grace; cancelling",
                        len(still_pending),
                        grace,
                    )
                    for task in still_pending:
                        task.cancel()
                    cancellation_window = max(grace, 1.0)
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*still_pending, return_exceptions=True),
                            timeout=cancellation_window,
                        )
                    except (TimeoutError, asyncio.TimeoutError):
                        logger.warning(
                            "InProcessTaskRunner.shutdown: %d task(s) did not exit within %.2fs "
                            "of cancellation; abandoning",
                            sum(not t.done() for t in still_pending),
                            cancellation_window,
                        )
        finally:
            # Release disk resources after the in-flight set has been
            # given a chance to drain — tasks that mutate the payload
            # mid-shutdown will fail to persist after this point, which
            # is the correct behaviour (the next process will replay
            # from whatever the last fully-committed state was).
            if self._cache is not None:
                try:
                    self._cache.close()
                except Exception:  # pragma: no cover - close errors aren't actionable
                    logger.exception("InProcessTaskRunner.shutdown: failed to close cache cleanly")
                self._cache = None
            if self._lock_handle is not None:
                release_state_dir_lock(self._lock_handle)
                self._lock_handle = None

    # ------------------------------------------------------------------ #
    # Internals — retry loop
    # ------------------------------------------------------------------ #

    async def _run_with_retry(
        self,
        handle: TaskHandle,
        handler: Callable[[Mapping[str, Any]], Awaitable[None]],
        payload: Mapping[str, Any],
        policy: RetryPolicy,
        *,
        _resume_from_attempt: int = 0,
    ) -> None:
        delay = policy.initial_backoff_seconds
        attempt = _resume_from_attempt
        try:
            while True:
                attempt += 1
                # Persist the attempt counter BEFORE we invoke the
                # handler so a crash mid-handler doesn't lose the fact
                # that we tried — replay sees the bumped counter and
                # respects the original retry budget. Trade-off: a
                # crash before the external call is made still consumes
                # one attempt (at-most-once semantics around the bump);
                # we document this as best-effort across crashes.
                self._update_record_attempts(handle.task_id, attempt)

                try:
                    await handler(payload)
                except asyncio.CancelledError:
                    # On a graceful shutdown of a disk-persistent runner
                    # we deliberately *don't* mark the record terminal —
                    # ``resume()`` will pick it up on the next boot and
                    # replay it with the persisted attempt counter. For
                    # in-memory runners (no cache) there's nothing to
                    # resume from, so we still mark ``cancelled`` so
                    # callers holding the handle can observe the
                    # outcome.
                    if not (self._shutting_down and self._cache is not None):
                        self._mark_terminal(handle.task_id, "cancelled")
                    raise
                except Exception as exc:
                    if attempt >= policy.max_attempts:
                        logger.exception(
                            "InProcessTaskRunner: task %s (%s) failed after %d attempts",
                            handle.name,
                            handle.task_id,
                            attempt,
                        )
                        self._mark_terminal(handle.task_id, "failed")
                        return
                    logger.warning(
                        "InProcessTaskRunner: task %s (%s) attempt %d/%d failed (%s); retrying in %.2fs",
                        handle.name,
                        handle.task_id,
                        attempt,
                        policy.max_attempts,
                        exc,
                        delay,
                    )
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        if not (self._shutting_down and self._cache is not None):
                            self._mark_terminal(handle.task_id, "cancelled")
                        raise
                    delay = min(delay * policy.backoff_multiplier, policy.max_backoff_seconds)
                else:
                    self._mark_terminal(handle.task_id, "succeeded")
                    return
        except asyncio.CancelledError:
            # Propagate so the outer ``asyncio.Task`` records cancellation
            # in its own state for any observer that holds the raw task.
            return

    # ------------------------------------------------------------------ #
    # Internals — record / disk helpers
    # ------------------------------------------------------------------ #

    def _build_record(
        self,
        name: str,
        payload: Mapping[str, Any],
        policy: RetryPolicy,
    ) -> dict[str, Any]:
        """Construct the on-disk record dict for a freshly-scheduled task."""
        return {
            _REC_HANDLER_NAME: name,
            _REC_NAME: name,
            _REC_PAYLOAD: dict(payload),
            _REC_RETRY_POLICY: policy,
            _REC_ATTEMPTS: 0,
            _REC_STATUS: "pending",
            _REC_CREATED_AT: time.time(),
        }

    def _validate_picklable(self, record: Mapping[str, Any]) -> None:
        """Pickle-probe a record at schedule time so misconfig is loud.

        We only do this when the cache is open (i.e. persistence is on).
        The probe runs ``pickle.dumps`` on the record and raises a
        framework-typed :class:`PushPayloadNotPicklable` if it fails.
        Loud failure here is better than silent data loss after the
        next restart.
        """
        try:
            pickle.dumps(record)  # nosec B301 - dumps only, no untrusted load
        except Exception as exc:
            raise PushPayloadNotPicklable(
                "InProcessTaskRunner: scheduled task payload is not picklable; "
                "disk persistence (state_dir) requires payloads to round-trip "
                "through pickle. Common causes: a user-supplied response that "
                "embeds a live network client, asyncio.Lock, or generator. "
                f"Underlying pickle error: {exc!r}"
            ) from exc

    def _update_record_attempts(self, task_id: str, attempt: int) -> None:
        """Bump the attempt counter on the persisted record (if any).

        Status stays ``"pending"`` while the task is in-flight — there
        is no transient ``"running"`` status. This keeps the resume
        contract simple: anything ``"pending"`` on disk is a candidate
        for replay, whether it was never picked up or crashed mid-attempt.
        """
        if self._cache is None:
            return
        rec = self._cache.get(task_id)
        if not isinstance(rec, dict):
            # Record was evicted / quarantined since schedule; nothing
            # to persist. The asyncio task continues — it just won't
            # be resumable on next boot.
            return
        rec[_REC_ATTEMPTS] = attempt
        try:
            self._cache.set(task_id, rec)
        except Exception:  # pragma: no cover - cache write failures aren't actionable
            logger.exception("InProcessTaskRunner: failed to persist attempt counter for %s", task_id)

    def _update_record_payload(self, task_id: str, new_payload: Mapping[str, Any]) -> None:
        """Persist a handler-side payload mutation back to disk.

        Called from :class:`_PersistedPayloadDict.__setitem__`. The whole
        payload mapping is re-written (the cache stores opaque pickled
        values, so partial-field updates aren't possible). Handler-side
        mutations on the runner's hot path are rare (today: only the
        ``echo_done`` cursor) so the extra write is acceptable.
        """
        if self._cache is None:
            return
        rec = self._cache.get(task_id)
        if not isinstance(rec, dict):
            return
        rec[_REC_PAYLOAD] = dict(new_payload)
        try:
            self._cache.set(task_id, rec)
        except Exception:  # pragma: no cover - cache write failures aren't actionable
            logger.exception("InProcessTaskRunner: failed to persist payload mutation for %s", task_id)

    def _mark_terminal(self, task_id: str, status: TaskStatus) -> None:
        """Move a task to a terminal status, updating both memory and disk.

        Records are first updated on disk (so a crash between the disk
        write and the in-memory write doesn't lose the terminal status),
        then mirrored to the in-memory cache, then FIFO-bounded.
        """
        # Disk side first.
        if self._cache is not None:
            rec = self._cache.get(task_id)
            if isinstance(rec, dict):
                rec[_REC_STATUS] = status
                rec[_REC_TERMINAL_AT] = time.time()
                # Truncate heavy fields (payload, retry_policy) — once
                # the task is terminal we never need them again, and
                # keeping them around bloats disk on long-lived hosts.
                rec[_REC_PAYLOAD] = None
                rec[_REC_RETRY_POLICY] = None
                try:
                    self._cache.set(task_id, rec)
                except Exception:  # pragma: no cover
                    logger.exception("InProcessTaskRunner: failed to persist terminal status for %s", task_id)

        # In-memory side.
        if task_id not in self._terminal:
            self._terminal_order.append(task_id)
        self._terminal[task_id] = status

        # FIFO-evict from BOTH layers once we exceed the cap.
        while len(self._terminal_order) > self._terminal_cache_size:
            evicted = self._terminal_order.pop(0)
            self._terminal.pop(evicted, None)
            if self._cache is not None:
                try:
                    del self._cache[evicted]
                except KeyError:
                    pass
                except Exception:  # pragma: no cover
                    logger.exception("InProcessTaskRunner: failed to evict %s from disk cache", evicted)

        # Persist the new ordering list so a restart sees the same FIFO
        # ordering for further eviction decisions.
        if self._cache is not None:
            try:
                self._cache.set(_TERMINAL_ORDER_KEY, list(self._terminal_order))
            except Exception:  # pragma: no cover
                logger.exception("InProcessTaskRunner: failed to persist terminal-order list")


__all__ = ["InProcessTaskRunner"]
