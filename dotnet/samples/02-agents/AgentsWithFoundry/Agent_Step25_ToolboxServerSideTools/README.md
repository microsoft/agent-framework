# Agent_Step25_ToolboxServerSideTools

This sample demonstrates loading a named Foundry toolbox and passing its tools as
**server-side tools** when creating an agent via `AsAIAgent()`.

When tools from a toolbox are passed this way, they are sent as tool definitions in
the Responses API request. The Foundry platform handles tool execution — the agent
process does not invoke tools locally.

This is the dotnet equivalent of the Python sample:
`python/samples/02-agents/providers/foundry/foundry_chat_client_with_toolbox.py`

## Prerequisites

- A Microsoft Foundry project
- `AZURE_AI_PROJECT_ENDPOINT` environment variable set to your Foundry project endpoint
- `AZURE_AI_MODEL_DEPLOYMENT_NAME` environment variable set (defaults to `gpt-5.4-mini`)

The sample recreates the toolbox on each run, replacing any existing toolbox with
the same name. Comment out the `CreateSampleToolboxAsync` call if you want to keep
an existing toolbox unchanged.

## How it works

1. `projectClient.GetToolboxVersionAsync(name)` fetches the toolbox definition from the
   Foundry project API (resolving the default version if none is specified)
2. `ToolboxVersion.ToAITools()` converts each tool definition to an `AITool` instance
3. The tools are passed to `AsAIAgent(tools: ...)` which includes them in the Responses
   API request as server-side tool definitions

For a one-liner, use `projectClient.GetToolboxToolsAsync(name)` to fetch and convert in one call.

## Sample flows

| Flow | Description |
|------|-------------|
| `Main` (default) | Loads a single toolbox and runs an agent with its tools |
| `CombineToolboxes` | Loads two toolboxes and merges their tools into one agent |

Uncomment the desired flow in the top-level statements to try each one.

## Running the sample

```bash
dotnet run
```
