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

### Workflow Hosting Patterns
- **[08_workflow](08_workflow/)**: Host a MAF `Workflow` as a durable orchestration on a standalone worker via `DurableAIAgentWorker.configure_workflow`. Demonstrates conditional routing and mixing AI agents with non-agent executors.
- **[09_workflow_hitl](09_workflow_hitl/)**: A workflow that pauses for human approval using `ctx.request_info` / `@response_handler`, with the client discovering and answering the pending request.
- **[10_workflow_streaming](10_workflow_streaming/)**: Stream a hosted workflow's events as typed `WorkflowEvent` objects by polling the orchestration's custom status.
- **[11_subworkflow](11_subworkflow/)**: Compose workflows by embedding an inner `Workflow` as a node via `WorkflowExecutor`. On the durable host the inner workflow runs as its own child orchestration, and a single `configure_workflow` call registers both.
- **[12_subworkflow_hitl](12_subworkflow_hitl/)**: A human-in-the-loop pause that lives **inside a sub-workflow**. The nested request surfaces to the client with a qualified request id (`{executor}::{requestId}`) behind a single top-level addressing surface.

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
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
export FOUNDRY_MODEL="your-deployment-name"
```

PowerShell:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
$env:FOUNDRY_MODEL="your-deployment-name"
```

### Installing Dependencies

Navigate to the sample directory and install dependencies. For example:

```bash
cd samples/04-hosting/durabletask/01_single_agent
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

