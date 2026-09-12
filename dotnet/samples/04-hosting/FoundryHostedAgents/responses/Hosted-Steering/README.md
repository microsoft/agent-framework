# Hosted-Steering

A Foundry Hosted Agent with steerable conversations enabled. When a second input arrives while a
conversation turn is running, AgentServer queues it instead of returning `conversation_locked`.

This sample deploys directly from source. Foundry uploads the project as a ZIP, restores its
packages, builds it, and runs `HostedSteering.dll`. No Dockerfile or container registry is needed.

## Key setting

```csharp
builder.Services.AddFoundryResponses(
    agent,
    configure: options => options.SteerableConversations = true);
```

Steering and resilient background execution are separate options. This sample enables only
steering. See [Hosted-Workflow-Resilient](../Hosted-Workflow-Resilient/README.md) for crash recovery.

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
$work = Join-Path $env:TEMP "hosted-steering-work"
New-Item -ItemType Directory -Path $work -Force | Out-Null
Set-Location $work

$sample = "<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Steering/azure.yaml"
azd auth login
azd ai agent init -m $sample -d <model-deployment>
```

### Contributors testing framework changes

**Skip this section unless you are testing an Agent Framework change from the current codebase that
has not been released yet.** The normal deployment uses the published packages. To test local
framework changes, pack the current repository source into the scaffolded upload before provisioning:

```powershell
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/Add-LocalFrameworkFeed.ps1 `
    -Path ./hosted-steering
```

The helper creates `local-feed/`, writes `nuget.config`, and changes `AgentFrameworkVersion` in the
scaffolded project. Both generated artifacts are included in the source ZIP.

```powershell
Set-Location hosted-steering
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME <model-deployment>
azd provision
azd deploy
```

## Exercise steering

Start a stored background response, keep its response or conversation identity, then submit a second
input to the same in-progress conversation. The second request should be queued instead of rejected.
Use the Responses API or an OpenAI-compatible client that exposes background and conversation fields.

## Related samples

- [Hosted-ChatClientAgent](../Hosted-ChatClientAgent/README.md): basic source-deployed agent.
- [Hosted-Workflow-Resilient](../Hosted-Workflow-Resilient/README.md): resilient background workflow.
- [Hosted-Workflow-Resilient-Long-Running](../Hosted-Workflow-Resilient-Long-Running/README.md): deterministic countdown recovery with exact output validation.
