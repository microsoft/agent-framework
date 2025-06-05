
from typing import Awaitable, Callable
from pydantic import BaseModel, field_validator

from ._event import Event
from ._event_handler import EventHandler, ClosureEventHandler
from ._input_source import UserInputSource


class RunConfig(BaseModel):
    """The configuraiton parameters for the current invocation of the agent."""

    event_handler: EventHandler
    """The event consumer for handling events emitted by the agent. Could be
    a callable that takes a message and returns an awaitable, or an instance of
    :class:`EventHandler` that handles events emitted by the agent."""

    user_input_source: UserInputSource
    """The user input source for requesting for user input during the agent run."""

    @field_validator("event_handler", mode="before")
    @classmethod
    def validate_event_handler(cls, value: EventHandler | Callable[[Event], Awaitable[None]]) -> EventHandler:
        """Validate the event handler to ensure it is an instance of EventHandler."""
        if isinstance(value, EventHandler):
            return value
        if callable(value):
            return ClosureEventHandler(value)
        raise ValueError("event_handler must be an instance of EventHandler or a callable.")

    ... # Other fields, could be extended to include more for application-specific needs.

