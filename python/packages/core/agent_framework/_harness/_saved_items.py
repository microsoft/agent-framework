# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from .._feature_stage import ExperimentalFeature, experimental
from .._sessions import (
    AgentSession,
    ContextProvider,
    JsonDumps,
    JsonLoads,
    SessionContext,
)
from .._tools import tool
from .._types import Message

DEFAULT_SAVED_ITEMS_SOURCE_ID = "saved_items"
DEFAULT_SAVED_ITEMS_CONTEXT_PROMPT = "## Saved context\nUse the following saved context when it is relevant."
SavedItemType = Literal["memory", "note"]
SavedItemScope = Literal["user", "session"]


@experimental(feature_id=ExperimentalFeature.HARNESS)
class SavedItemRecord:
    """Represent one persisted saved item."""

    item_id: str
    item_type: SavedItemType
    scope: SavedItemScope
    topic: str
    text: str
    date: str
    session_id: str
    owner_id: str | None
    ttl_seconds: int | None
    __slots__ = ("date", "item_id", "item_type", "owner_id", "scope", "session_id", "text", "topic", "ttl_seconds")

    def __init__(
        self,
        item_id: str,
        item_type: SavedItemType,
        scope: SavedItemScope,
        topic: str,
        text: str,
        date: str,
        session_id: str,
        owner_id: str | None,
        ttl_seconds: int | None,
    ) -> None:
        """Initialize one saved item record."""
        self.item_id = item_id
        self.item_type = item_type
        self.scope = scope
        self.topic = topic
        self.text = text
        self.date = date
        self.session_id = session_id
        self.owner_id = owner_id
        self.ttl_seconds = ttl_seconds

    @property
    def created_at(self) -> datetime:
        """Return the parsed creation timestamp."""
        created_at = datetime.fromisoformat(self.date)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return created_at

    @property
    def expires_at(self) -> datetime | None:
        """Return the expiration timestamp, if this item is finite."""
        if self.ttl_seconds is None:
            return None
        return self.created_at + timedelta(seconds=self.ttl_seconds)

    def is_expired(self, *, now: datetime) -> bool:
        """Return whether this item has passed its TTL."""
        expires_at = self.expires_at
        return expires_at is not None and expires_at <= now

    def to_dict(self) -> dict[str, str | int | None]:
        """Serialize the record for persistence."""
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "scope": self.scope,
            "topic": self.topic,
            "text": self.text,
            "date": self.date,
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, raw_record: dict[str, Any]) -> SavedItemRecord:
        """Parse a record loaded from storage."""
        required_fields = {
            "item_id",
            "item_type",
            "scope",
            "topic",
            "text",
            "date",
            "session_id",
            "owner_id",
            "ttl_seconds",
        }
        if not required_fields.issubset(raw_record):
            raise ValueError("Saved item record is missing required JSON fields.")

        item_id = raw_record["item_id"]
        item_type = raw_record["item_type"]
        scope = raw_record["scope"]
        topic = raw_record["topic"]
        text = raw_record["text"]
        date = raw_record["date"]
        session_id = raw_record["session_id"]
        owner_id = raw_record["owner_id"]
        ttl_seconds = raw_record["ttl_seconds"]
        if not all(isinstance(value, str) for value in (item_id, item_type, scope, topic, text, date, session_id)):
            raise ValueError("Saved item string fields must all be strings.")
        if item_type not in {"memory", "note"}:
            raise ValueError("Saved item item_type must be either 'memory' or 'note'.")
        if scope not in {"user", "session"}:
            raise ValueError("Saved item scope must be either 'user' or 'session'.")
        if owner_id is not None and not isinstance(owner_id, str):
            raise ValueError("Saved item owner_id must be a string or null.")
        if ttl_seconds is not None and not isinstance(ttl_seconds, int):
            raise ValueError("Saved item ttl_seconds must be an integer or null.")

        return cls(
            item_id=item_id,
            item_type=item_type,
            scope=scope,
            topic=topic,
            text=text,
            date=date,
            session_id=session_id,
            owner_id=owner_id,
            ttl_seconds=ttl_seconds,
        )

    def __eq__(self, other: object) -> bool:
        """Compare two saved item records by value."""
        if not isinstance(other, SavedItemRecord):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return (
            "SavedItemRecord("
            f"item_id={self.item_id!r}, item_type={self.item_type!r}, scope={self.scope!r}, "
            f"topic={self.topic!r}, text={self.text!r}, date={self.date!r}, "
            f"session_id={self.session_id!r}, owner_id={self.owner_id!r}, ttl_seconds={self.ttl_seconds!r})"
        )


@experimental(feature_id=ExperimentalFeature.HARNESS)
class SavedTopicLogEntry:
    """Track a historical topic for saved items."""

    topic: str
    first_seen: str
    last_seen: str
    times_recorded: int
    __slots__ = ("first_seen", "last_seen", "times_recorded", "topic")

    def __init__(self, topic: str, first_seen: str, last_seen: str, times_recorded: int) -> None:
        """Initialize one saved-topic log entry."""
        self.topic = topic
        self.first_seen = first_seen
        self.last_seen = last_seen
        self.times_recorded = times_recorded

    def to_dict(self) -> dict[str, str | int]:
        """Serialize the topic log entry for persistence."""
        return {
            "topic": self.topic,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "times_recorded": self.times_recorded,
        }

    @classmethod
    def from_dict(cls, raw_entry: dict[str, Any]) -> SavedTopicLogEntry:
        """Parse a topic log entry loaded from storage."""
        required_fields = {"topic", "first_seen", "last_seen", "times_recorded"}
        if not required_fields.issubset(raw_entry):
            raise ValueError("Saved topic log entry is missing required JSON fields.")
        topic = raw_entry["topic"]
        first_seen = raw_entry["first_seen"]
        last_seen = raw_entry["last_seen"]
        times_recorded = raw_entry["times_recorded"]
        if not all(isinstance(value, str) for value in (topic, first_seen, last_seen)):
            raise ValueError("Saved topic log string fields must all be strings.")
        if not isinstance(times_recorded, int):
            raise ValueError("Saved topic log times_recorded must be an integer.")
        return cls(topic=topic, first_seen=first_seen, last_seen=last_seen, times_recorded=times_recorded)

    def __eq__(self, other: object) -> bool:
        """Compare two saved topic entries by value."""
        if not isinstance(other, SavedTopicLogEntry):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return (
            "SavedTopicLogEntry("
            f"topic={self.topic!r}, first_seen={self.first_seen!r}, "
            f"last_seen={self.last_seen!r}, times_recorded={self.times_recorded!r})"
        )


def _default_json_dumps(value: Any) -> str:
    """Serialize JSON-compatible data to a pretty-printed string."""
    return json.dumps(value, indent=2)


def _default_json_loads(value: str | bytes) -> Any:
    """Deserialize JSON text or bytes."""
    return json.loads(value)


def _serialize_json(value: object, *, dumps: JsonDumps) -> str:
    """Serialize JSON-compatible data to text."""
    serialized = dumps(value)
    return serialized.decode("utf-8") if isinstance(serialized, bytes) else serialized


def _normalize_item_text(value: str, *, field_name: str) -> str:
    """Validate and normalize a text field used by a saved item record."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized


def _normalize_item_type(item_type: str) -> SavedItemType:
    """Validate a saved item type."""
    normalized = item_type.strip().lower()
    if normalized not in {"memory", "note"}:
        raise ValueError("item_type must be either 'memory' or 'note'.")
    return cast(SavedItemType, normalized)


def _normalize_scope(scope: str) -> SavedItemScope:
    """Validate a saved item scope."""
    normalized = scope.strip().lower()
    if normalized not in {"user", "session"}:
        raise ValueError("scope must be either 'user' or 'session'.")
    return cast(SavedItemScope, normalized)


def _normalize_ttl_seconds(ttl_seconds: int | None) -> int | None:
    """Validate an optional TTL in seconds."""
    if ttl_seconds is None:
        return None
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be greater than zero when provided.")
    return ttl_seconds


def _format_saved_item(record: SavedItemRecord) -> dict[str, Any]:
    """Shape one saved item record for tool output."""
    expires_at = record.expires_at
    return {
        "item_id": record.item_id,
        "item_type": record.item_type,
        "scope": record.scope,
        "topic": record.topic,
        "text": record.text,
        "date": record.date,
        "session_id": record.session_id,
        "owner_id": record.owner_id,
        "ttl_seconds": record.ttl_seconds,
        "ttl": "infinite" if record.ttl_seconds is None else f"{record.ttl_seconds} seconds",
        "expires_at": None if expires_at is None else expires_at.replace(microsecond=0).isoformat(),
    }


def _format_saved_item_context(records: list[SavedItemRecord]) -> str:
    """Render active saved items for the provider context message."""
    if not records:
        return "- none saved yet"
    lines: list[str] = []
    for record in records:
        ttl_text = "infinite" if record.ttl_seconds is None else f"{record.ttl_seconds} seconds"
        lines.append(
            f"- {record.item_id} | type={record.item_type} | scope={record.scope} | "
            f"topic={record.topic} | ttl={ttl_text} | {record.text}"
        )
    return "\n".join(lines)


def _format_topic_context(entries: list[SavedTopicLogEntry]) -> str:
    """Render historical topic entries for the provider context message."""
    if not entries:
        return "- none recorded yet"
    return "\n".join(
        f"- {entry.topic} (recorded {entry.times_recorded} time(s), last seen {entry.last_seen})" for entry in entries
    )


class SavedItemsStore(ABC):
    """Abstract backing store for saved items."""

    def get_owner_id(self, session: AgentSession) -> str | None:
        """Return the logical owner ID for one session, if the store uses one."""
        del session
        return None

    @abstractmethod
    def list_items(
        self,
        session: AgentSession,
        *,
        source_id: str,
        scope: SavedItemScope | None = None,
        session_id: str | None = None,
        item_type: SavedItemType | None = None,
    ) -> list[SavedItemRecord]:
        """Return stored items filtered by scope/session/type."""

    @abstractmethod
    def get_item(self, session: AgentSession, *, source_id: str, item_id: str) -> SavedItemRecord:
        """Return one stored item by ID."""

    @abstractmethod
    def write_item(self, session: AgentSession, record: SavedItemRecord, *, source_id: str) -> None:
        """Persist one saved item."""

    @abstractmethod
    def delete_item(self, session: AgentSession, record: SavedItemRecord, *, source_id: str) -> None:
        """Delete one saved item."""

    @abstractmethod
    def list_topics(self, session: AgentSession, *, source_id: str) -> list[SavedTopicLogEntry]:
        """Return all recorded saved-item topics."""

    @abstractmethod
    def record_topic(self, session: AgentSession, *, source_id: str, topic: str, now: datetime) -> None:
        """Record one saved-item topic occurrence."""

    @abstractmethod
    def get_next_item_id(self, session: AgentSession, *, source_id: str) -> str:
        """Allocate the next stable saved-item ID."""

    def prune_expired_items(
        self,
        session: AgentSession,
        *,
        source_id: str,
        now: datetime | None = None,
    ) -> list[SavedItemRecord]:
        """Delete expired saved items and return the removed records."""
        current_time = now or datetime.now(UTC)
        removed_records: list[SavedItemRecord] = []
        for record in self.list_items(session, source_id=source_id):
            if record.is_expired(now=current_time):
                self.delete_item(session, record, source_id=source_id)
                removed_records.append(record)
        return removed_records

    def list_visible_items(
        self,
        session: AgentSession,
        *,
        source_id: str,
        item_type: SavedItemType | None = None,
        scope: SavedItemScope | None = None,
    ) -> list[SavedItemRecord]:
        """Return items visible from the current session."""
        if scope == "user":
            return self.list_items(session, source_id=source_id, scope="user", item_type=item_type)
        if scope == "session":
            return self.list_items(
                session,
                source_id=source_id,
                scope="session",
                session_id=session.session_id,
                item_type=item_type,
            )
        return sorted(
            [
                *self.list_items(session, source_id=source_id, scope="user", item_type=item_type),
                *self.list_items(
                    session,
                    source_id=source_id,
                    scope="session",
                    session_id=session.session_id,
                    item_type=item_type,
                ),
            ],
            key=lambda record: (record.item_type, record.scope, record.topic, record.date, record.item_id),
        )

    def get_visible_item(self, session: AgentSession, *, source_id: str, item_id: str) -> SavedItemRecord:
        """Return one item visible from the current session."""
        record = self.get_item(session, source_id=source_id, item_id=item_id)
        if record.scope == "session" and record.session_id != session.session_id:
            raise PermissionError(
                f"Saved item '{item_id}' belongs to session '{record.session_id}' "
                f"and is not visible in '{session.session_id}'."
            )
        return record


@experimental(feature_id=ExperimentalFeature.HARNESS)
class SavedItemsSessionStore(SavedItemsStore):
    """Store saved items inside ``AgentSession.state``."""

    def _get_provider_state(self, session: AgentSession, *, source_id: str) -> dict[str, Any]:
        """Return the mutable provider state stored on the session."""
        provider_state_value = session.state.get(source_id)
        provider_state = cast(dict[str, Any], provider_state_value) if isinstance(provider_state_value, dict) else {}
        if not isinstance(provider_state_value, dict):
            session.state[source_id] = provider_state
        if not isinstance(provider_state.get("items"), list):
            provider_state["items"] = []
        if not isinstance(provider_state.get("topics"), list):
            provider_state["topics"] = []
        if not isinstance(provider_state.get("next_id"), int):
            provider_state["next_id"] = 1
        return provider_state

    def list_items(
        self,
        session: AgentSession,
        *,
        source_id: str,
        scope: SavedItemScope | None = None,
        session_id: str | None = None,
        item_type: SavedItemType | None = None,
    ) -> list[SavedItemRecord]:
        """Return saved items stored in session state."""
        provider_state = self._get_provider_state(session, source_id=source_id)
        raw_items = provider_state.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError("Saved item state items must be a list.")
        typed_raw_items = cast(list[Any], raw_items)
        records = [
            SavedItemRecord.from_dict(cast(dict[str, Any], item)) for item in typed_raw_items if isinstance(item, dict)
        ]
        filtered_records: list[SavedItemRecord] = []
        for record in records:
            if scope is not None and record.scope != scope:
                continue
            if item_type is not None and record.item_type != item_type:
                continue
            if session_id is not None and record.session_id != session_id:
                continue
            filtered_records.append(record)
        return sorted(
            filtered_records,
            key=lambda record: (record.item_type, record.scope, record.topic, record.date, record.item_id),
        )

    def get_item(self, session: AgentSession, *, source_id: str, item_id: str) -> SavedItemRecord:
        """Return one saved item stored in session state."""
        for record in self.list_items(session, source_id=source_id):
            if record.item_id == item_id:
                return record
        raise FileNotFoundError(f"No saved item named '{item_id}' was found for this session.")

    def write_item(self, session: AgentSession, record: SavedItemRecord, *, source_id: str) -> None:
        """Persist one saved item into session state."""
        provider_state = self._get_provider_state(session, source_id=source_id)
        records = [
            existing for existing in self.list_items(session, source_id=source_id) if existing.item_id != record.item_id
        ]
        records.append(record)
        provider_state["items"] = [saved_item.to_dict() for saved_item in records]

    def delete_item(self, session: AgentSession, record: SavedItemRecord, *, source_id: str) -> None:
        """Delete one saved item from session state."""
        provider_state = self._get_provider_state(session, source_id=source_id)
        provider_state["items"] = [
            existing.to_dict()
            for existing in self.list_items(session, source_id=source_id)
            if existing.item_id != record.item_id
        ]

    def list_topics(self, session: AgentSession, *, source_id: str) -> list[SavedTopicLogEntry]:
        """Return stored topic log entries from session state."""
        provider_state = self._get_provider_state(session, source_id=source_id)
        raw_topics = provider_state.get("topics", [])
        if not isinstance(raw_topics, list):
            raise ValueError("Saved item topic state must be a list.")
        typed_raw_topics = cast(list[Any], raw_topics)
        return sorted(
            [
                SavedTopicLogEntry.from_dict(cast(dict[str, Any], entry))
                for entry in typed_raw_topics
                if isinstance(entry, dict)
            ],
            key=lambda entry: entry.topic,
        )

    def record_topic(self, session: AgentSession, *, source_id: str, topic: str, now: datetime) -> None:
        """Record one topic occurrence in session state."""
        provider_state = self._get_provider_state(session, source_id=source_id)
        normalized_topic = _normalize_item_text(topic, field_name="topic")
        timestamp = now.replace(microsecond=0).isoformat()
        updated_entries: list[SavedTopicLogEntry] = []
        matched_entry = False
        for entry in self.list_topics(session, source_id=source_id):
            if entry.topic == normalized_topic:
                updated_entries.append(
                    SavedTopicLogEntry(
                        topic=entry.topic,
                        first_seen=entry.first_seen,
                        last_seen=timestamp,
                        times_recorded=entry.times_recorded + 1,
                    )
                )
                matched_entry = True
            else:
                updated_entries.append(entry)
        if not matched_entry:
            updated_entries.append(
                SavedTopicLogEntry(
                    topic=normalized_topic,
                    first_seen=timestamp,
                    last_seen=timestamp,
                    times_recorded=1,
                )
            )
        provider_state["topics"] = [entry.to_dict() for entry in sorted(updated_entries, key=lambda entry: entry.topic)]

    def get_next_item_id(self, session: AgentSession, *, source_id: str) -> str:
        """Allocate the next stable saved-item ID from session state."""
        provider_state = self._get_provider_state(session, source_id=source_id)
        next_id = provider_state.get("next_id", 1)
        if not isinstance(next_id, int):
            next_id = 1
        provider_state["next_id"] = next_id + 1
        return f"item-{next_id}"


@experimental(feature_id=ExperimentalFeature.HARNESS)
class SavedItemsFileStore(SavedItemsStore):
    """Store saved items on disk under owner/session directories."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        kind: str = "memories",
        owner_prefix: str = "",
        owner_state_key: str,
        dumps: JsonDumps | None = None,
        loads: JsonLoads | None = None,
    ) -> None:
        """Initialize the file-backed saved-items store.

        Args:
            base_path: Root storage directory.

        Keyword Args:
            kind: Storage bucket name under each owner directory.
            owner_prefix: Optional prefix applied to the resolved owner ID.
            owner_state_key: Session-state key holding the logical owner ID.
            dumps: Callable used to serialize persisted saved-item JSON.
            loads: Callable used to deserialize persisted saved-item JSON.
        """
        self.base_path = Path(base_path)
        self.kind = kind
        self.owner_prefix = owner_prefix
        self.owner_state_key = owner_state_key
        self.dumps = dumps or _default_json_dumps
        self.loads = loads or _default_json_loads

    def _get_owner_id(self, session: AgentSession) -> str:
        """Return the logical owner ID for one session."""
        owner_value = session.state.get(self.owner_state_key)
        if owner_value is None:
            raise RuntimeError(
                "SavedItemsFileStore requires "
                f"session.state[{self.owner_state_key!r}] to be set for file-backed storage."
            )
        return str(owner_value)

    def get_owner_id(self, session: AgentSession) -> str | None:
        """Return the logical owner ID for one session."""
        return self._get_owner_id(session)

    def _get_owner_directory(self, session: AgentSession) -> Path:
        """Return the owner-level storage directory."""
        owner_directory = self.base_path / f"{self.owner_prefix}{self._get_owner_id(session)}" / self.kind
        owner_directory.mkdir(parents=True, exist_ok=True)
        return owner_directory

    def _get_session_directory(self, session: AgentSession, *, session_id: str | None = None) -> Path:
        """Return the session-level storage directory."""
        session_directory = self._get_owner_directory(session) / (session_id or session.session_id)
        session_directory.mkdir(parents=True, exist_ok=True)
        return session_directory

    def _list_session_directories(self, session: AgentSession) -> list[Path]:
        """Return all stored session directories for the current owner."""
        owner_directory = self._get_owner_directory(session)
        return sorted(path for path in owner_directory.iterdir() if path.is_dir())

    def _get_item_path(self, session: AgentSession, *, session_id: str, item_id: str) -> Path:
        """Return the file path for one saved item."""
        return self._get_session_directory(session, session_id=session_id) / f"{item_id}.json"

    def _get_topic_log_path(self, session: AgentSession, *, session_id: str) -> Path:
        """Return the topic log path for one owner/session pair."""
        return self._get_session_directory(session, session_id=session_id) / "topics.json"

    def _list_item_paths(self, session: AgentSession) -> list[Path]:
        """Return all persisted saved-item files for one owner."""
        item_paths: list[Path] = []
        for session_directory in self._list_session_directories(session):
            item_paths.extend(
                path
                for path in sorted(session_directory.glob("*.json"))
                if path.is_file() and path.name != "topics.json"
            )
        return item_paths

    def _load_item_record(self, item_path: Path) -> SavedItemRecord:
        """Load one saved item record from disk."""
        raw_record = cast(dict[str, Any], self.loads(item_path.read_text(encoding="utf-8")))
        if not isinstance(raw_record, dict):
            raise ValueError(f"Saved item file {item_path.name} must contain a JSON object.")
        return SavedItemRecord.from_dict(raw_record)

    def list_items(
        self,
        session: AgentSession,
        *,
        source_id: str,
        scope: SavedItemScope | None = None,
        session_id: str | None = None,
        item_type: SavedItemType | None = None,
    ) -> list[SavedItemRecord]:
        """Return stored items filtered by scope/session/type."""
        del source_id
        records = [self._load_item_record(item_path) for item_path in self._list_item_paths(session)]
        filtered_records: list[SavedItemRecord] = []
        for record in records:
            if scope is not None and record.scope != scope:
                continue
            if item_type is not None and record.item_type != item_type:
                continue
            if session_id is not None and record.session_id != session_id:
                continue
            filtered_records.append(record)
        return sorted(
            filtered_records,
            key=lambda record: (record.item_type, record.scope, record.topic, record.date, record.item_id),
        )

    def get_item(self, session: AgentSession, *, source_id: str, item_id: str) -> SavedItemRecord:
        """Return one stored item by ID."""
        del source_id
        for item_path in self._list_item_paths(session):
            if item_path.stem == item_id:
                return self._load_item_record(item_path)
        raise FileNotFoundError(f"No saved item named '{item_id}' was found for this owner.")

    def write_item(self, session: AgentSession, record: SavedItemRecord, *, source_id: str) -> None:
        """Persist one saved item to disk."""
        del source_id
        item_path = self._get_item_path(session, session_id=record.session_id, item_id=record.item_id)
        item_path.write_text(_serialize_json(record.to_dict(), dumps=self.dumps) + "\n", encoding="utf-8")

    def delete_item(self, session: AgentSession, record: SavedItemRecord, *, source_id: str) -> None:
        """Delete one saved item from disk."""
        del source_id
        self._get_item_path(session, session_id=record.session_id, item_id=record.item_id).unlink(missing_ok=True)

    def list_topics(self, session: AgentSession, *, source_id: str) -> list[SavedTopicLogEntry]:
        """Load the historical topic log for the current owner."""
        del source_id
        merged_entries: dict[str, SavedTopicLogEntry] = {}
        for session_directory in self._list_session_directories(session):
            topic_log_path = session_directory / "topics.json"
            if not topic_log_path.exists():
                continue
            raw_log = self.loads(topic_log_path.read_text(encoding="utf-8"))
            if not isinstance(raw_log, dict) or "topics" not in raw_log or not isinstance(raw_log["topics"], list):
                raise ValueError(f"Saved topic log {topic_log_path} must contain a 'topics' list.")
            for raw_entry in cast(list[Any], raw_log["topics"]):
                if not isinstance(raw_entry, dict):
                    continue
                entry = SavedTopicLogEntry.from_dict(cast(dict[str, Any], raw_entry))
                existing_entry = merged_entries.get(entry.topic)
                if existing_entry is None:
                    merged_entries[entry.topic] = entry
                else:
                    merged_entries[entry.topic] = SavedTopicLogEntry(
                        topic=entry.topic,
                        first_seen=min(existing_entry.first_seen, entry.first_seen),
                        last_seen=max(existing_entry.last_seen, entry.last_seen),
                        times_recorded=existing_entry.times_recorded + entry.times_recorded,
                    )
        return sorted(merged_entries.values(), key=lambda entry: entry.topic)

    def record_topic(self, session: AgentSession, *, source_id: str, topic: str, now: datetime) -> None:
        """Record one topic occurrence in the current session directory."""
        del source_id
        normalized_topic = _normalize_item_text(topic, field_name="topic")
        timestamp = now.replace(microsecond=0).isoformat()
        topic_log_path = self._get_topic_log_path(session, session_id=session.session_id)
        existing_entries: list[SavedTopicLogEntry] = []
        if topic_log_path.exists():
            raw_log = self.loads(topic_log_path.read_text(encoding="utf-8"))
            if not isinstance(raw_log, dict) or "topics" not in raw_log or not isinstance(raw_log["topics"], list):
                raise ValueError(f"Saved topic log {topic_log_path} must contain a 'topics' list.")
            existing_entries = [
                SavedTopicLogEntry.from_dict(cast(dict[str, Any], entry))
                for entry in cast(list[Any], raw_log["topics"])
                if isinstance(entry, dict)
            ]
        updated_entries: list[SavedTopicLogEntry] = []
        matched_entry = False
        for entry in existing_entries:
            if entry.topic == normalized_topic:
                updated_entries.append(
                    SavedTopicLogEntry(
                        topic=entry.topic,
                        first_seen=entry.first_seen,
                        last_seen=timestamp,
                        times_recorded=entry.times_recorded + 1,
                    )
                )
                matched_entry = True
            else:
                updated_entries.append(entry)
        if not matched_entry:
            updated_entries.append(
                SavedTopicLogEntry(
                    topic=normalized_topic,
                    first_seen=timestamp,
                    last_seen=timestamp,
                    times_recorded=1,
                )
            )
        topic_log_path.write_text(
            _serialize_json(
                {"topics": [entry.to_dict() for entry in sorted(updated_entries, key=lambda entry: entry.topic)]},
                dumps=self.dumps,
            )
            + "\n",
            encoding="utf-8",
        )

    def get_next_item_id(self, session: AgentSession, *, source_id: str) -> str:
        """Allocate the next stable saved-item ID for the current owner."""
        del source_id
        next_number = 1
        for record in self.list_items(session, source_id=DEFAULT_SAVED_ITEMS_SOURCE_ID):
            _, _, suffix = record.item_id.partition("-")
            if suffix.isdigit():
                next_number = max(next_number, int(suffix) + 1)
        return f"item-{next_number}"


@experimental(feature_id=ExperimentalFeature.HARNESS)
class SavedItemsContextProvider(ContextProvider):
    """Inject saved-item tools, instructions, and current context."""

    def __init__(
        self,
        source_id: str = DEFAULT_SAVED_ITEMS_SOURCE_ID,
        *,
        context_prompt: str | None = None,
        store: SavedItemsStore | None = None,
        dumps: JsonDumps | None = None,
    ) -> None:
        """Initialize the saved-items provider.

        Args:
            source_id: Unique source ID for the provider.

        Keyword Args:
            context_prompt: Optional context prompt override.
            store: Optional saved-items store override.
            dumps: Callable used to serialize tool results to JSON text.
        """
        super().__init__(source_id)
        self.context_prompt = context_prompt or DEFAULT_SAVED_ITEMS_CONTEXT_PROMPT
        self.store = store or SavedItemsSessionStore()
        self.dumps = dumps or _default_json_dumps

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject saved-item tools, instructions, and current context before the model runs."""
        del agent, state

        self.store.prune_expired_items(session, source_id=self.source_id)

        @tool(name="list_saved_items", approval_mode="never_require")
        def list_saved_items(item_type: str | None = None, scope: str | None = None) -> str:
            """List active saved items visible from the current session."""
            normalized_item_type = None if item_type is None else _normalize_item_type(item_type)
            normalized_scope = None if scope is None else _normalize_scope(scope)
            records = self.store.list_visible_items(
                session,
                source_id=self.source_id,
                item_type=normalized_item_type,
                scope=normalized_scope,
            )
            return (
                _serialize_json([_format_saved_item(record) for record in records], dumps=self.dumps)
                if records
                else "[]"
            )

        @tool(name="read_saved_item", approval_mode="never_require")
        def read_saved_item(item_id: str) -> str:
            """Read one saved item that is visible from the current session."""
            record = self.store.get_visible_item(
                session,
                source_id=self.source_id,
                item_id=_normalize_item_text(item_id, field_name="item_id"),
            )
            return _serialize_json(_format_saved_item(record), dumps=self.dumps)

        @tool(name="add_saved_item", approval_mode="never_require")
        def add_saved_item(
            topic: str,
            text: str,
            item_type: str = "memory",
            scope: str = "user",
            ttl_seconds: int | None = None,
        ) -> str:
            """Create one saved item for the current session/user scope."""
            record = SavedItemRecord(
                item_id=self.store.get_next_item_id(session, source_id=self.source_id),
                item_type=_normalize_item_type(item_type),
                scope=_normalize_scope(scope),
                topic=_normalize_item_text(topic, field_name="topic"),
                text=_normalize_item_text(text, field_name="text"),
                date=datetime.now(UTC).replace(microsecond=0).isoformat(),
                session_id=session.session_id,
                owner_id=self.store.get_owner_id(session),
                ttl_seconds=_normalize_ttl_seconds(ttl_seconds),
            )
            self.store.write_item(session, record, source_id=self.source_id)
            self.store.record_topic(session, source_id=self.source_id, topic=record.topic, now=record.created_at)
            return _serialize_json(_format_saved_item(record), dumps=self.dumps)

        @tool(name="update_saved_item", approval_mode="never_require")
        def update_saved_item(
            item_id: str,
            text: str | None = None,
            topic: str | None = None,
            item_type: str | None = None,
            scope: str | None = None,
        ) -> str:
            """Update one saved item without changing its age or TTL."""
            existing_record = self.store.get_visible_item(
                session,
                source_id=self.source_id,
                item_id=_normalize_item_text(item_id, field_name="item_id"),
            )
            updated_topic = existing_record.topic if topic is None else _normalize_item_text(topic, field_name="topic")
            updated_item_type = existing_record.item_type if item_type is None else _normalize_item_type(item_type)
            updated_scope = existing_record.scope if scope is None else _normalize_scope(scope)
            updated_record = SavedItemRecord(
                item_id=existing_record.item_id,
                item_type=updated_item_type,
                scope=updated_scope,
                topic=updated_topic,
                text=existing_record.text if text is None else _normalize_item_text(text, field_name="text"),
                date=existing_record.date,
                session_id=session.session_id if updated_scope == "session" else existing_record.session_id,
                owner_id=existing_record.owner_id,
                ttl_seconds=existing_record.ttl_seconds,
            )
            self.store.write_item(session, updated_record, source_id=self.source_id)
            if updated_record.session_id != existing_record.session_id:
                self.store.delete_item(session, existing_record, source_id=self.source_id)
            if updated_topic != existing_record.topic:
                self.store.record_topic(
                    session,
                    source_id=self.source_id,
                    topic=updated_topic,
                    now=datetime.now(UTC).replace(microsecond=0),
                )
            return _serialize_json(_format_saved_item(updated_record), dumps=self.dumps)

        @tool(name="set_saved_item_ttl", approval_mode="never_require")
        def set_saved_item_ttl(item_id: str, ttl_seconds: int | None = None) -> str:
            """Set or clear the TTL for one saved item visible in the current session."""
            current_time = datetime.now(UTC).replace(microsecond=0)
            existing_record = self.store.get_visible_item(
                session,
                source_id=self.source_id,
                item_id=_normalize_item_text(item_id, field_name="item_id"),
            )
            updated_record = SavedItemRecord(
                item_id=existing_record.item_id,
                item_type=existing_record.item_type,
                scope=existing_record.scope,
                topic=existing_record.topic,
                text=existing_record.text,
                date=existing_record.date,
                session_id=existing_record.session_id,
                owner_id=existing_record.owner_id,
                ttl_seconds=_normalize_ttl_seconds(ttl_seconds),
            )
            if updated_record.is_expired(now=current_time):
                self.store.delete_item(session, updated_record, source_id=self.source_id)
                return (
                    f"Deleted saved item '{updated_record.item_id}' because the new TTL "
                    "had already expired relative to "
                    f"its creation time {updated_record.date}."
                )
            self.store.write_item(session, updated_record, source_id=self.source_id)
            return _serialize_json(_format_saved_item(updated_record), dumps=self.dumps)

        @tool(name="delete_saved_item", approval_mode="never_require")
        def delete_saved_item(item_id: str) -> str:
            """Delete one saved item visible in the current session."""
            existing_record = self.store.get_visible_item(
                session,
                source_id=self.source_id,
                item_id=_normalize_item_text(item_id, field_name="item_id"),
            )
            self.store.delete_item(session, existing_record, source_id=self.source_id)
            return f"Deleted saved item '{existing_record.item_id}'."

        @tool(name="list_saved_item_topics", approval_mode="never_require")
        def list_saved_item_topics(item_type: str | None = None) -> str:
            """List all topics ever recorded for the current saved items."""
            entries = self.store.list_topics(session, source_id=self.source_id)
            if item_type is None:
                return _serialize_json([entry.to_dict() for entry in entries], dumps=self.dumps)
            normalized_item_type = _normalize_item_type(item_type)
            visible_topics = {
                record.topic
                for record in self.store.list_items(session, source_id=self.source_id, item_type=normalized_item_type)
            }
            return _serialize_json(
                [entry.to_dict() for entry in entries if entry.topic in visible_topics],
                dumps=self.dumps,
            )

        @tool(name="list_saved_items_in_session", approval_mode="always_require")
        def list_saved_items_in_session(session_id: str, item_type: str = "note") -> str:
            """List saved items from another session after approval."""
            records = self.store.list_items(
                session,
                source_id=self.source_id,
                session_id=_normalize_item_text(session_id, field_name="session_id"),
                scope="session",
                item_type=_normalize_item_type(item_type),
            )
            return (
                _serialize_json([_format_saved_item(record) for record in records], dumps=self.dumps)
                if records
                else "[]"
            )

        @tool(name="read_saved_item_in_session", approval_mode="always_require")
        def read_saved_item_in_session(item_id: str, session_id: str) -> str:
            """Read one session-scoped saved item from another session after approval."""
            record = self.store.get_item(
                session,
                source_id=self.source_id,
                item_id=_normalize_item_text(item_id, field_name="item_id"),
            )
            normalized_session_id = _normalize_item_text(session_id, field_name="session_id")
            if record.scope != "session" or record.session_id != normalized_session_id:
                raise FileNotFoundError(
                    f"No session-scoped saved item named '{record.item_id}' was found "
                    f"for session '{normalized_session_id}'."
                )
            return _serialize_json(_format_saved_item(record), dumps=self.dumps)

        user_scoped_records = self.store.list_items(session, source_id=self.source_id, scope="user")
        session_scoped_records = self.store.list_items(
            session,
            source_id=self.source_id,
            scope="session",
            session_id=session.session_id,
        )
        topic_entries = self.store.list_topics(session, source_id=self.source_id)
        context.extend_tools(
            self.source_id,
            [
                list_saved_items,
                read_saved_item,
                add_saved_item,
                update_saved_item,
                set_saved_item_ttl,
                delete_saved_item,
                list_saved_item_topics,
                list_saved_items_in_session,
                read_saved_item_in_session,
            ],
        )
        context.extend_instructions(
            self.source_id,
            [
                "Use the saved-item tools for durable context that belongs to this user or session.",
                (
                    "Use item_type='memory' for durable facts or preferences, and "
                    "item_type='note' for note-like information."
                ),
                (
                    "Use scope='user' for information that should follow the same "
                    "user across sessions, and scope='session' for information that "
                    "should stay local to the current session."
                ),
                (
                    "Use add_saved_item to save something new, update_saved_item to "
                    "correct it, set_saved_item_ttl to make it temporary or infinite, "
                    "and delete_saved_item when it should be forgotten."
                ),
                (
                    "Use list_saved_items, read_saved_item, and list_saved_item_topics "
                    "to inspect what is currently saved and which topics have been seen before."
                ),
                (
                    "Use list_saved_items_in_session or read_saved_item_in_session "
                    "only when the user explicitly asks for session-scoped saved items "
                    "from another session, because those tools require approval."
                ),
            ],
        )
        context.extend_messages(
            self.source_id,
            [
                Message(
                    role="user",
                    contents=[
                        (
                            f"{self.context_prompt}\n\n"
                            "### User-scoped saved items\n"
                            f"{_format_saved_item_context(user_scoped_records)}\n\n"
                            f"### Session-scoped saved items for session {session.session_id}\n"
                            f"{_format_saved_item_context(session_scoped_records)}\n\n"
                            "### Historical saved-item topics\n"
                            f"{_format_topic_context(topic_entries)}"
                        )
                    ],
                )
            ],
        )
