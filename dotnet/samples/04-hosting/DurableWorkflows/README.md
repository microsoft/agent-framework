# Durable Workflow Samples

This directory contains samples demonstrating how to build durable workflows using the Microsoft Agent Framework.

## Environment Setup

### Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0) or later
- [Durable Task Scheduler](https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-task-scheduler/durable-task-scheduler) running locally or in Azure

### Running the Durable Task Scheduler Emulator

To run the emulator locally using Docker:

```bash
docker run -d -p 8080:8080 --name durabletask-emulator mcr.microsoft.com/durabletask/emulator:latest
```

Set the connection string environment variable to point to the local emulator:

```bash
# Linux/macOS
export DURABLE_TASK_SCHEDULER_CONNECTION_STRING="AccountEndpoint=http://localhost:8080"

# Windows (PowerShell)
$env:DURABLE_TASK_SCHEDULER_CONNECTION_STRING = "AccountEndpoint=http://localhost:8080"
```

## Samples

### Console Apps

| Sample | Description |
|--------|-------------|
| [01_SequentialWorkflow](ConsoleApps/01_SequentialWorkflow/) | Basic sequential workflow with ordered executor steps |
| [02_ConcurrentWorkflow](ConsoleApps/02_ConcurrentWorkflow/) | Fan-out/fan-in concurrent workflow execution |
| [03_ConditionalEdges](ConsoleApps/03_ConditionalEdges/) | Workflows with conditional routing between executors |
| [05_WorkflowEvents](ConsoleApps/05_WorkflowEvents/) | Publishing and subscribing to workflow events |
| [06_WorkflowSharedState](ConsoleApps/06_WorkflowSharedState/) | Sharing state across workflow executors |
| [07_SubWorkflows](ConsoleApps/07_SubWorkflows/) | Nested sub-workflow composition |
| [08_WorkflowHITL](ConsoleApps/08_WorkflowHITL/) | Human-in-the-loop workflow with approval gates |

### Azure Functions

| Sample | Description |
|--------|-------------|
| [01_SequentialWorkflow](AzureFunctions/01_SequentialWorkflow/) | Sequential workflow hosted in Azure Functions |
| [02_ConcurrentWorkflow](AzureFunctions/02_ConcurrentWorkflow/) | Concurrent workflow hosted in Azure Functions |
| [03_WorkflowHITL](AzureFunctions/03_WorkflowHITL/) | Human-in-the-loop workflow hosted in Azure Functions |
