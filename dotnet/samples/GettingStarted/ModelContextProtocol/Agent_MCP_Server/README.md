# Model Context Protocol Sample

This example demonstrates how to use tools from a Model Context Protocol server with Agent Framework.

MCP is an open protocol that standardizes how applications provide context to LLMs.

For information on Model Context Protocol (MCP) please refer to the [documentation](https://modelcontextprotocol.io/introduction).

The sample shows:

1. How to connect to an MCP Server
1. Retrieve the list of tools the MCP Server makes available
1. Convert the MCP tools to `AIFunction`'s so they can be added to an agent
1. Invoke the tools from an agent using function calling

## Configuring Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure OpenAI resource endpoint
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Setup and Running

Run the ModelContextProtocolPluginAuth sample

```bash
dotnet run
```
