# Agent with Foundry Toolbox MCP Skills (Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that discovers **Agent Skills attached to a Foundry Toolbox** over the **MCP protocol** and exposes them to the model using the [Agent Skills](https://agentskills.io/) progressive-disclosure pattern, hosted on Microsoft Foundry using the **Responses protocol**.

Unlike the [C# reference sample](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/csharp/hosted-agents/agent-framework/foundry-toolbox-mcp-skills), which consumes skills from a toolbox that already exists, **this sample is self-contained**: it ships the `SKILL.md` sources and a `toolbox.yaml`, and walks you through creating the skills and the toolbox from zero with `azd`.

## How progressive disclosure works

The `FoundryToolbox` is attached to the agent and its skills are exposed through a `SkillsProvider`. When the agent runs, it discovers the toolbox's skills and applies the progressive-disclosure pattern so a skill's full body is only fetched when the agent actually needs it, reducing token usage:

1. **Advertise** — each skill's name and description are injected into the system prompt so the model knows what is available (~100 tokens per skill).
2. **Load** — when the model decides a skill is relevant, it retrieves the full `SKILL.md` body on demand via `resources/read`.

> The Agent Skills spec defines a third stage — **read resources** — where a skill fetches supplementary files (reference documents, assets) on demand. That stage requires skills to be served as `type: skill-md` with sibling resources, but Foundry serves ZIP-uploaded (multi-file) skills as `type: archive`, which the Python `MCPSkillsSource` does not currently discover. So this sample keeps both skills as single-file `SKILL.md` (advertise + load only). See the [`09_foundry_skills`](../09_foundry_skills/README.md) sample for the same instruction-only pattern via direct download.

## Toolbox MCP skills vs. Foundry Skills

Foundry exposes skills in two ways, and this sample uses the second one.

**Foundry Skills** are downloaded directly into an agent: the agent pulls each `SKILL.md` from the Skills API at startup and serves the bodies from local files. See the [`09_foundry_skills`](../09_foundry_skills/README.md) sample.

**Toolbox MCP skills** are accessed through a toolbox over the MCP protocol. A toolbox bundles a curated set of skills (and optionally tools) behind one MCP endpoint, and any MCP client discovers them automatically. Skill bodies are fetched on demand. The same `SKILL.md` files power both modes — the difference is only in delivery.

## How it works

### Model integration

[`main.py`](main.py) uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It then:

1. Constructs a `FoundryToolbox(credential, load_tools=False)`. The toolbox resolves its MCP endpoint from `TOOLBOX_ENDPOINT`, authenticates every request with the credential, and forwards the platform per-request call-id. `load_tools=False` keeps the toolbox's tools hidden so only its Agent Skills are surfaced.
2. Calls `toolbox.as_skills_provider()`, which discovers skills from the well-known `skill://index.json` resource on the toolbox's MCP session and exposes them as an agent context provider.
3. Passes the toolbox via `tools=` **and** the provider via `context_providers=`. The `tools=` wiring connects the MCP session (the connection the provider reads from); the `context_providers=` wiring runs the advertise/load logic over that session. Both are required — see [main.py](main.py) for the full implementation.

### Agent hosting

The agent is hosted with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol on `http://localhost:8088`.

## The bundled skills

This sample ships two source skills under [`skills/`](skills/), reused from the [`09_foundry_skills`](../09_foundry_skills/README.md) sample so you can compare the two delivery modes side by side:

| Skill | Purpose |
|---|---|
| [`support-style`](skills/support-style/SKILL.md) | Voice, formatting, and signature rules for Contoso Outdoors support replies. |
| [`escalation-policy`](skills/escalation-policy/SKILL.md) | When and how to escalate a customer ticket, including the refund-authority matrix. |

Each file includes a unique `*-CANARY-*` token that the model is asked to echo, so a response proves the model actually **loaded** the skill rather than hallucinating:

| Artifact | Canary | Proves |
|---|---|---|
| `support-style/SKILL.md` | `STYLE-CANARY-3318` | The model loaded the `support-style` body. |
| `escalation-policy/SKILL.md` | `ESC-CANARY-7742` | The model loaded the `escalation-policy` body. |

> The `name` and `description` values in the YAML front matter must be **unquoted** — quoting them causes the Skills API to reject the import.

## Prerequisites

- Python 3.12+
- A Microsoft Foundry project with a deployed model (e.g., `gpt-5`)
- **Azure Developer CLI (`azd`)** 1.25+ with the unified Foundry extension bundle:
  ```bash
  azd extension install microsoft.foundry
  ```
- Authenticated: `azd auth login` (and `az login` if you run the host with plain `python`)

### Required RBAC

Your identity (and, in production, the Managed Identity running the container) needs the **Foundry User** role (formerly *Azure AI User*) on the Foundry project. This covers creating skills, creating the toolbox, and discovering skills over MCP at runtime.

## Building the toolbox from zero

The agent reads the toolbox's MCP endpoint from `TOOLBOX_ENDPOINT`. Before you can run it, create the skills in your Foundry project and then create a toolbox that references them.

Point `azd` at your project once:

```bash
azd ai project set "https://<account>.services.ai.azure.com/api/projects/<project>"
```

### Step 1 — Create the skills in Foundry

Skills referenced by a toolbox must already exist in the same Foundry project. Both skills in this sample are single-file `SKILL.md` skills, so upload each directly:

```bash
azd ai skill create support-style     --file ./skills/support-style/SKILL.md     --no-prompt
azd ai skill create escalation-policy --file ./skills/escalation-policy/SKILL.md --no-prompt
```

> **Why single files (not ZIPs)?** Uploading a skill as a `.zip` (to bundle supplementary resource files) makes Foundry serve it as `type: archive` in the toolbox's `skill://index.json`. The Python `MCPSkillsSource` only discovers `type: skill-md` entries, so archive skills are silently dropped. Keeping each skill as a single `SKILL.md` ensures both are discovered.

> The `name:` in each `SKILL.md` front matter must equal the positional skill name you pass to `azd ai skill create`. To replace a skill after editing it, re-run with `--force` (this deletes the existing skill and all its versions, then uploads a fresh v1).

### Step 2 — Create the toolbox

Create the toolbox once from the bundled [`toolbox.yaml`](toolbox.yaml), which references both skills by name plus one connectionless placeholder tool (`code_interpreter`):

```bash
azd ai toolbox create maf-skills-toolbox --from-file ./toolbox.yaml --no-prompt
```

> **Why a placeholder tool?** `azd ai toolbox create` requires at least one `tools` or `connections` entry, so a purely skills-only toolbox cannot be created directly. The bundled `toolbox.yaml` includes a single connectionless `code_interpreter` tool to satisfy this. Because the agent builds the toolbox with `load_tools=False` (see [main.py](main.py)), that tool is never surfaced to the model — only the skills are — so the toolbox stays effectively skills-only from the agent's perspective.

The first version becomes the default automatically. Use `azd ai toolbox list`, `azd ai toolbox show maf-skills-toolbox`, and `azd ai toolbox version list maf-skills-toolbox` to inspect it, and `azd ai toolbox delete maf-skills-toolbox --force` to remove it.

### Step 3 — Store the toolbox endpoint

`azd ai toolbox create` prints the toolbox's **versioned** MCP endpoint. Copy it and store it so the agent connects to it:

```bash
azd env set TOOLBOX_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/maf-skills-toolbox/versions/1/mcp?api-version=v1"
```

When running the host with plain `python`, put the same value in a `.env` file next to `main.py` instead — see [`.env.example`](.env.example).

## Running the agent host

Follow the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the parent README to run the host with either `azd ai agent run` or plain `python main.py`. This sample requires `TOOLBOX_ENDPOINT` to be set (see Step 3) in addition to the standard `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` variables.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. See the [parent README](../../README.md) for details. Use this README for sample queries.

Send a POST request with a JSON body containing an `"input"` field:

```bash
# Discover what the toolbox advertises (advertise step only)
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What skills do you have available?"}'

# Routine question -> loads support-style
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi, I am Alex. Can I return my tent within 30 days?"}'

# Large refund + legal threat -> loads escalation-policy (which includes the refund matrix)
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "I want a $750 refund on Order #A-1042 right now or I am calling my lawyer."}'
```

| Prompt mentions | Skill that should drive the response | Canary you should see |
|---|---|---|
| Routine return / shipping / care question | `support-style` | `STYLE-CANARY-3318` |
| Injury, legal threat, press, or refund > $500 | `escalation-policy` (+ `support-style`) | `ESC-CANARY-7742` |

Because skills are loaded on demand, a canary token in a response proves the model actually invoked `load_skill` for the matching skill — not that it merely saw the name in the advertised list.

## Deploying the agent to Foundry

Once tested locally, deploy to Microsoft Foundry by following the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the parent README.

Make sure the skills and toolbox exist in the **same** Foundry project you deploy to (run the steps above against it first), and that `TOOLBOX_ENDPOINT` is set in your `azd` environment so it is injected into the hosted container per [`agent.manifest.yaml`](agent.manifest.yaml):

```bash
azd env set TOOLBOX_ENDPOINT "<versioned-endpoint-from-step-2>"
```

The deployed agent's Managed Identity needs the **Foundry User** role on the Foundry project to discover skills over MCP at startup.

> The bundled `skills/` folder and `toolbox.yaml` are authoring inputs only; they are excluded from the deployed container via [`.azdignore`](.azdignore) / [`.dockerignore`](.dockerignore). The running agent discovers everything it needs from the toolbox MCP endpoint.
