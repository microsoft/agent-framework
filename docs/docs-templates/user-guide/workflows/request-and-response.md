# Microsoft Agent Framework Workflows: Request and Response

This page provides an overview of how **Request and Response** handling works in the Microsoft Agent Framework Workflow system.

## Overview

Executors in a workflow can send requests to outside of the workflow and wait for responses. This is useful for scenarios where an executor needs to interact with external systems, such as human-in-the-loop interactions, or any other asynchronous operations.

::: zone pivot="programming-language-csharp"

## Enable Request and Response Handling in a Workflow

Requests and responses are handled via a special type called `InputPort`.

```csharp
// Create an input port that receives requests of type CustomRequestType and responses of type CustomResponseType.
var inputPort = InputPort.Create<CustomRequestType, CustomResponseType>("input-port");
```

Add the input port to a workflow.

```csharp
var executorA = new SomeExecutor();
var workflow = new WorkflowBuilder(inputPort)
    .AddEdge(inputPort, executorA)
    .AddEdge(executorA, inputPort)
    .Build<CustomRequestType>();
```

Now, because in the workflow we have `executorA` connected to the `inputPort` in both directions, `executorA` needs to be able to send requests and receive responses via the `inputPort`. Here is what we need to do in `SomeExecutor` to send a request and receive a response.

```csharp
internal sealed class SomeExecutor() : ReflectingExecutor<SomeExecutor>("SomeExecutor"), IMessageHandler<CustomResponseType>
{
    public async ValueTask HandleAsync(CustomResponseType message, IWorkflowContext context)
    {
        // Process the response...
        ...
        // Send a request
        await context.SendMessageAsync(new CustomRequestType(...)).ConfigureAwait(false);
    }
}
```

Alternatively, `SomeExecutor` can separate the request sending and response handling into two handlers.

```csharp

internal sealed class SomeExecutor() : ReflectingExecutor<SomeExecutor>("SomeExecutor"), IMessageHandler<CustomResponseType>, IMessageHandler<OtherDataType>
{
    public async ValueTask HandleAsync(CustomResponseType message, IWorkflowContext context)
    {
        // Process the response...
        ...
    }

    public async ValueTask HandleAsync(OtherDataType message, IWorkflowContext context)
    {
        // Process the message...
        ...
        // Send a request
        await context.SendMessageAsync(new CustomRequestType(...)).ConfigureAwait(false);
    }
}

```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

## Handling Requests and Responses

::: zone pivot="programming-language-csharp"

An `InputPort` emits a `RequestInfoEvent` when it receives a request. You can subscribe to these events to handle incoming requests from the workflow. When you receive a response from an external system, send it back to the workflow using the response mechanism. The framework automatically routes the response to the executor that sent the original request.

```csharp
StreamingRun handle = await InProcessExecution.StreamAsync(workflow, input).ConfigureAwait(false);
await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
{
    switch (evt)
    {
        case RequestInfoEvent requestInputEvt:
            // Handle `RequestInfoEvent` from the workflow
            ExternalResponse response = requestInputEvt.Request.CreateResponse<CustomResponseType>(...);
            await handle.SendResponseAsync(response).ConfigureAwait(false);
            break;

        case WorkflowCompletedEvent workflowCompleteEvt:
            // The workflow has completed successfully
            Console.WriteLine($"Workflow completed with result: {workflowCompleteEvt.Data}");
            return;
    }
}
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

## Checkpoints and Requests

To learn more about checkpoints, please refer to this [page](./checkpointing.md).

When a checkpoint is created, pending requests are also saved as part of the checkpoint state. When you restore from a checkpoint, any pending requests will be re-emitted, allowing the workflow to continue processing from where it left off.

## Next Steps

- [Learn how to use agents in workflows](./using-agents.md) to build intelligent workflows.
- [Learn how to use workflows as agents](./as-agents.md).
- [Learn how to manage state](./shared-states.md) in workflows.
- [Learn how to create checkpoints and resume from them](./checkpointing.md).
