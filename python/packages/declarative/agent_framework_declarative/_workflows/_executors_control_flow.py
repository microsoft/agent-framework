# Copyright (c) Microsoft. All rights reserved.

"""Control flow executors for the graph-based declarative workflow system.

Control flow in the graph-based system is handled differently than the interpreter:
- If/Switch: Condition evaluation happens in a dedicated evaluator executor that
  returns a ConditionResult with the first-matching branch index. Edge conditions
  then check the branch_index to route to the correct branch. This ensures only
  one branch executes (first-match semantics), matching the interpreter behavior.
- Foreach: Loop iteration state managed in SharedState + loop edges
- Goto: Edge to target action (handled by builder)
- Break/Continue: Special signals for loop control

The key insight is that control flow becomes GRAPH STRUCTURE, not executor logic.
"""

from typing import Any, cast

from agent_framework._workflows import (
    WorkflowContext,
    handler,
)

from ._declarative_base import (
    ActionComplete,
    ActionTrigger,
    ConditionResult,
    DeclarativeActionExecutor,
    LoopControl,
    LoopIterationResult,
)

# Keys for loop state in SharedState
LOOP_STATE_KEY = "_declarative_loop_state"

# Index value indicating the else/default branch
ELSE_BRANCH_INDEX = -1


class ConditionGroupEvaluatorExecutor(DeclarativeActionExecutor):
    """Evaluates conditions for ConditionGroup/Switch and outputs the first-matching branch.

    This executor implements first-match semantics by evaluating conditions sequentially
    and outputting a ConditionResult with the index of the first matching branch.
    Edge conditions downstream check this index to route to the correct branch.

    This mirrors .NET's ConditionGroupExecutor.ExecuteAsync which returns the step ID
    of the first matching condition.
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        conditions: list[dict[str, Any]],
        *,
        id: str | None = None,
    ):
        """Initialize the condition evaluator.

        Args:
            action_def: The ConditionGroup/Switch action definition
            conditions: List of condition items, each with 'condition' and optional 'id'
            id: Optional executor ID
        """
        super().__init__(action_def, id=id)
        self._conditions = conditions

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ConditionResult],
    ) -> None:
        """Evaluate conditions and output the first matching branch index."""
        state = await self._ensure_state_initialized(ctx, trigger)

        # Evaluate conditions sequentially - first match wins
        for index, cond_item in enumerate(self._conditions):
            condition_expr = cond_item.get("condition")
            if condition_expr is None:
                continue

            # Normalize boolean conditions
            if condition_expr is True:
                condition_expr = "=true"
            elif condition_expr is False:
                condition_expr = "=false"
            elif isinstance(condition_expr, str) and not condition_expr.startswith("="):
                condition_expr = f"={condition_expr}"

            result = await state.eval(condition_expr)
            if bool(result):
                # First matching condition found
                await ctx.send_message(ConditionResult(matched=True, branch_index=index, value=result))
                return

        # No condition matched - use else/default branch
        await ctx.send_message(ConditionResult(matched=False, branch_index=ELSE_BRANCH_INDEX))


class SwitchEvaluatorExecutor(DeclarativeActionExecutor):
    """Evaluates a Switch action by matching a value against cases.

    The Switch action uses a different schema than ConditionGroup:
    - value: expression to evaluate once
    - cases: list of {match: value_to_match, actions: [...]}
    - default: default actions if no case matches

    This evaluator evaluates the value expression once, then compares it
    against each case's match value sequentially. First match wins.
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        cases: list[dict[str, Any]],
        *,
        id: str | None = None,
    ):
        """Initialize the switch evaluator.

        Args:
            action_def: The Switch action definition (contains 'value' expression)
            cases: List of case items, each with 'match' and optional 'actions'
            id: Optional executor ID
        """
        super().__init__(action_def, id=id)
        self._cases = cases

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ConditionResult],
    ) -> None:
        """Evaluate the switch value and find the first matching case."""
        state = await self._ensure_state_initialized(ctx, trigger)

        value_expr = self._action_def.get("value")
        if not value_expr:
            # No value to switch on - use default
            await ctx.send_message(ConditionResult(matched=False, branch_index=ELSE_BRANCH_INDEX))
            return

        # Evaluate the switch value once
        switch_value = await state.eval_if_expression(value_expr)

        # Compare against each case's match value
        for index, case_item in enumerate(self._cases):
            match_expr = case_item.get("match")
            if match_expr is None:
                continue

            # Evaluate the match value
            match_value = await state.eval_if_expression(match_expr)

            if switch_value == match_value:
                # Found matching case
                await ctx.send_message(ConditionResult(matched=True, branch_index=index, value=switch_value))
                return

        # No case matched - use default branch
        await ctx.send_message(ConditionResult(matched=False, branch_index=ELSE_BRANCH_INDEX))


class IfConditionEvaluatorExecutor(DeclarativeActionExecutor):
    """Evaluates a single If condition and outputs a ConditionResult.

    This is simpler than ConditionGroupEvaluator - just evaluates one condition
    and outputs branch_index=0 (then) or branch_index=-1 (else).
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        condition_expr: str,
        *,
        id: str | None = None,
    ):
        """Initialize the if condition evaluator.

        Args:
            action_def: The If action definition
            condition_expr: The condition expression to evaluate
            id: Optional executor ID
        """
        super().__init__(action_def, id=id)
        self._condition_expr = condition_expr

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ConditionResult],
    ) -> None:
        """Evaluate the condition and output the result."""
        state = await self._ensure_state_initialized(ctx, trigger)

        result = await state.eval(self._condition_expr)
        is_truthy = bool(result)

        if is_truthy:
            await ctx.send_message(ConditionResult(matched=True, branch_index=0, value=result))
        else:
            await ctx.send_message(ConditionResult(matched=False, branch_index=ELSE_BRANCH_INDEX, value=result))


class ForeachInitExecutor(DeclarativeActionExecutor):
    """Initializes a foreach loop.

    Sets up the loop state in SharedState and determines if there are items.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[LoopIterationResult],
    ) -> None:
        """Initialize the loop and check for first item."""
        state = await self._ensure_state_initialized(ctx, trigger)

        # Support multiple schema formats:
        # - Graph mode: itemsSource, items
        # - Interpreter mode: source
        items_expr = (
            self._action_def.get("itemsSource") or self._action_def.get("items") or self._action_def.get("source")
        )
        items_raw: Any = await state.eval_if_expression(items_expr) or []

        items: list[Any]
        items = (list(items_raw) if items_raw else []) if not isinstance(items_raw, (list, tuple)) else list(items_raw)  # type: ignore

        loop_id = self.id

        # Store loop state
        state_data = await state.get_state_data()
        loop_states: dict[str, Any] = cast(dict[str, Any], state_data).setdefault(LOOP_STATE_KEY, {})
        loop_states[loop_id] = {
            "items": items,
            "index": 0,
            "length": len(items),
        }
        await state.set_state_data(state_data)

        # Check if we have items
        if items:
            # Set the iteration variable
            # Support multiple schema formats:
            # - Graph mode: iteratorVariable, item (default "Local.item")
            # - Interpreter mode: itemName (default "item", stored in Local scope)
            item_var = self._action_def.get("iteratorVariable") or self._action_def.get("item")
            if not item_var:
                # Interpreter mode: itemName defaults to "item", store in Local scope
                item_name = self._action_def.get("itemName", "item")
                item_var = f"Local.{item_name}"

            # Support multiple schema formats for index:
            # - Graph mode: indexVariable, index
            # - Interpreter mode: indexName (default "index", stored in Local scope)
            index_var = self._action_def.get("indexVariable") or self._action_def.get("index")
            if not index_var and "indexName" in self._action_def:
                index_name = self._action_def.get("indexName", "index")
                index_var = f"Local.{index_name}"

            await state.set(item_var, items[0])
            if index_var:
                await state.set(index_var, 0)

            await ctx.send_message(LoopIterationResult(has_next=True, current_item=items[0], current_index=0))
        else:
            await ctx.send_message(LoopIterationResult(has_next=False))


class ForeachNextExecutor(DeclarativeActionExecutor):
    """Advances to the next item in a foreach loop.

    This executor is triggered after the loop body completes.
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        init_executor_id: str,
        *,
        id: str | None = None,
    ):
        """Initialize with reference to the init executor.

        Args:
            action_def: The Foreach action definition
            init_executor_id: ID of the corresponding ForeachInitExecutor
            id: Optional executor ID
        """
        super().__init__(action_def, id=id)
        self._init_executor_id = init_executor_id

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[LoopIterationResult],
    ) -> None:
        """Advance to next item and send result."""
        state = await self._ensure_state_initialized(ctx, trigger)

        loop_id = self._init_executor_id

        # Get loop state
        state_data = await state.get_state_data()
        loop_states: dict[str, Any] = cast(dict[str, Any], state_data).get(LOOP_STATE_KEY, {})
        loop_state = loop_states.get(loop_id)

        if not loop_state:
            # No loop state - shouldn't happen but handle gracefully
            await ctx.send_message(LoopIterationResult(has_next=False))
            return

        items = loop_state["items"]
        current_index = loop_state["index"] + 1

        if current_index < len(items):
            # Update loop state
            loop_state["index"] = current_index
            await state.set_state_data(state_data)

            # Set the iteration variable
            # Support multiple schema formats:
            # - Graph mode: iteratorVariable, item (default "Local.item")
            # - Interpreter mode: itemName (default "item", stored in Local scope)
            item_var = self._action_def.get("iteratorVariable") or self._action_def.get("item")
            if not item_var:
                # Interpreter mode: itemName defaults to "item", store in Local scope
                item_name = self._action_def.get("itemName", "item")
                item_var = f"Local.{item_name}"

            # Support multiple schema formats for index:
            # - Graph mode: indexVariable, index
            # - Interpreter mode: indexName (default "index", stored in Local scope)
            index_var = self._action_def.get("indexVariable") or self._action_def.get("index")
            if not index_var and "indexName" in self._action_def:
                index_name = self._action_def.get("indexName", "index")
                index_var = f"Local.{index_name}"

            await state.set(item_var, items[current_index])
            if index_var:
                await state.set(index_var, current_index)

            await ctx.send_message(
                LoopIterationResult(has_next=True, current_item=items[current_index], current_index=current_index)
            )
        else:
            # Loop complete - clean up
            loop_states_dict = cast(dict[str, Any], state_data).get(LOOP_STATE_KEY, {})
            if loop_id in loop_states_dict:
                del loop_states_dict[loop_id]
            await state.set_state_data(state_data)

            await ctx.send_message(LoopIterationResult(has_next=False))

    @handler
    async def handle_loop_control(
        self,
        control: LoopControl,
        ctx: WorkflowContext[LoopIterationResult],
    ) -> None:
        """Handle break/continue signals."""
        state = self._get_state(ctx.shared_state)

        if control.action == "break":
            # Clean up loop state and signal done
            state_data = await state.get_state_data()
            loop_states: dict[str, Any] = cast(dict[str, Any], state_data).get(LOOP_STATE_KEY, {})
            if self._init_executor_id in loop_states:
                del loop_states[self._init_executor_id]
                await state.set_state_data(state_data)

            await ctx.send_message(LoopIterationResult(has_next=False))

        elif control.action == "continue":
            # Just advance to next iteration
            await self.handle_action(ActionTrigger(), ctx)


class BreakLoopExecutor(DeclarativeActionExecutor):
    """Executor for BreakLoop action.

    Sends a LoopControl signal to break out of the enclosing loop.
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        loop_next_executor_id: str,
        *,
        id: str | None = None,
    ):
        """Initialize with reference to the loop's next executor.

        Args:
            action_def: The action definition
            loop_next_executor_id: ID of the ForeachNextExecutor to signal
            id: Optional executor ID
        """
        super().__init__(action_def, id=id)
        self._loop_next_executor_id = loop_next_executor_id

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[LoopControl],
    ) -> None:
        """Send break signal to the loop."""
        await ctx.send_message(LoopControl(action="break"))


class ContinueLoopExecutor(DeclarativeActionExecutor):
    """Executor for ContinueLoop action.

    Sends a LoopControl signal to continue to next iteration.
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        loop_next_executor_id: str,
        *,
        id: str | None = None,
    ):
        """Initialize with reference to the loop's next executor.

        Args:
            action_def: The action definition
            loop_next_executor_id: ID of the ForeachNextExecutor to signal
            id: Optional executor ID
        """
        super().__init__(action_def, id=id)
        self._loop_next_executor_id = loop_next_executor_id

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[LoopControl],
    ) -> None:
        """Send continue signal to the loop."""
        await ctx.send_message(LoopControl(action="continue"))


class EndWorkflowExecutor(DeclarativeActionExecutor):
    """Executor for EndWorkflow/EndDialog action.

    This executor simply doesn't send any message, causing the workflow
    to terminate at this point.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """End the workflow by not sending any continuation message."""
        # Don't send ActionComplete - workflow ends here
        pass


class EndConversationExecutor(DeclarativeActionExecutor):
    """Executor for EndConversation action."""

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """End the conversation."""
        # For now, just don't continue
        # In a full implementation, this would signal to close the conversation
        pass


# Passthrough executor for joining control flow branches
class JoinExecutor(DeclarativeActionExecutor):
    """Executor that joins multiple branches back together.

    Used after If/Switch to merge control flow back to a single path.
    Also used as passthrough nodes for else/default branches.
    """

    @handler
    async def handle_action(
        self,
        trigger: dict[str, Any] | str | ActionTrigger | ActionComplete | ConditionResult | LoopIterationResult,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Simply pass through to continue the workflow."""
        await ctx.send_message(ActionComplete())


class CancelDialogExecutor(DeclarativeActionExecutor):
    """Executor for CancelDialog action.

    Cancels the current dialog/workflow, equivalent to .NET CancelDialog.
    This terminates execution similarly to EndWorkflow.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Cancel the current dialog/workflow."""
        # CancelDialog terminates execution without continuing
        # Similar to EndWorkflow but semantically different (cancellation vs completion)
        pass


class CancelAllDialogsExecutor(DeclarativeActionExecutor):
    """Executor for CancelAllDialogs action.

    Cancels all dialogs in the execution stack, equivalent to .NET CancelAllDialogs.
    This terminates the entire workflow execution.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Cancel all dialogs/workflows."""
        # CancelAllDialogs terminates all execution
        pass


# Mapping of control flow action kinds to executor classes
# Note: Most control flow is handled by the builder creating graph structure,
# these are the executors that are part of that structure
CONTROL_FLOW_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "EndWorkflow": EndWorkflowExecutor,
    "EndDialog": EndWorkflowExecutor,
    "EndConversation": EndConversationExecutor,
    "CancelDialog": CancelDialogExecutor,
    "CancelAllDialogs": CancelAllDialogsExecutor,
}
