# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that loads its behavioral guidelines from [**Foundry Skills**](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills?view=foundry&pivots=python) at startup, hosted using the **Responses protocol**. Skills are authored once as `SKILL.md` files, uploaded to your Foundry project through `AIProjectClient.beta.skills`, and downloaded by the agent on boot so updates ship without code changes.

## How It Works

### Authoring skills

Each skill is a Markdown file with a YAML front matter block. This sample ships two source skills under [`skills/`](skills/):

| Skill | Purpose |
|---|---|
| [`support-style`](skills/support-style/SKILL.md) | Voice, formatting, and signature rules for Contoso Outdoors support replies. |
| [`escalation-policy`](skills/escalation-policy/SKILL.md) | When and how to escalate a customer ticket. |

Each `SKILL.md` includes a unique `*-CANARY-*` token that the model is asked to echo, so you can prove the skill was loaded from Foundry (not hallucinated) by checking the response.

> The `name` and `description` values in the YAML front matter must be **unquoted** — quoting them causes the Skills REST API to return HTTP 500 on import.

### Uploading skills with `AIProjectClient`

[`provision_skills.py`](provision_skills.py) walks `skills/*/SKILL.md`, packages each file as an in-memory ZIP (with `SKILL.md` at the archive root), and imports it through [`AIProjectClient.beta.skills.create_from_package`](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills?view=foundry&pivots=python#option-2-import-from-a-skillmd-zip). The client is constructed with `allow_preview=True` (Skills is a preview feature) and authenticates with `DefaultAzureCredential`. Existing skills are deleted first via `beta.skills.delete` so the script is safe to re-run after editing a `SKILL.md`, and `beta.skills.list` is called at the end to verify each skill round-trips.

### Downloading skills at agent startup

[`main.py`](main.py) reads the comma-separated `SKILL_NAMES` env var, opens an `AIProjectClient` (also with `allow_preview=True`), and for each skill name streams the ZIP archive from `beta.skills.download(name)` and unpacks it into a **separate runtime directory** at `downloaded_skills/<name>/` (kept distinct from the static `skills/` source folder so the two never get confused — `skills/` is the input to `provision_skills.py`, `downloaded_skills/` is the output of `main.py`'s bootstrap step).

A [`SkillsProvider`](../../../../../packages/core/agent_framework/_skills.py) is then built over `downloaded_skills/` and attached to the `Agent` as a context provider. The provider follows the [Agent Skills](https://agentskills.io/) progressive-disclosure pattern:

1. **Advertise** — skill names and descriptions are injected into the system prompt at session start (~100 tokens per skill).
2. **Load** — the model calls the `load_skill` tool when it decides a skill is relevant to the user's turn, and the full `SKILL.md` body is returned.

This means the model only pays the token cost for a skill's full body when it actually needs it, and updating a skill in Foundry + restarting the agent is enough to pick up the change — no code redeploy required.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Prerequisites

- An Azure AI Foundry project with a deployed model (e.g., `gpt-4.1-mini`)
- Azure CLI logged in (`az login`)

### Required RBAC

Your identity (or the Managed Identity running the container in production) needs **Azure AI User** on the Foundry project scope. This single role covers both authoring skills with `provision_skills.py` and downloading them from `main.py`.

## Provisioning the skills (one time)

From this directory, with the venv activated and `az login` done:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
python provision_skills.py
```

Or in PowerShell:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
python provision_skills.py
```

Expected output:

```text
Provisioning skill 'escalation-policy' from skills/escalation-policy/SKILL.md...
  Imported skill 'escalation-policy' (id=skill_..., has_blob=True).
Provisioning skill 'support-style' from skills/support-style/SKILL.md...
  Imported skill 'support-style' (id=skill_..., has_blob=True).
Done.
```

Re-running the script after editing a `SKILL.md` re-imports the skill, replacing the previous version.

> To remove a skill manually, call `project.beta.skills.delete("<name>")` on an `AIProjectClient` constructed with `allow_preview=True`.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

In addition to the standard environment variables, this sample requires:

```bash
export SKILL_NAMES="support-style,escalation-policy"
```

Or in PowerShell:

```powershell
$env:SKILL_NAMES="support-style,escalation-policy"
```

You can also place these in a `.env` file next to `main.py` — see [`.env.example`](.env.example).

On startup you should see:

```text
Downloading skill 'support-style' from Foundry...
Downloading skill 'escalation-policy' from Foundry...
```

The downloaded `SKILL.md` files land under `downloaded_skills/<name>/SKILL.md` next to `main.py`. This directory is recreated from scratch on every run, so deleting it manually is never necessary.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

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

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.

When deploying, make sure `SKILL_NAMES` is set in your `azd` environment so it gets injected into the hosted container per [`agent.manifest.yaml`](agent.manifest.yaml):

```bash
azd env set SKILL_NAMES "support-style,escalation-policy"
```

If it is not set, running `azd ai agent init -m <agent-manifest.yaml>` will prompt you to enter it interactively.

The deployed agent's Managed Identity needs **Azure AI User** on the Foundry project to download skills at startup. Make sure you have run `provision_skills.py` against the same Foundry project before deploying — otherwise the agent will fail to start with HTTP 404 on the skill download.

> The `skills/` source folder is **not** deployed to Foundry — only the downloaded skills are used at runtime. The `provision_skills.py` step is required to upload the skills to Foundry before the agent can download them.