# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any, Literal, cast

import pytest
from agent_framework import FunctionTool, ToolMode
from agent_framework.exceptions import ChatClientInvalidRequestException, ChatClientInvalidResponseException
from pydantic import BaseModel
from typesafe_sdk import SystemOneResponse

import agent_framework_typesafe._tool_calls as tool_calls
from agent_framework_typesafe._tool_calls import (
    MAX_ENUM_VALUES,
    MAX_INTERNAL_QUESTIONS,
    MAX_ROUTABLE_TOOLS,
    MAX_TOOL_PROPERTIES,
    TOOL_QUESTION_PREFIX,
    compile_tool_call_plan,
)


def response(answers: dict[str, dict[str, Any]]) -> SystemOneResponse:
    """Create a TypeSafe response for tool-plan decoding."""
    return SystemOneResponse.model_validate({
        "model": "jev-latest",
        "usage": {},
        "answers": answers,
    })


def function(name: str, schema: dict[str, Any]) -> FunctionTool:
    """Create a tool with an explicit JSON schema."""
    return FunctionTool(name=name, description=f"{name} tool", func=lambda **kwargs: kwargs, input_model=schema)


def test_reserved_question_ids_are_rejected() -> None:
    with pytest.raises(ChatClientInvalidRequestException, match="reserved"):
        compile_tool_call_plan(
            [function("noop", {})],
            tool_mode=None,
            user_question_ids={f"{TOOL_QUESTION_PREFIX}.custom"},
        )


def test_tool_choice_none_skips_compilation() -> None:
    assert (
        compile_tool_call_plan(
            [function("unsupported", {"type": "string"})],
            tool_mode={"mode": "none"},
            user_question_ids=set(),
        )
        is None
    )


def test_previous_calls_are_included_in_routing_and_argument_questions() -> None:
    tool = function(
        "weather",
        {
            "type": "object",
            "properties": {"city": {"enum": ["Seattle", "Amsterdam"], "type": "string"}},
            "required": ["city"],
        },
    )

    plan = compile_tool_call_plan(
        [tool],
        tool_mode=None,
        user_question_ids=set(),
        previous_calls={"weather": [{"city": "Seattle"}]},
    )

    assert plan is not None
    route = plan.questions["__af_tool__.route"]
    argument = plan.questions["__af_tool__.t0.a0.value"]
    assert "Seattle" in str(route)
    assert "Seattle" in str(argument)
    assert "different value" in str(argument)


def test_required_tool_modes_validate_availability() -> None:
    with pytest.raises(ChatClientInvalidRequestException, match="no tools"):
        compile_tool_call_plan([], tool_mode={"mode": "required"}, user_question_ids=set())
    with pytest.raises(ChatClientInvalidRequestException, match="unavailable"):
        compile_tool_call_plan(
            [function("available", {})],
            tool_mode={"mode": "required", "required_function_name": "missing"},
            user_question_ids=set(),
        )


def test_empty_allowed_tools_denies_all_tools() -> None:
    assert (
        compile_tool_call_plan(
            [function("available", {})],
            tool_mode={"mode": "auto", "allowed_tools": []},
            user_question_ids=set(),
        )
        is None
    )
    with pytest.raises(ChatClientInvalidRequestException, match="no supported tools remain"):
        compile_tool_call_plan(
            [function("available", {})],
            tool_mode={"mode": "required", "allowed_tools": []},
            user_question_ids=set(),
        )


def test_auto_mode_omits_unsupported_tool() -> None:
    assert (
        compile_tool_call_plan(
            [
                function(
                    "search", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
                )
            ],
            tool_mode=None,
            user_question_ids=set(),
        )
        is None
    )


def test_required_name_missing_from_properties_is_rejected() -> None:
    missing_property = function(
        "broken",
        {
            "type": "object",
            "properties": {},
            "required": ["scope"],
        },
    )

    with pytest.raises(ChatClientInvalidRequestException, match="missing from properties"):
        compile_tool_call_plan(
            [missing_property],
            tool_mode={"mode": "required"},
            user_question_ids=set(),
        )


def test_root_schema_constraints_exclude_entire_tool() -> None:
    constrained = function(
        "delete_records",
        {
            "type": "object",
            "properties": {"scope": {"type": "string", "enum": ["one", "all"]}},
            "required": ["scope"],
            "allOf": [{"properties": {"scope": {"const": "one"}}}],
        },
    )

    assert compile_tool_call_plan([constrained], tool_mode=None, user_question_ids=set()) is None
    with pytest.raises(ChatClientInvalidRequestException, match="root-level.*allOf"):
        compile_tool_call_plan(
            [constrained],
            tool_mode={"mode": "required"},
            user_question_ids=set(),
        )


@pytest.mark.parametrize(
    "property_schema",
    [
        {
            "type": "string",
            "enum": ["one", "all"],
            "allOf": [{"const": "one"}],
        },
        {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["one", "all"],
                "allOf": [{"const": "one"}],
            },
        },
    ],
    ids=["argument", "array-item"],
)
def test_nested_schema_constraints_exclude_entire_tool(property_schema: dict[str, Any]) -> None:
    constrained = function(
        "delete_records",
        {
            "type": "object",
            "properties": {"scope": property_schema},
            "required": ["scope"],
        },
    )

    assert compile_tool_call_plan([constrained], tool_mode=None, user_question_ids=set()) is None
    with pytest.raises(ChatClientInvalidRequestException, match="allOf"):
        compile_tool_call_plan(
            [constrained],
            tool_mode={"mode": "required"},
            user_question_ids=set(),
        )


def test_unsupported_optional_argument_excludes_entire_tool() -> None:
    broad_default = function(
        "delete_records",
        {
            "type": "object",
            "properties": {"scope": {"type": "string", "default": "all"}},
        },
    )

    assert compile_tool_call_plan([broad_default], tool_mode=None, user_question_ids=set()) is None
    with pytest.raises(ChatClientInvalidRequestException, match="optional argument 'scope'"):
        compile_tool_call_plan(
            [broad_default],
            tool_mode={"mode": "required"},
            user_question_ids=set(),
        )


def test_routable_tool_limit_is_enforced_before_compilation(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = [function(f"tool_{index}", {}) for index in range(MAX_ROUTABLE_TOOLS + 1)]

    def fail_if_called(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("tool compilation should not run")

    monkeypatch.setattr("agent_framework_typesafe._tool_calls._compile_tool", fail_if_called)

    with pytest.raises(ChatClientInvalidRequestException, match="at most"):
        compile_tool_call_plan(tools, tool_mode=None, user_question_ids=set())


@pytest.mark.parametrize(
    "tool_mode",
    [
        {"mode": "auto", "allowed_tools": ["tool_0"]},
        {"mode": "required", "required_function_name": "tool_0"},
    ],
    ids=["allowed", "required"],
)
def test_routable_tool_limit_is_applied_after_tool_filter(tool_mode: ToolMode) -> None:
    tools = [function(f"tool_{index}", {}) for index in range(MAX_ROUTABLE_TOOLS + 1)]

    plan = compile_tool_call_plan(
        tools,
        tool_mode=tool_mode,
        user_question_ids=set(),
    )

    assert plan is not None
    assert [tool.function.name for tool in plan.tools] == ["tool_0"]


def test_cumulative_question_limit_is_enforced_before_materialization(monkeypatch: pytest.MonkeyPatch) -> None:
    created_questions = 0
    original_noul = tool_calls.Noul

    def counting_noul(*args: Any, **kwargs: Any) -> Any:
        nonlocal created_questions
        created_questions += 1
        if created_questions > MAX_INTERNAL_QUESTIONS:
            raise AssertionError("question materialization exceeded the cumulative budget")
        return original_noul(*args, **kwargs)

    monkeypatch.setattr(tool_calls, "Noul", counting_noul)
    enum_values = [f"value_{index}" for index in range(MAX_ENUM_VALUES)]
    tools = [
        function(
            f"tool_{tool_index}",
            {
                "type": "object",
                "properties": {
                    "values": {
                        "type": "array",
                        "items": {"type": "string", "enum": enum_values},
                    }
                },
                "required": ["values"],
            },
        )
        for tool_index in range(3)
    ]

    with pytest.raises(ChatClientInvalidRequestException, match="more than 128 internal questions"):
        compile_tool_call_plan(tools, tool_mode=None, user_question_ids=set())

    assert created_questions == MAX_INTERNAL_QUESTIONS


def test_unsupported_tool_rolls_back_cumulative_question_budget() -> None:
    enum_values = [f"value_{index}" for index in range(MAX_ENUM_VALUES)]
    expensive_unsupported = function(
        "unsupported",
        {
            "type": "object",
            "properties": {
                "first": {
                    "type": "array",
                    "items": {"type": "string", "enum": enum_values},
                },
                "second": {
                    "type": "array",
                    "items": {"type": "string", "enum": enum_values},
                },
                "unrepresentable": {"type": "string"},
            },
            "required": ["first", "second", "unrepresentable"],
        },
    )
    valid = function("valid", {})

    plan = compile_tool_call_plan(
        [expensive_unsupported, valid],
        tool_mode=None,
        user_question_ids=set(),
    )

    assert plan is not None
    assert [tool.function.name for tool in plan.tools] == ["valid"]


def test_tool_property_limit_is_enforced_before_compilation() -> None:
    properties = {f"field_{index}": {"type": "boolean"} for index in range(MAX_TOOL_PROPERTIES + 1)}

    with pytest.raises(ChatClientInvalidRequestException, match="properties"):
        compile_tool_call_plan(
            [function("large", {"type": "object", "properties": properties})],
            tool_mode={"mode": "required"},
            user_question_ids=set(),
        )


def test_enum_value_limit_is_enforced_before_materialization() -> None:
    enum_values = [f"value_{index}" for index in range(MAX_ENUM_VALUES + 1)]

    with pytest.raises(ChatClientInvalidRequestException, match="enum defines"):
        compile_tool_call_plan(
            [
                function(
                    "large_enum",
                    {
                        "type": "object",
                        "properties": {"value": {"type": "string", "enum": enum_values}},
                        "required": ["value"],
                    },
                )
            ],
            tool_mode={"mode": "required"},
            user_question_ids=set(),
        )


@pytest.mark.parametrize("constraint", ["minItems", "maxItems", "uniqueItems", "prefixItems", "contains"])
def test_constrained_enum_arrays_are_rejected(constraint: str) -> None:
    constrained = function(
        "select",
        {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["a", "b"]},
                    constraint: 1 if constraint != "uniqueItems" else True,
                }
            },
            "required": ["values"],
        },
    )

    with pytest.raises(ChatClientInvalidRequestException, match="constraints"):
        compile_tool_call_plan(
            [constrained],
            tool_mode={"mode": "required"},
            user_question_ids=set(),
        )


def test_optional_nullable_enum_and_const_decode_deterministically() -> None:
    class Arguments(BaseModel):
        unit: Literal["c", "f"] | None = None
        version: Literal["v1"] = "v1"

    tool = FunctionTool(name="weather", func=lambda **kwargs: kwargs, input_model=Arguments)
    plan = compile_tool_call_plan(
        [tool],
        tool_mode=cast(ToolMode, {"mode": "required", "required_function_name": "weather"}),
        user_question_ids=set(),
    )

    assert plan is not None
    selected = plan.decode(
        response({
            "__af_tool__.t0.a0.present": {"type": "noul", "noul": 0.9},
            "__af_tool__.t0.a0.value": {
                "type": "choice",
                "choice": "v1",
                "confidence": 1.0,
                "probabilities": {"v0": 0.0, "v1": 1.0},
            },
            "__af_tool__.t0.a1.present": {"type": "noul", "noul": 0.9},
        })
    )

    assert selected is not None
    assert selected[1] == {"unit": "f", "version": "v1"}


def test_required_nullable_argument_is_unsupported() -> None:
    nullable_required = function(
        "nullable",
        {
            "type": "object",
            "properties": {
                "value": {
                    "anyOf": [
                        {"enum": ["a", "b"], "type": "string"},
                        {"type": "null"},
                    ]
                }
            },
            "required": ["value"],
        },
    )

    with pytest.raises(ChatClientInvalidRequestException, match="nullable"):
        compile_tool_call_plan(
            [nullable_required],
            tool_mode={"mode": "required"},
            user_question_ids=set(),
        )


def test_unknown_route_and_missing_answers_are_rejected() -> None:
    plan = compile_tool_call_plan([function("noop", {})], tool_mode=None, user_question_ids=set())
    assert plan is not None

    with pytest.raises(ChatClientInvalidResponseException, match="missing Choice"):
        plan.decode(response({}))
    with pytest.raises(ChatClientInvalidResponseException, match="unknown tool route"):
        plan.decode(
            response({
                "__af_tool__.route": {
                    "type": "choice",
                    "choice": "unknown",
                    "confidence": 1.0,
                    "probabilities": {"unknown": 1.0},
                }
            })
        )
