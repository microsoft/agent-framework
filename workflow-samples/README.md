# Declarative Workflows

This folder contains sample workflow definitions than be ran using the
[Declarative Workflow](../dotnet/samples/GettingStarted/Workflows/Declarative/ExecuteWorkflow) demo.

Each workflow is defined in a single YAML file and contains 
comments with additional information specific to that workflow.

A _Declarative Workflow_ may be executed locally no different from any `Workflow` defined by code.  
The difference is that the workflow definition is loaded from a YAML file instead of being defined in code.

```c#
Workflow<string> workflow = DeclarativeWorkflowBuilder.Build<string>("Marketing.yaml", options);
```

Workflows may also be hosted in your _Azure Foundry Project_.

> _Python_ support in the works!

#### Agents

The sample workflows rely on agents defined in your Azure Foundry Project.

To create agents, run the [`Create.ps1`](./setup) script.
This will create the agents used in the sample workflows in your Azure Foundry Project and format a script you can copy and use to configure your environment.

> Note: `Create.ps1` relies upon the `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT_NAME`, and `FOUNDRY_CONNECTION_GROUNDING_TOOL` settings.
See [README.md](../dotnet/samples/GettingStarted/Workflows/Declarative/README.md) from the demo for configuration details.
