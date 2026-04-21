# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson
from agent_framework import AgentSession, ContextProvider, FileHistoryProvider, Message, SessionContext, tool
from helpers import (
    CURRENT_TURN_CONTEXT,
    STORAGE_KIND_HISTORY,
    ReminderEntry,
    _cancel_reminder_job,
    _format_reminder_entry,
    _get_chat_state,
    _get_current_chat_state,
    _get_current_session_reminder,
    _get_user_session_directory,
    _normalize_reminder_target,
    _require_job_queue,
)

from telegram.ext import Application

if TYPE_CHECKING:
    from collections.abc import Sequence

    from agent_framework import SupportsAgentRun


DEFAULT_SOURCE_ID = "telegram_reminders"
DEFAULT_CONTEXT_PROMPT = "## Pending reminders\nUse the following reminder context when it is relevant."


def _sanitize_file_history_message(message: Message) -> Message | None:
    """Remove replay-only hosted files before persisting assistant messages."""
    if message.role != "assistant":
        return message

    filtered_contents = [content for content in message.contents if content.type != "hosted_file"]
    if len(filtered_contents) == len(message.contents):
        return message
    if not filtered_contents:
        return None

    return Message(
        message.role,
        filtered_contents,
        author_name=message.author_name,
        message_id=message.message_id,
        additional_properties=dict(message.additional_properties),
        raw_representation=message.raw_representation,
    )


def _format_reminder_context(reminders: list[ReminderEntry]) -> str:
    """Render current-session reminders for the reminders provider context message."""
    if not reminders:
        return "- none scheduled yet"

    return "\n".join(
        (
            f"- {reminder.reminder_id} [{reminder.target}] "
            f"{reminder.due_at.replace(microsecond=0).isoformat()}: {reminder.reminder_text}"
        )
        for reminder in reminders
    )


def _schedule_reminder_job(
    *, application: Application, chat_id: int, seconds_from_now: int, reminder_id: str, job_name: str
) -> None:
    """Schedule the JobQueue callback for one reminder entry."""
    from handlers import send_reminder_callback

    job_queue = _require_job_queue(application)
    job_queue.run_once(
        send_reminder_callback,
        when=seconds_from_now,
        data={"chat_id": chat_id, "reminder_id": reminder_id},
        name=job_name,
        chat_id=chat_id,
    )


class TelegramFileHistoryProvider(FileHistoryProvider):
    """Persist Telegram sample history to local JSONL files."""

    def __init__(self, storage_path: Path, **kwargs: Any) -> None:
        super().__init__(storage_path, **kwargs)
        self._provider_kwargs = kwargs
        self._providers_by_user_and_session: dict[tuple[int, str | None], FileHistoryProvider] = {}

    def _get_session_provider(self, *, session_id: str | None, telegram_user_id: int) -> FileHistoryProvider:
        provider_key = (telegram_user_id, session_id)
        provider = self._providers_by_user_and_session.get(provider_key)
        if provider is not None:
            return provider

        session_directory = _get_user_session_directory(
            storage_directory=self.storage_path,
            telegram_user_id=telegram_user_id,
            kind=STORAGE_KIND_HISTORY,
            session_id=session_id or "default",
        )
        provider = FileHistoryProvider(session_directory, **self._provider_kwargs)
        self._providers_by_user_and_session[provider_key] = provider
        return provider

    @staticmethod
    def _require_telegram_user_id(state: dict[str, Any] | None) -> int:
        telegram_user_id = state.get("telegram_user_id") if state is not None else None
        if not isinstance(telegram_user_id, int):
            turn_context = CURRENT_TURN_CONTEXT.get()
            user_profile = turn_context.user_profile if turn_context is not None else None
            telegram_user_id = user_profile.telegram_user_id if user_profile is not None else None
            if isinstance(telegram_user_id, int) and state is not None:
                state["telegram_user_id"] = telegram_user_id
        if not isinstance(telegram_user_id, int):
            raise RuntimeError("Telegram file history requires session.state['telegram_user_id'] to be set.")
        return telegram_user_id

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        telegram_user_id = self._require_telegram_user_id(state)
        provider = self._get_session_provider(session_id=session_id, telegram_user_id=telegram_user_id)
        return await provider.get_messages(None, state=state, **kwargs)

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        telegram_user_id = self._require_telegram_user_id(state)
        sanitized_messages = [
            sanitized_message
            for message in messages
            if (sanitized_message := _sanitize_file_history_message(message)) is not None
        ]
        provider = self._get_session_provider(session_id=session_id, telegram_user_id=telegram_user_id)
        await provider.save_messages(None, sanitized_messages, state=state, **kwargs)


@tool(approval_mode="never_require")
def create_reminder(seconds_from_now: int, reminder_text: str, target: str = "user") -> str:
    """Schedule a reminder message for the current Telegram chat."""
    if seconds_from_now <= 0:
        raise ValueError("seconds_from_now must be greater than zero.")

    turn_context, chat_state = _get_current_chat_state()
    normalized_target = _normalize_reminder_target(target)
    reminder_id = f"reminder-{chat_state.next_reminder_number}"
    chat_state.next_reminder_number += 1
    created_at = datetime.now(UTC)
    due_at = created_at.timestamp() + seconds_from_now
    reminder_job_name = f"reminder:{turn_context.chat_id}:{reminder_id}:{int(time.time())}"
    reminder_entry = ReminderEntry(
        reminder_id=reminder_id,
        session_id=turn_context.session_id,
        target=normalized_target,
        reminder_text=reminder_text.strip(),
        due_at=datetime.fromtimestamp(due_at, tz=UTC),
        created_at=created_at,
        job_name=reminder_job_name,
    )
    chat_state.reminders[reminder_id] = reminder_entry
    _schedule_reminder_job(
        application=turn_context.application,
        chat_id=turn_context.chat_id,
        seconds_from_now=seconds_from_now,
        reminder_id=reminder_id,
        job_name=reminder_job_name,
    )
    return orjson.dumps(_format_reminder_entry(reminder_entry), option=orjson.OPT_INDENT_2).decode("utf-8")


@tool(approval_mode="never_require")
def list_reminders() -> str:
    """List pending reminders for the current local session."""
    turn_context, chat_state = _get_current_chat_state()
    reminders = [
        _format_reminder_entry(reminder_entry)
        for reminder_entry in sorted(chat_state.reminders.values(), key=lambda entry: entry.due_at)
        if reminder_entry.session_id == turn_context.session_id
    ]
    return orjson.dumps(reminders, option=orjson.OPT_INDENT_2).decode("utf-8")


@tool(approval_mode="never_require")
def read_reminder(reminder_id: str) -> str:
    """Read one pending reminder for the current local session."""
    turn_context, chat_state = _get_current_chat_state()
    reminder_entry = _get_current_session_reminder(
        chat_state=chat_state,
        reminder_id=reminder_id,
        session_id=turn_context.session_id,
    )
    return orjson.dumps(_format_reminder_entry(reminder_entry), option=orjson.OPT_INDENT_2).decode("utf-8")


@tool(approval_mode="never_require")
def update_reminder(reminder_id: str, seconds_from_now: int, reminder_text: str, target: str | None = None) -> str:
    """Update one pending reminder for the current local session."""
    if seconds_from_now <= 0:
        raise ValueError("seconds_from_now must be greater than zero.")

    turn_context, chat_state = _get_current_chat_state()
    reminder_entry = _get_current_session_reminder(
        chat_state=chat_state,
        reminder_id=reminder_id,
        session_id=turn_context.session_id,
    )
    normalized_target = reminder_entry.target if target is None else _normalize_reminder_target(target)
    _cancel_reminder_job(application=turn_context.application, job_name=reminder_entry.job_name)

    updated_due_at = datetime.fromtimestamp(datetime.now(UTC).timestamp() + seconds_from_now, tz=UTC)
    updated_job_name = f"reminder:{turn_context.chat_id}:{reminder_id}:{int(time.time())}"
    updated_entry = ReminderEntry(
        reminder_id=reminder_entry.reminder_id,
        session_id=reminder_entry.session_id,
        target=normalized_target,
        reminder_text=reminder_text.strip(),
        due_at=updated_due_at,
        created_at=reminder_entry.created_at,
        job_name=updated_job_name,
    )
    chat_state.reminders[reminder_id] = updated_entry
    _schedule_reminder_job(
        application=turn_context.application,
        chat_id=turn_context.chat_id,
        seconds_from_now=seconds_from_now,
        reminder_id=reminder_id,
        job_name=updated_job_name,
    )
    return orjson.dumps(_format_reminder_entry(updated_entry), option=orjson.OPT_INDENT_2).decode("utf-8")


@tool(approval_mode="never_require")
def delete_reminder(reminder_id: str) -> str:
    """Delete one pending reminder from the current local session."""
    turn_context, chat_state = _get_current_chat_state()
    reminder_entry = _get_current_session_reminder(
        chat_state=chat_state,
        reminder_id=reminder_id,
        session_id=turn_context.session_id,
    )
    _cancel_reminder_job(application=turn_context.application, job_name=reminder_entry.job_name)
    chat_state.reminders.pop(reminder_id, None)
    return f"Deleted reminder '{reminder_id}' from session '{turn_context.session_id}'."


class TelegramReminderContextProvider(ContextProvider):
    """Inject reminder tools, instructions, and current-session reminder context."""

    def __init__(self, source_id: str = DEFAULT_SOURCE_ID, *, context_prompt: str | None = None) -> None:
        """Initialize the Telegram reminders provider."""
        super().__init__(source_id)
        self.context_prompt = context_prompt or DEFAULT_CONTEXT_PROMPT

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject reminder tools, instructions, and pending reminder context before the model runs."""
        turn_context = CURRENT_TURN_CONTEXT.get()
        if turn_context is None:
            return

        chat_state = _get_chat_state(turn_context.application, turn_context.chat_id)
        reminders = [
            reminder_entry
            for reminder_entry in sorted(chat_state.reminders.values(), key=lambda entry: entry.due_at)
            if reminder_entry.session_id == turn_context.session_id
        ]
        context.extend_tools(
            self.source_id,
            [create_reminder, list_reminders, read_reminder, update_reminder, delete_reminder],
        )
        context.extend_instructions(
            self.source_id,
            [
                ("Use the Telegram reminder tools when the user asks to be reminded later in this Telegram chat."),
                "Convert relative reminder times into integer seconds from now.",
                "Use target='user' when the reminder should only notify the user later.",
                "Use target='agent' when the reminder should wake the agent later and have the agent act on it.",
                (
                    "Use list_reminders, read_reminder, update_reminder, and delete_reminder to manage reminders "
                    "in the current session. When updating a reminder, keep its current target unless the user "
                    "asks to change it."
                ),
                "Agent-targeted reminders should remind the agent to do the requested task and then let the agent answer naturally.",
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
                            f"### Pending reminders for session {turn_context.session_id}\n"
                            f"{_format_reminder_context(reminders)}"
                        )
                    ],
                )
            ],
        )
