**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates a **key advantage of code-based hosted agents**:

- **Local Python tool execution** - Run custom Python functions as agent tools

Code-based agents can execute **any Python code** you write. This sample includes a Seattle Hotel Agent with a `get_available_hotels` tool that searches for available hotels based on check-in/check-out dates and budget preferences.

The agent is hosted using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/) and can be deployed to Microsoft Foundry.

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

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. **Microsoft Foundry Project**
   - A Microsoft Project created.
   - Chat model deployed (e.g., `gpt-4o` or `gpt-4.1`).
   - Note your project endpoint URL and model deployment name.

2. **Azure CLI**
   - Installed and authenticated
   - Run `az login` and verify with `az account show`

3. **Python 3.10 or higher**
   - Verify your version: `python --version`
   - If you have Python 3.9 or older, install a newer version:
     - Windows: `winget install Python.Python.3.12`
     - macOS: `brew install python@3.12`
     - Linux: Use your package manager

### Environment Variables

Set the following environment variables:

- `PROJECT_ENDPOINT` - Your Microsoft Foundry project endpoint URL (required)
- `MODEL_DEPLOYMENT_NAME` - The deployment name for your chat model (defaults to `gpt-4.1-mini`)

This sample loads environment variables from a local `.env` file if present.

Create a `.env` file in this directory with the following content:

```
PROJECT_ENDPOINT=https://<your-resource>.services.ai.azure.com/api/projects/<your-project>
MODEL_DEPLOYMENT_NAME=gpt-4.1-mini
```

Or set them via PowerShell:

```powershell
# Replace with your actual values
$env:PROJECT_ENDPOINT="https://<your-resource>.services.ai.azure.com/api/projects/<your-project>"
$env:MODEL_DEPLOYMENT_NAME="gpt-4.1-mini"
```

### Setting Up a Virtual Environment

It's recommended to use a virtual environment to isolate project dependencies:

**macOS/Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Installing Dependencies

Install the required Python dependencies using pip:

```bash
pip install -r requirements.txt
```

The required packages are:

- `azure-ai-agentserver-agentframework` - Agent Framework and AgentServer SDK

### Running the Sample

#### Option 1: Press F5 (Recommended)

Press **F5** in VS Code to start debugging. Alternatively, you can use the VS Code debug menu:

1. Open the **Run and Debug** view (Ctrl+Shift+D / Cmd+Shift+D)
2. Select **"Debug Local Workflow HTTP Server"** from the dropdown
3. Click the green **Start Debugging** button (or press F5)

This will:

1. Start the HTTP server with debugging enabled
2. Open the AI Toolkit Agent Inspector for interactive testing
3. Allow you to set breakpoints and inspect the workflow

#### Option 2: Run in Terminal

Run as HTTP server (default):

```bash
python main.py
```

This will start the hosted agent locally on `http://localhost:8088/`.

**PowerShell (Windows):**

```powershell
$body = @{
   input = "I need a hotel in Seattle from 2025-03-15 to 2025-03-18, budget under `$200 per night"
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

## Deploying the Agent to Microsoft Foundry

To deploy the hosted agent:

1. Open the VS Code Command Palette and run the `Microsoft Foundry: Deploy Hosted Agent` command.

2. Follow the interactive deployment prompts. The extension will help you select or create the container files it needs:
   - It first looks for a Dockerfile at the repository root. If not found, you can select an existing Dockerfile or generate a new one.
   - If you choose to generate a Dockerfile, the extension will place the files at the repo root and open the Dockerfile in the editor; the deployment flow is intentionally cancelled in that case so you can review and edit the generated files before re-running the deploy command.

3. After deployment completes, the hosted agent appears under the `Hosted Agents (Preview)` section of the extension tree. You can select the agent there to view details and test it using the integrated playground.

**What the deploy flow does for you:**

- Creates or obtains an Azure Container Registry for the target project.
- Builds and pushes a container image from your workspace (the build packages the workspace respecting `.dockerignore`).
- Creates an agent version in Microsoft Foundry using the built image. If a `.env` file exists at the workspace root, the extension will parse it and include its key/value pairs as the hosted agent's environment variables in the create request (these variables will be available to the agent runtime).
- Starts the agent container on the project's capability host. If the capability host is not provisioned, the extension will prompt you to enable it and will guide you through creating it.

### MSI Configuration in the Azure Portal

This sample requires the Microsoft Foundry Project to authenticate using a Managed Identity when running remotely in Azure. Grant the project's managed identity the required permissions by assigning the built-in [Azure AI User](https://aka.ms/foundry-ext-project-role) role.

To configure the Managed Identity:

1. In the Azure Portal, open the Foundry Project.
2. Select "Access control (IAM)" from the left-hand menu.
3. Click "Add" and choose "Add role assignment".
4. In the role selection, search for and select "Azure AI User", then click "Next".
5. For "Assign access to", choose "Managed identity".
6. Click "Select members", locate the managed identity associated with your Foundry Project (you can search by the project name), then click "Select".
7. Click "Review + assign" to complete the assignment.
8. Allow a few minutes for the role assignment to propagate before running the application.

## Additional Resources

- [Microsoft Agents Framework](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview)
- [Managed Identities for Azure Resources](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/)
