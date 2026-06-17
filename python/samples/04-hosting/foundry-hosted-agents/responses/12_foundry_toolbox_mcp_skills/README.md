# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that discovers **MCP-based skills from a Foundry Toolbox** and makes them available via `SkillsProvider(MCPSkillsSource(...))`, hosted using the **Responses protocol**.

The `SkillsProvider` is attached to the agent as a context provider and implements the [Agent Skills](https://agentskills.io/) progressive-disclosure pattern. When the agent is prompted, it discovers available skills in the Foundry Toolbox via the provider:

1. **Advertise** — skill names and descriptions are injected into the system prompt so the agent knows what is available.
2. **Load** — when the agent decides a skill is relevant, it retrieves the full skill body with detailed instructions via the provider.
3. **Read resources** — if a skill includes supplementary content (reference documents, assets), the agent reads them on demand via the provider.

This way the full skill body and resources are only loaded when the agent actually needs them, reducing token usage.

## Toolbox MCP skills vs. Foundry Skills

Foundry exposes skills in two ways, and this sample uses the second one.

Foundry Skills are managed through the Foundry Skills REST API. An agent downloads each `SKILL.md` as a ZIP at startup, serving the bodies from local files. See the [`09_foundry_skills`](../09_foundry_skills/README.md) sample for a demonstration.

Toolbox MCP skills are accessed through a toolbox over the MCP protocol. A toolbox bundles a curated set of skills behind one MCP endpoint, and any MCP client discovers them automatically. Skill bodies and any supplementary resources are fetched on demand.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It connects to the toolbox's MCP endpoint via the `mcp` library's `streamable_http_client`, discovers skills served by the toolbox through `MCPSkillsSource`, and injects them as a context provider via `SkillsProvider`. The toolbox endpoint URL is derived from `FOUNDRY_PROJECT_ENDPOINT` and `TOOLBOX_NAME`.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Prerequisites

- Python 3.12+
- An Azure AI Foundry project with a deployed model (e.g., `gpt-5`)
- A Foundry Toolbox with skills attached (see below)
- Azure CLI logged in (`az login`)

## Setting up a Foundry Toolbox with skills

This sample requires a Foundry Toolbox that has skills attached to it. Skills are `SKILL.md` files you author once, store centrally in Foundry through the versioned Skills API, and attach to a toolbox so any MCP client can discover and load them.

1. **Author a skill** — Create a `SKILL.md` file following the [Agent Skills](https://agentskills.io/) specification format (YAML front matter with `name` and `description`, plus Markdown body).
2. **Create the skill in Foundry** — Upload the skill via the Skills REST API, Python SDK, or `azd ai skill create`. See [Use skills with Microsoft Foundry agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills).
3. **Attach the skill to a toolbox** — Add a skill reference to a toolbox version so MCP clients can discover it. See [Attach skills to a toolbox](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox#attach-skills-to-a-toolbox).

When the agent connects to the toolbox MCP endpoint, skills are advertised through a well-known `skill://index.json` discovery resource. The `MCPSkillsSource` in this sample reads `skill://index.json` the first time the agent runs to discover all attached skills, then fetches each `SKILL.md` body on demand via `resources/read`.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

An extra environment variable must be set to point to the toolbox name:

```bash
export TOOLBOX_NAME="my-toolbox"
```

Or in PowerShell:

```powershell
$env:TOOLBOX_NAME="my-toolbox"
```

You can also place these in a `.env` file next to `main.py` — see [`.env.example`](.env.example).

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What skills do you have available?"}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.
