# Microsoft Agent Framework Workflows: Using workflows as Agents

This document provides an overview of how to use **Workflows as Agents** in the Microsoft Agent Framework.

## Overview

Developers can turn a workflow into an Agent Framework Agent and interact with the workflow as if it were an agent. This feature enables the following scenarios:

- Integrate workflows with APIs that already support the Agent interface.
- Use a workflow to drive single agent interactions, which can create more powerful agents.
- Close the loop between agents and workflows, creating opportunities for advanced compositions.

## Creating a Workflow Agent

Create a workflow of any complexity and then wrap it as an agent.

::: zone pivot="programming-language-csharp"

```csharp
var workflowAgent = workflow.AsAgent(id: "workflow-agent", name: "Workflow Agent");
var workflowAgentThread = workflowAgent.GetNewThread();
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

## Using a Workflow Agent

Then use the workflow agent like any other Agent Framework agent.

::: zone pivot="programming-language-csharp"

```csharp
await foreach (var update in workflowAgent.RunStreamingAsync(input, workflowAgentThread).ConfigureAwait(false))
{
    Console.WriteLine(update);
}
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

## Next Steps

- [Learn how to use agents in workflows](./using-agents.md) to build intelligent workflows.
- [Learn how to handle requests and responses](./request-and-response.md) in workflows.
- [Learn how to manage state](./shared-states.md) in workflows.
- [Learn how to create checkpoints and resume from them](./checkpointing.md).
