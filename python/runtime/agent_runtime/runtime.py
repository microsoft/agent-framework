"""In-process actor runtime implementation"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable

from .agent_actor import (
    Actor,
    ActorId,
    ActorMessage,
    ActorMessageType,
    ActorRequestMessage,
    ActorResponseMessage,
    ActorRuntimeContext,
    RequestStatus,
)


class ActorResponseHandle(ABC):
    """Handle for async actor responses (runtime infrastructure)"""

    @abstractmethod
    async def get_response(self) -> ActorResponseMessage:
        """Get the final response (blocking until complete)"""
        pass

    @abstractmethod
    async def watch_updates(self) -> AsyncIterator[ActorResponseMessage]:
        """Watch for streaming updates"""
        pass


class ActorStateStorage(ABC):
    """Interface for actor state persistence (runtime infrastructure)"""

    @abstractmethod
    async def read_state(self, actor_id: ActorId) -> dict[str, Any]:
        """Read all state for an actor"""
        pass

    @abstractmethod
    async def write_state(self, actor_id: ActorId, state: dict[str, Any]) -> bool:
        """Write state for an actor"""
        pass

    @abstractmethod
    async def delete_state(self, actor_id: ActorId) -> bool:
        """Delete all state for an actor"""
        pass


class ActorClient(ABC):
    """Interface for sending requests to actors (runtime infrastructure)"""

    @abstractmethod
    async def send_request(
        self, actor_id: ActorId, method: str, params: dict[str, Any] | None = None, message_id: str | None = None
    ) -> ActorResponseHandle:
        """Send a request to an actor"""
        pass


logger = logging.getLogger(__name__)


class InMemoryStateStorage(ActorStateStorage):
    """Simple in-memory state storage for development"""

    def __init__(self):
        self._storage: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def read_state(self, actor_id: ActorId) -> dict[str, Any]:
        async with self._lock:
            return self._storage.get(str(actor_id), {})

    async def write_state(self, actor_id: ActorId, state: dict[str, Any]) -> bool:
        async with self._lock:
            self._storage[str(actor_id)] = state
            return True

    async def delete_state(self, actor_id: ActorId) -> bool:
        async with self._lock:
            self._storage.pop(str(actor_id), None)
            return True


@dataclass(kwonly=True)
class RequestEntry:
    """Tracks a request, its response, and progress updates."""

    request: ActorRequestMessage
    _response_future: Future
    _progress_queue: asyncio.Queue

    def __init__(self, request: ActorRequestMessage):
        self.request = request
        self._response_future = Future()  # concurrent.futures.Future
        self._progress_queue = asyncio.Queue()  # of ActorResponseMessage (PENDING)

    def set_response(self, response: ActorResponseMessage) -> None:
        if not self._response_future.done():
            self._response_future.set_result(response)

    def get_response_future(self) -> Future:
        return self._response_future

    def add_progress_update(self, sequence_number: int, data: Any) -> None:
        # Wrap progress payload in a PENDING response message for streaming consumers
        progress = ActorResponseMessage(
            message_id=self.request.message_id,
            message_type=ActorMessageType.RESPONSE,
            sender_id=None,
            status=RequestStatus.PENDING,
            data={"sequence": sequence_number, "progress": data},
        )
        try:
            self._progress_queue.put_nowait(progress)
        except asyncio.QueueFull:  # pragma: no cover - unlikely with default
            pass


class InProcessResponseHandle(ActorResponseHandle):
    """Response handle for in-process actors"""

    def __init__(self, entry: RequestEntry):
        self._entry = entry

    async def get_response(self) -> ActorResponseMessage:
        future = self._entry.get_response_future()
        return await asyncio.wrap_future(future)

    async def watch_updates(self) -> AsyncIterator[ActorResponseMessage]:
        """Yield progress updates followed by the final response."""
        # Loop until final is done and queue drained
        while True:
            # If final response available and no pending progress, yield it and break
            if self._entry.get_response_future().done():
                # Drain any remaining progress first
                while not self._entry._progress_queue.empty():  # type: ignore[attr-defined]
                    yield await self._entry._progress_queue.get()  # type: ignore[attr-defined]
                yield await self.get_response()
                break
            try:
                progress = await asyncio.wait_for(self._entry._progress_queue.get(), timeout=0.05)  # type: ignore[attr-defined]
                yield progress
            except asyncio.TimeoutError:
                continue


class InProcessActorContext(ActorRuntimeContext):
    """Runtime context for an in-process actor"""

    def __init__(self, actor_id: ActorId, storage: ActorStateStorage, runtime: Any) -> None:
        self._actor_id = actor_id
        self._storage = storage
        self._runtime = runtime
        self._message_queue = asyncio.Queue()  # type: ignore[var-annotated]
        self._inbox = {}
        self._completed_order = []
        self._max_completed_retention = 128

    @property
    def actor_id(self) -> ActorId:
        return self._actor_id

    async def watch_messages(self) -> AsyncIterator[ActorMessage]:
        while True:
            try:
                msg = await self._message_queue.get()
                yield msg
                self._message_queue.task_done()
            except asyncio.CancelledError:
                break

    async def read_state(self, key: str) -> Any | None:
        state = await self._storage.read_state(self._actor_id)
        return state.get(key)

    async def write_state(self, key: str, value: Any) -> bool:
        # Read current state, update it, and write back
        state = await self._storage.read_state(self._actor_id)
        state[key] = value
        return await self._storage.write_state(self._actor_id, state)

    def enqueue_message(self, message: ActorMessage) -> None:
        self._message_queue.put_nowait(message)
        logger.debug(f"Message {message.message_id} enqueued for actor {self._actor_id}")

    def send_request(self, request: ActorRequestMessage) -> "InProcessResponseHandle":
        if request.message_id in self._inbox:
            return InProcessResponseHandle(self._inbox[request.message_id])
        entry = RequestEntry(request)
        self._inbox[request.message_id] = entry
        self.enqueue_message(request)
        return InProcessResponseHandle(entry)

    def complete_request(self, message_id: str, response: ActorResponseMessage) -> None:
        if message_id in self._inbox:
            entry = self._inbox[message_id]
            entry.set_response(response)
            if message_id not in self._completed_order:
                self._completed_order.append(message_id)
            if len(self._completed_order) > self._max_completed_retention:
                oldest = self._completed_order.pop(0)
                if oldest != message_id:
                    self._inbox.pop(oldest, None)
            logger.debug(f"Request {message_id} completed for actor {self._actor_id}")

    def on_progress_update(self, message_id: str, sequence_number: int, data: Any) -> None:
        if message_id in self._inbox:
            self._inbox[message_id].add_progress_update(sequence_number, data)


class InProcessActorRuntime:
    """In-process actor runtime"""

    def __init__(self, storage: ActorStateStorage | None = None):
        self._storage = storage or InMemoryStateStorage()
        self._actors = {}
        self._actor_tasks = {}
        self._actor_factories = {}
        self._running = False

    def register_actor_type(self, type_name: str, factory: Callable[[ActorRuntimeContext], Actor]) -> None:
        """Register a factory for creating actors of a given type"""
        self._actor_factories[type_name] = factory
        logger.info(f"Registered actor type: {type_name}")

    async def start(self) -> None:
        """Start the runtime"""
        self._running = True
        logger.info("Actor runtime started")

    async def stop(self) -> None:
        """Stop the runtime and all actors"""
        self._running = False

        # Cancel all actor tasks
        for task in self._actor_tasks.values():
            task.cancel()

        # Wait for tasks to complete
        if self._actor_tasks:
            await asyncio.gather(*self._actor_tasks.values(), return_exceptions=True)

        # Cleanup actors
        for actor_context in self._actors.values():
            # Allow actors to cleanup
            pass

        self._actors.clear()
        self._actor_tasks.clear()
        logger.info("Actor runtime stopped")

    def get_or_create_actor(self, actor_id: ActorId) -> InProcessActorContext:
        """Get an existing actor or create a new one"""
        if actor_id in self._actors:
            return self._actors[actor_id]

        # Check if we have a factory for this actor type
        if actor_id.type_name not in self._actor_factories:
            raise ValueError(f"No factory registered for actor type: {actor_id.type_name}")

        # Create the actor context
        context = InProcessActorContext(actor_id, self._storage, self)
        self._actors[actor_id] = context

        # Create the actor instance
        factory = self._actor_factories[actor_id.type_name]
        actor = factory(context)

        # Start the actor task
        task = asyncio.create_task(self._run_actor(actor, context))
        self._actor_tasks[actor_id] = task

        logger.info(f"Created actor: {actor_id}")
        return context

    async def _run_actor(self, actor: Actor, context: InProcessActorContext) -> None:
        """Run an actor instance"""
        try:
            logger.debug(f"Starting actor: {context.actor_id}")
            await actor.run(context)
        except asyncio.CancelledError:
            logger.debug(f"Actor cancelled: {context.actor_id}")
            raise
        except Exception as e:
            logger.error(f"Actor {context.actor_id} failed: {e}")
            raise
        finally:
            await actor.dispose()
            logger.debug(f"Actor disposed: {context.actor_id}")


class InProcessActorClient(ActorClient):
    """Client for sending requests to in-process actors"""

    def __init__(self, runtime: InProcessActorRuntime):
        self._runtime = runtime

    async def send_request(
        self, actor_id: ActorId, method: str, params: dict[str, Any] | None = None, message_id: str | None = None
    ) -> ActorResponseHandle:
        """Send a request to an actor"""
        if not message_id:
            message_id = str(uuid.uuid4())

        request = ActorRequestMessage(
            message_id=message_id, message_type=ActorMessageType.REQUEST, method=method, params=params
        )

        # Get or create the target actor
        context = self._runtime.get_or_create_actor(actor_id)

        # Send the request and get a response handle
        handle = context.send_request(request)

        logger.debug(f"Sent request {message_id} to actor {actor_id}")
        return handle
