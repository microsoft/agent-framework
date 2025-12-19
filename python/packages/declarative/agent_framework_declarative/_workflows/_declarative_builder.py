# Copyright (c) Microsoft. All rights reserved.

"""Builder that transforms declarative YAML into a workflow graph.

This module provides the DeclarativeWorkflowBuilder which is analogous to
.NET's WorkflowActionVisitor + WorkflowElementWalker. It walks the YAML
action definitions and creates a proper workflow graph with:
- Executor nodes for each action
- Edges for sequential flow
- Condition evaluator executors for If/Switch that ensure first-match semantics
- Loop edges for foreach
"""

from typing import Any

from agent_framework._workflows import (
    Workflow,
    WorkflowBuilder,
)

from ._declarative_base import (
    ConditionResult,
    DeclarativeActionExecutor,
    LoopIterationResult,
)
from ._executors_agents import AGENT_ACTION_EXECUTORS, InvokeAzureAgentExecutor
from ._executors_basic import BASIC_ACTION_EXECUTORS
from ._executors_control_flow import (
    CONTROL_FLOW_EXECUTORS,
    ELSE_BRANCH_INDEX,
    ConditionGroupEvaluatorExecutor,
    ForeachInitExecutor,
    ForeachNextExecutor,
    IfConditionEvaluatorExecutor,
    JoinExecutor,
    SwitchEvaluatorExecutor,
)
from ._executors_external_input import EXTERNAL_INPUT_EXECUTORS

# Combined mapping of all action kinds to executor classes
ALL_ACTION_EXECUTORS = {
    **BASIC_ACTION_EXECUTORS,
    **CONTROL_FLOW_EXECUTORS,
    **AGENT_ACTION_EXECUTORS,
    **EXTERNAL_INPUT_EXECUTORS,
}

# Action kinds that terminate control flow (no fall-through to successor)
# These actions transfer control elsewhere and should not have sequential edges to the next action
TERMINATOR_ACTIONS = frozenset({"Goto", "GotoAction", "BreakLoop", "ContinueLoop", "EndWorkflow", "EndDialog"})

# Required fields for specific action kinds (schema validation)
# Each action needs at least one of the listed fields (checked with alternates)
ACTION_REQUIRED_FIELDS: dict[str, list[str]] = {
    "SetValue": ["path"],
    "SetVariable": ["variable"],
    "AppendValue": ["path", "value"],
    "SendActivity": ["activity"],
    "InvokeAzureAgent": ["agent"],
    "Goto": ["target"],
    "GotoAction": ["actionId"],
    "Foreach": ["items", "actions"],
    "If": ["condition"],
    "Switch": ["value"],  # Switch can use value/cases or conditions (ConditionGroup style)
    "ConditionGroup": ["conditions"],
    "RequestHumanInput": ["variable"],
    "WaitForHumanInput": ["variable"],
    "EmitEvent": ["event"],
}

# Alternate field names that satisfy required field requirements
# Key: "ActionKind.field", Value: list of alternates that satisfy the requirement
ACTION_ALTERNATE_FIELDS: dict[str, list[str]] = {
    "SetValue.path": ["variable"],
    "Goto.target": ["actionId"],
    "GotoAction.actionId": ["target"],
    "InvokeAzureAgent.agent": ["agentName"],
    "Foreach.items": ["itemsSource", "source"],  # source is used in some schemas
    "Switch.value": ["conditions"],  # Switch can be condition-based instead of value-based
}


class DeclarativeWorkflowBuilder:
    """Builds a Workflow graph from declarative YAML actions.

    This builder transforms declarative action definitions into a proper
    workflow graph with executor nodes and edges. It handles:
    - Sequential actions (simple edges)
    - Conditional branching (If/Switch with condition edges)
    - Loops (Foreach with loop edges)
    - Jumps (Goto with target edges)

    Example usage:
        yaml_def = {
            "actions": [
                {"kind": "SendActivity", "activity": {"text": "Hello"}},
                {"kind": "SetValue", "path": "turn.count", "value": 0},
            ]
        }
        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()
    """

    def __init__(
        self,
        yaml_definition: dict[str, Any],
        workflow_id: str | None = None,
        agents: dict[str, Any] | None = None,
        checkpoint_storage: Any | None = None,
        validate: bool = True,
    ):
        """Initialize the builder.

        Args:
            yaml_definition: The parsed YAML workflow definition
            workflow_id: Optional ID for the workflow (defaults to name from YAML)
            agents: Registry of agent instances by name (for InvokeAzureAgent actions)
            checkpoint_storage: Optional checkpoint storage for pause/resume support
            validate: Whether to validate the workflow definition before building (default: True)
        """
        self._yaml_def = yaml_definition
        self._workflow_id = workflow_id or yaml_definition.get("name", "declarative_workflow")
        self._executors: dict[str, Any] = {}  # id -> executor
        self._action_index = 0  # Counter for generating unique IDs
        self._agents = agents or {}  # Agent registry for agent executors
        self._checkpoint_storage = checkpoint_storage
        self._pending_gotos: list[tuple[Any, str]] = []  # (goto_executor, target_id)
        self._validate = validate
        self._seen_explicit_ids: set[str] = set()  # Track explicit IDs for duplicate detection

    def build(self) -> Workflow:
        """Build the workflow graph.

        Returns:
            A Workflow instance with all executors wired together

        Raises:
            ValueError: If no actions are defined (empty workflow), or validation fails
        """
        builder = WorkflowBuilder(name=self._workflow_id)

        # Enable checkpointing if storage is provided
        if self._checkpoint_storage:
            builder.with_checkpointing(self._checkpoint_storage)

        actions = self._yaml_def.get("actions", [])
        if not actions:
            # Empty workflow - raise an error since we need at least one executor
            raise ValueError("Cannot build workflow with no actions. At least one action is required.")

        # Validate workflow definition before building
        if self._validate:
            self._validate_workflow(actions)

        # First pass: create all executors
        entry_executor = self._create_executors_for_actions(actions, builder)

        # Set the entry point
        if entry_executor:
            # Check if entry is a control flow structure (If/Switch)
            if getattr(entry_executor, "_is_if_structure", False) or getattr(
                entry_executor, "_is_switch_structure", False
            ):
                # Create an entry passthrough node and wire to the structure's branches
                entry_node = JoinExecutor({"kind": "Entry"}, id="_workflow_entry")
                self._executors[entry_node.id] = entry_node
                builder.set_start_executor(entry_node)
                # Use _add_sequential_edge which knows how to wire to structures
                self._add_sequential_edge(builder, entry_node, entry_executor)
            else:
                builder.set_start_executor(entry_executor)
        else:
            raise ValueError("Failed to create any executors from actions.")

        # Resolve pending gotos (back-edges for loops, forward-edges for jumps)
        self._resolve_pending_gotos(builder)

        return builder.build()

    def _validate_workflow(self, actions: list[dict[str, Any]]) -> None:
        """Validate the workflow definition before building.

        Performs:
        - Schema validation (required fields for action types)
        - Duplicate explicit action ID detection
        - Circular goto reference detection

        Args:
            actions: List of action definitions to validate

        Raises:
            ValueError: If validation fails
        """
        seen_ids: set[str] = set()
        goto_targets: list[tuple[str, str | None]] = []  # (target_id, source_id)
        defined_ids: set[str] = set()

        # Collect all defined IDs and validate each action
        self._validate_actions_recursive(actions, seen_ids, goto_targets, defined_ids)

        # Check for circular goto chains (A -> B -> A)
        # Build a simple graph of goto targets
        self._validate_no_circular_gotos(goto_targets, defined_ids)

    def _validate_actions_recursive(
        self,
        actions: list[dict[str, Any]],
        seen_ids: set[str],
        goto_targets: list[tuple[str, str | None]],
        defined_ids: set[str],
    ) -> None:
        """Recursively validate actions and collect metadata.

        Args:
            actions: List of action definitions
            seen_ids: Set of seen explicit IDs (for duplicate detection)
            goto_targets: List of (target_id, source_id) tuples for goto validation
            defined_ids: Set of all defined action IDs
        """
        for action_def in actions:
            kind = action_def.get("kind", "")

            # Check for duplicate explicit IDs
            explicit_id = action_def.get("id")
            if explicit_id:
                if explicit_id in seen_ids:
                    raise ValueError(f"Duplicate action ID '{explicit_id}'. Action IDs must be unique.")
                seen_ids.add(explicit_id)
                defined_ids.add(explicit_id)

            # Schema validation: check required fields
            required_fields = ACTION_REQUIRED_FIELDS.get(kind, [])
            for field in required_fields:
                if field not in action_def and not self._has_alternate_field(action_def, kind, field):
                    raise ValueError(f"Action '{kind}' is missing required field '{field}'. Action: {action_def}")

            # Collect goto targets for circular reference detection
            if kind in ("Goto", "GotoAction"):
                target = action_def.get("target") or action_def.get("actionId")
                if target:
                    goto_targets.append((target, explicit_id))

            # Recursively validate nested actions
            if kind == "If":
                then_actions = action_def.get("then", action_def.get("actions", []))
                if then_actions:
                    self._validate_actions_recursive(then_actions, seen_ids, goto_targets, defined_ids)
                else_actions = action_def.get("else", [])
                if else_actions:
                    self._validate_actions_recursive(else_actions, seen_ids, goto_targets, defined_ids)

            elif kind in ("Switch", "ConditionGroup"):
                cases = action_def.get("cases", action_def.get("conditions", []))
                for case in cases:
                    case_actions = case.get("actions", [])
                    if case_actions:
                        self._validate_actions_recursive(case_actions, seen_ids, goto_targets, defined_ids)
                else_actions = action_def.get("elseActions", action_def.get("else", action_def.get("default", [])))
                if else_actions:
                    self._validate_actions_recursive(else_actions, seen_ids, goto_targets, defined_ids)

            elif kind == "Foreach":
                body_actions = action_def.get("actions", [])
                if body_actions:
                    self._validate_actions_recursive(body_actions, seen_ids, goto_targets, defined_ids)

    def _has_alternate_field(self, action_def: dict[str, Any], kind: str, field: str) -> bool:
        """Check if an action has an alternate field that satisfies the requirement.

        Some actions support multiple field names for the same purpose.

        Args:
            action_def: The action definition
            kind: The action kind
            field: The required field name

        Returns:
            True if an alternate field exists
        """
        key = f"{kind}.{field}"
        return any(alt in action_def for alt in ACTION_ALTERNATE_FIELDS.get(key, []))

    def _validate_no_circular_gotos(
        self,
        goto_targets: list[tuple[str, str | None]],
        defined_ids: set[str],
    ) -> None:
        """Validate that there are no problematic circular goto chains.

        Note: Some circular references are valid (e.g., loop-back patterns).
        This checks for direct self-references only as a basic validation.

        Args:
            goto_targets: List of (target_id, source_id) tuples
            defined_ids: Set of defined action IDs
        """
        for target_id, source_id in goto_targets:
            # Check for direct self-reference
            if source_id and target_id == source_id:
                raise ValueError(
                    f"Action '{source_id}' has a direct self-referencing Goto, which would cause an infinite loop."
                )

    def _resolve_pending_gotos(self, builder: WorkflowBuilder) -> None:
        """Resolve pending goto edges after all executors are created.

        Creates edges from goto executors to their target executors.

        Raises:
            ValueError: If a goto target references an action ID that does not exist.
        """
        for goto_executor, target_id in self._pending_gotos:
            target_executor = self._executors.get(target_id)
            if target_executor:
                # Create edge from goto to target
                builder.add_edge(source=goto_executor, target=target_executor)
            else:
                available_ids = list(self._executors.keys())
                raise ValueError(f"Goto target '{target_id}' not found. Available action IDs: {available_ids}")

    def _create_executors_for_actions(
        self,
        actions: list[dict[str, Any]],
        builder: WorkflowBuilder,
        parent_context: dict[str, Any] | None = None,
    ) -> Any | None:
        """Create executors for a list of actions and wire them together.

        Args:
            actions: List of action definitions
            builder: The workflow builder
            parent_context: Context from parent (e.g., loop info)

        Returns:
            The first executor in the chain, or None if no actions
        """
        if not actions:
            return None

        first_executor = None
        prev_executor = None
        executors_in_chain: list[Any] = []

        for action_def in actions:
            executor = self._create_executor_for_action(action_def, builder, parent_context)

            if executor is None:
                continue

            executors_in_chain.append(executor)

            if first_executor is None:
                first_executor = executor

            # Wire sequential edge from previous executor
            if prev_executor is not None:
                self._add_sequential_edge(builder, prev_executor, executor)

            # Check if this action is a terminator (transfers control elsewhere)
            # Terminators should not have fall-through edges to subsequent actions
            action_kind = action_def.get("kind", "")
            # Don't wire terminators to the next action - control flow ends there
            prev_executor = None if action_kind in TERMINATOR_ACTIONS else executor

        # Store the chain for later reference
        if first_executor is not None:
            first_executor._chain_executors = executors_in_chain  # type: ignore[attr-defined]

        return first_executor

    def _create_executor_for_action(
        self,
        action_def: dict[str, Any],
        builder: WorkflowBuilder,
        parent_context: dict[str, Any] | None = None,
    ) -> Any | None:
        """Create an executor for a single action.

        Args:
            action_def: The action definition from YAML
            builder: The workflow builder
            parent_context: Context from parent

        Returns:
            The created executor, or None if action type not supported
        """
        kind = action_def.get("kind", "")

        # Handle special control flow actions
        if kind == "If":
            return self._create_if_structure(action_def, builder, parent_context)
        if kind == "Switch" or kind == "ConditionGroup":
            return self._create_switch_structure(action_def, builder, parent_context)
        if kind == "Foreach":
            return self._create_foreach_structure(action_def, builder, parent_context)
        if kind == "Goto" or kind == "GotoAction":
            return self._create_goto_reference(action_def, builder, parent_context)
        if kind == "BreakLoop":
            return self._create_break_executor(action_def, builder, parent_context)
        if kind == "ContinueLoop":
            return self._create_continue_executor(action_def, builder, parent_context)

        # Get the executor class for this action kind
        executor_class = ALL_ACTION_EXECUTORS.get(kind)

        if executor_class is None:
            # Unknown action type - skip with warning
            # In production, might want to log this
            return None

        # Create the executor with ID
        # Priority: explicit ID from YAML > index-based ID (matches .NET behavior)
        explicit_id = action_def.get("id")
        if explicit_id:
            action_id = explicit_id
        else:
            parent_id = (parent_context or {}).get("parent_id")
            action_id = f"{parent_id}_{kind}_{self._action_index}" if parent_id else f"{kind}_{self._action_index}"
        self._action_index += 1

        # Pass agents to agent-related executors
        executor: Any
        if kind in ("InvokeAzureAgent",):
            executor = InvokeAzureAgentExecutor(action_def, id=action_id, agents=self._agents)
        else:
            executor = executor_class(action_def, id=action_id)
        self._executors[action_id] = executor

        return executor

    def _create_if_structure(
        self,
        action_def: dict[str, Any],
        builder: WorkflowBuilder,
        parent_context: dict[str, Any] | None = None,
    ) -> Any:
        """Create the graph structure for an If action.

        An If action is implemented with a condition evaluator executor that
        outputs a ConditionResult. Edge conditions check the branch_index to
        route to either the then or else branch. This ensures first-match
        semantics (only one branch executes).

        Args:
            action_def: The If action definition
            builder: The workflow builder
            parent_context: Context from parent

        Returns:
            A structure representing the If with evaluator, branch entries and exits
        """
        action_id = action_def.get("id") or f"If_{self._action_index}"
        self._action_index += 1

        condition_expr = action_def.get("condition", "true")
        # Normalize boolean conditions from YAML to PowerFx-style strings
        if condition_expr is True:
            condition_expr = "=true"
        elif condition_expr is False:
            condition_expr = "=false"
        elif isinstance(condition_expr, str) and not condition_expr.startswith("="):
            # Bare string conditions should be evaluated as expressions
            condition_expr = f"={condition_expr}"

        # Pass the If's ID as context for child action naming
        branch_context = {
            **(parent_context or {}),
            "parent_id": action_id,
        }

        # Create the condition evaluator executor
        evaluator = IfConditionEvaluatorExecutor(
            action_def,
            condition_expr,
            id=f"{action_id}_eval",
        )
        self._executors[evaluator.id] = evaluator

        # Create then branch
        then_actions = action_def.get("then", action_def.get("actions", []))
        then_entry = self._create_executors_for_actions(then_actions, builder, branch_context)

        # Create else branch
        else_actions = action_def.get("else", [])
        else_entry = self._create_executors_for_actions(else_actions, builder, branch_context) if else_actions else None
        else_passthrough = None
        if not else_entry:
            # No else branch - create a passthrough for continuation when condition is false
            else_passthrough = JoinExecutor({"kind": "ElsePassthrough"}, id=f"{action_id}_else_pass")
            self._executors[else_passthrough.id] = else_passthrough

        # Wire evaluator to branches with conditions that check ConditionResult.branch_index
        # branch_index=0 means "then" branch, branch_index=-1 (ELSE_BRANCH_INDEX) means "else"
        # For nested If/Switch structures, wire to the evaluator (entry point)
        if then_entry:
            then_target = self._get_structure_entry(then_entry)
            builder.add_edge(
                source=evaluator,
                target=then_target,
                condition=lambda msg: isinstance(msg, ConditionResult) and msg.branch_index == 0,
            )
        if else_entry:
            else_target = self._get_structure_entry(else_entry)
            builder.add_edge(
                source=evaluator,
                target=else_target,
                condition=lambda msg: isinstance(msg, ConditionResult) and msg.branch_index == ELSE_BRANCH_INDEX,
            )
        elif else_passthrough:
            builder.add_edge(
                source=evaluator,
                target=else_passthrough,
                condition=lambda msg: isinstance(msg, ConditionResult) and msg.branch_index == ELSE_BRANCH_INDEX,
            )

        # Get branch exit executors for later wiring to successor
        then_exit = self._get_branch_exit(then_entry)
        else_exit = self._get_branch_exit(else_entry) if else_entry else else_passthrough

        # Collect all branch exits (for wiring to successor)
        branch_exits: list[Any] = []
        if then_exit:
            branch_exits.append(then_exit)
        if else_exit:
            branch_exits.append(else_exit)

        # Create an IfStructure to hold all the info needed for wiring
        class IfStructure:
            def __init__(self) -> None:
                self.id = action_id
                self.evaluator = evaluator  # The entry point for this structure
                self.then_entry = then_entry
                self.else_entry = else_entry
                self.else_passthrough = else_passthrough
                self.branch_exits = branch_exits  # All exits that need wiring to successor
                self._is_if_structure = True

        return IfStructure()

    def _create_switch_structure(
        self,
        action_def: dict[str, Any],
        builder: WorkflowBuilder,
        parent_context: dict[str, Any] | None = None,
    ) -> Any:
        """Create the graph structure for a Switch/ConditionGroup action.

        Supports two schema formats:
        1. ConditionGroup schema (matches .NET):
           - conditions: list of {condition: expr, actions: [...]}
           - elseActions: default actions

        2. Switch schema (interpreter style):
           - value: expression to match
           - cases: list of {match: value, actions: [...]}
           - default: default actions

        Both use evaluator executors that output ConditionResult with branch_index
        for first-match semantics.

        Args:
            action_def: The Switch/ConditionGroup action definition
            builder: The workflow builder
            parent_context: Context from parent

        Returns:
            A SwitchStructure containing branch info for wiring
        """
        action_id = action_def.get("id") or f"Switch_{self._action_index}"
        self._action_index += 1

        # Pass the Switch's ID as context for child action naming
        branch_context = {
            **(parent_context or {}),
            "parent_id": action_id,
        }

        # Detect schema type:
        # - If "cases" present: interpreter Switch schema (value/cases/default)
        # - If "conditions" present: ConditionGroup schema (conditions/elseActions)
        cases = action_def.get("cases", [])
        conditions = action_def.get("conditions", [])

        if cases:
            # Interpreter Switch schema: value/cases/default
            evaluator: DeclarativeActionExecutor = SwitchEvaluatorExecutor(
                action_def,
                cases,
                id=f"{action_id}_eval",
            )
            branch_items = cases
        else:
            # ConditionGroup schema: conditions/elseActions
            evaluator = ConditionGroupEvaluatorExecutor(
                action_def,
                conditions,
                id=f"{action_id}_eval",
            )
            branch_items = conditions

        self._executors[evaluator.id] = evaluator

        # Collect branches and create executors for each
        branch_entries: list[tuple[int, Any]] = []  # (branch_index, entry_executor)
        branch_exits: list[Any] = []  # All exits that need wiring to successor

        for i, item in enumerate(branch_items):
            branch_actions = item.get("actions", [])
            # Use branch-specific context
            case_context = {**branch_context, "parent_id": f"{action_id}_case{i}"}
            branch_entry = self._create_executors_for_actions(branch_actions, builder, case_context)

            if branch_entry:
                branch_entries.append((i, branch_entry))
                # Track exit for later wiring
                branch_exit = self._get_branch_exit(branch_entry)
                if branch_exit:
                    branch_exits.append(branch_exit)

        # Handle else/default branch
        # .NET uses "elseActions", interpreter uses "else" or "default"
        else_actions = action_def.get("elseActions", action_def.get("else", action_def.get("default", [])))
        default_entry = None
        default_passthrough = None
        if else_actions:
            default_context = {**branch_context, "parent_id": f"{action_id}_else"}
            default_entry = self._create_executors_for_actions(else_actions, builder, default_context)
            if default_entry:
                default_exit = self._get_branch_exit(default_entry)
                if default_exit:
                    branch_exits.append(default_exit)
        else:
            # No else actions - create a passthrough for the "no match" case
            # This allows the workflow to continue to the next action when no condition matches
            default_passthrough = JoinExecutor({"kind": "DefaultPassthrough"}, id=f"{action_id}_default")
            self._executors[default_passthrough.id] = default_passthrough
            branch_exits.append(default_passthrough)

        # Wire evaluator to branches with conditions that check ConditionResult.branch_index
        # For nested If/Switch structures, wire to the evaluator (entry point)
        for branch_index, branch_entry in branch_entries:
            # Capture branch_index in closure properly using a factory function for type inference
            def make_branch_condition(expected: int) -> Any:
                return lambda msg: isinstance(msg, ConditionResult) and msg.branch_index == expected  # type: ignore

            branch_target = self._get_structure_entry(branch_entry)
            builder.add_edge(
                source=evaluator,
                target=branch_target,
                condition=make_branch_condition(branch_index),
            )

        # Wire evaluator to default/else branch
        if default_entry:
            default_target = self._get_structure_entry(default_entry)
            builder.add_edge(
                source=evaluator,
                target=default_target,
                condition=lambda msg: isinstance(msg, ConditionResult) and msg.branch_index == ELSE_BRANCH_INDEX,
            )
        elif default_passthrough:
            builder.add_edge(
                source=evaluator,
                target=default_passthrough,
                condition=lambda msg: isinstance(msg, ConditionResult) and msg.branch_index == ELSE_BRANCH_INDEX,
            )

        # Create a SwitchStructure to hold all the info needed for wiring
        class SwitchStructure:
            def __init__(self) -> None:
                self.id = action_id
                self.evaluator = evaluator  # The entry point for this structure
                self.branch_entries = branch_entries
                self.default_entry = default_entry
                self.default_passthrough = default_passthrough
                self.branch_exits = branch_exits  # All exits that need wiring to successor
                self._is_switch_structure = True

        return SwitchStructure()

    def _create_foreach_structure(
        self,
        action_def: dict[str, Any],
        builder: WorkflowBuilder,
        parent_context: dict[str, Any] | None = None,
    ) -> Any:
        """Create the graph structure for a Foreach action.

        A Foreach action becomes:
        1. ForeachInit node that initializes the loop
        2. Loop body actions
        3. ForeachNext node that advances to next item
        4. Back-edge from ForeachNext to loop body (when has_next=True)
        5. Exit edge from ForeachNext (when has_next=False)

        Args:
            action_def: The Foreach action definition
            builder: The workflow builder
            parent_context: Context from parent

        Returns:
            The foreach init executor (entry point)
        """
        action_id = action_def.get("id") or f"Foreach_{self._action_index}"
        self._action_index += 1

        # Create foreach init executor
        init_executor = ForeachInitExecutor(action_def, id=f"{action_id}_init")
        self._executors[init_executor.id] = init_executor

        # Create foreach next executor (for advancing to next item)
        next_executor = ForeachNextExecutor(action_def, init_executor.id, id=f"{action_id}_next")
        self._executors[next_executor.id] = next_executor

        # Create join node for loop exit
        join_executor = JoinExecutor({"kind": "Join"}, id=f"{action_id}_exit")
        self._executors[join_executor.id] = join_executor

        # Create loop body
        body_actions = action_def.get("actions", [])
        loop_context = {
            **(parent_context or {}),
            "loop_id": action_id,
            "loop_next_executor": next_executor,
        }
        body_entry = self._create_executors_for_actions(body_actions, builder, loop_context)

        if body_entry:
            # For nested If/Switch structures, wire to the evaluator (entry point)
            body_target = self._get_structure_entry(body_entry)

            # Init -> body (when has_next=True)
            builder.add_edge(
                source=init_executor,
                target=body_target,
                condition=lambda msg: isinstance(msg, LoopIterationResult) and msg.has_next,
            )

            # Body exit -> Next (get all exits from body and wire to next_executor)
            body_exits = self._get_source_exits(body_entry)
            for body_exit in body_exits:
                builder.add_edge(source=body_exit, target=next_executor)

            # Next -> body (when has_next=True, loop back)
            builder.add_edge(
                source=next_executor,
                target=body_target,
                condition=lambda msg: isinstance(msg, LoopIterationResult) and msg.has_next,
            )

        # Init -> join (when has_next=False, empty collection)
        builder.add_edge(
            source=init_executor,
            target=join_executor,
            condition=lambda msg: isinstance(msg, LoopIterationResult) and not msg.has_next,
        )

        # Next -> join (when has_next=False, loop complete)
        builder.add_edge(
            source=next_executor,
            target=join_executor,
            condition=lambda msg: isinstance(msg, LoopIterationResult) and not msg.has_next,
        )

        init_executor._exit_executor = join_executor  # type: ignore[attr-defined]
        return init_executor

    def _create_goto_reference(
        self,
        action_def: dict[str, Any],
        builder: WorkflowBuilder,
        parent_context: dict[str, Any] | None = None,
    ) -> Any | None:
        """Create a GotoAction executor that jumps to the target action.

        GotoAction creates a back-edge (or forward-edge) in the graph to the target action.
        We create a pass-through executor and record the pending edge to be resolved
        after all executors are created.
        """
        from ._executors_control_flow import JoinExecutor

        target_id = action_def.get("target") or action_def.get("actionId")

        if not target_id:
            return None

        # Create a pass-through executor for the goto
        action_id = action_def.get("id") or f"goto_{target_id}_{self._action_index}"
        self._action_index += 1

        # Use JoinExecutor as a simple pass-through node
        goto_executor = JoinExecutor(action_def, id=action_id)
        self._executors[action_id] = goto_executor

        # Record pending goto edge to be resolved after all executors created
        self._pending_gotos.append((goto_executor, target_id))

        return goto_executor

    def _create_break_executor(
        self,
        action_def: dict[str, Any],
        builder: WorkflowBuilder,
        parent_context: dict[str, Any] | None = None,
    ) -> Any | None:
        """Create a break executor for loop control.

        Raises:
            ValueError: If BreakLoop is used outside of a loop.
        """
        from ._executors_control_flow import BreakLoopExecutor

        if parent_context and "loop_next_executor" in parent_context:
            loop_next = parent_context["loop_next_executor"]
            action_id = action_def.get("id") or f"Break_{self._action_index}"
            self._action_index += 1

            executor = BreakLoopExecutor(action_def, loop_next.id, id=action_id)
            self._executors[action_id] = executor

            # Wire break to loop next
            builder.add_edge(source=executor, target=loop_next)

            return executor

        raise ValueError("BreakLoop action can only be used inside a Foreach loop")

    def _create_continue_executor(
        self,
        action_def: dict[str, Any],
        builder: WorkflowBuilder,
        parent_context: dict[str, Any] | None = None,
    ) -> Any | None:
        """Create a continue executor for loop control.

        Raises:
            ValueError: If ContinueLoop is used outside of a loop.
        """
        from ._executors_control_flow import ContinueLoopExecutor

        if parent_context and "loop_next_executor" in parent_context:
            loop_next = parent_context["loop_next_executor"]
            action_id = action_def.get("id") or f"Continue_{self._action_index}"
            self._action_index += 1

            executor = ContinueLoopExecutor(action_def, loop_next.id, id=action_id)
            self._executors[action_id] = executor

            # Wire continue to loop next
            builder.add_edge(source=executor, target=loop_next)

            return executor

        raise ValueError("ContinueLoop action can only be used inside a Foreach loop")

    def _add_sequential_edge(
        self,
        builder: WorkflowBuilder,
        source: Any,
        target: Any,
    ) -> None:
        """Add a sequential edge between two executors.

        Handles control flow structures:
        - If source is a structure (If/Switch), wire from all branch exits
        - If target is a structure (If/Switch), wire with conditional edges to branches
        """
        # Get all source exit points
        source_exits = self._get_source_exits(source)

        # Wire each source exit to target
        for source_exit in source_exits:
            self._wire_to_target(builder, source_exit, target)

    def _get_source_exits(self, source: Any) -> list[Any]:
        """Get all exit executors from a source (handles structures with multiple exits)."""
        # Check if source is a structure with branch_exits
        if hasattr(source, "branch_exits"):
            # Collect all exits, recursively flattening nested structures
            all_exits: list[Any] = []
            for exit_item in source.branch_exits:
                if hasattr(exit_item, "branch_exits"):
                    # Nested structure - recurse
                    all_exits.extend(self._collect_all_exits(exit_item))
                else:
                    all_exits.append(exit_item)
            return all_exits if all_exits else []

        # Check if source has a single exit executor
        actual_exit = getattr(source, "_exit_executor", source)
        return [actual_exit]

    def _wire_to_target(
        self,
        builder: WorkflowBuilder,
        source: Any,
        target: Any,
    ) -> None:
        """Wire a single source executor to a target (which may be a structure).

        For If/Switch structures, wire to the evaluator executor. The evaluator
        handles condition evaluation and outputs ConditionResult, which is then
        routed to the appropriate branch by edges created in _create_*_structure.
        """
        # Check if target is an IfStructure or SwitchStructure (wire to evaluator)
        if getattr(target, "_is_if_structure", False) or getattr(target, "_is_switch_structure", False):
            # Wire from source to the evaluator - the evaluator then routes to branches
            builder.add_edge(source=source, target=target.evaluator)

        else:
            # Normal sequential edge to a regular executor
            builder.add_edge(source=source, target=target)

    def _get_structure_entry(self, entry: Any) -> Any:
        """Get the entry point executor for a structure or regular executor.

        For If/Switch structures, returns the evaluator. For regular executors,
        returns the executor itself.

        Args:
            entry: An executor or structure

        Returns:
            The entry point executor
        """
        is_structure = getattr(entry, "_is_if_structure", False) or getattr(entry, "_is_switch_structure", False)
        return entry.evaluator if is_structure else entry

    def _get_branch_exit(self, branch_entry: Any) -> Any | None:
        """Get the exit executor of a branch.

        For a linear sequence of actions, returns the last executor.
        For nested structures, returns None (they have their own branch_exits).

        Args:
            branch_entry: The first executor of the branch

        Returns:
            The exit executor, or None if branch is empty or ends with a structure
        """
        if branch_entry is None:
            return None

        # Get the chain of executors in this branch
        chain = getattr(branch_entry, "_chain_executors", [branch_entry])

        last_executor = chain[-1]

        # Check if last executor is a structure with branch_exits
        # In that case, we return the structure so its exits can be collected
        if hasattr(last_executor, "branch_exits"):
            return last_executor

        # Regular executor - get its exit point
        return getattr(last_executor, "_exit_executor", last_executor)

    def _collect_all_exits(self, structure: Any) -> list[Any]:
        """Recursively collect all exit executors from a structure."""
        exits: list[Any] = []

        if not hasattr(structure, "branch_exits"):
            # Not a structure - return the executor itself
            actual_exit = getattr(structure, "_exit_executor", structure)
            return [actual_exit]

        for exit_item in structure.branch_exits:
            if hasattr(exit_item, "branch_exits"):
                # Nested structure - recurse
                exits.extend(self._collect_all_exits(exit_item))
            else:
                exits.append(exit_item)

        return exits
