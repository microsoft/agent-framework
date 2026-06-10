# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that loads its behavioral guidelines from [**Foundry Skills**](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills) at startup, hosted using the **Responses protocol**. Skills are authored once as `SKILL.md` files, uploaded to your Foundry project through the Skills REST API, and downloaded by the agent on boot so updates ship without code changes.

## How It Works

### Authoring skills

Each skill is a Markdown file with a YAML front matter block. This sample ships two source skills under [`skills/`](skills/):

| Skill | Purpose |
|---|---|
| [`support-style`](skills/support-style/SKILL.md) | Voice, formatting, and signature rules for Contoso Outdoors support replies. |
| [`escalation-policy`](skills/escalation-policy/SKILL.md) | When and how to escalate a customer ticket. |

Each `SKILL.md` includes a unique `*-CANARY-*` token that the model is asked to echo, so you can prove the skill was loaded from Foundry (not hallucinated) by checking the response.

> The `name` and `description` values in the YAML front matter must be **unquoted** — quoting them causes the Skills REST API to return HTTP 500 on import.

### Uploading skills

The sample includes a convenience provisioning step that checks whether each skill exists in Foundry and uploads it if not, gated behind the `PROVISION_SAMPLE_SKILLS=true` env var. **In production, skill provisioning is an external concern** — it is NOT the hosted agent's responsibility. A real deployment pipeline would provision skills separately (e.g., via a CI/CD step, a CLI script, or a management portal).

The provisioning uses `ProjectAgentSkills.CreateSkillFromPackageAsync(directoryPath)` from the `Azure.AI.Projects.Agents` SDK. The method packages the `SKILL.md` file as a ZIP and uploads it to Foundry.

### Downloading skills at agent startup

[`Program.cs`](Program.cs) reads the comma-separated `SKILL_NAMES` env var and for each skill name downloads the ZIP archive from Foundry via `ProjectAgentSkills.DownloadSkillAsync(name)`, then unpacks it into a **separate runtime directory** at `downloaded_skills/<name>/` (kept distinct from the static `skills/` source folder).

An [`AgentSkillsProvider`](../../../../../src/Microsoft.Agents.AI/Skills/AgentSkillsProvider.cs) is then built over `downloaded_skills/` and attached to the agent as a context provider. The provider follows the [Agent Skills](https://agentskills.io/) progressive-disclosure pattern:

1. **Advertise** — skill names and descriptions are injected into the system prompt at session start (~100 tokens per skill).
2. **Load** — the model calls the `load_skill` tool when it decides a skill is relevant to the user's turn, and the full `SKILL.md` body is returned.

This means the model only pays the token cost for a skill's full body when it actually needs it, and updating a skill in Foundry + restarting the agent is enough to pick up the change — no code redeploy required.

> **Note:** This sample supports instruction-only and resource-based skills. If your downloaded skills contain scripts, add a script runner when constructing the `AgentSkillsProvider`.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the Responses API hosting layer (`AddFoundryResponses` / `MapFoundryResponses`).

## Prerequisites

- An Azure AI Foundry project with a deployed model (e.g., `gpt-4o`)
- Azure CLI logged in (`az login`)

### Required RBAC

Your identity (or the Managed Identity running the container in production) needs **Azure AI User** on the Foundry project scope. This single role covers both authoring skills and downloading them.

## Running the Agent Host

Set the required environment variables and run the sample with `dotnet run`:

```bash
export AZURE_AI_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"
export SKILL_NAMES="support-style,escalation-policy"
export PROVISION_SAMPLE_SKILLS="true"   # First run only — provisions skills to Foundry
```

Or in PowerShell:

```powershell
$env:SKILL_NAMES="support-style,escalation-policy"
$env:PROVISION_SAMPLE_SKILLS="true"     # First run only — provisions skills to Foundry
```

You can also place these in a `.env` file next to `Program.cs` — see [`.env.example`](.env.example).

On startup you should see:

```text
Skill 'support-style' already exists in Foundry.
Skill 'escalation-policy' already exists in Foundry.
Downloading skill 'support-style' from Foundry...
Downloading skill 'escalation-policy' from Foundry...
```

The downloaded `SKILL.md` files land under `downloaded_skills/<name>/SKILL.md` next to the published output. This directory is recreated from scratch on every run, so deleting it manually is never necessary.

## Interacting with the agent

> Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi, I am Alex. I just want to confirm I can return my tent within 30 days."}'
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "I want a $750 refund on Order #A-1042 right now or I am calling my lawyer."}'
```

| Prompt mentions | Skill that should drive the response |
|---|---|
| Routine return / shipping / care question | Model loads `support-style` (canary `STYLE-CANARY-3318`) — no escalation. |
| Injury, legal threat, press, or refund > $500 | Model loads `escalation-policy` (canary `ESC-CANARY-7742`) **and** `support-style`. |

Because skills are loaded on demand, the canary token in a response also proves the model actually invoked `load_skill` for the matching skill (not just saw its name in the advertised list).

## Deploying the Agent to Foundry

When deploying to Foundry, make sure `SKILL_NAMES` is set in your `azd` environment so it gets injected into the hosted container per [`agent.manifest.yaml`](agent.manifest.yaml):

```bash
azd env set SKILL_NAMES "support-style,escalation-policy"
```

The deployed agent's Managed Identity needs **Azure AI User** on the Foundry project to download skills at startup.

> The `skills/` source folder is **not** deployed to Foundry — only the downloaded skills are used at runtime. The provisioning step must have been run against the same Foundry project before the agent can download the skills.

### Deploying to Foundry (azd spec)

This sample includes an `azd` manifest (`agent.manifest.yaml`) and hosted agent spec (`agent.yaml`) for deployment to Foundry.

Initialize an `azd` project from this sample's manifest:

```bash
mkdir hosted-agent-skills && cd hosted-agent-skills
azd ai agent init -m https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-AgentSkills/agent.manifest.yaml
```

Then deploy:

```bash
azd deploy
```

If you need to override defaults, set deployment-time environment variables in the `azd` environment before deploying:

```bash
azd env set AGENT_NAME hosted-agent-skills
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-4o
```

For end-to-end hosted agent deployment guidance, see the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).
