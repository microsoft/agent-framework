# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
import os
import weakref
from abc import ABC, abstractmethod
from base64 import urlsafe_b64encode
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any, ClassVar, cast

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


def _parse_todo_items(items_payload: list[Any], *, source_description: str) -> list[TodoItem]:
    """Parse persisted todo item payloads with clear corruption errors."""
    items: list[TodoItem] = []
    for index, item in enumerate(items_payload):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"Todo item at index {index} in {source_description} must be a mapping; got {type(item).__name__}."
            )
        items.append(TodoItem.from_dict(dict(cast(Mapping[str, Any], item))))
    return items


def _coerce_todo_input(todo: TodoInput | dict[str, Any] | Any) -> TodoInput:
    """Normalize tool-provided todo input into a TodoInput model."""
    if isinstance(todo, TodoInput):
        return todo
    if isinstance(todo, MutableMapping):
        return TodoInput.from_dict(cast(MutableMapping[str, Any], todo))
    raise ValueError("Todo input must be a TodoInput instance or JSON object.")


def _safe_next_id(items: list[TodoItem], next_id: int) -> int:
    """Clamp ``next_id`` so it cannot collide with any persisted item id."""
    return max(next_id, max((item.id for item in items), default=0) + 1)


@experimental(feature_id=ExperimentalFeature.HARNESS)
class TodoStore(ABC):
    """Abstract backing store for session todo items."""

    @abstractmethod
    async def load_state(self, session: AgentSession, *, source_id: str) -> tuple[list[TodoItem], int]:
        """Load persisted todo items and the next available ID."""

    @abstractmethod
    async def save_state(self, session: AgentSession, items: list[TodoItem], *, next_id: int, source_id: str) -> None:
        """Persist todo items and the next available ID."""

    async def load_items(self, session: AgentSession, *, source_id: str) -> list[TodoItem]:
        """Load todo items for one session."""
        items, _ = await self.load_state(session, source_id=source_id)
        return items


@experimental(feature_id=ExperimentalFeature.HARNESS)
class TodoSessionStore(TodoStore):
    """Store todo state inside ``AgentSession.state``."""

    async def load_state(self, session: AgentSession, *, source_id: str) -> tuple[list[TodoItem], int]:
        """Load todo state from session state."""
        provider_state_value = session.state.get(source_id)
        if provider_state_value is None:
            provider_state: dict[str, Any] = {}
            session.state[source_id] = provider_state
        elif isinstance(provider_state_value, dict):
            provider_state = cast(dict[str, Any], provider_state_value)
        else:
            raise ValueError(
                f"Session state for source_id {source_id!r} must be a dict; got {type(provider_state_value).__name__}."
            )

        raw_items = provider_state.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError(
                f"Session state for source_id {source_id!r} has a non-list 'items' field; "
                f"got {type(raw_items).__name__}."
            )
        raw_next_id = provider_state.get("next_id", 1)
        if not isinstance(raw_next_id, int):
            raise ValueError(
                f"Session state for source_id {source_id!r} has a non-integer 'next_id' field; "
                f"got {type(raw_next_id).__name__}."
            )
        items_payload: list[Any] = cast(Any, raw_items)
        items = _parse_todo_items(items_payload, source_description="session todo state")
        return items, _safe_next_id(items, raw_next_id)

    async def save_state(self, session: AgentSession, items: list[TodoItem], *, next_id: int, source_id: str) -> None:
        """Persist todo state back into session state."""
        provider_state_value = session.state.get(source_id)
        provider_state = cast(dict[str, Any], provider_state_value) if isinstance(provider_state_value, dict) else {}
        if not isinstance(provider_state_value, dict):
            session.state[source_id] = provider_state
        provider_state["items"] = [item.to_dict(exclude_none=False) for item in items]
        provider_state["next_id"] = _safe_next_id(items, next_id)


@experimental(feature_id=ExperimentalFeature.HARNESS)
class TodoFileStore(TodoStore):
    """Store todo state in one JSON file per session and source ID."""

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
        self._base_root = self.base_path.resolve()

    _ENCODED_SEGMENT_PREFIX: ClassVar[str] = "~todo-"
    _WINDOWS_RESERVED_FILE_STEMS: ClassVar[frozenset[str]] = frozenset({
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    })

    def _get_state_path(self, session: AgentSession, *, source_id: str) -> Path:
        """Return the JSON file path for one session and source ID."""
        session_directory = self.base_path
        if self.owner_state_key is not None:
            owner_value = session.state.get(self.owner_state_key)
            if owner_value is None:
                raise RuntimeError(
                    f"TodoFileStore requires session.state[{self.owner_state_key!r}] to be set for file-backed storage."
                )
            owner_segment = self._path_segment(owner_value, label="owner")
            session_directory = session_directory / f"{self.owner_prefix}{owner_segment}" / self.kind
        session_directory = session_directory / self._path_segment(
            session.session_id, label="session_id", reject_path_separators=True
        )
        state_path = (session_directory / self._state_filename(source_id)).resolve()
        if not state_path.is_relative_to(self._base_root):
            raise ValueError(f"Todo file path escaped base directory for session_id {session.session_id!r}.")
        return state_path

    @classmethod
    def _path_segment(cls, value: object, *, label: str, reject_path_separators: bool = False) -> str:
        """Return a filesystem-safe path segment for user-controlled state values."""
        raw_value = str(value)
        if reject_path_separators and ("/" in raw_value or "\\" in raw_value):
            raise ValueError(f"TodoFileStore {label} must not contain path separators: {raw_value!r}")
        if cls._is_literal_path_segment_safe(raw_value):
            return raw_value
        encoded_value = urlsafe_b64encode(raw_value.encode("utf-8")).decode("ascii").rstrip("=")
        return f"{cls._ENCODED_SEGMENT_PREFIX}{encoded_value or label}"

    @classmethod
    def _is_literal_path_segment_safe(cls, value: str) -> bool:
        """Return whether a value can be used directly as one path segment."""
        if (
            not value
            or value.startswith(".")
            or value.endswith((" ", "."))
            or value.upper() in cls._WINDOWS_RESERVED_FILE_STEMS
        ):
            return False
        if any(ord(character) < 32 for character in value):
            return False
        return all(character.isalnum() or character in "._-" for character in value)

    def _state_filename(self, source_id: str) -> str:
        """Return a source-specific JSON state filename."""
        state_path = Path(self.state_filename)
        source_segment = self._path_segment(source_id, label="source_id")
        if state_path.suffix:
            return f"{state_path.stem}.{source_segment}{state_path.suffix}"
        return f"{state_path.name}.{source_segment}.json"

    async def load_state(self, session: AgentSession, *, source_id: str) -> tuple[list[TodoItem], int]:
        """Load todo state from disk."""
        state_path = self._get_state_path(session, source_id=source_id)
        return await asyncio.to_thread(self._load_state_sync, state_path)

    @staticmethod
    def _load_state_sync(state_path: Path) -> tuple[list[TodoItem], int]:
        """Synchronous helper that performs the disk I/O for ``load_state``."""
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
        items = _parse_todo_items(items_payload, source_description=f"todo file {state_path}")
        return items, _safe_next_id(items, raw_next_id)

    async def save_state(self, session: AgentSession, items: list[TodoItem], *, next_id: int, source_id: str) -> None:
        """Persist todo state to disk."""
        state_path = self._get_state_path(session, source_id=source_id)
        payload = (
            json.dumps({
                "items": [item.to_dict(exclude_none=False) for item in items],
                "next_id": _safe_next_id(items, next_id),
            })
            + "\n"
        )
        await asyncio.to_thread(self._save_state_sync, state_path, payload)

    @staticmethod
    def _save_state_sync(state_path: Path, payload: str) -> None:
        """Synchronous helper that atomically writes the JSON state file."""
        state_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a sibling temp file then atomically replace, so a crash mid-write cannot leave
        # a truncated state file that breaks every subsequent tool call.
        temp_path = state_path.with_name(f"{state_path.name}.tmp.{os.getpid()}")
        try:
            temp_path.write_text(payload, encoding="utf-8")
            os.replace(temp_path, state_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)


@experimental(feature_id=ExperimentalFeature.HARNESS)
class TodoProvider(ContextProvider):
    """Provide todo management tools and instructions to an agent.

    The ``TodoProvider`` enables agents to create, complete, remove, and query todo items as part of their planning
    and execution workflow. Todo state is stored in the configured ``TodoStore`` and persists across agent invocations
    within the same session. By default, state is stored in ``AgentSession.state`` with ``TodoSessionStore``; callers
    can provide ``TodoFileStore`` or another store implementation for file-backed or custom persistence.

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
        # WeakKeyDictionary so per-session locks are evicted automatically when the session is GC'd
        # rather than accumulating in long-running services that create many sessions.
        self._mutation_locks: weakref.WeakKeyDictionary[AgentSession, asyncio.Lock] = weakref.WeakKeyDictionary()

    def _mutation_lock(self, session: AgentSession) -> asyncio.Lock:
        """Return the per-session lock for read-modify-write todo operations."""
        lock = self._mutation_locks.get(session)
        if lock is None:
            lock = asyncio.Lock()
            self._mutation_locks[session] = lock
        return lock

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
        async def add_todos(todos: list[dict[str, Any]]) -> str:
            """Add one or more todo items for the current session."""
            if not todos:
                raise ValueError("todos must contain at least one item.")

            async with self._mutation_lock(session):
                existing_items, next_id = await self.store.load_state(session, source_id=self.source_id)
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

                await self.store.save_state(session, existing_items, next_id=next_id, source_id=self.source_id)
            return json.dumps([item.to_dict(exclude_none=False) for item in created_items])

        @tool(name="complete_todos", approval_mode="never_require")
        async def complete_todos(ids: list[int]) -> str:
            """Mark one or more todo items as complete by ID."""
            if not ids:
                raise ValueError("ids must contain at least one todo ID.")

            async with self._mutation_lock(session):
                items, next_id = await self.store.load_state(session, source_id=self.source_id)
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
                    await self.store.save_state(session, updated_items, next_id=next_id, source_id=self.source_id)
            return json.dumps({"completed": completed_count})

        @tool(name="remove_todos", approval_mode="never_require")
        async def remove_todos(ids: list[int]) -> str:
            """Remove one or more todo items by ID."""
            if not ids:
                raise ValueError("ids must contain at least one todo ID.")

            async with self._mutation_lock(session):
                items, next_id = await self.store.load_state(session, source_id=self.source_id)
                remaining_items = [item for item in items if item.id not in set(ids)]
                removed_count = len(items) - len(remaining_items)
                if removed_count:
                    await self.store.save_state(session, remaining_items, next_id=next_id, source_id=self.source_id)
            return json.dumps({"removed": removed_count})

        @tool(name="get_remaining_todos", approval_mode="never_require")
        async def get_remaining_todos() -> str:
            """Retrieve only incomplete todo items for the current session."""
            items = [
                item for item in await self.store.load_items(session, source_id=self.source_id) if not item.is_complete
            ]
            return json.dumps([item.to_dict(exclude_none=False) for item in items])

        @tool(name="get_all_todos", approval_mode="never_require")
        async def get_all_todos() -> str:
            """Retrieve all todo items for the current session."""
            items = await self.store.load_items(session, source_id=self.source_id)
            return json.dumps([item.to_dict(exclude_none=False) for item in items])

        context.extend_instructions(self.source_id, [self.instructions])
        context.extend_tools(
            self.source_id,
            [add_todos, complete_todos, remove_todos, get_remaining_todos, get_all_todos],
        )
        current_items = await self.store.load_items(session, source_id=self.source_id)
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
                                for item in current_items
                            )
                            or "- none yet"
                        )
                    ],
                )
            ],
        )
