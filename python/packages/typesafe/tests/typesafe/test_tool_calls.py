# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any, Literal, cast

import pytest
from agent_framework import FunctionTool, ToolMode
from agent_framework.exceptions import ChatClientInvalidRequestException, ChatClientInvalidResponseException
from pydantic import BaseModel
from typesafe_sdk import SystemOneResponse

from agent_framework_typesafe._tool_calls import (
    MAX_ROUTABLE_TOOLS,
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


def test_required_tool_modes_validate_availability() -> None:
    with pytest.raises(ChatClientInvalidRequestException, match="no tools"):
        compile_tool_call_plan([], tool_mode={"mode": "required"}, user_question_ids=set())
    with pytest.raises(ChatClientInvalidRequestException, match="unavailable"):
        compile_tool_call_plan(
            [function("available", {})],
            tool_mode={"mode": "required", "required_function_name": "missing"},
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


def test_routable_tool_limit_is_enforced() -> None:
    tools = [function(f"tool_{index}", {}) for index in range(MAX_ROUTABLE_TOOLS + 1)]

    with pytest.raises(ChatClientInvalidRequestException, match="at most"):
        compile_tool_call_plan(tools, tool_mode=None, user_question_ids=set())


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
