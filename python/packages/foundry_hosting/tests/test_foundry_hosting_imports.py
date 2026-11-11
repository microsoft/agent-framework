# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
import subprocess
import sys
import textwrap
from typing import Any, cast
from unittest.mock import patch

import pytest

import agent_framework_foundry_hosting as hosting


def test_package_import_is_lazy() -> None:
    code = textwrap.dedent(
        """
        import sys

        import agent_framework_foundry_hosting

        assert "agent_framework_foundry_hosting._invocations_agent" not in sys.modules
        assert "agent_framework_foundry_hosting._invocations_shared" not in sys.modules
        assert "agent_framework_foundry_hosting._invocations_workflow" not in sys.modules
        assert "agent_framework_foundry_hosting._responses_agent" not in sys.modules
        assert "agent_framework_foundry_hosting._responses_shared" not in sys.modules
        assert "agent_framework_foundry_hosting._responses_workflow" not in sys.modules
        assert "agent_framework_foundry_hosting._scope" not in sys.modules
        assert "agent_framework_foundry_hosting._state_store" not in sys.modules
        assert "agent_framework_foundry_hosting._toolbox" not in sys.modules
        assert "agent_framework_foundry_hosting._shared" not in sys.modules
        assert "agent_framework_foundry_hosting._workflow_state" not in sys.modules
        """
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)


@pytest.mark.parametrize("protocol", ["Responses", "Invocations"])
@pytest.mark.parametrize("workflow_first", [False, True])
def test_protocol_hosts_import_independently_in_either_order(protocol: str, workflow_first: bool) -> None:
    agent = f"{protocol}HostServer"
    workflow = f"{protocol}WorkflowHostServer"
    names = (workflow, agent) if workflow_first else (agent, workflow)
    other_module = "agent" if workflow_first else "workflow"
    base = "ResponsesAgentServerHost" if protocol == "Responses" else "InvocationAgentServerHost"
    sdk_module = "responses.hosting" if protocol == "Responses" else "invocations"
    code = textwrap.dedent(
        f"""
        import sys

        from agent_framework_foundry_hosting import {names[0]}
        assert "agent_framework_foundry_hosting._{protocol.lower()}_{other_module}" not in sys.modules
        from agent_framework_foundry_hosting import {names[1]}
        from azure.ai.agentserver.{sdk_module} import {base}

        assert issubclass({agent}, {base})
        assert issubclass({workflow}, {base})
        """
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)


def test_native_workflow_exports_match_runtime_and_typing_namespace() -> None:
    import agent_framework.foundry as foundry

    import agent_framework_foundry_hosting as hosting

    for name in (
        "WorkflowTurn",
        "WorkflowSource",
        "ResponsesRequest",
        "response_input_messages",
        "ResponsesWorkflowHostServer",
        "InvocationsWorkflowHostServer",
    ):
        assert name in hosting.__all__
        assert name in dir(hosting)
        assert name in dir(foundry)
        assert getattr(foundry, name) is getattr(hosting, name)


@pytest.mark.parametrize("protocol", ["Responses", "Invocations"])
def test_host_signatures_expose_only_the_selected_execution_model(protocol: str) -> None:
    agent_host = getattr(hosting, f"{protocol}HostServer")
    workflow_host = getattr(hosting, f"{protocol}WorkflowHostServer")
    agent_parameters = inspect.signature(agent_host).parameters
    workflow_parameters = inspect.signature(workflow_host).parameters
    parser = "parse_input"

    assert agent_parameters["agent"].default is inspect.Parameter.empty
    assert "workflow" not in agent_parameters
    assert workflow_parameters["workflow"].default is inspect.Parameter.empty
    assert workflow_parameters[parser].default is inspect.Parameter.empty
    assert workflow_parameters[parser].kind is inspect.Parameter.KEYWORD_ONLY
    for legacy in ("parse_response", "parse_request"):
        assert legacy not in agent_parameters
        assert legacy not in workflow_parameters
    assert "checkpoint_store_provider" in workflow_parameters
    assert "checkpoint_store_provider" not in agent_parameters
    for name in ("agent", "agent_session_store_provider", "history_source", "background_source", "unsupported_options"):
        assert name not in workflow_parameters
    assert ("prepare_options" in workflow_parameters) is (protocol == "Responses")
    if protocol == "Responses":
        assert "response_store" in agent_parameters
        assert "store" not in agent_parameters


@pytest.mark.parametrize("protocol", ["Responses", "Invocations"])
@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda: None, id="zero-argument"),
        pytest.param(lambda model="gpt-4": None, id="optional-configuration"),
        pytest.param(lambda request=None: None, id="optional-request"),
        pytest.param(lambda _request: None, id="different-parameter-name"),
        pytest.param(lambda request, /: None, id="positional-only-request"),
        pytest.param(lambda *request: None, id="variadic-positional-request"),
        pytest.param(lambda **request: None, id="variadic-keyword-request"),
        pytest.param(lambda request, dependency: None, id="required-positional-dependency"),
        pytest.param(lambda request, *, dependency: None, id="required-keyword-dependency"),
        pytest.param(dict, id="uninspectable"),
    ],
)
def test_agent_hosts_reject_ambiguous_factories_before_sdk_construction(protocol: str, factory: Any) -> None:
    host = getattr(hosting, f"{protocol}HostServer")
    base = (
        "azure.ai.agentserver.responses.hosting.ResponsesAgentServerHost"
        if protocol == "Responses"
        else "azure.ai.agentserver.invocations.InvocationAgentServerHost"
    )
    with patch(f"{base}.__init__", return_value=None) as initialize:
        with pytest.raises(TypeError, match="required named 'request' parameter"):
            host(agent=factory)
        initialize.assert_not_called()


@pytest.mark.parametrize(
    ("protocol", "setting"),
    [
        ("Responses", "agent"),
        ("Responses", "agent_session_store_provider"),
        ("Responses", "function_approval_store_provider"),
        ("Responses", "history_source"),
        ("Responses", "background_source"),
        ("Responses", "unsupported_options"),
        ("Responses", "store"),
    ],
)
def test_workflow_hosts_reject_agent_settings_before_sdk_construction(protocol: str, setting: str) -> None:
    workflow_host = getattr(hosting, f"{protocol}WorkflowHostServer")
    parser = "parse_input"
    values: dict[str, Any] = {parser: lambda _: None, setting: None}
    base = (
        "azure.ai.agentserver.responses.hosting.ResponsesAgentServerHost"
        if protocol == "Responses"
        else "azure.ai.agentserver.invocations.InvocationAgentServerHost"
    )
    with patch(f"{base}.__init__", return_value=None) as initialize:
        with pytest.raises(TypeError, match=setting):
            workflow_host(workflow=lambda _: None, **values)
        initialize.assert_not_called()


@pytest.mark.parametrize("protocol", ["Responses", "Invocations"])
def test_workflow_hosts_validate_factories_and_parsers_at_construction(protocol: str) -> None:
    workflow_host = getattr(hosting, f"{protocol}WorkflowHostServer")
    parser = "parse_input"
    with pytest.raises(TypeError, match=parser):
        workflow_host(workflow=lambda _: None, **{parser: None})
    with pytest.raises(TypeError, match="one request"):
        workflow_host(workflow=lambda: None, **{parser: lambda _: None})


def test_legacy_responses_request_name_is_not_exported() -> None:
    assert "HostedResponseRequest" not in hosting.__all__
    assert "HostedResponseRequest" not in dir(hosting)
    with pytest.raises(AttributeError, match="HostedResponseRequest"):
        hosting.__getattr__("HostedResponseRequest")


@pytest.mark.parametrize(
    ("name", "legacy"),
    [
        ("ResponsesWorkflowHostServer", "parse_response"),
    ],
)
def test_legacy_parser_name_is_not_silently_forwarded_to_sdk(name: str, legacy: str) -> None:
    host = getattr(hosting, name)
    source = "workflow" if "Workflow" in name else "agent"
    values = {source: lambda _: None, "parse_input": lambda _: None, legacy: lambda _: None}
    base = (
        "azure.ai.agentserver.responses.hosting.ResponsesAgentServerHost"
        if name.startswith("Responses")
        else "azure.ai.agentserver.invocations.InvocationAgentServerHost"
    )
    with patch(f"{base}.__init__", return_value=None) as initialize:
        with pytest.raises(TypeError, match=f"{legacy} was renamed to parse_input"):
            host(**values)
        initialize.assert_not_called()


def test_responses_workflow_host_preserves_steering_guard() -> None:
    from azure.ai.agentserver.responses import ResponsesServerOptions

    with pytest.raises(RuntimeError, match="steerable_conversations=True is temporarily unavailable"):
        cast(Any, hosting.ResponsesWorkflowHostServer)(
            workflow=lambda _: None,
            parse_input=lambda _: None,
            options=ResponsesServerOptions(steerable_conversations=True),
        )
