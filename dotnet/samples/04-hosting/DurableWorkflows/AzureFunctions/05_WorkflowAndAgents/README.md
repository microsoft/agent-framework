# Workflow and Agents Sample

This sample demonstrates how to use `ConfigureDurableOptions` to register **both** AI agents **and** workflows in a single Azure Functions app. This is the recommended approach when your application needs both standalone agents and orchestrated workflows.

## Key Concepts Demonstrated

- **Unified Configuration**: Use `ConfigureDurableOptions` to register agents and workflows together
- **Standalone Agent**: An AI agent accessible via HTTP and MCP tool triggers
- **Workflow**: A simple text translation workflow also exposed as an MCP tool
- **Mixed Triggers**: Both agents and workflows coexist in the same Functions host

## Sample Architecture

### Standalone Agent

| Agent | Description |
|-------|-------------|
| **Assistant** | A general-purpose AI assistant accessible via HTTP (`/agents/Assistant/run`) and as an MCP tool |

### Translate Workflow

| Executor | Input | Output | Description |
|----------|-------|--------|-------------|
| **TranslateText** | `string` | `TranslationResult` | Converts input text to uppercase |
| **FormatOutput** | `TranslationResult` | `string` | Formats the result into a readable string |

## Environment Setup

See the [README.md](../../README.md) file in the parent directory for complete setup instructions, including:

- Prerequisites installation
- Durable Task Scheduler setup
- Storage emulator configuration

This sample also requires Azure OpenAI credentials. Set the following in `local.settings.json`:

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint URL
- `AZURE_OPENAI_DEPLOYMENT_NAME`: Your chat model deployment name
- `AZURE_OPENAI_API_KEY` (optional): If not set, Azure CLI credential is used

## Running the Sample

1. **Start the Function App**:

   ```bash
   cd dotnet/samples/04-hosting/DurableWorkflows/AzureFunctions/05_WorkflowAndAgents
   func start
   ```

2. **Expected Functions**: When the app starts, you should see functions for both the agent and the workflow:

   - `dafx-Assistant` (entity trigger for the agent)
   - `http-Assistant` (HTTP trigger for the agent)
   - `mcptool-Assistant` (MCP tool trigger for the agent)
   - `wf-Translate` (orchestration trigger for the workflow)
   - `mcptool-wf-Translate` (MCP tool trigger for the workflow)

## Invoking the Agent via HTTP

```bash
curl -X POST http://localhost:7071/agents/Assistant/run \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the capital of France?"}'
```

## Invoking via MCP Inspector

1. Install and run the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector):

   ```bash
   npx @modelcontextprotocol/inspector
   ```

2. Connect to `http://localhost:7071/runtime/webhooks/mcp` using **Streamable HTTP** transport.

3. Click **List Tools** to see both the `Assistant` agent tool and the `Translate` workflow tool.
