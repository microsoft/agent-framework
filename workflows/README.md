# No-Code Workflows

This folder contains sample workflow definitions than be ran using the
[Declarative Workflow](./dotnet/demos/DeclarativeWorkflow) demo.

Each workflow is defined in a single YAML file and contains 
comments with additional information specific to that workflow.

A _Declarative Workflow_ may be executed locally no different from any `Workflow` defined by code.  
The difference is that the workflow definition is loaded from a YAML file instead of being defined in code.

```c#
Workflow<string> workflow = DeclarativeWorkflowBuilder.Build<string>("HelloWorld.yaml", options);
```

Workflows may also be hosted in your _Azure Foundry Project_.

> _Python_ support in the works!