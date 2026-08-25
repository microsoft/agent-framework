# Hosted-Workflow-Resilient

A sequential translation workflow hosted with resilient background Responses enabled. AgentServer
re-invokes an interrupted background response, Foundry Hosting reloads the AgentSession, and the
workflow runtime continues from the checkpoint referenced by that session.

This sample deploys directly from source. Foundry uploads the project as a ZIP, restores its
packages, builds it, and runs `HostedWorkflowResilient.dll`. No Dockerfile or container registry is
needed.

## Key setting

```csharp
builder.Services.AddFoundryResponses(
    agent,
    configure: options => options.ResilientBackground = true);
```

Each workflow agent has a fixed `Id` and `Name`. A restarted process must reconstruct the same
executor identities for a stored workflow checkpoint to match.

## State ownership

| State | Owner |
| --- | --- |
| Background task, response events, and selected response snapshots | AgentServer |
| AgentSession and workflow checkpoint reference | `FoundryAgentSessionStore` |
| Workflow execution checkpoints | `FoundryJsonCheckpointStore` |

At each completed workflow superstep, the hosting adapter saves the AgentSession, records the
workflow checkpoint ID in AgentServer internal response metadata, and calls
`ResponseEventStream.Checkpoint()`. Recovery selects that exact workflow checkpoint ID. The response
output count is not used as the workflow cursor.

## Local development

Copy `.env.example` to `.env`, set the project endpoint and model deployment, then run:

```powershell
az login
dotnet run --tl:off
```

The in-repository project automatically uses ProjectReference to run the current framework source.

## Deploy from source

Create an empty working directory outside the repository:

```powershell
$work = Join-Path $env:TEMP "hosted-workflow-resilient-work"
New-Item -ItemType Directory -Path $work -Force | Out-Null
Set-Location $work

$sample = "<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Workflow-Resilient/azure.yaml"
azd auth login
azd ai agent init -m $sample -d <model-deployment>
```

### Contributors testing framework changes

**Skip this section unless you are testing an Agent Framework change from the current codebase that
has not been released yet.** The normal deployment uses the published packages. To test local
framework changes, pack the current repository source into the scaffolded upload before provisioning:

```powershell
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/Add-LocalFrameworkFeed.ps1 `
    -Path ./hosted-workflow-resilient
```

The helper creates `local-feed/`, writes `nuget.config`, and changes `AgentFrameworkVersion` in the
scaffolded project. Both generated artifacts are included in the source ZIP.

```powershell
Set-Location hosted-workflow-resilient
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME <model-deployment>
azd provision
azd deploy
```

The workflow checkpoint store writes through the hosted agent's managed identity. Grant that
identity `Foundry User` on the existing Foundry project after the first deployment:

```powershell
$agent = azd ai agent show hosted-workflow-resilient -o json | ConvertFrom-Json
az role assignment create `
    --assignee-object-id $agent.instance_identity.principal_id `
    --assignee-principal-type ServicePrincipal `
    --role "Foundry User" `
    --scope <foundry-project-resource-id>
```

Allow a few minutes for the role assignment to take effect before the first request.

Submit the request with `store=true` and `background=true`. Poll the returned response id until it
reaches a terminal status.

## Live integration coverage

`Foundry.Hosting.IntegrationTests` contains a deterministic `resilient-workflow` scenario:

- `long:<token>` holds a background workflow without client traffic, then completes with the token.
- `crash:<token>` writes a crash-once marker, terminates the container process, and completes only
  after AgentServer reclaims the response and the workflow resumes in a replacement process.

The test suite deploys that scenario to a real Foundry project and validates both behaviors.

## Related samples

- [Hosted-Workflow-Resilient-Long-Running](../Hosted-Workflow-Resilient-Long-Running/README.md): deterministic countdown recovery with exact output validation.
- [Hosted-Workflow-Simple](../Hosted-Workflow-Simple/README.md): workflow hosting without resilient background execution.
- [Hosted-Steering](../Hosted-Steering/README.md): mid-turn steering.
