# Azure Functions Samples

This directory contains samples for Azure Functions.

- **[01_SingleAgent](01_SingleAgent)**: A sample that demonstrates how to host a single conversational agent in an Azure Functions app and invoke it directly over HTTP.
- **[02_AgentOrchestration_Chaining](02_AgentOrchestration_Chaining)**: A sample that demonstrates how to host a single conversational agent in an Azure Functions app and invoke it using a durable orchestration.
- **[03_AgentOrchestration_Concurrency](03_AgentOrchestration_Concurrency)**: A sample that demonstrates how to host multiple agents in an Azure Functions app and run them concurrently using a durable orchestration.
- **[04_AgentOrchestration_Conditionals](04_AgentOrchestration_Conditionals)**: A sample that demonstrates how to host multiple agents in an Azure Functions app and run them sequentially using a durable orchestration with conditionals.
- **[05_AgentOrchestration_HITL](05_AgentOrchestration_HITL)**: A sample that demonstrates how to implement a human-in-the-loop workflow using durable orchestration, including external event handling for human approval.
- **[06_LongRunningTools](06_LongRunningTools)**: A sample that demonstrates how agents can start and interact with durable orchestrations from tool calls to enable long-running tool scenarios.
- **[07_AgentAsMcpTool](07_AgentAsMcpTool)**: A sample that demonstrates how to configure durable AI agents to be accessible as Model Context Protocol (MCP) tools.

## Running the Samples

These samples are designed to be run locally in a cloned repository.

### Prerequisites

The following prerequisites are required to run the samples:

- [.NET 9.0 SDK or later](https://dotnet.microsoft.com/download/dotnet)
- [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local) (version 4.x or later)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed and authenticated (`az login`) or an API key for the Azure OpenAI service
- [Azure OpenAI Service](https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource) with a deployed model (gpt-4o-mini or better is recommended)
- [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/develop-with-durable-task-scheduler) (local emulator or Azure-hosted)
- [Docker](https://docs.docker.com/get-docker/) installed if running the Durable Task Scheduler emulator locally

### Configuring RBAC Permissions for Azure OpenAI

These samples are configured to use the Azure OpenAI service with RBAC permissions to access the model. You'll need to configure the RBAC permissions for the Azure OpenAI service to allow the Azure Functions app to access the model.

Below is an example of how to configure the RBAC permissions for the Azure OpenAI service to allow the current user to access the model.

Bash (Linux/macOS/WSL):

```bash
az role assignment create \
    --assignee "yourname@contoso.com" \
    --role "Cognitive Services OpenAI User" \
    --scope /subscriptions/<your-subscription-id>/resourceGroups/<your-resource-group-name>/providers/Microsoft.CognitiveServices/accounts/<your-openai-resource-name>
```

PowerShell:

```powershell
az role assignment create `
    --assignee "yourname@contoso.com" `
    --role "Cognitive Services OpenAI User" `
    --scope /subscriptions/<your-subscription-id>/resourceGroups/<your-resource-group-name>/providers/Microsoft.CognitiveServices/accounts/<your-openai-resource-name>
```

More information on how to configure RBAC permissions for Azure OpenAI can be found in the [Azure OpenAI documentation](https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource?pivots=cli).

### Setting an API key for the Azure OpenAI service

As an alternative to configuring Azure RBAC permissions, you can set an API key for the Azure OpenAI service by setting the `AZURE_OPENAI_KEY` environment variable.

Bash (Linux/macOS/WSL):

```bash
export AZURE_OPENAI_KEY="your-api-key"
```

PowerShell:

```powershell
$env:AZURE_OPENAI_KEY="your-api-key"
```

### Start Durable Task Scheduler

Most samples use the Durable Task Scheduler (DTS) to support hosted agents and durable orchestrations. DTS also allows you to view the status of orchestrations and their inputs and outputs from a web UI.

To run the Durable Task Scheduler locally, you can use the following `docker` command:

```bash
docker run -d --name dts-emulator -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
```

The DTS dashboard will be available at `http://localhost:8080`.

### Start the Azure Storage Emulator

All Function apps require an Azure Storage account to store functions-specific state. You can use the Azure Storage Emulator to run a local instance of the Azure Storage service.

You can run the Azure Storage emulator locally as a standalone process or via a Docker container.

#### Docker

```bash
docker run -d --name storage-emulator -p 10000:10000 -p 10001:10001 -p 10002:10002 mcr.microsoft.com/azure-storage/azurite
```

#### Standalone

```bash
npm install -g azurite
azurite
```

### Environment Configuration

Each sample has its own `local.settings.json` file that contains the environment variables for the sample. You'll need to update the `local.settings.json` file with the correct values for your Azure OpenAI resource.

```json
{
  "Values": {
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT": "your-deployment-name"
  }
}
```

Alternatively, you can set the environment variables in the command line.

### Bash (Linux/macOS/WSL)

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="your-deployment-name"
```

### PowerShell

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT="your-deployment-name"
```

These environment variables, when set, will override the values in the `local.settings.json` file, making it convenient to test the sample without having to update the `local.settings.json` file.

### Start the Azure Functions app

Navigate to the sample directory and start the Azure Functions app:

```bash
cd dotnet/samples/AzureFunctions/01_SingleAgent
func start
```

The Azure Functions app will be available at `http://localhost:7071`.

### Test the Azure Functions app

The README.md file in each sample directory contains instructions for testing the sample. Each sample also includes a `demo.http` file that can be used to test the sample from the command line. These files can be opened in VS Code with the [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) extension or in the Visual Studio IDE.

### Viewing the sample output

The Azure Functions app logs are displayed in the terminal where you ran `func start`. This is where most agent output will be displayed. You can adjust logging levels in the `host.json` file as needed.

You can also see the state of agents and orchestrations in the DTS dashboard.
