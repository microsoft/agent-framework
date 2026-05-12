# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import weakref
from abc import ABC, abstractmethod
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, ClassVar, Final, cast

from .._clients import SupportsChatGetResponse
from .._compaction import group_messages
from .._feature_stage import ExperimentalFeature, experimental
from .._sessions import AgentSession, FileHistoryProvider, HistoryProvider, JsonDumps, JsonLoads, SessionContext
from .._tools import tool
from .._types import ChatResponse, Message
from ..exceptions import ChatClientException

LOGGER = logging.getLogger(__name__)

DEFAULT_MEMORY_SOURCE_ID = "memory"
DEFAULT_MEMORY_CONTEXT_PROMPT = "## Memory\nUse MEMORY.md and the loaded topic files when they are relevant."
DEFAULT_MEMORY_INDEX_FILE_NAME = "MEMORY.md"
DEFAULT_MEMORY_TOPICS_DIRECTORY_NAME = "topics"
DEFAULT_MEMORY_TRANSCRIPTS_DIRECTORY_NAME = "transcripts"
DEFAULT_MEMORY_STATE_FILE_NAME = "state.json"
DEFAULT_MEMORY_INDEX_LINE_LIMIT = 200
DEFAULT_MEMORY_INDEX_LINE_LENGTH = 150
DEFAULT_MEMORY_SELECTION_LIMIT = 3
DEFAULT_MEMORY_CONSOLIDATION_MIN_SESSIONS = 5
DEFAULT_MEMORY_MAX_EXTRACTIONS = 5
DEFAULT_MEMORY_CONSOLIDATION_INTERVAL: Final[timedelta] = timedelta(hours=24)
DEFAULT_MEMORY_INDEX_HEADER = "# MEMORY"
DEFAULT_MEMORY_NO_TOPICS_TEXT = "- none yet"
DEFAULT_MEMORY_EXTRACTION_PROMPT = """You extract durable memory candidates from an agent transcript delta.

Return only JSON with this exact shape:
{"memories":[{"topic":"short topic name","memory":"durable fact"}]}

Rules:
- include only durable facts, preferences, decisions, or patterns worth remembering later
- do not include transient tasks, temporary reminders, one-off outputs, or tool chatter
- keep topic names short and stable
- keep each memory item to one sentence
- return at most 5 memory items
- return {"memories": []} when nothing should be remembered
"""
DEFAULT_MEMORY_CONSOLIDATION_PROMPT = """You consolidate one topic memory file into a tighter durable form.

Return only JSON with this exact shape:
{"summary":"short summary","memories":["memory 1","memory 2"]}

Rules:
- preserve durable facts, preferences, and decisions
- remove duplicates and overlaps
- drop stale or obviously transient items
- keep the summary concise
- keep the memory list short and high-signal
"""
_FILE_HISTORY_ENCODED_SESSION_PREFIX = "~session-"
HistoryMessageFilter = Callable[[Message], Message | None]
_WORD_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,}", flags=re.IGNORECASE)


def _payload_preview(text: str, *, limit: int = 120) -> str:
    """Return a single-line, length-capped preview of an LLM payload for log messages."""
    flattened = " ".join(text.split())
    return f"{flattened[:limit]}…" if len(flattened) > limit else flattened


# Narrow set of exceptions we treat as transient when calling the chat client during
# memory extraction/consolidation. Programmer errors (AttributeError, TypeError, KeyError, ...)
# are intentionally NOT caught so misconfigured clients fail loudly.
_TRANSIENT_CHAT_CLIENT_ERRORS: Final[tuple[type[BaseException], ...]] = (
    ChatClientException,
    asyncio.TimeoutError,
    OSError,
)


def _normalize_topic(topic: str) -> str:
    normalized = " ".join(topic.strip().split())
    if not normalized:
        raise ValueError("topic must not be empty.")
    return normalized


def _normalize_memory_text(memory: str) -> str:
    normalized = " ".join(memory.strip().split())
    if not normalized:
        raise ValueError("memory must not be empty.")
    return normalized


def _escape_markdown_line(line: str) -> str:
    """Escape a markdown line so it cannot be re-interpreted as a heading on a later read."""
    if line.lstrip().startswith(("#", "\\#")):
        return f"\\{line}"
    return line


def _unescape_markdown_line(line: str) -> str:
    """Reverse :func:`_escape_markdown_line` when reading persisted memory content."""
    leading_whitespace_length = len(line) - len(line.lstrip())
    body = line[leading_whitespace_length:]
    if body.startswith("\\#"):
        return f"{line[:leading_whitespace_length]}{body[1:]}"
    return line


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write text to ``path`` atomically via a sibling temp file plus :func:`os.replace`.

    A crash, OOM, or disk-full mid-write leaves the previous file (if any) intact instead of
    producing a truncated file that breaks every subsequent read.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        temp_path.write_text(text, encoding=encoding)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _slugify_topic(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_topic(topic).lower()).strip("-")
    return slug or "memory-topic"


def _timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    return current.replace(microsecond=0).isoformat()


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        dedupe_key = normalized.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(normalized)
    return deduped


def _trim_pointer_line(pointer_line: str, *, max_length: int) -> str:
    if len(pointer_line) <= max_length:
        return pointer_line
    if max_length <= 3:
        return pointer_line[:max_length]
    return f"{pointer_line[: max_length - 3].rstrip()}..."


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        fenced_lines = stripped.splitlines()
        if len(fenced_lines) >= 3:
            return "\n".join(fenced_lines[1:-1]).strip()
    return stripped


def _extract_keywords(messages: Sequence[Message]) -> set[str]:
    keywords: set[str] = set()
    for message in messages:
        keywords.update(match.group(0).lower() for match in _WORD_PATTERN.finditer(message.text))
    return keywords


def _select_recent_turn_messages(
    messages: Sequence[Message],
    *,
    turn_count: int,
    load_tool_turns: bool,
) -> list[Message]:
    if turn_count <= 0 or not messages:
        return []

    recent_messages = list(messages)
    spans = group_messages(recent_messages)
    if not spans:
        return []

    user_span_indices = [index for index, span in enumerate(spans) if span["kind"] == "user"]
    selected_span_start = user_span_indices[max(0, len(user_span_indices) - turn_count)] if user_span_indices else 0

    selected_messages: list[Message] = []
    for span in spans[selected_span_start:]:
        if not load_tool_turns and span["kind"] == "tool_call":
            continue
        start_index = int(span["start_index"])
        end_index = int(span["end_index"])
        selected_messages.extend(recent_messages[start_index : end_index + 1])
    return selected_messages


def _format_messages_for_memory_model(messages: Sequence[Message]) -> str:
    rendered_lines: list[str] = []
    for message in messages:
        text = message.text.strip()
        if not text:
            continue
        rendered_lines.append(f"{message.role.upper()}: {text}")
    return "\n\n".join(rendered_lines)


def _coerce_summary(summary: str, memories: Sequence[str]) -> str:
    normalized_summary = " ".join(summary.strip().split())
    if normalized_summary:
        return normalized_summary
    if not memories:
        return "No summary yet."
    if len(memories) == 1:
        return memories[0]
    return f"{memories[0]} {memories[1]}".strip()


def _default_state() -> dict[str, Any]:
    return {"last_consolidated_at": None, "sessions_since_consolidation": []}


def _format_search_results(results: Sequence[Mapping[str, Any]]) -> str:
    return json.dumps(list(results), ensure_ascii=False)


@experimental(feature_id=ExperimentalFeature.HARNESS)
class MemoryIndexEntry:
    """Represent one pointer entry written into ``MEMORY.md``."""

    topic: str
    slug: str
    summary: str
    updated_at: str
    __slots__ = ("slug", "summary", "topic", "updated_at")

    def __init__(self, topic: str, slug: str, summary: str, updated_at: str) -> None:
        """Initialize one memory-index entry.

        Args:
            topic: Human-readable topic name.
            slug: Stable topic filename stem.
            summary: Short summary used by the index line.
            updated_at: Last update timestamp for the topic.
        """
        self.topic = _normalize_topic(topic)
        self.slug = _slugify_topic(slug)
        self.summary = _coerce_summary(summary, [])
        self.updated_at = updated_at

    def to_dict(self) -> dict[str, str]:
        """Serialize the index entry for tool output.

        Returns:
            A JSON-compatible dict for the topic pointer entry.
        """
        return {
            "topic": self.topic,
            "slug": self.slug,
            "summary": self.summary,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw_entry: Mapping[str, Any]) -> MemoryIndexEntry:
        """Parse one index entry from JSON-compatible data.

        Args:
            raw_entry: Raw mapping loaded from structured data.

        Returns:
            The parsed index entry.

        Raises:
            ValueError: If any required field is missing or not a string.
        """
        required_fields = {"topic", "slug", "summary", "updated_at"}
        if not required_fields.issubset(raw_entry):
            raise ValueError("Memory index entry is missing required JSON fields.")
        topic = raw_entry["topic"]
        slug = raw_entry["slug"]
        summary = raw_entry["summary"]
        updated_at = raw_entry["updated_at"]
        if not all(isinstance(value, str) for value in (topic, slug, summary, updated_at)):
            raise ValueError("Memory index entry fields must all be strings.")
        return cls(topic=topic, slug=slug, summary=summary, updated_at=updated_at)

    @classmethod
    def from_topic_record(cls, record: MemoryTopicRecord) -> MemoryIndexEntry:
        """Create one index entry from a topic record.

        Args:
            record: The topic record to summarize into the index.

        Returns:
            The derived memory-index entry.
        """
        return cls(
            topic=record.topic,
            slug=record.slug,
            summary=_coerce_summary(record.summary, record.memories),
            updated_at=record.updated_at,
        )

    def to_pointer_line(self, *, max_length: int = DEFAULT_MEMORY_INDEX_LINE_LENGTH) -> str:
        """Render the one-line pointer stored in ``MEMORY.md``.

        Keyword Args:
            max_length: Maximum pointer-line length.

        Returns:
            One compact pointer line.
        """
        pointer_line = f"- [{self.topic}](topics/{self.slug}.md): {self.summary}"
        return _trim_pointer_line(pointer_line, max_length=max_length)

    def __eq__(self, other: object) -> bool:
        """Compare two index entries by value."""
        if not isinstance(other, MemoryIndexEntry):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return (
            "MemoryIndexEntry("
            f"topic={self.topic!r}, slug={self.slug!r}, summary={self.summary!r}, updated_at={self.updated_at!r})"
        )


@experimental(feature_id=ExperimentalFeature.HARNESS)
class MemoryTopicRecord:
    """Represent one topic memory markdown file."""

    topic: str
    slug: str
    summary: str
    memories: list[str]
    updated_at: str
    session_ids: list[str]
    __slots__ = ("memories", "session_ids", "slug", "summary", "topic", "updated_at")

    def __init__(
        self,
        *,
        topic: str,
        slug: str | None = None,
        summary: str,
        memories: Sequence[str],
        updated_at: str,
        session_ids: Sequence[str] | None = None,
    ) -> None:
        """Initialize one topic memory record.

        Keyword Args:
            topic: Human-readable topic name.
            slug: Optional stable filename stem override.
            summary: Short topic summary.
            memories: Durable memory bullets for the topic.
            updated_at: Last update timestamp.
            session_ids: Session IDs that contributed to this topic.
        """
        normalized_topic = _normalize_topic(topic)
        self.topic = normalized_topic
        self.slug = _slugify_topic(slug or normalized_topic)
        self.memories = _dedupe_strings(memories)
        self.summary = _coerce_summary(summary, self.memories)
        self.updated_at = updated_at
        self.session_ids = _dedupe_strings(session_ids or [])

    def to_dict(self) -> dict[str, Any]:
        """Serialize the topic record for tool output.

        Returns:
            A JSON-compatible dict for the topic record.
        """
        return {
            "topic": self.topic,
            "slug": self.slug,
            "summary": self.summary,
            "memories": list(self.memories),
            "updated_at": self.updated_at,
            "session_ids": list(self.session_ids),
        }

    @classmethod
    def from_dict(cls, raw_record: Mapping[str, Any]) -> MemoryTopicRecord:
        """Parse one topic record from structured data.

        Args:
            raw_record: Raw JSON-compatible mapping.

        Returns:
            The parsed topic record.

        Raises:
            ValueError: If the mapping does not match the expected schema.
        """
        required_fields = {"topic", "slug", "summary", "memories", "updated_at", "session_ids"}
        if not required_fields.issubset(raw_record):
            raise ValueError("Memory topic record is missing required JSON fields.")
        topic = raw_record["topic"]
        slug = raw_record["slug"]
        summary = raw_record["summary"]
        memories = raw_record["memories"]
        updated_at = raw_record["updated_at"]
        session_ids = raw_record["session_ids"]
        if not all(isinstance(value, str) for value in (topic, slug, summary, updated_at)):
            raise ValueError("Memory topic record string fields must all be strings.")
        if not isinstance(memories, list):
            raise ValueError("Memory topic record memories must be a list of strings.")
        memory_items: list[str] = []
        for memory in cast(list[object], memories):
            if not isinstance(memory, str):
                raise ValueError("Memory topic record memories must be a list of strings.")
            memory_items.append(memory)
        if not isinstance(session_ids, list):
            raise ValueError("Memory topic record session_ids must be a list of strings.")
        session_id_items: list[str] = []
        for session_id in cast(list[object], session_ids):
            if not isinstance(session_id, str):
                raise ValueError("Memory topic record session_ids must be a list of strings.")
            session_id_items.append(session_id)
        return cls(
            topic=topic,
            slug=slug,
            summary=summary,
            memories=memory_items,
            updated_at=updated_at,
            session_ids=session_id_items,
        )

    def to_markdown(self) -> str:
        """Render the topic record as the on-disk markdown file.

        Returns:
            The canonical markdown representation.
        """
        session_line = ", ".join(self.session_ids) if self.session_ids else "-"
        # Escape any heading-looking lines in the summary so a future read cannot mistake summary
        # content (or LLM-supplied consolidation output) for a section delimiter.
        escaped_summary_lines = [_escape_markdown_line(line) for line in self.summary.splitlines()]
        escaped_summary = "\n".join(escaped_summary_lines)
        memory_lines = [f"- {_escape_markdown_line(memory)}" for memory in self.memories] or [
            f"- {DEFAULT_MEMORY_NO_TOPICS_TEXT[2:]}"
        ]
        return "\n".join([
            f"# {self.topic}",
            "",
            f"Updated: {self.updated_at}",
            f"Sessions: {session_line}",
            "",
            "## Summary",
            escaped_summary,
            "",
            "## Memories",
            *memory_lines,
        ]).rstrip()

    @classmethod
    def from_markdown(cls, markdown: str, *, fallback_topic: str | None = None) -> MemoryTopicRecord:
        """Parse one topic record from the canonical markdown format.

        Args:
            markdown: The markdown file contents.

        Keyword Args:
            fallback_topic: Topic name to use when the markdown heading is missing.

        Returns:
            The parsed topic record.

        Raises:
            ValueError: If the markdown cannot be parsed into the expected format.
        """
        topic = fallback_topic
        updated_at = _timestamp()
        session_ids: list[str] = []
        summary_lines: list[str] = []
        memories: list[str] = []
        current_section: str | None = None

        for raw_line in markdown.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if stripped.startswith("# "):
                topic = stripped[2:].strip()
                current_section = None
                continue
            if stripped.startswith("Updated: "):
                updated_at = stripped.removeprefix("Updated: ").strip()
                continue
            if stripped.startswith("Sessions: "):
                raw_sessions = stripped.removeprefix("Sessions: ").strip()
                session_ids = (
                    []
                    if raw_sessions in {"", "-"}
                    else [item.strip() for item in raw_sessions.split(",") if item.strip()]
                )
                continue
            if stripped == "## Summary":
                current_section = "summary"
                continue
            if stripped == "## Memories":
                current_section = "memories"
                continue
            if current_section == "summary":
                if stripped:
                    summary_lines.append(_unescape_markdown_line(stripped))
                continue
            if current_section == "memories" and stripped.startswith("- "):
                memory_text = _unescape_markdown_line(stripped[2:].strip())
                if memory_text and memory_text != DEFAULT_MEMORY_NO_TOPICS_TEXT[2:]:
                    memories.append(memory_text)

        if topic is None:
            raise ValueError("Memory topic markdown is missing a '# <topic>' heading.")
        return cls(
            topic=topic,
            summary="\n".join(summary_lines).strip(),
            memories=memories,
            updated_at=updated_at,
            session_ids=session_ids,
        )

    def __eq__(self, other: object) -> bool:
        """Compare two topic records by value."""
        if not isinstance(other, MemoryTopicRecord):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return (
            "MemoryTopicRecord("
            f"topic={self.topic!r}, slug={self.slug!r}, summary={self.summary!r}, memories={self.memories!r}, "
            f"updated_at={self.updated_at!r}, session_ids={self.session_ids!r})"
        )


@experimental(feature_id=ExperimentalFeature.HARNESS)
class MemoryStore(ABC):
    """Abstract backing store for the memory harness."""

    def get_owner_id(self, session: AgentSession) -> str | None:
        """Return the logical owner ID for one session, if the store uses one."""
        del session
        return None

    def export_provider_state(self, session: AgentSession) -> dict[str, Any]:
        """Return the provider-scoped routing state needed to reopen storage.

        Args:
            session: The active session whose routing metadata should be exported.

        Returns:
            A JSON-serializable provider-state mapping.
        """
        del session
        return {}

    def import_provider_state(self, session: AgentSession, *, state: Mapping[str, Any]) -> None:
        """Apply provider-scoped routing state back onto a temporary session.

        Args:
            session: The temporary session receiving the routing metadata.

        Keyword Args:
            state: Provider-scoped state previously exported by ``export_provider_state``.
        """
        del session, state

    @abstractmethod
    def list_topics(self, session: AgentSession, *, source_id: str) -> list[MemoryTopicRecord]:
        """Return all topic memory files visible from the current owner."""

    @abstractmethod
    def get_topic(self, session: AgentSession, *, source_id: str, topic: str) -> MemoryTopicRecord:
        """Return one topic memory file by topic name or slug."""

    @abstractmethod
    def write_topic(self, session: AgentSession, record: MemoryTopicRecord, *, source_id: str) -> None:
        """Persist one topic memory file."""

    @abstractmethod
    def delete_topic(self, session: AgentSession, *, source_id: str, topic: str) -> None:
        """Delete one topic memory file."""

    @abstractmethod
    def rebuild_index(
        self,
        session: AgentSession,
        *,
        source_id: str,
        line_limit: int,
        line_length: int,
    ) -> list[MemoryIndexEntry]:
        """Rebuild ``MEMORY.md`` from the current topic files and return its entries."""

    @abstractmethod
    def get_index_text(
        self,
        session: AgentSession,
        *,
        source_id: str,
        line_limit: int,
        line_length: int,
        index_entries: Sequence[MemoryIndexEntry] | None = None,
    ) -> str:
        """Return the current ``MEMORY.md`` text, rebuilding it when needed."""

    @abstractmethod
    def read_state(self, session: AgentSession, *, source_id: str) -> dict[str, Any]:
        """Return the maintenance state for the current owner."""

    @abstractmethod
    def write_state(self, session: AgentSession, state: Mapping[str, Any], *, source_id: str) -> None:
        """Persist the maintenance state for the current owner."""

    @abstractmethod
    def get_transcripts_directory(self, session: AgentSession, *, source_id: str) -> Path:
        """Return the owner-level transcript archive directory."""

    @abstractmethod
    def search_transcripts(
        self,
        session: AgentSession,
        *,
        source_id: str,
        query: str,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search the raw transcript archive for matching text snippets."""


@experimental(feature_id=ExperimentalFeature.HARNESS)
class MemoryFileStore(MemoryStore):
    """Store memory files under ``MEMORY.md``, ``topics/``, and ``transcripts/``."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        kind: str = "memory",
        owner_prefix: str = "",
        owner_state_key: str,
        index_file_name: str = DEFAULT_MEMORY_INDEX_FILE_NAME,
        topics_directory_name: str = DEFAULT_MEMORY_TOPICS_DIRECTORY_NAME,
        transcripts_directory_name: str = DEFAULT_MEMORY_TRANSCRIPTS_DIRECTORY_NAME,
        state_file_name: str = DEFAULT_MEMORY_STATE_FILE_NAME,
        dumps: JsonDumps | None = None,
        loads: JsonLoads | None = None,
    ) -> None:
        """Initialize the file-backed memory store.

        Args:
            base_path: Root storage directory.

        Keyword Args:
            kind: Storage bucket name under each owner directory.
            owner_prefix: Optional prefix applied to the resolved owner ID.
            owner_state_key: Session-state key holding the logical owner ID.
            index_file_name: File name for the root memory index.
            topics_directory_name: Directory name for topic markdown files.
            transcripts_directory_name: Directory name for transcript history files.
            state_file_name: File name for maintenance state JSON.
            dumps: Callable used to serialize maintenance state JSON.
            loads: Callable used to deserialize maintenance state JSON.
        """
        self.base_path = Path(base_path)
        self._base_root = self.base_path.resolve()
        self.kind = kind
        self.owner_prefix = owner_prefix
        self.owner_state_key = owner_state_key
        self.index_file_name = index_file_name
        self.topics_directory_name = topics_directory_name
        self.transcripts_directory_name = transcripts_directory_name
        self.state_file_name = state_file_name
        self.dumps = dumps or json.dumps
        self.loads = loads or json.loads

    def _get_owner_id(self, session: AgentSession) -> str:
        owner_value = session.state.get(self.owner_state_key)
        if owner_value is None:
            raise RuntimeError(
                f"MemoryFileStore requires session.state[{self.owner_state_key!r}] to be set for file-backed storage."
            )
        owner_id = str(owner_value)
        owner_path = Path(owner_id)
        if owner_path.is_absolute() or any(part == ".." for part in owner_path.parts):
            raise ValueError("Memory owner ID must not contain path traversal segments.")
        return owner_id

    def get_owner_id(self, session: AgentSession) -> str | None:
        """Return the logical owner ID for one session."""
        return self._get_owner_id(session)

    def export_provider_state(self, session: AgentSession) -> dict[str, Any]:
        """Return the routing metadata needed to reopen this owner's memory root."""
        owner_value = session.state.get(self.owner_state_key)
        if owner_value is None:
            raise RuntimeError(
                f"MemoryFileStore requires session.state[{self.owner_state_key!r}] to be set for file-backed storage."
            )
        return {self.owner_state_key: owner_value}

    def import_provider_state(self, session: AgentSession, *, state: Mapping[str, Any]) -> None:
        """Apply the persisted owner routing metadata to a temporary session."""
        owner_value = state.get(self.owner_state_key)
        if owner_value is None:
            raise RuntimeError(
                f"MemoryFileStore requires provider state[{self.owner_state_key!r}] to be set for file-backed storage."
            )
        session.state[self.owner_state_key] = owner_value

    @staticmethod
    def _encode_path_component(value: str) -> str:
        encoded_value = urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
        return encoded_value or "_"

    def _get_memory_root(self, session: AgentSession, *, source_id: str) -> Path:
        owner_component = self._encode_path_component(f"{self.owner_prefix}{self._get_owner_id(session)}")
        source_component = self._encode_path_component(source_id)
        memory_root = (self._base_root / source_component / owner_component / self.kind).resolve()
        if not memory_root.is_relative_to(self._base_root):
            raise ValueError("Memory storage path escaped base_path.")
        return memory_root

    def _get_topics_directory(self, session: AgentSession, *, source_id: str) -> Path:
        return self._get_memory_root(session, source_id=source_id) / self.topics_directory_name

    def get_transcripts_directory(self, session: AgentSession, *, source_id: str) -> Path:
        """Return the owner-level transcript archive directory."""
        return self._get_memory_root(session, source_id=source_id) / self.transcripts_directory_name

    def _get_index_path(self, session: AgentSession, *, source_id: str) -> Path:
        return self._get_memory_root(session, source_id=source_id) / self.index_file_name

    def _get_state_path(self, session: AgentSession, *, source_id: str) -> Path:
        return self._get_memory_root(session, source_id=source_id) / self.state_file_name

    def _topic_path(self, session: AgentSession, *, source_id: str, topic: str) -> Path:
        return self._get_topics_directory(session, source_id=source_id) / f"{_slugify_topic(topic)}.md"

    @staticmethod
    def _serialize_json(value: object, *, dumps: JsonDumps) -> str:
        serialized = dumps(value)
        return serialized.decode("utf-8") if isinstance(serialized, bytes) else serialized

    @staticmethod
    def _decode_transcript_session_id(file_path: Path) -> str | None:
        file_stem = file_path.stem
        if file_stem == FileHistoryProvider.DEFAULT_SESSION_FILE_STEM:
            return None
        if not file_stem.startswith(_FILE_HISTORY_ENCODED_SESSION_PREFIX):
            return file_stem
        encoded_value = file_stem[len(_FILE_HISTORY_ENCODED_SESSION_PREFIX) :]
        padded_value = encoded_value + ("=" * (-len(encoded_value) % 4))
        return urlsafe_b64decode(padded_value.encode("ascii")).decode("utf-8")

    def list_topics(self, session: AgentSession, *, source_id: str) -> list[MemoryTopicRecord]:
        """Return all topic memory files visible from the current owner."""
        topics: list[MemoryTopicRecord] = []
        topics_directory = self._get_topics_directory(session, source_id=source_id)
        if not topics_directory.exists():
            return topics
        for topic_path in sorted(topics_directory.glob("*.md")):
            if not topic_path.is_file():
                continue
            record = MemoryTopicRecord.from_markdown(
                topic_path.read_text(encoding="utf-8"),
                fallback_topic=topic_path.stem.replace("-", " "),
            )
            topics.append(record)
        return sorted(topics, key=lambda record: (record.topic.lower(), record.updated_at))

    def get_topic(self, session: AgentSession, *, source_id: str, topic: str) -> MemoryTopicRecord:
        """Return one topic memory file by topic name or slug."""
        topic_path = self._topic_path(session, source_id=source_id, topic=topic)
        if not topic_path.exists():
            raise FileNotFoundError(f"No memory topic named '{topic}' was found for this owner.")
        return MemoryTopicRecord.from_markdown(topic_path.read_text(encoding="utf-8"), fallback_topic=topic)

    def write_topic(self, session: AgentSession, record: MemoryTopicRecord, *, source_id: str) -> None:
        """Persist one topic memory file."""
        topic_path = self._topic_path(session, source_id=source_id, topic=record.slug)
        _atomic_write_text(topic_path, f"{record.to_markdown()}\n")

    def delete_topic(self, session: AgentSession, *, source_id: str, topic: str) -> None:
        """Delete one topic memory file."""
        topic_path = self._topic_path(session, source_id=source_id, topic=topic)
        if not topic_path.exists():
            raise FileNotFoundError(f"No memory topic named '{topic}' was found for this owner.")
        topic_path.unlink()

    def rebuild_index(
        self,
        session: AgentSession,
        *,
        source_id: str,
        line_limit: int,
        line_length: int,
    ) -> list[MemoryIndexEntry]:
        """Rebuild ``MEMORY.md`` from the current topic files and return its entries."""
        topics = self.list_topics(session, source_id=source_id)
        entries = [MemoryIndexEntry.from_topic_record(topic) for topic in topics]
        pointer_lines = [entry.to_pointer_line(max_length=line_length) for entry in entries[:line_limit]]
        index_lines = [
            DEFAULT_MEMORY_INDEX_HEADER,
            "",
            *(pointer_lines if pointer_lines else [DEFAULT_MEMORY_NO_TOPICS_TEXT]),
        ]
        index_text = "\n".join(index_lines).rstrip()
        index_path = self._get_index_path(session, source_id=source_id)
        index_file_text = f"{index_text}\n"
        if not index_path.exists() or index_path.read_text(encoding="utf-8") != index_file_text:
            _atomic_write_text(index_path, index_file_text)
        return entries[:line_limit]

    def get_index_text(
        self,
        session: AgentSession,
        *,
        source_id: str,
        line_limit: int,
        line_length: int,
        index_entries: Sequence[MemoryIndexEntry] | None = None,
    ) -> str:
        """Return the current ``MEMORY.md`` text, rebuilding it when needed."""
        if index_entries is None:
            self.rebuild_index(session, source_id=source_id, line_limit=line_limit, line_length=line_length)
        else:
            pointer_lines = [entry.to_pointer_line(max_length=line_length) for entry in index_entries[:line_limit]]
            index_lines = [
                DEFAULT_MEMORY_INDEX_HEADER,
                "",
                *(pointer_lines if pointer_lines else [DEFAULT_MEMORY_NO_TOPICS_TEXT]),
            ]
            index_text = "\n".join(index_lines).rstrip()
            index_path = self._get_index_path(session, source_id=source_id)
            index_file_text = f"{index_text}\n"
            if not index_path.exists() or index_path.read_text(encoding="utf-8") != index_file_text:
                _atomic_write_text(index_path, index_file_text)
        return self._get_index_path(session, source_id=source_id).read_text(encoding="utf-8").strip()

    def read_state(self, session: AgentSession, *, source_id: str) -> dict[str, Any]:
        """Return the maintenance state for the current owner."""
        state_path = self._get_state_path(session, source_id=source_id)
        if not state_path.exists():
            return _default_state()
        raw_state = self.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(raw_state, dict):
            raise ValueError("Memory state file must contain a JSON object.")
        state = {**_default_state(), **cast(dict[str, Any], raw_state)}
        if not isinstance(state.get("sessions_since_consolidation"), list):
            state["sessions_since_consolidation"] = []
        if not isinstance(state.get("last_consolidated_at"), (str, type(None))):
            state["last_consolidated_at"] = None
        return state

    def write_state(self, session: AgentSession, state: Mapping[str, Any], *, source_id: str) -> None:
        """Persist the maintenance state for the current owner."""
        state_path = self._get_state_path(session, source_id=source_id)
        _atomic_write_text(state_path, f"{self._serialize_json(dict(state), dumps=self.dumps)}\n")

    def search_transcripts(
        self,
        session: AgentSession,
        *,
        source_id: str,
        query: str,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search the raw transcript archive for matching text snippets."""
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty.")
        query_casefold = normalized_query.casefold()
        transcripts_directory = self.get_transcripts_directory(session, source_id=source_id)
        if not transcripts_directory.exists():
            return []
        transcript_files = sorted(transcripts_directory.glob("*.jsonl"))
        results: list[dict[str, Any]] = []
        for transcript_file in transcript_files:
            decoded_session_id = self._decode_transcript_session_id(transcript_file)
            if session_id is not None and decoded_session_id != session_id:
                continue
            with transcript_file.open(encoding="utf-8") as file_handle:
                for line_number, line in enumerate(file_handle, start=1):
                    serialized = line.strip()
                    if not serialized:
                        continue
                    raw_payload = self.loads(serialized)
                    if not isinstance(raw_payload, Mapping):
                        continue
                    message = Message.from_dict(dict(cast(Mapping[str, Any], raw_payload)))
                    text = message.text.strip()
                    if not text or query_casefold not in text.casefold():
                        continue
                    results.append({
                        "session_id": decoded_session_id,
                        "line_number": line_number,
                        "role": message.role,
                        "text": text,
                    })
                    if len(results) >= limit:
                        return results
        return results


@experimental(feature_id=ExperimentalFeature.HARNESS)
class MemoryContextProvider(HistoryProvider):
    """Inject ``MEMORY.md``, topic memory tools, and transcript-backed extraction."""

    _LOCKS_GUARD: ClassVar[threading.Lock] = threading.Lock()
    _STORE_LOCKS_BY_LOOP: ClassVar[
        weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, weakref.WeakKeyDictionary[MemoryStore, dict[str, asyncio.Lock]]
        ]
    ] = weakref.WeakKeyDictionary()

    def __init__(
        self,
        recent_turns: int = 0,
        load_tool_turns: bool = True,
        *,
        store: MemoryStore,
        source_id: str = DEFAULT_MEMORY_SOURCE_ID,
        context_prompt: str | None = None,
        index_line_limit: int = DEFAULT_MEMORY_INDEX_LINE_LIMIT,
        index_line_length: int = DEFAULT_MEMORY_INDEX_LINE_LENGTH,
        selection_limit: int = DEFAULT_MEMORY_SELECTION_LIMIT,
        max_extractions: int = DEFAULT_MEMORY_MAX_EXTRACTIONS,
        consolidation_interval: timedelta = DEFAULT_MEMORY_CONSOLIDATION_INTERVAL,
        consolidation_min_sessions: int = DEFAULT_MEMORY_CONSOLIDATION_MIN_SESSIONS,
        extraction_prompt: str = DEFAULT_MEMORY_EXTRACTION_PROMPT,
        consolidation_prompt: str = DEFAULT_MEMORY_CONSOLIDATION_PROMPT,
        consolidation_client: SupportsChatGetResponse[Any] | None = None,
        history_message_filter: HistoryMessageFilter | None = None,
        history_dumps: JsonDumps | None = None,
        history_loads: JsonLoads | None = None,
    ) -> None:
        """Initialize the memory provider.

        Keyword Args:
            store: Backing store used for the index, topics, and transcript root.
            source_id: Unique source ID for the provider.
            context_prompt: Optional context prompt override.
            index_line_limit: Maximum number of topic pointers kept in ``MEMORY.md``.
            index_line_length: Maximum length of one pointer line in ``MEMORY.md``.
            selection_limit: Maximum number of topic files to auto-load each turn.
            recent_turns: Number of most recent transcript turns to inject into context alongside
                durable memory. A turn starts at a user message and includes the following messages.
            load_tool_turns: Whether the recent-turn window should include grouped tool-call
                turns, including reasoning prefixes and tool result messages.
            max_extractions: Maximum number of extracted memory items per turn.
            consolidation_interval: Minimum time between automatic consolidation runs.
            consolidation_min_sessions: Number of sessions required before consolidation runs.
            extraction_prompt: Prompt used for automated memory extraction.
            consolidation_prompt: Prompt used for automated memory consolidation.
            consolidation_client: Optional chat client override used only for consolidation so the
                cleanup pass can use a cheaper or faster model than the main agent client.
            history_message_filter: Optional callback that can rewrite or drop messages before transcript save.
            history_dumps: Callable used to serialize transcript JSONL.
            history_loads: Callable used to deserialize transcript JSONL and state JSON.
        """
        super().__init__(
            source_id=source_id,
            load_messages=True,
            store_inputs=True,
            store_context_messages=False,
            store_outputs=True,
        )
        if index_line_limit <= 0:
            raise ValueError("index_line_limit must be greater than 0.")
        if index_line_length <= 0:
            raise ValueError("index_line_length must be greater than 0.")
        if selection_limit < 0:
            raise ValueError("selection_limit must be greater than or equal to 0.")
        if recent_turns < 0:
            raise ValueError("recent_turns must be greater than or equal to 0.")
        if max_extractions < 0:
            raise ValueError("max_extractions must be greater than or equal to 0.")
        if consolidation_min_sessions <= 0:
            raise ValueError("consolidation_min_sessions must be greater than 0.")

        self.store = store
        self.context_prompt = context_prompt or DEFAULT_MEMORY_CONTEXT_PROMPT
        self.index_line_limit = index_line_limit
        self.index_line_length = index_line_length
        self.selection_limit = selection_limit
        self.recent_turns = recent_turns
        self.load_tool_turns = load_tool_turns
        self.max_extractions = max_extractions
        self.consolidation_interval = consolidation_interval
        self.consolidation_min_sessions = consolidation_min_sessions
        self.extraction_prompt = extraction_prompt
        self.consolidation_prompt = consolidation_prompt
        self.consolidation_client = consolidation_client
        self.history_message_filter = history_message_filter
        self.history_dumps = history_dumps
        self.history_loads = history_loads

    def _store_async_lock(self, session: AgentSession, *, kind: str, key: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        owner_id = self.store.get_owner_id(session) or ""
        lock_key = f"{self.source_id}:{owner_id}:{kind}:{key}"
        with self._LOCKS_GUARD:
            store_locks_by_loop: weakref.WeakKeyDictionary[MemoryStore, dict[str, asyncio.Lock]] | None = (
                self._STORE_LOCKS_BY_LOOP.get(loop)
            )
            if store_locks_by_loop is None:
                store_locks_by_loop = weakref.WeakKeyDictionary[MemoryStore, dict[str, asyncio.Lock]]()
                self._STORE_LOCKS_BY_LOOP[loop] = store_locks_by_loop
            store_locks = store_locks_by_loop.get(self.store)
            if store_locks is None:
                store_locks = {}
                store_locks_by_loop[self.store] = store_locks
            store_lock = store_locks.get(lock_key)
            if store_lock is None:
                store_lock = asyncio.Lock()
                store_locks[lock_key] = store_lock
            return store_lock

    def _topic_async_lock(self, session: AgentSession, topic: str) -> asyncio.Lock:
        return self._store_async_lock(session, kind="topic", key=_slugify_topic(topic))

    def _state_async_lock(self, session: AgentSession) -> asyncio.Lock:
        return self._store_async_lock(session, kind="state", key="maintenance")

    def _create_history_provider(self, session: AgentSession) -> FileHistoryProvider:
        return FileHistoryProvider(
            self.store.get_transcripts_directory(session, source_id=self.source_id),
            source_id=self.source_id,
            load_messages=True,
            store_inputs=self.store_inputs,
            store_context_messages=self.store_context_messages,
            store_context_from=self.store_context_from,
            store_outputs=self.store_outputs,
            dumps=self.history_dumps,
            loads=self.history_loads,
        )

    @staticmethod
    def _chat_client(
        agent: Any,
        *,
        override: SupportsChatGetResponse[Any] | None = None,
    ) -> SupportsChatGetResponse[Any] | None:
        if override is not None:
            return override
        client: object = getattr(agent, "client", None)
        if isinstance(client, SupportsChatGetResponse):
            return cast(SupportsChatGetResponse[Any], client)  # type: ignore[redundant-cast]
        return None

    @staticmethod
    def _topic_score(entry: MemoryIndexEntry, keywords: set[str]) -> int:
        topic_keywords = {match.group(0).lower() for match in _WORD_PATTERN.finditer(f"{entry.topic} {entry.summary}")}
        return len(topic_keywords & keywords)

    def _select_topics(
        self,
        *,
        entries: Sequence[MemoryIndexEntry],
        input_messages: Sequence[Message],
    ) -> list[MemoryIndexEntry]:
        if self.selection_limit == 0 or not entries:
            return []
        keywords = _extract_keywords(input_messages)
        if not keywords:
            return []
        scored_entries = sorted(
            ((self._topic_score(entry, keywords), entry) for entry in entries),
            key=lambda item: (-item[0], item[1].topic.lower()),
        )
        return [entry for score, entry in scored_entries[: self.selection_limit] if score > 0]

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        """Load transcript messages for one session from the archive.

        Args:
            session_id: The transcript session ID to load.

        Keyword Args:
            state: Provider-scoped state used to resolve the owner directory.
            **kwargs: Additional extensibility arguments.

        Returns:
            The stored transcript messages for the requested session.
        """
        del kwargs
        if state is None:
            return []
        session = AgentSession(session_id=session_id or FileHistoryProvider.DEFAULT_SESSION_FILE_STEM)
        self.store.import_provider_state(session, state=state)
        # Skip provider construction (which would mkdir the transcripts directory) when nothing
        # has been written yet; pure read paths should not have side effects on disk.
        if not self.store.get_transcripts_directory(session, source_id=self.source_id).exists():
            return []
        return await self._create_history_provider(session).get_messages(session_id, state=state)

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Persist transcript messages for one session.

        Args:
            session_id: The transcript session ID to write.
            messages: Transcript messages to append.

        Keyword Args:
            state: Provider-scoped state used to resolve the owner directory.
            **kwargs: Additional extensibility arguments.
        """
        del kwargs
        if state is None or not messages:
            return
        session = AgentSession(session_id=session_id or FileHistoryProvider.DEFAULT_SESSION_FILE_STEM)
        self.store.import_provider_state(session, state=state)
        filtered_messages: list[Message] = []
        for message in messages:
            if self.history_message_filter is None:
                filtered_messages.append(message)
                continue
            filtered_message = self.history_message_filter(message)
            if filtered_message is not None:
                filtered_messages.append(filtered_message)
        if not filtered_messages:
            return
        transcripts_directory = self.store.get_transcripts_directory(session, source_id=self.source_id)
        transcripts_directory.mkdir(parents=True, exist_ok=True)
        await self._create_history_provider(session).save_messages(session_id, filtered_messages, state=state)

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject ``MEMORY.md`` and selected topic files before the model runs."""
        state.clear()
        state.update(self.store.export_provider_state(session))

        index_entries = self.store.rebuild_index(
            session,
            source_id=self.source_id,
            line_limit=self.index_line_limit,
            line_length=self.index_line_length,
        )
        index_text = self.store.get_index_text(
            session,
            source_id=self.source_id,
            line_limit=self.index_line_limit,
            line_length=self.index_line_length,
            index_entries=index_entries,
        )
        recent_history_messages = _select_recent_turn_messages(
            await self.get_messages(context.session_id, state=state),
            turn_count=self.recent_turns,
            load_tool_turns=self.load_tool_turns,
        )
        selected_entries = self._select_topics(entries=index_entries, input_messages=context.input_messages)
        selected_topics = [
            self.store.get_topic(session, source_id=self.source_id, topic=entry.slug) for entry in selected_entries
        ]

        @tool(name="list_memory_topics", approval_mode="never_require")
        def list_memory_topics() -> str:
            """List the current topic pointers recorded in ``MEMORY.md``."""
            current_entries = self.store.rebuild_index(
                session,
                source_id=self.source_id,
                line_limit=self.index_line_limit,
                line_length=self.index_line_length,
            )
            return json.dumps([entry.to_dict() for entry in current_entries], ensure_ascii=False)

        @tool(name="read_memory_topic", approval_mode="never_require")
        def read_memory_topic(topic: str) -> str:
            """Read one topic memory file by topic name or slug."""
            return self.store.get_topic(
                session,
                source_id=self.source_id,
                topic=_normalize_topic(topic),
            ).to_markdown()

        @tool(name="write_memory", approval_mode="never_require")
        async def write_memory(topic: str, memory: str) -> str:
            """Add one durable memory line to a topic file."""
            updated_record = await self._merge_memory(
                session=session,
                topic=topic,
                memory=memory,
                now=datetime.now(timezone.utc).replace(microsecond=0),
            )
            self.store.rebuild_index(
                session,
                source_id=self.source_id,
                line_limit=self.index_line_limit,
                line_length=self.index_line_length,
            )
            return json.dumps(updated_record.to_dict(), ensure_ascii=False)

        @tool(name="delete_memory_topic", approval_mode="never_require")
        async def delete_memory_topic(topic: str) -> str:
            """Delete one topic memory file by topic name or slug."""
            normalized_topic = _normalize_topic(topic)
            async with self._topic_async_lock(session, normalized_topic):
                self.store.delete_topic(session, source_id=self.source_id, topic=normalized_topic)
                self.store.rebuild_index(
                    session,
                    source_id=self.source_id,
                    line_limit=self.index_line_limit,
                    line_length=self.index_line_length,
                )
            return f"Deleted memory topic '{normalized_topic}'."

        @tool(name="search_memory_transcripts", approval_mode="never_require")
        def search_memory_transcripts(query: str, session_id: str | None = None, limit: int = 20) -> str:
            """Search the raw transcript archive for matching text snippets."""
            results = self.store.search_transcripts(
                session,
                source_id=self.source_id,
                query=query,
                session_id=session_id,
                limit=limit,
            )
            return _format_search_results(results)

        @tool(name="consolidate_memories", approval_mode="never_require")
        async def consolidate_memories() -> str:
            """Force an immediate consolidation pass across all topic files."""
            consolidated_count = await self._run_consolidation(
                client=self._chat_client(agent, override=self.consolidation_client),
                session=session,
                force=True,
                now=datetime.now(timezone.utc).replace(microsecond=0),
            )
            return json.dumps({"consolidated_topics": consolidated_count}, ensure_ascii=False)

        loaded_topic_blocks = [
            f"### topics/{record.slug}.md\n{record.to_markdown()}" for record in selected_topics
        ] or ["- none auto-loaded for this turn"]
        loaded_topics_text = "\n\n".join(loaded_topic_blocks)
        context.extend_tools(
            self.source_id,
            [
                list_memory_topics,
                read_memory_topic,
                write_memory,
                delete_memory_topic,
                search_memory_transcripts,
                consolidate_memories,
            ],
        )
        context.extend_instructions(
            self.source_id,
            [
                "Use MEMORY.md as the always-loaded table of contents for durable memory.",
                ("Use the loaded topic files when they are relevant, but do not assume every topic file was loaded."),
                (
                    "Use loaded recent transcript turns for short-term continuity when they are present, "
                    "and use topic files for durable memory."
                ),
                (
                    "Recent transcript loading can omit grouped tool-call turns, so use transcript search "
                    "only when exact raw tool chatter is needed."
                ),
                "Use write_memory to save durable facts, decisions, or preferences into a topic file.",
                "Use read_memory_topic to inspect or correct a specific topic file before editing it.",
                (
                    "Use search_memory_transcripts only when raw historical detail is necessary, "
                    "because it searches the raw archive."
                ),
                "Use consolidate_memories only when the user asks to rebuild or clean up memory explicitly.",
            ],
        )
        if recent_history_messages:
            context.extend_messages(self.source_id, recent_history_messages)
        context.extend_messages(
            self.source_id,
            [
                Message(
                    role="user",
                    contents=[
                        (
                            f"{self.context_prompt}\n\n"
                            "### MEMORY.md\n"
                            f"{index_text}\n\n"
                            "### Auto-loaded topic files\n"
                            f"{loaded_topics_text}"
                        )
                    ],
                )
            ],
        )

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Persist transcripts, extract memories, and consolidate when needed."""
        state.clear()
        state.update(self.store.export_provider_state(session))
        messages_to_store: list[Message] = []
        messages_to_store.extend(self._get_context_messages_to_store(context))
        if self.store_inputs:
            messages_to_store.extend(context.input_messages)
        if self.store_outputs and context.response and context.response.messages:
            messages_to_store.extend(context.response.messages)
        if messages_to_store:
            await self.save_messages(session.session_id, messages_to_store, state=state)

        current_time = datetime.now(timezone.utc).replace(microsecond=0)
        async with self._state_async_lock(session):
            maintenance_state = self.store.read_state(session, source_id=self.source_id)
            session_ids_since_consolidation = cast(list[str], maintenance_state["sessions_since_consolidation"])
            if session.session_id not in session_ids_since_consolidation:
                session_ids_since_consolidation.append(session.session_id)
            maintenance_state["sessions_since_consolidation"] = session_ids_since_consolidation
            self.store.write_state(session, maintenance_state, source_id=self.source_id)

        extracted_topics = await self._extract_memories(
            client=self._chat_client(agent),
            session=session,
            context=context,
            now=current_time,
        )
        if extracted_topics:
            self.store.rebuild_index(
                session,
                source_id=self.source_id,
                line_limit=self.index_line_limit,
                line_length=self.index_line_length,
            )

        await self._run_consolidation(
            client=self._chat_client(agent, override=self.consolidation_client),
            session=session,
            force=False,
            now=current_time,
        )

    async def _extract_memories(
        self,
        *,
        client: SupportsChatGetResponse[Any] | None,
        session: AgentSession,
        context: SessionContext,
        now: datetime,
    ) -> list[MemoryTopicRecord]:
        if client is None or self.max_extractions == 0 or context.response is None or not context.response.messages:
            return []
        transcript_delta = _format_messages_for_memory_model([*context.input_messages, *context.response.messages])
        if not transcript_delta:
            return []

        try:
            extraction_response: ChatResponse[Any] = await client.get_response(
                [
                    Message(role="system", contents=[self.extraction_prompt]),
                    Message(role="user", contents=[transcript_delta]),
                ],
                stream=False,
            )
        except _TRANSIENT_CHAT_CLIENT_ERRORS as exc:
            LOGGER.warning("Skipping memory extraction: extractor call failed (%s).", exc)
            return []

        extracted_text = extraction_response.text.strip() if extraction_response.text else ""
        if not extracted_text:
            return []
        try:
            payload: object = json.loads(_extract_json_text(extracted_text))
        except (TypeError, ValueError) as exc:
            LOGGER.warning("Skipping memory extraction: extractor returned invalid JSON (%s).", exc)
            return []

        raw_items: object = (
            cast(Mapping[str, object], payload).get("memories") if isinstance(payload, Mapping) else payload
        )
        if not isinstance(raw_items, list):
            LOGGER.warning(
                "Skipping memory extraction: 'memories' is not a list (payload preview: %r).",
                _payload_preview(extracted_text),
            )
            return []

        updated_records: list[MemoryTopicRecord] = []
        for raw_item in cast(list[object], raw_items)[: self.max_extractions]:
            if not isinstance(raw_item, Mapping):
                LOGGER.warning(
                    "Skipping memory item: not a JSON object (item preview: %r).",
                    _payload_preview(repr(raw_item)),
                )
                continue
            item = cast(Mapping[str, object], raw_item)
            raw_topic = item.get("topic")
            raw_memory = item.get("memory")
            if not isinstance(raw_topic, str) or not isinstance(raw_memory, str):
                LOGGER.warning(
                    "Skipping memory item: missing 'topic' or 'memory' string (item preview: %r).",
                    _payload_preview(repr(item)),
                )
                continue
            try:
                updated_record = await self._merge_memory(
                    session=session,
                    topic=raw_topic,
                    memory=raw_memory,
                    now=now,
                )
            except ValueError:
                continue
            updated_records.append(updated_record)
        return updated_records

    async def _merge_memory(
        self,
        *,
        session: AgentSession,
        topic: str,
        memory: str,
        now: datetime,
    ) -> MemoryTopicRecord:
        normalized_topic = _normalize_topic(topic)
        normalized_memory = _normalize_memory_text(memory)
        async with self._topic_async_lock(session, normalized_topic):
            try:
                existing_record = self.store.get_topic(session, source_id=self.source_id, topic=normalized_topic)
            except FileNotFoundError:
                updated_record = MemoryTopicRecord(
                    topic=normalized_topic,
                    summary=normalized_memory,
                    memories=[normalized_memory],
                    updated_at=_timestamp(now),
                    session_ids=[session.session_id],
                )
            else:
                updated_record = MemoryTopicRecord(
                    topic=existing_record.topic,
                    slug=existing_record.slug,
                    summary=existing_record.summary,
                    memories=[*existing_record.memories, normalized_memory],
                    updated_at=_timestamp(now),
                    session_ids=[*existing_record.session_ids, session.session_id],
                )
            self.store.write_topic(session, updated_record, source_id=self.source_id)
            return updated_record

    async def _run_consolidation(
        self,
        *,
        client: SupportsChatGetResponse[Any] | None,
        session: AgentSession,
        force: bool,
        now: datetime,
    ) -> int:
        # Read maintenance state and the topic list under the state lock, then release it before
        # making LLM calls so concurrent before/after_run invocations don't have to wait through
        # multi-second consolidation calls.
        async with self._state_async_lock(session):
            maintenance_state = self.store.read_state(session, source_id=self.source_id)
            if not force and not self._should_consolidate(maintenance_state, now=now):
                return 0
            topic_records = self.store.list_topics(session, source_id=self.source_id)
            if not topic_records:
                maintenance_state["last_consolidated_at"] = _timestamp(now)
                maintenance_state["sessions_since_consolidation"] = []
                self.store.write_state(session, maintenance_state, source_id=self.source_id)
                return 0

        success_count = 0
        for record in topic_records:
            async with self._topic_async_lock(session, record.slug):
                try:
                    current_record = self.store.get_topic(session, source_id=self.source_id, topic=record.slug)
                except FileNotFoundError:
                    continue
                consolidated_record, succeeded = await self._consolidate_topic(
                    client=client, record=current_record, now=now
                )
                if succeeded:
                    self.store.write_topic(session, consolidated_record, source_id=self.source_id)
                    success_count += 1

        # Only advance the maintenance window if at least one topic actually consolidated. If every
        # topic call hit a transient error we keep the prior `last_consolidated_at` and the queued
        # session IDs so the next after_run will retry instead of silently sliding the window.
        if success_count > 0:
            async with self._state_async_lock(session):
                maintenance_state = self.store.read_state(session, source_id=self.source_id)
                maintenance_state["last_consolidated_at"] = _timestamp(now)
                maintenance_state["sessions_since_consolidation"] = []
                self.store.write_state(session, maintenance_state, source_id=self.source_id)
                self.store.rebuild_index(
                    session,
                    source_id=self.source_id,
                    line_limit=self.index_line_limit,
                    line_length=self.index_line_length,
                )
        return success_count

    def _should_consolidate(self, state: Mapping[str, Any], *, now: datetime) -> bool:
        session_ids: object = state.get("sessions_since_consolidation")
        if not isinstance(session_ids, list) or len(cast(list[object], session_ids)) < self.consolidation_min_sessions:
            return False
        last_consolidated_at: object = state.get("last_consolidated_at")
        if last_consolidated_at is None:
            return True
        if not isinstance(last_consolidated_at, str):
            return False
        try:
            parsed_timestamp = datetime.fromisoformat(last_consolidated_at)
        except ValueError:
            return True
        if parsed_timestamp.tzinfo is None:
            parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
        return now - parsed_timestamp >= self.consolidation_interval

    async def _consolidate_topic(
        self,
        *,
        client: SupportsChatGetResponse[Any] | None,
        record: MemoryTopicRecord,
        now: datetime,
    ) -> tuple[MemoryTopicRecord, bool]:
        """Return the consolidated record and a flag indicating whether consolidation succeeded.

        ``succeeded`` is False when the LLM call raises a transient error or returns malformed
        output. The caller uses this flag to decide whether to overwrite the on-disk record and
        whether to advance the maintenance window — preventing transient failures from silently
        sliding the consolidation cadence forward.
        """
        if client is None:
            return (
                MemoryTopicRecord(
                    topic=record.topic,
                    slug=record.slug,
                    summary=_coerce_summary(record.summary, record.memories),
                    memories=_dedupe_strings(record.memories),
                    updated_at=_timestamp(now),
                    session_ids=record.session_ids,
                ),
                True,
            )

        try:
            consolidation_response: ChatResponse[Any] = await client.get_response(
                [
                    Message(role="system", contents=[self.consolidation_prompt]),
                    Message(role="user", contents=[json.dumps(record.to_dict(), ensure_ascii=False)]),
                ],
                stream=False,
            )
        except _TRANSIENT_CHAT_CLIENT_ERRORS as exc:
            LOGGER.warning("Skipping memory consolidation for topic %r: %s", record.topic, exc)
            return record, False

        consolidation_text = consolidation_response.text.strip() if consolidation_response.text else ""
        if not consolidation_text:
            LOGGER.warning("Skipping consolidation for topic %r: empty response.", record.topic)
            return record, False
        try:
            payload: object = json.loads(_extract_json_text(consolidation_text))
        except (TypeError, ValueError) as exc:
            LOGGER.warning(
                "Skipping consolidation for topic %r: invalid JSON (%s; payload preview: %r).",
                record.topic,
                exc,
                _payload_preview(consolidation_text),
            )
            return record, False
        if not isinstance(payload, Mapping):
            LOGGER.warning(
                "Skipping consolidation for topic %r: payload is not a JSON object (preview: %r).",
                record.topic,
                _payload_preview(consolidation_text),
            )
            return record, False
        typed_payload = cast(Mapping[str, object], payload)
        summary = typed_payload.get("summary")
        raw_memories = typed_payload.get("memories")
        if not isinstance(summary, str) or not isinstance(raw_memories, list):
            LOGGER.warning(
                "Skipping consolidation for topic %r: missing 'summary' string or 'memories' list "
                "(payload preview: %r).",
                record.topic,
                _payload_preview(consolidation_text),
            )
            return record, False
        consolidated_memories = [memory for memory in cast(list[object], raw_memories) if isinstance(memory, str)]
        return (
            MemoryTopicRecord(
                topic=record.topic,
                slug=record.slug,
                summary=summary,
                memories=consolidated_memories,
                updated_at=_timestamp(now),
                session_ids=record.session_ids,
            ),
            True,
        )
