# Hosted-Workflow-Handoff

A hosted triage handoff workflow: a triage agent routes each request to a specialist agent (a code expert or a creative writer) and hands control back when done. The sample also wires client-side and server-side MCP tools, and it is backed by an Azure OpenAI resource. It is served over the Responses protocol.

This sample deploys to Foundry **directly from source (code / ZIP upload)**: the platform builds and runs your code with no container image. Source deploy is the default for .NET.

> **Requires an Azure OpenAI resource.** Unlike the other samples (which use the Foundry project's
> model deployment), this one reads `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT` and talks
> to Azure OpenAI directly. Set both to a resource your identity can call before running or
> deploying.

> **The deployed agent needs its own role on that Azure OpenAI resource.** Because the workflow
> builds its own `AzureOpenAIClient` (a data-plane client) instead of using the Foundry project's
> hosted model, `azd deploy` does **not** grant it access automatically. `azd` only grants the agent
> identity the `Foundry User` role on the project; it does not touch a separate Azure OpenAI account.
> After the first deploy, grant the agent's managed identity the **`Cognitive Services OpenAI User`**
> role on the `AZURE_OPENAI_ENDPOINT` account, or the first model call fails with
> `server_error: An error occurred while executing the workflow.` at the triage step. See
> [Grant the agent access to Azure OpenAI](#grant-the-agent-access-to-azure-openai) below.

## Files

| File | Purpose |
|------|---------|
| `Program.cs` | Builds the triage + specialist agents and the handoff workflow, wires MCP tools, hosts it with the Responses protocol and serves demo pages. |
| `Pages.cs` | Static HTML demo pages. |
| `ResponseStreamValidator.cs` | Validates captured SSE streams for the demo. |
| `azure.yaml` | The unified `azd` project file: `codeConfiguration` (source/ZIP deploy) plus the listen port and the Azure OpenAI settings passed through `env`. |
| `.agentignore` | Controls which files are excluded from the code-deploy ZIP upload (`.gitignore` syntax). |
| `HostedWorkflowHandoff.csproj` | Self-contained project: single target framework, explicit package versions, opts out of the repo's central package management. |
| `.env.example` | Template for local configuration. |
| `../../scripts/Add-LocalFrameworkFeed.ps1`, `../../scripts/add-local-framework-feed.sh` | Contributor-only helpers. |

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An **existing** Foundry project.
- An **Azure OpenAI** resource with a deployed model (for `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT`).
- Azure CLI logged in (`az login`)
- Azure Developer CLI (`azd`) with the AI agents extension: `azd extension install azure.ai.agents`

## Configuration

Copy the template and fill it in:

```env
AZURE_OPENAI_ENDPOINT=https://<your-openai>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
ASPNETCORE_URLS=http://+:8088
AZURE_TOKEN_CREDENTIALS=dev
```

> `.env` is gitignored. Write it as UTF-8 **without** a byte order mark, or `azd ai agent init` fails.
> `AZURE_TOKEN_CREDENTIALS=dev` restricts `DefaultAzureCredential` to developer credentials on a
> machine with no managed identity. Both are local-development only.

## Run and test locally

```
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Workflow-Handoff
az login
dotnet run
```

The agent starts on `http://localhost:8088` and also serves demo pages at `/`, `/tool-demo` and `/workflow-demo`.

## Deploy to Foundry (source / ZIP)

`azd` scaffolds the project into a working folder outside the repository; `-m` points at this sample's `azure.yaml`.

```powershell
$work = Join-Path $env:TEMP "hosted-workflow-handoff-work"
mkdir $work; cd $work

$sample = "<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Workflow-Handoff/azure.yaml"
azd auth login
azd ai agent init -m $sample

cd hosted-workflow-handoff

# Provide the Azure OpenAI settings to the azd environment before deploying:
azd env set AZURE_OPENAI_ENDPOINT https://<your-openai>.openai.azure.com/
azd env set AZURE_OPENAI_DEPLOYMENT gpt-4o

azd provision
azd deploy
```

`azd` packages the source into a ZIP (honoring `.agentignore`), uploads it, and Foundry runs
`dotnet restore` + `dotnet publish` on it during provisioning (`dependencyResolution: remote_build`).
No Dockerfile, no container registry. Clean up with `azd down`.

> **`azd down` does not delete the hosted agent.** It reports success but leaves the deployed agent
> in place. Delete it explicitly with a REST call:
>
> ```bash
> az rest --method delete \
>   --url "<project-endpoint>/agents/hosted-workflow-handoff" \
>   --url-parameters api-version=v1 force=true \
>   --resource https://ai.azure.com
> ```

## Grant the agent access to Azure OpenAI

The deployed agent runs under a managed identity that Foundry creates. Because this sample calls
Azure OpenAI directly (a data-plane call), that identity needs the `Cognitive Services OpenAI User`
role on the Azure OpenAI account, and `azd` does not grant it. Do this once, after the first
`azd deploy`, and before `azd ai agent invoke`:

```bash
# 1. Read the agent's managed-identity principal id from the deployed version.
PRINCIPAL=$(az rest --method get \
  --url "<project-endpoint>/agents/hosted-workflow-handoff" \
  --url-parameters api-version=v1 \
  --resource https://ai.azure.com \
  --query "versions.latest.instance_identity.principal_id" \
  --output tsv)

# 2. Grant it the data-plane role on the Azure OpenAI account behind AZURE_OPENAI_ENDPOINT.
az role assignment create \
  --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<openai-account>"
```

Role assignments take up to a few minutes to propagate. Wait, then
`azd ai agent invoke --new-conversation "Write a haiku about the sea."`. Until the role is in place,
the workflow starts (`HandoffStart` runs) but fails at the triage agent's first model call with
`server_error: An error occurred while executing the workflow.`

> Creating the role assignment needs `Microsoft.Authorization/roleAssignments/write` on that
> account (for example `Owner` or `User Access Administrator`). If you lack it, ask a resource owner
> to grant the agent's principal id the `Cognitive Services OpenAI User` role.

## Deploy your local framework changes (contributors)

**Skip this unless you are changing the Agent Framework itself.** Run the helper between
`azd ai agent init` and `azd provision` to ship a local framework build inside the upload:

```powershell
cd $work
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/Add-LocalFrameworkFeed.ps1 -Path ./hosted-workflow-handoff
```

See the [`Hosted-ChatClientAgent`](../Hosted-ChatClientAgent/README.md#deploy-your-local-framework-changes-contributors) README for the full explanation.

For the full hosted-agent deployment guide, see the [official source-code deployment doc](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code).
