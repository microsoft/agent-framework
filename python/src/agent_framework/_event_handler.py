from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from ._event import Event


class EventHandler(ABC):

    @abstractmethod
    async def handle(self, event: Event) -> None:
        """Handle an event emitted by the agent."""
        ...

class ClosureEventHandler(EventHandler):
    """A closure-based event handler that wraps a callable."""

    def __init__(self, handler: Callable[[Event], Awaitable[None]]):
        self._handler = handler

    async def handle(self, event: Event) -> None:
        await self._handler(event)