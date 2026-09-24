# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from agent_framework import FunctionTool, ToolMode
from agent_framework.exceptions import ChatClientInvalidRequestException, ChatClientInvalidResponseException
from typesafe_sdk import Choice, ChoiceAnswer, Noul, NoulAnswer, Questions, SystemOneResponse

logger = logging.getLogger("agent_framework.typesafe")

TOOL_QUESTION_PREFIX = "__af_tool__"
TOOL_ROUTE_QUESTION_ID = f"{TOOL_QUESTION_PREFIX}.route"
TOOL_ROUTE_NONE = "none"
MAX_ROUTABLE_TOOLS = 32
MAX_INTERNAL_QUESTIONS = 128
MAX_TOOL_PROPERTIES = 64
MAX_ENUM_VALUES = 64
NOUL_TRUE_THRESHOLD = 0.5
_SCHEMA_ANNOTATION_KEYS = frozenset({
    "$comment",
    "$id",
    "$schema",
    "default",
    "deprecated",
    "description",
    "examples",
    "readOnly",
    "title",
    "writeOnly",
})
_SUPPORTED_ROOT_SCHEMA_KEYS = _SCHEMA_ANNOTATION_KEYS | {
    "$defs",
    "additionalProperties",
    "properties",
    "required",
    "type",
}
_SUPPORTED_ARGUMENT_SCHEMA_KEYS = _SCHEMA_ANNOTATION_KEYS | {"const", "enum", "items", "type"}
_SUPPORTED_ARRAY_ITEM_SCHEMA_KEYS = _SCHEMA_ANNOTATION_KEYS | {"enum", "type"}


class _UnsupportedToolSchema(ValueError):
    """Raised when a tool schema cannot be represented with TypeSafe questions."""


@dataclass
class _QuestionBudget:
    count: int = 0

    def reserve(self, count: int) -> None:
        next_count = self.count + count
        if next_count > MAX_INTERNAL_QUESTIONS:
            raise ChatClientInvalidRequestException(
                f"TypeSafe tool schemas require more than {MAX_INTERNAL_QUESTIONS} internal questions. "
                "Narrow the available tools."
            )
        self.count = next_count


@dataclass(frozen=True)
class _ArgumentPlan:
    name: str
    presence_question_id: str | None
    kind: Literal["const", "choice", "boolean", "set"]
    value_question_id: str | None = None
    member_question_ids: tuple[tuple[str, Any], ...] = ()
    values: tuple[tuple[str, Any], ...] = ()
    const_value: Any = None

    def decode(self, response: SystemOneResponse) -> tuple[bool, Any]:
        if self.presence_question_id is not None:
            presence = _get_noul(response, self.presence_question_id)
            if presence.noul <= NOUL_TRUE_THRESHOLD:
                return False, None

        if self.kind == "const":
            return True, self.const_value
        if self.kind == "boolean":
            if self.value_question_id is None:
                raise ChatClientInvalidResponseException(f"TypeSafe argument plan for {self.name!r} is incomplete.")
            return True, _get_noul(response, self.value_question_id).noul > NOUL_TRUE_THRESHOLD
        if self.kind == "choice":
            if self.value_question_id is None:
                raise ChatClientInvalidResponseException(f"TypeSafe argument plan for {self.name!r} is incomplete.")
            answer = _get_choice(response, self.value_question_id)
            values = dict(self.values)
            if answer.choice not in values:
                raise ChatClientInvalidResponseException(
                    f"TypeSafe returned unknown choice {answer.choice!r} for tool argument {self.name!r}."
                )
            return True, values[answer.choice]
        if self.kind == "set":
            return True, [
                value
                for question_id, value in self.member_question_ids
                if _get_noul(response, question_id).noul > NOUL_TRUE_THRESHOLD
            ]
        raise AssertionError(f"Unexpected argument plan kind: {self.kind}")


@dataclass(frozen=True)
class _CompiledTool:
    function: FunctionTool
    route_label: str
    questions: Questions
    arguments: tuple[_ArgumentPlan, ...]

    def decode_arguments(self, response: SystemOneResponse) -> dict[str, Any]:
        arguments: dict[str, Any] = {}
        for argument in self.arguments:
            include, value = argument.decode(response)
            if include:
                arguments[argument.name] = value
        return arguments


@dataclass(frozen=True)
class ToolCallPlan:
    """Compiled TypeSafe questions and decoders for one function-call decision."""

    questions: Questions
    tools: tuple[_CompiledTool, ...]
    route_question_id: str | None
    required_tool: _CompiledTool | None

    def decode(self, response: SystemOneResponse) -> tuple[FunctionTool, dict[str, Any]] | None:
        selected = self.required_tool
        if selected is None:
            if self.route_question_id is None:
                raise ChatClientInvalidResponseException("TypeSafe tool routing plan is incomplete.")
            route = _get_choice(response, self.route_question_id).choice
            if route == TOOL_ROUTE_NONE:
                return None
            selected = next((tool for tool in self.tools if tool.route_label == route), None)
            if selected is None:
                raise ChatClientInvalidResponseException(f"TypeSafe returned unknown tool route {route!r}.")
        return selected.function, selected.decode_arguments(response)


def compile_tool_call_plan(
    tools: list[FunctionTool],
    *,
    tool_mode: ToolMode | None,
    user_question_ids: set[str],
    previous_calls: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> ToolCallPlan | None:
    """Compile supported FunctionTool schemas into TypeSafe routing questions."""
    collisions = sorted(
        question_id for question_id in user_question_ids if question_id.startswith(TOOL_QUESTION_PREFIX)
    )
    if collisions:
        raise ChatClientInvalidRequestException(
            f"TypeSafe question IDs starting with {TOOL_QUESTION_PREFIX!r} are reserved: {', '.join(collisions)}."
        )

    mode = tool_mode.get("mode") if tool_mode is not None else "auto"
    if mode == "none":
        return None
    if not tools:
        if mode == "required":
            raise ChatClientInvalidRequestException("TypeSafe tool_choice is required, but no tools are available.")
        return None

    required_name = tool_mode.get("required_function_name") if tool_mode is not None else None
    allowed_names = set(tool_mode["allowed_tools"]) if tool_mode is not None and "allowed_tools" in tool_mode else None
    selected_tools = [
        tool
        for tool in tools
        if (allowed_names is None or tool.name in allowed_names)
        and (required_name is None or tool.name == required_name)
    ]

    if required_name is not None and not selected_tools:
        raise ChatClientInvalidRequestException(f"Required TypeSafe tool {required_name!r} is unavailable.")
    if len(selected_tools) > MAX_ROUTABLE_TOOLS:
        raise ChatClientInvalidRequestException(
            f"TypeSafe supports at most {MAX_ROUTABLE_TOOLS} routable tools per request. "
            "Use tool_choice.allowed_tools to narrow MCP or local tools."
        )

    compiled: list[_CompiledTool] = []
    unsupported: dict[str, str] = {}
    question_budget = _QuestionBudget()
    for index, tool in enumerate(selected_tools):
        try:
            compiled.append(
                _compile_tool(
                    tool,
                    index,
                    list((previous_calls or {}).get(tool.name, ())),
                    question_budget=question_budget,
                )
            )
        except _UnsupportedToolSchema as exc:
            unsupported[tool.name] = str(exc)

    if unsupported:
        for name, reason in unsupported.items():
            logger.warning("Excluding unsupported TypeSafe tool %r: %s", name, reason)

    if mode == "required" and not compiled:
        details = "; ".join(f"{name}: {reason}" for name, reason in unsupported.items())
        raise ChatClientInvalidRequestException(
            f"TypeSafe tool_choice is required, but no supported tools remain. {details}".rstrip()
        )

    if not compiled:
        return None

    required_tool = compiled[0] if mode == "required" and len(compiled) == 1 else None
    route_question_id: str | None = None
    questions: dict[str, Any] = {}
    if required_tool is None:
        route_question_id = TOOL_ROUTE_QUESTION_ID
        criteria: dict[str, str] = {}
        for tool in compiled:
            description = tool.function.description or f"Call the {tool.function.name} tool."
            prior = list((previous_calls or {}).get(tool.function.name, ()))
            if prior:
                description += (
                    " Call this tool again only if the latest user request still needs a distinct execution. "
                    f"Do not repeat argument sets already called this turn: {_describe_value(prior)}."
                )
            criteria[tool.route_label] = description
        if mode != "required":
            criteria[TOOL_ROUTE_NONE] = (
                "Do not call a tool because all requested tool actions are already satisfied, "
                "or because no tool is needed."
            )
        question_budget.reserve(1)
        questions[route_question_id] = Choice(
            instructions="Which available tool, if any, should handle the latest user request?",
            criteria=criteria,
        )

    for tool in compiled:
        questions.update(tool.questions)
    if len(questions) > MAX_INTERNAL_QUESTIONS:
        raise ChatClientInvalidRequestException(
            f"TypeSafe tool schemas generated {len(questions)} internal questions; "
            f"the supported maximum is {MAX_INTERNAL_QUESTIONS}. Narrow the available tools."
        )

    return ToolCallPlan(
        questions=cast(Questions, questions),
        tools=tuple(compiled),
        route_question_id=route_question_id,
        required_tool=required_tool,
    )


def _compile_tool(
    tool: FunctionTool,
    tool_index: int,
    previous_calls: list[Mapping[str, Any]],
    *,
    question_budget: _QuestionBudget,
) -> _CompiledTool:
    schema: dict[str, Any] = tool.parameters()
    if not schema:
        schema = cast(dict[str, Any], {"type": "object", "properties": {}})
    _reject_unsupported_schema_constraints(
        schema,
        supported_keys=_SUPPORTED_ROOT_SCHEMA_KEYS,
        location="root-level",
    )
    if schema.get("type") not in (None, "object"):
        raise _UnsupportedToolSchema("the top-level input schema must be an object")
    properties_raw: Any = schema.get("properties", {})
    if properties_raw is None:
        properties_raw = {}
    if not isinstance(properties_raw, dict):
        raise _UnsupportedToolSchema("the input schema properties must be an object")
    properties = cast(dict[str, Any], properties_raw)
    if len(properties) > MAX_TOOL_PROPERTIES:
        raise _UnsupportedToolSchema(
            f"the input schema defines {len(properties)} properties; the supported maximum is {MAX_TOOL_PROPERTIES}"
        )
    required_raw: Any = schema.get("required", [])
    if not isinstance(required_raw, (list, tuple)):
        raise _UnsupportedToolSchema("the input schema required field must be a string array")
    required_items = cast(list[Any] | tuple[Any, ...], required_raw)
    if not all(isinstance(item, str) for item in required_items):
        raise _UnsupportedToolSchema("the input schema required field must be a string array")
    required = {item for item in required_items if isinstance(item, str)}
    missing_required = sorted(required - properties.keys())
    if missing_required:
        raise _UnsupportedToolSchema(f"required arguments are missing from properties: {', '.join(missing_required)}")

    questions: dict[str, Any] = {}
    arguments: list[_ArgumentPlan] = []
    for argument_index, (name, raw_property) in enumerate(properties.items()):
        if not isinstance(name, str) or not isinstance(raw_property, dict):
            raise _UnsupportedToolSchema(f"argument {name!r} has an invalid schema")
        try:
            argument, argument_questions = _compile_argument(
                tool=tool,
                root_schema=schema,
                name=name,
                raw_schema=cast(dict[str, Any], raw_property),
                required=name in required,
                tool_index=tool_index,
                argument_index=argument_index,
                previous_values=[call[name] for call in previous_calls if name in call],
                question_budget=question_budget,
            )
        except _UnsupportedToolSchema as exc:
            qualifier = "required" if name in required else "optional"
            raise _UnsupportedToolSchema(f"{qualifier} argument {name!r}: {exc}") from exc
        arguments.append(argument)
        questions.update(argument_questions)

    return _CompiledTool(
        function=tool,
        route_label=f"t{tool_index}",
        questions=cast(Questions, questions),
        arguments=tuple(arguments),
    )


def _compile_argument(
    *,
    tool: FunctionTool,
    root_schema: dict[str, Any],
    name: str,
    raw_schema: dict[str, Any],
    required: bool,
    tool_index: int,
    argument_index: int,
    previous_values: list[Any],
    question_budget: _QuestionBudget,
) -> tuple[_ArgumentPlan, Questions]:
    schema, nullable = _resolve_schema(raw_schema, root_schema)
    _reject_unsupported_schema_constraints(
        schema,
        supported_keys=_SUPPORTED_ARGUMENT_SCHEMA_KEYS,
        location="argument",
    )
    if nullable and required:
        raise _UnsupportedToolSchema("required nullable arguments are not supported")

    prefix = f"{TOOL_QUESTION_PREFIX}.t{tool_index}.a{argument_index}"
    description = schema.get("description") or raw_schema.get("description") or schema.get("title") or name
    previous_instruction = (
        f" Values already used for this argument in earlier calls this turn: {_describe_value(previous_values)}. "
        "Choose a different value when the user requested another distinct call."
        if previous_values
        else ""
    )
    presence_question_id = None if required else f"{prefix}.present"
    questions: dict[str, Any] = {}

    if "const" in schema:
        question_budget.reserve(0 if required else 1)
        _add_presence_question(
            questions,
            presence_question_id=presence_question_id,
            tool=tool,
            name=name,
            description=description,
            previous_instruction=previous_instruction,
        )
        return (
            _ArgumentPlan(
                name=name,
                presence_question_id=presence_question_id,
                kind="const",
                const_value=schema["const"],
            ),
            cast(Questions, questions),
        )

    enum_values_raw = schema.get("enum")
    if isinstance(enum_values_raw, list) and enum_values_raw:
        enum_values = cast(list[Any], enum_values_raw)
        if len(enum_values) > MAX_ENUM_VALUES:
            raise _UnsupportedToolSchema(
                f"enum defines {len(enum_values)} values; the supported maximum is {MAX_ENUM_VALUES}"
            )
        if len(enum_values) == 1:
            question_budget.reserve(0 if required else 1)
            _add_presence_question(
                questions,
                presence_question_id=presence_question_id,
                tool=tool,
                name=name,
                description=description,
                previous_instruction=previous_instruction,
            )
            return (
                _ArgumentPlan(
                    name=name,
                    presence_question_id=presence_question_id,
                    kind="const",
                    const_value=enum_values[0],
                ),
                cast(Questions, questions),
            )
        values = tuple((f"v{index}", value) for index, value in enumerate(enum_values))
        question_id = f"{prefix}.value"
        question_budget.reserve(1 if required else 2)
        _add_presence_question(
            questions,
            presence_question_id=presence_question_id,
            tool=tool,
            name=name,
            description=description,
            previous_instruction=previous_instruction,
        )
        questions[question_id] = Choice(
            instructions=(
                f"For the {tool.name} tool, choose the {name} argument. "
                f"Argument meaning: {description}.{previous_instruction}"
            ),
            criteria={label: _describe_value(value) for label, value in values},
        )
        return (
            _ArgumentPlan(
                name=name,
                presence_question_id=presence_question_id,
                kind="choice",
                value_question_id=question_id,
                values=values,
            ),
            cast(Questions, questions),
        )

    schema_type = schema.get("type")
    if schema_type == "boolean":
        question_id = f"{prefix}.value"
        question_budget.reserve(1 if required else 2)
        _add_presence_question(
            questions,
            presence_question_id=presence_question_id,
            tool=tool,
            name=name,
            description=description,
            previous_instruction=previous_instruction,
        )
        questions[question_id] = Noul(
            instructions=(
                f"For the {tool.name} tool, should the {name} argument be true? "
                f"Argument meaning: {description}.{previous_instruction}"
            )
        )
        return (
            _ArgumentPlan(
                name=name,
                presence_question_id=presence_question_id,
                kind="boolean",
                value_question_id=question_id,
            ),
            cast(Questions, questions),
        )

    if schema_type == "array":
        items_raw = schema.get("items")
        if not isinstance(items_raw, dict):
            raise _UnsupportedToolSchema("array items must define an enum")
        items, items_nullable = _resolve_schema(cast(dict[str, Any], items_raw), root_schema)
        _reject_unsupported_schema_constraints(
            items,
            supported_keys=_SUPPORTED_ARRAY_ITEM_SCHEMA_KEYS,
            location="array item",
        )
        if items_nullable:
            raise _UnsupportedToolSchema("nullable array members are not supported")
        members_raw = items.get("enum")
        if not isinstance(members_raw, list) or not members_raw:
            raise _UnsupportedToolSchema("array items must define a non-empty enum")
        members = cast(list[Any], members_raw)
        if len(members) > MAX_ENUM_VALUES:
            raise _UnsupportedToolSchema(
                f"array enum defines {len(members)} values; the supported maximum is {MAX_ENUM_VALUES}"
            )
        question_budget.reserve(len(members) + (0 if required else 1))
        _add_presence_question(
            questions,
            presence_question_id=presence_question_id,
            tool=tool,
            name=name,
            description=description,
            previous_instruction=previous_instruction,
        )
        member_questions: list[tuple[str, Any]] = []
        for member_index, member in enumerate(members):
            question_id = f"{prefix}.m{member_index}"
            questions[question_id] = Noul(
                instructions=(
                    f"For the {tool.name} tool, should the {name} argument include {_describe_value(member)}? "
                    f"Argument meaning: {description}.{previous_instruction}"
                )
            )
            member_questions.append((question_id, member))
        return (
            _ArgumentPlan(
                name=name,
                presence_question_id=presence_question_id,
                kind="set",
                member_question_ids=tuple(member_questions),
            ),
            cast(Questions, questions),
        )

    raise _UnsupportedToolSchema("only const, enum/Literal, boolean, and arrays of enum/Literal values are supported")


def _resolve_schema(schema: dict[str, Any], root_schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    resolved = dict(schema)
    if "$ref" in resolved:
        ref = resolved.pop("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise _UnsupportedToolSchema("only local $defs references are supported")
        definition_name = ref.removeprefix("#/$defs/")
        definitions_raw = root_schema.get("$defs")
        if not isinstance(definitions_raw, dict):
            raise _UnsupportedToolSchema(f"unresolved schema reference {ref!r}")
        definitions = cast(dict[str, Any], definitions_raw)
        if not isinstance(definitions.get(definition_name), dict):
            raise _UnsupportedToolSchema(f"unresolved schema reference {ref!r}")
        resolved = {**cast(dict[str, Any], definitions[definition_name]), **resolved}

    nullable = False
    if "anyOf" in resolved:
        any_of_raw = resolved.pop("anyOf")
        if not isinstance(any_of_raw, list):
            raise _UnsupportedToolSchema("anyOf must be an array")
        any_of = cast(list[Any], any_of_raw)
        object_arms = [cast(dict[str, Any], item) for item in any_of if isinstance(item, dict)]
        non_null = [item for item in object_arms if item.get("type") != "null"]
        null_arms = [item for item in object_arms if item.get("type") == "null"]
        if len(non_null) != 1 or len(null_arms) != 1 or len(any_of) != 2:
            raise _UnsupportedToolSchema("only a single schema combined with null is supported")
        nested, _ = _resolve_schema(non_null[0], root_schema)
        resolved = {**nested, **resolved}
        nullable = True
    return resolved, nullable


def _add_presence_question(
    questions: dict[str, Any],
    *,
    presence_question_id: str | None,
    tool: FunctionTool,
    name: str,
    description: Any,
    previous_instruction: str,
) -> None:
    if presence_question_id is None:
        return
    questions[presence_question_id] = Noul(
        instructions=(
            f"For the {tool.name} tool, did the user explicitly specify the {name} argument? "
            f"Argument meaning: {description}.{previous_instruction}"
        )
    )


def _reject_unsupported_schema_constraints(
    schema: dict[str, Any],
    *,
    supported_keys: frozenset[str],
    location: str,
) -> None:
    unsupported_constraints = sorted(schema.keys() - supported_keys)
    if unsupported_constraints:
        raise _UnsupportedToolSchema(
            f"unsupported {location} schema constraints: {', '.join(unsupported_constraints)}"
        )


def _describe_value(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(value)


def _get_choice(response: SystemOneResponse, question_id: str) -> ChoiceAnswer:
    answer = response.answers.get(question_id)
    if not isinstance(answer, ChoiceAnswer):
        raise ChatClientInvalidResponseException(f"TypeSafe response is missing Choice answer {question_id!r}.")
    return answer


def _get_noul(response: SystemOneResponse, question_id: str) -> NoulAnswer:
    answer = response.answers.get(question_id)
    if not isinstance(answer, NoulAnswer):
        raise ChatClientInvalidResponseException(f"TypeSafe response is missing Noul answer {question_id!r}.")
    return answer
