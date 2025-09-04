# Agent Definitions

The sample workflows rely on agents defined in your Azure Foundry Project.

These agent definitions are based on _Semantic Kernel_'s _Declarative Agent_ feature:

- [Semantic Kernel Agents](https://github.com/microsoft/semantic-kernel/tree/main/dotnet/src/Agents)
- [Declarative Agent Extensions](https://github.com/microsoft/semantic-kernel/tree/main/dotnet/src/Agents/Yaml)
- [Sample](https://github.com/microsoft/semantic-kernel/blob/main/dotnet/samples/GettingStartedWithAgents/AzureAIAgent/Step08_AzureAIAgent_Declarative.cs)

To create agents, run the [`Create.ps1`](./Create.ps1) script.
This will create the agents for the sample workflows in your Azure Foundry Project and format a script you can copy and use to configure your environment.

> Note: `Create.ps1` relies upon the `FOUNDRY_PROJECT_ENDPOINT` setting.  See [README.md](../../dotnet/demos/DeclarativeWorkflow/README.md) from the demo for configuration details.
