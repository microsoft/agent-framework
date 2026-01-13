# Copyright (c) Microsoft. All rights reserved.

"""Control flow action handlers for declarative workflows.

This module implements handlers for:
- Foreach: Iterate over a collection and execute nested actions
- If: Conditional branching
- Switch: Multi-way branching based on value matching
- RepeatUntil: Loop until a condition is met
- BreakLoop: Exit the current loop
- ContinueLoop: Skip to the next iteration
"""

from collections.abc import AsyncGenerator

from agent_framework import get_logger

from ._handlers import (
    ActionContext,
    LoopControlSignal,
    WorkflowEvent,
    action_handler,
)

logger = get_logger("agent_framework.declarative.workflows.actions")


@action_handler("Foreach")
async def handle_foreach(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:
    """Iterate over a collection and execute nested actions for each item.

    Action schema:
        kind: Foreach
        source: =expression returning a collection
        itemName: itemVariable  # optional, defaults to 'item'
        indexName: indexVariable  # optional, defaults to 'index'
        actions:
          - kind: ...
    """
    source_expr = ctx.action.get("source")
    item_name = ctx.action.get("itemName", "item")
    index_name = ctx.action.get("indexName", "index")
    actions = ctx.action.get("actions", [])

    if not source_expr:
        logger.warning("Foreach action missing 'source' property")
        return

    # Evaluate the source collection
    collection = ctx.state.eval_if_expression(source_expr)

    if collection is None:
        logger.debug("Foreach: source evaluated to None, skipping")
        return

    if not hasattr(collection, "__iter__"):
        logger.warning(f"Foreach: source is not iterable: {type(collection).__name__}")
        return

    collection_len = len(list(collection)) if hasattr(collection, "__len__") else "?"
    logger.debug(f"Foreach: iterating over {collection_len} items")

    # Iterate over the collection
    for index, item in enumerate(collection):
        # Set loop variables in the Local scope
        ctx.state.set(f"Local.{item_name}", item)
        ctx.state.set(f"Local.{index_name}", index)

        # Execute nested actions
        try:
            async for event in ctx.execute_actions(actions, ctx.state):
                # Check for loop control signals
                if isinstance(event, LoopControlSignal):
                    if event.signal_type == "break":
                        logger.debug(f"Foreach: break signal received at index {index}")
                        return
                    elif event.signal_type == "continue":
                        logger.debug(f"Foreach: continue signal received at index {index}")
                        break  # Break inner loop to continue outer
                else:
                    yield event
        except StopIteration:
            # Continue signal was raised
            continue


@action_handler("If")
async def handle_if(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:
    """Conditional branching based on a condition expression.

    Action schema:
        kind: If
        condition: =boolean expression
        then:
          - kind: ...  # actions if condition is true
        else:
          - kind: ...  # actions if condition is false (optional)
    """
    condition_expr = ctx.action.get("condition")
    then_actions = ctx.action.get("then", [])
    else_actions = ctx.action.get("else", [])

    if condition_expr is None:
        logger.warning("If action missing 'condition' property")
        return

    # Evaluate the condition
    condition_result = ctx.state.eval_if_expression(condition_expr)

    # Coerce to boolean
    is_truthy = bool(condition_result)

    logger.debug(
        "If: condition '%s' evaluated to %s",
        condition_expr[:50] if len(str(condition_expr)) > 50 else condition_expr,
        is_truthy,
    )

    # Execute the appropriate branch
    actions_to_execute = then_actions if is_truthy else else_actions

    async for event in ctx.execute_actions(actions_to_execute, ctx.state):
        yield event


@action_handler("Switch")
async def handle_switch(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:
    """Multi-way branching based on value matching.

    Action schema:
        kind: Switch
        value: =expression to match
        cases:
          - match: value1
            actions:
              - kind: ...
          - match: value2
            actions:
              - kind: ...
        default:
          - kind: ...  # optional default actions
    """
    value_expr = ctx.action.get("value")
    cases = ctx.action.get("cases", [])
    default_actions = ctx.action.get("default", [])

    if not value_expr:
        logger.warning("Switch action missing 'value' property")
        return

    # Evaluate the switch value
    switch_value = ctx.state.eval_if_expression(value_expr)

    logger.debug(f"Switch: value = {switch_value}")

    # Find matching case
    matched_actions = None
    for case in cases:
        match_value = ctx.state.eval_if_expression(case.get("match"))
        if switch_value == match_value:
            matched_actions = case.get("actions", [])
            logger.debug(f"Switch: matched case '{match_value}'")
            break

    # Use default if no match found
    if matched_actions is None:
        matched_actions = default_actions
        logger.debug("Switch: using default case")

    # Execute matched actions
    async for event in ctx.execute_actions(matched_actions, ctx.state):
        yield event


@action_handler("RepeatUntil")
async def handle_repeat_until(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:
    """Loop until a condition becomes true.

    Action schema:
        kind: RepeatUntil
        condition: =boolean expression (loop exits when true)
        maxIterations: 100  # optional safety limit
        actions:
          - kind: ...
    """
    condition_expr = ctx.action.get("condition")
    max_iterations = ctx.action.get("maxIterations", 100)
    actions = ctx.action.get("actions", [])

    if condition_expr is None:
        logger.warning("RepeatUntil action missing 'condition' property")
        return

    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        ctx.state.set("Local.iteration", iteration)

        logger.debug(f"RepeatUntil: iteration {iteration}")

        # Execute loop body
        should_break = False
        async for event in ctx.execute_actions(actions, ctx.state):
            if isinstance(event, LoopControlSignal):
                if event.signal_type == "break":
                    logger.debug(f"RepeatUntil: break signal received at iteration {iteration}")
                    should_break = True
                    break
                elif event.signal_type == "continue":
                    logger.debug(f"RepeatUntil: continue signal received at iteration {iteration}")
                    break
            else:
                yield event

        if should_break:
            break

        # Check exit condition
        condition_result = ctx.state.eval_if_expression(condition_expr)
        if bool(condition_result):
            logger.debug(f"RepeatUntil: condition met after {iteration} iterations")
            break

    if iteration >= max_iterations:
        logger.warning(f"RepeatUntil: reached max iterations ({max_iterations})")


@action_handler("BreakLoop")
async def handle_break_loop(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Signal to break out of the current loop.

    Action schema:
        kind: BreakLoop
    """
    logger.debug("BreakLoop: signaling break")
    yield LoopControlSignal(signal_type="break")


@action_handler("ContinueLoop")
async def handle_continue_loop(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Signal to continue to the next iteration of the current loop.

    Action schema:
        kind: ContinueLoop
    """
    logger.debug("ContinueLoop: signaling continue")
    yield LoopControlSignal(signal_type="continue")


@action_handler("ConditionGroup")
async def handle_condition_group(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:
    """Multi-condition branching (like else-if chains).

    Evaluates conditions in order and executes the first matching condition's actions.
    If no conditions match and elseActions is provided, executes those.

    Action schema:
        kind: ConditionGroup
        conditions:
          - condition: =boolean expression
            actions:
              - kind: ...
          - condition: =another expression
            actions:
              - kind: ...
        elseActions:
          - kind: ...  # optional, executed if no conditions match
    """
    conditions = ctx.action.get("conditions", [])
    else_actions = ctx.action.get("elseActions", [])

    matched = False
    for condition_def in conditions:
        condition_expr = condition_def.get("condition")
        actions = condition_def.get("actions", [])

        if condition_expr is None:
            logger.warning("ConditionGroup condition missing 'condition' property")
            continue

        # Evaluate the condition
        condition_result = ctx.state.eval_if_expression(condition_expr)
        is_truthy = bool(condition_result)

        logger.debug(
            "ConditionGroup: condition '%s' evaluated to %s",
            str(condition_expr)[:50] if len(str(condition_expr)) > 50 else condition_expr,
            is_truthy,
        )

        if is_truthy:
            matched = True
            # Execute this condition's actions
            async for event in ctx.execute_actions(actions, ctx.state):
                yield event
            # Only execute the first matching condition
            break

    # Execute elseActions if no condition matched
    if not matched and else_actions:
        logger.debug("ConditionGroup: no conditions matched, executing elseActions")
        async for event in ctx.execute_actions(else_actions, ctx.state):
            yield event


@action_handler("GotoAction")
async def handle_goto_action(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Jump to another action by ID (triggers re-execution from that action).

    Note: GotoAction in the .NET implementation creates a loop by restarting
    execution from a specific action. In Python, we emit a GotoSignal that
    the top-level executor should handle.

    Action schema:
        kind: GotoAction
        actionId: target_action_id
    """
    action_id = ctx.action.get("actionId")

    if not action_id:
        logger.warning("GotoAction missing 'actionId' property")
        return

    logger.debug(f"GotoAction: jumping to action '{action_id}'")

    # Emit a goto signal that the executor should handle
    yield GotoSignal(target_action_id=action_id)


class GotoSignal(WorkflowEvent):
    """Signal to jump to a specific action by ID.

    This signal is used by GotoAction to implement control flow jumps.
    The top-level executor should handle this signal appropriately.
    """

    def __init__(self, target_action_id: str) -> None:
        self.target_action_id = target_action_id


class EndWorkflowSignal(WorkflowEvent):
    """Signal to end the workflow execution.

    This signal causes the workflow to terminate gracefully.
    """

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason


class EndConversationSignal(WorkflowEvent):
    """Signal to end the current conversation.

    This signal causes the conversation to terminate while the workflow may continue.
    """

    def __init__(self, conversation_id: str | None = None, reason: str | None = None) -> None:
        self.conversation_id = conversation_id
        self.reason = reason


@action_handler("EndWorkflow")
async def handle_end_workflow(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """End the workflow execution.

    Action schema:
        kind: EndWorkflow
        reason: Optional reason for ending (for logging)
    """
    reason = ctx.action.get("reason")

    logger.debug(f"EndWorkflow: ending workflow{f' (reason: {reason})' if reason else ''}")

    yield EndWorkflowSignal(reason=reason)


@action_handler("EndConversation")
async def handle_end_conversation(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """End the current conversation.

    Action schema:
        kind: EndConversation
        conversationId: Optional specific conversation to end
        reason: Optional reason for ending
    """
    conversation_id = ctx.action.get("conversationId")
    reason = ctx.action.get("reason")

    # Evaluate conversation ID if provided
    if conversation_id:
        evaluated_id = ctx.state.eval_if_expression(conversation_id)
    else:
        evaluated_id = ctx.state.get("System.ConversationId")

    logger.debug(f"EndConversation: ending conversation {evaluated_id}{f' (reason: {reason})' if reason else ''}")

    yield EndConversationSignal(conversation_id=evaluated_id, reason=reason)
