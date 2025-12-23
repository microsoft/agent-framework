# Declarative Workflows

A _Declarative Workflow_ is defined as a single YAML file and
may be executed locally no different from any regular `Workflow` that is defined by code.

The difference is that the workflow definition is loaded from a YAML file instead of being defined in code:

```c#
Workflow workflow = DeclarativeWorkflowBuilder.Build("Marketing.yaml", options);
```

These example workflows may be executed by the workflow
[Samples](../dotnet/samples/GettingStarted/Workflows/Declarative)
that are present in this repository.

> See the [README.md](../dotnet/samples/GettingStarted/Workflows/Declarative/README.md) 
 associated with the samples for configuration details.
