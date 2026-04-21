# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import datetime
import time
from contextvars import Token
from pathlib import Path

from agent_framework import (
    DEFAULT_MEMORY_SOURCE_ID,
    DEFAULT_TODO_SOURCE_ID,
    Agent,
    AgentResponse,
    MemoryFileStore,
    TodoFileStore,
)
from agent_framework import Message as AgentMessage
from helpers import (
    CURRENT_TURN_CONTEXT,
    LOGGER,
    STREAM_EDIT_INTERVAL_SECONDS,
    STREAM_EDIT_MIN_CHARS,
    TELEGRAM_PARSE_MODE,
    TurnContext,
    _build_approval_markup,
    _build_user_profile,
    _clear_active_reply_message,
    _clear_active_turn,
    _create_session_entry,
    _ensure_persisted_sessions_loaded,
    _escape_telegram_markdown,
    _format_approval_prompt,
    _format_reasoning_preview,
    _format_sessions_list,
    _format_telegram_text,
    _format_token_usage,
    _get_active_session_entry,
    _get_chat_state,
    _get_latest_approval_request,
    _get_resume_entry,
    _get_session_entry_by_session_id,
    _has_active_turn,
    _parse_approval_callback_data,
    _persist_session_snapshot,
    _register_active_turn,
    _strip_replayed_hosted_files,
)

from telegram import InlineKeyboardMarkup, Update
from telegram import Message as TelegramMessage
from telegram.constants import ChatAction
from telegram.error import BadRequest, RetryAfter
from telegram.ext import ContextTypes


async def send_reminder_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deliver a scheduled reminder back into the originating Telegram chat."""
    job = context.job
    if job is None or not isinstance(job.data, dict):
        LOGGER.warning("Reminder job ran without valid data.")
        return

    chat_id = job.data.get("chat_id")
    reminder_id = job.data.get("reminder_id")
    if not isinstance(chat_id, int) or not isinstance(reminder_id, str):
        LOGGER.warning("Reminder job data was missing required fields.")
        return

    chat_state = _get_chat_state(context.application, chat_id)
    reminder_entry = chat_state.reminders.pop(reminder_id, None)
    if reminder_entry is None:
        LOGGER.info("Reminder %s was no longer pending when its callback fired.", reminder_id)
        return

    if reminder_entry.target == "agent":
        session_entry = chat_state.sessions.get(reminder_entry.session_id)
        if session_entry is None:
            session_entry = _get_session_entry_by_session_id(chat_state, reminder_entry.session_id)
        if session_entry is None:
            await context.bot.send_message(
                chat_id=chat_id,
                text=_format_telegram_text(
                    "The agent reminder fired, but the original session is no longer available."
                ),
                parse_mode=TELEGRAM_PARSE_MODE,
            )
            return

        if _has_active_turn(chat_state):
            await context.bot.send_message(
                chat_id=chat_id,
                text=_format_telegram_text(
                    "*Reminder*\n"
                    f"I was reminded to `{_escape_telegram_markdown(reminder_entry.reminder_text)}` for the agent, "
                    "but another response is already running."
                ),
                parse_mode=TELEGRAM_PARSE_MODE,
            )
            return

        chat_state.active_session_label = session_entry.label
        await context.bot.send_message(
            chat_id=chat_id,
            text=_format_telegram_text(
                "*Reminder*\n"
                f"I reminded the agent to `{_escape_telegram_markdown(reminder_entry.reminder_text)}`.\n"
                "The agent is responding now."
            ),
            parse_mode=TELEGRAM_PARSE_MODE,
        )
        reply_message = await context.bot.send_message(
            chat_id=chat_id,
            text="Thinking...",
            parse_mode=TELEGRAM_PARSE_MODE,
        )
        current_task = _register_active_turn(chat_state=chat_state, reply_message=reply_message)

        async def send_followup_message(text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=TELEGRAM_PARSE_MODE,
                reply_markup=reply_markup,
            )

        try:
            await _complete_agent_turn(
                application=context.application,
                bot=context.bot,
                chat_id=chat_id,
                chat_state=chat_state,
                entry=session_entry,
                prompt=(
                    "A scheduled reminder just fired. Please do this now and then reply to the user with the result: "
                    f"{reminder_entry.reminder_text}"
                ),
                reply_message=reply_message,
                send_followup_message=send_followup_message,
            )
        except asyncio.CancelledError:
            await _clear_active_reply_message(
                bot=context.bot,
                chat_id=chat_id,
                chat_state=chat_state,
            )
            return
        finally:
            _clear_active_turn(chat_state=chat_state, task=current_task)
        return

    reminder_message = _format_telegram_text(
        "*Reminder*\n"
        f"*Session:* {_escape_telegram_markdown(reminder_entry.session_id)}\n"
        f"*Message:* {_escape_telegram_markdown(reminder_entry.reminder_text)}"
    )
    await context.bot.send_message(chat_id=chat_id, text=reminder_message, parse_mode=TELEGRAM_PARSE_MODE)


def _append_stream_chunk(existing_text: str, chunk: str) -> str:
    """Append a streamed chunk while tolerating repeated or overlapping content."""
    if not chunk:
        return existing_text
    if not existing_text:
        return chunk
    if existing_text.endswith(chunk):
        return existing_text

    overlap_limit = min(len(existing_text), len(chunk))
    for overlap_size in range(overlap_limit, 0, -1):
        if existing_text.endswith(chunk[:overlap_size]):
            return existing_text + chunk[overlap_size:]
    return existing_text + chunk


def _format_stream_answer(text: str) -> str:
    """Escape model text before sending it through Telegram Markdown."""
    return _escape_telegram_markdown(text.strip())


def _get_retry_after_seconds(error: RetryAfter) -> float:
    """Return the Telegram flood-control delay in seconds."""
    return max(float(error.retry_after), 0.0)


async def _edit_message_text_with_backoff(
    *,
    blocked_until: float = 0.0,
    message: TelegramMessage,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    wait_for_slot: bool,
) -> tuple[bool, float]:
    """Edit a Telegram message while respecting flood-control backoff."""
    current_blocked_until = blocked_until
    while True:
        delay_seconds = current_blocked_until - time.monotonic()
        if delay_seconds > 0:
            if not wait_for_slot:
                return False, current_blocked_until
            await asyncio.sleep(delay_seconds)

        try:
            await message.edit_text(
                text,
                parse_mode=TELEGRAM_PARSE_MODE,
                reply_markup=reply_markup,
            )
        except RetryAfter as error:
            retry_after_seconds = _get_retry_after_seconds(error)
            current_blocked_until = time.monotonic() + retry_after_seconds
            LOGGER.warning(
                "Telegram edit rate limited for %.1f seconds; buffering the latest response text in memory.",
                retry_after_seconds,
            )
            if not wait_for_slot:
                return False, current_blocked_until
        except BadRequest as error:
            if "Message is not modified" in str(error):
                return False, current_blocked_until
            raise
        else:
            return True, 0.0


async def _stream_reply(
    *,
    agent: Agent,
    session: object,
    chat_state: object,
    prompt: str | AgentMessage,
    reply_message: TelegramMessage,
) -> tuple[AgentResponse, str]:
    """Stream an Agent Framework response into a single Telegram reply."""
    stream = agent.run(prompt, session=session, stream=True)
    streamed_text = ""
    visible_reasoning_text = ""
    last_sent_text = ""
    last_edit_at = 0.0
    last_reasoning_visible = False
    blocked_until = 0.0

    async for update in stream:
        reasoning_updated = False
        for content in update.contents:
            if content.type == "text" and content.text:
                streamed_text = _append_stream_chunk(streamed_text, content.text)
                visible_reasoning_text = ""
                continue
            if content.type == "text_reasoning" and content.text:
                visible_reasoning_text = _append_stream_chunk(visible_reasoning_text, content.text)
                reasoning_updated = True

        chat_state.active_answer_text = streamed_text.strip()
        reasoning_preview = ""
        if chat_state.show_reasoning and (not streamed_text or reasoning_updated):
            reasoning_preview = _format_reasoning_preview(visible_reasoning_text)
        reasoning_visible = bool(reasoning_preview)
        answer_preview = _format_stream_answer(streamed_text)
        preview_sections = [section for section in (reasoning_preview, answer_preview) if section]
        if not preview_sections:
            continue

        candidate_text = _format_telegram_text("\n\n".join(preview_sections))
        should_edit = candidate_text != last_sent_text and (
            reasoning_visible != last_reasoning_visible
            or len(candidate_text) < len(last_sent_text)
            or len(candidate_text) - len(last_sent_text) >= STREAM_EDIT_MIN_CHARS
            or candidate_text.endswith(("\n", ".", "!", "?", ":"))
            or time.monotonic() - last_edit_at >= STREAM_EDIT_INTERVAL_SECONDS
        )
        if not should_edit:
            continue

        updated, blocked_until = await _edit_message_text_with_backoff(
            blocked_until=blocked_until,
            message=reply_message,
            text=candidate_text,
            wait_for_slot=False,
        )
        if updated:
            last_sent_text = candidate_text
            last_edit_at = time.monotonic()
            last_reasoning_visible = reasoning_visible

    final_response = await stream.get_final_response()
    final_sections = [
        section
        for section in (
            _format_stream_answer(final_response.text or streamed_text),
            _format_token_usage(final_response.usage_details, enabled=chat_state.show_token_usage),
        )
        if section
    ]
    final_text = _format_telegram_text("\n\n".join(final_sections)) if final_sections else ""
    if not final_text or final_text == last_sent_text:
        return final_response, last_sent_text

    updated, _ = await _edit_message_text_with_backoff(
        blocked_until=blocked_until,
        message=reply_message,
        text=final_text,
        wait_for_slot=True,
    )
    if not updated:
        return final_response, last_sent_text
    return final_response, final_text


async def _complete_agent_turn(
    *,
    application: object,
    bot: object,
    chat_id: int,
    chat_state: object,
    entry: object,
    prompt: str | AgentMessage,
    reply_message: TelegramMessage,
    send_followup_message: object,
) -> None:
    """Complete one agent turn once the placeholder reply message already exists."""
    agent = application.bot_data["agent"]
    entry.last_used_at = datetime.datetime.now(datetime.UTC)
    turn_token: Token[TurnContext | None] = CURRENT_TURN_CONTEXT.set(
        TurnContext(
            application=application,
            chat_id=chat_id,
            session_id=entry.session.session_id,
            session_label=entry.label,
            user_profile=chat_state.last_known_user,
        )
    )
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        final_response, displayed_text = await _stream_reply(
            agent=agent,
            session=entry.session,
            chat_state=chat_state,
            prompt=prompt,
            reply_message=reply_message,
        )
    finally:
        CURRENT_TURN_CONTEXT.reset(turn_token)
    _strip_replayed_hosted_files(entry.session)
    storage_directory = application.bot_data.get("storage_directory")
    telegram_user_id = entry.session.state.get("telegram_user_id")
    if isinstance(storage_directory, Path) and isinstance(telegram_user_id, int):
        _persist_session_snapshot(
            storage_directory=storage_directory,
            chat_id=chat_id,
            session=entry.session,
            telegram_user_id=telegram_user_id,
        )

    approval_request = _get_latest_approval_request(final_response)
    if approval_request is not None:
        entry.pending_approval = approval_request
        approval_prompt = _format_approval_prompt(entry=entry, approval_request=approval_request)
        approval_markup = _build_approval_markup(entry.label)
        if displayed_text:
            await send_followup_message(approval_prompt, approval_markup)
        else:
            await _edit_message_text_with_backoff(
                message=reply_message,
                text=approval_prompt,
                reply_markup=approval_markup,
                wait_for_slot=True,
            )
        return

    entry.pending_approval = None
    if displayed_text:
        return

    await _edit_message_text_with_backoff(
        message=reply_message,
        text="I couldn't generate a reply.",
        wait_for_slot=True,
    )


async def _handle_agent_turn(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    entry: object,
    prompt: str | AgentMessage,
) -> None:
    """Run one agent turn and bridge text or approval requests back to Telegram."""
    if update.effective_chat is None or update.effective_message is None:
        return

    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    reply_message = await update.effective_message.reply_text("Thinking...", parse_mode=TELEGRAM_PARSE_MODE)
    current_task = _register_active_turn(chat_state=chat_state, reply_message=reply_message)

    async def send_followup_message(text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        await update.effective_message.reply_text(
            text,
            parse_mode=TELEGRAM_PARSE_MODE,
            reply_markup=reply_markup,
        )

    try:
        await _complete_agent_turn(
            application=context.application,
            bot=context.bot,
            chat_id=update.effective_chat.id,
            chat_state=chat_state,
            entry=entry,
            prompt=prompt,
            reply_message=reply_message,
            send_followup_message=send_followup_message,
        )
    except asyncio.CancelledError:
        await _clear_active_reply_message(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            chat_state=chat_state,
        )
        return
    finally:
        _clear_active_turn(chat_state=chat_state, task=current_task)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Introduce the Telegram sample and mention the available tools."""
    if update.effective_message is None:
        return

    await update.effective_message.reply_text(
        "Hi! I am your personal bot, powered by the Agent Framework.\n\n"
        "Commands: /new, /sessions, /todo, /memories, /reminders, /resume, /cancel, /reasoning, /tokens.\n"
        "Ask me normal questions, current-events questions that may need web search, "
        "time questions that may need my UTC time tool, reminder create/read/update/delete requests for either the user or the agent, "
        "or ask me to save, inspect, or clean up durable memory topics. "
        "For longer tasks, I can also manage a session todo list while I work. "
        "Raw transcript searches use approval buttons.",
        parse_mode=TELEGRAM_PARSE_MODE,
    )


async def handle_new_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a fresh local session for the current Telegram chat."""
    if update.effective_chat is None or update.effective_message is None or update.effective_user is None:
        return

    agent = context.application.bot_data["agent"]
    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    chat_state.last_known_user = _build_user_profile(update.effective_user)
    _ensure_persisted_sessions_loaded(
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    entry = _create_session_entry(
        agent=agent,
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    await update.effective_message.reply_text(f"Started {entry.label}.")


async def handle_list_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List the local sessions tracked for the current Telegram chat."""
    if update.effective_chat is None or update.effective_message is None or update.effective_user is None:
        return

    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    chat_state.last_known_user = _build_user_profile(update.effective_user)
    _ensure_persisted_sessions_loaded(
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    await update.effective_message.reply_text(_format_sessions_list(chat_state))


async def handle_list_memories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List durable memory topics for the active local session owner."""
    if update.effective_chat is None or update.effective_message is None:
        return

    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    if update.effective_user is None:
        await update.effective_message.reply_text("I could not determine which Telegram user owns these memories.")
        return

    chat_state.last_known_user = _build_user_profile(update.effective_user)
    _ensure_persisted_sessions_loaded(
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    entry = chat_state.sessions.get(chat_state.active_session_label or "") or _get_resume_entry(chat_state)
    if entry is None:
        await update.effective_message.reply_text("No active session yet. Send /new to start one.")
        return

    chat_state.active_session_label = entry.label
    memory_store: MemoryFileStore = context.application.bot_data["memory_store"]
    topic_records = memory_store.list_topics(entry.session, source_id=DEFAULT_MEMORY_SOURCE_ID)
    if not topic_records:
        await update.effective_message.reply_text(f"No memory topics yet for {entry.label}.")
        return

    lines = [f"*Memory topics for {entry.label}*"]
    for topic_record in topic_records:
        lines.append(
            f"- `{_escape_telegram_markdown(topic_record.topic)}` - "
            f"{_escape_telegram_markdown(topic_record.updated_at)}"
        )
    await update.effective_message.reply_text(_format_telegram_text("\n".join(lines)), parse_mode=TELEGRAM_PARSE_MODE)


async def handle_list_todos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List todo items for the active local session."""
    if update.effective_chat is None or update.effective_message is None or update.effective_user is None:
        return

    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    chat_state.last_known_user = _build_user_profile(update.effective_user)
    _ensure_persisted_sessions_loaded(
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    entry = chat_state.sessions.get(chat_state.active_session_label or "") or _get_resume_entry(chat_state)
    if entry is None:
        await update.effective_message.reply_text("No active session yet. Send /new to start one.")
        return

    chat_state.active_session_label = entry.label
    todo_store: TodoFileStore = context.application.bot_data["todo_store"]
    items = todo_store.load_items(entry.session, source_id=DEFAULT_TODO_SOURCE_ID)
    if not items:
        await update.effective_message.reply_text(f"No todos for {entry.label}.")
        return

    lines = [f"*Todos for {entry.label}*"]
    for item in items:
        status = "done" if item.is_complete else "open"
        line = f"- `{item.id}` ({status}) {_escape_telegram_markdown(item.title)}"
        if item.description:
            line = f"{line}: {_escape_telegram_markdown(item.description)}"
        lines.append(line)
    await update.effective_message.reply_text(_format_telegram_text("\n".join(lines)), parse_mode=TELEGRAM_PARSE_MODE)


async def handle_list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending reminders for the active local session."""
    if update.effective_chat is None or update.effective_message is None or update.effective_user is None:
        return

    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    chat_state.last_known_user = _build_user_profile(update.effective_user)
    _ensure_persisted_sessions_loaded(
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    entry = chat_state.sessions.get(chat_state.active_session_label or "") or _get_resume_entry(chat_state)
    if entry is None:
        await update.effective_message.reply_text("No active session yet. Send /new to start one.")
        return

    chat_state.active_session_label = entry.label
    reminders = [
        reminder_entry
        for reminder_entry in sorted(chat_state.reminders.values(), key=lambda item: item.due_at)
        if reminder_entry.session_id == entry.session.session_id
    ]
    if not reminders:
        await update.effective_message.reply_text(f"No pending reminders for {entry.label}.")
        return

    lines = [f"*Reminders for {entry.label}*"]
    for reminder_entry in reminders:
        lines.append(
            f"- `{_escape_telegram_markdown(reminder_entry.reminder_id)}` "
            f"[{_escape_telegram_markdown(reminder_entry.target)}] "
            f"{_escape_telegram_markdown(reminder_entry.due_at.replace(microsecond=0).isoformat())}: "
            f"{_escape_telegram_markdown(reminder_entry.reminder_text)}"
        )
    await update.effective_message.reply_text(_format_telegram_text("\n".join(lines)), parse_mode=TELEGRAM_PARSE_MODE)


async def handle_resume_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch the active session to the best resumable session for this chat."""
    if update.effective_chat is None or update.effective_message is None or update.effective_user is None:
        return

    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    chat_state.last_known_user = _build_user_profile(update.effective_user)
    _ensure_persisted_sessions_loaded(
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    entry = _get_resume_entry(chat_state)
    if entry is None:
        await update.effective_message.reply_text("No saved session is available yet. Send /new to start one.")
        return

    chat_state.active_session_label = entry.label
    entry.last_used_at = datetime.datetime.now(datetime.UTC)
    status = " and it is waiting for approval" if entry.pending_approval is not None else ""
    await update.effective_message.reply_text(f"Resumed {entry.label}{status}.")


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel the active response for the current Telegram chat."""
    if update.effective_chat is None or update.effective_message is None:
        return

    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    if not _has_active_turn(chat_state):
        await update.effective_message.reply_text("Nothing is running right now.")
        return

    active_task = chat_state.active_turn_task
    await _clear_active_reply_message(
        bot=context.bot,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
    )
    chat_state.active_turn_task = None
    if active_task is not None:
        active_task.cancel()
    await update.effective_message.reply_text("Cancelled the current response.")


async def handle_toggle_reasoning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle transient reasoning previews for the current Telegram chat."""
    if update.effective_chat is None or update.effective_message is None:
        return

    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    chat_state.show_reasoning = not chat_state.show_reasoning
    if not chat_state.show_reasoning and chat_state.active_reply_message_id is not None:
        replacement_text = _format_telegram_text(chat_state.active_answer_text or "Thinking...")
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=chat_state.active_reply_message_id,
                text=replacement_text,
                parse_mode=TELEGRAM_PARSE_MODE,
            )
        except BadRequest as exc:
            if "Message is not modified" not in str(exc):
                raise
    status = "on" if chat_state.show_reasoning else "off"
    await update.effective_message.reply_text(f"Transient reasoning preview is now {status}.")


async def handle_toggle_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle token usage details for the current Telegram chat."""
    if update.effective_chat is None or update.effective_message is None:
        return

    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    chat_state.show_token_usage = not chat_state.show_token_usage
    status = "on" if chat_state.show_token_usage else "off"
    await update.effective_message.reply_text(f"Token usage details are now {status}.")


async def handle_approval_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve or reject a pending tool request through an inline button press."""
    if update.callback_query is None or update.effective_chat is None or update.effective_user is None:
        return

    callback_query = update.callback_query
    parsed = _parse_approval_callback_data(callback_query.data)
    if parsed is None:
        await callback_query.answer("That approval action is no longer valid.")
        return

    approved, session_label = parsed
    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    chat_state.last_known_user = _build_user_profile(update.effective_user)
    _ensure_persisted_sessions_loaded(
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    entry = chat_state.sessions.get(session_label)
    if entry is None or entry.pending_approval is None:
        await callback_query.answer("That approval request is no longer pending.")
        if callback_query.message is not None:
            await callback_query.edit_message_reply_markup(reply_markup=None)
        return

    await callback_query.answer("Approved." if approved else "Rejected.")
    chat_state.active_session_label = entry.label
    approval_request = entry.pending_approval
    entry.pending_approval = None
    if callback_query.message is not None:
        resolution_text = (
            f"{entry.label} approval {'granted' if approved else 'rejected'}.\nContinuing the conversation..."
        )
        await callback_query.edit_message_text(_format_telegram_text(resolution_text))

    await _handle_agent_turn(
        update=update,
        context=context,
        entry=entry,
        prompt=AgentMessage(role="user", contents=[approval_request.to_function_approval_response(approved)]),
    )


async def handle_direct_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a private Telegram message with streaming agent output."""
    if (
        update.effective_chat is None
        or update.effective_message is None
        or update.effective_user is None
        or not update.effective_message.text
    ):
        return

    agent = context.application.bot_data["agent"]
    chat_state = _get_chat_state(context.application, update.effective_chat.id)
    chat_state.last_known_user = _build_user_profile(update.effective_user)
    _ensure_persisted_sessions_loaded(
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    if _has_active_turn(chat_state):
        await update.effective_message.reply_text("I'm still working on the previous request. Send /cancel to stop it.")
        return

    entry = _get_active_session_entry(
        agent=agent,
        application=context.application,
        chat_id=update.effective_chat.id,
        chat_state=chat_state,
        telegram_user_id=update.effective_user.id,
    )
    LOGGER.info("Handling Telegram message for chat_id=%s", update.effective_chat.id)
    await _handle_agent_turn(
        update=update,
        context=context,
        entry=entry,
        prompt=update.effective_message.text,
    )


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log callback failures and notify the Telegram user."""
    LOGGER.exception("Telegram sample handler failed", exc_info=context.error)
    telegram_update = update if isinstance(update, Update) else None
    if telegram_update is not None and telegram_update.effective_message is not None:
        await telegram_update.effective_message.reply_text(
            "Sorry, something went wrong while I was talking to the agent.",
            parse_mode=TELEGRAM_PARSE_MODE,
        )
