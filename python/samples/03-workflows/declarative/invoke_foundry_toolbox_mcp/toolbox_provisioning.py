# Copyright (c) Microsoft. All rights reserved.

"""Foundry toolbox provisioning helper for ``invoke_foundry_toolbox_mcp``.

Toolboxes are normally created through the Foundry portal or a separate
deployment script. Bundling the one-off setup here lets the sample run
end-to-end without manual steps. ``main.py`` owns the workflow
execution path.
"""

from collections.abc import Mapping

from azure.identity import AzureCliCredential

# Toolbox admin and MCP runtime traffic are both gated by a preview
# feature flag. The Python ``AIProjectClient`` does not add it
# automatically, so we attach it to every admin call here AND to the
# ``httpx.AsyncClient`` in ``main.py`` so the MCP ``initialize``
# handshake carries it too. Without the flag on admin calls,
# provisioning succeeds at the HTTP layer but the toolbox is never
# wired to the MCP endpoint — surfacing later as "MCP server failed to
# initialize: Session terminated" on the first ``InvokeMcpTool`` call.
FOUNDRY_FEATURES_HEADERS: Mapping[str, str] = {"Foundry-Features": "Toolboxes=V1Preview"}


def create_sample_toolbox(*, name: str, docs_server_label: str, project_endpoint: str) -> None:
    """Provision a toolbox version (delete-then-create; idempotent).

    Bundles the Microsoft Learn Docs MCP server under ``docs_server_label``.
    Uses ``AzureCliCredential`` because the sample expects ``az login``;
    switch to a managed identity or service principal for production
    deployments.
    """
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPTool, Tool
    from azure.core.exceptions import ResourceNotFoundError

    with (
        AzureCliCredential() as credential,
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
                server_url="https://learn.microsoft.com/api/mcp",
                require_approval="never",
            ),
        ]

        created = project_client.beta.toolboxes.create_version(
            name=name,
            description="Sample toolbox exposing the Microsoft Learn Docs MCP server.",
            tools=tools,
            headers=FOUNDRY_FEATURES_HEADERS,
        )
        print(f"Created toolbox {created.name}@{created.version} ({len(created.tools)} tool(s)).")
