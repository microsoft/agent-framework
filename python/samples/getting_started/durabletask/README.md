# Durable Task Samples

This directory contains samples for durable agent hosting using the Durable Task Scheduler. These samples demonstrate the worker-client architecture pattern, enabling distributed agent execution with persistent conversation state.

## Sample Catalog

### Basic Patterns
- **[01_single_agent](01_single_agent/)**: Host a single conversational agent and interact with it via a client. Demonstrates basic worker-client architecture and agent state management.
- **[02_multi_agent](02_multi_agent/)**: Host multiple domain-specific agents (physicist and chemist) and route requests to the appropriate agent based on the question topic.
- **[03_single_agent_streaming](03_single_agent_streaming/)**: Enable reliable, resumable streaming using Redis Streams with agent response callbacks. Demonstrates non-blocking agent execution and cursor-based resumption for disconnected clients.

### Orchestration Patterns
- **[04_single_agent_orchestration_chaining](04_single_agent_orchestration_chaining/)**: Chain multiple invocations of the same agent using durable orchestration, preserving conversation context across sequential runs.
- **[05_multi_agent_orchestration_concurrency](05_multi_agent_orchestration_concurrency/)**: Run multiple agents concurrently within an orchestration, aggregating their responses in parallel.
- **[06_multi_agent_orchestration_conditionals](06_multi_agent_orchestration_conditionals/)**: Implement conditional branching in orchestrations with spam detection and email assistant agents. Demonstrates structured outputs with Pydantic models and activity functions for side effects.
- **[07_single_agent_orchestration_hitl](07_single_agent_orchestration_hitl/)**: Human-in-the-loop pattern with external event handling, timeouts, and iterative refinement based on human feedback. Shows long-running workflows with external interactions.

## Running the Samples

These samples are designed to be run locally in a cloned repository.

### Prerequisites

The following prerequisites are required to run the samples:

- [Python 3.9 or later](https://www.python.org/downloads/)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed and authenticated (`az login`) or an API key for the Azure OpenAI service
- [Azure OpenAI Service](https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource) with a deployed model (gpt-4o-mini or better is recommended)
- [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/develop-with-durable-task-scheduler) (local emulator or Azure-hosted)
- [Docker](https://docs.docker.com/get-docker/) installed if running the Durable Task Scheduler emulator locally

### Configuring RBAC Permissions for Azure OpenAI

These samples are configured to use the Azure OpenAI service with RBAC permissions to access the model. You'll need to configure the RBAC permissions for the Azure OpenAI service to allow the Python app to access the model.

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

The DTS dashboard will be available at `http://localhost:8082`.

### Environment Configuration

Each sample reads configuration from environment variables. You'll need to set the following environment variables:

Bash (Linux/macOS/WSL):

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="your-deployment-name"
```

PowerShell:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="your-deployment-name"
```

### Installing Dependencies

Navigate to the sample directory and install dependencies. For example:

```bash
cd samples/getting_started/durabletask/01_single_agent
pip install -r requirements.txt
```

If you're using `uv` for package management:

```bash
uv pip install -r requirements.txt
```

### Running the Samples

Each sample follows a worker-client architecture. Most samples provide separate `worker.py` and `client.py` files, though some include a combined `sample.py` for convenience.

**Running with separate worker and client:**

In one terminal, start the worker:

```bash
python worker.py
```

In another terminal, run the client:

```bash
python client.py
```

**Running with combined sample:**

```bash
python sample.py
```

### Viewing the Sample Output

The sample output is displayed directly in the terminal where you ran the Python script. Agent responses are printed to stdout with log formatting for better readability.

You can also see the state of agents and orchestrations in the Durable Task Scheduler dashboard at `http://localhost:8082`.

