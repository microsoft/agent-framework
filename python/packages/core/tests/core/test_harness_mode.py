# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json

import pytest

from agent_framework import (
    DEFAULT_MODE_SOURCE_ID,
    Agent,
    AgentModeProvider,
    AgentSession,
    FunctionTool,
    Message,
    SupportsChatGetResponse,
    get_agent_mode,
    set_agent_mode,
)
from agent_framework._harness._mode import DEFAULT_MODE_INSTRUCTIONS, DEFAULT_MODE_MAP


def _tool_by_name(tools: list[object], name: str) -> object:
    """Return the tool with the requested name from a prepared tool list."""
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool
    raise AssertionError(f"Tool {name!r} was not found.")


def test_get_and_set_agent_mode_manage_session_state() -> None:
    """Mode helpers should initialize session state, normalize values, and validate modes."""
    session = AgentSession(session_id="session-1")

    assert get_agent_mode(session) == "plan"
    assert session.state[DEFAULT_MODE_SOURCE_ID] == {"current_mode": "plan"}
    assert set_agent_mode(session, " execute ") == "execute"
    assert get_agent_mode(session) == "execute"

    custom_session = AgentSession(session_id="session-2")
    assert (
        get_agent_mode(
            custom_session,
            default_mode="draft",
            available_modes=("draft", "final"),
        )
        == "draft"
    )

    with pytest.raises(ValueError, match="Invalid mode"):
        set_agent_mode(session, "ship")


def test_agent_mode_helpers_reject_non_dict_provider_state() -> None:
    """Mode helpers should not overwrite unrelated non-dict session state."""
    session = AgentSession(session_id="session-1")
    session.state[DEFAULT_MODE_SOURCE_ID] = "unrelated state"

    with pytest.raises(TypeError, match="source_id 'agent_mode'.*str"):
        get_agent_mode(session)

    assert session.state[DEFAULT_MODE_SOURCE_ID] == "unrelated state"


def test_agent_mode_context_provider_validates_configuration() -> None:
    """Mode provider should validate configuration; graduated types carry no experimental metadata."""
    with pytest.raises(ValueError, match="at least one mode"):
        AgentModeProvider(mode_instructions={})

    with pytest.raises(ValueError, match="Invalid mode"):
        AgentModeProvider(default_mode="ship")

    for graduated in (AgentModeProvider, get_agent_mode, set_agent_mode):
        assert not hasattr(graduated, "__feature_id__")
    assert AgentModeProvider.__doc__ is not None
    assert ".. warning:: Experimental" not in AgentModeProvider.__doc__


async def test_external_read_with_provider_config_preserves_nondefault_mode(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """A pre-run external mode read must honor the provider's configured default, not the built-in one.

    Regression test for the harness console bug where ``configure_run_options`` read the mode with a
    bare ``get_agent_mode(session)`` before the agent ran. Because ``get_agent_mode`` persists the
    resolved default into session state, the built-in ``plan`` default was stored and the provider —
    configured with ``default_mode="execute"`` — then read back ``plan``, so the agent ran in plan
    mode while the console showed execute. Threading the provider's configuration into the read keeps
    the two in sync.
    """
    provider = AgentModeProvider(default_mode="execute")

    # A bare read (the original buggy call) would resolve and persist the built-in ``plan`` default,
    # which does not match the provider's configured ``execute`` default.
    poisoned_session = AgentSession(session_id="poisoned")
    assert get_agent_mode(poisoned_session) == "plan"
    agent = Agent(client=chat_client_base, context_providers=[provider])
    _, poisoned_options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=poisoned_session,
        input_messages=[Message(role="user", contents=["Go"])],
    )
    assert "You are currently operating in the plan mode." in poisoned_options["instructions"]

    # Reading with the provider's own configuration resolves and persists ``execute``, so the
    # provider injects execute-mode instructions on the run.
    session = AgentSession(session_id="configured")
    assert (
        get_agent_mode(
            session,
            source_id=provider.source_id,
            default_mode=provider.default_mode,
            available_modes=provider.available_modes,
        )
        == "execute"
    )
    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Go"])],
    )
    assert "You are currently operating in the execute mode." in options["instructions"]


async def test_agent_mode_context_provider_normalizes_custom_modes(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Mode provider should accept differently-cased custom modes and display configured names."""
    session = AgentSession(session_id="session-1")
    provider = AgentModeProvider(
        default_mode="Draft", mode_instructions={"Draft": "Draft it.", "Final": "Finalize it."}
    )
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Start drafting"])],
    )
    instructions = options["instructions"]
    assert isinstance(instructions, str)
    assert "#### Draft" in instructions
    assert "Draft it." in instructions
    assert "#### Final" in instructions
    assert "Finalize it." in instructions
    assert "You are currently operating in the draft mode." in instructions

    assert (
        get_agent_mode(session, source_id=provider.source_id, default_mode="Draft", available_modes=("Draft", "Final"))
        == "draft"
    )
    assert set_agent_mode(session, "draft", source_id=provider.source_id, available_modes=("Draft", "Final")) == "draft"
    assert (
        get_agent_mode(session, source_id=provider.source_id, default_mode="Draft", available_modes=("Draft", "Final"))
        == "draft"
    )


async def test_agent_mode_context_provider_serializes_tool_outputs_as_json(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Mode tools should serialize JSON correctly for mode names with quotes."""
    session = AgentSession(session_id="session-1")
    mode_name = 'edit "preview"'
    provider = AgentModeProvider(default_mode=mode_name, mode_instructions={mode_name: "Preview edits."})
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Preview edits"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)
    get_mode_tool = _tool_by_name(tools, "mode_get")
    set_mode_tool = _tool_by_name(tools, "mode_set")

    initial_mode = await get_mode_tool.invoke()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert json.loads(initial_mode[0].text) == {"mode": mode_name}

    set_result = await set_mode_tool.invoke(arguments={"mode": mode_name})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert json.loads(set_result[0].text) == {"mode": mode_name, "message": f"Mode changed to '{mode_name}'."}


async def test_agent_mode_context_provider_updates_agent_mode(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Mode provider tools should read and write session-backed mode state."""
    session = AgentSession(session_id="session-1")
    provider = AgentModeProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Start planning"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)
    instructions = options["instructions"]
    assert isinstance(instructions, str)
    assert "## Agent Mode" in instructions
    assert "Use the mode_set tool to switch between modes as your work progresses." in instructions
    assert "ask clarifying questions, discuss options, and get user approval before proceeding" in instructions
    assert "If you encounter ambiguity" in instructions
    assert "You are currently operating in the plan mode." in instructions

    get_mode_tool = _tool_by_name(tools, "mode_get")
    set_mode_tool = _tool_by_name(tools, "mode_set")

    initial_mode = await get_mode_tool.invoke()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert json.loads(initial_mode[0].text) == {"mode": "plan"}

    set_result = await set_mode_tool.invoke(arguments={"mode": "execute"})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert json.loads(set_result[0].text) == {"mode": "execute", "message": "Mode changed to 'execute'."}
    assert get_agent_mode(session, source_id=provider.source_id) == "execute"
    assert set_agent_mode(session, "plan", source_id=provider.source_id) == "plan"


@pytest.mark.parametrize("expose_mode_set", [True, False])
@pytest.mark.parametrize("expose_mode_get", [True, False])
async def test_agent_mode_provider_tool_exposure(
    chat_client_base: SupportsChatGetResponse, expose_mode_set: bool, expose_mode_get: bool
) -> None:
    """Tool exposure must match built-in guidance without disabling the mode workflow."""
    session = AgentSession(session_id="session-1")
    provider = AgentModeProvider(expose_mode_set=expose_mode_set, expose_mode_get=expose_mode_get)
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Start planning"])],
    )
    tools: list[object] = options.get("tools") or []
    expected_names = [
        name for name, exposed in (("mode_set", expose_mode_set), ("mode_get", expose_mode_get)) if exposed
    ]
    assert [tool.name for tool in tools if isinstance(tool, FunctionTool)] == expected_names
    instructions = options["instructions"]
    assert isinstance(instructions, str)
    assert ("mode_set" in instructions) == expose_mode_set
    assert ("mode_get" in instructions) == expose_mode_get
    assert "### Mandatory Mode based Workflow" in instructions
    assert "get user approval before proceeding" in instructions
    assert "You are currently operating in the plan mode." in instructions
    assert get_agent_mode(session) == "plan"
    if not expose_mode_set:
        assert "only after the mode has changed" in instructions
    for mode_tool in tools:
        assert isinstance(mode_tool, FunctionTool)
        assert mode_tool.approval_mode == "never_require"
        if mode_tool.name == "mode_set":
            result = await mode_tool.invoke(arguments={"mode": "execute"})
            assert result[0].text is not None
            assert json.loads(result[0].text) == {"mode": "execute", "message": "Mode changed to 'execute'."}
        else:
            result = await mode_tool.invoke()
            assert result[0].text is not None
            assert json.loads(result[0].text) == {"mode": "execute" if expose_mode_set else "plan"}


@pytest.mark.parametrize("instructions", [None, ""])
def test_agent_mode_provider_preserves_default_instructions(instructions: str | None) -> None:
    """Suppression on one provider must not alter another provider's defaults."""
    AgentModeProvider(expose_mode_set=False, expose_mode_get=False)
    provider = AgentModeProvider(instructions=instructions)
    mode_lines = "".join(f"#### {name}\n\n{text}\n\n" for name, text in DEFAULT_MODE_MAP.items())
    expected = DEFAULT_MODE_INSTRUCTIONS.replace("{available_modes}", mode_lines).replace("{current_mode}", "plan")
    assert provider._build_instructions("plan") == expected  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize("custom_instructions", [True, False])
@pytest.mark.parametrize("custom_modes", [True, False])
def test_agent_mode_provider_preserves_custom_instructions(custom_instructions: bool, custom_modes: bool) -> None:
    """Only built-in guidance should be adapted; caller text still expands placeholders."""
    mode_text = "Custom mode_get and mode_set guidance for {current_mode}."
    mode_map = {"draft": mode_text} if custom_modes else None
    instructions = "Use update_mode, not mode_set or mode_get. {current_mode}\n{available_modes}"
    provider = AgentModeProvider(
        expose_mode_set=False,
        expose_mode_get=False,
        instructions=instructions if custom_instructions else None,
        mode_instructions=mode_map,
    )
    current_mode = "draft" if custom_modes else "plan"
    rendered = provider._build_instructions(current_mode)  # pyright: ignore[reportPrivateUsage]
    if custom_modes:
        assert mode_map == {"draft": mode_text}
        assert f"Custom mode_get and mode_set guidance for {current_mode}." in rendered
    if custom_instructions:
        assert rendered.startswith(f"Use update_mode, not mode_set or mode_get. {current_mode}\n")
    assert "{available_modes}" not in rendered
    assert "{current_mode}" not in rendered
    if not custom_modes and not custom_instructions:
        assert "mode_set" not in rendered
        assert "mode_get" not in rendered


async def test_agent_mode_provider_hidden_tools_preserve_state_and_notifications(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """State and one-shot external notifications must survive even with no mode tools."""
    session = AgentSession(session_id="session-1")
    provider = AgentModeProvider(
        source_id="ui_mode", default_mode="execute", expose_mode_set=False, expose_mode_get=False
    )
    agent = Agent(client=chat_client_base, context_providers=[provider])
    _, first_options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Start"])],
    )
    assert not first_options.get("tools")
    assert "You are currently operating in the execute mode." in first_options["instructions"]
    assert get_agent_mode(session, source_id=provider.source_id) == "execute"
    set_agent_mode(session, "plan", source_id=provider.source_id)

    changed_context, changed_options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Continue"])],
    )
    assert "You are currently operating in the plan mode." in changed_options["instructions"]
    notifications = changed_context.context_messages.get(provider.source_id, [])
    assert len(notifications) == 1
    assert notifications[0].role == "user"
    assert 'from "execute" to "plan"' in notifications[0].text
    assert "previous_mode_for_notification" not in session.state[provider.source_id]

    set_agent_mode(session, "plan", source_id=provider.source_id)
    unchanged_context, _ = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Continue planning"])],
    )
    assert unchanged_context.context_messages.get(provider.source_id, []) == []

    reconfigured_provider = AgentModeProvider(source_id=provider.source_id, default_mode="execute")
    reconfigured_agent = Agent(client=chat_client_base, context_providers=[reconfigured_provider])
    _, restored_options = await reconfigured_agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Status"])],
    )
    assert "You are currently operating in the plan mode." in restored_options["instructions"]
    assert get_agent_mode(session, source_id=provider.source_id) == "plan"
    assert DEFAULT_MODE_SOURCE_ID not in session.state


def test_default_mode_falls_back_to_first_available_mode() -> None:
    """When ``default_mode`` is omitted, helpers and provider should use the first configured mode."""
    session = AgentSession(session_id="session-1")

    assert get_agent_mode(session, available_modes=("draft", "final")) == "draft"

    provider = AgentModeProvider(mode_instructions={"Draft": "Draft it.", "Final": "Finalize it."})
    assert provider.default_mode == "draft"


def test_get_agent_mode_falls_back_when_stored_mode_not_in_available_modes() -> None:
    """A previously persisted mode that is no longer configured should be reset to the default."""
    session = AgentSession(session_id="session-1")
    set_agent_mode(session, "execute")
    assert session.state[DEFAULT_MODE_SOURCE_ID]["current_mode"] == "execute"

    # Reconfigure with a smaller mode set that no longer includes "execute".
    current = get_agent_mode(session, default_mode="draft", available_modes=("draft", "final"))
    assert current == "draft"
    assert session.state[DEFAULT_MODE_SOURCE_ID]["current_mode"] == "draft"


def test_set_agent_mode_records_previous_mode_for_external_change_notification() -> None:
    """External mode changes via ``set_agent_mode`` should record the previous mode for notification."""
    session = AgentSession(session_id="session-1")
    set_agent_mode(session, "plan")
    set_agent_mode(session, "execute")

    assert session.state[DEFAULT_MODE_SOURCE_ID]["current_mode"] == "execute"
    assert session.state[DEFAULT_MODE_SOURCE_ID]["previous_mode_for_notification"] == "plan"


def test_set_agent_mode_no_op_does_not_record_previous_mode() -> None:
    """Setting the same mode should not queue a notification."""
    session = AgentSession(session_id="session-1")
    set_agent_mode(session, "plan")
    set_agent_mode(session, "plan")

    assert "previous_mode_for_notification" not in session.state[DEFAULT_MODE_SOURCE_ID]


def test_set_agent_mode_can_skip_external_change_notification() -> None:
    """Agent-invoked replacement tools should be able to avoid a redundant notification."""
    session = AgentSession(session_id="session-1")
    set_agent_mode(session, "plan")
    set_agent_mode(session, "execute", notify=False)

    assert get_agent_mode(session) == "execute"
    assert "previous_mode_for_notification" not in session.state[DEFAULT_MODE_SOURCE_ID]


def test_set_agent_mode_without_notification_clears_pending_notification() -> None:
    """An agent-observed update should replace pending external transition context."""
    session = AgentSession(session_id="session-1")
    set_agent_mode(session, "plan")
    set_agent_mode(session, "execute")
    assert session.state[DEFAULT_MODE_SOURCE_ID]["previous_mode_for_notification"] == "plan"

    set_agent_mode(session, "plan", notify=False)

    assert get_agent_mode(session) == "plan"
    assert "previous_mode_for_notification" not in session.state[DEFAULT_MODE_SOURCE_ID]


async def test_agent_mode_provider_injects_user_message_after_external_change(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """External mode changes should inject a user message announcing the switch on the next run."""
    session = AgentSession(session_id="session-1")
    provider = AgentModeProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    # First run: agent uses mode_set tool to switch to execute. The tool path must NOT queue a
    # notification because the agent already saw its own tool call in the chat history.
    _, first_options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Plan first."])],
    )
    set_mode_tool = _tool_by_name(first_options["tools"], "mode_set")
    await set_mode_tool.invoke(arguments={"mode": "execute"})  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert "previous_mode_for_notification" not in session.state[provider.source_id]

    # Now an external caller (e.g., a /mode slash command) switches the mode back to plan.
    set_agent_mode(session, "plan", source_id=provider.source_id)
    assert session.state[provider.source_id]["previous_mode_for_notification"] == "execute"

    # Next run: the provider should inject a user message announcing the change and clear the flag.
    second_context, second_options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Carry on."])],
    )
    instructions = second_options["instructions"]
    assert isinstance(instructions, str)
    assert "You are currently operating in the plan mode." in instructions

    notification_messages = [message for message in second_context.context_messages.get(provider.source_id, [])]
    assert len(notification_messages) == 1
    assert notification_messages[0].role == "user"
    assert "Mode changed" in notification_messages[0].text
    assert '"execute"' in notification_messages[0].text
    assert '"plan"' in notification_messages[0].text
    assert "previous_mode_for_notification" not in session.state[provider.source_id]

    # Third run with no further external change must not re-inject the notification.
    third_context, _ = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["Status?"])],
    )
    assert third_context.context_messages.get(provider.source_id, []) == []
