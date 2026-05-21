# Copyright (c) Microsoft. All rights reserved.

"""Foundry toolbox provisioning helper for the ``invoke_foundry_toolbox_mcp`` sample.

This module is intentionally narrow: it covers the one-off **administrative**
setup needed to (re)create a Foundry toolbox so the sample can be run
end-to-end without manual portal/CLI steps. Workflow execution, MCP
handling, and agent orchestration live in :mod:`main`.

Toolboxes are normally provisioned through the Foundry portal or a separate
deployment script. Bundling the provisioning step here keeps the sample
self-contained and re-runnable.

The Foundry-Features preview header is exported here as well so the
runtime MCP client in ``main.py`` can attach it on every outbound request
(the MCP ``initialize`` handshake also requires the flag, not just the
toolbox administration calls).
"""

from collections.abc import Mapping

from azure.identity import AzureCliCredential

DEFAULT_DOCS_MCP_SERVER_URL = "https://learn.microsoft.com/api/mcp"

# Bump the ``az.cmd`` subprocess timeout from the default 10s. On Windows
# the Azure CLI batch wrapper can take noticeably longer than 10s to
# return a token (cold-start + ``az`` self-update checks + AAD round-trip),
# which surfaces as ``CredentialUnavailableError: Failed to invoke the
# Azure CLI`` after a ``subprocess.TimeoutExpired`` from the credential's
# internal call.
AZ_CLI_PROCESS_TIMEOUT_SECONDS = 60

# Toolbox administration AND runtime MCP traffic are both gated by an
# Azure AI Foundry preview feature flag. The .NET sample injects this
# header via a pipeline policy on the ``AgentAdministrationClient``;
# the Python ``AIProjectClient`` doesn't add it automatically, so we pass
# it as a per-call header on every toolbox admin operation (delete +
# create_version) here, and the runtime code in ``main.py`` attaches it
# as a default header on the ``httpx.AsyncClient`` so it travels on the
# MCP ``initialize`` handshake as well. Without this header on admin
# calls, provisioning succeeds at the HTTP layer but the toolbox is
# never wired up to the MCP endpoint — surfacing at runtime as "MCP
# server failed to initialize: Session terminated" on the first
# ``InvokeMcpTool`` call.
FOUNDRY_FEATURES_HEADER_NAME = "Foundry-Features"
FOUNDRY_FEATURES_HEADER_VALUE = "Toolboxes=V1Preview"
FOUNDRY_FEATURES_HEADERS: Mapping[str, str] = {
    FOUNDRY_FEATURES_HEADER_NAME: FOUNDRY_FEATURES_HEADER_VALUE,
}


def build_toolbox_mcp_server_url(project_endpoint: str, name: str, api_version: str) -> str:
    """Compose the Foundry toolbox MCP proxy URL.

    Toolboxes provisioned via ``AIProjectClient.beta.toolboxes`` live under
    the ``/toolboxes/{name}`` resource path (the Python SDK's
    ``BetaToolboxesOperations`` routes POST/GET/DELETE there — see
    ``azure/ai/projects/operations/_operations.py``). Their MCP proxy URL
    is ``<project_endpoint>/toolboxes/{name}/mcp?api-version=<api_version>``,
    matching the .NET sample.
    """
    base = project_endpoint.rstrip("/")
    return f"{base}/toolboxes/{name}/mcp?api-version={api_version}"


def create_sample_toolbox(
    *,
    name: str,
    docs_server_label: str,
    project_endpoint: str,
    docs_server_url: str = DEFAULT_DOCS_MCP_SERVER_URL,
) -> None:
    """Provision a toolbox version in the Foundry project (idempotent).

    Deletes any existing toolbox under ``name`` and then creates a new
    version that bundles:

    - the Microsoft Learn Docs MCP server
      (``server_label=docs_server_label``), and
    - the Foundry built-in ``web_search`` tool.

    Uses ``AzureCliCredential`` because the sample is meant to be run by
    a developer with ``az login`` already configured; switch to a managed
    identity / service principal credential for production deployments.
    """
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPTool, Tool, WebSearchTool
    from azure.core.exceptions import ResourceNotFoundError

    with (
        AzureCliCredential(process_timeout=AZ_CLI_PROCESS_TIMEOUT_SECONDS) as credential,
        AIProjectClient(credential=credential, endpoint=project_endpoint) as project_client,
    ):
        try:
            project_client.beta.toolboxes.delete(name, headers=FOUNDRY_FEATURES_HEADERS)
            print(f"Toolbox '{name}' deleted (replacing with a fresh version).")
        except ResourceNotFoundError:
            pass

        tools: list[Tool] = [
            MCPTool(
                server_label=docs_server_label,
                server_url=docs_server_url,
                require_approval="never",
            ),
            WebSearchTool(),
        ]

        created = project_client.beta.toolboxes.create_version(
            name=name,
            description="Sample toolbox combining Microsoft Learn Docs MCP and Foundry web search.",
            tools=tools,
            headers=FOUNDRY_FEATURES_HEADERS,
        )
        print(f"Created toolbox {created.name}@{created.version} ({len(created.tools)} tool(s)).")
