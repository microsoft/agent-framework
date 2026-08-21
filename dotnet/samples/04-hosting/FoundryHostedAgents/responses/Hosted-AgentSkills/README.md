# Hosted-AgentSkills

A hosted agent that uploads and consumes Foundry Skills (SKILL.md) via the Skills REST API. Set PROVISION_SAMPLE_SKILLS=true to have the sample upload its bundled skills on startup, and SKILL_NAMES to select which to load.

This sample deploys to Foundry **directly from source (code / ZIP upload)**: the platform builds and runs your code with no container image, so there is no Dockerfile to author or container registry to manage. Source deploy is the default for .NET.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An **existing** Foundry project with an **existing** model deployment (for example `gpt-4o`).
  This sample's `azure.yaml` declares no `deployments:` block, so `azd` connects to a project and
  a deployment you already have rather than creating them. `azd ai agent init` prompts you to pick
  the project, and takes the deployment name as the `-d` argument.
- Azure CLI logged in (`az login`)
- Azure Developer CLI (`azd`) with the AI agents extension: `azd extension install azure.ai.agents`
- Permission to assign **Foundry User** on the Foundry project. The agent identity is created by
  the first deploy, so this role is granted after `azd deploy`.

## Files

| File | Purpose |
|------|---------|
| `Program.cs` | The agent: provisions and loads Foundry Skills, hosts it with the Responses protocol. |
| `azure.yaml` | The unified `azd` project file. Declares the Foundry project and the hosted agent with `codeConfiguration` (source/ZIP deploy), and passes the listen port and the model deployment name to the container through env. |
| `.agentignore` | Controls which files are excluded from the code-deploy ZIP upload (`.gitignore` syntax). |
| `HostedAgentSkills.csproj` | Self-contained project: single target framework and explicit package versions. It also opts out of the repository's central package management, which does not travel inside the ZIP. |
| `.env.example` | Template for local configuration. |
| `../../scripts/Add-LocalFrameworkFeed.ps1`, `../../scripts/add-local-framework-feed.sh` | Contributor-only helpers, see [Deploy your local framework changes](#deploy-your-local-framework-changes-contributors). |

## Configuration

Copy the template and fill in your project endpoint:

PowerShell:

```powershell
copy .env.example .env
```

Bash:

```bash
cp .env.example .env
```

```env
FOUNDRY_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
PROVISION_SAMPLE_SKILLS=true
SKILL_NAMES=support-style,escalation-policy
ASPNETCORE_URLS=http://+:8088
AZURE_TOKEN_CREDENTIALS=dev
```

> `.env` is gitignored. The `.env.example` template is checked in as a reference.

> `ASPNETCORE_URLS` pins the local run to the port the `Using-Samples` REPLs expect. Recent
> `Microsoft.Agents.AI.Foundry.Hosting` versions bind that port themselves, so it only matters
> while this project is pinned to an older published package.

> **Windows note:** write `.env` as UTF-8 **without** a byte order mark. `azd` reads the file
> during `azd ai agent init` and fails with `unexpected character` when a mark is present.

> **Local development on a machine without a managed identity:** set `AZURE_TOKEN_CREDENTIALS=dev`.
> `Program.cs` authenticates with `DefaultAzureCredential`. On a developer machine with no
> managed identity, `DefaultAzureCredential` probes the Azure Instance Metadata Service (IMDS,
> `169.254.169.254`) and blocks for a long time before every model call. `AZURE_TOKEN_CREDENTIALS=dev`
> restricts it to developer credentials (Azure CLI, Visual Studio, `azd`) and skips that probe.
> Only for local runs; the deployed agent uses the platform-injected managed identity.

## Run and test locally

Local runs use two terminals: one hosts the agent, the other is a code-first client that talks to it,
see the sibling [`Using-Samples`](../Using-Samples/) REPLs.

**Terminal 1 — host the agent:**

```
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-AgentSkills
az login
dotnet run
```

The agent starts on `http://localhost:8088`.

**Terminal 2 — chat with it (code-first REPL):**

PowerShell:

```powershell
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Using-Samples/SimpleAgent
$env:AZURE_AI_AGENT_NAME = "hosted-agent-skills"
dotnet run -- --local
```

Bash:

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Using-Samples/SimpleAgent
export AZURE_AI_AGENT_NAME="hosted-agent-skills"
dotnet run -- --local
```

Try: `Introduce yourself using your configured skills.`

## Deploy to Foundry (source / ZIP)

`azd` scaffolds the project into a working folder, so every step below runs from an **empty
directory outside the repository**, and `-m` points at this sample's `azure.yaml`.

### Step 1: create the working directory and enter it

PowerShell:

```powershell
$work = Join-Path $env:TEMP "hosted-agent-skills-work"
mkdir $work
cd $work
```

### Step 2: scaffold the project

`azd ai agent init` copies the sample into a subfolder named `hosted-agent-skills` (the top-level `name:`
in `azure.yaml`) and writes the adopted `azure.yaml` and the `azd` environment there. It prompts
you to pick the Foundry project; `-d` is the name of an existing model deployment in that project.

PowerShell:

```powershell
$sample = "<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-AgentSkills/azure.yaml"

azd auth login
azd ai agent init -m $sample -d <model-deployment>
```

### Step 3: provision and deploy

Contributors changing the Agent Framework source: do the extra step in
[Deploy your local framework changes](#deploy-your-local-framework-changes-contributors) now,
before the commands below. Everyone else can ignore it.

```
cd hosted-agent-skills
azd env get-values
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME <model-deployment>
azd env set PROVISION_SAMPLE_SKILLS true
azd env set SKILL_NAMES support-style,escalation-policy
azd provision
azd deploy

# Grant the new hosted-agent identity project data-plane access:
az rest --method get --url "<project-endpoint>/agents/hosted-agent-skills" --url-parameters api-version=v1 --resource https://ai.azure.com --query "versions.latest.instance_identity.principal_id" --output tsv
az role assignment create --assignee-object-id <principal-id-from-previous-command> --assignee-principal-type ServicePrincipal --role 53ca6127-db72-4b80-b1b0-d745d6d5456d --scope <project-resource-id>

# Wait briefly for the role assignment to propagate, then invoke:
azd ai agent invoke "Introduce yourself using your configured skills."
```

`azd` packages the source into a ZIP (honoring `.agentignore`), uploads it, and Foundry runs
`dotnet restore` + `dotnet publish` on it during provisioning (`dependencyResolution: remote_build`
in `azure.yaml`). No Dockerfile, no container registry.

`53ca6127-db72-4b80-b1b0-d745d6d5456d` is the stable role definition ID for **Foundry User**.
Do not substitute `Azure AI Developer`; Microsoft documents that role as insufficient for Foundry
hosted agents. Recreate the role assignment when the agent is deleted and created again, because
the new agent receives a new identity.

The Skills API is a preview surface. `Program.cs` adds the required
`Foundry-Features: Skills=V1Preview` header and downloads skills into the writable temporary
directory. The source-deploy application directory (`/app`) is read-only.

### Step 4: clean up

```
azd down
```

> **`azd down` does not delete the hosted agent.** It reports success but leaves the deployed agent
> in place. Delete it explicitly with a REST call:
>
> ```bash
> az rest --method delete \
>   --url "<project-endpoint>/agents/hosted-agent-skills" \
>   --url-parameters api-version=v1 force=true \
>   --resource https://ai.azure.com
> ```

Then delete the working directory.

## Deploy your local framework changes (contributors)

**Skip this section unless you are changing the Agent Framework itself.** The project restores the
**published** Agent Framework packages, and Foundry restores from nuget.org when it builds the
upload, so editing framework source in this repository changes nothing about the deployed agent.

The helper script packs your local framework source into NuGet packages and puts them **inside the
upload**, together with a `nuget.config` that points the restore at them. Run it in the flow above,
**between step 2 and step 3**:

PowerShell:

```powershell
cd $work
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/Add-LocalFrameworkFeed.ps1 -Path ./hosted-agent-skills
```

Bash:

```bash
cd "$WORK"
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/add-local-framework-feed.sh ./hosted-agent-skills
```

See the
[`Hosted-ChatClientAgent`](../Hosted-ChatClientAgent/README.md#deploy-your-local-framework-changes-contributors)
README for the full explanation of what the script changes and why.

## Troubleshooting

**`azd ai agent invoke` fails with `404 not_found: Conversation '<id>' not found`**

`azd` reuses the saved session and conversation per agent. Once the agent is redeployed or deleted,
that conversation no longer exists on the server. Start a fresh one:

```
azd ai agent invoke --new-conversation "Hello!"
```

For the full hosted-agent deployment guide, see the [official source-code deployment doc](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code).