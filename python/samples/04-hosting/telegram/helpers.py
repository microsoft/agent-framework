# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import orjson
from agent_framework import AgentResponse, AgentSession, Content, Message

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Message as TelegramMessage
from telegram import User as TelegramUser
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application

LOGGER = logging.getLogger(__name__)
DEFAULT_LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
TELEGRAM_MESSAGE_LIMIT = 4096
STREAM_EDIT_INTERVAL_SECONDS = 1.0
STREAM_EDIT_MIN_CHARS = 80
TELEGRAM_PARSE_MODE = ParseMode.MARKDOWN
APPROVAL_CALLBACK_PREFIX = "approval"
BOT_COMMANDS = [
    BotCommand("start", "Introduce the bot"),
    BotCommand("new", "Start a new local session"),
    BotCommand("sessions", "List local sessions"),
    BotCommand("todo", "List todos for the active session"),
    BotCommand("notes", "List notes for the active session"),
    BotCommand("reminders", "List reminders for the active session"),
    BotCommand("resume", "Resume the latest pending or previous session"),
    BotCommand("cancel", "Cancel the active response"),
    BotCommand("reasoning", "Toggle the transient reasoning preview"),
    BotCommand("tokens", "Toggle token usage details"),
]


@dataclass
class SessionEntry:
    """Track one local Agent Framework session for a Telegram chat."""

    label: str
    session: AgentSession
    created_at: datetime
    last_used_at: datetime
    pending_approval: Content | None = None


@dataclass
class ReminderEntry:
    """Track one scheduled reminder for a Telegram chat."""

    reminder_id: str
    session_id: str
    target: str
    reminder_text: str
    due_at: datetime
    created_at: datetime
    job_name: str


@dataclass
class ChatState:
    """Track local sessions, reminders, and approvals for one Telegram chat."""

    next_session_number: int = 1
    next_reminder_number: int = 1
    active_session_label: str | None = None
    sessions: dict[str, SessionEntry] = field(default_factory=dict)
    reminders: dict[str, ReminderEntry] = field(default_factory=dict)
    active_turn_task: asyncio.Task[None] | None = None
    active_reply_message_id: int | None = None
    active_answer_text: str = ""
    show_reasoning: bool = True
    show_token_usage: bool = False
    last_known_user: TelegramUserProfile | None = None
    history_loaded_for_user_id: int | None = None


@dataclass(frozen=True)
class TelegramUserProfile:
    """Capture Telegram user metadata that is available on inbound updates."""

    telegram_user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None


@dataclass(frozen=True)
class TurnContext:
    """Track the Telegram chat/application used for local tools."""

    application: Application
    chat_id: int
    session_id: str
    session_label: str
    user_profile: TelegramUserProfile | None = None


CURRENT_TURN_CONTEXT: ContextVar[TurnContext | None] = ContextVar("telegram_turn_context", default=None)

JSON_INDENT_OPTIONS = orjson.OPT_INDENT_2
FILE_HISTORY_EXTENSION = ".jsonl"
SESSION_METADATA_FILENAME = "session.json"
SESSION_STORAGE_DIRECTORY = Path(__file__).resolve().parent / "sessions"
STORAGE_USER_DIRECTORY_PREFIX = "user_"
STORAGE_KIND_HISTORY = "history"
STORAGE_KIND_MEMORIES = "memories"
STORAGE_KIND_SESSION = "session"
STORAGE_KIND_TODOS = "todos"


def configure_logging() -> None:
    """Configure console logging for the Telegram sample."""
    log_level_name = os.getenv("TELEGRAM_SAMPLE_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        force=True,
    )

    for logger_name in (
        "asyncio",
        "httpx",
        "httpcore",
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.identity",
        "azure.monitor.opentelemetry",
        "urllib3.connectionpool",
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    for logger_name in (
        "openai",
        "telegram",
    ):
        logging.getLogger(logger_name).setLevel(logging.INFO)


def _format_telegram_text(text: str) -> str:
    """Clamp text to Telegram's message size limit."""
    trimmed = text.strip()
    if not trimmed:
        return "..."

    if len(trimmed) <= TELEGRAM_MESSAGE_LIMIT:
        return trimmed

    suffix = "\n\n[truncated]"
    return trimmed[: TELEGRAM_MESSAGE_LIMIT - len(suffix)] + suffix


def _escape_telegram_markdown(text: str) -> str:
    """Escape Telegram Markdown control characters in plain text."""
    escaped = text.replace("\\", "\\\\")
    for character in ("`", "*", "_", "["):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def _require_turn_context() -> TurnContext:
    """Return the current Telegram turn context for local tools."""
    turn_context = CURRENT_TURN_CONTEXT.get()
    if turn_context is None:
        raise RuntimeError("This tool is only available during an active Telegram chat turn.")
    return turn_context


def _get_current_chat_state() -> tuple[TurnContext, ChatState]:
    """Return the current turn context and mutable chat state."""
    turn_context = _require_turn_context()
    return turn_context, _get_chat_state(turn_context.application, turn_context.chat_id)


def _build_user_profile(user: TelegramUser | None) -> TelegramUserProfile | None:
    """Shape Telegram user metadata into a stable local profile record."""
    if user is None:
        return None

    return TelegramUserProfile(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )


def _write_json_file(path: Path, payload: object) -> None:
    """Write a JSON payload to disk using orjson."""
    path.write_bytes(orjson.dumps(payload, option=JSON_INDENT_OPTIONS) + b"\n")


def _read_json_file(path: Path) -> object:
    """Read a JSON payload from disk using orjson."""
    return orjson.loads(path.read_bytes())


def _new_uuid7() -> uuid.UUID:
    """Create a UUIDv7 value for sortable local Telegram session ids."""
    timestamp_ms = int(datetime.now(UTC).timestamp() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    uuid_int = (timestamp_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=uuid_int)


def _build_local_session_id() -> str:
    """Build a sortable local Telegram session id using UUIDv7."""
    return str(_new_uuid7())


def _get_user_storage_directory(*, storage_directory: Path, telegram_user_id: int) -> Path:
    """Return the local storage root for one Telegram user."""
    user_directory = storage_directory / f"{STORAGE_USER_DIRECTORY_PREFIX}{telegram_user_id}"
    user_directory.mkdir(parents=True, exist_ok=True)
    return user_directory


def _get_user_kind_directory(*, storage_directory: Path, telegram_user_id: int, kind: str) -> Path:
    """Return one per-user storage bucket such as history, memories, or session."""
    kind_directory = (
        _get_user_storage_directory(
            storage_directory=storage_directory,
            telegram_user_id=telegram_user_id,
        )
        / kind
    )
    kind_directory.mkdir(parents=True, exist_ok=True)
    return kind_directory


def _get_user_session_directory(*, storage_directory: Path, telegram_user_id: int, kind: str, session_id: str) -> Path:
    """Return one per-user, per-kind, per-session storage directory."""
    session_directory = (
        _get_user_kind_directory(
            storage_directory=storage_directory,
            telegram_user_id=telegram_user_id,
            kind=kind,
        )
        / session_id
    )
    session_directory.mkdir(parents=True, exist_ok=True)
    return session_directory


def _get_session_metadata_path(*, storage_directory: Path, telegram_user_id: int, session_id: str) -> Path:
    """Return the metadata file path for one persisted Telegram session."""
    return (
        _get_user_session_directory(
            storage_directory=storage_directory,
            telegram_user_id=telegram_user_id,
            kind=STORAGE_KIND_SESSION,
            session_id=session_id,
        )
        / SESSION_METADATA_FILENAME
    )


def _persist_session_snapshot(
    *,
    storage_directory: Path,
    chat_id: int,
    session: AgentSession,
    telegram_user_id: int,
) -> None:
    """Persist one Telegram session snapshot under the session storage bucket."""
    session.state["telegram_chat_id"] = chat_id
    session.state["telegram_user_id"] = telegram_user_id
    payload = session.to_dict()
    payload["name"] = session.session_id
    _write_json_file(
        _get_session_metadata_path(
            storage_directory=storage_directory,
            telegram_user_id=telegram_user_id,
            session_id=session.session_id,
        ),
        payload,
    )


def _extract_session_created_at(*, session_id: str, file_path: Path) -> datetime:
    """Infer a session creation time from a UUIDv7 session ID or file metadata."""
    try:
        parsed_uuid = uuid.UUID(session_id)
    except ValueError:
        parsed_uuid = None
    if parsed_uuid is not None and parsed_uuid.version == 7:
        timestamp_ms = parsed_uuid.int >> 80
        return datetime.fromtimestamp(timestamp_ms / 1000, UTC)

    return datetime.fromtimestamp(file_path.stat().st_mtime, UTC)


def _load_persisted_sessions(
    *,
    application: Application,
    chat_id: int,
    chat_state: ChatState,
    telegram_user_id: int,
) -> None:
    """Hydrate persisted local sessions for one Telegram chat from local session storage."""
    storage_directory = application.bot_data.get("storage_directory")
    if not isinstance(storage_directory, Path):
        return

    persisted_sessions: list[tuple[datetime, AgentSession]] = []

    user_session_directory = _get_user_kind_directory(
        storage_directory=storage_directory,
        telegram_user_id=telegram_user_id,
        kind=STORAGE_KIND_SESSION,
    )
    for session_directory in user_session_directory.iterdir():
        if not session_directory.is_dir():
            continue
        metadata_path = session_directory / SESSION_METADATA_FILENAME
        if not metadata_path.exists():
            continue
        raw_metadata = _read_json_file(metadata_path)
        if not isinstance(raw_metadata, dict):
            continue
        session_id = raw_metadata.get("session_id")
        if not isinstance(session_id, str):
            continue
        try:
            session = AgentSession.from_dict(raw_metadata)
        except (KeyError, TypeError, ValueError):
            continue
        stored_chat_id = session.state.get("telegram_chat_id")
        if stored_chat_id is not None and stored_chat_id != chat_id:
            continue
        session.state["telegram_chat_id"] = chat_id
        session.state["telegram_user_id"] = telegram_user_id
        persisted_sessions.append((
            _extract_session_created_at(session_id=session_id, file_path=metadata_path),
            session,
        ))

    user_history_directory = _get_user_kind_directory(
        storage_directory=storage_directory,
        telegram_user_id=telegram_user_id,
        kind=STORAGE_KIND_HISTORY,
    )
    for session_directory in user_history_directory.iterdir():
        if not session_directory.is_dir():
            continue
        session_id = session_directory.name
        if any(existing_session.session_id == session_id for _, existing_session in persisted_sessions):
            continue
        history_file_path = next(
            (path for path in sorted(session_directory.glob(f"*{FILE_HISTORY_EXTENSION}")) if path.is_file()),
            None,
        )
        if history_file_path is None:
            continue
        session = AgentSession(session_id=session_id)
        session.state["telegram_chat_id"] = chat_id
        session.state["telegram_user_id"] = telegram_user_id
        _persist_session_snapshot(
            storage_directory=storage_directory,
            chat_id=chat_id,
            session=session,
            telegram_user_id=telegram_user_id,
        )
        persisted_sessions.append((
            _extract_session_created_at(session_id=session_id, file_path=history_file_path),
            session,
        ))

    if not persisted_sessions:
        chat_state.history_loaded_for_user_id = telegram_user_id
        return

    for index, (created_at, session) in enumerate(sorted(persisted_sessions, key=lambda item: item[0]), start=1):
        label = f"session-{index}"
        chat_state.sessions[label] = SessionEntry(
            label=label,
            session=session,
            created_at=created_at,
            last_used_at=created_at,
        )

    chat_state.next_session_number = len(chat_state.sessions) + 1
    newest_entry = max(chat_state.sessions.values(), key=lambda entry: entry.created_at)
    chat_state.active_session_label = newest_entry.label
    chat_state.history_loaded_for_user_id = telegram_user_id
    LOGGER.info(
        "Loaded %s persisted Telegram sessions for chat_id=%s user_id=%s; active session is %s.",
        len(chat_state.sessions),
        chat_id,
        telegram_user_id,
        newest_entry.label,
    )


def _ensure_persisted_sessions_loaded(
    *,
    application: Application,
    chat_id: int,
    chat_state: ChatState,
    telegram_user_id: int,
) -> None:
    """Load persisted local sessions for the current Telegram user once per chat state."""
    if chat_state.history_loaded_for_user_id == telegram_user_id:
        return
    _load_persisted_sessions(
        application=application,
        chat_id=chat_id,
        chat_state=chat_state,
        telegram_user_id=telegram_user_id,
    )


def _require_job_queue(application: Application) -> object:
    """Return the PTB JobQueue, or raise if the extra dependency is unavailable."""
    job_queue = application.job_queue
    if job_queue is None:
        raise RuntimeError("Telegram JobQueue is not available. Install python-telegram-bot[job-queue].")
    return job_queue


def _cancel_reminder_job(*, application: Application, job_name: str) -> None:
    """Cancel a scheduled reminder job by name."""
    job_queue = _require_job_queue(application)
    for job in job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()


def _normalize_reminder_target(target: str) -> str:
    """Normalize and validate a reminder target."""
    normalized_target = target.strip().lower()
    if normalized_target not in {"user", "agent"}:
        raise ValueError("target must be either 'user' or 'agent'.")
    return normalized_target


def _format_reminder_entry(reminder_entry: ReminderEntry) -> dict[str, str]:
    """Render one reminder entry as structured data."""
    return {
        "reminder_id": reminder_entry.reminder_id,
        "target": reminder_entry.target,
        "reminder_text": reminder_entry.reminder_text,
        "due_at": reminder_entry.due_at.replace(microsecond=0).isoformat(),
        "created_at": reminder_entry.created_at.replace(microsecond=0).isoformat(),
        "session_id": reminder_entry.session_id,
    }


def _get_current_session_reminder(*, chat_state: ChatState, reminder_id: str, session_id: str) -> ReminderEntry:
    """Load a reminder entry that belongs to the current session."""
    reminder_entry = chat_state.reminders.get(reminder_id)
    if reminder_entry is None:
        raise FileNotFoundError(f"No pending reminder named '{reminder_id}' was found.")
    if reminder_entry.session_id != session_id:
        raise PermissionError(f"Reminder '{reminder_id}' belongs to session '{reminder_entry.session_id}'.")
    return reminder_entry


def _has_active_turn(chat_state: ChatState) -> bool:
    """Return whether this chat currently has an in-flight agent turn."""
    return chat_state.active_turn_task is not None and not chat_state.active_turn_task.done()


async def _clear_active_reply_message(*, bot: object, chat_id: int, chat_state: ChatState) -> None:
    """Delete the current placeholder reply message, if one exists."""
    message_id = chat_state.active_reply_message_id
    if message_id is None:
        return

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest as exc:
        if "message to delete not found" not in str(exc).lower():
            raise
    finally:
        chat_state.active_reply_message_id = None


def _register_active_turn(*, chat_state: ChatState, reply_message: TelegramMessage) -> asyncio.Task[None]:
    """Track the current in-flight agent turn for cancellation."""
    current_task = asyncio.current_task()
    if current_task is None:
        raise RuntimeError("Expected an active asyncio task for the Telegram turn.")
    chat_state.active_turn_task = current_task
    chat_state.active_reply_message_id = reply_message.message_id
    return current_task


def _clear_active_turn(*, chat_state: ChatState, task: asyncio.Task[None]) -> None:
    """Clear tracked turn state once the in-flight agent turn ends."""
    if chat_state.active_turn_task is task:
        chat_state.active_turn_task = None
        chat_state.active_reply_message_id = None
        chat_state.active_answer_text = ""


def _format_argument_name(name: str) -> str:
    """Convert tool argument keys into human-readable labels."""
    humanized = name.replace("_", " ").strip()
    if not humanized:
        return "value"
    return _escape_telegram_markdown(humanized.capitalize())


def _format_argument_scalar(value: object) -> str:
    """Render one scalar argument value for Telegram Markdown."""
    if value is None:
        return "_null_"
    if isinstance(value, bool):
        return "_true_" if value else "_false_"
    if isinstance(value, str):
        escaped = _escape_telegram_markdown(value)
        if "\n" in escaped:
            return escaped
        if len(escaped) <= 80:
            return f"`{escaped}`"
        return escaped
    return f"`{_escape_telegram_markdown(str(value))}`"


def _strip_replayed_hosted_files(session: AgentSession) -> None:
    """Remove assistant hosted-file annotations from local replay history."""
    session_messages = session.state.get("messages")
    if not isinstance(session_messages, list):
        return

    sanitized_messages: list[Message | object] = []
    removed_items = 0
    for message in session_messages:
        if not isinstance(message, Message) or message.role != "assistant":
            sanitized_messages.append(message)
            continue

        filtered_contents = [content for content in message.contents if content.type != "hosted_file"]
        removed_items += len(message.contents) - len(filtered_contents)
        if not filtered_contents:
            continue

        sanitized_messages.append(
            Message(
                message.role,
                filtered_contents,
                author_name=message.author_name,
                message_id=message.message_id,
                additional_properties=dict(message.additional_properties),
                raw_representation=message.raw_representation,
            )
        )

    if removed_items:
        LOGGER.info("Removed %s replay-only hosted file annotations from local session history", removed_items)
        session.state["messages"] = sanitized_messages


def _format_argument_lines(value: object, *, indent: int = 0, name: str | None = None) -> list[str]:
    """Render approval arguments as readable Markdown bullet lines."""
    prefix = "  " * indent
    formatted_name = _format_argument_name(name) if name is not None else None

    if isinstance(value, dict):
        lines = [f"{prefix}- *{formatted_name}*:"] if formatted_name is not None else []
        if not value:
            lines.append(f"{prefix}  _empty object_")
            return lines

        for key, nested_value in value.items():
            lines.extend(_format_argument_lines(nested_value, indent=indent + 1, name=str(key)))
        return lines

    if isinstance(value, list):
        lines = [f"{prefix}- *{formatted_name}*:"] if formatted_name is not None else []
        if not value:
            lines.append(f"{prefix}  _empty list_")
            return lines

        for index, item in enumerate(value, start=1):
            item_name = f"item {index}"
            lines.extend(_format_argument_lines(item, indent=indent + 1, name=item_name))
        return lines

    rendered_value = _format_argument_scalar(value)
    if "\n" in rendered_value:
        lines = [f"{prefix}- *{formatted_name}*:"] if formatted_name is not None else []
        lines.extend(f"{prefix}  {line}" for line in rendered_value.splitlines())
        return lines

    if formatted_name is None:
        return [f"{prefix}- {rendered_value}"]
    return [f"{prefix}- *{formatted_name}*: {rendered_value}"]


def _format_reasoning_preview(reasoning_text: str) -> str:
    """Render the last three reasoning lines for transient display."""
    visible_lines = [line.strip() for line in reasoning_text.splitlines() if line.strip()]
    if not visible_lines:
        return ""

    preview_lines = visible_lines[-3:]
    preview_sections = ["*Thinking...*"]
    if len(visible_lines) > len(preview_lines):
        preview_sections.append("...")
    preview_sections.extend(f"`> {_escape_telegram_markdown(line)}`" for line in preview_lines)
    return "\n".join(preview_sections)


def _format_token_usage(usage_details: object, *, enabled: bool) -> str:
    """Render a compact input/output token footer for Telegram replies."""
    if not enabled or not isinstance(usage_details, dict):
        return ""

    input_tokens = usage_details.get("input_token_count")
    output_tokens = usage_details.get("output_token_count")
    if not isinstance(input_tokens, int) and not isinstance(output_tokens, int):
        return ""

    input_label = "?" if not isinstance(input_tokens, int) else str(input_tokens)
    output_label = "?" if not isinstance(output_tokens, int) else str(output_tokens)
    return f"_Tokens: in {input_label} | out {output_label}_"


def _format_approval_arguments(arguments: object) -> str:
    """Parse and render approval arguments for a Telegram approval prompt."""
    if isinstance(arguments, str):
        try:
            parsed_arguments = orjson.loads(arguments)
        except orjson.JSONDecodeError:
            return _escape_telegram_markdown(arguments)
    elif arguments is None:
        return "_no arguments_"
    else:
        parsed_arguments = arguments

    lines = _format_argument_lines(parsed_arguments)
    return "\n".join(lines) if lines else "_no arguments_"


def _create_session_entry(
    *,
    agent: object,
    application: Application,
    chat_id: int,
    chat_state: ChatState,
    telegram_user_id: int,
) -> SessionEntry:
    """Create and register a fresh local session for one Telegram chat."""
    session_number = chat_state.next_session_number
    chat_state.next_session_number += 1
    label = f"session-{session_number}"
    now = datetime.now(UTC)
    session = agent.create_session(session_id=_build_local_session_id())
    session.state["telegram_chat_id"] = chat_id
    session.state["telegram_user_id"] = telegram_user_id
    storage_directory = application.bot_data.get("storage_directory")
    if isinstance(storage_directory, Path):
        _persist_session_snapshot(
            storage_directory=storage_directory,
            chat_id=chat_id,
            session=session,
            telegram_user_id=telegram_user_id,
        )
    entry = SessionEntry(
        label=label,
        session=session,
        created_at=now,
        last_used_at=now,
    )
    chat_state.sessions[label] = entry
    chat_state.active_session_label = label
    return entry


def _get_chat_state(application: Application, chat_id: int) -> ChatState:
    """Return the mutable chat state for one Telegram chat."""
    chat_states = application.bot_data.setdefault("chat_states", {})
    chat_state = chat_states.get(chat_id)
    if isinstance(chat_state, ChatState):
        return chat_state

    chat_state = ChatState()
    chat_states[chat_id] = chat_state
    return chat_state


def _get_session_entry_by_session_id(chat_state: ChatState, session_id: str) -> SessionEntry | None:
    """Return a session entry by its persisted AgentSession ID."""
    for entry in chat_state.sessions.values():
        if entry.session.session_id == session_id:
            return entry
    return None


def _get_active_session_entry(
    *,
    agent: object,
    application: Application,
    chat_id: int,
    chat_state: ChatState,
    telegram_user_id: int,
) -> SessionEntry:
    """Return the active session for the chat, creating one when needed."""
    if chat_state.active_session_label is not None:
        active_entry = chat_state.sessions.get(chat_state.active_session_label)
        if active_entry is not None:
            return active_entry

    return _create_session_entry(
        agent=agent,
        application=application,
        chat_id=chat_id,
        chat_state=chat_state,
        telegram_user_id=telegram_user_id,
    )


def _get_latest_pending_entry(chat_state: ChatState) -> SessionEntry | None:
    """Return the latest session waiting on tool approval, if any."""
    pending_entries = [entry for entry in chat_state.sessions.values() if entry.pending_approval is not None]
    if not pending_entries:
        return None
    return max(pending_entries, key=lambda entry: entry.last_used_at)


def _get_resume_entry(chat_state: ChatState) -> SessionEntry | None:
    """Pick the best session to resume for the current chat."""
    pending_entry = _get_latest_pending_entry(chat_state)
    if pending_entry is not None:
        return pending_entry

    ordered_entries = sorted(chat_state.sessions.values(), key=lambda entry: entry.created_at, reverse=True)
    if not ordered_entries:
        return None
    if chat_state.active_session_label is None:
        return ordered_entries[0]

    for index, entry in enumerate(ordered_entries):
        if entry.label != chat_state.active_session_label:
            continue
        if index + 1 < len(ordered_entries):
            return ordered_entries[index + 1]
        return ordered_entries[0] if len(ordered_entries) > 1 else entry

    return ordered_entries[0]


def _get_latest_approval_request(response: AgentResponse) -> Content | None:
    """Return the latest approval request emitted by the agent, if any."""
    for message in reversed(response.messages):
        for content in reversed(message.contents):
            if content.type == "function_approval_request":
                return content
    return None


def _format_approval_prompt(*, entry: SessionEntry, approval_request: Content) -> str:
    """Describe a pending approval request with readable Markdown formatting."""
    tool_name = approval_request.function_call.name if approval_request.function_call is not None else None
    arguments = approval_request.function_call.arguments if approval_request.function_call is not None else "{}"
    formatted_arguments = _format_approval_arguments(arguments)
    return _format_telegram_text(
        "*Approval needed*\n"
        f"*Session:* {_escape_telegram_markdown(entry.label)}\n"
        f"*Tool:* {_escape_telegram_markdown(tool_name or 'unknown_tool')}\n\n"
        "*Arguments*\n"
        f"{formatted_arguments}\n\n"
        "_Use the buttons below to approve or reject._"
    )


def _build_approval_markup(session_label: str) -> InlineKeyboardMarkup:
    """Create inline approval buttons for a pending tool request."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"{APPROVAL_CALLBACK_PREFIX}:approve:{session_label}"),
            InlineKeyboardButton("Reject", callback_data=f"{APPROVAL_CALLBACK_PREFIX}:reject:{session_label}"),
        ]
    ])


def _parse_approval_callback_data(callback_data: str | None) -> tuple[bool, str] | None:
    """Parse callback data emitted by the inline approval buttons."""
    if not callback_data:
        return None

    prefix, separator, remainder = callback_data.partition(":")
    if prefix != APPROVAL_CALLBACK_PREFIX or not separator:
        return None

    decision, separator, session_label = remainder.partition(":")
    if decision not in {"approve", "reject"} or not separator or not session_label:
        return None
    return decision == "approve", session_label


def _format_sessions_list(chat_state: ChatState) -> str:
    """Render the current local sessions for one Telegram chat."""
    if not chat_state.sessions:
        return "No local sessions yet. Send /new to start one."

    lines = ["Local sessions:"]
    for label, entry in sorted(chat_state.sessions.items(), key=lambda item: item[1].created_at, reverse=True):
        markers: list[str] = []
        if label == chat_state.active_session_label:
            markers.append("active")
        if entry.pending_approval is not None:
            markers.append("awaiting approval")
        suffix = f" ({', '.join(markers)})" if markers else ""
        lines.append(f"- {label}{suffix}")
    return "\n".join(lines)
