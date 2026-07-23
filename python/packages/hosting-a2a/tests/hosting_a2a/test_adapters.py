# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast

from a2a.types import AgentCapabilities, AgentInterface, AgentSkill, Part, Role
from a2a.types import Message as A2AMessage
from agent_framework import (
    InlineSkill,
    Message,
    SkillFrontmatter,
    SkillsProvider,
    SupportsAgentRun,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunResult,
    executor,
)
from agent_framework_hosting import AgentState, WorkflowState
from google.protobuf.json_format import ParseDict
from pytest import raises

from agent_framework_hosting_a2a import AgentA2AAdapter, WorkflowA2AAdapter


@dataclass
class StructuredInput:
    value: str


async def test_agent_card_infers_metadata_and_keeps_a2a_policy_explicit() -> None:
    target = cast("SupportsAgentRun", SimpleNamespace(name="Travel Agent", description="Plans trips."))
    interface = AgentInterface(url="https://example.com/a2a", protocol_binding="JSONRPC")
    skill = AgentSkill(
        id="plan_trip",
        name="Plan trip",
        description="Plan a trip.",
        tags=["travel"],
        examples=["Plan a weekend in Paris."],
    )

    adapter = AgentA2AAdapter(
        AgentState(lambda: target),
        version="1.0.0",
        supported_interfaces=[interface],
        skills=[skill],
        capabilities=AgentCapabilities(streaming=True),
    )
    card = await adapter.get_card()

    assert card.name == "Travel Agent"
    assert card.description == "Plans trips."
    assert card.default_input_modes == ["text"]
    assert card.default_output_modes == ["text"]
    assert card.capabilities.streaming is True
    assert card.supported_interfaces == [interface]
    assert card.skills == [skill]
    run = adapter.a2a_to_run(A2AMessage(message_id="message-1", role=Role.ROLE_USER, parts=[Part(text="hello")]))
    assert isinstance(run["messages"], list)
    assert isinstance(run["messages"][0], Message)
    assert run["messages"][0].text == "hello"
    assert adapter.a2a_from_run(Message("assistant", ["hello"]))[0].text == "hello"
    with raises(ValueError, match="audio/wav"):
        adapter.a2a_to_run(
            A2AMessage(
                message_id="message-2",
                role=Role.ROLE_USER,
                parts=[Part(raw=b"audio", media_type="audio/wav")],
            )
        )
    assert adapter.a2a_to_run(
        A2AMessage(
            message_id="message-2",
            role=Role.ROLE_USER,
            parts=[Part(raw=b"audio", media_type="audio/wav")],
        ),
        validate_modes=False,
    )["messages"]


async def test_agent_card_requires_public_metadata_and_interface() -> None:
    target = cast("SupportsAgentRun", SimpleNamespace(name=None, description=None))

    with raises(ValueError, match="supported interface"):
        AgentA2AAdapter(target, version="1.0.0", supported_interfaces=[])

    with raises(ValueError, match="non-empty strings"):
        AgentA2AAdapter(
            target,
            version="1.0.0",
            supported_interfaces=[AgentInterface(url="https://example.com/a2a", protocol_binding="JSONRPC")],
            default_input_modes=[""],
        )

    with raises(ValueError, match="requires a name"):
        await AgentA2AAdapter(
            target,
            version="1.0.0",
            supported_interfaces=[AgentInterface(url="https://example.com/a2a", protocol_binding="JSONRPC")],
        ).get_card()


async def test_agent_card_infers_agent_framework_skills_and_can_disable_inference() -> None:
    skill = InlineSkill(
        frontmatter=SkillFrontmatter(name="plan-trip", description="Plan a trip."),
        instructions="Help the user plan a trip.",
    )
    target = cast(
        "SupportsAgentRun",
        SimpleNamespace(
            name="Travel Agent",
            description="Plans trips.",
            context_providers=[SkillsProvider([skill])],
        ),
    )
    interface = AgentInterface(url="https://example.com/a2a", protocol_binding="JSONRPC")

    inferred_card = await AgentA2AAdapter(
        target,
        version="1.0.0",
        supported_interfaces=[interface],
    ).get_card()
    explicit_card = await AgentA2AAdapter(
        target,
        version="1.0.0",
        supported_interfaces=[interface],
        skills=[skill],
        infer_skills=False,
    ).get_card()
    disabled_card = await AgentA2AAdapter(
        target,
        version="1.0.0",
        supported_interfaces=[interface],
        infer_skills=False,
    ).get_card()

    assert inferred_card.skills[0].id == "plan-trip"
    assert inferred_card.skills[0].description == "Plan a trip."
    assert inferred_card.skills[0].input_modes == ["text"]
    assert explicit_card.skills[0] == inferred_card.skills[0]
    assert disabled_card.skills == []


async def test_workflow_card_infers_json_input_and_text_output_modes() -> None:
    @executor(id="structured")
    async def structured(value: StructuredInput, ctx: WorkflowContext[object, str]) -> None:
        await ctx.yield_output(value.value)

    workflow = WorkflowBuilder(
        start_executor=structured,
        name="Structured Workflow",
        description="Processes structured input.",
        output_from=[structured],
    ).build()

    adapter = WorkflowA2AAdapter(
        WorkflowState(lambda: workflow),
        version="1.0.0",
        supported_interfaces=[AgentInterface(url="https://example.com/a2a", protocol_binding="JSONRPC")],
        default_input_modes=[],
        default_output_modes=[],
    )
    output_result = WorkflowRunResult([WorkflowEvent("output", "hello", executor_id="structured")])
    with raises(RuntimeError, match="get_card"):
        adapter.a2a_from_run(output_result)
    assert adapter.a2a_from_run(output_result, validate_modes=False)[0].text == "hello"

    card = await adapter.get_card()
    data_part = Part()
    ParseDict({"value": "hello"}, data_part.data)
    workflow_input = await adapter.a2a_to_run(
        A2AMessage(message_id="message-1", role=Role.ROLE_USER, parts=[data_part])
    )
    output_parts = adapter.a2a_from_run(output_result)

    assert card.name == "Structured Workflow"
    assert card.description == "Processes structured input."
    assert card.default_input_modes == ["application/json"]
    assert card.default_output_modes == ["text"]
    assert workflow_input == StructuredInput(value="hello")
    assert output_parts[0].text == "hello"


async def test_workflow_card_allows_explicit_modes_for_unsupported_types() -> None:
    @executor(id="custom")
    async def custom(value: object, ctx: WorkflowContext[object, object]) -> None:
        await ctx.yield_output(value)

    workflow = WorkflowBuilder(
        start_executor=custom,
        name="Custom Workflow",
        description="Processes a custom protocol value.",
        output_from=[custom],
    ).build()
    interface = AgentInterface(url="https://example.com/a2a", protocol_binding="JSONRPC")

    with raises(ValueError, match="Cannot infer"):
        await WorkflowA2AAdapter(
            workflow,
            version="1.0.0",
            supported_interfaces=[interface],
        ).get_card()

    card = await WorkflowA2AAdapter(
        workflow,
        version="1.0.0",
        supported_interfaces=[interface],
        default_input_modes=["application/x-custom"],
        default_output_modes=["application/x-custom"],
    ).get_card()

    assert card.default_input_modes == ["application/x-custom"]
    assert card.default_output_modes == ["application/x-custom"]


async def test_workflow_card_requires_one_input_type() -> None:
    from agent_framework import Executor, handler

    class MultipleInputs(Executor):
        @handler
        async def handle_text(self, value: str, ctx: WorkflowContext[object, str]) -> None:
            await ctx.yield_output(value)

        @handler
        async def handle_number(self, value: int, ctx: WorkflowContext[object, str]) -> None:
            await ctx.yield_output(str(value))

    workflow = WorkflowBuilder(
        start_executor=MultipleInputs(id="multiple"),
        name="Multiple",
        description="Multiple inputs.",
        output_from="all",
    ).build()

    with raises(ValueError, match="exactly one"):
        await WorkflowA2AAdapter(
            workflow,
            version="1.0.0",
            supported_interfaces=[AgentInterface(url="https://example.com/a2a", protocol_binding="JSONRPC")],
        ).get_card()
