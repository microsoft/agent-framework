# Hosted Agent Samples

These samples demonstrate how to build and host AI agents in Python using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/) together with Microsoft Agent Framework. Each sample runs locally as a hosted agent and includes `Dockerfile` and `agent.yaml` assets for deployment to Microsoft Foundry.

## Samples

| Sample | Description |
|--------|-------------|
| [`agent_with_hosted_mcp`](./agent_with_hosted_mcp/) | Hosted MCP tool that connects to Microsoft Learn via `https://learn.microsoft.com/api/mcp` |
| [`agent_with_text_search_rag`](./agent_with_text_search_rag/) | Retrieval-augmented generation using a custom `BaseContextProvider` with Contoso Outdoors sample data |
| [`agents_in_workflow`](./agents_in_workflow/) | Concurrent workflow that combines researcher, marketer, and legal specialist agents |
| [`azure_ai_agent_with_local_tool`](./azure_ai_agent_with_local_tool/) | Azure AI Foundry project-backed agent with local Python tool execution for Seattle hotel search |
| [`azure_ai_agents_in_workflow`](./azure_ai_agents_in_workflow/) | Azure AI Foundry project-backed Writer/Reviewer workflow |

## Two Configuration Models

These samples fall into two groups:

### Azure OpenAI hosted agent samples

These use `AzureOpenAIChatClient(...).as_agent(...)` with `DefaultAzureCredential`:

- [`agent_with_hosted_mcp`](./agent_with_hosted_mcp/)
- [`agent_with_text_search_rag`](./agent_with_text_search_rag/)
- [`agents_in_workflow`](./agents_in_workflow/)

Required environment variables:

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | Chat model deployment name |

### Azure AI Foundry project-backed samples

These use `AzureAIProjectAgentProvider` and create agents against a Foundry project:

- [`azure_ai_agent_with_local_tool`](./azure_ai_agent_with_local_tool/)
- [`azure_ai_agents_in_workflow`](./azure_ai_agents_in_workflow/)

Required environment variables:

| Variable | Description |
|----------|-------------|
| `PROJECT_ENDPOINT` | Foundry project endpoint, for example `https://<resource>.services.ai.azure.com/api/projects/<project>` |
| `MODEL_DEPLOYMENT_NAME` | Model deployment name in that Foundry project |

## Common Prerequisites

Before running any sample, ensure you have:

1. Python 3.10 or later
2. [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed
3. Azure access configured for one of these setups:
	 - An Azure OpenAI resource with a chat model deployment
	 - An Azure AI Foundry project with a chat model deployment

### Authenticate with Azure CLI

All samples rely on Azure credentials. For local development, the simplest approach is Azure CLI authentication:

```powershell
az login
az account show
```

Samples using `DefaultAzureCredential` will pick up Azure CLI credentials locally. The Foundry project-backed samples use `AzureCliCredential` locally and switch to managed identity automatically when running in Azure.

## Running a Sample

Each sample folder contains its own `requirements.txt`. Run commands from the specific sample directory you want to try.

### Recommended: `uv`

The sample dependencies include preview packages, so allow prerelease installs:

```powershell
cd <sample-directory>
uv venv .venv
uv pip install --prerelease=allow -r requirements.txt
uv run main.py
```

### Alternative: `venv`

Windows PowerShell:

```powershell
cd <sample-directory>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

macOS/Linux:

```bash
cd <sample-directory>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Each sample starts a hosted agent locally on `http://localhost:8088/`.

## Environment Variable Setup

You can either export variables in your shell or create a local `.env` file in the sample directory.

### Azure OpenAI samples

Example `.env`:

```dotenv
AZURE_OPENAI_ENDPOINT=https://<your-openai-resource>.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4o-mini
```

### Azure AI Foundry project-backed samples

Example `.env`:

```dotenv
PROJECT_ENDPOINT=https://<your-resource>.services.ai.azure.com/api/projects/<your-project>
MODEL_DEPLOYMENT_NAME=gpt-4.1-mini
```

## Interacting with the Agent

After starting a sample, send requests to the Responses endpoint.

PowerShell:

```powershell
$body = @{
		input = "Your question here"
		stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8088/responses" -Method Post -Body $body -ContentType "application/json"
```

curl:

```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
	-d '{"input":"Your question here","stream":false}'
```

Example prompts by sample:

| Sample | Example input |
|--------|---------------|
| `agent_with_hosted_mcp` | `What does Microsoft Learn say about managed identities in Azure?` |
| `agent_with_text_search_rag` | `What is Contoso Outdoors' return policy for refunds?` |
| `agents_in_workflow` | `Create a launch strategy for a budget-friendly electric SUV.` |
| `azure_ai_agent_with_local_tool` | `Find me Seattle hotels from 2025-03-15 to 2025-03-18 under $200 per night.` |
| `azure_ai_agents_in_workflow` | `Write a slogan for a new affordable electric SUV.` |

## Deploying to Microsoft Foundry

Each sample includes a `Dockerfile` and `agent.yaml` for deployment. For deployment steps, follow the hosted agents guidance in Microsoft Foundry:

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents)
- [Create a hosted agent with CLI](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?tabs=cli#create-a-hosted-agent)

## Troubleshooting

### Missing Azure credentials

If startup fails with authentication errors, run `az login` and verify the selected subscription with `az account show`.

### Missing `PROJECT_ENDPOINT`

The Foundry project-backed samples require `PROJECT_ENDPOINT` and `MODEL_DEPLOYMENT_NAME`. Make sure both are set before running:

- [`azure_ai_agent_with_local_tool`](./azure_ai_agent_with_local_tool/)
- [`azure_ai_agents_in_workflow`](./azure_ai_agents_in_workflow/)

### Missing `AZURE_OPENAI_ENDPOINT` or deployment name

The Azure OpenAI-based samples require `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`:

- [`agent_with_hosted_mcp`](./agent_with_hosted_mcp/)
- [`agent_with_text_search_rag`](./agent_with_text_search_rag/)
- [`agents_in_workflow`](./agents_in_workflow/)

### Preview package install issues

These samples depend on preview packages such as `azure-ai-agentserver-agentframework`. Use `uv pip install --prerelease=allow -r requirements.txt` or `pip install -r requirements.txt`.

### ARM64 container images fail after deployment

If you build images locally on ARM64 hardware such as Apple Silicon, build for `linux/amd64`:

```bash
docker build --platform=linux/amd64 -t image .
```
