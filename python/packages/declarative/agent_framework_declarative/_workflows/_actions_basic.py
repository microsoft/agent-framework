# Copyright (c) Microsoft. All rights reserved.

"""Basic action handlers for variable manipulation and output.

This module implements handlers for:
- SetValue: Set a variable in the workflow state
- AppendValue: Append a value to a list variable
- SendActivity: Send text or attachments to the user
- EmitEvent: Emit a custom workflow event

Note: All handlers are defined as async generators (AsyncGenerator[WorkflowEvent, None])
for consistency with the ActionHandler protocol, even when they don't perform async
operations. This uniform interface allows the workflow executor to consume all handlers
the same way, and some handlers (like InvokeAzureAgent) genuinely require async for
network calls. The `return; yield` pattern makes a function an async generator without
actually yielding any events.
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, cast

from agent_framework import get_logger

from ._handlers import (
    ActionContext,
    AttachmentOutputEvent,
    CustomEvent,
    TextOutputEvent,
    WorkflowEvent,
    action_handler,
)

if TYPE_CHECKING:
    from ._state import WorkflowState

logger = get_logger("agent_framework.declarative.workflows.actions")


@action_handler("SetValue")
async def handle_set_value(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Set a value in the workflow state.

    Action schema:
        kind: SetValue
        path: Local.variableName  # or Workflow.Outputs.result
        value: =expression or literal value
    """
    path = ctx.action.get("path")
    value = ctx.action.get("value")

    if not path:
        logger.warning("SetValue action missing 'path' property")
        return

    # Evaluate the value if it's an expression
    evaluated_value = ctx.state.eval_if_expression(value)

    logger.debug(f"SetValue: {path} = {evaluated_value}")
    ctx.state.set(path, evaluated_value)

    return
    yield  # Make it a generator


@action_handler("SetVariable")
async def handle_set_variable(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Set a variable in the workflow state (.NET workflow format).

    This is an alias for SetValue with 'variable' instead of 'path'.

    Action schema:
        kind: SetVariable
        variable: Local.variableName
        value: =expression or literal value
    """
    variable = ctx.action.get("variable")
    value = ctx.action.get("value")

    if not variable:
        logger.warning("SetVariable action missing 'variable' property")
        return

    # Evaluate the value if it's an expression
    evaluated_value = ctx.state.eval_if_expression(value)

    # Use .NET-style variable names directly (Local.X, System.X, Workflow.X)
    path = _normalize_variable_path(variable)

    logger.debug(f"SetVariable: {variable} ({path}) = {evaluated_value}")
    ctx.state.set(path, evaluated_value)

    return
    yield  # Make it a generator


def _normalize_variable_path(variable: str) -> str:
    """Normalize variable names to ensure they have a scope prefix.

    Args:
        variable: Variable name like 'Local.X' or 'System.ConversationId'

    Returns:
        The variable path with a scope prefix (defaults to Local if none provided)
    """
    if variable.startswith(("Local.", "System.", "Workflow.", "Agent.", "Conversation.")):
        # Already has a proper namespace
        return variable
    if "." in variable:
        # Has some namespace, use as-is
        return variable
    # Default to Local scope
    return "Local." + variable


@action_handler("AppendValue")
async def handle_append_value(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Append a value to a list in the workflow state.

    Action schema:
        kind: AppendValue
        path: Local.results
        value: =expression or literal value
    """
    path = ctx.action.get("path")
    value = ctx.action.get("value")

    if not path:
        logger.warning("AppendValue action missing 'path' property")
        return

    # Evaluate the value if it's an expression
    evaluated_value = ctx.state.eval_if_expression(value)

    logger.debug(f"AppendValue: {path} += {evaluated_value}")
    ctx.state.append(path, evaluated_value)

    return
    yield  # Make it a generator


@action_handler("SendActivity")
async def handle_send_activity(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Send text or attachments to the user.

    Action schema (object form):
        kind: SendActivity
        activity:
            text: =expression or literal text
            attachments:
              - content: ...
                contentType: text/plain

    Action schema (simple form):
        kind: SendActivity
        activity: =expression or literal text
    """
    activity = ctx.action.get("activity", {})

    # Handle simple string form
    if isinstance(activity, str):
        evaluated_text = ctx.state.eval_if_expression(activity)
        if evaluated_text:
            logger.debug(
                "SendActivity: text = %s", evaluated_text[:100] if len(str(evaluated_text)) > 100 else evaluated_text
            )
            yield TextOutputEvent(text=str(evaluated_text))
        return

    # Handle object form - text output
    text = activity.get("text")
    if text:
        evaluated_text = ctx.state.eval_if_expression(text)
        if evaluated_text:
            logger.debug(
                "SendActivity: text = %s", evaluated_text[:100] if len(str(evaluated_text)) > 100 else evaluated_text
            )
            yield TextOutputEvent(text=str(evaluated_text))

    # Handle attachments
    attachments = activity.get("attachments", [])
    for attachment in attachments:
        content = attachment.get("content")
        content_type = attachment.get("contentType", "application/octet-stream")

        if content:
            evaluated_content = ctx.state.eval_if_expression(content)
            logger.debug(f"SendActivity: attachment type={content_type}")
            yield AttachmentOutputEvent(content=evaluated_content, content_type=content_type)


@action_handler("EmitEvent")
async def handle_emit_event(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Emit a custom workflow event.

    Action schema:
        kind: EmitEvent
        event:
            name: eventName
            data: =expression or literal data
    """
    event_def = ctx.action.get("event", {})
    name = event_def.get("name")
    data = event_def.get("data")

    if not name:
        logger.warning("EmitEvent action missing 'event.name' property")
        return

    # Evaluate data if it's an expression
    evaluated_data = ctx.state.eval_if_expression(data)

    logger.debug(f"EmitEvent: {name} = {evaluated_data}")
    yield CustomEvent(name=name, data=evaluated_data)


def _evaluate_dict_values(d: dict[str, Any], state: "WorkflowState") -> dict[str, Any]:
    """Recursively evaluate PowerFx expressions in a dictionary.

    Args:
        d: Dictionary that may contain expression values
        state: The workflow state for expression evaluation

    Returns:
        Dictionary with all expressions evaluated
    """
    result: dict[str, Any] = {}
    for key, value in d.items():
        if isinstance(value, str):
            result[key] = state.eval_if_expression(value)
        elif isinstance(value, dict):
            result[key] = _evaluate_dict_values(cast(dict[str, Any], value), state)
        elif isinstance(value, list):
            evaluated_list: list[Any] = []
            for list_item in value:
                if isinstance(list_item, dict):
                    evaluated_list.append(_evaluate_dict_values(cast(dict[str, Any], list_item), state))
                elif isinstance(list_item, str):
                    evaluated_list.append(state.eval_if_expression(list_item))
                else:
                    evaluated_list.append(list_item)
            result[key] = evaluated_list
        else:
            result[key] = value
    return result


@action_handler("SetTextVariable")
async def handle_set_text_variable(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Set a text variable with string interpolation support.

    This is similar to SetVariable but supports multi-line text with
    {Local.Variable} style interpolation.

    Action schema:
        kind: SetTextVariable
        variable: Local.myText
        value: |-
          Multi-line text with {Local.Variable} interpolation
          and more content here.
    """
    variable = ctx.action.get("variable")
    value = ctx.action.get("value")

    if not variable:
        logger.warning("SetTextVariable action missing 'variable' property")
        return

    # Evaluate the value - handle string interpolation
    if isinstance(value, str):
        evaluated_value = _interpolate_string(value, ctx.state)
    else:
        evaluated_value = ctx.state.eval_if_expression(value)

    path = _normalize_variable_path(variable)

    logger.debug(f"SetTextVariable: {variable} ({path}) = {str(evaluated_value)[:100]}")
    ctx.state.set(path, evaluated_value)

    return
    yield  # Make it a generator


@action_handler("SetMultipleVariables")
async def handle_set_multiple_variables(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Set multiple variables at once.

    Action schema:
        kind: SetMultipleVariables
        variables:
          - variable: Local.var1
            value: value1
          - variable: Local.var2
            value: =expression
    """
    variables = ctx.action.get("variables", [])

    for var_def in variables:
        variable = var_def.get("variable")
        value = var_def.get("value")

        if not variable:
            logger.warning("SetMultipleVariables: variable entry missing 'variable' property")
            continue

        evaluated_value = ctx.state.eval_if_expression(value)
        path = _normalize_variable_path(variable)

        logger.debug(f"SetMultipleVariables: {variable} ({path}) = {evaluated_value}")
        ctx.state.set(path, evaluated_value)

    return
    yield  # Make it a generator


@action_handler("ResetVariable")
async def handle_reset_variable(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Reset a variable to its default/blank state.

    Action schema:
        kind: ResetVariable
        variable: Local.variableName
    """
    variable = ctx.action.get("variable")

    if not variable:
        logger.warning("ResetVariable action missing 'variable' property")
        return

    path = _normalize_variable_path(variable)

    logger.debug(f"ResetVariable: {variable} ({path}) = None")
    ctx.state.set(path, None)

    return
    yield  # Make it a generator


@action_handler("ClearAllVariables")
async def handle_clear_all_variables(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Clear all turn-scoped variables.

    Action schema:
        kind: ClearAllVariables
    """
    logger.debug("ClearAllVariables: clearing turn scope")
    ctx.state.reset_local()

    return
    yield  # Make it a generator


@action_handler("CreateConversation")
async def handle_create_conversation(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Create a new conversation context.

    Action schema (.NET style):
        kind: CreateConversation
        conversationId: Local.myConversationId  # Variable to store the generated ID

    The conversationId parameter is the OUTPUT variable where the generated
    conversation ID will be stored. This matches .NET behavior where:
    - A unique conversation ID is always auto-generated
    - The conversationId parameter specifies where to store it
    """
    import uuid

    conversation_id_var = ctx.action.get("conversationId")

    # Always generate a unique ID (.NET behavior)
    generated_id = str(uuid.uuid4())

    # Store conversation in state
    conversations: dict[str, Any] = ctx.state.get("System.conversations") or {}
    conversations[generated_id] = {
        "id": generated_id,
        "messages": [],
        "created_at": None,  # Could add timestamp
    }
    ctx.state.set("System.conversations", conversations)

    logger.debug(f"CreateConversation: created {generated_id}")

    # Store the generated ID in the specified variable (.NET style output binding)
    if conversation_id_var:
        output_path = _normalize_variable_path(conversation_id_var)
        ctx.state.set(output_path, generated_id)
        logger.debug(f"CreateConversation: bound to {output_path} = {generated_id}")

    # Also handle legacy output binding for backwards compatibility
    output = ctx.action.get("output", {})
    output_var = output.get("conversationId")
    if output_var:
        output_path = _normalize_variable_path(output_var)
        ctx.state.set(output_path, generated_id)
        logger.debug(f"CreateConversation: legacy output bound to {output_path}")

    return
    yield  # Make it a generator


@action_handler("AddConversationMessage")
async def handle_add_conversation_message(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Add a message to a conversation.

    Action schema:
        kind: AddConversationMessage
        conversationId: =expression or variable reference
        message:
          role: user | assistant | system
          content: =expression or literal text
    """
    conversation_id = ctx.action.get("conversationId")
    message_def = ctx.action.get("message", {})

    if not conversation_id:
        logger.warning("AddConversationMessage missing 'conversationId' property")
        return

    # Evaluate conversation ID
    evaluated_id = ctx.state.eval_if_expression(conversation_id)

    # Evaluate message content
    role = message_def.get("role", "user")
    content = message_def.get("content", "")

    evaluated_content = ctx.state.eval_if_expression(content)
    if isinstance(evaluated_content, str):
        evaluated_content = _interpolate_string(evaluated_content, ctx.state)

    # Get or create conversation
    conversations: dict[str, Any] = ctx.state.get("System.conversations") or {}
    if evaluated_id not in conversations:
        conversations[evaluated_id] = {"id": evaluated_id, "messages": []}

    # Add message
    message: dict[str, Any] = {"role": role, "content": evaluated_content}
    conv_entry: dict[str, Any] = dict(conversations[evaluated_id])
    messages_list: list[Any] = list(conv_entry.get("messages", []))
    messages_list.append(message)
    conv_entry["messages"] = messages_list
    conversations[evaluated_id] = conv_entry
    ctx.state.set("System.conversations", conversations)

    # Also add to global conversation state
    ctx.state.add_conversation_message(message)

    logger.debug(f"AddConversationMessage: added {role} message to {evaluated_id}")

    return
    yield  # Make it a generator


@action_handler("CopyConversationMessages")
async def handle_copy_conversation_messages(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Copy messages from one conversation to another.

    Action schema:
        kind: CopyConversationMessages
        sourceConversationId: =expression
        targetConversationId: =expression
        count: 10  # optional, number of messages to copy
    """
    source_id = ctx.action.get("sourceConversationId")
    target_id = ctx.action.get("targetConversationId")
    count = ctx.action.get("count")

    if not source_id or not target_id:
        logger.warning("CopyConversationMessages missing source or target conversation ID")
        return

    # Evaluate IDs
    evaluated_source = ctx.state.eval_if_expression(source_id)
    evaluated_target = ctx.state.eval_if_expression(target_id)

    # Get conversations
    conversations: dict[str, Any] = ctx.state.get("System.conversations") or {}

    source_conv: dict[str, Any] = conversations.get(evaluated_source, {})
    source_messages: list[Any] = source_conv.get("messages", [])

    # Limit messages if count specified
    if count is not None:
        source_messages = source_messages[-count:]

    # Get or create target conversation
    if evaluated_target not in conversations:
        conversations[evaluated_target] = {"id": evaluated_target, "messages": []}

    # Copy messages
    target_entry: dict[str, Any] = dict(conversations[evaluated_target])
    target_messages: list[Any] = list(target_entry.get("messages", []))
    target_messages.extend(source_messages)
    target_entry["messages"] = target_messages
    conversations[evaluated_target] = target_entry
    ctx.state.set("System.conversations", conversations)

    logger.debug(
        "CopyConversationMessages: copied %d messages from %s to %s",
        len(source_messages),
        evaluated_source,
        evaluated_target,
    )

    return
    yield  # Make it a generator


@action_handler("RetrieveConversationMessages")
async def handle_retrieve_conversation_messages(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Retrieve messages from a conversation and store in a variable.

    Action schema:
        kind: RetrieveConversationMessages
        conversationId: =expression
        output:
          messages: Local.myMessages
        count: 10  # optional
    """
    conversation_id = ctx.action.get("conversationId")
    output = ctx.action.get("output", {})
    count = ctx.action.get("count")

    if not conversation_id:
        logger.warning("RetrieveConversationMessages missing 'conversationId' property")
        return

    # Evaluate conversation ID
    evaluated_id = ctx.state.eval_if_expression(conversation_id)

    # Get messages
    conversations: dict[str, Any] = ctx.state.get("System.conversations") or {}
    conv: dict[str, Any] = conversations.get(evaluated_id, {})
    messages: list[Any] = conv.get("messages", [])

    # Limit messages if count specified
    if count is not None:
        messages = messages[-count:]

    # Handle output binding
    output_var = output.get("messages")
    if output_var:
        output_path = _normalize_variable_path(output_var)
        ctx.state.set(output_path, messages)
        logger.debug(f"RetrieveConversationMessages: bound {len(messages)} messages to {output_path}")

    return
    yield  # Make it a generator


def _interpolate_string(text: str, state: "WorkflowState") -> str:
    """Interpolate {Variable.Path} references in a string.

    Args:
        text: Text that may contain {Variable.Path} references
        state: The workflow state for variable lookup

    Returns:
        Text with variables interpolated
    """
    import re

    def replace_var(match: re.Match[str]) -> str:
        var_path: str = match.group(1)
        # Map .NET style to Python style
        path = _normalize_variable_path(var_path)
        value = state.get(path)
        return str(value) if value is not None else ""

    # Match {Variable.Path} patterns
    pattern = r"\{([A-Za-z][A-Za-z0-9_.]*)\}"
    return re.sub(pattern, replace_var, text)
