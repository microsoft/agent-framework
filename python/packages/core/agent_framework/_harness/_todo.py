# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, cast

from .._feature_stage import ExperimentalFeature, experimental
from .._serialization import SerializationMixin
from .._sessions import AgentSession, ContextProvider, SessionContext
from .._tools import tool
from .._types import Message

DEFAULT_TODO_SOURCE_ID = "todo"
DEFAULT_TODO_INSTRUCTIONS = (
    "## Todo Items\n\n"
    "You have access to a todo list for tracking work items.\n"
    "While planning, make sure that you break down complex tasks into manageable todo items "
    "and add them to the list.\n"
    "Ask questions from the user where clarification is needed to create effective todos.\n"
    "If the user provides feedback on your plan, adjust your todos accordingly by adding new items "
    "or removing irrelevant ones.\n"
    "During execution, use the todo list to keep track of what needs to be done, "
    "mark items as complete when finished, and remove any items that are no longer needed.\n"
    "When a user changes the topic or changes their mind, ensure that you update the todo list accordingly "
    "by removing irrelevant items or adding new ones as needed.\n\n"
    "Use these tools to manage your tasks:\n"
    "- Use add_todos to break down complex work into trackable items (supports adding one or many at once).\n"
    "- Use complete_todos to mark items as done when finished (supports one or many at once).\n"
    "- Use get_remaining_todos to check what work is still pending.\n"
    "- Use get_all_todos to review the full list including completed items.\n"
    "- Use remove_todos to remove items that are no longer needed (supports one or many at once)."
)


@experimental(feature_id=ExperimentalFeature.HARNESS)
class TodoItem(SerializationMixin):
    """Represent one todo item tracked for the current session."""

    id: int
    title: str
    description: str | None
    is_complete: bool
    __slots__ = ("description", "id", "is_complete", "title")

    def __init__(self, id: int, title: str, description: str | None = None, is_complete: bool = False) -> None:
        """Initialize one todo item."""
        self.id = id
        self.title = title
        self.description = description
        self.is_complete = is_complete

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Serialize the todo item for persistence."""
        del exclude
        payload = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "is_complete": self.is_complete,
        }
        return {key: value for key, value in payload.items() if value is not None or not exclude_none}

    @classmethod
    def from_dict(
        cls, raw_item: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> TodoItem:
        """Parse one todo item loaded from storage."""
        del dependencies
        item_id = raw_item.get("id")
        title = raw_item.get("title")
        description = raw_item.get("description")
        is_complete = raw_item.get("is_complete", False)
        if not isinstance(item_id, int):
            raise ValueError("Todo item id must be an integer.")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Todo item title must be a non-empty string.")
        if description is not None and not isinstance(description, str):
            raise ValueError("Todo item description must be a string or null.")
        if not isinstance(is_complete, bool):
            raise ValueError("Todo item is_complete must be a boolean.")
        return cls(id=item_id, title=title, description=description, is_complete=is_complete)

    def __eq__(self, other: object) -> bool:
        """Return whether two todo items have the same values."""
        return isinstance(other, TodoItem) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        """Return a helpful debug representation."""
        return (
            "TodoItem("
            f"id={self.id!r}, title={self.title!r}, description={self.description!r}, is_complete={self.is_complete!r})"
        )


@experimental(feature_id=ExperimentalFeature.HARNESS)
class TodoInput(SerializationMixin):
    """Describe one todo item to create."""

    title: str
    description: str | None
    __slots__ = ("description", "title")

    def __init__(self, title: str, description: str | None = None) -> None:
        """Initialize one todo input."""
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("Todo input title must be a non-empty string.")
        if description is not None and not isinstance(description, str):
            raise ValueError("Todo input description must be a string or null.")
        self.title = normalized_title
        self.description = description

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Serialize the todo input."""
        del exclude
        payload = {"title": self.title, "description": self.description}
        return {key: value for key, value in payload.items() if value is not None or not exclude_none}

    @classmethod
    def from_dict(
        cls, raw_todo: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> TodoInput:
        """Parse one todo input loaded from tool arguments."""
        del dependencies
        title = raw_todo.get("title")
        description = raw_todo.get("description")
        if not isinstance(title, str):
            raise ValueError("Todo input title must be a string.")
        return cls(title=title, description=description)


def _coerce_todo_input(todo: TodoInput | dict[str, Any] | Any) -> TodoInput:
    """Normalize tool-provided todo input into a TodoInput model."""
    if isinstance(todo, TodoInput):
        return todo
    if isinstance(todo, MutableMapping):
        return TodoInput.from_dict(cast(MutableMapping[str, Any], todo))
    raise ValueError("Todo input must be a TodoInput instance or JSON object.")


class TodoStore(ABC):
    """Abstract backing store for session todo items."""

    @abstractmethod
    def load_state(self, session: AgentSession, *, source_id: str) -> tuple[list[TodoItem], int]:
        """Load persisted todo items and the next available ID."""

    @abstractmethod
    def save_state(self, session: AgentSession, items: list[TodoItem], *, next_id: int, source_id: str) -> None:
        """Persist todo items and the next available ID."""

    def load_items(self, session: AgentSession, *, source_id: str) -> list[TodoItem]:
        """Load todo items for one session."""
        items, _ = self.load_state(session, source_id=source_id)
        return items


@experimental(feature_id=ExperimentalFeature.HARNESS)
class TodoSessionStore(TodoStore):
    """Store todo state inside ``AgentSession.state``."""

    def load_state(self, session: AgentSession, *, source_id: str) -> tuple[list[TodoItem], int]:
        """Load todo state from session state."""
        provider_state_value = session.state.get(source_id)
        provider_state = cast(dict[str, Any], provider_state_value) if isinstance(provider_state_value, dict) else {}
        if not isinstance(provider_state_value, dict):
            session.state[source_id] = provider_state

        raw_items = provider_state.get("items")
        items_payload: list[Any] = cast(Any, raw_items) if isinstance(raw_items, list) else []
        if not isinstance(raw_items, list):
            provider_state["items"] = items_payload

        raw_next_id = provider_state.get("next_id")
        next_id = raw_next_id if isinstance(raw_next_id, int) else 1
        if not isinstance(raw_next_id, int):
            provider_state["next_id"] = next_id

        return [TodoItem.from_dict(cast(dict[str, Any], item)) for item in items_payload], next_id

    def save_state(self, session: AgentSession, items: list[TodoItem], *, next_id: int, source_id: str) -> None:
        """Persist todo state back into session state."""
        provider_state_value = session.state.get(source_id)
        provider_state = cast(dict[str, Any], provider_state_value) if isinstance(provider_state_value, dict) else {}
        if not isinstance(provider_state_value, dict):
            session.state[source_id] = provider_state
        provider_state["items"] = [item.to_dict(exclude_none=False) for item in items]
        provider_state["next_id"] = next_id


@experimental(feature_id=ExperimentalFeature.HARNESS)
class TodoFileStore(TodoStore):
    """Store todo state in one JSON file per session."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        kind: str = "todos",
        owner_prefix: str = "",
        owner_state_key: str | None = None,
        state_filename: str = "todos.json",
    ) -> None:
        """Initialize the file-backed todo store.

        Args:
            base_path: Root storage directory.

        Keyword Args:
            kind: Storage bucket name under each owner directory.
            owner_prefix: Optional prefix applied to the resolved owner ID.
            owner_state_key: Session-state key holding the logical owner ID.
            state_filename: File name used for the persisted todo state.
        """
        self.base_path = Path(base_path)
        self.kind = kind
        self.owner_prefix = owner_prefix
        self.owner_state_key = owner_state_key
        self.state_filename = state_filename

    def _get_state_path(self, session: AgentSession) -> Path:
        """Return the JSON file path for one session."""
        session_directory = self.base_path
        if self.owner_state_key is not None:
            owner_value = session.state.get(self.owner_state_key)
            if owner_value is None:
                raise RuntimeError(
                    f"TodoFileStore requires session.state[{self.owner_state_key!r}] to be set for file-backed storage."
                )
            session_directory = session_directory / f"{self.owner_prefix}{owner_value}" / self.kind
        session_directory = session_directory / session.session_id
        session_directory.mkdir(parents=True, exist_ok=True)
        return session_directory / self.state_filename

    def load_state(self, session: AgentSession, *, source_id: str) -> tuple[list[TodoItem], int]:
        """Load todo state from disk."""
        del source_id
        state_path = self._get_state_path(session)
        if not state_path.exists():
            return [], 1
        payload = cast(dict[str, Any], json.loads(state_path.read_text(encoding="utf-8")))
        if not isinstance(payload, dict):
            raise ValueError(f"Todo file {state_path} must contain a JSON object.")
        raw_items = payload.get("items", [])
        raw_next_id = payload.get("next_id", 1)
        if not isinstance(raw_items, list):
            raise ValueError(f"Todo file {state_path} has a non-list 'items' field.")
        if not isinstance(raw_next_id, int):
            raise ValueError(f"Todo file {state_path} has a non-integer 'next_id' field.")
        items_payload: list[Any] = cast(Any, raw_items)
        return [TodoItem.from_dict(cast(dict[str, Any], item)) for item in items_payload], raw_next_id

    def save_state(self, session: AgentSession, items: list[TodoItem], *, next_id: int, source_id: str) -> None:
        """Persist todo state to disk."""
        del source_id
        state_path = self._get_state_path(session)
        state_path.write_text(
            json.dumps({"items": [item.to_dict(exclude_none=False) for item in items], "next_id": next_id}) + "\n",
            encoding="utf-8",
        )


@experimental(feature_id=ExperimentalFeature.HARNESS)
class TodoListContextProvider(ContextProvider):
    """Provide todo management tools and instructions to an agent.

    The ``TodoListContextProvider`` enables agents to create, complete, remove, and query todo items as part of
    their planning and execution workflow. Todo state is stored in the configured ``TodoStore`` and persists across
    agent invocations within the same session. By default, state is stored in ``AgentSession.state`` with
    ``TodoSessionStore``; callers can provide ``TodoFileStore`` or another store implementation for file-backed or
    custom persistence.

    This provider exposes the following tools to the agent:
    - ``add_todos``: Add one or more todo items, each with a title and optional description.
    - ``complete_todos``: Mark one or more todo items as complete by their IDs.
    - ``remove_todos``: Remove one or more todo items by their IDs.
    - ``get_remaining_todos``: Retrieve only incomplete todo items.
    - ``get_all_todos``: Retrieve all todo items, complete and incomplete.
    """

    def __init__(
        self,
        source_id: str = DEFAULT_TODO_SOURCE_ID,
        *,
        instructions: str | None = None,
        store: TodoStore | None = None,
    ) -> None:
        """Initialize the todo provider.

        Args:
            source_id: Unique source ID for the provider.

        Keyword Args:
            instructions: Optional instruction override.
            store: Optional todo store override.
        """
        super().__init__(source_id)
        self.instructions = instructions or DEFAULT_TODO_INSTRUCTIONS
        self.store = store or TodoSessionStore()

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject todo tools and instructions before the model runs."""
        del agent, state

        @tool(name="add_todos", approval_mode="never_require")
        def add_todos(todos: list[dict[str, Any]]) -> str:
            """Add one or more todo items for the current session."""
            if not todos:
                raise ValueError("todos must contain at least one item.")

            existing_items, next_id = self.store.load_state(session, source_id=self.source_id)
            created_items: list[TodoItem] = []
            for raw_todo in todos:
                todo = _coerce_todo_input(raw_todo)
                created_item = TodoItem(
                    id=next_id,
                    title=todo.title,
                    description=todo.description.strip() if todo.description is not None else None,
                )
                existing_items.append(created_item)
                created_items.append(created_item)
                next_id += 1

            self.store.save_state(session, existing_items, next_id=next_id, source_id=self.source_id)
            return json.dumps([item.to_dict(exclude_none=False) for item in created_items])

        @tool(name="complete_todos", approval_mode="never_require")
        def complete_todos(ids: list[int]) -> str:
            """Mark one or more todo items as complete by ID."""
            if not ids:
                raise ValueError("ids must contain at least one todo ID.")

            items, next_id = self.store.load_state(session, source_id=self.source_id)
            id_set = set(ids)
            completed_count = 0
            updated_items: list[TodoItem] = []
            for item in items:
                if not item.is_complete and item.id in id_set:
                    updated_items.append(
                        TodoItem(
                            id=item.id,
                            title=item.title,
                            description=item.description,
                            is_complete=True,
                        )
                    )
                    completed_count += 1
                else:
                    updated_items.append(item)

            if completed_count:
                self.store.save_state(session, updated_items, next_id=next_id, source_id=self.source_id)
            return json.dumps({"completed": completed_count})

        @tool(name="remove_todos", approval_mode="never_require")
        def remove_todos(ids: list[int]) -> str:
            """Remove one or more todo items by ID."""
            if not ids:
                raise ValueError("ids must contain at least one todo ID.")

            items, next_id = self.store.load_state(session, source_id=self.source_id)
            remaining_items = [item for item in items if item.id not in set(ids)]
            removed_count = len(items) - len(remaining_items)
            if removed_count:
                self.store.save_state(session, remaining_items, next_id=next_id, source_id=self.source_id)
            return json.dumps({"removed": removed_count})

        @tool(name="get_remaining_todos", approval_mode="never_require")
        def get_remaining_todos() -> str:
            """Retrieve only incomplete todo items for the current session."""
            items = [item for item in self.store.load_items(session, source_id=self.source_id) if not item.is_complete]
            return json.dumps([item.to_dict(exclude_none=False) for item in items])

        @tool(name="get_all_todos", approval_mode="never_require")
        def get_all_todos() -> str:
            """Retrieve all todo items for the current session."""
            items = self.store.load_items(session, source_id=self.source_id)
            return json.dumps([item.to_dict(exclude_none=False) for item in items])

        context.extend_instructions(self.source_id, [self.instructions])
        context.extend_tools(
            self.source_id,
            [add_todos, complete_todos, remove_todos, get_remaining_todos, get_all_todos],
        )
        context.extend_messages(
            self.source_id,
            [
                Message(
                    role="user",
                    contents=[
                        "### Current todo list\n"
                        + (
                            "\n".join(
                                f"- {item.id} [{'done' if item.is_complete else 'open'}] {item.title}"
                                + (f": {item.description}" if item.description else "")
                                for item in self.store.load_items(session, source_id=self.source_id)
                            )
                            or "- none yet"
                        )
                    ],
                )
            ],
        )
