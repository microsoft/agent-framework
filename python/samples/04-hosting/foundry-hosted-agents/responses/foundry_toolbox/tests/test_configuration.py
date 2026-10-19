# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import re
from graphlib import TopologicalSorter
from pathlib import Path

import yaml

SAMPLE_ROOT = Path(__file__).parents[1]
AGENT_NAME = "agent-framework-agent-with-foundry-toolbox-responses"


def _configuration() -> dict:
    return yaml.safe_load((SAMPLE_ROOT / "azure.yaml").read_text(encoding="utf-8"))


def test_hosted_agent_preserves_metadata_protocol_and_resources() -> None:
    configuration = _configuration()
    agent = configuration["services"][AGENT_NAME]

    assert configuration["name"] == agent["name"] == AGENT_NAME
    assert agent["kind"] == "hosted"
    assert agent["description"] == "An Agent Framework agent with Foundry Toolbox integration."
    assert agent["metadata"]["tags"] == [
        "Agent Framework",
        "AI Agent Hosting",
        "Azure AI AgentServer",
        "Responses Protocol",
        "Streaming",
    ]
    assert agent["protocols"] == [{"protocol": "responses", "version": "2.0.0"}]
    assert agent["container"]["resources"] == {"cpu": "0.25", "memory": "0.5Gi"}
    assert configuration["infra"]["provider"] == "microsoft.foundry"


def test_flat_source_layout_is_independently_deployable() -> None:
    agent = _configuration()["services"][AGENT_NAME]

    assert agent["project"] == "."
    assert agent["language"] == "python"
    assert agent["codeConfiguration"] == {
        "dependencyResolution": "remote_build",
        "runtime": "python_3_13",
        "entryPoint": "main.py",
    }
    assert (SAMPLE_ROOT / agent["project"] / agent["codeConfiguration"]["entryPoint"]).is_file()
    assert (SAMPLE_ROOT / agent["project"] / "requirements.txt").is_file()


def test_model_and_runtime_environment_bindings() -> None:
    services = _configuration()["services"]
    deployment = services["ai-project"]["deployments"][0]

    assert deployment["name"] == deployment["model"]["name"] == "gpt-4.1"
    assert deployment["model"]["format"] == "OpenAI"
    assert isinstance(deployment["model"]["version"], str)
    assert services[AGENT_NAME]["env"] == {
        "FOUNDRY_PROJECT_ENDPOINT": "${FOUNDRY_PROJECT_ENDPOINT}",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": "${AZURE_AI_MODEL_DEPLOYMENT_NAME}",
        "TOOLBOX_ENDPOINT": "${TOOLBOX_AGENT_TOOLS_MCP_ENDPOINT}",
    }


def test_dependency_graph_orders_project_connections_toolbox_and_agent() -> None:
    services = _configuration()["services"]
    graph = {name: service.get("uses", []) for name, service in services.items()}

    assert all(dependency in services for dependencies in graph.values() for dependency in dependencies)
    order = list(TopologicalSorter(graph).static_order())
    assert order[0] == "ai-project"
    assert order[-1] == AGENT_NAME
    for connection in ("ghmcppat", "langmcpconn", "foundrymcpconn"):
        assert order.index(connection) < order.index("agent-tools")
        assert services[connection]["uses"] == ["ai-project"]
    assert services[AGENT_NAME]["uses"] == ["ai-project", "agent-tools"]


def test_six_tool_sources_use_declared_connections() -> None:
    services = _configuration()["services"]
    tools = services["agent-tools"]["tools"]

    assert [tool["type"] for tool in tools] == ["web_search", "code_interpreter", "mcp", "mcp", "mcp", "mcp"]
    assert all(tool["require_approval"] == "never" for tool in tools)
    mcp_tools = {tool["server_label"]: tool for tool in tools if tool["type"] == "mcp"}
    assert mcp_tools["noauth_mcp"]["server_url"] == "https://gitmcp.io/Azure/azure-rest-api-specs"
    assert "connection" not in mcp_tools["noauth_mcp"]
    for label, connection in (
        ("github", "ghmcppat"),
        ("language-mcp", "langmcpconn"),
        ("foundry-mcp", "foundrymcpconn"),
    ):
        assert mcp_tools[label]["connection"] == connection
        assert connection in services["agent-tools"]["uses"]
        assert mcp_tools[label]["server_url"] == services[connection]["target"]
        assert "project_connection_id" not in mcp_tools[label]


def test_authentication_and_external_inputs_are_forwarded_without_embedded_secrets() -> None:
    services = _configuration()["services"]

    assert services["ghmcppat"]["authType"] == "CustomKeys"
    assert services["ghmcppat"]["credentials"] == {
        "type": "CustomKeys",
        "keys": {"Authorization": "Bearer ${GITHUB_MCP_PAT}"},
    }
    assert services["langmcpconn"]["authType"] == "ProjectManagedIdentity"
    assert services["langmcpconn"]["audience"] == "https://cognitiveservices.azure.com/"
    assert services["foundrymcpconn"]["authType"] == "UserEntraToken"
    assert services["foundrymcpconn"]["audience"] == "https://mcp.ai.azure.com"
    assert "GITHUB_MCP_PAT" not in services[AGENT_NAME]["env"]
    for service in services.values():
        payload = {key: value for key, value in service.items() if key != "env"}
        references = re.findall(r"\$\{([^}]+)\}", yaml.safe_dump(payload))
        assert all(reference in service.get("env", {}) for reference in references)


def test_readme_uses_own_template_and_existing_local_links() -> None:
    readme = (SAMPLE_ROOT / "README.md").read_text(encoding="utf-8")

    assert (
        "--template https://github.com/microsoft/agent-framework/blob/main/"
        "python/samples/04-hosting/foundry-hosted-agents/responses/foundry_toolbox/azure.yaml --src ."
    ) in readme
    assert readme.index("Create a fine-grained personal access token") < readme.index("azd ai agent init --template")
    assert "--model-deployment <existing-deployment-name>" in readme
    assert "https://github.com/Azure/azure-dev/issues/10519" in readme
    assert "azd deploy --all" in readme
    for target in re.findall(r"\]\(([^)]+)\)", readme):
        if not target.startswith(("https://", "http://", "#")):
            assert (SAMPLE_ROOT / target.split("#", 1)[0]).exists(), target


def test_legacy_definitions_are_retired_and_local_secrets_excluded() -> None:
    for filename in ("agent.manifest.yaml", "agent.yaml", "toolbox.yaml"):
        assert not (SAMPLE_ROOT / filename).exists()
    for filename in (".azdignore", ".dockerignore"):
        patterns = (SAMPLE_ROOT / filename).read_text(encoding="utf-8").splitlines()
        assert ".env" in patterns
        assert ".azure" in patterns
