# Foundry Hosted Agent Samples

This directory contains samples that demonstrate how to use hosted [Agent Framework](https://github.com/microsoft/agent-framework) agents with different capabilities and configurations on Foundry using the Foundry Hosting Agent service. Each sample includes a README with instructions on how to set up, run, and interact with the agent.

> [IMPORTANT] Migrating from Protocol version 1.0.0 to 2.0.0: Foundry Hosting Agents service has been updated to use Protocol version 2.0.0. If your application is using Protocol version 1.0.0, please upgrade to Protocol version 2.0.0 in your `agent.manifest.yaml` or `agent.yaml` and upgrade to the latest `agent-framework-foundry-hosting` package. `agent-framework-foundry-hosting==1.0.0a260625` is the last version that supports Protocol version 1.0.0.
>
> The `agent-framework-foundry-hosting` Python API surface is intended to remain stable, but protocol 1.0.0 and 2.0.0 are incompatible.
## Samples

### Responses API

| # | Sample | Description |
|---|--------|-------------|
| 1 | [Basic](responses/basic/) | A minimal agent demonstrating basic request/response interaction and multi-turn conversations using `previous_response_id`. |
| 2 | [Tools](responses/tools/) | An agent with local tools (e.g., weather lookup), demonstrating how to register and invoke custom tool functions alongside the LLM. |
| 3 | [MCP](responses/mcp/) | An agent connected to a remote MCP server (GitHub), demonstrating external MCP tool provider integration. |
| 4 | [Foundry Toolbox](responses/foundry_toolbox/) | An agent using Azure Foundry Toolbox, demonstrating toolbox provisioning and querying available tools at runtime. |
| 5 | [Workflows](responses/workflows/) | An agent with a multi-step orchestrated workflow, demonstrating chaining prompts through an orchestrated flow. |
| 6 | [Files](responses/files/) | An agent demonstrating how to work with files in a hosted agent session, including uploading files to a hosted agent session and having the agent read and manipulate those files at runtime. |
| 7 | [Observability](responses/observability/) | A sample demonstrating how to enable observability for the agent deployed to Foundry. |
| 8 | [Azure AI Search RAG](responses/azure_search_rag/) | An agent with Retrieval Augmented Generation (RAG) capabilities backed by Azure AI Search, grounding answers in documents indexed in a pre-provisioned search index. |
| 9 | [Foundry Memory](responses/foundry_memory/) | An agent with persistent semantic memory backed by a Microsoft Foundry Memory Store, using `FoundryMemoryProvider` to remember user facts across sessions. |
| 10 | [Monty CodeAct](responses/monty_codeact/) | An agent with a Monty-backed CodeAct context provider, exposing a single `execute_code` tool that runs Python in a [pydantic-monty](https://github.com/pydantic/monty) interpreter and invokes typed host tools (`compute`, `fetch_data`) from inside the sandbox. Uses the beta `agent-framework-monty` package. |
| 11 | [Foundry Toolbox MCP Skills](responses/foundry_toolbox_mcp_skills/) | An agent that discovers MCP-based skills attached to a Foundry Toolbox and serves them via `SkillsProvider(MCPSkillsSource(...))`, fetching `SKILL.md` bodies and supplementary resources on demand. |
| 12 | [Using deployed agent](responses/using_deployed_agent.py) | Invoke an agent already deployed to Foundry using either a service-created or user-created hosted session, then delete the session after use. |

## Session Identifiers

Foundry hosted agents use multiple session-related values for different purposes. They are stored together on an
Agent Framework `AgentSession`, but they are not interchangeable.

| Value | Owner | Purpose | Lifecycle |
|-------|-------|---------|-----------|
| `AgentSession` | Agent Framework | A lightweight application-side container that keeps identifiers and mutable state together across agent runs. | Create one per logical application conversation and pass it to each `agent.run(...)` call. It can be serialized if the application needs to persist it. |
| `AgentSession.session_id` | Agent Framework/application | Identifies the local `AgentSession`, including lookup in an Agent Framework session store. It does not identify a Foundry resource. | Generated locally by default, or supplied by the application. Deleting a Foundry session does not delete this local identifier. |
| `AgentSession.service_session_id` | Responses API | Continues the model-side response or conversation chain. For Foundry agents, this may be a response ID sent as `previous_response_id` or a conversation ID sent as `conversation`. | Agent Framework updates and reuses it automatically. It is not the Foundry hosted-agent session ID and is not passed to `project_client.agents.delete_session(...)`. |
| Foundry `agent_session_id` | Foundry Agent Service | Identifies the hosted-agent [runtime session](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents#isolation-model) used by the deployed agent. Foundry can create it on the first request, or the application can create it explicitly with `project_client.agents.create_session(...)`. | Agent Framework stores it in `AgentSession.state[FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY]` and sends it as `extra_body["agent_session_id"]` on later requests. Delete it with `project_client.agents.delete_session(agent_name, agent_session_id)` when finished. |

During a hosted-agent conversation, one `AgentSession` can therefore contain both remote values:

```python
session.service_session_id
# Response or conversation continuation handle

session.state[FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY]
# Foundry hosted-agent session ID
```

Keep the same `AgentSession` across turns so Agent Framework can forward both values correctly. When cleaning up,
read the Foundry `agent_session_id` from `session.state` and pass that value to the Foundry session deletion API.
See [Using deployed agent](responses/using_deployed_agent.py) for service-created and user-created lifecycle examples.

### Invocations API

| # | Sample | Description |
|---|--------|-------------|
| 1 | [Basic](invocations/basic/) | A minimal agent demonstrating basic request/response using the invocations protocol. |
| 2 | [Break Glass](invocations/break_glass/) | An agent demonstrating a "break glass" scenario where customizations of the API behaviors are needed, allowing for more direct control over how requests and responses are handled by the hosting layer. |

## Running the Agent Host Locally

### Using `azd`

#### Prerequisites

1. **Azure Developer CLI (`azd`)**

    - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) and the AI agent extension: `azd ext install azure.ai.agents`
    - Authenticated: `azd auth login`

2. **Azure Subscription**

#### Create a new project

**No cloning required**. Create a new folder, point azd at the manifest on GitHub.

```bash
mkdir hosted-agent-framework-agent && cd hosted-agent-framework-agent

# Initialize from the manifest
azd ai agent init -m https://github.com/microsoft/agent-framework/blob/main/python/samples/04-hosting/foundry-hosted-agents/responses/basic/agent.manifest.yaml
```

Follow the instructions from `azd ai agent init` to complete the agent initialization. If you don't have an existing Foundry project and a model deployment, `azd ai agent init` will guide you through creating them.

#### Provision Azure Resources

> This step is only needed if you don't have an existing Foundry project and model deployment.

Run the following command to provision the necessary Azure resources:

```bash
azd provision
```

This will create the following Azure resources:

- A new resource group named `rg-[project_name]-dev`. In this guide, `[project_name]` will be `hosted-agent-framework-agent`.
- Within the resource group, among other resources, the most important ones are:
  - A new Foundry instance
  - A new Foundry project, within which a new model deployment will be created
  - An Application Insights instance
  - A container registry, which will be used to store the container images for the hosted agent

#### Set Environment Variables

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
# And any other environment variables required by the sample
```

Or in PowerShell:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
# And any other environment variables required by the sample
```

> Note: The environment variables set above are only for the current session. You will need to set them again if you open a new terminal session. if you want to set the environment variables permanently in the azd environment, you can use `azd env set <name> <value>`.

#### Running the Agent Host

```bash
azd ai agent run
```

Right now, the agent host should be running on `http://localhost:8088`

#### Invoking the Agent

Open another terminal, **navigate to the project directory**, and run the following command to invoke the agent:

```bash
azd ai agent invoke --local "Hello!"
```

Or you can in another terminal, without navigating to the project directory, run the following command to invoke the agent:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hello!"}'
```

Or in PowerShell:

```powershell
(Invoke-WebRequest -Uri http://localhost:8088/responses -Method POST -ContentType "application/json" -Body '{"input": "Hello!"}').Content
```

### Using `python`

#### Prerequisites

1. An existing Foundry project
2. A deployed model in your Foundry project
3. Azure CLI installed and authenticated
4. Python 3.10 or later

#### Running the Agent Host with Python

Clone the repository containing the sample code:

```bash
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework/python/samples/04-hosting/foundry-hosted-agents/responses
```

#### Environment setup

1. Navigate to the sample directory you want to explore. Create and activate a virtual environment using [uv](https://docs.astral.sh/uv/) (recommended):

   ```bash
   uv venv .venv
   ```

   ```bash
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1

   # Windows (Command Prompt)
   .venv\Scripts\activate.bat

   # macOS/Linux
   source .venv/bin/activate
   ```

   > **Note:** `python -m venv .venv` also works, but can hang indefinitely on Windows with Microsoft Store Python due to a known `ensurepip` issue. Use `uv venv .venv` to avoid this.

2. Install dependencies:

   ```bash
   uv pip install -r requirements.txt
   ```

3. Create a `.env` file with your Foundry configuration following the `env.example` file in the sample.

4. Make sure you are logged in with the Azure CLI:

   ```bash
   az login
   ```

#### Running the Agent Host

```bash
python main.py
```

Right now, the agent host should be running on `http://localhost:8088`

#### Invoking the Agent

On another terminal, run the following command to invoke the agent:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hello!"}'
```

Or in PowerShell:

```powershell
(Invoke-WebRequest -Uri http://localhost:8088/responses -Method POST -ContentType "application/json" -Body '{"input": "Hello!"}').Content
```

## Deploying the Agent to Foundry

Once you've tested locally, deploy to Microsoft Foundry.

### With an Existing Foundry Project

If you already have a Foundry project and the necessary Azure resources provisioned, you can skip the setup steps and proceed directly to deploying the agent.

After running `azd ai agent init -m <agent.manifest.yaml>` and following the prompts to configure your agent, you will have a project ready for deployment.

### Setting Up a New Foundry Project

Follow the steps in [Using `azd`](#using-azd) to set up the project and provision the necessary Azure resources for your Foundry deployment.

### Deploying the Agent

Once the project is setup and resources are provisioned, you can deploy the agent to Foundry by running:

```bash
azd deploy
```

> The Foundry hosting infrastructure will inject the following environment variables into your agent at runtime:
>
> - `FOUNDRY_PROJECT_ENDPOINT`: The endpoint URL for the Foundry project where the agent is deployed.
> - `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of the model deployment in your Foundry project. This is configured during the agent initialization process with `azd ai agent init`.
> - `APPLICATIONINSIGHTS_CONNECTION_STRING`: The connection string for Application Insights to enable telemetry for your agent.

This will package your agent and deploy it to the Foundry environment, making it accessible through the Foundry project endpoint. Once it's deployed, you can also access the agent through the Foundry UI.

For the full deployment guide, see the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

Once deployed, learn more about how to manage deployed agents in the [official management guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent).
