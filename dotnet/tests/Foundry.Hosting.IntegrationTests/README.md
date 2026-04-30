# Foundry.Hosting.IntegrationTests

Integration tests for `Microsoft.Agents.AI.Foundry.Hosting` against real Foundry hosted agents.

## How it works

Each test class is bound to a scenario fixture (e.g. `HappyPathHostedAgentFixture`,
`ToolCallingHostedAgentFixture`). On `InitializeAsync` the fixture:

1. Reads `AZURE_AI_PROJECT_ENDPOINT` and `IT_HOSTED_AGENT_IMAGE` from the environment.
2. Calls `AgentAdministrationClient.CreateAgentVersionAsync` with a `HostedAgentDefinition`
   that points at the image and sets `IT_SCENARIO=<scenario>` in the container env vars.
3. Polls until the agent reports `AgentVersionStatus.Active` (timeout: 5 minutes).
4. Wraps the agent via `AIProjectClient.AsAIAgent(record)` for the test code.

On `DisposeAsync` the fixture deletes the agent version. Failures during cleanup are
swallowed because they would mask the real test failure; orphan agents can be reaped by a
separate maintenance script.

The container image is **the same for every scenario**. The `IT_SCENARIO` env var, set on
the agent definition by each fixture, drives a `switch` in the test container's
`Program.cs` to wire up the scenario specific behavior (tools, toolbox, custom storage,
etc.).

## Required environment variables

| Variable | Source | Purpose |
| --- | --- | --- |
| `AZURE_AI_PROJECT_ENDPOINT` | Foundry project | Where to provision the agent. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Foundry project | Model the agent uses. Defaults to `gpt-4o` inside the container. |
| `IT_HOSTED_AGENT_IMAGE` | `scripts/it-build-image.ps1` | ACR image reference the agent points at. |

## Building and pushing the test container image

The test container source lives at `dotnet/tests/Foundry.Hosting.IntegrationTests.TestContainer`.
Build and push it with:

```powershell
$env:IT_REGISTRY = "<your-acr>.azurecr.io"
$env:IT_HOSTED_AGENT_IMAGE = (./scripts/it-build-image.ps1 -Registry $env:IT_REGISTRY | Select-String IT_HOSTED_AGENT_IMAGE).Line.Split('=', 2)[1]
```

The script tags the image by content hash of the test container source. If you didn't
change anything since the last build, the push is a no op.

## Running the tests locally

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT = "https://<your-account>.services.ai.azure.com/api/projects/<your-project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME = "gpt-4o"
# IT_HOSTED_AGENT_IMAGE was set above.

dotnet test dotnet/tests/Foundry.Hosting.IntegrationTests/Foundry.Hosting.IntegrationTests.csproj
```

> **Note:** all tests are currently tagged `[Fact(Skip = ...)]` until end to end smoke
> verification has run against a live Foundry deployment. Once a scenario has been
> exercised and the assertions stabilized, remove the Skip annotation on its tests.

## Scenarios

| Fixture | `IT_SCENARIO` | What it tests |
| --- | --- | --- |
| `HappyPathHostedAgentFixture` | `happy-path` | Round trip, streaming, multi turn (`previous_response_id` and `conversation_id`), `stored=false` flag in three combinations, instructions obeyed. |
| `ToolCallingHostedAgentFixture` | `tool-calling` | Server side AIFunction invocation; arguments; multi turn referencing prior tool result. |
| `ToolCallingApprovalHostedAgentFixture` | `tool-calling-approval` | Approval requests raised, approved, denied. |
| `ToolboxHostedAgentFixture` | `toolbox` | Server registered toolbox tool callable; client side additions visible (placeholder). |
| `McpToolboxHostedAgentFixture` | `mcp-toolbox` | MCP backed tool invocation against `https://learn.microsoft.com/api/mcp` (placeholder). |
| `CustomStorageHostedAgentFixture` | `custom-storage` | Round trip with custom `IResponsesStorageProvider`; multi turn reads from the custom store (placeholder). |

The placeholder scenarios will be wired up in the test container `Program.cs` once the
relevant `Microsoft.Agents.AI.Foundry.Hosting` API surfaces stabilize.
