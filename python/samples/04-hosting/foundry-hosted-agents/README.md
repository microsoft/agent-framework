# Foundry Hosted Agent Samples

This directory contains samples that demonstrate how to use hosted [Agent Framework](https://github.com/microsoft/agent-framework) agents with different capabilities and configurations on Foundry using the Foundry Hosting Agent service. Each sample includes a README with instructions on how to set up, run, and interact with the agent.

## Samples

### Responses API

| # | Sample | Description |
|---|--------|-------------|
| 1 | [Basic](responses/01_basic/) | A minimal agent demonstrating basic request/response interaction and multi-turn conversations using `previous_response_id`. |
| 2 | [Tools](responses/02_tools/) | An agent with local tools (e.g., weather lookup), demonstrating how to register and invoke custom tool functions alongside the LLM. |
| 3 | [MCP](responses/03_mcp/) | An agent connected to a remote MCP server (GitHub), demonstrating external MCP tool provider integration. |
| 4 | [Foundry Toolbox](responses/04_foundry_toolbox/) | An agent using Azure Foundry Toolbox, demonstrating toolbox provisioning and querying available tools at runtime. |
| 5 | [Workflows](responses/05_workflows/) | An agent with a multi-step orchestrated workflow, demonstrating chaining prompts through an orchestrated flow. |
| 6 | [Using deployed agent](responses/using_deployed_agent.py) | A sample demonstrating how to invoke an agent that has already been deployed to Foundry, showing how to interact with a hosted agent in code. |

### Invocations API

| # | Sample | Description |
|---|--------|-------------|
| 1 | [Basic](invocations/01_basic/) | A minimal agent demonstrating session state management via `agent_session_id` in URL params/response headers. |
| 2 | [Break Glass](invocations/02_break_glass/) | An agent demonstrating a "break glass" scenario where customizations of the API behaviors are needed, allowing for more direct control over how requests and responses are handled by the hosting layer. |

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
azd ai agent init -m https://github.com/microsoft/agent-framework/blob/main/python/samples/04-hosting/foundry-hosted-agents/responses/01_basic/agent.manifest.yaml
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

1. Navigate to the sample directory you want to explore. Create a virtual environment:

   ```bash
   python -m venv .venv

   # Windows
   .venv\Scripts\Activate

   # macOS/Linux
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
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