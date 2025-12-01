# Copyright (c) Microsoft. All rights reserved.

from types import SimpleNamespace

from agent_framework_ag_ui._orchestration._tooling import merge_tools, register_additional_client_tools


class DummyTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.declaration_only = True


def test_merge_tools_filters_duplicates() -> None:
    server = [DummyTool("a"), DummyTool("b")]
    client = [DummyTool("b"), DummyTool("c")]

    merged = merge_tools(server, client)

    assert merged is not None
    names = [getattr(t, "name", None) for t in merged]
    assert names == ["a", "b", "c"]


def test_register_additional_client_tools_assigns_when_configured() -> None:
    class Fic:
        def __init__(self) -> None:
            self.additional_tools = None

    holder = SimpleNamespace(function_invocation_configuration=Fic())
    agent = SimpleNamespace(chat_client=holder)

    tools = [DummyTool("x")]
    register_additional_client_tools(agent, tools)

    assert holder.function_invocation_configuration.additional_tools == tools
