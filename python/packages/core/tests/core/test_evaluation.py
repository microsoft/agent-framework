# Copyright (c) Microsoft. All rights reserved.

"""Tests for provider-neutral evaluation item construction and splitting."""

from __future__ import annotations

import asyncio
import pickle
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any, Literal, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry.sdk.metrics import MeterProvider

from agent_framework import AgentEvalConverter as ExportedAgentEvalConverter
from agent_framework._agents import Agent, SupportsAgentRun
from agent_framework._clients import BaseChatClient
from agent_framework._evaluation import (
    AgentEvalConverter,
    ConversationSplit,
    EvalItem,
    LocalEvaluator,
    _to_eval_item,
    evaluate_agent,
    evaluator,
)
from agent_framework._harness._agent import create_harness_agent
from agent_framework._harness._loop import AgentLoopMiddleware
from agent_framework._mcp import MCPTool
from agent_framework._middleware import ChatContext, FunctionInvocationContext
from agent_framework._sessions import AgentSession, ContextProvider, SessionContext
from agent_framework._skills import InlineSkill, SkillFrontmatter, SkillsProvider
from agent_framework._tools import FunctionInvocationLayer, FunctionTool
from agent_framework._types import (
    AgentResponse,
    AgentResponseUpdate,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    _get_operation_state,
    _set_operation_state,
)


class _FunctionOnlyChatClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    def __init__(self, backend: Any) -> None:
        super().__init__()
        self.backend = backend

    def _inner_get_response(self, *, messages: Any, stream: bool, options: Any, **kwargs: Any) -> Any:
        assert "_evaluation_tool_capture" not in kwargs
        return self.backend._inner_get_response(messages=messages, stream=stream, options=options, **kwargs)


class TestAgentEvalConverterCompatibility:
    def test_root_export_is_legacy_converter(self) -> None:
        assert ExportedAgentEvalConverter is AgentEvalConverter

    def test_convert_messages_preserves_legacy_foundry_wire_format(self) -> None:
        messages = [
            Message("user", ["What's the weather?"]),
            Message(
                "assistant",
                [Content.from_function_call(call_id="call_1", name="get_weather", arguments={"city": "Seattle"})],
            ),
        ]

        with pytest.warns(DeprecationWarning, match="AgentEvalConverter"):
            converted = AgentEvalConverter.convert_messages(messages)

        assert converted == [
            {"role": "user", "content": [{"type": "text", "text": "What's the weather?"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_call",
                        "tool_call_id": "call_1",
                        "name": "get_weather",
                        "arguments": {"city": "Seattle"},
                    }
                ],
            },
        ]

    def test_to_eval_item_delegates_to_provider_neutral_builder(self) -> None:
        response = AgentResponse(messages=[Message("assistant", ["Sunny."])])

        with pytest.warns(DeprecationWarning, match="AgentEvalConverter"):
            item = AgentEvalConverter.to_eval_item(query="Weather?", response=response)

        assert item.query == "Weather?"
        assert item.response == "Sunny."


class TestToEvalItem:
    def test_string_query(self) -> None:
        response = AgentResponse(messages=[Message("assistant", ["The weather is sunny."])])
        item = _to_eval_item(query="What's the weather?", response=response)

        assert item.query == "What's the weather?"
        assert item.response == "The weather is sunny."
        assert [message.role for message in item.conversation] == ["user", "assistant"]

    def test_message_query(self) -> None:
        input_messages = [
            Message("system", ["Be helpful."]),
            Message("user", ["Hello"]),
        ]
        response = AgentResponse(messages=[Message("assistant", ["Hi there!"])])

        item = _to_eval_item(query=input_messages, response=response)

        assert item.query == "Hello"
        assert len(item.conversation) == 3

    def test_with_context(self) -> None:
        response = AgentResponse(messages=[Message("assistant", ["Answer."])])

        item = _to_eval_item(
            query="Question?",
            response=response,
            context="Some reference document.",
        )

        assert item.context == "Some reference document."

    def test_with_explicit_tools(self) -> None:
        def search(query: str) -> str:
            """Search the web."""
            return f"Results for {query}"

        response = AgentResponse(messages=[Message("assistant", ["Found it."])])

        item = _to_eval_item(query="Find info", response=response, tools=[search])

        assert item.tools is not None
        assert len(item.tools) == 1
        assert item.tools[0].name == "search"

    def test_with_agent_and_mcp_tools(self) -> None:
        agent_tool = FunctionTool(name="calculate", description="Calculate", func=lambda value: str(value))
        mcp_tool = FunctionTool(name="search", description="Search", func=lambda query: query)
        agent = MagicMock()
        agent.default_options = {"tools": [agent_tool]}
        agent.mcp_tools = [MagicMock(functions=[agent_tool, mcp_tool])]
        response = AgentResponse(messages=[Message("assistant", ["Done"])])

        item = _to_eval_item(query="Research this", response=response, agent=agent)

        assert item.tools == [agent_tool, mcp_tool]

    def test_explicit_tools_override_agent(self) -> None:
        agent_tool = FunctionTool(name="agent_tool", description="from agent", func=lambda: "")
        explicit_tool = FunctionTool(name="explicit_tool", description="explicit", func=lambda: "")
        agent = MagicMock()
        agent.default_options = {"tools": [agent_tool]}
        response = AgentResponse(messages=[Message("assistant", ["Done"])])

        item = _to_eval_item(
            query="Test",
            response=response,
            agent=agent,
            tools=[explicit_tool],
        )

        assert item.tools == [explicit_tool]

    def test_explicit_empty_tools_override_agent(self) -> None:
        agent = MagicMock()
        agent.default_options = {"tools": [FunctionTool(name="unused", func=lambda: "")]}

        item = _to_eval_item(query="Test", response=AgentResponse(), agent=agent, tools=[])

        assert item.tools is None

    @pytest.mark.parametrize("stream", [False, True])
    async def test_with_agent_context_provider_tools(self, chat_client_base: Any, stream: bool) -> None:
        skill = InlineSkill(
            frontmatter=SkillFrontmatter(name="test-skill", description="A test skill."),
            instructions="Skill instructions.",
        )
        provider = SkillsProvider(skill, disable_load_skill_approval=True)
        provider.before_run = AsyncMock(wraps=provider.before_run)  # type: ignore[method-assign]
        default_tool = FunctionTool(name="calculate", description="Calculate", func=lambda: "42")
        mcp_tool = FunctionTool(name="search", description="Search", func=lambda: "Found it")
        mcp = MagicMock(spec=MCPTool)
        mcp.functions = [mcp_tool]
        mcp.is_connected = True
        mcp._prepare_for_run = AsyncMock()
        agent = Agent(client=chat_client_base, tools=[default_tool, mcp], context_providers=[provider])
        call = Content.from_function_call("call_1", "load_skill", arguments={"skill_name": "test-skill"})
        if stream:
            chat_client_base.streaming_responses = [
                [ChatResponseUpdate(role="assistant", contents=[call])],
                [ChatResponseUpdate(role="assistant", contents=[Content.from_text("Done")])],
            ]
            response = await agent.run("Use the skill", stream=True).get_final_response()
        else:
            chat_client_base.run_responses = [
                ChatResponse(messages=[Message("assistant", [call])]),
                ChatResponse(messages=[Message("assistant", ["Done"])]),
            ]
            response = await agent.run("Use the skill")

        item = _to_eval_item(query="Use the skill", response=response, agent=agent)

        assert item.tools is not None
        definitions = {tool.name: tool for tool in item.tools}
        assert set(definitions) == {
            "calculate",
            "search",
            "load_skill",
            "read_skill_resource",
            "run_skill_script",
        }
        assert len(item.tools) == len(definitions)
        assert definitions["calculate"].parameters() == default_tool.parameters()
        assert definitions["search"].parameters() == mcp_tool.parameters()
        assert all(tool.declaration_only for tool in item.tools)
        assert definitions["load_skill"].parameters()["required"] == ["skill_name"]
        expected_content = await skill.get_content()
        assert any(
            content.type == "function_result" and content.result == expected_content
            for message in response.messages
            for content in message.contents
        )
        provider.before_run.assert_awaited_once()

        # Post-hoc evaluation must use the original run, not the agent's current configuration.
        agent.context_providers.clear()
        agent.default_options["tools"] = []
        agent.mcp_tools.clear()
        for supplied_agent in (None, agent):
            captured = _to_eval_item(query="Use the skill", response=response, agent=supplied_agent).tools
            assert captured is not None
            assert {tool.name: tool.parameters() for tool in captured} == {
                tool.name: tool.parameters() for tool in item.tools
            }
        explicit_tool = FunctionTool(name="explicit", func=lambda: "")
        assert _to_eval_item(query="Test", response=response, tools=[explicit_tool]).tools == [explicit_tool]
        assert _to_eval_item(query="Test", response=response, tools=[]).tools is None
        serialized = response.to_dict()
        assert "tools" not in serialized
        assert AgentResponse.from_json(response.to_json()).messages[0].contents[0].name == "load_skill"
        restored = pickle.loads(pickle.dumps(response))
        for restored_response in [
            AgentResponse.from_dict(serialized),
            AgentResponse.from_json(response.to_json()),
            restored,
        ]:
            restored_item = _to_eval_item(query="Use the skill", response=restored_response)
            assert restored_item.tools is not None
            assert {tool.name: (tool.description, tool.parameters()) for tool in restored_item.tools} == {
                tool.name: (tool.description, tool.parameters()) for tool in item.tools
            }
            assert all(tool.declaration_only for tool in restored_item.tools)

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("replace_tool", [False, True])
    async def test_chat_middleware_exposure_overrides_prepared_tools(
        self, chat_client_base: Any, stream: bool, replace_tool: bool
    ) -> None:
        original = FunctionTool(name="search", input_model={"type": "object"}, func=lambda **kwargs: "Seattle")
        replacement = FunctionTool(
            name="search",
            input_model={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            func=lambda city: city,
        )
        exposed_tools = [replacement] if replace_tool else []

        async def change_tools(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            context.options = {**(context.options or {}), "tools": exposed_tools}
            await call_next()

        agent = Agent(client=chat_client_base, tools=[original], middleware=[change_tools])
        contents = [Content.from_text("Done")]
        if replace_tool:
            contents.insert(0, Content.from_function_call("call_1", "search", arguments={"city": "Seattle"}))
        chat_client_base.run_responses = [ChatResponse(messages=[Message("assistant", contents)])]
        chat_client_base.streaming_responses = [[ChatResponseUpdate(role="assistant", contents=contents)]]
        reconstructed_responses: list[AgentResponse[Any]] = []
        with patch.object(chat_client_base, "_inner_get_response", wraps=chat_client_base._inner_get_response) as model:
            if stream:
                response_stream = agent.run("Test", stream=True)
                updates = [AgentResponseUpdate.from_json(update.to_json()) async for update in response_stream]
                response = await response_stream.get_final_response()
                reconstructed_responses.append(AgentResponse.from_updates(updates))
            else:
                response = await agent.run("Test")
        assert model.call_count >= 1
        assert all(call.kwargs["options"]["tools"] == exposed_tools for call in model.call_args_list)

        for result in (
            response,
            *reconstructed_responses,
            AgentResponse.from_dict(response.to_dict()),
            AgentResponse.from_json(response.to_json()),
            pickle.loads(pickle.dumps(response)),
        ):
            item = _to_eval_item(query="Test", response=result, agent=agent)
            if replace_tool:
                assert item.tools is not None
                assert [(tool.name, tool.parameters()) for tool in item.tools] == [("search", replacement.parameters())]
            else:
                assert item.tools is None

    @pytest.mark.parametrize("stream", [False, True])
    async def test_chat_middleware_removal_retains_previously_exposed_tools(
        self, chat_client_base: Any, stream: bool
    ) -> None:
        search = FunctionTool(name="search", func=lambda: "Seattle")
        exposed_tools: list[list[Any]] = []

        async def remove_after_first_call(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            if exposed_tools:
                context.options = {**(context.options or {}), "tools": []}
            exposed_tools.append(list((context.options or {}).get("tools") or []))
            await call_next()

        call = Content.from_function_call("call_1", "search", arguments={})
        chat_client_base.run_responses = [
            ChatResponse(messages=[Message("assistant", [call])]),
            ChatResponse(messages=[Message("assistant", ["Done"])]),
        ]
        chat_client_base.streaming_responses = [
            [ChatResponseUpdate(role="assistant", contents=[call])],
            [ChatResponseUpdate(role="assistant", contents=[Content.from_text("Done")])],
        ]
        agent = Agent(client=chat_client_base, tools=[search], middleware=[remove_after_first_call])
        if stream:
            response_stream = agent.run("Test", stream=True)
            updates = [AgentResponseUpdate.from_json(update.to_json()) async for update in response_stream]
            response = AgentResponse.from_updates(updates)
        else:
            response = await agent.run("Test")

        assert exposed_tools == [[search], []]
        for result in (response, AgentResponse.from_json(response.to_json())):
            item = _to_eval_item(query="Test", response=result)
            assert item.tools is not None
            assert [tool.name for tool in item.tools] == ["search"]

    @pytest.mark.parametrize("stream", [False, True])
    async def test_custom_client_retains_prepared_tool_fallback(self, client: Any, stream: bool) -> None:
        search = FunctionTool(name="search", func=lambda: "Seattle")
        agent = Agent(client=client, tools=[search])
        if stream:
            response_stream = agent.run("Test", stream=True)
            updates = [AgentResponseUpdate.from_json(update.to_json()) async for update in response_stream]
            response = AgentResponse.from_updates(updates)
        else:
            response = await agent.run("Test")

        for result in (response, AgentResponse.from_json(response.to_json())):
            item = _to_eval_item(query="Test", response=result)
            assert item.tools is not None
            assert [(tool.name, tool.parameters()) for tool in item.tools] == [("search", search.parameters())]

    async def test_context_provider_tools_are_isolated_per_run(self, chat_client_base: Any) -> None:
        class QueryToolsProvider(ContextProvider):
            async def before_run(
                self,
                *,
                agent: SupportsAgentRun,
                session: AgentSession,
                context: SessionContext,
                state: dict[str, Any],
            ) -> None:
                name = context.input_messages[0].text
                context.extend_tools(self.source_id, [FunctionTool(name=name, func=lambda: name)])
                await asyncio.sleep(0)

        provider = QueryToolsProvider("query-tools")
        provider.before_run = AsyncMock(wraps=provider.before_run)  # type: ignore[method-assign]
        agent = Agent(client=chat_client_base, context_providers=[provider])
        first, second = await asyncio.gather(agent.run("first"), agent.run("second"))

        for name, response in [("first", first), ("second", second)]:
            item = _to_eval_item(query=name, response=response, agent=agent)
            assert item.tools is not None
            assert [tool.name for tool in item.tools] == [name]
        assert provider.before_run.await_count == 2

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("chat_middleware", [False, True])
    async def test_progressively_exposed_tools_are_retained(
        self, chat_client_base: Any, stream: bool, chat_middleware: bool
    ) -> None:
        def finish(ctx: FunctionInvocationContext) -> str:
            ctx.remove_tools(["finish"])
            return "Finished"

        finish_tool = FunctionTool(name="finish", func=finish)

        def load(ctx: FunctionInvocationContext) -> str:
            ctx.add_tools([finish_tool])
            return "Loaded"

        loader = FunctionTool(name="load", func=load)
        calls = [
            Content.from_function_call("call_1", "load", arguments={}),
            Content.from_function_call("call_2", "finish", arguments={}),
        ]
        client = chat_client_base if chat_middleware else _FunctionOnlyChatClient(chat_client_base)
        agent = Agent(client=client, tools=[loader])
        if stream:
            chat_client_base.streaming_responses = [
                [ChatResponseUpdate(role="assistant", contents=[call])] for call in calls
            ]
            response_stream = agent.run("Test", stream=True)
            updates = [AgentResponseUpdate.from_json(update.to_json()) async for update in response_stream]
            response = await response_stream.get_final_response()
            assert sum("agent_framework.evaluation" in (update.additional_properties or {}) for update in updates) == 1
            assert "agent_framework.evaluation" in (updates[-1].additional_properties or {})
            restored_item = _to_eval_item(query="Test", response=AgentResponse.from_updates(updates))
            assert restored_item.tools is not None
            assert [tool.name for tool in restored_item.tools] == ["load", "finish"]
        else:
            chat_client_base.run_responses = [ChatResponse(messages=[Message("assistant", [call])]) for call in calls]
            response = await agent.run("Test")

        item = _to_eval_item(query="Test", response=response)

        assert item.tools is not None
        assert [tool.name for tool in item.tools] == ["load", "finish"]
        assert all(tool.declaration_only for tool in item.tools)
        assert any(
            content.type == "function_result" and content.result == "Finished"
            for message in response.messages
            for content in message.contents
        )

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("chat_middleware", [False, True])
    async def test_progressively_replaced_tool_rejects_ambiguous_evaluation(
        self, chat_client_base: Any, stream: bool, chat_middleware: bool
    ) -> None:
        replacement = FunctionTool(
            name="search",
            description="Search by city",
            input_model={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            func=lambda city: city,
        )

        def replace(ctx: FunctionInvocationContext) -> str:
            ctx.remove_tools(["search"])
            ctx.add_tools([replacement])
            return "Replaced"

        original = FunctionTool(name="search", description="Load city search", func=replace)
        client = chat_client_base if chat_middleware else _FunctionOnlyChatClient(chat_client_base)
        agent = Agent(client=client, tools=[original])
        calls = [
            Content.from_function_call("call_1", "search", arguments={}),
            Content.from_function_call("call_2", "search", arguments={"city": "Seattle"}),
        ]
        reconstructed_responses: list[AgentResponse[Any]] = []
        if stream:
            chat_client_base.streaming_responses = [
                [ChatResponseUpdate(role="assistant", contents=[call])] for call in calls
            ]
            response_stream = agent.run("Test", stream=True)
            updates = [update async for update in response_stream]
            response = await response_stream.get_final_response()
            reconstructed_responses.append(AgentResponse.from_updates(updates))
        else:
            chat_client_base.run_responses = [ChatResponse(messages=[Message("assistant", [call])]) for call in calls]
            response = await agent.run("Test")

        for result in (
            response,
            *reconstructed_responses,
            AgentResponse.from_dict(response.to_dict()),
            AgentResponse.from_json(response.to_json()),
            pickle.loads(pickle.dumps(response)),
        ):
            with pytest.raises(ValueError, match="search.*changed input schema"):
                _to_eval_item(query="Test", response=result)
            assert _to_eval_item(query="Test", response=result, tools=[replacement]).tools == [replacement]
            assert _to_eval_item(query="Test", response=result, tools=[]).tools is None
        assert any(
            content.type == "function_result" and content.result == "Seattle"
            for message in response.messages
            for content in message.contents
        )

    @pytest.mark.parametrize("constraint", ["const", "enum"])
    async def test_boolean_numeric_schema_change_rejects_evaluation(
        self, chat_client_base: Any, constraint: str
    ) -> None:
        def schema(value: bool | int) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"value": {constraint: [value] if constraint == "enum" else value}},
                "required": ["value"],
            }

        replacement = FunctionTool(name="search", input_model=schema(1), func=lambda value: str(value))

        def replace(value: bool, ctx: FunctionInvocationContext) -> str:
            ctx.remove_tools(["search"])
            ctx.add_tools([replacement])
            return "Replaced"

        original = FunctionTool(name="search", input_model=schema(True), func=replace)
        chat_client_base.run_responses = [
            ChatResponse(
                messages=[
                    Message("assistant", [Content.from_function_call("call_1", "search", arguments={"value": True})])
                ]
            ),
            ChatResponse(
                messages=[
                    Message("assistant", [Content.from_function_call("call_2", "search", arguments={"value": 1})])
                ]
            ),
        ]
        response = await Agent(client=chat_client_base, tools=[original]).run("Test")

        for result in (response, AgentResponse.from_json(response.to_json())):
            with pytest.raises(ValueError, match="search.*changed input schema"):
                _to_eval_item(query="Test", response=result)

    @pytest.mark.parametrize("serialization", ["dict", "json", "pickle"])
    async def test_empty_snapshot_survives_agent_reconfiguration(
        self, chat_client_base: Any, serialization: str
    ) -> None:
        agent = Agent(client=chat_client_base)
        response = await agent.run("No tools")
        agent.default_options["tools"] = [FunctionTool(name="unused", func=lambda: "")]
        if serialization == "dict":
            restored = AgentResponse.from_dict(response.to_dict())
        elif serialization == "json":
            restored = AgentResponse.from_json(response.to_json())
        else:
            restored = pickle.loads(pickle.dumps(response))

        assert restored.additional_properties["agent_framework.evaluation"] == {}
        assert _to_eval_item(query="No tools", response=restored, agent=agent).tools is None

    @pytest.mark.parametrize("replace_same_name", [False, True])
    async def test_empty_followup_stream_publishes_changed_tools(
        self, chat_client_base: Any, replace_same_name: bool
    ) -> None:
        added_tool = FunctionTool(
            name="load" if replace_same_name else "finish",
            description="New declaration",
            input_model={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            func=lambda city: city,
        )

        def load(ctx: FunctionInvocationContext) -> str:
            if replace_same_name:
                ctx.remove_tools(["load"])
            ctx.add_tools([added_tool])
            return "Loaded"

        agent = Agent(client=chat_client_base, tools=[FunctionTool(name="load", func=load)])
        chat_client_base.streaming_responses = [
            [
                ChatResponseUpdate(
                    role="assistant",
                    contents=[Content.from_function_call("call_1", "load", arguments={})],
                )
            ],
            [],
        ]
        stream = agent.run("Test", stream=True)
        updates = [AgentResponseUpdate.from_json(update.to_json()) async for update in stream]
        final = await stream.get_final_response()
        restored = AgentResponse.from_updates(updates)

        assert chat_client_base.call_count == 2
        assert updates[-1].contents == []
        assert (
            restored.additional_properties["agent_framework.evaluation"]
            == (final.additional_properties["agent_framework.evaluation"])
        )
        for response in (final, restored):
            if replace_same_name:
                with pytest.raises(ValueError, match="load.*changed input schema"):
                    _to_eval_item(query="Test", response=response)
                continue
            item = _to_eval_item(query="Test", response=response)
            assert item.tools is not None
            tools = {tool.name: tool for tool in item.tools}
            assert set(tools) == {"load", "finish"}
            assert tools[added_tool.name].description == added_tool.description
            assert tools[added_tool.name].parameters() == added_tool.parameters()

    @pytest.mark.parametrize("serialization", ["dict", "json", "pickle"])
    async def test_tuple_schema_constraints_survive_serialization(
        self, chat_client_base: Any, serialization: str
    ) -> None:
        schema = {
            "type": "object",
            "properties": {"city": {"type": "string", "enum": ("Seattle", "Paris")}},
            "required": ("city",),
        }
        tool = FunctionTool(name="weather", input_model=schema, func=lambda city: city)
        response = await Agent(client=chat_client_base, tools=[tool]).run("Weather?")
        if serialization == "dict":
            restored = AgentResponse.from_dict(response.to_dict())
        elif serialization == "json":
            restored = AgentResponse.from_json(response.to_json())
        else:
            restored = pickle.loads(pickle.dumps(response))

        item = _to_eval_item(query="Weather?", response=restored)
        assert item.tools is not None
        assert item.tools[0].parameters()["properties"]["city"]["enum"] == ["Seattle", "Paris"]
        assert item.tools[0].parameters()["required"] == ["city"]
        assert tool.parameters()["properties"]["city"]["enum"] == ("Seattle", "Paris")

    @pytest.mark.parametrize("serialization", ["dict", "json", "pickle"])
    async def test_schema_snapshots_do_not_retain_runtime_objects(
        self,
        chat_client_base: Any,
        serialization: str,
    ) -> None:
        schema = {
            "type": "object",
            "properties": {"city": {"type": "string", "enum": ["Seattle", "Paris"]}},
            "required": ["city"],
            "additionalProperties": False,
        }
        tool = FunctionTool(
            name="weather",
            description="Original description",
            func=lambda city: city,
            input_model=schema,
            additional_properties={"runtime_marker": "not-in-snapshot"},
        )
        agent = Agent(client=chat_client_base, tools=[tool])
        response = await agent.run("Weather?")
        tool.description = "Changed description"
        tool.parameters()["properties"]["city"]["enum"].append("London")
        agent.default_options["tools"] = []
        if serialization == "dict":
            restored = AgentResponse.from_dict(response.to_dict())
        elif serialization == "json":
            restored = AgentResponse.from_json(response.to_json())
        else:
            restored = pickle.loads(pickle.dumps(response))

        item = _to_eval_item(query="Weather?", response=restored, agent=agent)

        assert item.tools is not None
        assert len(item.tools) == 1
        captured = item.tools[0]
        assert captured.name == "weather"
        assert captured.description == "Original description"
        assert captured.parameters()["properties"]["city"]["enum"] == ["Seattle", "Paris"]
        assert captured.parameters()["additionalProperties"] is False
        assert captured.func is None
        assert captured.additional_properties is None
        metadata = response.to_dict()["additional_properties"]["agent_framework.evaluation"]
        assert metadata == {
            "weather": {
                "description": "Original description",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string", "enum": ["Seattle", "Paris"]}},
                    "required": ["city"],
                    "additionalProperties": False,
                },
            },
        }
        assert "not-in-snapshot" not in response.to_json()

    async def test_deepcopy_preserves_snapshots_without_copying_telemetry(
        self, chat_client_base: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        meter_provider = MeterProvider(shutdown_on_exit=False)
        monkeypatch.setattr("agent_framework._tools.get_meter", lambda: meter_provider.get_meter("evaluation-test"))
        monkeypatch.setattr("agent_framework.observability.OBSERVABILITY_SETTINGS.enable_instrumentation", True)
        try:
            tool = FunctionTool(
                name="weather",
                description="Get the weather",
                input_model={"type": "object", "properties": {"city": {"type": "string"}}},
                func=lambda city: city,
            )
            response = await Agent(client=chat_client_base, tools=[tool]).run("Weather?")
            copied = deepcopy(response)

            assert (
                copied.additional_properties["agent_framework.evaluation"]
                == (response.additional_properties["agent_framework.evaluation"])
            )
            item = _to_eval_item(query="Weather?", response=copied)
            assert item.tools is not None
            assert len(item.tools) == 1
            assert item.tools[0].name == tool.name
            assert item.tools[0].description == tool.description
            assert item.tools[0].parameters() == tool.parameters()
            assert item.tools[0].declaration_only
            item.tools[0].parameters()["properties"]["city"]["type"] = "number"
            assert copied.additional_properties["agent_framework.evaluation"]["weather"]["input_schema"] == (
                tool.parameters()
            )
            copied.additional_properties["agent_framework.evaluation"].clear()
            assert len(response.additional_properties["agent_framework.evaluation"]) == 1
        finally:
            meter_provider.shutdown()

    @pytest.mark.parametrize(
        "metadata",
        [
            None,
            [],
            {"weather": None},
            {"": {"description": "", "input_schema": {}}},
            {1: {"description": "", "input_schema": {}}},
            {"weather": {"description": None, "input_schema": {}}},
            {"weather": {"description": "", "input_schema": []}},
            {"weather": {"description": "", "input_schema": {"default": object()}}},
            {"weather": {"description": "", "input_schema": {}, "schema_changed": "yes"}},
        ],
    )
    def test_invalid_serialized_tool_metadata_raises(self, metadata: Any) -> None:
        response = AgentResponse(additional_properties={"agent_framework.evaluation": metadata})

        with pytest.raises(ValueError, match="agent_framework.evaluation"):
            _to_eval_item(query="Weather?", response=response)

        explicit = FunctionTool(name="explicit", func=lambda: "")
        assert _to_eval_item(query="Weather?", response=response, tools=[explicit]).tools == [explicit]


class TestEvaluateAgentTools:
    @pytest.mark.parametrize("with_approval_middleware", [False, True])
    @pytest.mark.parametrize("operation_state", [None, "in_progress", "terminal"])
    async def test_stream_tool_metadata_preserves_continuation(
        self,
        chat_client_base: Any,
        with_approval_middleware: bool,
        operation_state: Literal["in_progress", "terminal"] | None,
    ) -> None:
        token = {"response_id": "response_1"}
        update = ChatResponseUpdate(
            role="assistant",
            contents=[Content.from_text("Working")],
            continuation_token=cast(Any, token),
        )
        _set_operation_state(update, "in_progress" if operation_state == "terminal" else operation_state)
        provider_updates = [update]
        if operation_state == "terminal":
            terminal_update = ChatResponseUpdate(finish_reason="stop")
            _set_operation_state(terminal_update, "terminal")
            provider_updates.append(terminal_update)
        chat_client_base.streaming_responses = [provider_updates]

        if with_approval_middleware:
            agent = create_harness_agent(
                chat_client_base,
                disable_compaction=True,
                disable_todo=True,
                disable_mode=True,
                disable_file_memory=True,
                disable_web_search=True,
            )
        else:
            agent = Agent(client=chat_client_base)

        stream = agent.run("Test", stream=True, session=agent.create_session())
        updates = [update async for update in stream]
        final = await stream.get_final_response()
        restored_updates = [AgentResponseUpdate.from_json(update.to_json()) for update in updates]
        expected_token = None if operation_state == "terminal" else token

        for result in (final, AgentResponse.from_updates(updates), AgentResponse.from_updates(restored_updates)):
            assert result.continuation_token == expected_token
            assert _get_operation_state(result) == operation_state
            assert result.text == "Working"
            assert len(result.messages) == 1
            assert result.additional_properties["agent_framework.evaluation"] == {}

    @pytest.mark.parametrize("auto_approve", [False, True])
    async def test_harness_stream_preserves_provider_tools(self, chat_client_base: Any, auto_approve: bool) -> None:
        skill = InlineSkill(
            frontmatter=SkillFrontmatter(name="test-skill", description="A test skill."),
            instructions="Skill instructions.",
        )
        provider = SkillsProvider(skill)
        provider.before_run = AsyncMock(wraps=provider.before_run)  # type: ignore[method-assign]

        class ChangingToolsProvider(ContextProvider):
            async def before_run(
                self,
                *,
                agent: SupportsAgentRun,
                session: AgentSession,
                context: SessionContext,
                state: dict[str, Any],
            ) -> None:
                iteration = state["iteration"] = state.get("iteration", 0) + 1
                context.extend_tools(
                    self.source_id,
                    [
                        FunctionTool(name=f"iteration_{iteration}", func=lambda: ""),
                        FunctionTool(name="versioned", description=f"Version {iteration}", func=lambda: ""),
                    ],
                )

        agent = create_harness_agent(
            chat_client_base,
            context_providers=[provider, ChangingToolsProvider("changing")],
            disable_compaction=True,
            disable_todo=True,
            disable_mode=True,
            disable_file_memory=True,
            disable_web_search=True,
            auto_approval_rules=[SkillsProvider.all_tools_auto_approval_rule] if auto_approve else [],
        )
        chat_client_base.streaming_responses = [
            [
                ChatResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call("call_1", "load_skill", arguments={"skill_name": "test-skill"})
                    ],
                )
            ],
            [ChatResponseUpdate(role="assistant", contents=[Content.from_text("Done")])],
        ]
        response_stream = agent.run("Use the skill", stream=True, session=agent.create_session())
        updates = [AgentResponseUpdate.from_json(update.to_json()) async for update in response_stream]
        response = await response_stream.get_final_response()

        for result in (response, AgentResponse.from_updates(updates), AgentResponse.from_json(response.to_json())):
            item = _to_eval_item(query="Use the skill", response=result)
            assert item.tools is not None
            tools = {tool.name: tool for tool in item.tools}
            expected = {"load_skill", "read_skill_resource", "run_skill_script", "iteration_1", "versioned"}
            if auto_approve:
                expected.add("iteration_2")
            assert set(tools) == expected
            assert tools["versioned"].description == f"Version {2 if auto_approve else 1}"
        assert provider.before_run.await_count == (2 if auto_approve else 1)
        assert any(
            content.type == ("function_result" if auto_approve else "function_approval_request")
            for message in response.messages
            for content in message.contents
        )

    @pytest.mark.parametrize("empty_stream", [False, True])
    async def test_tool_free_stream_updates_preserve_empty_snapshot(
        self, chat_client_base: Any, empty_stream: bool
    ) -> None:
        if empty_stream:
            chat_client_base.streaming_responses = [[]]
        agent = Agent(client=chat_client_base)
        stream = agent.run("No tools", stream=True)
        updates = [AgentResponseUpdate.from_json(update.to_json()) async for update in stream]
        final = await stream.get_final_response()
        restored = AgentResponse.from_updates(updates)
        agent.default_options["tools"] = [FunctionTool(name="unrelated", func=lambda: "")]

        assert updates
        assert restored.text == final.text
        assert len(restored.messages) == len(final.messages)
        if empty_stream:
            assert restored.messages == final.messages == []
        assert _to_eval_item(query="No tools", response=restored, agent=agent).tools is None
        assert restored.additional_properties["agent_framework.evaluation"] == {}

    async def test_loop_aggregation_uses_latest_same_name_description(self, chat_client_base: Any) -> None:
        class ChangingToolsProvider(ContextProvider):
            async def before_run(
                self,
                *,
                agent: SupportsAgentRun,
                session: AgentSession,
                context: SessionContext,
                state: dict[str, Any],
            ) -> None:
                iteration = state["iteration"] = state.get("iteration", 0) + 1
                context.extend_tools(
                    self.source_id,
                    [
                        FunctionTool(name="search", description=f"Version {iteration}", func=lambda: ""),
                        FunctionTool(name=f"iteration_{iteration}", func=lambda: ""),
                    ],
                )

        agent = Agent(
            client=chat_client_base,
            context_providers=[ChangingToolsProvider("changing")],
            middleware=[AgentLoopMiddleware(lambda iteration, **kwargs: iteration < 2)],
        )
        response = await agent.run("Test", session=agent.create_session())
        for result in (response, AgentResponse.from_json(response.to_json())):
            item = _to_eval_item(query="Test", response=result)
            assert item.tools is not None
            tools = {tool.name: tool for tool in item.tools}
            assert set(tools) == {"search", "iteration_1", "iteration_2"}
            assert tools["search"].description == "Version 2"

    @pytest.mark.parametrize("stream", [False, True])
    async def test_loop_rejects_called_tool_with_changing_schema(self, chat_client_base: Any, stream: bool) -> None:
        class ChangingToolsProvider(ContextProvider):
            async def before_run(
                self,
                *,
                agent: SupportsAgentRun,
                session: AgentSession,
                context: SessionContext,
                state: dict[str, Any],
            ) -> None:
                iteration = state["iteration"] = state.get("iteration", 0) + 1
                context.extend_tools(
                    self.source_id,
                    [
                        FunctionTool(
                            name="search",
                            input_model={
                                "type": "object",
                                "properties": {"value": {"type": "integer", "enum": [min(iteration, 2)]}},
                                "required": ["value"],
                            },
                            func=lambda value: str(value),
                        )
                    ],
                )

        calls = [
            Content.from_function_call(f"call_{iteration}", "search", arguments={"value": min(iteration, 2)})
            for iteration in (1, 2, 3)
        ]
        agent = Agent(
            client=chat_client_base,
            context_providers=[ChangingToolsProvider("changing")],
            middleware=[AgentLoopMiddleware(lambda iteration, **kwargs: iteration < 3)],
        )
        if stream:
            chat_client_base.streaming_responses = [
                updates
                for call in calls
                for updates in (
                    [ChatResponseUpdate(role="assistant", contents=[call])],
                    [ChatResponseUpdate(role="assistant", contents=[Content.from_text("Done")])],
                )
            ]
            response_stream = agent.run("Test", stream=True, session=agent.create_session())
            updates = [update async for update in response_stream]
            response = AgentResponse.from_updates(updates)
        else:
            chat_client_base.run_responses = [
                result
                for call in calls
                for result in (
                    ChatResponse(messages=[Message("assistant", [call])]),
                    ChatResponse(messages=[Message("assistant", ["Done"])]),
                )
            ]
            response = await agent.run("Test", session=agent.create_session())

        for result in (response, AgentResponse.from_json(response.to_json())):
            assert [
                content.arguments
                for message in result.messages
                for content in message.contents
                if content.type == "function_call"
            ] == [{"value": 1}, {"value": 2}, {"value": 2}]
            with pytest.raises(ValueError, match="search.*changed input schema"):
                _to_eval_item(query="Test", response=result)

    @pytest.mark.parametrize("tool_free_final", [False, True])
    async def test_streaming_loop_updates_retain_previous_tool_definitions(
        self, chat_client_base: Any, tool_free_final: bool
    ) -> None:
        class ChangingToolsProvider(ContextProvider):
            async def before_run(
                self,
                *,
                agent: SupportsAgentRun,
                session: AgentSession,
                context: SessionContext,
                state: dict[str, Any],
            ) -> None:
                iteration = state["iteration"] = state.get("iteration", 0) + 1
                if tool_free_final and iteration == 2:
                    return
                context.extend_tools(
                    self.source_id,
                    [
                        FunctionTool(name=f"iteration_{iteration}", func=lambda: "Done"),
                        FunctionTool(
                            name="search",
                            description=f"Version {iteration}",
                            input_model={
                                "type": "object",
                                "properties": {"value": {"type": "integer", "enum": [iteration]}},
                                "required": ["value"],
                            },
                            func=lambda value: str(value),
                        ),
                    ],
                )

        agent = Agent(
            client=chat_client_base,
            context_providers=[ChangingToolsProvider("changing")],
            middleware=[AgentLoopMiddleware(lambda iteration, **kwargs: iteration < 2)],
        )
        chat_client_base.streaming_responses = [
            [
                ChatResponseUpdate(
                    role="assistant",
                    contents=[Content.from_function_call("call_1", "iteration_1", arguments={})],
                )
            ],
            [ChatResponseUpdate(role="assistant", contents=[Content.from_text("First done")])],
            [ChatResponseUpdate(role="assistant", contents=[Content.from_text("Second done")])],
        ]
        stream = agent.run("Test", stream=True, session=agent.create_session())
        updates = [AgentResponseUpdate.from_json(update.to_json()) async for update in stream]
        final = await stream.get_final_response()
        restored = AgentResponse.from_updates(updates)
        item = _to_eval_item(query="Test", response=restored)

        assert item.tools is not None
        tools = {tool.name: tool for tool in item.tools}
        expected = {"search", "iteration_1"}
        if not tool_free_final:
            expected.add("iteration_2")
        assert set(tools) == expected
        version = 1 if tool_free_final else 2
        assert tools["search"].description == f"Version {version}"
        assert tools["search"].parameters()["properties"]["value"]["enum"] == [version]
        assert [
            content.name
            for message in restored.messages
            for content in message.contents
            if content.type == "function_call"
        ] == ["iteration_1"]
        assert final.text == "Second done"
        final_tools = _to_eval_item(query="Test", response=final).tools
        assert {tool.name for tool in final_tools or []} == (set() if tool_free_final else {"search", "iteration_2"})

    @pytest.mark.parametrize("return_final_only", [False, True])
    async def test_loop_response_retains_skill_tools(self, chat_client_base: Any, return_final_only: bool) -> None:
        skill = InlineSkill(
            frontmatter=SkillFrontmatter(name="test-skill", description="A test skill."),
            instructions="Skill instructions.",
        )
        agent = Agent(
            client=chat_client_base,
            context_providers=[SkillsProvider(skill)],
            middleware=[
                AgentLoopMiddleware(
                    lambda iteration, **kwargs: iteration < 2,
                    return_final_only=return_final_only,
                )
            ],
        )
        response = await agent.run("Test")

        item = _to_eval_item(query="Test", response=response)

        assert item.tools is not None
        assert {tool.name for tool in item.tools} == {"load_skill", "read_skill_resource", "run_skill_script"}
        assert len(item.tools) == 3
        assert chat_client_base.call_count == 2
        restored_item = _to_eval_item(query="Test", response=AgentResponse.from_json(response.to_json()))
        assert restored_item.tools is not None
        assert {tool.name for tool in restored_item.tools} == {"load_skill", "read_skill_resource", "run_skill_script"}

    async def test_evaluate_agent_includes_skill_tools(self, chat_client_base: Any) -> None:
        skill = InlineSkill(
            frontmatter=SkillFrontmatter(name="test-skill", description="A test skill."),
            instructions="Skill instructions.",
        )
        agent = Agent(client=chat_client_base, context_providers=[SkillsProvider(skill)])

        @evaluator
        def has_skill_tools(tools: list[FunctionTool]) -> bool:
            return "load_skill" in {tool.name for tool in tools}

        results = await evaluate_agent(
            agent=agent,
            queries="Test",
            evaluators=LocalEvaluator(has_skill_tools),
        )

        assert results[0].passed == 1

    @pytest.mark.parametrize("serialization", [None, "json", "pickle"])
    async def test_evaluate_existing_response_discovers_skill_tools(
        self,
        chat_client_base: Any,
        serialization: str | None,
    ) -> None:
        skill = InlineSkill(
            frontmatter=SkillFrontmatter(name="test-skill", description="A test skill."),
            instructions="Skill instructions.",
        )
        provider = SkillsProvider(skill)
        provider.before_run = AsyncMock(wraps=provider.before_run)  # type: ignore[method-assign]
        agent = Agent(client=chat_client_base, context_providers=[provider])
        response = await agent.run("Test")
        if serialization == "json":
            response = AgentResponse.from_json(response.to_json())
        elif serialization == "pickle":
            response = pickle.loads(pickle.dumps(response))

        @evaluator
        def has_skill_tools(tools: list[FunctionTool]) -> bool:
            return all(tool.declaration_only for tool in tools) and "load_skill" in {tool.name for tool in tools}

        results = await evaluate_agent(
            queries="Test",
            responses=response,
            evaluators=LocalEvaluator(has_skill_tools),
        )

        assert results[0].passed == 1
        assert chat_client_base.call_count == 1
        provider.before_run.assert_awaited_once()

    async def test_explicit_tools_override_fresh_run(self, chat_client_base: Any) -> None:
        configured_tool = FunctionTool(name="configured", func=lambda: "")
        explicit_tool = FunctionTool(name="explicit", func=lambda: "")
        agent = Agent(client=chat_client_base, tools=[configured_tool])

        @evaluator
        def has_explicit_tools(tools: list[FunctionTool]) -> bool:
            return tools == [explicit_tool]

        results = await evaluate_agent(
            agent=agent,
            queries="Test",
            tools=[explicit_tool],
            evaluators=LocalEvaluator(has_explicit_tools),
        )

        assert results[0].passed == 1

    async def test_explicit_tools_for_restored_response(self) -> None:
        response = AgentResponse.from_json(AgentResponse(messages=[Message("assistant", ["Done"])]).to_json())
        tool = FunctionTool(name="load_skill", func=lambda skill_name: skill_name)

        @evaluator
        def has_explicit_tools(tools: list[FunctionTool]) -> bool:
            return tools == [tool]

        results = await evaluate_agent(
            queries="Test",
            responses=response,
            tools=[tool],
            evaluators=LocalEvaluator(has_explicit_tools),
        )

        assert results[0].passed == 1


class TestEvalItemSplitting:
    def test_split_messages_format(self) -> None:
        tool = FunctionTool(name="test", description="Test", func=lambda: "")
        item = _to_eval_item(
            query="Q",
            response=AgentResponse(messages=[Message("assistant", ["Answer"])]),
            tools=[tool],
        )

        query_messages, response_messages = item.split_messages()

        assert [message.role for message in query_messages] == ["user"]
        assert [message.role for message in response_messages] == ["assistant"]
        assert item.tools == [tool]

    def test_multiturn_preserves_interleaving(self) -> None:
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's sunny in Seattle."]),
            Message("user", ["And tomorrow?"]),
            Message("assistant", [Content(type="function_call", name="get_forecast")]),
            Message("tool", [Content(type="function_result", result="Rain expected")]),
            Message("assistant", ["Rain is expected tomorrow."]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages()

        assert [message.role for message in query_messages] == ["user", "assistant", "user"]
        assert [message.role for message in response_messages] == ["assistant", "tool", "assistant"]

    def test_full_split(self) -> None:
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's 62°F in Seattle."]),
            Message("user", ["And tomorrow?"]),
            Message("assistant", ["Rain is expected tomorrow."]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, ConversationSplit.FULL)
        )

        assert [message.text for message in query_messages] == ["What's the weather?"]
        assert [message.role for message in response_messages] == ["assistant", "user", "assistant"]

    def test_full_split_includes_system_message(self) -> None:
        conversation = [
            Message("system", ["You are a weather assistant."]),
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's sunny."]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, ConversationSplit.FULL)
        )

        assert [message.role for message in query_messages] == ["system", "user"]
        assert [message.role for message in response_messages] == ["assistant"]

    def test_full_split_puts_tool_interactions_in_response(self) -> None:
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", [Content(type="function_call", name="get_weather")]),
            Message("tool", [Content(type="function_result", result="62°F")]),
            Message("assistant", ["It's 62°F."]),
            Message("user", ["Thanks!"]),
            Message("assistant", ["You're welcome!"]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, ConversationSplit.FULL)
        )

        assert len(query_messages) == 1
        assert len(response_messages) == 5

    def test_last_turn_is_default(self) -> None:
        conversation = [
            Message("user", ["Hello"]),
            Message("assistant", ["Hi there"]),
            Message("user", ["Bye"]),
            Message("assistant", ["Goodbye"]),
        ]
        item = EvalItem(conversation=conversation)

        default_query, default_response = item.split_messages()
        explicit_query, explicit_response = item.split_messages(split=cast(Any, ConversationSplit.LAST_TURN))

        assert default_query == explicit_query
        assert default_response == explicit_response

    def test_per_turn_items(self) -> None:
        conversation = [
            Message("user", ["What's the weather?"]),
            Message("assistant", ["It's 62°F."]),
            Message("user", ["And tomorrow?"]),
            Message("assistant", ["Rain expected."]),
        ]

        items = EvalItem.per_turn_items(conversation)

        assert len(items) == 2
        assert (items[0].query, items[0].response) == ("What's the weather?", "It's 62°F.")
        assert (items[1].query, items[1].response) == ("What's the weather? And tomorrow?", "Rain expected.")
        assert [len(item.conversation) for item in items] == [2, 4]

    def test_per_turn_items_preserve_tools(self) -> None:
        conversation = [
            Message("user", ["Check weather"]),
            Message("assistant", [Content(type="function_call", name="get_weather")]),
            Message("tool", [Content(type="function_result", result="sunny")]),
            Message("assistant", ["It's sunny."]),
            Message("user", ["Thanks"]),
            Message("assistant", ["You're welcome!"]),
        ]
        tool = FunctionTool(name="get_weather", description="Get weather")

        items = EvalItem.per_turn_items(conversation, tools=[tool])

        assert len(items) == 2
        assert items[0].tools == [tool]
        assert items[0].response == "It's sunny."
        assert items[1].response == "You're welcome!"

    def test_per_turn_items_without_user_messages(self) -> None:
        assert EvalItem.per_turn_items([Message("assistant", ["Hello"])]) == []

    def test_per_turn_items_single_turn(self) -> None:
        items = EvalItem.per_turn_items([
            Message("user", ["Hi"]),
            Message("assistant", ["Hello!"]),
        ])

        assert len(items) == 1
        assert (items[0].query, items[0].response) == ("Hi", "Hello!")

    def test_custom_splitter_callable(self) -> None:
        conversation = [
            Message("user", ["Remember my name is Alice"]),
            Message("assistant", ["Got it, Alice!"]),
            Message("user", ["What's the capital of France?"]),
            Message("assistant", [Content(type="function_call", name="retrieve_memory", call_id="m1")]),
            Message("tool", [Content(type="function_result", call_id="m1", result="User name: Alice")]),
            Message("assistant", ["The capital of France is Paris, Alice!"]),
        ]

        def split_before_memory(messages: list[Message]) -> tuple[list[Message], list[Message]]:
            for index, message in enumerate(messages):
                if any(content.name == "retrieve_memory" for content in message.contents):
                    return messages[:index], messages[index:]
            return EvalItem._split_last_turn_static(messages)

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, split_before_memory)
        )

        assert len(query_messages) == 3
        assert query_messages[-1].role == "user"
        assert len(response_messages) == 3
        assert response_messages[0].role == "assistant"

    def test_custom_splitter_fallback(self) -> None:
        conversation = [
            Message("user", ["Hello"]),
            Message("assistant", ["Hi there!"]),
        ]

        def split_before_memory(messages: list[Message]) -> tuple[list[Message], list[Message]]:
            for index, message in enumerate(messages):
                if any(content.name == "retrieve_memory" for content in message.contents):
                    return messages[:index], messages[index:]
            return EvalItem._split_last_turn_static(messages)

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, split_before_memory)
        )

        assert [message.role for message in query_messages] == ["user"]
        assert [message.role for message in response_messages] == ["assistant"]

    def test_custom_splitter_lambda(self) -> None:
        conversation = [
            Message("user", ["A"]),
            Message("assistant", ["B"]),
            Message("user", ["C"]),
            Message("assistant", ["D"]),
        ]

        query_messages, response_messages = EvalItem(conversation=conversation).split_messages(
            split=cast(Any, lambda messages: (messages[:2], messages[2:]))
        )

        assert len(query_messages) == 2
        assert len(response_messages) == 2

    def test_item_split_strategy_is_default(self) -> None:
        conversation = [
            Message("user", ["First"]),
            Message("assistant", ["Response 1"]),
            Message("user", ["Second"]),
            Message("assistant", ["Response 2"]),
        ]
        item = EvalItem(conversation=conversation, split_strategy=cast(Any, ConversationSplit.FULL))

        query_messages, response_messages = item.split_messages()

        assert [message.text for message in query_messages] == ["First"]
        assert len(response_messages) == 3

    def test_explicit_split_overrides_item_strategy(self) -> None:
        conversation = [
            Message("user", ["First"]),
            Message("assistant", ["Response 1"]),
            Message("user", ["Second"]),
            Message("assistant", ["Response 2"]),
        ]
        item = EvalItem(conversation=conversation, split_strategy=cast(Any, ConversationSplit.FULL))

        query_messages, response_messages = item.split_messages(split=cast(Any, ConversationSplit.LAST_TURN))

        assert len(query_messages) == 3
        assert query_messages[-1].text == "Second"
        assert len(response_messages) == 1

    def test_no_split_defaults_to_last_turn(self) -> None:
        item = EvalItem(
            conversation=[
                Message("user", ["Hello"]),
                Message("assistant", ["Hi"]),
            ]
        )

        query_messages, _ = item.split_messages()

        assert item.split_strategy is None
        assert [message.role for message in query_messages] == ["user"]
