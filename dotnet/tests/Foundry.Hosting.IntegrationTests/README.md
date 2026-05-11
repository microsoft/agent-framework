# Foundry.Hosting.IntegrationTests

Integration tests for `Microsoft.Agents.AI.Foundry.Hosting` against real Foundry hosted agents.

## How it works

Each test class is bound to a scenario fixture (e.g. `HappyPathHostedAgentFixture`,
`ToolCallingHostedAgentFixture`). On `InitializeAsync` the fixture:

1. Reads `AZURE_AI_PROJECT_ENDPOINT` and `IT_HOSTED_AGENT_IMAGE` from the environment.
2. Targets a stable, scenario keyed agent name (e.g. `it-happy-path`). The agent is
   provisioned out of band by `scripts/it-bootstrap-agents.ps1`; tests only manage versions.
3. Calls `AgentAdministrationClient.CreateAgentVersionAsync` with a `HostedAgentDefinition`
   that points at the image, sets `IT_SCENARIO=<scenario>` in the container env vars, and
   adds a per-run `IT_RUN_ID` so each run gets a fresh content-addressed version (Foundry
   deduplicates versions by definition hash).
4. Polls until the agent reports `AgentVersionStatus.Active` (timeout: 5 minutes).
5. Patches the agent endpoint with `AgentEndpointConfig` (Responses protocol, version
   selector pointing 100% at the new version).
6. Builds a per-agent `ProjectOpenAIClient` with `AgentName` set on the options (this
   selects the `/agents/{name}/endpoint/protocols/openai` URL suffix; the cached
   `projectClient.ProjectOpenAIClient` cannot serve a hosted agent), wraps the
   `ProjectResponsesClient` as an `AIAgent`, and exposes it via `Agent`.

On `DisposeAsync` only the version created by this fixture is deleted. The agent itself
is intentionally never deleted, because its managed identity must hold the pre-granted
`Azure AI User` role on the project scope for inbound inference to succeed.

The container image is **the same for every scenario**. The `IT_SCENARIO` env var, set on
the agent definition by each fixture, drives a `switch` in the test container's
`Program.cs` to wire up the scenario specific behavior (tools, toolbox, custom storage,
etc.).

## Required environment variables

| Variable | Source | Purpose |
| --- | --- | --- |
| `AZURE_AI_PROJECT_ENDPOINT` | Foundry project | Where to provision the agent. Must be in a region that has the Hosted Agents preview enabled (e.g. East US 2). |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Foundry project | Model the agent uses. Defaults to `gpt-4o` inside the container. |
| `IT_HOSTED_AGENT_IMAGE` | `scripts/it-build-image.ps1` | ACR image reference the agent points at. |

## One-time bootstrap (per Foundry project)

Hosted agent invocation requires the agent's own managed identity to hold the
`Azure AI User` role on the project scope. Because each agent's MI is created when the
agent is first provisioned (and recycled on agent delete), the bootstrap creates the
six stable scenario agents once and grants the role to each MI. The fixture then only
manages versions under those existing agents, so the role grants survive across runs.

```powershell
./scripts/it-bootstrap-agents.ps1 `
    -ProjectEndpoint "https://<account>.services.ai.azure.com/api/projects/<project>" `
    -Image "<acr>.azurecr.io/foundry-hosting-it:<tag>"
```

The script is idempotent. It requires Owner or User Access Administrator on the project
scope (RBAC writes). Wait ~3 minutes after first-time grants for AAD propagation before
running the tests.

## Building and pushing the test container image

The test container source lives at `dotnet/tests/Foundry.Hosting.IntegrationTests.TestContainer`.
Build and push it with:

```powershell
$env:IT_REGISTRY = "<your-acr>.azurecr.io"
$env:IT_HOSTED_AGENT_IMAGE = (./scripts/it-build-image.ps1 -Registry $env:IT_REGISTRY | Select-String IT_HOSTED_AGENT_IMAGE).Line.Split('=', 2)[1]
```

The script tags the image by content hash of the test container source. If you didn't
change anything since the last build, the push is a no op.

The Foundry project's account MI and project MI both need `AcrPull` on the registry.

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

All test classes carry `[Trait("Category", "FoundryHostedAgents")]` so the CI workflow can
route them to a separate Foundry project than the rest of the integration tests (see
`.github/workflows/dotnet-build-and-test.yml`).

## CI wiring

The main "Run Integration Tests" step excludes this category. Two extra steps run only on
`ubuntu-latest` for this category, gated on `paths-filter.outputs.foundryHostingChanges`
so they execute only when the project under test, its dependency chain, the test
container, the test fixture, or their tooling changed:

1. **Build and push Foundry Hosted Agents test container** invokes
   `scripts/it-build-image.ps1` against `vars.IT_HOSTED_AGENT_REGISTRY`. The image is
   rebuilt every IT run; its tag is content-hashed across the test container source AND
   its referenced framework projects (`Microsoft.Agents.AI.Foundry.Hosting`,
   `Microsoft.Agents.AI.Foundry`, `Microsoft.Agents.AI`, `Microsoft.Agents.AI.Abstractions`),
   so unchanged content is a `docker push` no-op while any framework code change forces
   a fresh image. The script pipes its `IT_HOSTED_AGENT_IMAGE=<tag>` line into
   `$GITHUB_ENV` for the next step.

2. **Run Foundry Hosted Agents Integration Tests** executes only `--filter-trait
   "Category=FoundryHostedAgents"` with the env vars below mapped onto the names the
   fixture reads. `IT_HOSTED_AGENT_IMAGE` is the value just exported by step 1.

| GitHub env var | Mapped to |
| --- | --- |
| `IT_HOSTED_AGENT_PROJECT_ENDPOINT` | `AZURE_AI_PROJECT_ENDPOINT` |
| `IT_HOSTED_AGENT_MODEL_DEPLOYMENT_NAME` | `AZURE_AI_MODEL_DEPLOYMENT_NAME` |
| `IT_HOSTED_AGENT_REGISTRY` | (consumed by `it-build-image.ps1`; not passed to tests) |

Like all integration tests in this workflow, the steps run only on `push` and merge-queue
events, never on plain `pull_request`. The path-filter list lives in the `paths-filter`
job in `.github/workflows/dotnet-build-and-test.yml` under `filters.foundryHosting` and
must stay in sync with `$hashedDirs` in `scripts/it-build-image.ps1`.

The CI service principal that backs `secrets.AZURE_CLIENT_ID` needs:
- `Azure AI User` on the hosted-agents Foundry project (to add/delete agent versions).
- `AcrPush` on the registry referenced by `IT_HOSTED_AGENT_REGISTRY` (to push the image).

The bootstrap script (and one-time `AcrPull` grants for the Foundry project's MIs) is a
human-only operation; CI only adds and deletes versions under existing agents.

## Scenarios

| Fixture | `IT_SCENARIO` | Agent name | What it tests |
| --- | --- | --- | --- |
| `HappyPathHostedAgentFixture` | `happy-path` | `it-happy-path` | Round trip, streaming, multi turn (`previous_response_id` and `conversation_id`), `stored=false` flag in three combinations, instructions obeyed. |
| `ToolCallingHostedAgentFixture` | `tool-calling` | `it-tool-calling` | Server side AIFunction invocation; arguments; multi turn referencing prior tool result. |
| `ToolCallingApprovalHostedAgentFixture` | `tool-calling-approval` | `it-tool-calling-approval` | Approval requests raised, approved, denied. |
| `ToolboxHostedAgentFixture` | `toolbox` | `it-toolbox` | Server registered toolbox tool callable; client side additions visible (placeholder). |
| `McpToolboxHostedAgentFixture` | `mcp-toolbox` | `it-mcp-toolbox` | MCP backed tool invocation against `https://learn.microsoft.com/api/mcp` (placeholder). |
| `CustomStorageHostedAgentFixture` | `custom-storage` | `it-custom-storage` | Round trip with custom `IResponsesStorageProvider`; multi turn reads from the custom store (placeholder). |
| `SessionFilesHostedAgentFixture` | `session-files` | `it-session-files` | End-to-end: upload via `AgentSessionFiles` (alpha) into a pinned `agent_session_id`, invoke the agent, assert it reads the file via the container's `ReadFile` tool. |

The placeholder scenarios will be wired up in the test container `Program.cs` once the
relevant `Microsoft.Agents.AI.Foundry.Hosting` API surfaces stabilize.

