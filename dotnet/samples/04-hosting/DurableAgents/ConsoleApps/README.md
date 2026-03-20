# Console App Samples

This directory contains samples for console app hosting of durable agents. These samples use standard I/O (stdin/stdout) for interaction, making them both interactive and scriptable.

- **[01_SingleAgent](01_SingleAgent)**: A sample that demonstrates how to host a single conversational agent in a console app and interact with it via stdin/stdout.
- **[02_AgentOrchestration_Chaining](02_AgentOrchestration_Chaining)**: A sample that demonstrates how to host a single conversational agent in a console app and invoke it using a durable orchestration.
- **[03_AgentOrchestration_Concurrency](03_AgentOrchestration_Concurrency)**: A sample that demonstrates how to host multiple agents in a console app and run them concurrently using a durable orchestration.
- **[04_AgentOrchestration_Conditionals](04_AgentOrchestration_Conditionals)**: A sample that demonstrates how to host multiple agents in a console app and run them sequentially using a durable orchestration with conditionals.
- **[05_AgentOrchestration_HITL](05_AgentOrchestration_HITL)**: A sample that demonstrates how to implement a human-in-the-loop workflow using durable orchestration, including interactive approval prompts.
- **[06_LongRunningTools](06_LongRunningTools)**: A sample that demonstrates how agents can start and interact with durable orchestrations from tool calls to enable long-running tool scenarios.
- **[07_ReliableStreaming](07_ReliableStreaming)**: A sample that demonstrates how to implement reliable streaming for durable agents using Redis Streams, enabling clients to disconnect and reconnect without losing messages.

## Running the Samples

These samples are designed to be run locally in a cloned repository.

### Prerequisites

The following prerequisites are required to run the samples:

- [.NET 10.0 SDK or later](https://dotnet.microsoft.com/download/dotnet)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed and authenticated (`az login`) or an API key for the Azure OpenAI service
- [Azure OpenAI Service](https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource) with a deployed model (gpt-4o-mini or better is recommended)
- [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/develop-with-durable-task-scheduler) (local emulator or Azure-hosted)
- [Docker](https://docs.docker.com/get-docker/) installed if running the Durable Task Scheduler emulator locally
- [Redis](https://redis.io/) (for sample 07 only) - can be run locally using Docker

### Configuring RBAC Permissions for Azure OpenAI

These samples are configured to use the Azure OpenAI service with RBAC permissions to access the model. You'll need to configure the RBAC permissions for the Azure OpenAI service to allow the console app to access the model.

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

As an alternative to configuring Azure RBAC permissions, you can set an API key for the Azure OpenAI service by setting the `AZURE_OPENAI_API_KEY` environment variable.

Bash (Linux/macOS/WSL):

```bash
export AZURE_OPENAI_API_KEY="your-api-key"
```

PowerShell:

```powershell
$env:AZURE_OPENAI_API_KEY="your-api-key"
```

### Start Durable Task Scheduler

Most samples use the Durable Task Scheduler (DTS) to support hosted agents and durable orchestrations. DTS also allows you to view the status of orchestrations and their inputs and outputs from a web UI.

To run the Durable Task Scheduler locally, you can use the following `docker` command:

```bash
docker run -d --name dts-emulator -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
```

The DTS dashboard will be available at `http://localhost:8080`.

### Environment Configuration

Each sample reads configuration from environment variables. You'll need to set the following environment variables:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="your-deployment-name"
```

### Running the Console Apps

Navigate to the sample directory and run the console app:

```bash
cd dotnet/samples/04-hosting/DurableAgents/ConsoleApps/01_SingleAgent
dotnet run --framework net10.0
```

> [!NOTE]
> The `--framework` option is required to specify the target framework for the console app because the samples are designed to support multiple target frameworks. If you are using a different target framework, you can specify it with the `--framework` option.

The app will prompt you for input via stdin.

### Viewing the sample output

The console app output is displayed directly in the terminal where you ran `dotnet run`. Agent responses are printed to stdout with subtle color coding for better readability.

You can also see the state of agents and orchestrations in the Durable Task Scheduler dashboard at `http://localhost:8082`.
