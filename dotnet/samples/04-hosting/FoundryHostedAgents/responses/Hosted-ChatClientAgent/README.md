# Hosted-ChatClientAgent

A minimal general-purpose AI assistant hosted as a Foundry Hosted Agent using the Responses protocol. The agent is created inline via `AIProjectClient.AsAIAgent(model, instructions)` and served with `AddFoundryResponses` / `MapFoundryResponses`.

This sample deploys to Foundry **directly from source (code / ZIP upload)**: the platform builds and runs your code with no container image, so there is no Dockerfile to author or container registry to manage.

The sibling [`Hosted-ChatClientAgent-Dockerfile`](../Hosted-ChatClientAgent-Dockerfile/) sample is the same agent deployed the other way, as a container image built from a `Dockerfile`. Source deploy is the default for .NET, so start here and switch only if you need control over the runtime image.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An **existing** Foundry project with an **existing** model deployment (for example `gpt-4o`).
  This sample's `azure.yaml` declares no `deployments:` block, so `azd` connects to a project and
  a deployment you already have rather than creating them. `azd ai agent init` prompts you to pick
  the project, and takes the deployment name as the `-d` argument.
- Azure CLI logged in (`az login`)
- Azure Developer CLI (`azd`) with the AI agents extension: `azd extension install azure.ai.agents`

## Files

| File | Purpose |
|------|---------|
| `Program.cs` | The agent: builds the agent, hosts it with the Responses protocol. |
| `azure.yaml` | The unified `azd` project file. Declares the Foundry project and the hosted agent with `codeConfiguration` (source/ZIP deploy), and passes the listen port and the model deployment name to the container through `env`. |
| `.agentignore` | Controls which files are excluded from the code-deploy ZIP upload (`.gitignore` syntax). |
| `HostedChatClientAgent.csproj` | Self-contained project: single target framework and explicit package versions. It also opts out of the repository's central package management, which does not travel inside the ZIP. |
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
ASPNETCORE_URLS=http://+:8088
AZURE_TOKEN_CREDENTIALS=dev
```

> `.env` is gitignored. The `.env.example` template is checked in as a reference.

> `ASPNETCORE_URLS` pins the local run to the port the `Using-Samples` REPLs expect. Recent
> `Microsoft.Agents.AI.Foundry.Hosting` versions bind that port themselves, so it only matters
> while this project is pinned to an older published package.

> **Windows note:** write `.env` as UTF-8 **without** a byte order mark. `azd` reads the file
> during `azd ai agent init` and fails with `unexpected character "»" in variable name` when a mark
> is present. PowerShell's `Set-Content -Encoding UTF8BOM` adds one; use `-Encoding utf8NoBOM`.

> **Local development on a machine without a managed identity:** set `AZURE_TOKEN_CREDENTIALS=dev`.
> `Program.cs` authenticates with `DefaultAzureCredential` (the pattern the hosted platform
> expects, where a managed identity is injected). On a developer machine with no managed identity,
> `DefaultAzureCredential` probes the Azure Instance Metadata Service (IMDS, `169.254.169.254`) and
> blocks for a long time on the network timeout before every model call, so requests appear to
> hang. Setting `AZURE_TOKEN_CREDENTIALS=dev` restricts `DefaultAzureCredential` to developer
> credentials (Azure CLI, Visual Studio, `azd`) and skips the managed-identity probe. This variable
> is only for local runs; the deployed agent in Foundry uses the platform-injected managed identity.

## Run and test locally

Local runs use two terminals: one hosts the agent, the other is a code-first client that talks to it
using Agent Framework components, see the sibling [`Using-Samples`](../Using-Samples/) REPLs.

`AddFoundryResponses` binds the app to the port Foundry probes for readiness (8088 by default,
overridable with the `PORT` environment variable), and `MapFoundryResponses` serves the standard
`POST /responses` route. That is the same route the platform routes to for a deployed agent, so the
local server needs no extra wiring: the client just points an OpenAI responses client at
`http://localhost:8088`.

**Terminal 1 — host the agent:**

```
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-ChatClientAgent
az login
dotnet run
```

The agent starts on `http://localhost:8088`.

**Terminal 2 — chat with it (code-first REPL):**

PowerShell:

```powershell
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Using-Samples/SimpleAgent
$env:AZURE_AI_AGENT_NAME = "hosted-chat-client-agent"
dotnet run -- --local
```

Bash:

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Using-Samples/SimpleAgent
export AZURE_AI_AGENT_NAME="hosted-chat-client-agent"
dotnet run -- --local
```

Without `--local` the REPL asks which agent to chat with; choose **2 (Local)**. Either way it
points an OpenAI responses client at the local server and streams the reply.

## Deploy to Foundry (source / ZIP)

`azd` scaffolds the project into a working folder, so every step below runs from an **empty
directory outside the repository**, and `-m` points at this sample's `azure.yaml`.

### Step 1: create the working directory and enter it

PowerShell:

```powershell
$work = Join-Path $env:TEMP "hosted-chat-work"
mkdir $work
cd $work
```

Bash:

```bash
WORK="${TMPDIR:-/tmp}/hosted-chat-work"
mkdir -p "$WORK"
cd "$WORK"
```

### Step 2: scaffold the project

`azd ai agent init` copies the sample into a subfolder named after the top-level `name:` in
`azure.yaml`, which is `hosted-chat-client-agent`. It also writes the adopted `azure.yaml` and the
`azd` environment there.

`azd ai agent init` prompts you to pick the Foundry project, so no project argument is needed.
`-d` is the name of an existing model deployment in that project; omit it and `azd` prompts for
that too.

> Pick an **existing** project at the prompt. The prompt needs an interactive terminal: run
> non-interactively (in CI, for example) and `azd` skips it and provisions a brand new Foundry
> project and resource group instead. Pass `-p <project-resource-id>` when you need that to be
> unattended.

`azure.yaml` passes the model deployment to the container by reading it from the `azd` environment.
Confirm it landed there, and set it yourself if it did not:

```
azd env get-values
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME <model-deployment>
```

PowerShell:

```powershell
$sample = "<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-ChatClientAgent/azure.yaml"

azd auth login
azd ai agent init -m $sample -d <model-deployment>
```

Bash:

```bash
SAMPLE="<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-ChatClientAgent/azure.yaml"

azd auth login
azd ai agent init -m "$SAMPLE" -d <model-deployment>
```

### Step 3: provision and deploy

Contributors: if you are changing the Agent Framework source in this repository and want the
deployed agent to run **your** build rather than the published packages, do the extra step in
[Deploy your local framework changes](#deploy-your-local-framework-changes-contributors) now,
before the commands below. Everyone else can ignore it.

```
cd hosted-chat-client-agent
azd provision
azd deploy
azd ai agent invoke "Hello!"
```

`azd` packages the source into a ZIP (honoring `.agentignore`), uploads it, and Foundry runs
`dotnet restore` + `dotnet publish` on it during provisioning (`dependencyResolution: remote_build`
in `azure.yaml`). No Dockerfile, no container registry.

You can also test the deployed agent with the REPL:

PowerShell:

```powershell
cd <repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Using-Samples/SimpleAgent
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<your-account>.services.ai.azure.com/api/projects/<your-project>"
$env:AZURE_AI_AGENT_NAME      = "hosted-chat-client-agent"
dotnet run -- --remote
```

Bash:

```bash
cd <repo>/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Using-Samples/SimpleAgent
export FOUNDRY_PROJECT_ENDPOINT="https://<your-account>.services.ai.azure.com/api/projects/<your-project>"
export AZURE_AI_AGENT_NAME="hosted-chat-client-agent"
dotnet run -- --remote
```

### Step 4: clean up

```
azd down
```

Then delete the working directory.

## Deploy your local framework changes (contributors)

**Skip this section unless you are changing the Agent Framework itself.** Everything above is the
complete flow for using the sample. This section only applies when you are working on the framework
source in this repository, or when you otherwise need a build of it that is not published on
nuget.org.

The reason it exists: the project restores the **published** Agent Framework packages, and Foundry
restores from nuget.org when it builds the upload. So editing framework source in this repository
changes nothing about the deployed agent, no matter how many times you rebuild locally. The
uploaded folder is self-contained and knows nothing about your working tree.

The extra step packs your local framework source into NuGet packages and puts them **inside the
upload**, together with a `nuget.config` that points the restore at them. The server-side restore
then resolves the framework from the packages you shipped instead of from nuget.org.

Run it in the flow above, **between step 2 and step 3**. Nothing else changes.

Run it from `$work`, the working directory created in step 1, which now holds the
`hosted-chat-client-agent` folder that `azd ai agent init` scaffolded:

PowerShell:

```powershell
cd $work
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/Add-LocalFrameworkFeed.ps1 -Path ./hosted-chat-client-agent
```

Bash:

```bash
cd "$WORK"
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/add-local-framework-feed.sh ./hosted-chat-client-agent
```

Then continue with step 3. The path argument is optional: called without it, the script uses the
current directory, so you can also run it from inside `hosted-chat-client-agent`.

The script changes three things in the scaffolded folder:

| Change | Detail |
|--------|--------|
| Creates `local-feed/` | The Agent Framework packed from your local source, stamped with a version like `1.15.0-preview-local.<timestamp>` |
| Creates `nuget.config` | Resolves `Microsoft.Agents.AI*` from that folder and everything else from nuget.org |
| Edits the `.csproj` | Repoints its `AgentFrameworkVersion` property at the version just packed |

Both generated files ship inside the ZIP, so the server-side restore resolves the framework from
the upload. The scaffolded folder is a throwaway copy, so the repository is left untouched.

Two details worth knowing:

- The version carries a timestamp because NuGet caches by package id and version. Reusing a version
  would silently restore the previously packed bits instead of the build you just made.
- The whole package closure is packed, not just the two packages the sample references. Packing
  only the leaf packages lets NuGet fill the rest from nuget.org, mixing a published core with a
  locally built host, which fails to compile.

Before spending a deploy, build the scaffolded folder locally. A restore problem surfaces in
seconds instead of after the server-side build:

```
cd hosted-chat-client-agent
dotnet build -c Debug --tl:off
```

## Troubleshooting

**`azd ai agent invoke` fails with `404 not_found: Conversation '<id>' not found`**

`azd` saves the session and conversation per agent and reuses them on the next invoke. Once the
agent is redeployed, deleted, or restarted, that saved conversation no longer exists on the server,
so every following invoke fails even though the agent itself is healthy. Start a fresh one:

```
azd ai agent invoke --new-conversation "Hello!"
```

Add `--new-session` as well if the failure persists.

For the full hosted-agent deployment guide, see the [official source-code deployment doc](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code).
