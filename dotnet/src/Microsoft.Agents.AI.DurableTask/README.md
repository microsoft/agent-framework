# Microsoft.Agents.AI.DurableTask

The Microsoft Agent Framework provides a programming model for building agents and agent workflows in .NET. This package, the *Durable Task extension for the Agent Framework*, extends the Agent Framework programming model with the following capabilities:

- Stateful, durable execution of agents in distributed environments
- Automatic conversation history management
- Long-running agent workflows as "durable orchestrator" functions
- Tools and dashboards for managing and monitoring agents and agent workflows

These capabilities are implemented using foundational technologies from the Durable Task technology stack:

- [Durable Entities](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-entities) for stateful, durable execution of agents
- [Durable Orchestrations](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-orchestrations) for long-running agent workflows
- The [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/choose-orchestration-framework) for managing durable task execution and observability at scale

This package can be used by itself or in conjunction with the `Microsoft.Agents.AI.Hosting.AzureFunctions` package, which provides additional features via Azure Functions integration.

## Install the package

From the command-line:

```bash
dotnet add package Microsoft.Agents.AI.DurableTask
```

Or directly in your project file:

```xml
<ItemGroup>
  <PackageReference Include="Microsoft.Agents.AI.DurableTask" Version="[CURRENTVERSION]" />
</ItemGroup>
```

You can alternatively just reference the `Microsoft.Agents.AI.Hosting.AzureFunctions` package if you're hosting your agents and orchestrations in the Azure Functions .NET Isolated worker.

## Usage Examples

For a comprehensive tour of all the functionality, concepts, and APIs, check out the [Azure Functions samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/).

## Feedback & Contributing

We welcome feedback and contributions in [our GitHub repo](https://github.com/microsoft/agent-framework).
