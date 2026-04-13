**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates a **key advantage of code-based hosted agents**:

- **Local Python tool execution** - Run custom Python functions as agent tools

Code-based agents can execute **any Python code** you write. This sample includes a Seattle Hotel Agent with a `get_available_hotels` tool that searches for available hotels based on check-in/check-out dates and budget preferences.

The agent is hosted using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/) and can be deployed to Microsoft Foundry using the Azure Developer CLI.

## How It Works

### Local Tools Integration

In [main.py](main.py), the agent uses a local Python function (`get_available_hotels`) that simulates a hotel availability API. This demonstrates how code-based agents can execute custom server-side logic that prompt agents cannot access.

The tool accepts:

- **check_in_date** - Check-in date in YYYY-MM-DD format
- **check_out_date** - Check-out date in YYYY-MM-DD format
- **max_price** - Maximum price per night in USD (optional, defaults to $500)

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/),
which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

### Agent Deployment

The hosted agent can be deployed to Microsoft Foundry using the Azure Developer CLI [ai agent](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli#create-a-hosted-agent) extension.

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. **Microsoft Foundry Project**
   - Project created in [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-foundry?view=foundry#microsoft-foundry-portals)
   - Chat model deployed (e.g., `gpt-4o` or `gpt-4.1`)
   - Note your project endpoint URL and model deployment name

2. **Azure CLI**
   - Installed and authenticated
   - Run `az login` and verify with `az account show`

3. **Python 3.10 or higher**
   - Verify your version: `python --version`

### Environment Variables

Set the following environment variables (matching `agent.yaml`):

- `FOUNDRY_PROJECT_ENDPOINT` - Your Microsoft Foundry project endpoint URL (required)
- `FOUNDRY_MODEL` - The deployment name for your chat model (defaults to `gpt-4.1-mini`)

This sample loads environment variables from a local `.env` file if present.

Create a `.env` file in this directory with the following content:

```
FOUNDRY_PROJECT_ENDPOINT=https://<your-resource>.services.ai.azure.com/api/projects/<your-project>
FOUNDRY_MODEL=gpt-4.1-mini
```

Or set them via PowerShell:

```powershell
# Replace with your actual values
$env:FOUNDRY_PROJECT_ENDPOINT="https://<your-resource>.services.ai.azure.com/api/projects/<your-project>"
$env:FOUNDRY_MODEL="gpt-4.1-mini"
```

### Running the Sample

**Recommended (`uv`):**

We recommend using [uv](https://docs.astral.sh/uv/) to create and manage the virtual environment for this sample.

```bash
uv venv .venv
uv pip install --prerelease=allow -r requirements.txt
uv run main.py
```

The sample depends on preview packages, so `--prerelease=allow` is required when installing with `uv`.

**Alternative (`venv`):**

If you do not have `uv` installed, you can use Python's built-in `venv` module instead:

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

**macOS/Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

This will start the hosted agent locally on `http://localhost:8088/`.

### Interacting with the Agent

**PowerShell (Windows):**

```powershell
$body = @{
   input = "I need a hotel in Seattle from 2025-03-15 to 2025-03-18, budget under $200 per night"
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -Body $body -ContentType "application/json"
```

**Bash/curl (Linux/macOS):**

```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
   -d '{"input": "Find me hotels in Seattle for March 20-23, 2025 under $200 per night","stream":false}'
```

The agent will use the `get_available_hotels` tool to search for available hotels matching your criteria.

### Deploying the Agent to Microsoft Foundry

To deploy your agent to Microsoft Foundry, follow the comprehensive deployment guide at https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry&tabs=cli

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

We **recommend using `azd` cloud build**, which always builds images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds**

Use this command to build the image locally:

```shell
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
