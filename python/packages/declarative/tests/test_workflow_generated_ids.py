# Copyright (c) Microsoft. All rights reserved.

"""Generated graph IDs must not shadow explicit declarative action IDs."""

from copy import deepcopy
from typing import Any

import pytest

from agent_framework_declarative import WorkflowFactory
from agent_framework_declarative._workflows import DeclarativeWorkflowBuilder
from agent_framework_declarative._workflows._errors import DeclarativeWorkflowError

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False

_requires_powerfx = pytest.mark.skipif(not _powerfx_available, reason="PowerFx engine not available")


@pytest.mark.parametrize("explicit_first", [False, True])
async def test_unnamed_action_preserves_explicit_id(explicit_first: bool) -> None:
    explicit_id = "SendActivity_1" if explicit_first else "SendActivity_0"
    unnamed = {"kind": "SendActivity", "activity": "unnamed"}
    explicit = {"kind": "SendActivity", "id": explicit_id, "activity": "explicit"}
    actions = [explicit, unnamed] if explicit_first else [unnamed, explicit]
    workflow = WorkflowFactory().create_workflow_from_definition({"actions": actions})

    events = await workflow.run({})

    assert events.get_outputs() == (["explicit", "unnamed"] if explicit_first else ["unnamed", "explicit"])
    assert workflow.executors[explicit_id].id == explicit_id


@pytest.mark.parametrize("explicit_first", [False, True])
@pytest.mark.parametrize(
    ("kind", "suffix"),
    [
        pytest.param("If", "eval", marks=_requires_powerfx),
        pytest.param("If", "else_pass", marks=_requires_powerfx),
        pytest.param("ConditionGroup", "eval", marks=_requires_powerfx),
        pytest.param("ConditionGroup", "default", marks=_requires_powerfx),
        ("Foreach", "init"),
        ("Foreach", "next"),
        ("Foreach", "exit"),
    ],
)
async def test_control_flow_internal_ids_preserve_explicit_actions(
    kind: str, suffix: str, explicit_first: bool
) -> None:
    child = {"kind": "SendActivity", "activity": "control"}
    control: dict[str, Any] = {"kind": kind, "id": "branch"}
    if kind == "If":
        control.update(condition=True, then=[child])
    elif kind == "ConditionGroup":
        control["conditions"] = [{"condition": "=true", "actions": [child]}]
    else:
        control.update(source=[1, 2], actions=[child])
    explicit_id = f"branch_{suffix}"
    explicit = {"kind": "SendActivity", "id": explicit_id, "activity": "explicit"}
    actions = [explicit, control] if explicit_first else [control, explicit]
    workflow = WorkflowFactory().create_workflow_from_definition({"actions": actions})

    events = await workflow.run({})

    control_outputs = ["control", "control"] if kind == "Foreach" else ["control"]
    assert events.get_outputs() == (
        ["explicit", *control_outputs] if explicit_first else [*control_outputs, "explicit"]
    )
    assert workflow.executors[explicit_id].id == explicit_id


@_requires_powerfx
async def test_nested_explicit_id_is_reserved_before_parent_nodes_are_created() -> None:
    workflow = WorkflowFactory().create_workflow_from_definition({
        "actions": [
            {
                "kind": "If",
                "id": "branch",
                "condition": True,
                "then": [{"kind": "SendActivity", "id": "branch_eval", "activity": "nested"}],
            },
            {"kind": "SendActivity", "activity": "after"},
        ]
    })

    assert (await workflow.run({})).get_outputs() == ["nested", "after"]
    assert "branch_eval" in workflow.executors


async def test_generated_suffix_avoids_other_explicit_ids_and_goto_targets() -> None:
    workflow = WorkflowFactory().create_workflow_from_definition({
        "actions": [
            {"kind": "SendActivity", "activity": "first"},
            {"kind": "SendActivity", "id": "SendActivity_0_2", "activity": "suffix"},
            {"kind": "GotoAction", "actionId": "SendActivity_0"},
            {"kind": "SendActivity", "id": "SendActivity_0", "activity": "target"},
        ]
    })

    assert (await workflow.run({})).get_outputs() == ["first", "suffix", "target"]
    assert {"SendActivity_0", "SendActivity_0_2"} <= workflow.executors.keys()


async def test_id_allocation_does_not_require_schema_validation() -> None:
    workflow = DeclarativeWorkflowBuilder(
        {
            "actions": [
                {"kind": "SendActivity", "activity": "first"},
                {"kind": "SendActivity", "id": "SendActivity_0", "activity": "second"},
            ]
        },
        validate=False,
    ).build()

    assert (await workflow.run({})).get_outputs() == ["first", "second"]


async def test_noncolliding_generated_ids_are_unchanged() -> None:
    workflow = WorkflowFactory().create_workflow_from_definition({
        "actions": [
            {"kind": "SendActivity", "activity": "first"},
            {"kind": "SendActivity", "activity": "second"},
        ]
    })

    assert list(workflow.executors) == ["_workflow_entry", "SendActivity_0", "SendActivity_1"]
    assert (await workflow.run({})).get_outputs() == ["first", "second"]


def test_duplicate_explicit_action_ids_still_raise() -> None:
    with pytest.raises(DeclarativeWorkflowError, match="Duplicate action ID 'same'"):
        WorkflowFactory().create_workflow_from_definition({
            "actions": [
                {"kind": "SendActivity", "id": "same", "activity": "first"},
                {"kind": "SendActivity", "id": "same", "activity": "second"},
            ]
        })


@pytest.mark.parametrize("nested", [False, True])
def test_reserved_entry_action_id_still_raises(nested: bool) -> None:
    action: dict[str, Any] = {"kind": "SendActivity", "id": "_workflow_entry", "activity": "reserved"}
    if nested:
        action = {"kind": "If", "condition": True, "then": [action]}

    with pytest.raises(DeclarativeWorkflowError, match="reserved for internal use"):
        WorkflowFactory().create_workflow_from_definition({"actions": [action]})


@pytest.mark.parametrize("kind", ["BreakLoop", "ContinueLoop"])
@pytest.mark.parametrize("collide_with_next", [False, True])
async def test_loop_terminators_use_the_allocated_loop_node(kind: str, collide_with_next: bool) -> None:
    terminator_prefix = "Break" if kind == "BreakLoop" else "Continue"
    explicit_id = "loop_next" if collide_with_next else f"{terminator_prefix}_2"
    definition: dict[str, Any] = {
        "actions": [
            {
                "kind": "Foreach",
                "id": "loop",
                "source": [1, 2],
                "actions": [{"kind": "SendActivity", "activity": "inside"}, {"kind": kind}],
            },
            {"kind": "SendActivity", "id": explicit_id, "activity": "after"},
        ]
    }
    normal_definition = deepcopy(definition)
    normal_definition["actions"][1]["id"] = "after"
    normal = WorkflowFactory().create_workflow_from_definition(normal_definition)
    workflow = WorkflowFactory().create_workflow_from_definition(definition)

    assert (await workflow.run({})).get_outputs() == (await normal.run({})).get_outputs()


@pytest.mark.parametrize(
    "kind",
    [pytest.param("If", marks=_requires_powerfx), pytest.param("ConditionGroup", marks=_requires_powerfx), "Foreach"],
)
async def test_noncolliding_control_structure_name_is_unchanged(kind: str) -> None:
    child = {"kind": "SendActivity", "activity": "inside"}
    control: dict[str, Any] = {"kind": kind}
    if kind == "If":
        control.update(condition=True, then=[child])
        expected_ids = ["If_0_eval", "If_0_SendActivity_1", "If_0_else_pass"]
    elif kind == "ConditionGroup":
        control["conditions"] = [{"condition": "=true", "actions": [child]}]
        expected_ids = ["ConditionGroup_0_eval", "ConditionGroup_0_case0_SendActivity_1", "ConditionGroup_0_default"]
    else:
        control.update(source=[1], actions=[child])
        expected_ids = ["Foreach_0_init", "SendActivity_1", "Foreach_0_next", "Foreach_0_exit"]
    explicit_id = f"{kind}_0"
    workflow = WorkflowFactory().create_workflow_from_definition({
        "actions": [control, {"kind": "SendActivity", "id": explicit_id, "activity": "after"}]
    })

    assert list(workflow.executors) == ["_workflow_entry", *expected_ids, explicit_id]
    assert (await workflow.run({})).get_outputs() == ["inside", "after"]
