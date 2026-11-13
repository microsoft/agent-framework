# Hosted-Workflow-Handoff

A hosted triage handoff workflow: a triage agent routes each request to a specialist agent (a code expert or a creative writer) and hands control back when done. The sample also wires client-side and server-side MCP tools, and it uses a model deployment from its Foundry project. It is served over the Responses protocol.

This sample deploys to Foundry **directly from source (code / ZIP upload)**: the platform builds and runs your code with no container image. Source deploy is the default for .NET.

The sample uses `AIProjectClient` so project endpoint selection, authentication, and the
`https://ai.azure.com/.default` token audience remain owned by the Foundry SDK. See
[Microsoft Foundry model endpoint authentication](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/endpoints#use-keyless-authentication).

The project temporarily pins `Microsoft.Extensions.AI.OpenAI` 10.11.0 because the published
Agent Framework 1.27 packages resolve 10.10.1, which returns HTTP 401 for project-model calls made
by the hosted agent identity. Remove the pin after the next Agent Framework release carries 10.11
or later transitively.

## Files

| File | Purpose |
|------|---------|
| `Program.cs` | Builds the triage + specialist agents and the handoff workflow, wires MCP tools, hosts it with the Responses protocol and serves demo pages. |
| `Pages.cs` | Static HTML demo pages. |
| `ResponseStreamValidator.cs` | Validates captured SSE streams for the demo. |
| `azure.yaml` | The unified `azd` project file: `codeConfiguration` (source/ZIP deploy), listen port, and selected Foundry project model. |
| `.agentignore` | Controls which files are excluded from the code-deploy ZIP upload (`.gitignore` syntax). |
| `HostedWorkflowHandoff.csproj` | Self-contained project: single target framework, explicit package versions, opts out of the repo's central package management. |
| `.env.example` | Template for local configuration. |
| `../../scripts/Add-LocalFrameworkFeed.ps1`, `../../scripts/add-local-framework-feed.sh` | Contributor-only helpers. |

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An **existing** Foundry project with a deployed model.
- Azure CLI logged in (`az login`)
- Azure Developer CLI (`azd`) with the AI agents extension: `azd extension install azure.ai.agents`

## Configuration

Copy the template and fill it in:

```env
FOUNDRY_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
FOUNDRY_MODEL=gpt-4o
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

```powershell
$sample = "<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Workflow-Handoff/azure.yaml"

azd auth login
azd ai agent init -m $sample -d <model-deployment>

cd hosted-workflow-handoff
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME <model-deployment>
azd provision
azd deploy
```

The source deployment creates a managed identity for the hosted agent, but it does not currently
grant that identity access to the project model. After the first deploy, grant **`Foundry User`**
at the Foundry project scope, not on a separate Azure OpenAI account:

```bash
PRINCIPAL=$(az rest --method get \
  --url "<project-endpoint>/agents/hosted-workflow-handoff" \
  --url-parameters api-version=v1 \
  --resource https://ai.azure.com \
  --query "versions.latest.instance_identity.principal_id" \
  --output tsv)

az role assignment create \
  --assignee-object-id "$PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
```

Role assignments can take a few minutes to propagate. Wait before the first
`azd ai agent invoke` call.

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

## Deploy your local framework changes (contributors)

**Skip this unless you are changing the Agent Framework itself.** Run the helper between
`azd ai agent init` and `azd provision` to ship a local framework build inside the upload:

```powershell
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/Add-LocalFrameworkFeed.ps1 -Path ./hosted-workflow-handoff
```

See the [`Hosted-ChatClientAgent`](../Hosted-ChatClientAgent/README.md#deploy-your-local-framework-changes-contributors) README for the full explanation.

For the full hosted-agent deployment guide, see the [official source-code deployment doc](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code).
